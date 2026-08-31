"""Pure helpers for dated executions, purchase lots, and performance."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from math import isfinite
from typing import Any
from uuid import uuid4

from .const import (
    CONF_CONTRIBUTIONS,
    CONF_INVESTED_AMOUNT,
    CONF_VALORS,
    CONTRIBUTION_AMOUNT,
    CONTRIBUTION_DATE,
    CONTRIBUTION_ID,
    CONTRIBUTION_LOTS,
    CONTRIBUTION_MANUALLY_EDITED,
    CONTRIBUTION_NOTE,
    CONTRIBUTION_PLAN_ID,
    CONTRIBUTION_PLAN_NAME,
    CONTRIBUTION_SCHEDULED_DATE,
    CONTRIBUTION_SOURCE,
    CONTRIBUTION_SOURCE_LEGACY,
    CONTRIBUTION_SOURCE_MANUAL,
    CONTRIBUTION_SOURCE_PURCHASE,
    LOT_AMOUNT,
    LOT_DATE,
    LOT_ESTIMATED,
    LOT_FX_RATE,
    LOT_ID,
    LOT_INCLUDED_IN_OPENING,
    LOT_QUOTE_CURRENCY,
    LOT_SYMBOL,
    LOT_UNIT_PRICE,
    LOT_UNITS,
    VALOR_AMOUNT,
    VALOR_SYMBOL,
)

LEGACY_CONTRIBUTION_ID = "legacy_invested_amount"
_DAYS_PER_YEAR = 365.2425


def normalize_date(value: Any, *, allow_none: bool = False) -> str | None:
    """Return an ISO date."""
    if value is None or value == "":
        if allow_none:
            return None
        raise ValueError("A date is required")
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(str(value)).isoformat()


def make_lot(
    *,
    symbol: str,
    execution_date: Any,
    amount: Any,
    unit_price: Any,
    quote_currency: str,
    fx_rate: Any = 1.0,
    units: Any | None = None,
    included_in_opening: bool = False,
    estimated: bool = True,
    lot_id: str | None = None,
    price_date: Any | None = None,
) -> dict[str, Any]:
    """Create and validate one purchase lot."""
    normalized_amount = float(amount)
    normalized_price = float(unit_price)
    normalized_fx = float(fx_rate)
    if not isfinite(normalized_amount) or normalized_amount <= 0:
        raise ValueError("Lot amount must be greater than zero")
    if (
        not isfinite(normalized_price)
        or not isfinite(normalized_fx)
        or normalized_price <= 0
        or normalized_fx <= 0
    ):
        raise ValueError("Lot price and FX rate must be greater than zero")

    normalized_units = (
        float(units)
        if units is not None
        else normalized_amount / (normalized_price * normalized_fx)
    )
    if not isfinite(normalized_units) or normalized_units <= 0:
        raise ValueError("Lot units must be greater than zero")

    normalized_symbol = symbol.strip().upper()
    normalized_currency = quote_currency.strip().upper()
    if not normalized_symbol or not normalized_currency:
        raise ValueError("Lot symbol and quote currency are required")
    item = {
        LOT_ID: lot_id or uuid4().hex,
        LOT_SYMBOL: normalized_symbol,
        LOT_DATE: normalize_date(execution_date),
        LOT_AMOUNT: normalized_amount,
        LOT_UNIT_PRICE: normalized_price,
        LOT_QUOTE_CURRENCY: normalized_currency,
        LOT_FX_RATE: normalized_fx,
        LOT_UNITS: normalized_units,
        LOT_INCLUDED_IN_OPENING: bool(included_in_opening),
        LOT_ESTIMATED: bool(estimated),
    }
    if price_date is not None:
        item["price_date"] = normalize_date(price_date)
    return item


def normalize_lot(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a serialized lot."""
    return make_lot(
        symbol=str(entry[LOT_SYMBOL]),
        execution_date=entry[LOT_DATE],
        amount=entry[LOT_AMOUNT],
        unit_price=entry[LOT_UNIT_PRICE],
        quote_currency=str(entry[LOT_QUOTE_CURRENCY]),
        fx_rate=entry.get(LOT_FX_RATE, 1.0),
        units=entry.get(LOT_UNITS),
        included_in_opening=bool(entry.get(LOT_INCLUDED_IN_OPENING, False)),
        estimated=bool(entry.get(LOT_ESTIMATED, True)),
        lot_id=str(entry.get(LOT_ID) or uuid4().hex),
        price_date=entry.get("price_date"),
    )


