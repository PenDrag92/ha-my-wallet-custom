"""Reconstruct a dated wallet history without writing recorder statistics."""

from __future__ import annotations

import calendar
from bisect import bisect_right
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from . import const as c
from .analytics import period_summaries
from .contributions import (
    all_lots,
    contributions_from_data,
    opening_balance_conflicts,
)
from .dividends import dividends_from_data
from .inflation import (
    InflationSeries,
    expected_annual_inflation,
    future_inflation_factor,
    purchasing_power,
)
from .target import (
    FORECAST_YEARS,
    add_years,
    target_contribution_series,
    target_projection,
    target_series,
    target_snapshots,
)
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


def _add_months(value: date, months: int) -> date:
    """Move a dashboard sample date by whole calendar months."""
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _forecast_sample_dates(projection, *, today: date, through: date) -> list[date]:
    """Sample long forecasts monthly and at every planned cash-flow date."""
    dates = {
        flow.date for flow in projection.cash_flows if today < flow.date <= through
    }
    month = 1
    while (candidate := _add_months(today, month)) < through:
        dates.add(candidate)
        month += 1
    dates.add(through)
    return sorted(dates)


def _today_value(
    amount: float,
    when: date,
    *,
    today: date,
    inflation: InflationSeries | None,
    expected_inflation: float,
) -> float | None:
    """Express a dated amount in today's purchasing power."""
    if inflation is None:
        return None
    if when <= today:
        return inflation.adjust(amount, when, today)
    return purchasing_power(
        amount,
        today=today,
        through=when,
        annual_percent=expected_inflation,
    )


def _real_target_contributions(
    projection,
    *,
    through: date,
    today: date,
    inflation: InflationSeries | None,
    expected_inflation: float,
) -> float | None:
    """Return planned external capital in today's purchasing power."""
    if projection.value is None or projection.start_date is None:
        return None
    values = []
    for flow in projection.cash_flows:
        if not projection.start_date <= flow.date <= through:
            continue
        value = _today_value(
            flow.amount,
            flow.date,
            today=today,
            inflation=inflation,
            expected_inflation=expected_inflation,
        )
        if value is None:
            return None
        values.append(value)
    return sum(values)


