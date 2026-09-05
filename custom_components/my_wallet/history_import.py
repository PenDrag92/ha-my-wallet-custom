"""Validate and prepare a statement import without changing an existing wallet."""

from __future__ import annotations

import re
from datetime import date, timedelta
from math import isfinite
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from . import const as c
from .contributions import make_contribution, make_lot
from .dividends import make_dividend
from .history import historical_fx, latest_close
from .ledger import validate_change, validate_records
from .plans import make_plan, scheduled_dates
from .yahoo import fetch_histories, fx_symbol

IMPORT_BATCH = "import_batch"
MAX_IMPORT_ITEMS = 2000


def _identifier(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", value):
        raise ValueError("invalid_import_id")
    return value


def _text(value: Any, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError("invalid_import_text")
    return value.strip()


def _number(value: Any, *, allow_zero=False) -> float:
    if isinstance(value, bool):
        raise ValueError("invalid_import_number")
    number = float(value)
    if (
        not isfinite(number)
        or number > 1e12
        or (number < 0 if allow_zero else number <= 0)
    ):
        raise ValueError("invalid_import_number")
    return number


def _day(value: Any, today: date) -> str:
    day = date.fromisoformat(str(value))
    if day > today:
        raise ValueError("future_date")
    return day.isoformat()


def _uid(batch: str, item: str) -> str:
    return uuid5(NAMESPACE_URL, f"my_wallet:{batch}:{item}").hex


def validate_document(document: dict[str, Any], *, today: date) -> dict[str, Any]:
    """Accept only explicit ledger records; no paths, URLs or executable data."""
    if document.get("format") != "my_wallet_history" or document.get("version") != 1:
        raise ValueError("invalid_import_format")
    batch = _identifier(document.get("batch_id"))
    base = _text(document.get("base_currency"), 3).upper()
    if not re.fullmatch(r"[A-Z]{3}", base):
        raise ValueError("invalid_import_currency")
    valors = []
    symbols = set()
    items = 0
    ids = set()

    def unique(raw):
        nonlocal items
        identifier = _identifier(raw)
        items += 1
        if identifier in ids or items > MAX_IMPORT_ITEMS:
            raise ValueError("duplicate_or_excess_import_items")
        ids.add(identifier)
        return identifier

    for asset in document.get("assets", []):
        symbol = _text(asset.get("symbol"), 32).upper()
        if not re.fullmatch(r"[A-Z0-9^][A-Z0-9^=._-]*", symbol) or symbol in symbols:
            raise ValueError("invalid_import_symbol")
        symbols.add(symbol)
        valor = {c.VALOR_SYMBOL: symbol, c.VALOR_AMOUNT: 0.0}
        if asset.get("target_share") is not None:
            share = _number(asset["target_share"], allow_zero=True)
            if share > 100:
                raise ValueError("invalid_import_target")
            valor[c.VALOR_TARGET_SHARE] = share
        valors.append(valor)
    if not 1 <= len(symbols) <= 100:
        raise ValueError("invalid_import_assets")
    if sum(valor.get(c.VALOR_TARGET_SHARE, 0) for valor in valors) > 100.00001:
        raise ValueError("invalid_import_target")
    plans = []
    plan_ids = {}
    for row in document.get("plans", []):
        identifier = unique(row.get("id"))
        plan = make_plan(
            plan_id=_uid(batch, identifier),
            name=_text(row.get("name")),
            first_date=row["first_date"],
            end_date=row.get("end_date"),
            allocation_mode=row["allocation_mode"],
            allocations=row["allocations"],
            amount=row.get("amount"),
            enabled=bool(row.get("enabled", True)),
            use_cash_balance=bool(row.get("use_cash_balance", True)),
        )
        if any(
            item[c.ALLOCATION_SYMBOL] not in symbols
            for item in plan[c.PLAN_ALLOCATIONS]
        ):
            raise ValueError("invalid_import_symbol")
        plan_ids[identifier] = plan
        plans.append(plan)
    deposits = []
    booked = set()
    for row in document.get("deposits", []):
        identifier = unique(row.get("id"))
        day = _day(row.get("date"), today)
        plan_key = row.get("plan_id")
        if plan_key is not None and plan_key not in plan_ids:
            raise ValueError("invalid_import_plan")
        plan = plan_ids.get(plan_key)
        scheduled = _day(row.get("scheduled_date"), today) if plan else None
        if plan:
            period = (plan[c.PLAN_ID], scheduled[:7])
            if period in booked or scheduled not in {
                item.isoformat() for item in scheduled_dates(plan, today)
            }:
                raise ValueError("invalid_import_schedule")
            booked.add(period)
        purchases = []
        for purchase in row.get("purchases", []):
            purchase_id = unique(purchase.get("id"))
            purchase_day = _day(purchase.get("date"), today)
            symbol = str(purchase.get("symbol", "")).upper()
            if symbol not in symbols or purchase_day < day:
                raise ValueError("invalid_import_purchase")
            result = {
                "id": purchase_id,
                "date": purchase_day,
                "symbol": symbol,
                "amount": _number(purchase.get("amount")),
            }
            for key in ("units", "unit_price"):
                if purchase.get(key) is not None:
                    result[key] = _number(purchase[key])
            if "units" in result and "unit_price" in result:
                raise ValueError("price_or_units")
            purchases.append(result)
        deposits.append(
            {
                "id": identifier,
                "date": day,
                "amount": _number(row.get("amount")),
                "note": _text(row["note"], 500) if row.get("note") else "",
                "plan": plan,
                "scheduled_date": scheduled,
                "purchases": purchases,
            }
        )
    dividends = []
    for row in document.get("dividends", []):
        identifier = unique(row.get("id"))
        symbol = row.get("symbol")
        if symbol is not None and symbol not in symbols:
            raise ValueError("invalid_import_symbol")
        dividends.append(
            make_dividend(
                amount=_number(row.get("amount")),
                booking_date=_day(row.get("booking_date"), today),
                value_date=_day(row["value_date"], today)
                if row.get("value_date")
                else None,
                symbol=symbol,
                note=_text(row["note"], 500) if row.get("note") else None,
                dividend_id=_uid(batch, identifier),
            )
        )
    if not deposits:
        raise ValueError("empty_import")
    # Imported statements own their past periods. Never silently fill gaps in
    # a statement with simulated deposits during the first coordinator refresh.
    for plan in plans:
        plan[c.PLAN_SKIPPED_PERIODS] = [
            day.strftime("%Y-%m")
            for day in scheduled_dates(plan, today)
            if (plan[c.PLAN_ID], day.strftime("%Y-%m")) not in booked
        ]
    return {
        IMPORT_BATCH: batch,
        c.CONF_WALLET_NAME: _text(document.get("wallet_name")),
        c.CONF_BASE_CURRENCY: base,
        c.CONF_SCAN_INTERVAL: 60,
        c.CONF_EXPECTED_ANNUAL_RETURN: c.DEFAULT_EXPECTED_ANNUAL_RETURN,
        c.CONF_EXPECTED_ANNUAL_INFLATION: c.DEFAULT_EXPECTED_ANNUAL_INFLATION,
        c.CONF_INFLATION_SOURCE: c.DEFAULT_INFLATION_SOURCE,
        c.CONF_VALORS: valors,
        c.CONF_SAVINGS_PLANS: plans,
        c.CONF_RETIRED_SAVINGS_PLANS: [],
        c.CONF_DIVIDENDS: dividends,
        "deposits": deposits,
    }


async def async_prepare_import(document, *, session, today: date, check_cash=True):
    validated = validate_document(document, today=today)
    batch = validated[IMPORT_BATCH]
    base = validated[c.CONF_BASE_CURRENCY]
    purchases = [item for row in validated["deposits"] for item in row["purchases"]]
    lookup = [
        item for item in purchases if "units" not in item and "unit_price" not in item
    ]
    histories = {}
    if lookup:
        start = min(date.fromisoformat(item["date"]) for item in lookup) - timedelta(
            days=7
        )
        end = max(date.fromisoformat(item["date"]) for item in lookup)
        histories = await fetch_histories(
            session, sorted({item["symbol"] for item in lookup}), start, end
        )
        currencies = {quote.currency for rows in histories.values() for quote in rows}
        pairs = sorted(
            {
                pair
                for currency in currencies - {base}
                for pair in (fx_symbol(currency, base), fx_symbol(base, currency))
            }
        )
        if pairs:
            histories.update(await fetch_histories(session, pairs, start, end))
    contributions = []
    missing = []
    for deposit in validated["deposits"]:
        lots = []
        for item in deposit["purchases"]:
            day = date.fromisoformat(item["date"])
            units = item.get("units")
            price = item.get("unit_price")
            estimated = units is None and price is None
            fx, currency, price_day = 1.0, base, day
            if estimated:
                quote = latest_close(histories.get(item["symbol"], []), day)
                fx = (
                    historical_fx(histories, quote.currency, base, day)
                    if quote
                    else None
                )
                if quote is None or fx is None:
                    missing.append(
                        {
                            "id": item["id"],
                            "symbol": item["symbol"],
                            "date": item["date"],
                            "amount": item["amount"],
                            "reason": "historical_price_unavailable"
                            if quote is None
                            else "historical_fx_unavailable",
                        }
                    )
                    continue
                price, currency, price_day = quote.close, quote.currency, quote.date
            elif units is not None:
                price = item["amount"] / units
            lot = make_lot(
                symbol=item["symbol"],
                execution_date=day,
                amount=item["amount"],
                unit_price=price,
                quote_currency=currency,
                fx_rate=fx,
                units=units,
                included_in_opening=False,
                estimated=estimated,
                lot_id=_uid(batch, item["id"]),
                price_date=price_day,
            )
            lots.append(lot)
        plan = deposit["plan"]
        contributions.append(
            make_contribution(
                deposit["amount"],
                deposit["date"],
                contribution_id=_uid(batch, deposit["id"]),
                source="import",
                lots=lots,
                note=deposit["note"],
                plan_id=plan[c.PLAN_ID] if plan else None,
                plan_name=plan[c.PLAN_NAME] if plan else None,
                scheduled_date=deposit["scheduled_date"],
            )
        )
    data = {key: value for key, value in validated.items() if key != "deposits"}
    data[c.CONF_CONTRIBUTIONS] = contributions
    capital = round(sum(row["amount"] for row in validated["deposits"]), 2)
    dividends = round(sum(row[c.DIVIDEND_AMOUNT] for row in data[c.CONF_DIVIDENDS]), 2)
    spending = round(sum(row["amount"] for row in purchases), 2)
    summary = {
        "wallet_name": data[c.CONF_WALLET_NAME],
        "currency": base,
        "deposits": len(contributions),
        "purchases": len(purchases),
        "dividends": len(data[c.CONF_DIVIDENDS]),
        "capital": capital,
        "dividend_total": dividends,
        "spending": spending,
        "cash": round(capital + dividends - spending, 2),
        "estimated": sum(
            lot[c.LOT_ESTIMATED]
            for row in contributions
            for lot in row[c.CONTRIBUTION_LOTS]
        ),
        "plans": data[c.CONF_SAVINGS_PLANS],
        "missing": missing,
    }
    if missing:
        return None, summary
    try:
        data = (
            validate_change({}, data, today=today)
            if check_cash
            else validate_records(data, today=today)
        )
    except ValueError as err:
        if str(err) == "cash_conflict":
            raise ValueError("import_cash_conflict") from err
        raise
    return data, summary
