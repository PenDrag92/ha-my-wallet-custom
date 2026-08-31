"""Pure helpers for dividend income and the broker cash balance."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
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
    if normalized_amount <= 0:
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


def cash_balance(
    data: Mapping[str, Any],
    *,
    through: date | None = None,
    contributions: Sequence[Mapping[str, Any]] | None = None,
) -> float:
    """Return deposits plus dividends minus purchases on the cash account.

    Legacy invested amounts are cost-basis placeholders rather than known cash
    deposits and therefore do not affect this balance.
    """
    balance = dividend_total(data, through=through)
    rows = (
        list(contributions)
        if contributions is not None
        else contributions_from_data(data)
    )
    for contribution in rows:
        contribution_date = contribution.get(CONTRIBUTION_DATE)
        if (
            contribution[CONTRIBUTION_SOURCE] != CONTRIBUTION_SOURCE_LEGACY
            and contribution_date is not None
            and (
                through is None or date.fromisoformat(str(contribution_date)) <= through
            )
        ):
            balance += float(contribution[CONTRIBUTION_AMOUNT])

        for lot in contribution[CONTRIBUTION_LOTS]:
            if through is None or date.fromisoformat(lot[LOT_DATE]) <= through:
                balance -= float(lot[LOT_AMOUNT])

    # Avoid display artefacts such as 0.00999999999999801 without discarding
    # fractional currency precision used by some brokers.
    return round(balance, 10)