def make_contribution(
    amount: Any | None,
    execution_date: Any,
    contribution_id: str | None = None,
    *,
    source: str = CONTRIBUTION_SOURCE_MANUAL,
    lots: Sequence[Mapping[str, Any]] | None = None,
    plan_id: str | None = None,
    scheduled_date: Any | None = None,
    note: str | None = None,
    plan_name: str | None = None,
    manually_edited: bool | None = None,
) -> dict[str, Any]:
    """Create one execution group, optionally containing purchase lots."""
    normalized_lots = [normalize_lot(item) for item in (lots or [])]
    normalized_date = normalize_date(execution_date, allow_none=True)
    if source == CONTRIBUTION_SOURCE_LEGACY and any(
        not lot[LOT_INCLUDED_IN_OPENING] for lot in normalized_lots
    ):
        raise ValueError("Legacy funding only accepts opening-balance lots")
    if normalized_date is not None and any(
        date.fromisoformat(lot[LOT_DATE]) < date.fromisoformat(normalized_date)
        for lot in normalized_lots
    ):
        raise ValueError("Funding contribution date must not be after lot date")
    normalized_amount = (
        sum(item[LOT_AMOUNT] for item in normalized_lots)
        if amount is None and normalized_lots
        else float(amount or 0)
    )
    purchase_only = source == CONTRIBUTION_SOURCE_PURCHASE
    if not isfinite(normalized_amount) or (
        normalized_amount != 0 if purchase_only else normalized_amount <= 0
    ):
        raise ValueError("Contribution amount must be greater than zero")

    item: dict[str, Any] = {
        CONTRIBUTION_ID: contribution_id or uuid4().hex,
        CONTRIBUTION_DATE: normalized_date,
        CONTRIBUTION_AMOUNT: normalized_amount,
        CONTRIBUTION_SOURCE: source,
        CONTRIBUTION_LOTS: normalized_lots,
    }
    if plan_id:
        item[CONTRIBUTION_PLAN_ID] = plan_id
    if scheduled_date is not None:
        item[CONTRIBUTION_SCHEDULED_DATE] = normalize_date(scheduled_date)
    if note and note.strip():
        item[CONTRIBUTION_NOTE] = note.strip()
    if plan_name:
        item[CONTRIBUTION_PLAN_NAME] = plan_name
    # Absence is intentional: old versions did not track manual corrections.
    # Such records need explicit review before they may be recalculated.
    if manually_edited is not None:
        item[CONTRIBUTION_MANUALLY_EDITED] = bool(manually_edited)
    return item


