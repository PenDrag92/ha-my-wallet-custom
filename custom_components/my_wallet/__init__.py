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

_LOGGER = logging.getLogger(__name__)

# Type alias for config entries of this integration.
type MyWalletConfigEntry = ConfigEntry[WalletCoordinator]


async def async_migrate_entry(hass: HomeAssistant, entry: MyWalletConfigEntry) -> bool:
    """Migrate legacy invested amounts and version-2 dated contributions."""
    if entry.version > 3:
        _LOGGER.error(
            "Cannot migrate My Wallet config entry from unsupported version %s",
            entry.version,
        )
        return False

    if entry.version in (1, 2):
        data: dict[str, Any] = dict(entry.data)
        legacy_amount = data.pop(CONF_INVESTED_AMOUNT, None)
        contributions = list(data.get(CONF_CONTRIBUTIONS, []))
        if not contributions and legacy_amount is not None and float(legacy_amount) > 0:
            contributions.append(
                make_contribution(
                    legacy_amount,
                    None,
                    contribution_id=LEGACY_CONTRIBUTION_ID,
                    source=CONTRIBUTION_SOURCE_LEGACY,
                )
            )
        data[CONF_CONTRIBUTIONS] = normalize_contributions(contributions)
        data.setdefault(CONF_SAVINGS_PLANS, [])
        data.setdefault(CONF_DIVIDENDS, [])
        hass.config_entries.async_update_entry(entry, data=data, version=3)
        _LOGGER.info("Migrated My Wallet config entry to version 3")

    return True


async def async_setup_entry(hass: HomeAssistant, entry: MyWalletConfigEntry) -> bool:
    """Set up a wallet from a config entry."""
    coordinator = WalletCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MyWalletConfigEntry) -> bool:
    """Unload a wallet."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_entry(hass: HomeAssistant, entry: MyWalletConfigEntry) -> None:
    """Reload the entry when its data (settings or valors) change."""
    await hass.config_entries.async_reload(entry.entry_id)
