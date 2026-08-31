"""Async Yahoo Finance client based on the public chart endpoint.

Uses ``https://query1.finance.yahoo.com/v8/finance/chart/{symbol}`` which
works without authentication (no cookie/crumb dance) and returns everything
we need: last price, previous close, currency and the instrument name.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as dt_time
from math import isfinite
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp

_LOGGER = logging.getLogger(__name__)

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
REQUEST_TIMEOUT = 20
# Yahoo rejects requests without a browser-like User-Agent.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


class YahooError(Exception):
    """Raised when a quote cannot be fetched or parsed."""


@dataclass
class Quote:
    """A single market quote."""

    symbol: str
    price: float
    currency: str
    previous_close: float | None = None
    short_name: str | None = None
    market_date: date | None = None
    market_closed: bool = False

    @property
    def day_change(self) -> float | None:
        """Absolute change vs previous close."""
        if self.previous_close is None or self.price is None:
            return None
        return self.price - self.previous_close

    @property
    def day_change_pct(self) -> float | None:
        """Percentage change vs previous close."""
        if not self.previous_close:
            return None
        return (self.price - self.previous_close) / self.previous_close * 100


@dataclass(frozen=True)
class HistoricalQuote:
    """A confirmed Yahoo daily close."""

    symbol: str
    date: date
    close: float
    currency: str


def _to_float(value: Any) -> float | None:
    """Best-effort conversion, treating None/invalid as missing."""
    if value is None:
        return None
    try:
        converted = float(value)
        return converted if isfinite(converted) else None
    except (TypeError, ValueError):
        return None


def fx_symbol(from_currency: str, to_currency: str) -> str:
    """Build the Yahoo symbol for an FX pair, e.g. ``USDPLN=X``."""
    return f"{from_currency}{to_currency}=X"


def _timestamp_date(timestamp: float, timezone_name: str | None) -> date:
    """Convert a Yahoo timestamp in the exchange's timezone."""
    try:
        timezone = ZoneInfo(timezone_name) if timezone_name else UTC
    except ZoneInfoNotFoundError:
        timezone = UTC
    return datetime.fromtimestamp(timestamp, timezone).date()


def _currency_and_factor(raw_currency: Any) -> tuple[str, float]:
    """Normalize Yahoo minor-unit currencies to ISO major units."""
    raw = str(raw_currency).strip()
    minor_units = {
        "GBp": ("GBP", 0.01),
        "GBX": ("GBP", 0.01),
        "ILA": ("ILS", 0.01),
        "ZAc": ("ZAR", 0.01),
    }
    return minor_units.get(raw, (raw.upper(), 1.0))


def _market_date_confirmed(
    market_date: date,
    timezone_name: str | None,
    regular_end: float | None,
    *,
    now_timestamp: float | None = None,
) -> bool:
    """Return whether a daily bar is final in the exchange timezone."""
    now_timestamp = time.time() if now_timestamp is None else now_timestamp
    try:
        timezone = ZoneInfo(timezone_name) if timezone_name else UTC
    except ZoneInfoNotFoundError:
        timezone = UTC
    exchange_today = datetime.fromtimestamp(now_timestamp, timezone).date()
    return market_date < exchange_today or (
        market_date == exchange_today
        and regular_end is not None
        and now_timestamp >= regular_end
    )


async def fetch_quote(session: aiohttp.ClientSession, symbol: str) -> Quote:
    """Fetch a single quote from the chart endpoint.

    Raises YahooError on HTTP errors, timeouts or unparsable payloads.
    """
    url = CHART_URL.format(symbol=symbol)
    try:
        async with session.get(
            url,
            params={"range": "1d", "interval": "1d"},
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        ) as resp:
            if resp.status != 200:
                raise YahooError(f"HTTP {resp.status} for {symbol}")
            payload: dict[str, Any] = await resp.json()
    except (TimeoutError, aiohttp.ClientError) as err:
        raise YahooError(f"Request failed for {symbol}: {err}") from err

    try:
        result = payload["chart"]["result"][0]
        meta = result["meta"]
        price = _to_float(meta["regularMarketPrice"])
        currency, price_factor = _currency_and_factor(meta["currency"])
    except (KeyError, IndexError, TypeError) as err:
        raise YahooError(f"Unexpected payload for {symbol}: {err}") from err

    if price is None or price <= 0:
        raise YahooError(f"No price in payload for {symbol}")

    market_timestamp = _to_float(meta.get("regularMarketTime"))
    market_date = (
        _timestamp_date(market_timestamp, meta.get("exchangeTimezoneName"))
        if market_timestamp is not None
        else None
    )
    regular_end = _to_float(
        meta.get("currentTradingPeriod", {}).get("regular", {}).get("end")
    )
    market_closed = bool(
        market_date is not None
        and _market_date_confirmed(
            market_date,
            meta.get("exchangeTimezoneName"),
            regular_end,
        )
    )

    return Quote(
        symbol=symbol,
        price=price * price_factor,
        currency=currency,
        previous_close=(
            previous * price_factor
            if (
                previous := _to_float(
                    meta.get("chartPreviousClose") or meta.get("previousClose")
                )
            )
            is not None
            else None
        ),
        short_name=meta.get("shortName") or meta.get("longName"),
        market_date=market_date,
        market_closed=market_closed,
    )


