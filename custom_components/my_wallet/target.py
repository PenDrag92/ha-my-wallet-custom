"""Compound-return target based on documented funding and savings plans."""

from __future__ import annotations

import calendar
from collections import defaultdict
from collections.abc import Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import date, timedelta
from math import isfinite
from typing import Any

from . import const as c
from .contributions import (
    all_lots,
    contributions_from_data,
    opening_balance_conflicts,
)
from .plans import (
    allocation_amounts,
    execution_rules,
    normalize_plan,
    rule_for_date,
    schedule_period,
)

_DAYS_PER_YEAR = 365.2425
_UNIT_TOLERANCE = 1e-8
FORECAST_YEARS = (1, 3, 5, 10, 20, 30)
MIN_FORECAST_YEARS = 1
MAX_FORECAST_YEARS = 50


@dataclass(frozen=True)
class TargetCashFlow:
    """One external amount used by the target calculation."""

    date: date
    amount: float
    source: str
    plan_id: str | None = None
    allocations: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True)
class TargetProjection:
    """Result and inputs of one target calculation."""

    annual_return: float
    monthly_return: float
    daily_factor: float
    start_date: date | None
    value: float | None
    cash_flows: tuple[TargetCashFlow, ...]
    unavailable_reason: str | None = None


def expected_annual_return(data: Mapping[str, Any]) -> float:
    """Return a validated configured percentage, with the legacy default."""
    try:
        value = float(
            data.get(
                c.CONF_EXPECTED_ANNUAL_RETURN,
                c.DEFAULT_EXPECTED_ANNUAL_RETURN,
            )
        )
    except (TypeError, ValueError):
        return c.DEFAULT_EXPECTED_ANNUAL_RETURN
    if (
        not isfinite(value)
        or value < c.MIN_EXPECTED_ANNUAL_RETURN
        or value > c.MAX_EXPECTED_ANNUAL_RETURN
    ):
        return c.DEFAULT_EXPECTED_ANNUAL_RETURN
    return value


def add_years(value: date, years: int) -> date:
    """Move a date by whole years, keeping leap-day forecasts valid."""
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)


def documented_wallet_start_date(
    data: Mapping[str, Any], *, through: date
) -> date | None:
    """Return the first documented wallet event, without guessing legacy data."""
    included: dict[str, float] = defaultdict(float)
    for lot in all_lots(data, through=through):
        if lot[c.LOT_INCLUDED_IN_OPENING]:
            included[lot[c.LOT_SYMBOL]] += float(lot[c.LOT_UNITS])

    if opening_balance_conflicts(data) or any(
        abs(included.get(valor[c.VALOR_SYMBOL], 0.0) - float(valor[c.VALOR_AMOUNT]))
        > _UNIT_TOLERANCE
        for valor in data.get(c.CONF_VALORS, [])
    ):
        return None

    contributions = contributions_from_data(data)
    if any(
        row[c.CONTRIBUTION_AMOUNT] > 0 and row[c.CONTRIBUTION_DATE] is None
        for row in contributions
    ):
        return None

    candidates = [
        date.fromisoformat(row[c.CONTRIBUTION_DATE])
        for row in contributions
        if row[c.CONTRIBUTION_DATE]
        and date.fromisoformat(row[c.CONTRIBUTION_DATE]) <= through
    ]
    candidates.extend(
        date.fromisoformat(lot[c.LOT_DATE]) for lot in all_lots(data, through=through)
    )
    return min(candidates, default=None)


