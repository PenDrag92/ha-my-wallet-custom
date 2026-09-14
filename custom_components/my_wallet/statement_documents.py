"""Statement adapters and reviewed events, independent of Home Assistant.

Documents describe external deposits, purchases and dividends separately. They
never imply funding, estimate units or change an existing confirmed booking.
"""

from __future__ import annotations

import csv
import io
import json
import re
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from . import const as c
from .contributions import (
    all_lots,
    contributions_from_data,
    make_contribution,
    make_lot,
)
from .dividends import cash_balance, dividends_from_data, make_dividend
from .followup_import import IMPORT_LINKS, IMPORT_RECORDS
from .history_import import MAX_IMPORT_ITEMS
from .ledger import prepare_change

MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_DOCUMENT_ROWS = 500
MAX_PDF_PAGES = 20
MAX_PDF_TEXT = 80000
FIELDS = ("type", "date", "amount", "currency", "symbol", "units", "value_date", "note")
CSV_REQUIRED = {"type", "id", "date", "amount", "currency", "symbol", "units"}


def _digest(value):
    return sha256(value).hexdigest()


def _text(value, maximum=500):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError("invalid_document_text")
    return value.strip()


def _filename(value):
    name = _text(value, 200)
    if not name or any(ord(character) < 32 for character in name):
        raise ValueError("invalid_document_filename")
    return name


def normalize_source_id(value):
    """Require an explicit stable source label without an account number."""
    value = _text(value, 100)
    if not value:
        raise ValueError("document_source_required")
    return value


def _row(raw, *, identifier, external_id, source):
    return {
        "id": identifier,
        "external_id": external_id,
        **{field: raw.get(field, "") for field in FIELDS},
        "source": source,
        "edited_fields": [],
    }


def parse_csv_document(content, *, filename, source_id):
    """Read the explicitly documented CSV dialect, retaining physical lines."""
    if not isinstance(content, str) or len(content.encode()) > MAX_DOCUMENT_BYTES:
        raise ValueError("document_too_large")
    filename = _filename(filename)
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")), strict=True)
    columns = reader.fieldnames or []
    if (
        not set(columns) >= CSV_REQUIRED
        or set(columns) - CSV_REQUIRED - {"value_date", "note"}
        or len(columns) != len(set(columns))
    ):
        raise ValueError("invalid_document_csv_columns")
    rows, identifiers = [], set()
    lines = content.splitlines()
    previous_line = reader.line_num
    try:
        for raw in reader:
            start = previous_line
            previous_line = reader.line_num
            if None in raw or any(value is None for value in raw.values()):
                raise ValueError("invalid_document_csv_row")
            external_id = _text(raw["id"], 100)
            if not external_id or external_id in identifiers:
                raise ValueError("duplicate_or_missing_document_id")
            identifiers.add(external_id)
            quote = "\n".join(lines[start : reader.line_num])
            if len(quote) > 2000 or len(rows) >= MAX_DOCUMENT_ROWS:
                raise ValueError("document_too_large")
            rows.append(
                _row(
                    raw,
                    identifier=f"row-{reader.line_num}",
                    external_id=external_id,
                    source={"filename": filename, "row": start + 1, "quote": quote},
                )
            )
    except csv.Error as err:
        raise ValueError("invalid_document_csv") from err
    if not rows:
        raise ValueError("empty_document")
    return {
        "format": "csv_v1",
        "source_id": normalize_source_id(source_id),
        "fingerprint": _digest(content.encode()),
        "filename": filename,
        "rows": rows,
        "issues": [],
        "requires_ai_review": False,
    }


