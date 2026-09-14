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
from .history_import import (
    IMPORT_BATCH,
    MAX_IMPORT_ITEMS,
    _uid,
    async_prepare_import,
    validate_document,
)
from .ledger import prepare_change, worsened_cash_history

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


def _source_pairs(raw_rows, prepared_rows, batch: str):
    """Join source records to prepared IDs independently of normalization order."""
    sources = {_uid(batch, row["id"]): row for row in raw_rows}
    prepared = {row["id"]: row for row in prepared_rows}
    if (
        len(sources) != len(raw_rows)
        or len(prepared) != len(prepared_rows)
        or sources.keys() != prepared.keys()
    ):
        raise ValueError("invalid_import_format")
    return [(raw, prepared[identifier]) for identifier, raw in sources.items()]


def add_initial_import_metadata(document, data, *, today: date):
    """Add source links needed for later statement reconciliation."""
    result = deepcopy(data)
    batch = result[IMPORT_BATCH]
    links = {"plans": {}, "contributions": {}, "lots": {}, "dividends": {}}
    for raw, plan in _source_pairs(
        document.get("plans", []), result[c.CONF_SAVINGS_PLANS], batch
    ):
        links["plans"][raw["id"]] = plan[c.PLAN_ID]
    for raw, row in _source_pairs(
        document.get("deposits", []), result[c.CONF_CONTRIBUTIONS], batch
    ):
        links["contributions"][raw["id"]] = row[c.CONTRIBUTION_ID]
        for raw_lot, lot in _source_pairs(
            raw.get("purchases", []), row[c.CONTRIBUTION_LOTS], batch
        ):
            links["lots"][raw_lot["id"]] = lot[c.LOT_ID]
    for raw, item in _source_pairs(
        document.get("dividends", []), result[c.CONF_DIVIDENDS], batch
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


def _lot_content(lot):
    return (
        lot[c.LOT_DATE],
        lot[c.LOT_SYMBOL],
        round(lot[c.LOT_AMOUNT], 8),
        round(lot[c.LOT_UNITS], 12),
    )


def _contribution_content(row):
    """Compare quantities as well as the fields used to locate a booking."""
    return (
        _contribution_signature(row),
        tuple(sorted(_lot_content(lot) for lot in row[c.CONTRIBUTION_LOTS])),
    )


def _lot_matches(existing, incoming, linked_id, batches, raw_id):
    direct = {
        linked_id,
        *(_uid(batch, raw_id) for batch in batches),
    } - {None}
    matches = [lot for lot in existing if lot[c.LOT_ID] in direct]
    if matches:
        return matches
    return [
        lot
        for lot in existing
        if lot[c.LOT_SYMBOL] == incoming[c.LOT_SYMBOL]
        and lot[c.LOT_DATE] == incoming[c.LOT_DATE]
        and abs(lot[c.LOT_AMOUNT] - incoming[c.LOT_AMOUNT]) <= 0.005
    ]


def _reserved_sources(links, raw_rows, batches):
    """Protect known identities even when their source row arrives later."""
    return {
        target for source, target in links.items() if not source.startswith("document:")
    } | {_uid(batch, raw["id"]) for raw in raw_rows for batch in batches}


def _available_matches(matches, *, used, reserved, direct):
    """A source may consume one original record, never another incoming row."""
    if any(row["id"] in direct and row["id"] in used for row in matches):
        raise ValueError("invalid_import_duplicate_match")
    return [
        row
        for row in matches
        if row["id"] not in used and (row["id"] not in reserved or row["id"] in direct)
    ]


def _dividend_content(row):
    return (
        row[c.DIVIDEND_BOOKING_DATE],
        row.get(c.DIVIDEND_VALUE_DATE),
        round(row[c.DIVIDEND_AMOUNT], 8),
        row.get(c.DIVIDEND_SYMBOL, ""),
    )


def _reconcile_document_lots(
    candidate, raw_rows, incoming_rows, *, batch, links, decisions, summary
):
    """Review purchases already stored independently by a document adapter.

    Their funding group stays in place. A JSON statement can reference an
    existing trade without moving it or adding the same units a second time.
    """
    document_ids = {
        target
        for source, target in links["lots"].items()
        if source.startswith("document:")
    }
    document_lots = [
        lot
        for row in contributions_from_data(candidate)
        if row[c.CONTRIBUTION_SOURCE] == c.CONTRIBUTION_SOURCE_PURCHASE
        for lot in row[c.CONTRIBUTION_LOTS]
        if lot[c.LOT_ID] in document_ids
    ]
    used, unresolved = set(), False
    for raw, incoming in _source_pairs(raw_rows, incoming_rows, batch):
        retained_raw, retained_lots = [], []
        for source, lot in _source_pairs(
            raw["purchases"], incoming[c.CONTRIBUTION_LOTS], batch
        ):
            linked = links["lots"].get(source["id"])
            stable = [
                existing for existing in document_lots if existing[c.LOT_ID] == linked
            ]
            matches = stable or [
                existing
                for existing in document_lots
                if _lot_content(existing) == _lot_content(lot)
            ]
            choice = decisions.get(source["id"])
            if not matches or (not stable and choice == "add"):
                retained_raw.append(source)
                retained_lots.append(lot)
                continue
            if not stable:
                selected = [
                    existing for existing in matches if existing[c.LOT_ID] == choice
                ]
                if len(selected) != 1:
                    summary["choices"].append(
                        {
                            "id": source["id"],
                            "kind": "ambiguous",
                            "options": [
                                {
                                    "id": existing[c.LOT_ID],
                                    "date": existing[c.LOT_DATE],
                                    "amount": existing[c.LOT_AMOUNT],
                                }
                                for existing in matches
                            ],
                        }
                    )
                    unresolved = True
                    retained_raw.append(source)
                    retained_lots.append(lot)
                    continue
                matches = selected
            current = matches[0]
            if current[c.LOT_ID] in used:
                raise ValueError("invalid_import_duplicate_match")
            used.add(current[c.LOT_ID])
            if _lot_content(current) != _lot_content(lot):
                if choice not in {"keep", "merge"}:
                    summary["choices"].append(
                        {
                            "id": source["id"],
                            "kind": "protected",
                            "options": ["keep", "merge"],
                            "existing": _lot_content(current),
                            "incoming": _lot_content(lot),
                        }
                    )
                    unresolved = True
                    retained_raw.append(source)
                    retained_lots.append(lot)
                    continue
                if choice == "merge":
                    replacement = {
                        **lot,
                        c.LOT_ID: current[c.LOT_ID],
                        c.LOT_INCLUDED_IN_OPENING: current[c.LOT_INCLUDED_IN_OPENING],
                    }
                    for row in candidate[c.CONF_CONTRIBUTIONS]:
                        if any(
                            item[c.LOT_ID] == current[c.LOT_ID]
                            for item in row[c.CONTRIBUTION_LOTS]
                        ):
                            row[c.CONTRIBUTION_LOTS] = [
                                replacement
                                if item[c.LOT_ID] == current[c.LOT_ID]
                                else item
                                for item in row[c.CONTRIBUTION_LOTS]
                            ]
                            row[c.CONTRIBUTION_MANUALLY_EDITED] = True
                            if (
                                row[c.CONTRIBUTION_SOURCE]
                                == c.CONTRIBUTION_SOURCE_PURCHASE
                            ):
                                row[c.CONTRIBUTION_DATE] = min(
                                    item[c.LOT_DATE]
                                    for item in row[c.CONTRIBUTION_LOTS]
                                )
                    summary["updated"] += 1
            links["lots"][source["id"]] = current[c.LOT_ID]
        raw["purchases"] = retained_raw
        incoming[c.CONTRIBUTION_LOTS] = retained_lots
    return unresolved


def _merge_contribution(
    existing,
    incoming,
    raw,
    links,
    batches,
    *,
    incoming_batch: str,
    overwrite_protected: bool,
    decisions,
    choices,
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
    # Match only pre-existing lots. New purchases in this file must never match
    # each other, nor consume a lot reserved by another purchase's stable ID.
    original_lots = list(lots)
    reserved = set(lot_links.values()) | {
        lot_id
        for raw_lot in raw["purchases"]
        for lot_id in (
            lot_links.get(raw_lot["id"]),
            *(_uid(batch, raw_lot["id"]) for batch in batches),
        )
        if lot_id is not None
    }
    used = set()
    unresolved = False
    for raw_lot, incoming_lot in _source_pairs(
        raw["purchases"], incoming[c.CONTRIBUTION_LOTS], incoming_batch
    ):
        raw_id = raw_lot["id"]
        matches = _lot_matches(
            original_lots, incoming_lot, lot_links.get(raw_id), batches, raw_id
        )
        direct = {
            lot_links.get(raw_id),
            *(_uid(batch, raw_id) for batch in batches),
        } - {None}
        if any(lot[c.LOT_ID] in direct and lot[c.LOT_ID] in used for lot in matches):
            raise ValueError("invalid_import_duplicate_match")
        matches = [
            lot
            for lot in matches
            if lot[c.LOT_ID] not in used
            and (lot[c.LOT_ID] not in reserved or lot[c.LOT_ID] in direct)
        ]
        if len(matches) > 1:
            choice = decisions.get(raw_id)
            selected = [lot for lot in matches if lot[c.LOT_ID] == choice]
            if choice != "add" and len(selected) != 1:
                choices.append(
                    {
                        "id": raw_id,
                        "kind": "ambiguous",
                        "options": [
                            {
                                "id": lot[c.LOT_ID],
                                "date": lot[c.LOT_DATE],
                                "amount": lot[c.LOT_AMOUNT],
                            }
                            for lot in matches
                        ],
                    }
                )
                unresolved = True
                continue
            matches = selected
        current = matches[0] if matches else None
        if current is None:
            lots.append(incoming_lot)
            lot_links[raw_id] = incoming_lot[c.LOT_ID]
        else:
            if (
                protected
                and not overwrite_protected
                and _lot_content(current) != _lot_content(incoming_lot)
            ):
                choices.append(
                    {
                        "id": raw["id"],
                        "kind": "protected",
                        "options": ["keep", "merge"],
                        "existing": _contribution_content(existing),
                        "incoming": _contribution_content(incoming),
                    }
                )
                return None
            used.add(current[c.LOT_ID])
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
    return None if unresolved else result


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
        document, session=session, today=today, check_cash=False
    )
    if incoming is None:
        return None, {**original_summary, "mode": "followup"}
    if incoming[c.CONF_BASE_CURRENCY] != existing[c.CONF_BASE_CURRENCY]:
        raise ValueError("import_currency_mismatch")

    candidate = deepcopy(dict(existing))
    incoming_batch = incoming[IMPORT_BATCH]
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
    unresolved_document_lots = _reconcile_document_lots(
        candidate,
        validated["deposits"],
        incoming[c.CONF_CONTRIBUTIONS],
        batch=incoming_batch,
        links=links,
        decisions=decisions,
        summary=summary,
    )

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
    for raw, plan in _source_pairs(
        document.get("plans", []), incoming[c.CONF_SAVINGS_PLANS], incoming_batch
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
    original_rows = list(current_rows)
    raw_rows = validated["deposits"]
    reserved_rows = _reserved_sources(links["contributions"], raw_rows, batches)
    used_rows = set()
    document_contributions = {
        target
        for source, target in links["contributions"].items()
        if source.startswith("document:")
    }
    unresolved = unresolved_document_lots
    for raw, row in _source_pairs(raw_rows, incoming_rows, incoming_batch):
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
            item for item in original_rows if item[c.CONTRIBUTION_ID] in direct_ids
        ]
        if (
            not matches
            and row.get(c.CONTRIBUTION_PLAN_ID)
            and row.get(c.CONTRIBUTION_SCHEDULED_DATE)
        ):
            matches = [
                item
                for item in original_rows
                if item.get(c.CONTRIBUTION_PLAN_ID) == row[c.CONTRIBUTION_PLAN_ID]
                and item.get(c.CONTRIBUTION_SCHEDULED_DATE, "")[:7]
                == row[c.CONTRIBUTION_SCHEDULED_DATE][:7]
            ]
        authoritative = bool(matches)
        if authoritative:
            direct_ids.update(item[c.CONTRIBUTION_ID] for item in matches)
        if not matches:
            matches = [
                item
                for item in original_rows
                if _contribution_signature(item) == _contribution_signature(row)
            ]
        matches = _available_matches(
            matches, used=used_rows, reserved=reserved_rows, direct=direct_ids
        )
        if len(matches) > 1 or (
            not authoritative
            and any(
                item[c.CONTRIBUTION_ID] in document_contributions for item in matches
            )
        ):
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
            for raw_lot, lot in _source_pairs(
                raw["purchases"], row[c.CONTRIBUTION_LOTS], incoming_batch
            ):
                links["lots"][raw_lot["id"]] = lot[c.LOT_ID]
            summary["added"]["deposits"] += 1
            summary["added"]["purchases"] += len(row[c.CONTRIBUTION_LOTS])
            continue
        current = matches[0]
        used_rows.add(current[c.CONTRIBUTION_ID])
        links["contributions"][raw_id] = current[c.CONTRIBUTION_ID]
        same = _contribution_content(current) == _contribution_content(row)
        if _protected(current) and not same:
            choice = decisions.get(raw_id)
            if choice not in {"keep", "merge"}:
                unresolved = True
                summary["choices"].append(
                    {
                        "id": raw_id,
                        "kind": "protected",
                        "options": ["keep", "merge"],
                        "existing": _contribution_content(current),
                        "incoming": _contribution_content(row),
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
            incoming_batch=incoming_batch,
            overwrite_protected=decisions.get(raw_id) == "merge",
            decisions=decisions,
            choices=summary["choices"],
        )
        if merged is None:
            unresolved = True
            continue
        summary["added"]["purchases"] += len(merged[c.CONTRIBUTION_LOTS]) - len(
            current[c.CONTRIBUTION_LOTS]
        )
        current_rows = [
            merged if item[c.CONTRIBUTION_ID] == current[c.CONTRIBUTION_ID] else item
            for item in current_rows
        ]
        summary["updated" if merged != current else "unchanged"] += 1
    candidate[c.CONF_CONTRIBUTIONS] = normalize_contributions(current_rows)

    dividends = dividends_from_data(candidate)
    original_dividends = list(dividends)
    reserved_dividends = _reserved_sources(
        links["dividends"], document.get("dividends", []), batches
    )
    used_dividends = set()
    document_dividends = {
        target
        for source, target in links["dividends"].items()
        if source.startswith("document:")
    }
    for raw, row in _source_pairs(
        document.get("dividends", []), incoming[c.CONF_DIVIDENDS], incoming_batch
    ):
        raw_id = raw["id"]
        ids = {
            links["dividends"].get(raw_id),
            *(_uid(batch, raw_id) for batch in batches),
        } - {None}
        matches = [item for item in original_dividends if item[c.DIVIDEND_ID] in ids]

        def signature(item):
            return (
                item.get(c.DIVIDEND_VALUE_DATE) or item[c.DIVIDEND_BOOKING_DATE],
                round(item[c.DIVIDEND_AMOUNT], 8),
                item.get(c.DIVIDEND_SYMBOL, ""),
            )

        if not matches:
            matches = [
                item for item in original_dividends if signature(item) == signature(row)
            ]
        matches = _available_matches(
            matches, used=used_dividends, reserved=reserved_dividends, direct=ids
        )
        if len(matches) > 1 or (
            not any(item[c.DIVIDEND_ID] in ids for item in matches)
            and any(item[c.DIVIDEND_ID] in document_dividends for item in matches)
        ):
            selected = [
                item for item in matches if item[c.DIVIDEND_ID] == decisions.get(raw_id)
            ]
            if len(selected) != 1 and decisions.get(raw_id) != "add":
                unresolved = True
                summary["choices"].append(
                    {
                        "id": raw_id,
                        "kind": "ambiguous",
                        "options": [
                            {
                                "id": item[c.DIVIDEND_ID],
                                "date": item[c.DIVIDEND_BOOKING_DATE],
                                "amount": item[c.DIVIDEND_AMOUNT],
                            }
                            for item in matches
                        ],
                    }
                )
                continue
            matches = selected
        if matches:
            current = matches[0]
            used_dividends.add(current[c.DIVIDEND_ID])
            links["dividends"][raw_id] = current[c.DIVIDEND_ID]
            if _dividend_content(current) != _dividend_content(row):
                if decisions.get(raw_id) not in {"keep", "merge"}:
                    unresolved = True
                    summary["choices"].append(
                        {
                            "id": raw_id,
                            "kind": "protected",
                            "options": ["keep", "merge"],
                            "existing": _dividend_content(current),
                            "incoming": _dividend_content(row),
                        }
                    )
                    continue
                if decisions[raw_id] == "merge":
                    replacement = {**row, c.DIVIDEND_ID: current[c.DIVIDEND_ID]}
                    dividends = [
                        replacement
                        if item[c.DIVIDEND_ID] == current[c.DIVIDEND_ID]
                        else item
                        for item in dividends
                    ]
                    summary["updated"] += 1
                    continue
                summary["protected"].append(raw_id)
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
    if worsened_cash_history(existing, candidate, today):
        raise ValueError("import_cash_conflict")
    if not unresolved:
        candidate = prepare_change(existing, candidate, today=today)
    summary["cash_change"] = round(cash_balance(candidate) - cash_balance(existing), 2)
    return (None if unresolved else candidate), summary
