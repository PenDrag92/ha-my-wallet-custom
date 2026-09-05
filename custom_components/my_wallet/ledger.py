"""Wallet transactions independent of Home Assistant and presentation code.

The stored contribution/lot format is retained. Every writer validates a complete
candidate against its previous snapshot, including intermediate cash balances.
Existing historical deficits and opening discrepancies may be repaired gradually.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import date
from enum import Enum
from math import isfinite
from typing import Any

from . import const as c
from .accounting import ACCOUNTING_REVISIONS, mark_accounting_changes
from .contributions import (
    all_lots,
    attach_lot,
    contributions_from_data,
    make_contribution,
    make_lot,
    normalize_contributions,
    opening_balance_conflicts,
)
from .dividends import cash_timeline, make_dividend, normalize_dividends
from .planning import is_plannable_deposit
from .plans import execution_rules, normalize_plan, schedule_period


class CashPolicy(Enum):
    """Historical purchase entry has a separate, explicitly confirmed workflow."""

    PRESERVE = "preserve"
    CONFIRMED_PURCHASE = "confirmed_purchase"


def worsened_cash_history(before, after, today: date) -> bool:
    """Reject a new or increased deficit at any past cash-effective event date."""
    old_timeline, new_timeline = cash_timeline(before), cash_timeline(after)
    previous = proposed = 0.0
    for day in sorted(old_timeline.keys() | new_timeline.keys()):
        if day > today:
            break
        previous = old_timeline.get(day, previous)
        proposed = new_timeline.get(day, proposed)
        if proposed < min(0.0, previous) - 1e-7:
            return True
    return False


def _unique(rows, key):
    values = [row[key] for row in rows]
    if any(not isinstance(value, str) or not value for value in values) or len(
        values
    ) != len(set(values)):
        raise ValueError("invalid_input")


def _reference_errors(data):
    symbols = {row[c.VALOR_SYMBOL] for row in data.get(c.CONF_VALORS, [])}
    plans = [
        *data.get(c.CONF_SAVINGS_PLANS, []),
        *data.get(c.CONF_RETIRED_SAVINGS_PLANS, []),
    ]
    plan_ids = {plan[c.PLAN_ID] for plan in plans}
    errors = set()
    for row in contributions_from_data(data):
        if row.get(c.CONTRIBUTION_PLAN_ID) not in (None, *plan_ids):
            errors.add(("plan", row[c.CONTRIBUTION_ID], row[c.CONTRIBUTION_PLAN_ID]))
        for lot in row[c.CONTRIBUTION_LOTS]:
            if lot[c.LOT_SYMBOL] not in symbols:
                errors.add(("lot", lot[c.LOT_ID], lot[c.LOT_SYMBOL]))
    for item in data.get(c.CONF_DIVIDENDS, []):
        if item.get(c.DIVIDEND_SYMBOL) not in (None, *symbols):
            errors.add(("dividend", item[c.DIVIDEND_ID], item[c.DIVIDEND_SYMBOL]))
    for plan in plans:
        for rule in execution_rules(plan):
            for allocation in rule[c.PLAN_ALLOCATIONS]:
                if allocation[c.ALLOCATION_SYMBOL] not in symbols:
                    errors.add(
                        ("allocation", plan[c.PLAN_ID], allocation[c.ALLOCATION_SYMBOL])
                    )
    return errors


def _future_errors(data, today):
    errors = set()
    for row in contributions_from_data(data):
        if (
            row[c.CONTRIBUTION_DATE] or ""
        ) > today.isoformat() and not is_plannable_deposit(row):
            errors.add(("deposit", row[c.CONTRIBUTION_ID], row[c.CONTRIBUTION_DATE]))
        for lot in row[c.CONTRIBUTION_LOTS]:
            if lot[c.LOT_DATE] > today.isoformat():
                errors.add(("lot", lot[c.LOT_ID], lot[c.LOT_DATE]))
    for item in data.get(c.CONF_DIVIDENDS, []):
        for key in (c.DIVIDEND_BOOKING_DATE, c.DIVIDEND_VALUE_DATE):
            if (item.get(key) or "") > today.isoformat():
                errors.add((key, item[c.DIVIDEND_ID], item[key]))
    return errors


def _only_added_purchases(before, after):
    """The cash exception cannot authorize edits, deletions or lost funding."""
    old = contributions_from_data(before)
    new = contributions_from_data(after)
    old_lots = {lot[c.LOT_ID]: lot for lot in all_lots(before)}
    new_lots = {lot[c.LOT_ID]: lot for lot in all_lots(after)}
    if not new_lots.keys() > old_lots.keys() or any(
        new_lots.get(key) != lot for key, lot in old_lots.items()
    ):
        return False
    for row in old:
        match = next(
            (item for item in new if item[c.CONTRIBUTION_ID] == row[c.CONTRIBUTION_ID]),
            None,
        )
        if match is None:
            return False
        if not {lot[c.LOT_ID] for lot in row[c.CONTRIBUTION_LOTS]} <= {
            lot[c.LOT_ID] for lot in match[c.CONTRIBUTION_LOTS]
        }:
            return False
        # attach_lot flags its parent as corrected, but may not change its funding.
        ignored = {c.CONTRIBUTION_LOTS, c.CONTRIBUTION_MANUALLY_EDITED}
        if {k: v for k, v in row.items() if k not in ignored} != {
            k: v for k, v in match.items() if k not in ignored
        }:
            return False
    old_ids = {row[c.CONTRIBUTION_ID] for row in old}
    if any(
        row[c.CONTRIBUTION_SOURCE] != c.CONTRIBUTION_SOURCE_PURCHASE
        for row in new
        if row[c.CONTRIBUTION_ID] not in old_ids
    ):
        return False
    return all(
        before.get(key) == after.get(key)
        for key in (
            c.CONF_VALORS,
            c.CONF_DIVIDENDS,
            c.CONF_SAVINGS_PLANS,
            c.CONF_RETIRED_SAVINGS_PLANS,
        )
    )


def validate_records(
    candidate: Mapping[str, Any],
    *,
    today: date,
    before: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate stored records, references and dates, also for backup restore.

    A restore preserves an existing account's funding/opening discrepancies.
    Edits additionally use validate_change to ensure those do not get worse.
    """
    before = before or {}
    result = deepcopy(dict(candidate))
    numeric_values = [
        row.get(c.CONTRIBUTION_AMOUNT) for row in result.get(c.CONF_CONTRIBUTIONS, [])
    ]
    numeric_values.extend(
        row.get(c.DIVIDEND_AMOUNT) for row in result.get(c.CONF_DIVIDENDS, [])
    )
    numeric_values.extend(
        lot.get(key)
        for row in result.get(c.CONF_CONTRIBUTIONS, [])
        for lot in row.get(c.CONTRIBUTION_LOTS, [])
        for key in (c.LOT_AMOUNT, c.LOT_UNITS, c.LOT_UNIT_PRICE, c.LOT_FX_RATE)
    )
    if any(isinstance(value, bool) for value in numeric_values):
        raise ValueError("invalid_number")
    if c.CONF_CONTRIBUTIONS in result:
        result[c.CONF_CONTRIBUTIONS] = normalize_contributions(
            result[c.CONF_CONTRIBUTIONS]
        )
        result.pop(c.CONF_INVESTED_AMOUNT, None)
    if c.CONF_DIVIDENDS in result:
        result[c.CONF_DIVIDENDS] = normalize_dividends(result[c.CONF_DIVIDENDS])
    for key in (c.CONF_SAVINGS_PLANS, c.CONF_RETIRED_SAVINGS_PLANS):
        if key in result:
            result[key] = [normalize_plan(plan) for plan in result[key]]
    valors = result.get(c.CONF_VALORS, [])
    for valor in valors:
        amount = float(valor[c.VALOR_AMOUNT])
        if (
            isinstance(valor[c.VALOR_AMOUNT], bool)
            or not isfinite(amount)
            or amount < 0
        ):
            raise ValueError("invalid_number")
        share = valor.get(c.VALOR_TARGET_SHARE)
        if share is not None and (
            isinstance(share, bool)
            or not isfinite(float(share))
            or not 0 <= float(share) <= 100
        ):
            raise ValueError("invalid_target_share")
    if (
        sum(float(valor.get(c.VALOR_TARGET_SHARE) or 0) for valor in valors)
        > 100 + c.TARGET_SHARE_SUM_TOLERANCE
    ):
        raise ValueError("invalid_target_share")
    for rows, key in (
        (valors, c.VALOR_SYMBOL),
        (contributions_from_data(result), c.CONTRIBUTION_ID),
        (all_lots(result), c.LOT_ID),
        (result.get(c.CONF_DIVIDENDS, []), c.DIVIDEND_ID),
        (
            [
                *result.get(c.CONF_SAVINGS_PLANS, []),
                *result.get(c.CONF_RETIRED_SAVINGS_PLANS, []),
            ],
            c.PLAN_ID,
        ),
    ):
        _unique(rows, key)
    if _reference_errors(result) - _reference_errors(before):
        raise ValueError("invalid_symbol")
    if _future_errors(result, today) - _future_errors(before, today):
        raise ValueError("future_date")
    return result


