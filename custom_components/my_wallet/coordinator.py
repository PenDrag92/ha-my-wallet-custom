"""Data update coordinator for a single wallet."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BASE_CURRENCY,
    CONF_CONTRIBUTIONS,
    CONF_SAVINGS_PLANS,
    CONF_SCAN_INTERVAL,
    CONF_VALORS,
    CONTRIBUTION_SOURCE_PLAN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    PLAN_AMOUNT,
    PLAN_ID,
    PLAN_NAME,
    PLAN_OPENING_CUTOFF_DATE,
    PLAN_USE_CASH_BALANCE,
    VALOR_AMOUNT,
    VALOR_SYMBOL,
    VALOR_TARGET_SHARE,
)
from .contributions import (
    additional_units,
    contributions_from_data,
    make_contribution,
    make_lot,
    normalize_contributions,
)
from .dividends import cash_balance
from .plans import allocation_amounts, due_dates, next_scheduled_date, normalize_plan
from .yahoo import (
    HistoricalQuote,
    Quote,
    fetch_fx_rates,
    fetch_histories,
    fetch_quotes,
    fx_symbol,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class ValorData:
    """Computed state for a single valor inside the wallet."""

    symbol: str
    amount: float
    opening_amount: float
    quote: Quote | None = None
    fx_rate: float | None = None
    error: str | None = None
    target_share: float | None = None

    @property
    def available(self) -> bool:
        return self.quote is not None and self.fx_rate is not None

    @property
    def value(self) -> float | None:
        """Valor value converted to the wallet base currency."""
        if not self.available:
            return None
        return self.amount * self.quote.price * self.fx_rate

    @property
    def has_target(self) -> bool:
        return self.target_share is not None and self.target_share > 0


@dataclass
class WalletData:
    """Result of one coordinator update."""

    valors: dict[str, ValorData] = field(default_factory=dict)
    pending_executions: list[dict[str, Any]] = field(default_factory=list)
    cash_balance: float = 0.0

    @property
    def securities_total(self) -> float | None:
        """Total market value of available securities."""
        values = [
            valor.value for valor in self.valors.values() if valor.value is not None
        ]
        return sum(values) if values else None

    @property
    def total(self) -> float | None:
        """Securities plus the broker cash account in the base currency."""
        securities = self.securities_total
        if securities is None:
            return self.cash_balance if self.cash_balance else None
        return securities + self.cash_balance

    @property
    def all_available(self) -> bool:
        return all(valor.available for valor in self.valors.values())


class WalletCoordinator(DataUpdateCoordinator[WalletData]):
    """Refresh quotes and book due monthly savings-plan executions."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.base_currency: str = entry.data[CONF_BASE_CURRENCY]
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
            name=f"{DOMAIN}_{entry.data.get(CONF_NAME, entry.title)}",
            update_interval=timedelta(minutes=interval),
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

    @staticmethod
    def _merge_confirmed_quote(
        history: list[HistoricalQuote], quote: Quote | None
    ) -> list[HistoricalQuote]:
        """Use a confirmed current close when Yahoo exposes no history."""
        by_date = {item.date: item for item in history}
        if quote is not None and quote.market_closed and quote.market_date is not None:
            by_date[quote.market_date] = HistoricalQuote(
                quote.symbol, quote.market_date, quote.price, quote.currency
            )
        return sorted(by_date.values(), key=lambda item: item.date)

    @staticmethod
    def _first_close(
        history: list[HistoricalQuote], start: date, end: date
    ) -> HistoricalQuote | None:
        return next((item for item in history if start <= item.date <= end), None)

    async def _async_book_due_plans(
        self,
        session: aiohttp.ClientSession,
        current_quotes: dict[str, Quote | None],
        today: date,
    ) -> list[dict[str, Any]]:
        """Book every due plan for which a confirmed Yahoo close is available."""
        contributions = contributions_from_data(self.entry.data)
        due: list[tuple[dict[str, Any], date]] = []
        for plan in self.savings_plans:
            due.extend(
                (plan, scheduled) for scheduled in due_dates(plan, contributions, today)
            )
        due.sort(key=lambda item: (item[1], item[0][PLAN_ID]))
        if not due:
            return []

        earliest = min(scheduled for _, scheduled in due)
        history_end = today - timedelta(days=1)
        symbols = sorted(
            {symbol for plan, _ in due for symbol in allocation_amounts(plan)}
        )
        histories = (
            await fetch_histories(session, symbols, earliest, history_end)
            if earliest <= history_end
            else {symbol: [] for symbol in symbols}
        )
        for symbol in symbols:
            histories[symbol] = self._merge_confirmed_quote(
                histories.get(symbol, []), current_quotes.get(symbol)
            )

        selected: dict[tuple[str, str], HistoricalQuote] = {}
        pending: list[dict[str, Any]] = []
        for plan, scheduled in due:
            next_date = next_scheduled_date(plan, scheduled + timedelta(days=1))
            window_end = min(
                today,
                next_date - timedelta(days=1) if next_date else today,
            )
            missing: list[str] = []
            for symbol in allocation_amounts(plan):
                quote = self._first_close(
                    histories.get(symbol, []), scheduled, window_end
                )
                if quote is None:
                    missing.append(symbol)
                else:
                    selected[(plan[PLAN_ID], f"{scheduled}:{symbol}")] = quote
            if missing:
                pending.append(
                    {
                        "plan_id": plan[PLAN_ID],
                        "plan_name": plan[PLAN_NAME],
                        "scheduled_date": scheduled.isoformat(),
                        "missing_symbols": missing,
                    }
                )

        ready = [
            (plan, scheduled)
            for plan, scheduled in due
            if not any(
                item["plan_id"] == plan[PLAN_ID]
                and item["scheduled_date"] == scheduled.isoformat()
                for item in pending
            )
        ]
        if not ready:
            return pending

        pairs: set[tuple[str, str]] = {
            (quote.currency, self.base_currency)
            for quote in selected.values()
            if quote.currency != self.base_currency
        }
        fx_histories: dict[str, list[HistoricalQuote]] = {}
        if pairs:
            fx_symbols = sorted(
                {
                    symbol
                    for source, target in pairs
                    for symbol in (
                        fx_symbol(source, target),
                        fx_symbol(target, source),
                    )
                }
            )
            fx_start = min(quote.date for quote in selected.values())
            fx_histories = await fetch_histories(
                session, fx_symbols, fx_start, history_end
            )

        booked = False
        for plan, scheduled in ready:
            lots: list[dict[str, Any]] = []
            missing_fx = False
            available_amount: float | None = None
            if plan[PLAN_USE_CASH_BALANCE]:
                available_amount = float(plan[PLAN_AMOUNT]) + max(
                    0.0,
                    cash_balance(
                        self.entry.data,
                        through=scheduled,
                        contributions=contributions,
                    ),
                )
            allocated_amounts = allocation_amounts(
                plan, available_amount=available_amount
            )
            for symbol, amount in allocated_amounts.items():
                quote = selected[(plan[PLAN_ID], f"{scheduled}:{symbol}")]
                fx_rate = 1.0
                if quote.currency != self.base_currency:
                    direct = self._first_close(
                        fx_histories.get(
                            fx_symbol(quote.currency, self.base_currency), []
                        ),
                        quote.date,
                        quote.date + timedelta(days=7),
                    )
                    inverse = self._first_close(
                        fx_histories.get(
                            fx_symbol(self.base_currency, quote.currency), []
                        ),
                        quote.date,
                        quote.date + timedelta(days=7),
                    )
                    if direct is not None:
                        fx_rate = direct.close
                    elif inverse is not None and inverse.close:
                        fx_rate = 1 / inverse.close
                    else:
                        missing_fx = True
                        break
                lots.append(
                    make_lot(
                        symbol=symbol,
                        execution_date=quote.date,
                        amount=amount,
                        unit_price=quote.close,
                        quote_currency=quote.currency,
                        fx_rate=fx_rate,
                        included_in_opening=bool(
                            plan[PLAN_OPENING_CUTOFF_DATE]
                            and quote.date
                            <= date.fromisoformat(plan[PLAN_OPENING_CUTOFF_DATE])
                        ),
                        estimated=True,
                    )
                )
            if missing_fx:
                pending.append(
                    {
                        "plan_id": plan[PLAN_ID],
                        "plan_name": plan[PLAN_NAME],
                        "scheduled_date": scheduled.isoformat(),
                        "missing_symbols": ["fx_rate"],
                    }
                )
                continue

            contributions.append(
                make_contribution(
                    plan[PLAN_AMOUNT],
                    scheduled,
                    source=CONTRIBUTION_SOURCE_PLAN,
                    lots=lots,
                    plan_id=plan[PLAN_ID],
                    scheduled_date=scheduled,
                )
            )
            booked = True

        if booked:
            data = dict(self.entry.data)
            data[CONF_CONTRIBUTIONS] = normalize_contributions(contributions)
            self.hass.config_entries.async_update_entry(self.entry, data=data)
            _LOGGER.info("Booked due savings-plan executions for %s", self.name)
        return pending

    async def _async_update_data(self) -> WalletData:
        valors = self.valors
        if not valors:
            return WalletData()

        session = async_get_clientsession(self.hass)
        symbols = [valor[VALOR_SYMBOL] for valor in valors]
        try:
            quotes = await fetch_quotes(session, symbols)
        except aiohttp.ClientError as err:  # pragma: no cover - defensive
            raise UpdateFailed(f"Yahoo Finance request failed: {err}") from err

        today = dt_util.now().date()
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
        )
        for valor in valors:
            symbol = valor[VALOR_SYMBOL]
            opening_amount = float(valor[VALOR_AMOUNT])
            amount = opening_amount + additional_units(self.entry.data, symbol)
            target = valor.get(VALOR_TARGET_SHARE)
            target = float(target) if target is not None and float(target) > 0 else None
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