def _monthly_date(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def _dates_for_rule(rule: Mapping[str, Any], through: date) -> list[date]:
    """Return dates for one historical plan definition."""
    if not rule.get(c.PLAN_ENABLED, True):
        return []
    first = date.fromisoformat(str(rule[c.PLAN_FIRST_DATE]))
    effective = date.fromisoformat(
        str(rule.get(c.PLAN_EFFECTIVE_FROM, rule[c.PLAN_FIRST_DATE]))
    )
    ends = [
        date.fromisoformat(str(value))
        for value in (rule.get(c.PLAN_END_DATE), rule.get(c.PLAN_VALID_UNTIL))
        if value
    ]
    end = min([through, *ends]) if ends else through
    if first > end or effective > end:
        return []

    result: list[date] = []
    year, month = first.year, first.month
    while True:
        candidate = _monthly_date(year, month, first.day)
        if candidate > end:
            break
        if candidate >= first and candidate >= effective:
            result.append(candidate)
        month += 1
        if month == 13:
            year += 1
            month = 1
    return result


def _plan_map(data: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    plans = [
        *data.get(c.CONF_RETIRED_SAVINGS_PLANS, []),
        *data.get(c.CONF_SAVINGS_PLANS, []),
    ]
    return {
        normalized[c.PLAN_ID]: normalized
        for item in plans
        for normalized in [normalize_plan(item)]
    }


def _planned_flows(
    data: Mapping[str, Any], *, through: date
) -> dict[tuple[str, str], TargetCashFlow]:
    """Build planned monthly funding, including due unbooked executions."""
    result: dict[tuple[str, str], TargetCashFlow] = {}
    active_plans = [normalize_plan(plan) for plan in data.get(c.CONF_SAVINGS_PLANS, [])]
    for plan in active_plans:
        skipped = set(plan[c.PLAN_SKIPPED_PERIODS])
        for rule in execution_rules(plan):
            allocations = tuple(sorted(allocation_amounts(rule).items()))
            for scheduled in _dates_for_rule(rule, through):
                period = schedule_period(scheduled)
                if period in skipped:
                    continue
                result[(plan[c.PLAN_ID], period)] = TargetCashFlow(
                    scheduled,
                    float(rule[c.PLAN_AMOUNT]),
                    "savings_plan",
                    plan[c.PLAN_ID],
                    allocations,
                )

    # Retired plans have no reliable retirement timestamp. Preserve only their
    # documented executions, and fill gaps for linked legacy rows of active plans.
    plans = _plan_map(data)
    for row in contributions_from_data(data):
        plan_id = row.get(c.CONTRIBUTION_PLAN_ID)
        scheduled_value = row.get(c.CONTRIBUTION_SCHEDULED_DATE)
        if not plan_id or not scheduled_value:
            continue
        scheduled = date.fromisoformat(str(scheduled_value))
        if scheduled > through:
            continue
        period = schedule_period(scheduled)
        key = (str(plan_id), period)
        plan = plans.get(str(plan_id))
        if period in set((plan or {}).get(c.PLAN_SKIPPED_PERIODS, [])):
            continue
        if key in result:
            continue
        amount = float(row[c.CONTRIBUTION_AMOUNT])
        allocations: tuple[tuple[str, float], ...] = ()
        if plan is not None:
            with suppress(ValueError):
                rule = rule_for_date(plan, scheduled)
                amount = float(rule[c.PLAN_AMOUNT])
                allocations = tuple(sorted(allocation_amounts(rule).items()))
        if amount > 0:
            result[key] = TargetCashFlow(
                scheduled, amount, "savings_plan", str(plan_id), allocations
            )
    return result


def target_cash_flows(
    data: Mapping[str, Any], *, through: date
) -> tuple[TargetCashFlow, ...]:
    """Return target funding without double-counting plan executions."""
    flows = list(_planned_flows(data, through=through).values())
    for row in contributions_from_data(data):
        amount = float(row[c.CONTRIBUTION_AMOUNT])
        value = row[c.CONTRIBUTION_DATE]
        if (
            amount <= 0
            or value is None
            or date.fromisoformat(value) > through
            or row.get(c.CONTRIBUTION_PLAN_ID)
            or row[c.CONTRIBUTION_SOURCE] == c.CONTRIBUTION_SOURCE_PURCHASE
        ):
            continue
        flows.append(
            TargetCashFlow(
                date.fromisoformat(value),
                amount,
                str(row[c.CONTRIBUTION_SOURCE]),
            )
        )
    return tuple(
        sorted(flows, key=lambda item: (item.date, item.source, item.plan_id or ""))
    )


def target_projection(data: Mapping[str, Any], *, through: date) -> TargetProjection:
    """Calculate the target value through one day."""
    annual = expected_annual_return(data)
    annual_factor = 1 + annual / 100
    monthly = (annual_factor ** (1 / 12) - 1) * 100
    daily_factor = annual_factor ** (1 / _DAYS_PER_YEAR)
    start = documented_wallet_start_date(data, through=through)
    flows = target_cash_flows(data, through=through)
    if start is None:
        return TargetProjection(
            annual, monthly, daily_factor, None, None, flows, "unknown_start"
        )
    relevant = tuple(flow for flow in flows if flow.date >= start)
    if not relevant:
        return TargetProjection(
            annual, monthly, daily_factor, start, None, relevant, "no_cash_flows"
        )

    value = 0.0
    previous = start
    grouped: dict[date, float] = defaultdict(float)
    for flow in relevant:
        grouped[flow.date] += flow.amount
    for flow_date in sorted(grouped):
        value *= daily_factor ** (flow_date - previous).days
        value += grouped[flow_date]
        previous = flow_date
    value *= daily_factor ** (through - previous).days
    return TargetProjection(annual, monthly, daily_factor, start, value, relevant)


def target_series(
    projection: TargetProjection, *, start: date, through: date
) -> dict[str, float]:
    """Return daily target points for the dashboard chart."""
    if projection.value is None or projection.start_date is None or start > through:
        return {}
    first = projection.start_date
    grouped: dict[date, float] = defaultdict(float)
    for flow in projection.cash_flows:
        grouped[flow.date] += flow.amount

    values: dict[str, float] = {}
    value = 0.0
    day = first - timedelta(days=1)
    while day <= through:
        if day >= start:
            values[day.isoformat()] = round(value, 2)
        day += timedelta(days=1)
        if day > through:
            break
        value *= projection.daily_factor
        value += grouped.get(day, 0.0)
    return values


def target_contribution_series(
    projection: TargetProjection, *, start: date, through: date
) -> dict[str, float]:
    """Return cumulative target funding for each dashboard day."""
    if projection.value is None or projection.start_date is None or start > through:
        return {}
    first = projection.start_date
    grouped: dict[date, float] = defaultdict(float)
    for flow in projection.cash_flows:
        grouped[flow.date] += flow.amount

    values: dict[str, float] = {}
    contributed = 0.0
    day = first - timedelta(days=1)
    while day <= through:
        if day >= start:
            values[day.isoformat()] = round(contributed, 2)
        day += timedelta(days=1)
        if day > through:
            break
        contributed += grouped.get(day, 0.0)
    return values


def target_snapshots(
    projection: TargetProjection, dates: Iterable[date]
) -> dict[str, dict[str, float]]:
    """Return exact target and contribution values for selected dates.

    Long forecasts use monthly samples and savings-plan dates in the dashboard.
    Evaluating those dates directly keeps the result exact without constructing
    decades of daily points.
    """
    if projection.value is None or projection.start_date is None:
        return {}

    requested = sorted(set(dates))
    if not requested:
        return {}

    start = projection.start_date
    flows = tuple(flow for flow in projection.cash_flows if flow.date >= start)
    flow_index = 0
    value = 0.0
    contributed = 0.0
    previous = start
    snapshots: dict[str, dict[str, float]] = {}

    for through in requested:
        if through < start:
            snapshots[through.isoformat()] = {"value": 0.0, "contributions": 0.0}
            continue
        while flow_index < len(flows) and flows[flow_index].date <= through:
            flow = flows[flow_index]
            value *= projection.daily_factor ** (flow.date - previous).days
            value += flow.amount
            contributed += flow.amount
            previous = flow.date
            flow_index += 1
        current = value * projection.daily_factor ** (through - previous).days
        snapshots[through.isoformat()] = {
            "value": round(current, 2),
            "contributions": round(contributed, 2),
        }
    return snapshots


def target_contributed_capital(
    projection: TargetProjection, *, through: date
) -> float | None:
    """Return the external capital included in a target through one day."""
    if projection.value is None or projection.start_date is None:
        return None
    return sum(
        flow.amount
        for flow in projection.cash_flows
        if projection.start_date <= flow.date <= through
    )


def target_allocation_forecast(
    projection: TargetProjection,
    *,
    current_date: date,
    through: date,
    positions: Mapping[str, float | None],
    cash: float | None,
) -> dict[str, Any] | None:
    """Project today's allocation using the same return and future plan flows."""
    values = list(positions.values())
    if (
        projection.value is None
        or through < current_date
        or cash is None
        or not isfinite(cash)
        or cash < 0
        or any(value is None or not isfinite(value) or value < 0 for value in values)
    ):
        return None

    horizon_factor = projection.daily_factor ** (through - current_date).days
    projected = {
        symbol: float(value) * horizon_factor
        for symbol, value in positions.items()
        if value is not None
    }
    projected_cash = cash * horizon_factor
    for flow in projection.cash_flows:
        if not current_date < flow.date <= through:
            continue
        flow_factor = projection.daily_factor ** (through - flow.date).days
        allocated = 0.0
        for symbol, amount in flow.allocations:
            projected[symbol] = projected.get(symbol, 0.0) + amount * flow_factor
            allocated += amount
        projected_cash += max(0.0, flow.amount - allocated) * flow_factor

    rounded_positions = {
        symbol: round(value, 2) for symbol, value in sorted(projected.items())
    }
    rounded_cash = round(projected_cash, 2)
    return {
        "date": through.isoformat(),
        "positions": rounded_positions,
        "cash": rounded_cash,
        "total": round(sum(projected.values()) + projected_cash, 2),
    }


def target_deviation(
    actual: float | None, target: float | None
) -> tuple[float | None, float | None]:
    """Return actual minus target in currency and percent of target."""
    if actual is None or target is None:
        return None, None
    absolute = actual - target
    percentage = absolute / target * 100 if target else None
    return absolute, percentage
