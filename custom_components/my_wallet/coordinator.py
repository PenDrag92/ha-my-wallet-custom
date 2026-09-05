"""Data update coordinator for a single wallet."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BASE_CURRENCY,
    CONF_CONTRIBUTIONS,
    CONF_INFLATION_SOURCE,
    CONF_LAST_PLAN_RESULT,
    CONF_SAVINGS_PLANS,
    CONF_SCAN_INTERVAL,
    CONF_VALORS,
    CONF_WALLET_NAME,
    DEFAULT_INFLATION_SOURCE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    VALOR_AMOUNT,
    VALOR_SYMBOL,
    VALOR_TARGET_SHARE,
)
from .contributions import (
    additional_units,
)
from .dividends import cash_balance
from .executions import (
    _close_date_bounds as _close_date_bounds,
)
from .executions import (
    _execution_sort_key as _execution_sort_key,
)
from .executions import (
    _first_close,
    _merge_confirmed_quote,
    async_prepare_executions,
)
from .executions import (
    _included_opening_overflows as _included_opening_overflows,
)
from .inflation_client import InflationDataClient
from .models import ValorData, WalletData
from .plans import normalize_plan
from .recorded_history import accounting_snapshot
from .store import commit_wallet_change
from .yahoo import (
    Quote,
    fetch_fx_rates,
    fetch_quotes,
)

_LOGGER = logging.getLogger(__name__)


class WalletCoordinator(DataUpdateCoordinator[WalletData]):
    """Refresh quotes and book due monthly savings-plan executions."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.base_currency: str = entry.data[CONF_BASE_CURRENCY]
        self._inflation = InflationDataClient(hass, entry.entry_id)
        interval = min(
            MAX_SCAN_INTERVAL,
            max(
                MIN_SCAN_INTERVAL,
                int(entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
            ),
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.data.get(CONF_WALLET_NAME, entry.title)}",
            update_interval=timedelta(minutes=interval),
            config_entry=entry,
        )

    @property
    def valors(self) -> list[dict[str, Any]]:
        """Configured valors; amount is the untracked opening balance."""
        return list(self.entry.data.get(CONF_VALORS, []))

    @property
    def savings_plans(self) -> list[dict[str, Any]]:
        """Configured monthly savings plans."""
        return [
            normalize_plan(plan) for plan in self.entry.data.get(CONF_SAVINGS_PLANS, [])
        ]

    _merge_confirmed_quote = staticmethod(_merge_confirmed_quote)
    _first_close = staticmethod(_first_close)

    async def _async_book_due_plans(
        self,
        session: aiohttp.ClientSession,
        current_quotes: dict[str, Quote | None],
        today: date,
    ) -> list[dict[str, Any]]:
        """Prepare first, then persist once if no other writer changed the entry."""
        snapshot = self.entry.data
        data, report = await async_prepare_executions(
            snapshot, session=session, today=today, current_quotes=current_quotes
        )
        if self.entry.data is not snapshot:
            return [
                *report["pending"],
                {
                    "scheduled_date": today.isoformat(),
                    "reason": "entry_changed",
                    "missing_symbols": [],
                    "repair_required": False,
                },
            ]
        if data.get(CONF_CONTRIBUTIONS) != snapshot.get(CONF_CONTRIBUTIONS):
            data[CONF_LAST_PLAN_RESULT] = report
            commit_wallet_change(
                self.hass,
                self.entry,
                data,
                snapshot=snapshot,
                today=today,
                reload=False,
            )
            _LOGGER.info(
                "Booked %s savings-plan executions for %s", report["created"], self.name
            )
        return report["pending"]

    async def _async_update_data(self) -> WalletData:
        valors = self.valors
        today = dt_util.now().date()
        session = async_get_clientsession(self.hass)
        inflation = await self._inflation.async_get(
            session,
            source=self.entry.data.get(CONF_INFLATION_SOURCE, DEFAULT_INFLATION_SOURCE),
            today=today,
        )
        if not valors:
            return WalletData(
                cash_balance=cash_balance(self.entry.data, through=today),
                inflation=inflation,
            )

        symbols = [valor[VALOR_SYMBOL] for valor in valors]
        try:
            quotes = await fetch_quotes(session, symbols)
        except aiohttp.ClientError as err:  # pragma: no cover - defensive
            raise UpdateFailed(f"Yahoo Finance request failed: {err}") from err

        pending = await self._async_book_due_plans(session, quotes, today)

        pairs: set[tuple[str, str]] = {
            (quote.currency, self.base_currency)
            for quote in quotes.values()
            if quote is not None and quote.currency != self.base_currency
        }
        fx_rates = await fetch_fx_rates(session, pairs) if pairs else {}

        data = WalletData(
            pending_executions=pending,
            cash_balance=cash_balance(self.entry.data, through=today),
            inflation=inflation,
            sampled_at=dt_util.now().isoformat(),
        )
        for valor in valors:
            symbol = valor[VALOR_SYMBOL]
            opening_amount = float(valor[VALOR_AMOUNT])
            amount = opening_amount + additional_units(
                self.entry.data, symbol, through=today
            )
            target = valor.get(VALOR_TARGET_SHARE)
            target = float(target) if target is not None else None
            quote = quotes.get(symbol)
            item = ValorData(
                symbol=symbol,
                amount=amount,
                opening_amount=opening_amount,
                quote=quote,
                target_share=target,
            )
            if quote is None:
                item.error = "quote_unavailable"
            elif quote.currency == self.base_currency:
                item.fx_rate = 1.0
            else:
                item.fx_rate = fx_rates.get((quote.currency, self.base_currency))
                if item.fx_rate is None:
                    item.error = "fx_rate_unavailable"
            data.valors[symbol] = item

        # Freeze the basis with this valuation. Later configuration edits must
        # not pair new costs with a still-cached old price/holding sample.
        data.history_snapshots = {
            symbol: accounting_snapshot(
                self.entry.data, today=today, symbol=symbol, sampled_at=data.sampled_at
            )
            for symbol in (None, *data.valors)
        }

        if not data.all_available:
            _LOGGER.warning(
                "Wallet %s: some valors could not be updated: %s",
                self.name,
                [
                    symbol
                    for symbol, valor in data.valors.items()
                    if not valor.available
                ],
            )
        return data
