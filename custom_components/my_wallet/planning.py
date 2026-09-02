"""Future one-off deposits using the existing dated cash ledger."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date
from math import isfinite
from typing import Any

from . import const as c
from .contributions import (
    contributions_from_data,
    make_contribution,
    normalize_contributions,
)
from .plans import execution_rules, next_due_date, normalize_plan


def is_plannable_deposit(row: Mapping[str, Any]) -> bool:
    """Only a standalone external deposit may be moved into the future."""
    return (
        row.get(c.CONTRIBUTION_SOURCE) == c.CONTRIBUTION_SOURCE_MANUAL
        and float(row.get(c.CONTRIBUTION_AMOUNT, 0)) > 0
        and not row.get(c.CONTRIBUTION_LOTS)
        and not row.get(c.CONTRIBUTION_PLAN_ID)
        and not row.get(c.CONTRIBUTION_SCHEDULED_DATE)
    )


def planned_contributions(
    data: Mapping[str, Any], *, today: date
) -> list[dict[str, Any]]:
    """Read pending deposits without including them in today's cash or capital."""
    return [
        row
        for row in contributions_from_data(data)
        if is_plannable_deposit(row)
        and row[c.CONTRIBUTION_DATE]
        and row[c.CONTRIBUTION_DATE] > today.isoformat()
    ]


def next_cash_investment(
    data: Mapping[str, Any], *, on_or_after: date
) -> dict[str, str] | None:
    """Find the first enabled cash-reinvesting plan, respecting pauses and skips."""
    candidates = []
    contributions = contributions_from_data(data)
    for raw in data.get(c.CONF_SAVINGS_PLANS, []):
        plan = normalize_plan(raw)
        if not plan[c.PLAN_ENABLED]:
            continue
        for rule in execution_rules(plan):
            if not rule[c.PLAN_USE_CASH_BALANCE]:
                continue
            day = next_due_date(rule, contributions, on_or_after)
            if day is None or (
                rule.get(c.PLAN_VALID_UNTIL)
                and day.isoformat() > rule[c.PLAN_VALID_UNTIL]
            ):
                continue
            candidates.append(
                {
                    "date": day.isoformat(),
                    "plan_id": plan[c.PLAN_ID],
                    "plan_name": rule[c.PLAN_NAME],
                }
            )
    return (
        min(candidates, key=lambda item: (item["date"], item["plan_id"]))
        if candidates
        else None
    )


def planned_deposit_summaries(
    data: Mapping[str, Any], *, today: date
) -> list[dict[str, Any]]:
    """Expose future deposits with the currently expected cash-plan execution."""
    return [
        {
            "id": row[c.CONTRIBUTION_ID],
            "date": row[c.CONTRIBUTION_DATE],
            "amount": row[c.CONTRIBUTION_AMOUNT],
            "note": row.get(c.CONTRIBUTION_NOTE, ""),
            "investment": next_cash_investment(
                data, on_or_after=date.fromisoformat(row[c.CONTRIBUTION_DATE])
            ),
        }
        for row in planned_contributions(data, today=today)
    ]


def change_planned_deposit(
    data: Mapping[str, Any],
    *,
    today: date,
    deposit_id: Any,
    action: str,
    amount: Any = None,
    deposit_date: Any = None,
    note: Any = "",
) -> dict[str, Any]:
    """Save or cancel future deposits with safe retries and immutable past rows."""
    if not isinstance(deposit_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_.:-]{1,100}", deposit_id
    ):
        raise ValueError("invalid_planned_deposit")
    rows = contributions_from_data(data)
    current = next((row for row in rows if row[c.CONTRIBUTION_ID] == deposit_id), None)
    if current is not None and (
        not is_plannable_deposit(current)
        or not current[c.CONTRIBUTION_DATE]
        or current[c.CONTRIBUTION_DATE] <= today.isoformat()
    ):
        raise ValueError("planned_deposit_locked")
    if action == "delete":
        if current is None:
            return dict(data)
        updated = [row for row in rows if row[c.CONTRIBUTION_ID] != deposit_id]
    elif action == "save":
        try:
            day = date.fromisoformat(str(deposit_date))
            value = float(amount)
        except (TypeError, ValueError) as err:
            raise ValueError("invalid_planned_deposit") from err
        if day <= today:
            raise ValueError("planned_date_required")
        if (
            isinstance(amount, bool)
            or not isfinite(value)
            or not 0.01 <= value <= 10_000_000_000
        ):
            raise ValueError("invalid_planned_deposit")
        if not isinstance(note, str) or len(note) > 500:
            raise ValueError("invalid_planned_deposit")
        replacement = make_contribution(
            value, day, contribution_id=deposit_id, note=note
        )
        if current is not None:
            replacement = {**current, **replacement}
            if not note.strip():
                replacement.pop(c.CONTRIBUTION_NOTE, None)
        updated = [row for row in rows if row[c.CONTRIBUTION_ID] != deposit_id]
        updated.append(replacement)
    else:
        raise ValueError("invalid_planned_deposit")
    return {**data, c.CONF_CONTRIBUTIONS: normalize_contributions(updated)}
