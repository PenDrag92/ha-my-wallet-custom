"""Deterministic, read-only scenarios starting at the actual wallet value."""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import replace
from datetime import date
from math import isfinite

from . import const as c
from .target import TargetCashFlow, add_years, expected_annual_return, target_cash_flows
from .wallet_snapshot import valuation_unavailable_reason, wallet_with_saved_units

_DAYS_PER_YEAR = 365.2425
_MAX_AMOUNT = 10_000_000_000


def _number(value, code, low, high):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as err:
        raise ValueError(code) from err
    if isinstance(value, bool) or not isfinite(number) or not low <= number <= high:
        raise ValueError(code)
    return number


def _day(value, code):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as err:
        raise ValueError(code) from err


def _monthly_dates(start, through):
    """Preserve the requested day after short months, including leap years."""
    month = start.year * 12 + start.month - 1
    while True:
        year, offset = divmod(month, 12)
        day = date(
            year, offset + 1, min(start.day, calendar.monthrange(year, offset + 1)[1])
        )
        if day > through:
            return
        yield day
        month += 1


def _projection(initial, flows, *, today, through, annual, samples):
    factor = (1 + annual / 100) ** (1 / _DAYS_PER_YEAR)
    grouped = defaultdict(float)
    for flow in flows:
        grouped[flow.date] += flow.amount
    value, capital, previous = initial, 0.0, today
    points = []
    for day in sorted({today, through, *samples, *grouped}):
        value *= factor ** (day - previous).days
        capital += grouped.get(day, 0.0)
        value += grouped.get(day, 0.0)
        points.append(
            {
                "date": day.isoformat(),
                "value": round(value, 2),
                "contributions": round(capital, 2),
            }
        )
        previous = day
    result = {
        "annual_return": annual,
        "initial_value": round(initial, 2),
        "future_contributions": round(capital, 2),
        "final_value": round(value, 2),
        "growth": round(value - initial - capital, 2),
        "points": points,
    }
    return result, value, capital


def build_wallet_scenario(
    data,
    current,
    *,
    today,
    years=10,
    annual_return=None,
    monthly_extra=0,
    one_off=0,
    start_date=None,
    plan_id=None,
    monthly_amount=None,
    pause_until=None,
    available=True,
):
    """Compare configured funding with explicit future-only overrides.

    A rate override or pause applies to the selected plan's existing execution
    dates. A pause without a plan selection applies to all future plan funding.
    Additional monthly funding is independent, including during a plan pause.
    """
    years_value = _number(years, "invalid_scenario_years", 1, 50)
    if not years_value.is_integer():
        raise ValueError("invalid_scenario_years")
    through = add_years(today, int(years_value))
    baseline_rate = expected_annual_return(data)
    rate = (
        baseline_rate
        if annual_return is None
        else _number(
            annual_return,
            "invalid_scenario_return",
            c.MIN_EXPECTED_ANNUAL_RETURN,
            c.MAX_EXPECTED_ANNUAL_RETURN,
        )
    )
    extra = _number(monthly_extra, "invalid_scenario_amount", 0, _MAX_AMOUNT)
    lump = _number(one_off, "invalid_scenario_amount", 0, _MAX_AMOUNT)
    start = today if start_date is None else _day(start_date, "invalid_scenario_date")
    if not today <= start <= through:
        raise ValueError("invalid_scenario_date")
    plans = {p[c.PLAN_ID] for p in data.get(c.CONF_SAVINGS_PLANS, [])}
    if plan_id is not None and (not isinstance(plan_id, str) or plan_id not in plans):
        raise ValueError("invalid_scenario_plan")
    amount = None
    if monthly_amount is not None:
        if plan_id is None:
            raise ValueError("scenario_plan_required")
        amount = _number(monthly_amount, "invalid_scenario_amount", 0, _MAX_AMOUNT)
    pause = None if pause_until is None else _day(pause_until, "invalid_scenario_date")
    if pause is not None and not start <= pause <= through:
        raise ValueError("invalid_scenario_date")
    current = wallet_with_saved_units(data, current, today=today)
    reason = valuation_unavailable_reason(current, available=available)
    if reason is None and current.cash_balance < -1e-7:
        reason = "cash_deficit"
    result = {
        "schema_version": 1,
        "status": "unavailable" if reason else "ok",
        "reason": reason,
        "as_of": today.isoformat(),
        "through": through.isoformat(),
        "sampled_at": current.sampled_at if current is not None else None,
        "currency": data[c.CONF_BASE_CURRENCY],
        "method": "actual_value_with_dated_external_funding",
        "inputs": {
            "years": int(years_value),
            "annual_return": rate,
            "monthly_extra": extra,
            "one_off": lump,
            "start_date": start.isoformat(),
            "plan_id": plan_id,
            "monthly_amount": amount,
            "pause_until": pause.isoformat() if pause else None,
        },
        "baseline": None,
        "scenario": None,
        "difference": None,
        "assumptions": [
            "Starts with today's actual securities value and settlement cash.",
            (
                "Uses configured future plan dates, historical plan definitions, "
                "skips and future deposits."
            ),
            (
                "A constant annual return compounds daily on the whole balance, "
                "including cash."
            ),
            (
                "No separate taxes, fees, inflation or additional dividend yield "
                "are modelled."
            ),
            (
                "Additional monthly funding starts on start_date and repeats on "
                "that calendar day, clipped in short months."
            ),
            (
                "Rate overrides and pauses affect future plan payments only; no "
                "saved booking or plan changes."
            ),
            (
                "This is a calculation under assumptions, not a forecast of market "
                "returns."
            ),
        ],
    }
    if reason:
        return result
    baseline = [
        f for f in target_cash_flows(data, through=through) if today < f.date <= through
    ]
    changed = []
    affected = 0
    for flow in baseline:
        selected = (
            flow.plan_id is not None
            and (plan_id is None or flow.plan_id == plan_id)
            and flow.date >= start
        )
        if selected and pause is not None and flow.date <= pause:
            affected += 1
            continue
        if selected and amount is not None:
            affected += 1
            flow = replace(flow, amount=amount)
        changed.append(flow)
    if lump:
        changed.append(TargetCashFlow(start, lump, "scenario_one_off"))
    if extra:
        changed.extend(
            TargetCashFlow(day, extra, "scenario_monthly")
            for day in _monthly_dates(start, through)
        )
    samples = set(_monthly_dates(today, through))
    samples.update(f.date for f in [*baseline, *changed])
    before, before_value, before_capital = _projection(
        current.total,
        baseline,
        today=today,
        through=through,
        annual=baseline_rate,
        samples=samples,
    )
    after, after_value, after_capital = _projection(
        current.total,
        changed,
        today=today,
        through=through,
        annual=rate,
        samples=samples,
    )
    result.update(
        {
            "baseline": before,
            "scenario": after,
            "difference": {
                "final_value": round(after_value - before_value, 2),
                "future_contributions": round(after_capital - before_capital, 2),
                "growth": round(
                    after_value - before_value - after_capital + before_capital, 2
                ),
            },
            "affected_plan_payments": affected,
        }
    )
    return result
