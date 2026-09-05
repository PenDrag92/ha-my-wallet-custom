"""Prepare savings-plan bookings without changing persisted financial data."""

from __future__ import annotations

import calendar
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from typing import Any

from .const import (
    CONF_BASE_CURRENCY,
    CONF_CONTRIBUTIONS,
    CONF_SAVINGS_PLANS,
    CONF_VALORS,
    CONTRIBUTION_ID,
    CONTRIBUTION_LOTS,
    CONTRIBUTION_MANUALLY_EDITED,
    CONTRIBUTION_NOTE,
    CONTRIBUTION_PLAN_ID,
    CONTRIBUTION_SCHEDULED_DATE,
    CONTRIBUTION_SOURCE,
    CONTRIBUTION_SOURCE_PLAN,
    LOT_ESTIMATED,
    LOT_ID,
    LOT_INCLUDED_IN_OPENING,
    LOT_SYMBOL,
    LOT_UNITS,
    PLAN_AMOUNT,
    PLAN_ID,
    PLAN_NAME,
    PLAN_OPENING_CUTOFF_DATE,
    PLAN_USE_CASH_BALANCE,
    VALOR_AMOUNT,
    VALOR_SYMBOL,
)
from .contributions import (
    contributions_from_data,
    make_contribution,
    make_lot,
    opening_balance_conflicts,
)
from .dividends import reinvestable_cash
from .ledger import prepare_change, worsened_cash_history
from .plans import (
    allocation_amounts,
    due_dates,
    next_scheduled_date,
    normalize_plan,
    rule_for_date,
    schedule_period,
    scheduled_dates,
)
from .yahoo import (
    HistoricalQuote,
    Quote,
    YahooError,
    fetch_histories,
    fetch_history,
    fx_symbol,
)


def _close_date_bounds(close_dates: Sequence[date]) -> tuple[date, date]:
    if not close_dates:
        raise ValueError("At least one close date is required")
    return min(close_dates), max(close_dates)


def _execution_sort_key(
    close_dates: Sequence[date], scheduled: date, plan_id: str
) -> tuple[date, date, str]:
    return _close_date_bounds(close_dates)[0], scheduled, plan_id


def _included_opening_overflows(
    valors: Sequence[Mapping[str, Any]],
    contributions: Sequence[Mapping[str, Any]],
    proposed_lots: Sequence[Mapping[str, Any]],
) -> list[str]:
    symbols = {lot[LOT_SYMBOL] for lot in proposed_lots if lot[LOT_INCLUDED_IN_OPENING]}
    opening = {valor[VALOR_SYMBOL]: float(valor[VALOR_AMOUNT]) for valor in valors}
    units = dict.fromkeys(symbols, 0.0)
    for lot in [
        *(lot for row in contributions for lot in row[CONTRIBUTION_LOTS]),
        *proposed_lots,
    ]:
        if lot[LOT_SYMBOL] in units and lot[LOT_INCLUDED_IN_OPENING]:
            units[lot[LOT_SYMBOL]] += float(lot[LOT_UNITS])
    return sorted(
        symbol for symbol in symbols if units[symbol] > opening.get(symbol, 0) + 1e-9
    )


def is_manually_corrected(row: Mapping[str, Any]) -> bool:
    """Recognize explicit corrections, including old manually corrected lots."""
    return bool(row.get(CONTRIBUTION_MANUALLY_EDITED)) or any(
        not lot.get(LOT_ESTIMATED, True) for lot in row.get(CONTRIBUTION_LOTS, [])
    )


def recalculable_ids(
    contributions: Sequence[Mapping[str, Any]],
    plan_id: str,
    *,
    approved_legacy_ids: Sequence[str] = (),
) -> set[str]:
    """Legacy records need review: older versions did not flag deposit edits."""
    return {
        row[CONTRIBUTION_ID]
        for row in contributions
        if row.get(CONTRIBUTION_PLAN_ID) == plan_id
        and row.get(CONTRIBUTION_SOURCE) == CONTRIBUTION_SOURCE_PLAN
        and row.get(CONTRIBUTION_SCHEDULED_DATE)
        and not is_manually_corrected(row)
        and (
            row.get(CONTRIBUTION_MANUALLY_EDITED) is False
            or row[CONTRIBUTION_ID] in approved_legacy_ids
        )
    }


