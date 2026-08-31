"""The My Wallet integration: portfolios valued via Yahoo Finance."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CONTRIBUTIONS,
    CONF_DIVIDENDS,
    CONF_INVESTED_AMOUNT,
    CONF_SAVINGS_PLANS,
    CONTRIBUTION_SOURCE_LEGACY,
    PLATFORMS,
)
from .contributions import (
    LEGACY_CONTRIBUTION_ID,
    make_contribution,
    normalize_contributions,
)
from .coordinator import WalletCoordinator
from .dividends import normalize_dividends
from .plans import normalize_plan

_LOGGER = logging.getLogger(__name__)

# Type alias for config entries of this integration.
type MyWalletConfigEntry = ConfigEntry[WalletCoordinator]


async def async_migrate_entry(hass: HomeAssistant, entry: MyWalletConfigEntry) -> bool:
    """Migrate legacy invested amounts and version-2 dated contributions."""
    if entry.version > 4:
        _LOGGER.error(
            "Cannot migrate My Wallet config entry from unsupported version %s",
            entry.version,
        )
        return False

    if entry.version < 4:
        data: dict[str, Any] = dict(entry.data)
        legacy_amount = data.pop(CONF_INVESTED_AMOUNT, None)
        contributions = list(data.get(CONF_CONTRIBUTIONS, []))
        if (
            entry.version in (1, 2)
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
        data[CONF_CONTRIBUTIONS] = normalize_contributions(contributions)
        data[CONF_SAVINGS_PLANS] = [
            normalize_plan(plan) for plan in data.get(CONF_SAVINGS_PLANS, [])
        ]
        data[CONF_DIVIDENDS] = normalize_dividends(data.get(CONF_DIVIDENDS, []))
        hass.config_entries.async_update_entry(entry, data=data, version=4)
        _LOGGER.info("Migrated My Wallet config entry to version 4")

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