def normalize_contribution(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a serialized execution group, including version-2 rows."""
    return make_contribution(
        entry.get(CONTRIBUTION_AMOUNT),
        entry.get(CONTRIBUTION_DATE),
        contribution_id=str(entry.get(CONTRIBUTION_ID) or uuid4().hex),
        source=str(entry.get(CONTRIBUTION_SOURCE) or CONTRIBUTION_SOURCE_MANUAL),
        lots=entry.get(CONTRIBUTION_LOTS, []),
        plan_id=entry.get(CONTRIBUTION_PLAN_ID),
        scheduled_date=entry.get(CONTRIBUTION_SCHEDULED_DATE),
        note=entry.get(CONTRIBUTION_NOTE),
        plan_name=entry.get(CONTRIBUTION_PLAN_NAME),
        manually_edited=entry.get(CONTRIBUTION_MANUALLY_EDITED),
    )


def normalize_contributions(
    entries: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Validate execution groups and order them chronologically."""
    normalized = [normalize_contribution(entry) for entry in entries]
    return sorted(
        normalized,
        key=lambda item: (
            item[CONTRIBUTION_DATE] is None,
            item[CONTRIBUTION_DATE] or "",
            item[CONTRIBUTION_ID],
        ),
    )


def attach_lot(
    entries: Sequence[Mapping[str, Any]],
    contribution_id: str,
    lot: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Attach a purchase lot to an existing external contribution."""
    contributions = normalize_contributions(entries)
    contribution = next(
        (item for item in contributions if item[CONTRIBUTION_ID] == contribution_id),
        None,
    )
    if contribution is None:
        raise ValueError("Funding contribution does not exist")
    normalized_lot = normalize_lot(lot)
    if (
        contribution[CONTRIBUTION_SOURCE] == CONTRIBUTION_SOURCE_LEGACY
        and not normalized_lot[LOT_INCLUDED_IN_OPENING]
    ):
        raise ValueError("Legacy funding only accepts opening-balance lots")
    contribution_date = contribution[CONTRIBUTION_DATE]
    if contribution_date is not None and date.fromisoformat(
        contribution_date
    ) > date.fromisoformat(normalized_lot[LOT_DATE]):
        raise ValueError("Funding contribution date must not be after lot date")

    updated: list[dict[str, Any]] = []
    for item in contributions:
        if item[CONTRIBUTION_ID] != contribution_id:
            updated.append(item)
            continue
        updated.append(
            make_contribution(
                item[CONTRIBUTION_AMOUNT],
                item[CONTRIBUTION_DATE],
                contribution_id=item[CONTRIBUTION_ID],
                source=item[CONTRIBUTION_SOURCE],
                lots=[*item[CONTRIBUTION_LOTS], normalized_lot],
                plan_id=item.get(CONTRIBUTION_PLAN_ID),
                scheduled_date=item.get(CONTRIBUTION_SCHEDULED_DATE),
                note=item.get(CONTRIBUTION_NOTE),
                plan_name=item.get(CONTRIBUTION_PLAN_NAME),
                manually_edited=True,
            )
        )
    return normalize_contributions(updated)


def contributions_from_data(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Read execution groups, with a fallback for version-1 config data."""
    if CONF_CONTRIBUTIONS in data:
        return normalize_contributions(data.get(CONF_CONTRIBUTIONS, []))

    legacy_amount = data.get(CONF_INVESTED_AMOUNT)
    if legacy_amount is None or float(legacy_amount) <= 0:
        return []
    return [
        make_contribution(
            legacy_amount,
            None,
            contribution_id=LEGACY_CONTRIBUTION_ID,
            source=CONTRIBUTION_SOURCE_LEGACY,
        )
    ]


def contributions_through(
    data: Mapping[str, Any], through: date | None = None
) -> list[dict[str, Any]]:
    """Return contributions effective on or before ``through``.

    Legacy contributions without a date remain included because their original
    execution date is unknown.
    """
    return [
        item
        for item in contributions_from_data(data)
        if through is None
        or item[CONTRIBUTION_DATE] is None
        or date.fromisoformat(item[CONTRIBUTION_DATE]) <= through
    ]


def invested_total(
    data: Mapping[str, Any], *, through: date | None = None
) -> float | None:
    """Return the sum of all executed contributions."""
    contributions = contributions_through(data, through)
    if not contributions:
        return None
    return sum(item[CONTRIBUTION_AMOUNT] for item in contributions)


def all_lots(
    data: Mapping[str, Any], *, through: date | None = None
) -> list[dict[str, Any]]:
    """Flatten every tracked purchase lot."""
    return [
        lot
        for contribution in contributions_through(data, through)
        for lot in contribution[CONTRIBUTION_LOTS]
        if through is None or date.fromisoformat(lot[LOT_DATE]) <= through
    ]


def lots_for_symbol(
    data: Mapping[str, Any], symbol: str, *, through: date | None = None
) -> list[dict[str, Any]]:
    """Return purchase lots for one Yahoo symbol."""
    normalized_symbol = symbol.upper()
    return [
        lot
        for lot in all_lots(data, through=through)
        if lot[LOT_SYMBOL] == normalized_symbol
    ]


def opening_balance_conflicts(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Describe legacy inconsistencies without guessing or rewriting holdings."""
    included: dict[str, float] = {}
    for lot in all_lots(data):
        if lot[LOT_INCLUDED_IN_OPENING]:
            symbol = lot[LOT_SYMBOL]
            included[symbol] = included.get(symbol, 0.0) + float(lot[LOT_UNITS])
    return sorted(
        [
            {
                "symbol": valor[VALOR_SYMBOL],
                "configured_units": float(valor[VALOR_AMOUNT]),
                "included_units": included[valor[VALOR_SYMBOL]],
            }
            for valor in data.get(CONF_VALORS, [])
            if included.get(valor[VALOR_SYMBOL], 0.0)
            > float(valor[VALOR_AMOUNT]) + 1e-9
        ],
        key=lambda item: item["symbol"],
    )


def additional_units(
    data: Mapping[str, Any], symbol: str, *, through: date | None = None
) -> float:
    """Units created after the configured opening balance."""
    return sum(
        lot[LOT_UNITS]
        for lot in lots_for_symbol(data, symbol, through=through)
        if not lot[LOT_INCLUDED_IN_OPENING]
    )


def lot_metrics(
    lot: Mapping[str, Any],
    current_unit_price_base: float,
    as_of: date,
    income: float = 0.0,
) -> dict[str, float | None]:
    """Calculate current value and returns for one purchase lot."""
    invested = float(lot[LOT_AMOUNT])
    current_value = float(lot[LOT_UNITS]) * current_unit_price_base
    profit = current_value + float(income) - invested
    performance = profit / invested * 100
    lot_date = date.fromisoformat(str(lot[LOT_DATE]))
    age_days = max(0, (as_of - lot_date).days)
    annualized: float | None = None
    if age_days > 0 and current_value + income > 0:
        try:
            annualized = (
                ((current_value + income) / invested) ** (_DAYS_PER_YEAR / age_days) - 1
            ) * 100
        except (OverflowError, ZeroDivisionError):
            annualized = None
        else:
            if not isfinite(annualized):
                annualized = None
    return {
        "current_value": current_value,
        "profit": profit,
        "performance_pct": performance,
        "annualized_performance_pct": annualized,
        "age_days": float(age_days),
    }


def cashflows(
    data: Mapping[str, Any], *, through: date | None = None
) -> list[tuple[date, float]] | None:
    """Return dated external deposits, or None if a date is missing.

    Purchase-lot amounts can exceed a deposit when accumulated dividend cash is
    included in a savings-plan execution. The contribution itself is therefore
    the external cashflow; lots are only the internal use of that cash.
    """
    result: list[tuple[date, float]] = []
    for contribution in contributions_through(data, through):
        if contribution[CONTRIBUTION_AMOUNT] == 0:
            continue
        contribution_date = contribution[CONTRIBUTION_DATE]
        if contribution_date is None:
            return None
        result.append(
            (
                date.fromisoformat(contribution_date),
                -float(contribution[CONTRIBUTION_AMOUNT]),
            )
        )
    return result


def xirr(flows: Sequence[tuple[date, float]]) -> float | None:
    """Calculate an annual money-weighted return for conventional cashflows."""
    if (
        len({flow_date for flow_date, _ in flows}) < 2
        or any(not isfinite(float(value)) for _, value in flows)
        or (
            not flows
            or not any(value < 0 for _, value in flows)
            or not any(value > 0 for _, value in flows)
        )
    ):
        return None
    origin = min(flow_date for flow_date, _ in flows)

    def npv(rate: float) -> float:
        return sum(
            value / (1 + rate) ** ((flow_date - origin).days / _DAYS_PER_YEAR)
            for flow_date, value in flows
        )

    low = -0.999999
    high = 1.0
    low_value = npv(low)
    high_value = npv(high)
    while low_value * high_value > 0 and high < 1_000_000:
        high *= 2
        high_value = npv(high)
    if low_value * high_value > 0:
        return None

    for _ in range(200):
        middle = (low + high) / 2
        middle_value = npv(middle)
        if abs(middle_value) < 1e-9:
            return middle
        if low_value * middle_value <= 0:
            high = middle
        else:
            low = middle
            low_value = middle_value
    return (low + high) / 2


def money_weighted_return(
    data: Mapping[str, Any], current_value: float, as_of: date
) -> float | None:
    """Return the wallet XIRR in percent, using today's value as terminal flow."""
    flows = cashflows(data, through=as_of)
    if (
        flows is None
        or not flows
        or not isfinite(float(current_value))
        or current_value <= 0
    ):
        return None
    result = xirr([*flows, (as_of, current_value)])
    return result * 100 if result is not None else None