async def fetch_history(
    session: aiohttp.ClientSession,
    symbol: str,
    start_date: date,
    end_date: date,
) -> list[HistoricalQuote]:
    """Fetch confirmed daily closes in an inclusive date range."""
    if end_date < start_date:
        return []
    period1 = int(datetime.combine(start_date, dt_time.min, tzinfo=UTC).timestamp())
    period2 = int(
        datetime.combine(
            end_date + timedelta(days=1), dt_time.min, tzinfo=UTC
        ).timestamp()
    )
    url = CHART_URL.format(symbol=symbol)
    try:
        async with session.get(
            url,
            params={
                "period1": period1,
                "period2": period2,
                "interval": "1d",
                "events": "history",
            },
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        ) as resp:
            if resp.status != 200:
                raise YahooError(f"HTTP {resp.status} for history of {symbol}")
            payload: dict[str, Any] = await resp.json()
    except (TimeoutError, aiohttp.ClientError) as err:
        raise YahooError(f"History request failed for {symbol}: {err}") from err

    try:
        result = payload["chart"]["result"][0]
        meta = result["meta"]
        currency, price_factor = _currency_and_factor(meta["currency"])
        timezone_name = meta.get("exchangeTimezoneName")
        regular_end = _to_float(
            meta.get("currentTradingPeriod", {}).get("regular", {}).get("end")
        )
        timestamps = result.get("timestamp") or []
        closes = result["indicators"]["quote"][0].get("close") or []
    except (KeyError, IndexError, TypeError) as err:
        raise YahooError(f"Unexpected history payload for {symbol}: {err}") from err

    history: list[HistoricalQuote] = []
    for timestamp, raw_close in zip(timestamps, closes, strict=False):
        close = _to_float(raw_close)
        if close is None or close <= 0:
            continue
        quote_date = _timestamp_date(timestamp, timezone_name)
        if start_date <= quote_date <= end_date and _market_date_confirmed(
            quote_date, timezone_name, regular_end
        ):
            history.append(
                HistoricalQuote(symbol, quote_date, close * price_factor, currency)
            )
    return sorted(history, key=lambda item: item.date)


async def fetch_histories(
    session: aiohttp.ClientSession,
    symbols: list[str],
    start_date: date,
    end_date: date,
) -> dict[str, list[HistoricalQuote]]:
    """Fetch daily histories in parallel without failing the whole wallet."""

    async def _safe(symbol: str) -> list[HistoricalQuote]:
        try:
            return await fetch_history(session, symbol, start_date, end_date)
        except YahooError as err:
            _LOGGER.warning("Yahoo Finance history failed: %s", err)
            return []

    results = await asyncio.gather(*(_safe(symbol) for symbol in symbols))
    return dict(zip(symbols, results, strict=True))


async def fetch_quotes(
    session: aiohttp.ClientSession, symbols: list[str]
) -> dict[str, Quote | None]:
    """Fetch several quotes in parallel.

    Returns a mapping of symbol to Quote, or None when that symbol failed
    (a single bad symbol must not break the whole wallet update).
    """

    async def _safe(symbol: str) -> Quote | None:
        try:
            return await fetch_quote(session, symbol)
        except YahooError as err:
            _LOGGER.warning("Yahoo Finance quote failed: %s", err)
            return None

    results = await asyncio.gather(*(_safe(sym) for sym in symbols))
    return dict(zip(symbols, results, strict=True))


async def fetch_fx_rates(
    session: aiohttp.ClientSession,
    pairs: set[tuple[str, str]],
) -> dict[tuple[str, str], float | None]:
    """Fetch FX rates for ``pairs`` of (from_currency, to_currency).

    Tries the direct Yahoo pair first (e.g. ``USDPLN=X``); if unavailable,
    falls back to the inverse pair (``PLNUSD=X``) and reciprocates it.
    """
    to_fetch: set[str] = set()
    for frm, to in pairs:
        if frm == to:
            continue
        to_fetch.add(fx_symbol(frm, to))
        to_fetch.add(fx_symbol(to, frm))

    quotes = await fetch_quotes(session, sorted(to_fetch)) if to_fetch else {}

    rates: dict[tuple[str, str], float | None] = {}
    for frm, to in pairs:
        if frm == to:
            rates[(frm, to)] = 1.0
            continue
        direct = quotes.get(fx_symbol(frm, to))
        if direct is not None:
            rates[(frm, to)] = direct.price
            continue
        inverse = quotes.get(fx_symbol(to, frm))
        if inverse is not None and inverse.price:
            rates[(frm, to)] = 1.0 / inverse.price
            continue
        _LOGGER.warning("No FX rate found for %s -> %s", frm, to)
        rates[(frm, to)] = None
    return rates