def _first_close(
    history: Sequence[HistoricalQuote], start: date, end: date
) -> HistoricalQuote | None:
    return next((quote for quote in history if start <= quote.date <= end), None)


def _merge_confirmed_quote(
    history: list[HistoricalQuote], quote: Quote | None
) -> list[HistoricalQuote]:
    by_date = {item.date: item for item in history}
    if quote is not None and quote.market_closed and quote.market_date is not None:
        by_date[quote.market_date] = HistoricalQuote(
            quote.symbol, quote.market_date, quote.price, quote.currency
        )
    return sorted(by_date.values(), key=lambda item: item.date)


async def async_prepare_executions(
    data: Mapping[str, Any],
    *,
    session: Any,
    today: date,
    current_quotes: dict[str, Quote | None] | None = None,
    only_plan_id: str | None = None,
    replace_ids: Sequence[str] = (),
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Prepare a transaction; a failed recalculation leaves every old row intact."""
    original = contributions_from_data(data)
    plans = [
        normalize_plan(plan)
        for plan in data.get(CONF_SAVINGS_PLANS, [])
        if only_plan_id is None or plan[PLAN_ID] == only_plan_id
    ]
    # Independently veto known manual corrections, even if a caller selects one.
    replacement_ids = {
        row[CONTRIBUTION_ID]
        for row in original
        if row[CONTRIBUTION_ID] in replace_ids
        and row.get(CONTRIBUTION_SOURCE) == CONTRIBUTION_SOURCE_PLAN
        and not is_manually_corrected(row)
        and any(
            row.get(CONTRIBUTION_PLAN_ID) == plan[PLAN_ID]
            and schedule_period(row[CONTRIBUTION_SCHEDULED_DATE])
            in {schedule_period(day) for day in scheduled_dates(plan, today)}
            for plan in plans
        )
    }
    replacements = {
        (
            row[CONTRIBUTION_PLAN_ID],
            schedule_period(row[CONTRIBUTION_SCHEDULED_DATE]),
        ): row
        for row in original
        if row[CONTRIBUTION_ID] in replacement_ids
    }
    rows = [row for row in original if row[CONTRIBUTION_ID] not in replacement_ids]
    report: dict[str, Any] = {
        "created": 0,
        "recalculated": 0,
        "pending": [],
        "failed": 0,
        "rolled_back": False,
    }
    due = [
        (rule_for_date(plan, day), day)
        for plan in plans
        for day in due_dates(plan, rows, today)
    ]
    result = dict(data)
    if not due:
        return result, report
    configured = {valor[VALOR_SYMBOL] for valor in data.get(CONF_VALORS, [])}
    invalid = [
        (plan, day, sorted(set(allocation_amounts(plan)) - configured))
        for plan, day in due
        if set(allocation_amounts(plan)) - configured
    ]
    if invalid:
        report["pending"] = [
            {
                "plan_id": plan[PLAN_ID],
                "plan_name": plan[PLAN_NAME],
                "scheduled_date": day.isoformat(),
                "reason": "unconfigured_symbol",
                "missing_symbols": symbols,
                "repair_required": True,
            }
            for plan, day, symbols in invalid
        ]
        report.update(failed=len(invalid), rolled_back=bool(replacement_ids))
        return result, report
    conflicts = opening_balance_conflicts(data)
    if conflicts:
        # Never build new history on top of contradictory legacy quantities,
        # including when an explicit recalculation would remove old rows.
        report["pending"] = [
            {
                "plan_id": plan[PLAN_ID],
                "plan_name": plan[PLAN_NAME],
                "scheduled_date": day.isoformat(),
                "reason": "opening_balance_conflict",
                "missing_symbols": [],
                "affected_symbols": [item["symbol"] for item in conflicts],
                "repair_required": True,
            }
            for plan, day in due
        ]
        report["rolled_back"] = bool(replacement_ids)
        report["failed"] = len(report["pending"])
        return result, report
    base_currency = str(data[CONF_BASE_CURRENCY])
    symbols = sorted({symbol for plan, _ in due for symbol in allocation_amounts(plan)})
    earliest = min(day for _, day in due)
    histories = await fetch_histories(session, symbols, earliest, today)
    for symbol in symbols:
        histories[symbol] = _merge_confirmed_quote(
            histories.get(symbol, []), (current_quotes or {}).get(symbol)
        )
    selected: dict[tuple[str, str], dict[str, HistoricalQuote]] = {}
    ready = []

    def pending(
        plan: Mapping[str, Any],
        day: date,
        reason: str,
        missing: Sequence[str] = (),
        *,
        repair: bool = False,
    ) -> None:
        report["pending"].append(
            {
                "plan_id": plan[PLAN_ID],
                "plan_name": plan[PLAN_NAME],
                "scheduled_date": day.isoformat(),
                "reason": reason,
                "missing_symbols": list(missing),
                "repair_required": repair,
            }
        )

    for plan, day in due:
        following = next_scheduled_date(plan, day + timedelta(days=1))
        if following is None:
            next_month = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
            following = next_month.replace(
                day=min(
                    day.day, calendar.monthrange(next_month.year, next_month.month)[1]
                )
            )
        window_end = min(today, following - timedelta(days=1))
        found = {
            symbol: _first_close(histories.get(symbol, []), day, window_end)
            for symbol in allocation_amounts(plan)
        }
        missing = [symbol for symbol, quote in found.items() if quote is None]
        if missing:
            pending(plan, day, "historical_price_unavailable", missing)
            continue
        selected[(plan[PLAN_ID], day.isoformat())] = found
        ready.append((plan, day))
    ready.sort(
        key=lambda item: _execution_sort_key(
            [
                quote.date
                for quote in selected[(item[0][PLAN_ID], item[1].isoformat())].values()
            ],
            item[1],
            item[0][PLAN_ID],
        )
    )
    foreign = {
        quote.currency
        for quotes in selected.values()
        for quote in quotes.values()
        if quote.currency != base_currency
    }
    fx_symbols = sorted(
        {
            symbol
            for source in foreign
            for symbol in (
                fx_symbol(source, base_currency),
                fx_symbol(base_currency, source),
            )
        }
    )
    fx_histories = (
        await fetch_histories(session, fx_symbols, earliest, today)
        if fx_symbols
        else {}
    )

    for plan, day in ready:
        quotes = selected[(plan[PLAN_ID], day.isoformat())]
        execution_date = min(quote.date for quote in quotes.values())
        available = float(plan[PLAN_AMOUNT])
        if plan[PLAN_USE_CASH_BALANCE]:
            available += reinvestable_cash(
                {**data, CONF_CONTRIBUTIONS: rows},
                execution_through=execution_date,
                today=today,
            )
        amounts = allocation_amounts(plan, available_amount=available)
        old = replacements.get((plan[PLAN_ID], schedule_period(day)))
        old_lot_ids = (
            {lot[LOT_SYMBOL]: lot[LOT_ID] for lot in old[CONTRIBUTION_LOTS]}
            if old
            else {}
        )
        lots = []
        for symbol, amount in amounts.items():
            quote = quotes[symbol]
            rate = 1.0
            if quote.currency != base_currency:
                direct = _first_close(
                    fx_histories.get(fx_symbol(quote.currency, base_currency), []),
                    quote.date,
                    min(today, quote.date + timedelta(days=7)),
                )
                inverse = _first_close(
                    fx_histories.get(fx_symbol(base_currency, quote.currency), []),
                    quote.date,
                    min(today, quote.date + timedelta(days=7)),
                )
                if direct is not None:
                    rate = direct.close
                elif inverse is not None and inverse.close:
                    rate = 1 / inverse.close
                else:
                    pending(plan, day, "historical_fx_unavailable", [symbol])
                    break
            if amount <= 0:
                pending(plan, day, "allocation_too_small", [symbol], repair=True)
                break
            lots.append(
                make_lot(
                    symbol=symbol,
                    execution_date=quote.date,
                    amount=amount,
                    unit_price=quote.close,
                    quote_currency=quote.currency,
                    fx_rate=rate,
                    included_in_opening=bool(
                        plan[PLAN_OPENING_CUTOFF_DATE]
                        and quote.date.isoformat() <= plan[PLAN_OPENING_CUTOFF_DATE]
                    ),
                    estimated=True,
                    lot_id=old_lot_ids.get(symbol),
                )
            )
        if len(lots) != len(amounts):
            continue
        overflows = _included_opening_overflows(data.get(CONF_VALORS, []), rows, lots)
        if overflows:
            pending(plan, day, "included_units_exceeded", overflows, repair=True)
            report["pending"][-1]["affected_symbols"] = overflows
            continue
        rows.append(
            make_contribution(
                plan[PLAN_AMOUNT],
                day,
                contribution_id=old[CONTRIBUTION_ID] if old else None,
                source=CONTRIBUTION_SOURCE_PLAN,
                lots=lots,
                plan_id=plan[PLAN_ID],
                plan_name=plan[PLAN_NAME],
                scheduled_date=day,
                manually_edited=False,
                note=old.get(CONTRIBUTION_NOTE) if old else None,
            )
        )
        report["recalculated" if old else "created"] += 1
    result[CONF_CONTRIBUTIONS] = contributions_from_data({CONF_CONTRIBUTIONS: rows})
    if replacement_ids and (
        report["pending"] or worsened_cash_history(data, result, today)
    ):
        if not report["pending"]:
            report["pending"].append(
                {
                    "plan_id": only_plan_id,
                    "reason": "cash_conflict",
                    "repair_required": True,
                    "missing_symbols": [],
                    "scheduled_date": earliest.isoformat(),
                }
            )
        result[CONF_CONTRIBUTIONS] = original
        report.update(created=0, recalculated=0, rolled_back=True)
    report["failed"] = sum(
        bool(item.get("repair_required")) for item in report["pending"]
    )
    return prepare_change(data, result, today=today), report


async def async_purchase_lot(
    *,
    session: Any,
    symbol: str,
    requested_date: date,
    amount: float,
    base_currency: str,
    today: date,
    included_in_opening: bool,
    manual_price: float | None = None,
    units: float | None = None,
) -> dict[str, Any]:
    """Resolve one historical purchase, with manual price/units as alternatives."""
    if requested_date > today:
        raise ValueError("future_date")
    if manual_price is not None and units is not None:
        raise ValueError("price_or_units")
    quote_date, currency, rate = requested_date, base_currency, 1.0
    estimated = manual_price is None and units is None
    price = amount / units if units is not None and units > 0 else manual_price
    if estimated:
        try:
            history = await fetch_history(
                session,
                symbol,
                requested_date,
                min(today, requested_date + timedelta(days=14)),
            )
        except YahooError:
            history = []
        if not history:
            raise ValueError("historical_price_unavailable")
        quote = history[0]
        quote_date, currency, price = quote.date, quote.currency, quote.close
        if currency != base_currency:
            histories = await fetch_histories(
                session,
                [
                    fx_symbol(currency, base_currency),
                    fx_symbol(base_currency, currency),
                ],
                quote_date,
                min(today, quote_date + timedelta(days=7)),
            )
            direct = histories.get(fx_symbol(currency, base_currency), [])
            inverse = histories.get(fx_symbol(base_currency, currency), [])
            if direct:
                rate = direct[0].close
            elif inverse and inverse[0].close:
                rate = 1 / inverse[0].close
            else:
                raise ValueError("historical_fx_unavailable")
    return make_lot(
        symbol=symbol,
        execution_date=quote_date,
        amount=amount,
        unit_price=price,
        quote_currency=currency,
        fx_rate=rate,
        units=units,
        included_in_opening=included_in_opening,
        estimated=estimated,
    )
