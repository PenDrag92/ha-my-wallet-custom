"""Reconstruct a dated wallet history without writing recorder statistics."""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from . import const as c
from .contributions import (
    all_lots,
    contributions_from_data,
    opening_balance_conflicts,
)
from .dividends import dividends_from_data
from .yahoo import HistoricalQuote, fetch_histories, fx_symbol

MAX_HISTORY_DAYS = 3653
MAX_QUOTE_AGE_DAYS = 7


def latest_close(
    history: list[HistoricalQuote], through: date
) -> HistoricalQuote | None:
    """Use only an already available close, never a future market price."""
    index = bisect_right(history, through, key=lambda item: item.date) - 1
    if index < 0 or (through - history[index].date).days > MAX_QUOTE_AGE_DAYS:
        return None
    return history[index]


def historical_fx(histories, currency: str, base: str, through: date) -> float | None:
    if currency == base:
        return 1.0
    direct = latest_close(histories.get(fx_symbol(currency, base), []), through)
    if direct is not None:
        return direct.close
    inverse = latest_close(histories.get(fx_symbol(base, currency), []), through)
    return 1 / inverse.close if inverse is not None and inverse.close > 0 else None


def ledger_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Expose deposits, purchases and dividends as separate cash events."""
    names = {
        plan[c.PLAN_ID]: plan[c.PLAN_NAME]
        for plan in [
            *data.get(c.CONF_SAVINGS_PLANS, []),
            *data.get(c.CONF_RETIRED_SAVINGS_PLANS, []),
        ]
    }
    events = []
    for row in contributions_from_data(data):
        legacy = row[c.CONTRIBUTION_SOURCE] == c.CONTRIBUTION_SOURCE_LEGACY
        common = {
            "plan": names.get(
                row.get(c.CONTRIBUTION_PLAN_ID), row.get(c.CONTRIBUTION_PLAN_NAME, "")
            ),
            "note": row.get(c.CONTRIBUTION_NOTE, ""),
            "source": row[c.CONTRIBUTION_SOURCE],
        }
        if row[c.CONTRIBUTION_AMOUNT] > 0:
            events.append(
                {
                    **common,
                    "id": row[c.CONTRIBUTION_ID],
                    "type": "opening" if legacy else "deposit",
                    "date": row[c.CONTRIBUTION_DATE],
                    "amount": row[c.CONTRIBUTION_AMOUNT],
                    "cash_delta": 0 if legacy else row[c.CONTRIBUTION_AMOUNT],
                }
            )
        for lot in row[c.CONTRIBUTION_LOTS]:
            events.append(
                {
                    **common,
                    "id": lot[c.LOT_ID],
                    "type": "purchase",
                    "date": lot[c.LOT_DATE],
                    "amount": -lot[c.LOT_AMOUNT],
                    "cash_delta": 0
                    if legacy and lot[c.LOT_INCLUDED_IN_OPENING]
                    else -lot[c.LOT_AMOUNT],
                    "symbol": lot[c.LOT_SYMBOL],
                    "units": lot[c.LOT_UNITS],
                    "estimated": lot[c.LOT_ESTIMATED],
                    "price_date": lot.get("price_date", lot[c.LOT_DATE]),
                }
            )
    for row in dividends_from_data(data):
        events.append(
            {
                "id": row[c.DIVIDEND_ID],
                "type": "dividend",
                "date": row.get(c.DIVIDEND_VALUE_DATE) or row[c.DIVIDEND_BOOKING_DATE],
                "booking_date": row[c.DIVIDEND_BOOKING_DATE],
                "amount": row[c.DIVIDEND_AMOUNT],
                "cash_delta": row[c.DIVIDEND_AMOUNT],
                "symbol": row.get(c.DIVIDEND_SYMBOL, ""),
                "note": row.get(c.DIVIDEND_NOTE, ""),
                "plan": "",
            }
        )
    order = {"opening": 0, "deposit": 1, "dividend": 2, "purchase": 3}
    return sorted(
        events, key=lambda row: (row["date"] or "", order[row["type"]], row["id"])
    )


def build_history(data, histories, *, today: date) -> dict[str, Any]:
    """Price only dated holdings; an unknown opening position leaves gaps."""
    events = ledger_rows(data)
    eligible = [
        row for row in events if not row["date"] or row["date"] <= today.isoformat()
    ]
    days = [date.fromisoformat(row["date"]) for row in eligible if row["date"]]
    first = min(days, default=today)
    start = max(first, today - timedelta(days=MAX_HISTORY_DAYS))
    included = defaultdict(float)
    for lot in all_lots(data):
        if lot[c.LOT_INCLUDED_IN_OPENING]:
            included[lot[c.LOT_SYMBOL]] += lot[c.LOT_UNITS]
    unknown_opening = [
        valor[c.VALOR_SYMBOL]
        for valor in data[c.CONF_VALORS]
        if valor[c.VALOR_AMOUNT] - included[valor[c.VALOR_SYMBOL]] > 1e-8
    ]
    conflicts = opening_balance_conflicts(data)
    positions = defaultdict(float)
    cash = invested = 0.0
    pointer = 0
    points = []
    base = data[c.CONF_BASE_CURRENCY]
    day = start
    missing = set()
    while day <= today:
        while (
            pointer < len(eligible)
            and (eligible[pointer]["date"] or "") <= day.isoformat()
        ):
            row = eligible[pointer]
            cash += row["cash_delta"]
            if row["type"] in ("deposit", "opening"):
                invested += row["amount"]
            if row["type"] == "purchase":
                positions[row["symbol"]] += row["units"]
            pointer += 1
        value = cash
        complete = not unknown_opening and not conflicts
        for symbol, units in positions.items():
            if units <= 1e-10:
                continue
            quote = latest_close(histories.get(symbol, []), day)
            fx = historical_fx(histories, quote.currency, base, day) if quote else None
            if quote is None or fx is None:
                complete = False
                missing.add(symbol)
            else:
                value += units * quote.close * fx
        points.append(
            {
                "date": day.isoformat(),
                "invested": round(invested, 2),
                "cash": round(cash, 2),
                "value": round(value, 2) if complete else None,
                "profit": round(value - invested, 2) if complete else None,
            }
        )
        day += timedelta(days=1)
    return {
        "points": points,
        "ledger": events,
        "estimated": any(row.get("estimated") for row in events),
        "unknown_opening": unknown_opening,
        "opening_conflicts": conflicts,
        "missing_history": sorted(missing),
        "range_limited": start != first,
    }


async def async_history(data, *, session, today: date) -> dict[str, Any]:
    events = ledger_rows(data)
    days = [date.fromisoformat(row["date"]) for row in events if row["date"]]
    start = max(min(days, default=today), today - timedelta(days=MAX_HISTORY_DAYS))
    symbols = sorted({lot[c.LOT_SYMBOL] for lot in all_lots(data)})
    histories = await fetch_histories(
        session, symbols, start - timedelta(days=7), today
    )
    base = data[c.CONF_BASE_CURRENCY]
    currencies = {quote.currency for rows in histories.values() for quote in rows}
    pairs = sorted(
        {
            pair
            for currency in currencies - {base}
            for pair in (fx_symbol(currency, base), fx_symbol(base, currency))
        }
    )
    if pairs:
        histories.update(
            await fetch_histories(session, pairs, start - timedelta(days=7), today)
        )
    return build_history(data, histories, today=today)