def extract_pdf_pages(content):
    """Extract text in an executor. Scans need a separate OCR adapter."""
    from pypdf import PdfReader  # Lazy import keeps CSV independent of PDF support.

    if not isinstance(content, bytes) or len(content) > MAX_DOCUMENT_BYTES:
        raise ValueError("document_too_large")
    if not content.startswith(b"%PDF-"):
        raise ValueError("invalid_document_pdf")
    try:
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise ValueError("encrypted_document_pdf")
        if not 1 <= len(reader.pages) <= MAX_PDF_PAGES:
            raise ValueError("document_too_large")
        pages, size = [], 0
        for page in reader.pages:
            text = page.extract_text() or ""
            size += len(text)
            if size > MAX_PDF_TEXT:
                raise ValueError("document_too_large")
            # A mixed scan/text document must not silently lose scanned pages.
            if not text.strip():
                raise ValueError("document_ocr_required")
            pages.append(text)
        return pages
    except ValueError:
        raise
    except Exception as err:
        raise ValueError("invalid_document_pdf") from err


def ai_document_draft(result, *, pages, content, filename, source_id):
    """Accept only bounded extraction results whose quotations exist in the PDF."""
    filename = _filename(filename)
    if not isinstance(result, dict) or not isinstance(result.get("rows"), list):
        raise ValueError("invalid_document_extraction")
    if not 1 <= len(result["rows"]) <= MAX_DOCUMENT_ROWS:
        raise ValueError("invalid_document_extraction")
    issues = []
    if result.get("complete") is not True:
        issues.append("incomplete_extraction")
    warnings = result.get("warnings", [])
    if not isinstance(warnings, list) or len(warnings) > 100:
        raise ValueError("invalid_document_extraction")
    issues.extend(_text(item) for item in warnings)
    fingerprint = _digest(content)
    rows = []
    for index, raw in enumerate(result["rows"]):
        if not isinstance(raw, dict):
            raise ValueError("invalid_document_extraction")
        page, quote = raw.get("page"), _text(raw.get("quote"), 2000)
        if (
            isinstance(page, bool)
            or not isinstance(page, int)
            or not 1 <= page <= len(pages)
            or not quote
            or " ".join(quote.split()) not in " ".join(pages[page - 1].split())
        ):
            raise ValueError("document_source_not_found")
        external_id = _text(raw.get("id", ""), 100)
        if external_id and external_id not in quote:
            raise ValueError("document_source_not_found")
        rows.append(
            _row(
                raw,
                identifier=f"row-{index + 1}",
                external_id=external_id or f"{fingerprint}:{index + 1}",
                source={"filename": filename, "page": page, "quote": quote},
            )
        )
    if len({row["external_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate_or_missing_document_id")
    return {
        "format": "pdf_ai_v1",
        "source_id": normalize_source_id(source_id),
        "fingerprint": fingerprint,
        "filename": filename,
        "rows": rows,
        "issues": issues,
        "requires_ai_review": True,
    }


def correct_document(draft, corrections):
    """Apply user-entered fields while retaining the original source quotation."""
    if not isinstance(corrections, dict) or len(corrections) > MAX_DOCUMENT_ROWS:
        raise ValueError("invalid_document_corrections")
    result = deepcopy(draft)
    rows = {row["id"]: row for row in result["rows"]}
    for identifier, fields in corrections.items():
        if (
            identifier not in rows
            or not isinstance(fields, dict)
            or set(fields) - set(FIELDS)
        ):
            raise ValueError("invalid_document_corrections")
        for field, value in fields.items():
            if not isinstance(value, (str, int, float)) or isinstance(value, bool):
                raise ValueError("invalid_document_corrections")
            rows[identifier][field] = value
        rows[identifier]["edited_fields"] = sorted(
            set(rows[identifier]["edited_fields"]) | fields.keys()
        )
    return result


def _number(value):
    if isinstance(value, bool) or not re.fullmatch(r"\d+(?:\.\d+)?", str(value)):
        raise ValueError("positive_decimal_required")
    try:
        result = Decimal(str(value))
    except InvalidOperation as err:
        raise ValueError("positive_decimal_required") from err
    if not result.is_finite() or not 0 < result <= Decimal("1e12"):
        raise ValueError("positive_decimal_required")
    return float(result)


def _day(value, today):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("iso_date_required")
    try:
        result = date.fromisoformat(value)
    except ValueError as err:
        raise ValueError("iso_date_required") from err
    if result > today:
        raise ValueError("future_date")
    return value


def _number_in_quote(value, quote):
    """Check that a quantity occurs in the source; ambiguous grouping needs review."""
    for token in re.findall(r"(?<![\w])\d[\d.,]*(?![\w])", quote):
        token = token.rstrip(".,")
        if "." in token and "," in token:
            decimal = "." if token.rfind(".") > token.rfind(",") else ","
            token = token.replace("," if decimal == "." else ".", "")
        token = token.replace(",", ".")
        try:
            if Decimal(token) == Decimal(str(value)):
                return True
        except InvalidOperation:
            continue
    return False


def _source_issues(row, normalized):
    """Generated financial values need evidence or an explicit user correction."""
    source = row["source"]
    if "page" not in source:
        return []
    quote, edited, issues = source["quote"], set(row["edited_fields"]), []
    for field in ("amount", "units"):
        if (
            normalized.get(field)
            and field not in edited
            and not _number_in_quote(normalized[field], quote)
        ):
            issues.append(f"{field}: value_not_in_source")
    for field in ("date", "value_date"):
        if normalized.get(field) and field not in edited:
            parsed = date.fromisoformat(normalized[field])
            forms = (
                parsed.isoformat(),
                parsed.strftime("%d.%m.%Y"),
                parsed.strftime("%d/%m/%Y"),
            )
            if not any(value in quote for value in forms):
                issues.append(f"{field}: value_not_in_source")
    currency = normalized.get("currency")
    if (
        currency
        and "currency" not in edited
        and currency not in quote.upper()
        and not (currency == "EUR" and "€" in quote)
    ):
        issues.append("currency: value_not_in_source")
    symbol = normalized.get("symbol")
    if symbol and "symbol" not in edited and symbol not in quote:
        issues.append("symbol: value_not_in_source")
    return issues


def _normalize(row, existing, today):
    normalized, issues = {}, []
    for field in FIELDS:
        value = row.get(field, "")
        try:
            if field == "type":
                if value not in {"deposit", "purchase", "dividend"}:
                    raise ValueError("unsupported_event_type")
            elif field == "amount" or (field == "units" and row["type"] == "purchase"):
                value = _number(value)
            elif field == "date" or (field == "value_date" and value):
                value = _day(value, today)
            else:
                value = _text(value)
            normalized[field] = value
        except (ValueError, TypeError, OverflowError) as err:
            issues.append(f"{field}: {err}")
    if normalized.get("currency") != existing[c.CONF_BASE_CURRENCY]:
        issues.append("currency: wallet_currency_required")
    symbol = normalized.get("symbol")
    if (row["type"] == "purchase" or symbol) and symbol not in {
        valor[c.VALOR_SYMBOL] for valor in existing[c.CONF_VALORS]
    }:
        issues.append("symbol: existing_wallet_symbol_required")
    if row["type"] != "dividend" and row.get("value_date"):
        issues.append("value_date: only_dividends_supported")
    if row["type"] != "purchase" and row.get("units"):
        issues.append("units: only_purchases_supported")
    if row["type"] == "deposit" and symbol:
        issues.append("symbol: deposit_has_no_symbol")
    if not issues:
        issues.extend(_source_issues(row, normalized))
    return normalized, issues


def _existing_events(data):
    result = []
    for row in contributions_from_data(data):
        if row[c.CONTRIBUTION_AMOUNT] > 0:
            result.append(
                {
                    "id": row[c.CONTRIBUTION_ID],
                    "type": "deposit",
                    "date": row[c.CONTRIBUTION_DATE],
                    "amount": row[c.CONTRIBUTION_AMOUNT],
                }
            )
    result.extend(
        {
            "id": lot[c.LOT_ID],
            "type": "purchase",
            "date": lot[c.LOT_DATE],
            "amount": lot[c.LOT_AMOUNT],
            "symbol": lot[c.LOT_SYMBOL],
            "units": lot[c.LOT_UNITS],
        }
        for lot in all_lots(data)
    )
    result.extend(
        {
            "id": row[c.DIVIDEND_ID],
            "type": "dividend",
            "date": row[c.DIVIDEND_BOOKING_DATE],
            "amount": row[c.DIVIDEND_AMOUNT],
            "symbol": row.get(c.DIVIDEND_SYMBOL, ""),
            "value_date": row.get(c.DIVIDEND_VALUE_DATE, ""),
        }
        for row in dividends_from_data(data)
    )
    return result


def _signature(row):
    return (
        row["type"],
        row["date"],
        round(row["amount"], 8),
        row.get("symbol", ""),
        round(row.get("units") or 0, 12),
        row.get("value_date") or "",
    )


def _link(row, source_id):
    group = {"deposit": "contributions", "purchase": "lots", "dividend": "dividends"}[
        row["type"]
    ]
    key = "document:" + _digest(
        json.dumps([source_id, row["type"], row["external_id"]]).encode()
    )
    return group, key


def prepare_document(draft, existing, *, today, decisions=None):
    """Reconcile only against the original wallet, then validate one candidate."""
    decisions = decisions or {}
    row_ids = {row["id"] for row in draft["rows"]}
    if (
        not isinstance(decisions, dict)
        or set(decisions) - row_ids
        or any(
            not isinstance(value, str) or len(value) > 100
            for value in decisions.values()
        )
    ):
        raise ValueError("invalid_document_decisions")
    candidate = deepcopy(dict(existing))
    links = candidate.setdefault(IMPORT_LINKS, {})
    for group in ("plans", "contributions", "lots", "dividends"):
        links.setdefault(group, {})
    original = _existing_events(existing)
    used, additions, audit, rows = set(), [], [], []
    issues = list(draft["issues"])
    for raw in draft["rows"]:
        row = deepcopy(raw)
        normalized, row_issues = _normalize(row, existing, today)
        row["issues"] = row_issues
        choice = decisions.get(row["id"])
        if choice == "skip":
            row["status"] = "skipped"
        elif row_issues:
            row["status"] = "invalid"
        else:
            group, key = _link(row, draft["source_id"])
            linked = links[group].get(key)
            stable = [
                item
                for item in original
                if item["type"] == row["type"] and item["id"] == linked
            ]
            matches = stable or [
                item for item in original if _signature(item) == _signature(normalized)
            ]
            row["matches"] = matches
            if linked and not stable:
                row["issues"].append("source_record_was_removed")
                row["status"] = "review"
            elif stable and _signature(stable[0]) != _signature(normalized):
                row["issues"].append("source_record_conflicts_with_wallet")
                row["status"] = "review"
            elif stable or (choice and choice not in {"add", "skip"}):
                selected = (
                    stable[0]
                    if stable
                    else next((item for item in matches if item["id"] == choice), None)
                )
                identity = (row["type"], selected["id"]) if selected else None
                if selected is None or identity in used:
                    row["issues"].append("invalid_or_reused_match")
                    row["status"] = "review"
                else:
                    used.add(identity)
                    row["status"] = "duplicate"
                    links[group][key] = selected["id"]
            elif matches and choice != "add":
                row["status"] = "review"
                row["issues"].append("possible_duplicate_requires_choice")
            else:
                row["status"] = "add"
                record_id = uuid5(NAMESPACE_URL, f"my_wallet:{key}").hex
                links[group][key] = record_id
                additions.append({**normalized, "id": record_id})
            if row["status"] in {"add", "duplicate"}:
                audit.append(
                    {
                        "source_id": key,
                        "record_id": links[group][key],
                        "source": row["source"],
                        "edited_fields": row["edited_fields"],
                    }
                )
        rows.append(row)
    summary = {
        "added": len(additions),
        "duplicates": sum(row["status"] == "duplicate" for row in rows),
        "cash_change": 0,
        "currency": existing[c.CONF_BASE_CURRENCY],
    }
    if issues or any(row["status"] in {"review", "invalid"} for row in rows):
        return None, {"rows": rows, "issues": issues, "summary": summary}
    # Funding/income first; all historical dates are still checked by the core.
    for row in (item for item in additions if item["type"] == "deposit"):
        candidate[c.CONF_CONTRIBUTIONS] = [
            *candidate.get(c.CONF_CONTRIBUTIONS, []),
            make_contribution(
                row["amount"],
                row["date"],
                contribution_id=row["id"],
                source="import",
                note=row["note"],
            ),
        ]
    for row in (item for item in additions if item["type"] == "dividend"):
        candidate[c.CONF_DIVIDENDS] = [
            *candidate.get(c.CONF_DIVIDENDS, []),
            make_dividend(
                amount=row["amount"],
                booking_date=row["date"],
                value_date=row["value_date"] or None,
                symbol=row["symbol"] or None,
                note=row["note"] or None,
                dividend_id=row["id"],
            ),
        ]
    try:
        for row in (item for item in additions if item["type"] == "purchase"):
            lot = make_lot(
                symbol=row["symbol"],
                execution_date=row["date"],
                amount=row["amount"],
                units=row["units"],
                unit_price=row["amount"] / row["units"],
                quote_currency=row["currency"],
                estimated=False,
                lot_id=row["id"],
            )
            candidate[c.CONF_CONTRIBUTIONS] = [
                *candidate.get(c.CONF_CONTRIBUTIONS, []),
                make_contribution(
                    0,
                    row["date"],
                    contribution_id="purchase:" + row["id"],
                    source=c.CONTRIBUTION_SOURCE_PURCHASE,
                    lots=[lot],
                ),
            ]
        candidate = prepare_change(existing, candidate, today=today)
    except ValueError as err:
        return None, {"rows": rows, "issues": [str(err)], "summary": summary}
    if not additions and candidate.get(IMPORT_LINKS) == existing.get(IMPORT_LINKS):
        return deepcopy(dict(existing)), {
            "rows": rows,
            "issues": [],
            "summary": summary,
        }
    records = list(candidate.get(IMPORT_RECORDS, []))
    prior = next(
        (
            record
            for record in records
            if record.get("document_hash") == draft["fingerprint"]
            and record.get("source_id") == draft["source_id"]
        ),
        None,
    )
    sources = {item["source_id"]: item for item in (prior or {}).get("sources", [])}
    sources.update({item["source_id"]: item for item in audit})
    record = {
        "batch_id": "document:"
        + _digest(json.dumps([draft["source_id"], draft["fingerprint"]]).encode()),
        "fingerprint": _digest(
            json.dumps(rows, sort_keys=True, allow_nan=False).encode()
        ),
        "document_hash": draft["fingerprint"],
        "source_id": draft["source_id"],
        "date": today.isoformat(),
        "adapter": draft["format"],
        "sources": list(sources.values()),
    }
    if prior is not None:
        records = [record if item is prior else item for item in records]
    else:
        records.append(record)
    candidate[IMPORT_RECORDS] = records
    if (
        len(records) > MAX_IMPORT_ITEMS
        or any(len(group) > MAX_IMPORT_ITEMS for group in links.values())
        or len(json.dumps(records, ensure_ascii=False).encode()) > MAX_DOCUMENT_BYTES
    ):
        raise ValueError("document_metadata_full")
    summary["cash_change"] = round(cash_balance(candidate) - cash_balance(existing), 2)
    return candidate, {"rows": rows, "issues": [], "summary": summary}
