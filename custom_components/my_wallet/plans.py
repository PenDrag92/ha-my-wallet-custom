"""Pure helpers for recurring monthly savings plans."""

from __future__ import annotations

import calendar
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal
from math import isfinite
from typing import Any
from uuid import uuid4

from .const import (
    ALLOCATION_MODE_FIXED,
    ALLOCATION_MODE_PERCENTAGE,
    ALLOCATION_SYMBOL,
    ALLOCATION_VALUE,
    CONTRIBUTION_PLAN_ID,
    CONTRIBUTION_SCHEDULED_DATE,
    PLAN_ALLOCATION_MODE,
    PLAN_ALLOCATIONS,
    PLAN_AMOUNT,
    PLAN_ENABLED,
    PLAN_END_DATE,
    PLAN_FIRST_DATE,
    PLAN_ID,
    PLAN_NAME,
    PLAN_OPENING_CUTOFF_DATE,
    PLAN_SKIPPED_PERIODS,
    PLAN_USE_CASH_BALANCE,
)
from .contributions import normalize_date

_PERCENT_TOLERANCE = 0.005


def make_plan(
    *,
    name: str,
    first_date: Any,
    allocation_mode: str,
    allocations: Sequence[Mapping[str, Any]],
    amount: Any | None = None,
    enabled: bool = True,
    end_date: Any | None = None,
    plan_id: str | None = None,
    use_cash_balance: bool = True,
    opening_cutoff_date: Any | None = None,
    skipped_periods: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Create and validate one monthly savings plan."""
    normalized_enabled = bool(enabled)
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("Savings-plan name is required")
    if allocation_mode not in (ALLOCATION_MODE_PERCENTAGE, ALLOCATION_MODE_FIXED):
        raise ValueError("Unknown allocation mode")

    normalized_allocations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for allocation in allocations:
        symbol = str(allocation[ALLOCATION_SYMBOL]).strip().upper()
        value = float(allocation[ALLOCATION_VALUE])
        if not symbol or not isfinite(value) or value <= 0:
            raise ValueError("Allocation symbol and value are required")
        if symbol in seen:
            raise ValueError(f"Duplicate allocation for {symbol}")
        seen.add(symbol)
        normalized_allocations.append(
            {ALLOCATION_SYMBOL: symbol, ALLOCATION_VALUE: value}
        )
    if not normalized_allocations:
        raise ValueError("At least one allocation is required")

    normalized_first = normalize_date(first_date)
    normalized_end = normalize_date(end_date, allow_none=True)
    normalized_cutoff = normalize_date(opening_cutoff_date, allow_none=True)
    if normalized_end is not None and normalized_end < normalized_first:
        raise ValueError("End date must not be before first execution")

    if allocation_mode == ALLOCATION_MODE_PERCENTAGE:
        normalized_amount = float(amount or 0)
        if not isfinite(normalized_amount) or normalized_amount <= 0:
            raise ValueError("Plan amount must be greater than zero")
        total_percent = sum(item[ALLOCATION_VALUE] for item in normalized_allocations)
        if abs(total_percent - 100) > _PERCENT_TOLERANCE:
            raise ValueError("Percentage allocations must total 100")
        if normalized_enabled and normalized_amount + 1e-9 < 0.01 * len(
            normalized_allocations
        ):
            raise ValueError("Plan amount is too small for all allocations")
    else:
        normalized_amount = sum(
            item[ALLOCATION_VALUE] for item in normalized_allocations
        )
        if not isfinite(normalized_amount):
            raise ValueError("Plan amount must be finite")

    normalized_skips = sorted(
        {schedule_period(item) for item in (skipped_periods or [])}
    )

    return {
        PLAN_ID: plan_id or uuid4().hex,
        PLAN_NAME: normalized_name,
        PLAN_ENABLED: normalized_enabled,
        PLAN_FIRST_DATE: normalized_first,
        PLAN_END_DATE: normalized_end,
        PLAN_ALLOCATION_MODE: allocation_mode,
        PLAN_AMOUNT: normalized_amount,
        PLAN_ALLOCATIONS: normalized_allocations,
        PLAN_USE_CASH_BALANCE: bool(use_cash_balance),
        PLAN_OPENING_CUTOFF_DATE: normalized_cutoff,
        PLAN_SKIPPED_PERIODS: normalized_skips,
    }


def normalize_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a serialized savings plan."""
    return make_plan(
        name=str(plan[PLAN_NAME]),
        first_date=plan[PLAN_FIRST_DATE],
        end_date=plan.get(PLAN_END_DATE),
        allocation_mode=str(plan[PLAN_ALLOCATION_MODE]),
        amount=plan.get(PLAN_AMOUNT),
        allocations=plan.get(PLAN_ALLOCATIONS, []),
        enabled=bool(plan.get(PLAN_ENABLED, True)),
        plan_id=str(plan.get(PLAN_ID) or uuid4().hex),
        use_cash_balance=bool(plan.get(PLAN_USE_CASH_BALANCE, True)),
        opening_cutoff_date=plan.get(PLAN_OPENING_CUTOFF_DATE),
        skipped_periods=plan.get(PLAN_SKIPPED_PERIODS, []),
    )


def same_plan_definition(
    first_plan: Mapping[str, Any], second_plan: Mapping[str, Any]
) -> bool:
    """Return whether two plans share one schedule and allocation identity.

    Enabled state is deliberately not identity: removing a paused plan and
    re-creating it as active must still retain its historical execution ID.
    """
    ignored = {PLAN_ENABLED, PLAN_ID, PLAN_SKIPPED_PERIODS}
    first = normalize_plan(first_plan)
    second = normalize_plan(second_plan)
    return {key: value for key, value in first.items() if key not in ignored} == {
        key: value for key, value in second.items() if key not in ignored
    }


def reactivate_matching_plan(
    plan: Mapping[str, Any], retired_plans: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Restore a retired plan's identity when its definition is re-created.

    Plan IDs are part of the monthly execution identity.  Reusing the old ID
    therefore keeps already booked and deliberately skipped months booked.
    """
    normalized = normalize_plan(plan)
    retired = [normalize_plan(item) for item in retired_plans]
    for index in range(len(retired) - 1, -1, -1):
        previous = retired[index]
        if not same_plan_definition(normalized, previous):
            continue
        restored = normalize_plan(
            {
                **normalized,
                PLAN_ID: previous[PLAN_ID],
                PLAN_SKIPPED_PERIODS: previous[PLAN_SKIPPED_PERIODS],
            }
        )
        return restored, retired[:index] + retired[index + 1 :]
    return normalized, retired


def allocation_amounts(
    plan: Mapping[str, Any], *, available_amount: float | None = None
) -> dict[str, float]:
    """Return the base-currency amount assigned to every symbol.

    The configured plan amount is fully allocated first. Extra settlement cash
    is then spread pro rata and truncated to cents, leaving the broker-style
    rounding remainder on the cash account.
    """
    normalized = normalize_plan(plan)
    plan_total_float = float(normalized[PLAN_AMOUNT])
    available_float = (
        plan_total_float if available_amount is None else float(available_amount)
    )
    if not isfinite(available_float) or available_float <= 0:
        raise ValueError("Available amount must be finite and greater than zero")
    if available_float + 1e-9 < plan_total_float:
        raise ValueError("Available amount must cover the configured plan amount")
    plan_total = Decimal(str(plan_total_float))
    available = (
        plan_total if available_amount is None else Decimal(str(available_float))
    )

    result: dict[str, Decimal] = {}
    allocations = normalized[PLAN_ALLOCATIONS]
    if normalized[PLAN_ALLOCATION_MODE] == ALLOCATION_MODE_FIXED:
        result.update(
            {
                item[ALLOCATION_SYMBOL]: Decimal(str(item[ALLOCATION_VALUE]))
                for item in allocations
            }
        )
    else:
        raw = [
            plan_total * Decimal(str(item[ALLOCATION_VALUE])) / Decimal(100)
            for item in allocations
        ]
        rounded = [
            value.quantize(Decimal("0.01"), rounding=ROUND_DOWN) for value in raw
        ]
        cents = int(((plan_total - sum(rounded)) / Decimal("0.01")).to_integral_value())
        order = sorted(
            range(len(allocations)),
            key=lambda index: (raw[index] - rounded[index], -index),
            reverse=True,
        )
        for index in order[:cents]:
            rounded[index] += Decimal("0.01")
        for index, value in enumerate(rounded):
            if value > 0:
                continue
            donors = [
                donor
                for donor, donor_value in enumerate(rounded)
                if donor_value > Decimal("0.01")
            ]
            if not donors:
                raise ValueError("Plan amount is too small for all allocations")
            donor = max(donors, key=lambda item: rounded[item] - raw[item])
            rounded[donor] -= Decimal("0.01")
            rounded[index] += Decimal("0.01")
        if any(value <= 0 for value in rounded):
            raise ValueError("Plan amount is too small for all allocations")
        result.update(
            {
                item[ALLOCATION_SYMBOL]: rounded[index]
                for index, item in enumerate(allocations)
            }
        )

    extra = max(Decimal(0), available - plan_total)
    if extra:
        weight_total = sum(Decimal(str(item[ALLOCATION_VALUE])) for item in allocations)
        for item in allocations:
            bonus = (
                extra * Decimal(str(item[ALLOCATION_VALUE])) / weight_total
            ).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
            result[item[ALLOCATION_SYMBOL]] += bonus
    return {symbol: float(value) for symbol, value in result.items()}


def _monthly_date(year: int, month: int, day: int) -> date:
    """Use the last day for plans scheduled on day 29, 30, or 31."""
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def schedule_period(value: date | str) -> str:
    """Return the canonical month identity for a monthly execution."""
    if isinstance(value, date):
        return value.strftime("%Y-%m")
    text = str(value)
    if len(text) == 7:
        parsed = date.fromisoformat(f"{text}-01")
    else:
        parsed = date.fromisoformat(text)
    return parsed.strftime("%Y-%m")


def is_scheduled_period(plan: Mapping[str, Any], period: date | str) -> bool:
    """Return whether a month belongs to a plan's configured date range.

    Unlike :func:`scheduled_dates`, this deliberately ignores whether the plan
    is enabled.  A skipped execution marker may still be managed while a plan
    is temporarily disabled.
    """
    normalized = normalize_plan(plan)
    first = date.fromisoformat(normalized[PLAN_FIRST_DATE])
    normalized_period = schedule_period(period)
    year, month = (int(part) for part in normalized_period.split("-", 1))
    candidate = _monthly_date(year, month, first.day)
    if candidate < first:
        return False
    end_value = normalized[PLAN_END_DATE]
    return end_value is None or candidate <= date.fromisoformat(end_value)


def scheduled_dates(plan: Mapping[str, Any], through: date) -> list[date]:
    """Return every monthly schedule date up to and including ``through``."""
    normalized = normalize_plan(plan)
    if not normalized[PLAN_ENABLED]:
        return []
    first = date.fromisoformat(normalized[PLAN_FIRST_DATE])
    end = (
        date.fromisoformat(normalized[PLAN_END_DATE])
        if normalized[PLAN_END_DATE]
        else through
    )
    end = min(end, through)
    if first > end:
        return []

    dates = [first]
    year, month = first.year, first.month
    while True:
        month += 1
        if month == 13:
            year += 1
            month = 1
        candidate = _monthly_date(year, month, first.day)
        if candidate > end:
            break
        dates.append(candidate)
    return dates


def booked_schedule_periods(
    contributions: Sequence[Mapping[str, Any]], plan_id: str
) -> set[str]:
    """Return schedule months already booked for a plan."""
    return {
        schedule_period(str(item[CONTRIBUTION_SCHEDULED_DATE]))
        for item in contributions
        if item.get(CONTRIBUTION_PLAN_ID) == plan_id
        and item.get(CONTRIBUTION_SCHEDULED_DATE)
    }


def due_dates(
    plan: Mapping[str, Any],
    contributions: Sequence[Mapping[str, Any]],
    through: date,
) -> list[date]:
    """Return unbooked schedule dates through the supplied date."""
    normalized = normalize_plan(plan)
    booked = booked_schedule_periods(contributions, normalized[PLAN_ID])
    skipped = set(normalized[PLAN_SKIPPED_PERIODS])
    return [
        item
        for item in scheduled_dates(normalized, through)
        if schedule_period(item) not in booked | skipped
    ]


def next_scheduled_date(plan: Mapping[str, Any], on_or_after: date) -> date | None:
    """Return the next calendar execution date for a plan."""
    normalized = normalize_plan(plan)
    if not normalized[PLAN_ENABLED]:
        return None
    first = date.fromisoformat(normalized[PLAN_FIRST_DATE])
    end = (
        date.fromisoformat(normalized[PLAN_END_DATE])
        if normalized[PLAN_END_DATE]
        else None
    )
    if on_or_after <= first:
        candidate = first
    else:
        months = (on_or_after.year - first.year) * 12 + on_or_after.month - first.month
        year = first.year + (first.month - 1 + months) // 12
        month = (first.month - 1 + months) % 12 + 1
        candidate = _monthly_date(year, month, first.day)
        if candidate < on_or_after:
            month += 1
            if month == 13:
                year += 1
                month = 1
            candidate = _monthly_date(year, month, first.day)
    if end is not None and candidate > end:
        return None
    return candidate


def next_due_date(
    plan: Mapping[str, Any],
    contributions: Sequence[Mapping[str, Any]],
    on_or_after: date,
) -> date | None:
    """Return the next monthly occurrence that is neither booked nor skipped."""
    normalized = normalize_plan(plan)
    booked = booked_schedule_periods(contributions, normalized[PLAN_ID])
    skipped = set(normalized[PLAN_SKIPPED_PERIODS])
    candidate = next_scheduled_date(normalized, on_or_after)
    while candidate is not None and schedule_period(candidate) in booked | skipped:
        candidate = next_scheduled_date(normalized, candidate + timedelta(days=1))
    return candidate