def validate_change(
    before: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    today: date,
    cash_policy: CashPolicy = CashPolicy.PRESERVE,
) -> dict[str, Any]:
    """Detach and validate a candidate without modifying either input."""
    if not isinstance(cash_policy, CashPolicy):
        raise ValueError("invalid_input")
    result = validate_records(candidate, today=today, before=before)
    previous = {
        row["symbol"]: row["included_units"] - row["configured_units"]
        for row in opening_balance_conflicts(before)
    }
    if any(
        row["included_units"] - row["configured_units"]
        > previous.get(row["symbol"], 0) + 1e-9
        for row in opening_balance_conflicts(result)
    ):
        raise ValueError("included_units_exceeded")
    if cash_policy is CashPolicy.CONFIRMED_PURCHASE and not _only_added_purchases(
        before, result
    ):
        raise ValueError("invalid_input")
    if cash_policy is CashPolicy.PRESERVE and worsened_cash_history(
        before, result, today
    ):
        raise ValueError("cash_conflict")
    return result


def prepare_change(before, candidate, *, today, cash_policy=CashPolicy.PRESERVE):
    """Apply the same accounting revision rules to every transaction source."""
    result = validate_change(before, candidate, today=today, cash_policy=cash_policy)
    # Revisions belong to the transaction, never to arbitrary submitted metadata.
    result.pop(ACCOUNTING_REVISIONS, None)
    if ACCOUNTING_REVISIONS in before:
        result[ACCOUNTING_REVISIONS] = deepcopy(before[ACCOUNTING_REVISIONS])
    mark_accounting_changes(before, result)
    return result