def build_history(
    data,
    histories,
    *,
    today: date,
    forecast_years: int | None = None,
    inflation: InflationSeries | None = None,
) -> dict[str, Any]:
    """Price only dated holdings; an unknown opening position leaves gaps."""
    events = [
        row
        for row in ledger_rows(data)
        if not row["date"] or row["date"] <= today.isoformat()
    ]
    expected_inflation = expected_annual_inflation(data)
    real_events_complete = inflation is not None
    for row in events:
        event_date = row.get("date")
        adjusted = (
            _today_value(
                float(row["amount"]),
                date.fromisoformat(event_date),
                today=today,
                inflation=inflation,
                expected_inflation=expected_inflation,
            )
            if event_date
            else None
        )
        row["real_amount"] = round(adjusted, 2) if adjusted is not None else None
        if adjusted is None and abs(float(row["amount"])) > 1e-12:
            real_events_complete = False
    eligible = [
        row for row in events if not row["date"] or row["date"] <= today.isoformat()
    ]
    days = [date.fromisoformat(row["date"]) for row in eligible if row["date"]]
    first = min(days, default=today)
    start = max(first, today - timedelta(days=MAX_HISTORY_DAYS))
    range_limited = start != first
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
    can_start_at_zero = (
        bool(days)
        and start == first
        and not unknown_opening
        and not conflicts
        and all(float(valor[c.VALOR_AMOUNT]) <= 1e-10 for valor in data[c.CONF_VALORS])
    )
    if can_start_at_zero:
        start -= timedelta(days=1)
    positions = defaultdict(float)
    position_costs = defaultdict(float)
    position_dividends = defaultdict(float)
    real_position_costs = defaultdict(float)
    real_position_dividends = defaultdict(float)
    cash = invested = 0.0
    real_invested = 0.0
    total_dividends = real_dividends = 0.0
    pointer = 0
    points = []
    requested_years = forecast_years or max(FORECAST_YEARS)
    horizons = tuple(sorted({*FORECAST_YEARS, requested_years}))
    forecast_through = add_years(today, max(horizons))
    projection = target_projection(data, through=forecast_through)
    target_values = target_series(projection, start=start, through=today)
    target_contributions = target_contribution_series(
        projection, start=start, through=today
    )
    future_dates = _forecast_sample_dates(
        projection, today=today, through=forecast_through
    )
    horizon_dates = [add_years(today, years) for years in horizons]
    future_snapshots = target_snapshots(projection, [*future_dates, *horizon_dates])
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
                if row["real_amount"] is not None:
                    real_invested += row["real_amount"]
            if row["type"] == "purchase":
                positions[row["symbol"]] += row["units"]
                position_costs[row["symbol"]] += -row["amount"]
                if row["real_amount"] is not None:
                    real_position_costs[row["symbol"]] += -row["real_amount"]
            if row["type"] == "dividend":
                total_dividends += row["amount"]
                if row["real_amount"] is not None:
                    real_dividends += row["real_amount"]
            if row["type"] == "dividend" and row.get("symbol"):
                position_dividends[row["symbol"]] += row["amount"]
                if row["real_amount"] is not None:
                    real_position_dividends[row["symbol"]] += row["real_amount"]
            pointer += 1
        value = cash
        complete = not unknown_opening and not conflicts
        position_values = {}
        for symbol, units in positions.items():
            if units <= 1e-10:
                continue
            quote = latest_close(histories.get(symbol, []), day)
            fx = historical_fx(histories, quote.currency, base, day) if quote else None
            if quote is None or fx is None:
                complete = False
                missing.add(symbol)
            else:
                position_values[symbol] = round(units * quote.close * fx, 2)
                value += position_values[symbol]
        for symbol in {valor[c.VALOR_SYMBOL] for valor in data[c.CONF_VALORS]}:
            if positions[symbol] > 1e-10 and symbol not in position_values:
                position_values[symbol] = None
        price_factor = inflation.factor(day, today) if inflation is not None else None
        real_value = (
            value * price_factor if complete and price_factor is not None else None
        )
        real_positions = {
            symbol: (
                round(position_value * price_factor, 2)
                if position_value is not None and price_factor is not None
                else None
            )
            for symbol, position_value in position_values.items()
        }
        target_value = target_values.get(day.isoformat())
        points.append(
            {
                "date": day.isoformat(),
                "invested": round(invested, 2),
                "dividends": round(total_dividends, 2),
                "real_dividends": round(real_dividends, 2)
                if real_events_complete
                else None,
                "cash": round(cash, 2),
                "value": round(value, 2) if complete else None,
                "profit": round(value - invested, 2) if complete else None,
                "positions": position_values,
                "position_costs": {
                    symbol: round(position_costs[symbol], 2)
                    for symbol in position_values
                },
                "position_dividends": {
                    symbol: round(position_dividends[symbol], 2)
                    for symbol in position_values
                },
                "real_invested": (
                    round(real_invested, 2) if real_events_complete else None
                ),
                "real_cash": (
                    round(cash * price_factor, 2) if price_factor is not None else None
                ),
                "real_value": round(real_value, 2) if real_value is not None else None,
                "real_profit": (
                    round(real_value - real_invested, 2)
                    if real_value is not None and real_events_complete
                    else None
                ),
                "real_positions": real_positions,
                "real_position_costs": {
                    symbol: round(real_position_costs[symbol], 2)
                    if real_events_complete
                    else None
                    for symbol in position_values
                },
                "real_position_dividends": {
                    symbol: round(real_position_dividends[symbol], 2)
                    if real_events_complete
                    else None
                    for symbol in position_values
                },
                "inflation_factor": price_factor,
                "baseline": can_start_at_zero and day == start,
                "target": target_value,
                "real_target": (
                    round(target_value * price_factor, 2)
                    if target_value is not None and price_factor is not None
                    else None
                ),
            }
        )
        day += timedelta(days=1)

    def target_snapshot(through: date) -> dict[str, Any]:
        key = through.isoformat()
        future = future_snapshots.get(key, {})
        value = target_values.get(key, future.get("value"))
        contributions = target_contributions.get(key, future.get("contributions"))
        if value is None:
            contributions = None
        if through <= today:
            price_factor = (
                inflation.factor(through, today) if inflation is not None else None
            )
            real_value = (
                value * price_factor if value is not None and price_factor else None
            )
        else:
            price_factor = future_inflation_factor(expected_inflation, today, through)
            real_value = value / price_factor if value is not None else None
        real_contributions = _real_target_contributions(
            projection,
            through=through,
            today=today,
            inflation=inflation,
            expected_inflation=expected_inflation,
        )
        return {
            "date": through.isoformat(),
            "value": value,
            "contributions": (
                round(contributions, 2) if contributions is not None else None
            ),
            "growth": (
                round(value - contributions, 2)
                if value is not None and contributions is not None
                else None
            ),
            "real_value": round(real_value, 2) if real_value is not None else None,
            "real_contributions": (
                round(real_contributions, 2) if real_contributions is not None else None
            ),
            "real_growth": (
                round(real_value - real_contributions, 2)
                if real_value is not None and real_contributions is not None
                else None
            ),
            "inflation_effect": (
                round(value - real_value, 2)
                if value is not None and real_value is not None
                else None
            ),
            "inflation_factor": round(price_factor, 8) if price_factor else None,
        }

    current_target = target_snapshot(today)
    forecasts = {
        str(years): target_snapshot(add_years(today, years)) for years in horizons
    }
    for forecast in forecasts.values():
        forecast["additional_contributions"] = (
            round(forecast["contributions"] - current_target["contributions"], 2)
            if forecast["contributions"] is not None
            and current_target["contributions"] is not None
            else None
        )
        forecast["additional_real_contributions"] = (
            round(
                forecast["real_contributions"] - current_target["real_contributions"],
                2,
            )
            if forecast["real_contributions"] is not None
            and current_target["real_contributions"] is not None
            else None
        )
    target_forecast = []
    for forecast_day, snapshot in future_snapshots.items():
        if forecast_day <= today.isoformat():
            continue
        real_snapshot = target_snapshot(date.fromisoformat(forecast_day))
        target_forecast.append(
            {
                "date": forecast_day,
                "target": snapshot["value"],
                "invested": snapshot["contributions"],
                "real_target": real_snapshot["real_value"],
                "real_invested": real_snapshot["real_contributions"],
                "inflation_factor": real_snapshot["inflation_factor"],
            }
        )

    result = {
        "points": points,
        "ledger": events,
        "estimated": any(row.get("estimated") for row in events),
        "unknown_opening": unknown_opening,
        "opening_conflicts": conflicts,
        "missing_history": sorted(missing),
        "range_limited": range_limited,
        "inflation": {
            "available": inflation is not None,
            "source": inflation.source if inflation is not None else None,
            "region": inflation.region if inflation is not None else None,
            "latest_month": inflation.latest_month if inflation is not None else None,
            "stale": inflation.stale if inflation is not None else False,
            "expected_annual_inflation": expected_inflation,
        },
        "target": {
            "annual_return": projection.annual_return,
            "expected_annual_inflation": expected_inflation,
            "monthly_return": projection.monthly_return,
            "start_date": (
                projection.start_date.isoformat() if projection.start_date else None
            ),
            "date": today.isoformat(),
            "current_value": current_target["value"],
            "real_current_value": current_target["real_value"],
            "contributions": current_target["contributions"],
            "real_contributions": current_target["real_contributions"],
            "growth": current_target["growth"],
            "real_growth": current_target["real_growth"],
            "unavailable_reason": projection.unavailable_reason,
            "calculation_basis": "planned_savings_rates",
            "forecasts": forecasts,
        },
        "target_forecast": target_forecast,
    }
    result["summaries"] = {
        "wallet": period_summaries(points, events),
        "positions": {
            valor[c.VALOR_SYMBOL]: period_summaries(
                points, events, symbol=valor[c.VALOR_SYMBOL]
            )
            for valor in data[c.CONF_VALORS]
        },
    }
    if real_events_complete:
        real_points = [
            {
                **point,
                "value": point["real_value"],
                "invested": point["real_invested"],
                "positions": point["real_positions"],
                "position_costs": point["real_position_costs"],
                "position_dividends": point["real_position_dividends"],
            }
            for point in points
        ]
        real_ledger = [{**event, "amount": event["real_amount"]} for event in events]
        result["summaries_real"] = {
            "wallet": period_summaries(real_points, real_ledger),
            "positions": {
                valor[c.VALOR_SYMBOL]: period_summaries(
                    real_points,
                    real_ledger,
                    symbol=valor[c.VALOR_SYMBOL],
                )
                for valor in data[c.CONF_VALORS]
            },
        }
    else:
        result["summaries_real"] = None
    return result


async def async_history(
    data,
    *,
    session,
    today: date,
    forecast_years: int | None = None,
    inflation: InflationSeries | None = None,
) -> dict[str, Any]:
    events = ledger_rows(data)
    days = [
        date.fromisoformat(row["date"])
        for row in events
        if row["date"] and row["date"] <= today.isoformat()
    ]
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
    return build_history(
        data,
        histories,
        today=today,
        forecast_years=forecast_years,
        inflation=inflation,
    )
