"""Pure helpers for dividend income and the broker cash balance."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from math import fsum, isfinite
from typing import Any
from uuid import uuid4

from .const import (
    CONF_DIVIDENDS,
    CONTRIBUTION_AMOUNT,
    CONTRIBUTION_DATE,
    CONTRIBUTION_LOTS,
    CONTRIBUTION_SOURCE,
    CONTRIBUTION_SOURCE_LEGACY,
    DIVIDEND_AMOUNT,
    DIVIDEND_BOOKING_DATE,
    DIVIDEND_ID,
    DIVIDEND_NOTE,
    DIVIDEND_SYMBOL,
    DIVIDEND_VALUE_DATE,
    LOT_AMOUNT,
    LOT_DATE,
    LOT_ID,
    LOT_INCLUDED_IN_OPENING,
    LOT_UNITS,
)
from .contributions import contributions_from_data, normalize_date


def make_dividend(
    *,
    booking_date: Any,
    amount: Any,
    symbol: str | None = None,
    value_date: Any | None = None,
    note: str | None = None,
    dividend_id: str | None = None,
) -> dict[str, Any]:
    """Create one net dividend credit in the wallet's base currency."""
    normalized_amount = float(amount)
    if not isfinite(normalized_amount) or normalized_amount <= 0:
        raise ValueError("Dividend amount must be greater than zero")

    item: dict[str, Any] = {
        DIVIDEND_ID: dividend_id or uuid4().hex,
        DIVIDEND_BOOKING_DATE: normalize_date(booking_date),
        DIVIDEND_VALUE_DATE: normalize_date(value_date, allow_none=True),
        DIVIDEND_AMOUNT: normalized_amount,
    }
    normalized_symbol = (symbol or "").strip().upper()
    if normalized_symbol:
        item[DIVIDEND_SYMBOL] = normalized_symbol
    normalized_note = (note or "").strip()
    if normalized_note:
        item[DIVIDEND_NOTE] = normalized_note
    return item