def put_dividend(data, fields, *, today, dividend_id=None):
    rows = list(data.get(c.CONF_DIVIDENDS, []))
    if dividend_id is not None and not any(
        row[c.DIVIDEND_ID] == dividend_id for row in rows
    ):
        raise ValueError("stale_selection")
    item = make_dividend(**fields, dividend_id=dividend_id)
    updated = [row for row in rows if row[c.DIVIDEND_ID] != item[c.DIVIDEND_ID]]
    return prepare_change(
        data, {**data, c.CONF_DIVIDENDS: [*updated, item]}, today=today
    )


def delete_dividend(data, dividend_id, *, today):
    rows = list(data.get(c.CONF_DIVIDENDS, []))
    if not any(row[c.DIVIDEND_ID] == dividend_id for row in rows):
        raise ValueError("stale_selection")
    return prepare_change(
        data,
        {
            **data,
            c.CONF_DIVIDENDS: [
                row for row in rows if row[c.DIVIDEND_ID] != dividend_id
            ],
        },
        today=today,
    )


def edit_contribution(data, contribution_id, *, amount, execution_date, note, today):
    rows = contributions_from_data(data)
    current = next(
        (row for row in rows if row[c.CONTRIBUTION_ID] == contribution_id), None
    )
    if current is None or current[c.CONTRIBUTION_AMOUNT] == 0:
        raise ValueError("stale_selection")
    replacement = {
        **current,
        c.CONTRIBUTION_AMOUNT: amount,
        c.CONTRIBUTION_DATE: execution_date,
        c.CONTRIBUTION_MANUALLY_EDITED: True,
    }
    replacement.pop(c.CONTRIBUTION_NOTE, None)
    if note:
        replacement[c.CONTRIBUTION_NOTE] = note
    return prepare_change(
        data,
        {
            **data,
            c.CONF_CONTRIBUTIONS: [
                replacement if row is current else row for row in rows
            ],
        },
        today=today,
    )


