"""The My Wallet integration: portfolios valued via Yahoo Finance."""

from __future__ import annotations

import logging
from math import isfinite
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    ALLOCATION_SYMBOL,
    CONF_CONTRIBUTIONS,
    CONF_DIVIDENDS,
    CONF_INVESTED_AMOUNT,
    CONF_RETIRED_SAVINGS_PLANS,
    CONF_SAVINGS_PLANS,
    CONF_VALORS,
    CONTRIBUTION_SOURCE_LEGACY,
    DIVIDEND_SYMBOL,
    LOT_SYMBOL,
    PLAN_ALLOCATIONS,
    PLAN_ENABLED,
    PLAN_ID,
    PLAN_NAME,
    PLAN_OPENING_CUTOFF_DATE,
    PLATFORMS,
    VALOR_AMOUNT,
    VALOR_SYMBOL,
)
from .contributions import (
    LEGACY_CONTRIBUTION_ID,
    all_lots,
    make_contribution,
    normalize_contributions,
    normalize_date,
    opening_balance_conflicts,
)
from .coordinator import WalletCoordinator
from .dividends import normalize_dividends
from .plans import normalize_plan

_LOGGER = logging.getLogger(__name__)

# Type alias for config entries of this integration.
type MyWalletConfigEntry = ConfigEntry[WalletCoordinator]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register the local, authenticated history panel once per HA instance."""
    from .panel import async_setup_panel

    await async_setup_panel(hass)
    return True


def _normalize_migrated_plan(
    plan: dict[str, Any], today: str
) -> tuple[dict[str, Any], bool, bool]:
    """Normalize one plan, preserving legacy mini-plans in a disabled state."""
    candidate = dict(plan)
    cutoff_clamped = False
    cutoff = candidate.get(PLAN_OPENING_CUTOFF_DATE)
    if cutoff is not None and cutoff != "":
        normalized_cutoff = normalize_date(cutoff)
        if normalized_cutoff > today:
            candidate[PLAN_OPENING_CUTOFF_DATE] = today
            cutoff_clamped = True

    try:
        return normalize_plan(candidate), False, cutoff_clamped
    except ValueError as original_error:
        candidate[PLAN_ENABLED] = False
        try:
            normalized = normalize_plan(candidate)
        except ValueError:
            raise original_error from None
    _LOGGER.warning(
        "Disabled legacy savings plan %s (%s) during migration because its "
        "amount cannot allocate at least one cent to every position",
        normalized.get(PLAN_NAME, candidate.get(PLAN_NAME, "?")),
        normalized.get(PLAN_ID, candidate.get(PLAN_ID, "?")),
    )
    return normalized, True, cutoff_clamped


def _validate_migrated_references(data: dict[str, Any]) -> None:
    """Reject malformed references; keep repairable opening conflicts editable."""
    opening_units: dict[str, float] = {}
    for valor in data.get(CONF_VALORS, []):
        symbol = str(valor[VALOR_SYMBOL]).strip().upper()
        amount = float(valor[VALOR_AMOUNT])
        if not symbol or not isfinite(amount) or amount < 0 or symbol in opening_units:
            raise ValueError("Invalid or duplicate configured valor")
        opening_units[symbol] = amount

    for lot in all_lots(data):
        symbol = lot[LOT_SYMBOL]
        if symbol not in opening_units:
            raise ValueError(f"Purchase lot references missing valor {symbol}")

    for plan in data.get(CONF_SAVINGS_PLANS, []):
        for allocation in plan[PLAN_ALLOCATIONS]:
            symbol = allocation[ALLOCATION_SYMBOL]
            if symbol not in opening_units:
                raise ValueError(f"Savings plan references missing valor {symbol}")
    for dividend in data.get(CONF_DIVIDENDS, []):
        symbol = dividend.get(DIVIDEND_SYMBOL)
        if symbol is not None and symbol not in opening_units:
            raise ValueError(f"Dividend references missing valor {symbol}")


async def async_migrate_entry(hass: HomeAssistant, entry: MyWalletConfigEntry) -> bool:
    """Migrate legacy ledger data and harden savings-plan boundaries."""
    if entry.version > 6:
        _LOGGER.error(
            "Cannot migrate My Wallet config entry from unsupported version %s",
            entry.version,
        )
        return False

    if entry.version == 6:
        return True

    original_version = entry.version
    today = dt_util.now().date().isoformat()
    try:
        data: dict[str, Any] = dict(entry.data)
        if original_version < 4:
            legacy_amount = data.pop(CONF_INVESTED_AMOUNT, None)
            contributions = list(data.get(CONF_CONTRIBUTIONS, []))
            if (
                original_version in (1, 2)
                and not contributions
                and legacy_amount is not None
                and float(legacy_amount) > 0
            ):
                contributions.append(
                    make_contribution(
                        legacy_amount,
                        None,
                        contribution_id=LEGACY_CONTRIBUTION_ID,
                        source=CONTRIBUTION_SOURCE_LEGACY,
                    )
                )
            data[CONF_CONTRIBUTIONS] = contributions

        # Version 4 briefly allowed lot edits that could violate their parent
        # funding date or legacy-opening semantics.  Validate every ledger on
        # the schema boundary instead of loading contradictory cash history.
        # Opening-unit disagreements are different: preserve both versions of
        # the recorded quantities and allow the user to reconcile them in UI.
        data[CONF_CONTRIBUTIONS] = normalize_contributions(
            data.get(CONF_CONTRIBUTIONS, [])
        )
        data[CONF_DIVIDENDS] = normalize_dividends(data.get(CONF_DIVIDENDS, []))

        migrated_plans: list[dict[str, Any]] = []
        disabled_count = 0
        clamped_count = 0
        for plan in data.get(CONF_SAVINGS_PLANS, []):
            migrated, disabled, clamped = _normalize_migrated_plan(dict(plan), today)
            migrated_plans.append(migrated)
            disabled_count += int(disabled)
            clamped_count += int(clamped)
        data[CONF_SAVINGS_PLANS] = migrated_plans
        data[CONF_RETIRED_SAVINGS_PLANS] = [
            _normalize_migrated_plan(dict(plan), today)[0]
            for plan in data.get(CONF_RETIRED_SAVINGS_PLANS, [])
        ]
        _validate_migrated_references(data)
    except (KeyError, TypeError, ValueError, OverflowError) as err:
        _LOGGER.error(
            "Failed to migrate My Wallet config entry from version %s: %s",
            original_version,
            err,
        )
        return False

    conflicts = opening_balance_conflicts(data)
    if conflicts:
        _LOGGER.warning(
            "Preserved opening-balance conflict while migrating My Wallet from "
            "version %s: %s. No holdings or purchase quantities were changed. "
            "Automatic savings-plan bookings are paused until the opening "
            "holdings and included purchase lots are reconciled in the options",
            original_version,
            "; ".join(
                f"{item['symbol']}: configured={item['configured_units']:.12g}, "
                f"included lots={item['included_units']:.12g}"
                for item in conflicts
            ),
        )
    hass.config_entries.async_update_entry(entry, data=data, version=6)
    _LOGGER.info(
        "Migrated My Wallet config entry from version %s to version 6 "
        "(%s legacy mini-plan(s) disabled, %s future opening cutoff(s) clamped)",
        original_version,
        disabled_count,
        clamped_count,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: MyWalletConfigEntry) -> bool:
    """Set up a wallet from a config entry."""
    coordinator = WalletCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MyWalletConfigEntry) -> bool:
    """Unload a wallet."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