def normalize_dividend(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a serialized dividend entry."""
    return make_dividend(
        booking_date=entry[DIVIDEND_BOOKING_DATE],
        value_date=entry.get(DIVIDEND_VALUE_DATE),
        amount=entry[DIVIDEND_AMOUNT],
        symbol=entry.get(DIVIDEND_SYMBOL),
        note=entry.get(DIVIDEND_NOTE),
        dividend_id=str(entry.get(DIVIDEND_ID) or uuid4().hex),
    )


def normalize_dividends(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Validate dividend entries and order them by cash-effective date."""
    return sorted(
        (normalize_dividend(entry) for entry in entries),
        key=lambda item: (
            item.get(DIVIDEND_VALUE_DATE) or item[DIVIDEND_BOOKING_DATE],
            item[DIVIDEND_ID],
        ),
    )


def dividends_from_data(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return normalized dividends from config-entry data."""
    return normalize_dividends(data.get(CONF_DIVIDENDS, []))


def dividend_total(data: Mapping[str, Any], *, through: date | None = None) -> float:
    """Return net dividends credited through an optional date."""
    total = 0.0
    for item in dividends_from_data(data):
        effective = date.fromisoformat(
            item.get(DIVIDEND_VALUE_DATE) or item[DIVIDEND_BOOKING_DATE]
        )
        if through is None or effective <= through:
            total += float(item[DIVIDEND_AMOUNT])
    return total


def cash_events(
    data: Mapping[str, Any], *, contributions: Sequence[Mapping[str, Any]] | None = None
) -> list[tuple[date, float]]:
    """One definition of cash-effective deposits, dividends and purchases.

    Undated legacy capital and its included opening lots are cash-neutral.
    """
    events = [
        (
            date.fromisoformat(
                item.get(DIVIDEND_VALUE_DATE) or item[DIVIDEND_BOOKING_DATE]
            ),
            float(item[DIVIDEND_AMOUNT]),
        )
        for item in dividends_from_data(data)
    ]
    rows = contributions if contributions is not None else contributions_from_data(data)
    for row in rows:
        legacy = row[CONTRIBUTION_SOURCE] == CONTRIBUTION_SOURCE_LEGACY
        if not legacy and row.get(CONTRIBUTION_DATE) is not None:
            events.append(
                (
                    date.fromisoformat(str(row[CONTRIBUTION_DATE])),
                    float(row[CONTRIBUTION_AMOUNT]),
                )
            )
        events.extend(
            (date.fromisoformat(lot[LOT_DATE]), -float(lot[LOT_AMOUNT]))
            for lot in row[CONTRIBUTION_LOTS]
            if not (legacy and lot[LOT_INCLUDED_IN_OPENING])
        )
    return events


def cash_balance(
    data: Mapping[str, Any],
    *,
    through: date | None = None,
    contributions: Sequence[Mapping[str, Any]] | None = None,
) -> float:
    """Return the cash balance without discarding fractional currency precision."""
    return round(
        fsum(
            amount
            for day, amount in cash_events(data, contributions=contributions)
            if through is None or day <= through
        ),
        10,
    )


def cash_timeline(data: Mapping[str, Any]) -> dict[date, float]:
    """Calculate all closing balances in one chronological pass."""
    by_date: dict[date, list[float]] = {}
    for day, amount in cash_events(data):
        by_date.setdefault(day, []).append(amount)
    # Keep low-order remainders across dates. Collapsing each day's balance to
    # one float can lose small credits before a later purchase cancels it out.
    partials: list[float] = []
    result = {}
    for day, amounts in sorted(by_date.items()):
        for amount in amounts:
            index = 0
            for partial in partials:
                if abs(amount) < abs(partial):
                    amount, partial = partial, amount
                total = amount + partial
                remainder = partial - (total - amount)
                if remainder:
                    partials[index] = remainder
                    index += 1
                amount = total
            partials[index:] = [amount]
        result[day] = round(fsum(partials), 10)
    return result


def reinvestable_cash(
    data: Mapping[str, Any],
    *,
    execution_through: date,
    today: date,
    reserved: float = 0.0,
) -> float:
    """Use the minimum balance throughout the execution interval, minus reserves."""
    timeline = cash_timeline(data)
    at_execution = at_today = 0.0
    balances = []
    for day, balance in timeline.items():
        if day <= execution_through:
            at_execution = balance
        if day <= today:
            at_today = balance
        if execution_through <= day <= today:
            balances.append(balance)
    return max(0.0, min(at_execution, at_today, *balances) - float(reserved))


def attributed_dividend_flows(
    data: Mapping[str, Any],
    *,
    symbol: str,
    opening_units: float,
    through: date,
) -> dict[str, list[tuple[date, float]]]:
    """Allocate symbol dividends to tracked lots without over-attribution.

    Units from the configured opening position that are not represented by an
    included lot remain in the denominator. Their dividend share is therefore
    intentionally left unattributed instead of inflating tracked performance.
    """
    from .contributions import lots_for_symbol

    lots = lots_for_symbol(data, symbol, through=through)
    flows = {str(lot[LOT_ID]): [] for lot in lots}
    included_units = sum(
        float(lot[LOT_UNITS]) for lot in lots if lot[LOT_INCLUDED_IN_OPENING]
    )
    untracked_opening = max(0.0, float(opening_units) - included_units)
    for dividend in dividends_from_data(data):
        if dividend.get(DIVIDEND_SYMBOL) != symbol:
            continue
        effective = date.fromisoformat(
            dividend.get(DIVIDEND_VALUE_DATE) or dividend[DIVIDEND_BOOKING_DATE]
        )
        if effective > through:
            continue
        eligible = [
            lot for lot in lots if date.fromisoformat(lot[LOT_DATE]) <= effective
        ]
        denominator = untracked_opening + sum(float(lot[LOT_UNITS]) for lot in eligible)
        if denominator <= 0:
            continue
        for lot in eligible:
            allocated = (
                float(dividend[DIVIDEND_AMOUNT]) * float(lot[LOT_UNITS]) / denominator
            )
            flows[str(lot[LOT_ID])].append((effective, allocated))
    return flows