def delete_contribution(data, contribution_id, *, today):
    rows = contributions_from_data(data)
    current = next(
        (row for row in rows if row[c.CONTRIBUTION_ID] == contribution_id), None
    )
    if current is None:
        raise ValueError("stale_selection")
    candidate = {
        **data,
        c.CONF_CONTRIBUTIONS: [row for row in rows if row is not current],
    }
    if current.get(c.CONTRIBUTION_PLAN_ID) and current.get(
        c.CONTRIBUTION_SCHEDULED_DATE
    ):
        period = schedule_period(current[c.CONTRIBUTION_SCHEDULED_DATE])
        for key in (c.CONF_SAVINGS_PLANS, c.CONF_RETIRED_SAVINGS_PLANS):
            if key in data:
                candidate[key] = [
                    {
                        **plan,
                        c.PLAN_SKIPPED_PERIODS: sorted(
                            set([*plan.get(c.PLAN_SKIPPED_PERIODS, []), period])
                        ),
                    }
                    if plan[c.PLAN_ID] == current[c.CONTRIBUTION_PLAN_ID]
                    else plan
                    for plan in data[key]
                ]
    return prepare_change(data, candidate, today=today)


def edit_lot(
    data, lot_id, *, amount, units, execution_date, included_in_opening, today
):
    rows = contributions_from_data(data)
    matches = [
        (row, lot)
        for row in rows
        for lot in row[c.CONTRIBUTION_LOTS]
        if lot[c.LOT_ID] == lot_id
    ]
    if len(matches) != 1:
        raise ValueError("stale_selection")
    row, current = matches[0]
    replacement = make_lot(
        symbol=current[c.LOT_SYMBOL],
        execution_date=execution_date,
        amount=amount,
        unit_price=amount / (units * current[c.LOT_FX_RATE]),
        units=units,
        quote_currency=current[c.LOT_QUOTE_CURRENCY],
        fx_rate=current[c.LOT_FX_RATE],
        included_in_opening=included_in_opening,
        estimated=False,
        lot_id=lot_id,
    )
    if (
        row[c.CONTRIBUTION_SOURCE] == c.CONTRIBUTION_SOURCE_LEGACY
        and not included_in_opening
    ):
        raise ValueError("legacy_opening_required")
    if (
        row[c.CONTRIBUTION_SOURCE] != c.CONTRIBUTION_SOURCE_PURCHASE
        and (row[c.CONTRIBUTION_DATE] or "") > replacement[c.LOT_DATE]
    ):
        raise ValueError("contribution_date_after_lot")
    row[c.CONTRIBUTION_LOTS] = [
        replacement if lot[c.LOT_ID] == lot_id else lot
        for lot in row[c.CONTRIBUTION_LOTS]
    ]
    row[c.CONTRIBUTION_MANUALLY_EDITED] = True
    if row[c.CONTRIBUTION_SOURCE] == c.CONTRIBUTION_SOURCE_PURCHASE:
        row[c.CONTRIBUTION_DATE] = min(
            lot[c.LOT_DATE] for lot in row[c.CONTRIBUTION_LOTS]
        )
    return prepare_change(data, {**data, c.CONF_CONTRIBUTIONS: rows}, today=today)


def book_purchase(
    data, lot, *, today, funding_id=None, cash_policy=CashPolicy.PRESERVE
):
    rows = contributions_from_data(data)
    if funding_id:
        rows = attach_lot(rows, funding_id, lot)
    else:
        rows.append(
            make_contribution(
                0, lot[c.LOT_DATE], source=c.CONTRIBUTION_SOURCE_PURCHASE, lots=[lot]
            )
        )
    return prepare_change(
        data, {**data, c.CONF_CONTRIBUTIONS: rows}, today=today, cash_policy=cash_policy
    )
