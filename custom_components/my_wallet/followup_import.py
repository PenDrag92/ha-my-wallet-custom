"""Reconcile a new statement with one existing wallet in a reviewable preview."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from hashlib import sha256
from typing import Any

from . import const as c
from .contributions import contributions_from_data, normalize_contributions
from .dividends import cash_balance, dividends_from_data
from .history import ledger_rows
from .history_import import (
    IMPORT_BATCH,
    MAX_IMPORT_ITEMS,
    _uid,
    async_prepare_import,
    validate_document,
)

IMPORT_RECORDS = "import_records"
IMPORT_LINKS = "import_links"


def _fingerprint(document: dict[str, Any]) -> str:
    content = {key: value for key, value in document.items() if key != "batch_id"}
    encoded = json.dumps(
        content,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return sha256(encoded).hexdigest()


def imported_batches(data) -> set[str]:
    batches = {row.get("batch_id") for row in data.get(IMPORT_RECORDS, [])}
    batches.add(data.get(IMPORT_BATCH))
    return {item for item in batches if item}


def has_import(data, batch: str | None, fingerprint: str | None = None) -> bool:
    if batch in imported_batches(data):
        return True
    return bool(
        fingerprint
        and any(
            row.get("fingerprint") == fingerprint
            for row in data.get(IMPORT_RECORDS, [])
        )
    )


def add_initial_import_metadata(document, data, *, today: date):
    """Add source links needed for later statement reconciliation."""
    result = deepcopy(data)
    links = {"plans": {}, "contributions": {}, "lots": {}, "dividends": {}}
    for raw, plan in zip(
        document.get("plans", []), result[c.CONF_SAVINGS_PLANS], strict=True
    ):
        links["plans"][raw["id"]] = plan[c.PLAN_ID]
    for raw, row in zip(
        document.get("deposits", []), result[c.CONF_CONTRIBUTIONS], strict=True
    ):
        links["contributions"][raw["id"]] = row[c.CONTRIBUTION_ID]
        for raw_lot, lot in zip(
            raw.get("purchases", []), row[c.CONTRIBUTION_LOTS], strict=True
        ):
            links["lots"][raw_lot["id"]] = lot[c.LOT_ID]
    for raw, item in zip(
        document.get("dividends", []), result[c.CONF_DIVIDENDS], strict=True
    ):
        links["dividends"][raw["id"]] = item[c.DIVIDEND_ID]
    result[IMPORT_LINKS] = links
    result[IMPORT_RECORDS] = [
        {
            "batch_id": result[IMPORT_BATCH],
            "fingerprint": _fingerprint(document),
            "date": today.isoformat(),
        }
    ]
    return result


def _plan_signature(plan):
    return (
        plan[c.PLAN_FIRST_DATE],
        plan.get(c.PLAN_END_DATE),
        plan[c.PLAN_ALLOCATION_MODE],
        round(float(plan[c.PLAN_AMOUNT]), 8),
        tuple(
            sorted(
                (row[c.ALLOCATION_SYMBOL], round(float(row[c.ALLOCATION_VALUE]), 8))
                for row in plan[c.PLAN_ALLOCATIONS]
            )
        ),
    )


def _contribution_signature(row):
    return (
        row[c.CONTRIBUTION_DATE],
        round(float(row[c.CONTRIBUTION_AMOUNT]), 8),
        tuple(
            sorted(
                (
                    lot[c.LOT_DATE],
                    lot[c.LOT_SYMBOL],
                    round(float(lot[c.LOT_AMOUNT]), 8),
                )
                for lot in row[c.CONTRIBUTION_LOTS]
            )
        ),
    )


def _protected(row) -> bool:
    return bool(row.get(c.CONTRIBUTION_MANUALLY_EDITED)) or any(
        not lot.get(c.LOT_ESTIMATED, True) for lot in row[c.CONTRIBUTION_LOTS]
    )


def _find_lot(existing, incoming, linked_id, batches, raw_id):
    direct = {
        linked_id,
        *(_uid(batch, raw_id) for batch in batches),
    } - {None}
    matches = [lot for lot in existing if lot[c.LOT_ID] in direct]
    if len(matches) == 1:
        return matches[0]
    exact = [
        lot
        for lot in existing
        if lot[c.LOT_SYMBOL] == incoming[c.LOT_SYMBOL]
        and lot[c.LOT_DATE] == incoming[c.LOT_DATE]
        and abs(lot[c.LOT_AMOUNT] - incoming[c.LOT_AMOUNT]) <= 0.005
    ]
    if len(exact) == 1:
        return exact[0]
    same_symbol = [
        lot for lot in existing if lot[c.LOT_SYMBOL] == incoming[c.LOT_SYMBOL]
    ]
    return same_symbol[0] if len(same_symbol) == 1 else None


def _merge_contribution(
    existing,
    incoming,
    raw,
    links,
    batches,
    *,
    overwrite_protected: bool,
):
    protected = _protected(existing)
    result = deepcopy(existing)
    if not protected or overwrite_protected:
        for key in (
            c.CONTRIBUTION_DATE,
            c.CONTRIBUTION_AMOUNT,
            c.CONTRIBUTION_PLAN_ID,
            c.CONTRIBUTION_PLAN_NAME,
            c.CONTRIBUTION_SCHEDULED_DATE,
            c.CONTRIBUTION_NOTE,
        ):
            if key in incoming:
                result[key] = incoming[key]
            else:
                result.pop(key, None)
    lots = list(result[c.CONTRIBUTION_LOTS])
    lot_links = links.setdefault("lots", {})
    for raw_lot, incoming_lot in zip(
        raw["purchases"], incoming[c.CONTRIBUTION_LOTS], strict=True
    ):
        raw_id = raw_lot["id"]
        current = _find_lot(lots, incoming_lot, lot_links.get(raw_id), batches, raw_id)
        if current is None:
            lots.append(incoming_lot)
            lot_links[raw_id] = incoming_lot[c.LOT_ID]
        else:
            lot_links[raw_id] = current[c.LOT_ID]
            if current.get(c.LOT_ESTIMATED, True) or overwrite_protected:
                replacement = {
                    **incoming_lot,
                    c.LOT_ID: current[c.LOT_ID],
                    c.LOT_INCLUDED_IN_OPENING: current[c.LOT_INCLUDED_IN_OPENING],
                }
                lots = [
                    replacement if lot[c.LOT_ID] == current[c.LOT_ID] else lot
                    for lot in lots
                ]
    result[c.CONTRIBUTION_LOTS] = lots
    result[c.CONTRIBUTION_SOURCE] = "import"
    if existing.get(c.CONTRIBUTION_MANUALLY_EDITED) or overwrite_protected:
        result[c.CONTRIBUTION_MANUALLY_EDITED] = True
    return result


def _minimum_cash(data) -> float:
    minimum = balance = 0.0
    for row in ledger_rows(data):
        balance += row["cash_delta"]
        minimum = min(minimum, balance)
    return minimum


async def async_prepare_followup(
    document,
    existing,
    *,
    session,
    today: date,
    decisions: dict[str, str] | None = None,
):
    """Return an immutable candidate or unresolved choices; never write data."""
    decisions = decisions or {}
    if len(decisions) > MAX_IMPORT_ITEMS or any(
        not isinstance(key, str)
        or len(key) > 100
        or not isinstance(value, str)
        or len(value) > 100
        for key, value in decisions.items()
    ):
        raise ValueError("invalid_import_decisions")
    fingerprint = _fingerprint(document)
    if has_import(existing, document.get("batch_id"), fingerprint):
        raise ValueError("already_imported")
    validated = validate_document(document, today=today)
    incoming, original_summary = await async_prepare_import(
        document, session=session, today=today
    )
    if incoming is None:
        return None, {**original_summary, "mode": "followup"}
    if incoming[c.CONF_BASE_CURRENCY] != existing[c.CONF_BASE_CURRENCY]:
        raise ValueError("import_currency_mismatch")

    candidate = deepcopy(dict(existing))
    batches = imported_batches(existing)
    links = deepcopy(
        existing.get(
            IMPORT_LINKS,
            {"plans": {}, "contributions": {}, "lots": {}, "dividends": {}},
        )
    )
    for group in ("plans", "contributions", "lots", "dividends"):
        links.setdefault(group, {})
    summary = {
        **original_summary,
        "mode": "followup",
        "added": {
            "deposits": 0,
            "purchases": 0,
            "dividends": 0,
            "assets": 0,
            "plans": 0,
        },
        "updated": 0,
        "unchanged": 0,
        "protected": [],
        "choices": [],
    }

    valors = list(candidate[c.CONF_VALORS])
    symbols = {row[c.VALOR_SYMBOL] for row in valors}
    for valor in incoming[c.CONF_VALORS]:
        if valor[c.VALOR_SYMBOL] not in symbols:
            valors.append({c.VALOR_SYMBOL: valor[c.VALOR_SYMBOL], c.VALOR_AMOUNT: 0.0})
            symbols.add(valor[c.VALOR_SYMBOL])
            summary["added"]["assets"] += 1
    candidate[c.CONF_VALORS] = valors

    plans = [
        *candidate.get(c.CONF_SAVINGS_PLANS, []),
        *candidate.get(c.CONF_RETIRED_SAVINGS_PLANS, []),
    ]
    plan_map = {}
    for raw, plan in zip(
        document.get("plans", []), incoming[c.CONF_SAVINGS_PLANS], strict=True
    ):
        raw_id = raw["id"]
        candidates = [
            row for row in plans if row[c.PLAN_ID] == links["plans"].get(raw_id)
        ]
        candidates += [
            row
            for row in plans
            if row[c.PLAN_ID] in {_uid(batch, raw_id) for batch in batches}
        ]
        candidates = list({row[c.PLAN_ID]: row for row in candidates}.values())
        if not candidates:
            candidates = [
                row for row in plans if _plan_signature(row) == _plan_signature(plan)
            ]
        if len(candidates) == 1:
            selected = candidates[0]
        elif len(candidates) > 1:
            raise ValueError("ambiguous_import_plan")
        else:
            selected = plan
            candidate[c.CONF_SAVINGS_PLANS] = [
                *candidate.get(c.CONF_SAVINGS_PLANS, []),
                selected,
            ]
            plans.append(selected)
            summary["added"]["plans"] += 1
        plan_map[plan[c.PLAN_ID]] = selected[c.PLAN_ID]
        links["plans"][raw_id] = selected[c.PLAN_ID]

    incoming_rows = incoming[c.CONF_CONTRIBUTIONS]
    current_rows = contributions_from_data(candidate)
    raw_rows = validated["deposits"]
    unresolved = False
    for raw, row in zip(raw_rows, incoming_rows, strict=True):
        raw_id = raw["id"]
        if row.get(c.CONTRIBUTION_PLAN_ID) in plan_map:
            row[c.CONTRIBUTION_PLAN_ID] = plan_map[row[c.CONTRIBUTION_PLAN_ID]]
            matching_plan = next(
                (
                    plan
                    for plan in plans
                    if plan[c.PLAN_ID] == row[c.CONTRIBUTION_PLAN_ID]
                ),
                None,
            )
            if matching_plan:
                row[c.CONTRIBUTION_PLAN_NAME] = matching_plan[c.PLAN_NAME]
        direct_ids = {
            links["contributions"].get(raw_id),
            *(_uid(batch, raw_id) for batch in batches),
        } - {None}
        matches = [
            item for item in current_rows if item[c.CONTRIBUTION_ID] in direct_ids
        ]
        if (
            not matches
            and row.get(c.CONTRIBUTION_PLAN_ID)
            and row.get(c.CONTRIBUTION_SCHEDULED_DATE)
        ):
            matches = [
                item
                for item in current_rows
                if item.get(c.CONTRIBUTION_PLAN_ID) == row[c.CONTRIBUTION_PLAN_ID]
                and item.get(c.CONTRIBUTION_SCHEDULED_DATE, "")[:7]
                == row[c.CONTRIBUTION_SCHEDULED_DATE][:7]
            ]
        authoritative = bool(matches)
        if not matches:
            matches = [
                item
                for item in current_rows
                if _contribution_signature(item) == _contribution_signature(row)
            ]
        if len(matches) > 1:
            choice = decisions.get(raw_id)
            options = [
                {
                    "id": item[c.CONTRIBUTION_ID],
                    "date": item[c.CONTRIBUTION_DATE],
                    "amount": item[c.CONTRIBUTION_AMOUNT],
                }
                for item in matches
            ]
            matches = [item for item in matches if item[c.CONTRIBUTION_ID] == choice]
            if len(matches) != 1 and choice != "add":
                unresolved = True
                summary["choices"].append(
                    {"id": raw_id, "kind": "ambiguous", "options": options}
                )
                continue
        if not matches or (decisions.get(raw_id) == "add" and not authoritative):
            current_rows.append(row)
            links["contributions"][raw_id] = row[c.CONTRIBUTION_ID]
            for raw_lot, lot in zip(
                raw["purchases"], row[c.CONTRIBUTION_LOTS], strict=True
            ):
                links["lots"][raw_lot["id"]] = lot[c.LOT_ID]
            summary["added"]["deposits"] += 1
            summary["added"]["purchases"] += len(row[c.CONTRIBUTION_LOTS])
            continue
        current = matches[0]
        links["contributions"][raw_id] = current[c.CONTRIBUTION_ID]
        same = _contribution_signature(current) == _contribution_signature(row)
        if _protected(current) and authoritative and not same:
            choice = decisions.get(raw_id)
            if choice not in {"keep", "merge"}:
                unresolved = True
                summary["choices"].append(
                    {
                        "id": raw_id,
                        "kind": "protected",
                        "options": ["keep", "merge"],
                        "existing": _contribution_signature(current),
                        "incoming": _contribution_signature(row),
                    }
                )
                continue
            if choice == "keep":
                summary["protected"].append(raw_id)
                summary["unchanged"] += 1
                continue
        merged = _merge_contribution(
            current,
            row,
            raw,
            links,
            batches,
            overwrite_protected=decisions.get(raw_id) == "merge",
        )
        current_rows = [
            merged if item[c.CONTRIBUTION_ID] == current[c.CONTRIBUTION_ID] else item
            for item in current_rows
        ]
        summary["updated" if merged != current else "unchanged"] += 1
    candidate[c.CONF_CONTRIBUTIONS] = normalize_contributions(current_rows)

    dividends = dividends_from_data(candidate)
    for raw, row in zip(
        document.get("dividends", []), incoming[c.CONF_DIVIDENDS], strict=True
    ):
        raw_id = raw["id"]
        ids = {
            links["dividends"].get(raw_id),
            *(_uid(batch, raw_id) for batch in batches),
        } - {None}
        matches = [item for item in dividends if item[c.DIVIDEND_ID] in ids]

        def signature(item):
            return (
                item.get(c.DIVIDEND_VALUE_DATE) or item[c.DIVIDEND_BOOKING_DATE],
                round(item[c.DIVIDEND_AMOUNT], 8),
                item.get(c.DIVIDEND_SYMBOL, ""),
            )

        if not matches:
            matches = [item for item in dividends if signature(item) == signature(row)]
        if matches:
            links["dividends"][raw_id] = matches[0][c.DIVIDEND_ID]
            summary["unchanged"] += 1
        else:
            dividends.append(row)
            links["dividends"][raw_id] = row[c.DIVIDEND_ID]
            summary["added"]["dividends"] += 1
    candidate[c.CONF_DIVIDENDS] = dividends
    represented = {
        (
            row.get(c.CONTRIBUTION_PLAN_ID),
            row.get(c.CONTRIBUTION_SCHEDULED_DATE, "")[:7],
        )
        for row in candidate[c.CONF_CONTRIBUTIONS]
        if row.get(c.CONTRIBUTION_PLAN_ID) and row.get(c.CONTRIBUTION_SCHEDULED_DATE)
    }
    candidate[c.CONF_SAVINGS_PLANS] = [
        {
            **plan,
            c.PLAN_SKIPPED_PERIODS: [
                period
                for period in plan.get(c.PLAN_SKIPPED_PERIODS, [])
                if (plan[c.PLAN_ID], period) not in represented
            ],
        }
        for plan in candidate.get(c.CONF_SAVINGS_PLANS, [])
    ]
    candidate[IMPORT_LINKS] = links
    candidate[IMPORT_RECORDS] = [
        *existing.get(IMPORT_RECORDS, []),
        {
            "batch_id": validated[IMPORT_BATCH],
            "fingerprint": fingerprint,
            "date": today.isoformat(),
        },
    ]
    if _minimum_cash(candidate) < min(-0.005, _minimum_cash(existing) - 0.005):
        raise ValueError("import_cash_conflict")
    summary["cash_change"] = round(cash_balance(candidate) - cash_balance(existing), 2)
    return (None if unresolved else candidate), summary
