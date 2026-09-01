"""Create and validate portable My Wallet configuration backups."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import date, datetime
from math import isfinite
from typing import Any
from uuid import uuid4

from . import const as c
from .contributions import all_lots, invested_total, normalize_contributions
from .corrections import UNIT_CORRECTIONS
from .dividends import cash_balance, dividend_total, normalize_dividends
from .followup_import import IMPORT_LINKS, IMPORT_RECORDS
from .history_import import IMPORT_BATCH, MAX_IMPORT_ITEMS
from .plans import normalize_plan

BACKUP_FORMAT = "my_wallet_backup"
BACKUP_VERSION = 1
BACKUP_RESTORE_ID = "_backup_restore_id"
_MAX_TEXT = 500
_MAX_ALIAS_LENGTH = 80


def _json_copy(value: Any) -> Any:
    """Return a detached JSON-safe value and reject NaN/infinity."""
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _identifier(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", value):
        raise ValueError("invalid_backup")
    return value


def _text(value: Any, maximum: int = _MAX_TEXT) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError("invalid_backup")
    return " ".join(value.split())


def _number(value: Any, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        raise ValueError("invalid_backup")
    result = float(value)
    if not isfinite(result) or result < minimum or result > maximum:
        raise ValueError("invalid_backup")
    return result


def create_backup(
    data: Mapping[str, Any], *, title: str, created_at: datetime
) -> dict[str, Any]:
    """Wrap one config-entry snapshot in a portable, versioned document."""
    return {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "backup_id": uuid4().hex,
        "created_at": created_at.isoformat(),
        "wallet": {
            "title": title,
            "data": _json_copy(dict(data)),
        },
    }


def is_backup(document: Any) -> bool:
    """Return whether a document declares the backup format."""
    return isinstance(document, Mapping) and document.get("format") == BACKUP_FORMAT


def _unique_ids(rows: list[Mapping[str, Any]], key: str = "id") -> None:
    values = [_identifier(row.get(key)) for row in rows]
    if len(values) != len(set(values)):
        raise ValueError("invalid_backup")


def _validate_preserved_metadata(
    raw: Mapping[str, Any], result: dict[str, Any]
) -> None:
    """Keep reconciliation/correction audit data after basic shape validation."""
    if IMPORT_BATCH in raw:
        result[IMPORT_BATCH] = _identifier(raw[IMPORT_BATCH])
    if IMPORT_RECORDS in raw:
        records = raw[IMPORT_RECORDS]
        if not isinstance(records, list) or len(records) > MAX_IMPORT_ITEMS:
            raise ValueError("invalid_backup")
        for row in records:
            if not isinstance(row, Mapping):
                raise ValueError("invalid_backup")
            _identifier(row.get("batch_id"))
            fingerprint = row.get("fingerprint")
            if not isinstance(fingerprint, str) or not re.fullmatch(
                r"[0-9a-f]{64}", fingerprint
            ):
                raise ValueError("invalid_backup")
            date.fromisoformat(str(row.get("date")))
        result[IMPORT_RECORDS] = _json_copy(records)
    if IMPORT_LINKS in raw:
        links = raw[IMPORT_LINKS]
        if not isinstance(links, Mapping):
            raise ValueError("invalid_backup")
        normalized_links: dict[str, dict[str, str]] = {}
        for category in ("plans", "contributions", "lots", "dividends"):
            values = links.get(category, {})
            if not isinstance(values, Mapping) or len(values) > MAX_IMPORT_ITEMS:
                raise ValueError("invalid_backup")
            normalized_links[category] = {
                _identifier(source): _identifier(target)
                for source, target in values.items()
            }
        result[IMPORT_LINKS] = normalized_links
    if UNIT_CORRECTIONS in raw:
        corrections = raw[UNIT_CORRECTIONS]
        if not isinstance(corrections, list) or len(corrections) > MAX_IMPORT_ITEMS:
            raise ValueError("invalid_backup")
        result[UNIT_CORRECTIONS] = _json_copy(corrections)


def prepare_backup(
    document: Mapping[str, Any], *, today: date
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate a backup without trusting or mutating its serialized data."""
    version = document.get("version")
    if (
        document.get("format") != BACKUP_FORMAT
        or isinstance(version, bool)
        or version != BACKUP_VERSION
    ):
        raise ValueError("invalid_backup")
    backup_id = _identifier(document.get("backup_id"))
    wallet = document.get("wallet")
    if not isinstance(wallet, Mapping) or not isinstance(wallet.get("data"), Mapping):
        raise ValueError("invalid_backup")
    raw = wallet["data"]

    name = _text(wallet.get("title") or raw.get(c.CONF_WALLET_NAME), 100)
    currency = _text(raw.get(c.CONF_BASE_CURRENCY), 3).upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("invalid_backup")
    interval_value = _number(
        raw.get(c.CONF_SCAN_INTERVAL, c.DEFAULT_SCAN_INTERVAL),
        minimum=c.MIN_SCAN_INTERVAL,
        maximum=c.MAX_SCAN_INTERVAL,
    )
    if not interval_value.is_integer():
        raise ValueError("invalid_backup")
    expected_return = _number(
        raw.get(
            c.CONF_EXPECTED_ANNUAL_RETURN,
            c.DEFAULT_EXPECTED_ANNUAL_RETURN,
        ),
        minimum=c.MIN_EXPECTED_ANNUAL_RETURN,
        maximum=c.MAX_EXPECTED_ANNUAL_RETURN,
    )

    raw_valors = raw.get(c.CONF_VALORS)
    if not isinstance(raw_valors, list) or not 1 <= len(raw_valors) <= 100:
        raise ValueError("invalid_backup")
    valors: list[dict[str, Any]] = []
    symbols: set[str] = set()
    for raw_valor in raw_valors:
        if not isinstance(raw_valor, Mapping):
            raise ValueError("invalid_backup")
        symbol = _text(raw_valor.get(c.VALOR_SYMBOL), 32).upper()
        if not re.fullmatch(r"[A-Z0-9^][A-Z0-9^=._-]*", symbol) or symbol in symbols:
            raise ValueError("invalid_backup")
        symbols.add(symbol)
        valor = {
            c.VALOR_SYMBOL: symbol,
            c.VALOR_AMOUNT: _number(
                raw_valor.get(c.VALOR_AMOUNT), minimum=0, maximum=1e12
            ),
        }
        if raw_valor.get(c.VALOR_TARGET_SHARE) is not None:
            valor[c.VALOR_TARGET_SHARE] = _number(
                raw_valor[c.VALOR_TARGET_SHARE], minimum=0, maximum=100
            )
        if raw_valor.get(c.VALOR_ALIAS):
            valor[c.VALOR_ALIAS] = _text(raw_valor[c.VALOR_ALIAS], _MAX_ALIAS_LENGTH)
        valors.append(valor)
    if (
        sum(item.get(c.VALOR_TARGET_SHARE, 0) for item in valors)
        > 100 + c.TARGET_SHARE_SUM_TOLERANCE
    ):
        raise ValueError("invalid_backup")

    raw_contributions = raw.get(c.CONF_CONTRIBUTIONS, [])
    raw_dividends = raw.get(c.CONF_DIVIDENDS, [])
    raw_plans = raw.get(c.CONF_SAVINGS_PLANS, [])
    raw_retired = raw.get(c.CONF_RETIRED_SAVINGS_PLANS, [])
    if not all(
        isinstance(rows, list)
        for rows in (raw_contributions, raw_dividends, raw_plans, raw_retired)
    ):
        raise ValueError("invalid_backup")
    contributions = normalize_contributions(raw_contributions)
    dividends = normalize_dividends(raw_dividends)
    plans = [normalize_plan(item) for item in raw_plans]
    retired = [normalize_plan(item) for item in raw_retired]
    lots = [lot for row in contributions for lot in row[c.CONTRIBUTION_LOTS]]
    if (
        len(valors)
        + len(contributions)
        + len(lots)
        + len(dividends)
        + len(plans)
        + len(retired)
        > MAX_IMPORT_ITEMS
    ):
        raise ValueError("invalid_backup")
    for rows in (contributions, lots, dividends, plans, retired):
        _unique_ids(rows)

    plan_ids = {item[c.PLAN_ID] for item in [*plans, *retired]}
    for row in contributions:
        if row[c.CONTRIBUTION_DATE] and row[c.CONTRIBUTION_DATE] > today.isoformat():
            raise ValueError("future_date")
        if row.get(c.CONTRIBUTION_PLAN_ID) not in (None, *plan_ids):
            raise ValueError("invalid_backup")
        for lot in row[c.CONTRIBUTION_LOTS]:
            if lot[c.LOT_SYMBOL] not in symbols or lot[c.LOT_DATE] > today.isoformat():
                raise ValueError("invalid_backup")
    for item in dividends:
        if item.get(c.DIVIDEND_SYMBOL) not in (None, *symbols):
            raise ValueError("invalid_backup")
        if (
            item[c.DIVIDEND_BOOKING_DATE] > today.isoformat()
            or (item.get(c.DIVIDEND_VALUE_DATE) or "") > today.isoformat()
        ):
            raise ValueError("future_date")
    for plan in [*plans, *retired]:
        if any(
            allocation[c.ALLOCATION_SYMBOL] not in symbols
            for allocation in plan[c.PLAN_ALLOCATIONS]
        ):
            raise ValueError("invalid_backup")

    result: dict[str, Any] = {
        c.CONF_WALLET_NAME: name,
        c.CONF_BASE_CURRENCY: currency,
        c.CONF_SCAN_INTERVAL: int(interval_value),
        c.CONF_EXPECTED_ANNUAL_RETURN: expected_return,
        c.CONF_VALORS: valors,
        c.CONF_CONTRIBUTIONS: contributions,
        c.CONF_DIVIDENDS: dividends,
        c.CONF_SAVINGS_PLANS: plans,
        c.CONF_RETIRED_SAVINGS_PLANS: retired,
        BACKUP_RESTORE_ID: backup_id,
    }
    _validate_preserved_metadata(raw, result)
    capital = invested_total(result, through=today) or 0.0
    summary = {
        "mode": "backup",
        "backup": True,
        "wallet_name": name,
        "currency": currency,
        "deposits": len(contributions),
        "purchases": len(all_lots(result, through=today)),
        "dividends": len(dividends),
        "capital": round(capital, 2),
        "dividend_total": round(dividend_total(result, through=today), 2),
        "spending": round(
            sum(lot[c.LOT_AMOUNT] for lot in all_lots(result, through=today)), 2
        ),
        "cash": round(cash_balance(result, through=today), 2),
        "estimated": sum(
            bool(lot[c.LOT_ESTIMATED]) for lot in all_lots(result, through=today)
        ),
        "plans": plans,
        "missing": [],
    }
    return result, summary
