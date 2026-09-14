"""Evidence-bearing wallet facts, monthly attribution and transparent checks."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from math import isfinite

from . import const as c
from .analytics import period_summaries
from .contributions import all_lots, opening_balance_conflicts
from .dividends import cash_balance, cash_timeline, dividends_from_data
from .target import target_deviation, target_projection
from .valuation import position_valuation, wallet_valuation
from .wallet_snapshot import valuation_unavailable_reason, wallet_with_saved_units


def _performance(result):
    return {
        "cost": result.cost,
        "income": result.income,
        "value": result.value,
        "profit": result.profit,
        "percentage": result.percentage,
        "annualized": result.annualized,
    }


def _period_report(data, history, *, today, month):
    """Use existing calendar-period accounting, never lifetime profit deltas."""
    month = month or today.strftime("%Y-%m")
    if not isinstance(month, str) or not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ValueError("invalid_report_month")
    try:
        start = date.fromisoformat(month + "-01")
    except ValueError as err:
        raise ValueError("invalid_report_month") from err
    if start > today:
        raise ValueError("invalid_report_month")
    result = {
        "status": "unavailable",
        "reason": "history_unavailable",
        "month": month,
        "source": "reconstructed_daily_closes",
        "wallet": None,
        "positions": [],
        "reconciliation": None,
        "assumptions": [
            (
                "Calendar-month gain uses daily closes reconstructed from the "
                "current ledger, not recorded live valuations."
            ),
            (
                "Wallet gain excludes external deposits; position gains exclude "
                "purchases and include assigned dividends."
            ),
            (
                "Missing opening values or any daily quote gap make the affected "
                "attribution unavailable."
            ),
            (
                "Historical prices and FX are evidence of value changes, not "
                "evidence of market causes."
            ),
        ],
    }
    if history is None:
        return result
    points = [
        point
        for point in history.get("points", [])
        if point["date"] <= today.isoformat()
    ]
    ledger = [
        row
        for row in history.get("ledger", [])
        if not row.get("date") or row["date"] <= today.isoformat()
    ]
    if not points:
        return result
    summaries = period_summaries(points, ledger)
    wallet = next((row for row in summaries["monthly"] if row["period"] == month), None)
    result["estimated_purchases"] = bool(history.get("estimated"))
    result["range_limited"] = bool(history.get("range_limited"))
    result["unknown_opening"] = list(history.get("unknown_opening", []))
    if wallet is None:
        return {**result, "reason": "period_outside_history"}
    # period_summaries intentionally retains endpoint gain for chart use even
    # when an interior quote is absent. Explanations require complete evidence.
    wallet = dict(wallet)
    if not wallet["complete"]:
        wallet.update({"gain": None, "return": None})
    result["wallet"] = wallet
    unknown = set(history.get("unknown_opening", []))
    unknown.update(row["symbol"] for row in history.get("opening_conflicts", []))
    for configured in data[c.CONF_VALORS]:
        symbol = configured[c.VALOR_SYMBOL]
        rows = period_summaries(points, ledger, symbol=symbol)["monthly"]
        row = next((row for row in rows if row["period"] == month), None)
        if row is None:
            continue
        item = {"symbol": symbol, **row}
        if symbol in unknown or not item["complete"]:
            item.update({"complete": False, "gain": None, "return": None})
        result["positions"].append(item)
    result["positions"].sort(
        key=lambda row: (row["gain"] is None, -(row["gain"] or 0), row["symbol"])
    )
    complete = wallet["complete"] and all(
        row["complete"] for row in result["positions"]
    )
    if complete:
        unassigned = sum(
            row["amount"]
            for row in ledger
            if row["type"] == "dividend"
            and not row.get("symbol")
            and (row.get("date") or "")[:7] == month
            and row["date"] <= today.isoformat()
        )
        position_gain = sum(row["gain"] for row in result["positions"])
        residual = round(wallet["gain"] - position_gain - unassigned, 2)
        # Historical daily points are already rounded per position; allow one
        # cent per component, but never present unreconciled attribution as fact.
        reconciled = abs(residual) <= 0.01 * (len(result["positions"]) + 1) + 1e-8
        result["reconciliation"] = {
            "position_gain": round(position_gain, 2),
            "unassigned_dividends": round(unassigned, 2),
            "rounding_residual": residual,
            "complete": reconciled,
        }
        result.update(
            {
                "status": "ok" if reconciled else "partial",
                "reason": None if reconciled else "attribution_mismatch",
            }
        )
    else:
        result["reason"] = "incomplete_period_history"
    return result


def build_wallet_insights(
    data, current, *, today, available=True, history=None, month=None
):
    """Return auditable facts and rule-based findings without rewriting records."""
    current = wallet_with_saved_units(data, current, today=today)
    reason = valuation_unavailable_reason(current, available=available)
    valuation = wallet_valuation(data, current, today=today, available=reason is None)
    total = valuation.nominal.value
    findings = []

    def finding(code, severity, message, **evidence):
        findings.append(
            {
                "code": code,
                "severity": severity,
                "message": message,
                "evidence": evidence,
            }
        )

    if reason:
        finding(reason, "warning", "Complete current market valuation is unavailable.")
    positions = []
    for configured in data[c.CONF_VALORS]:
        symbol = configured[c.VALOR_SYMBOL]
        valor = current.valors.get(symbol) if current is not None else None
        valid = bool(available and valor is not None and valor.available)
        if valid:
            valid = (
                all(
                    isfinite(value) and value >= 0
                    for value in (
                        valor.amount,
                        valor.quote.price,
                        valor.fx_rate,
                        valor.value,
                    )
                )
                and valor.quote.price > 0
                and valor.fx_rate > 0
            )
        evaluated = position_valuation(
            data,
            symbol,
            today=today,
            valor=valor if valid else None,
            inflation=current.inflation if current is not None else None,
        )
        share = (
            evaluated.nominal.value / total * 100
            if evaluated.nominal.value is not None and total and total > 0
            else None
        )
        target = configured.get(c.VALOR_TARGET_SHARE)
        deviation = share - target if share is not None and target is not None else None
        positions.append(
            {
                "symbol": symbol,
                "nominal": _performance(evaluated.nominal),
                "real": _performance(evaluated.real),
                "tracked": _performance(evaluated.tracked),
                "cost_complete": evaluated.cost_complete,
                "target_share": target,
                "share": share,
                "deviation": deviation,
            }
        )
        if not evaluated.cost_complete:
            finding(
                "incomplete_opening_cost",
                "warning",
                (
                    "The whole position's cost and profit are unavailable because "
                    "opening purchases are not fully documented."
                ),
                symbol=symbol,
            )
        if deviation is not None and abs(deviation) >= 5:
            finding(
                "allocation_deviation",
                "info",
                (
                    "The current share differs from the configured target by at least "
                    "five percentage points."
                ),
                symbol=symbol,
                share=share,
                target=target,
                deviation=deviation,
                threshold=5,
            )
        if (
            valid
            and (previous := valor.quote.previous_close)
            and isfinite(previous)
            and previous > 0
        ):
            change = (valor.quote.price / previous - 1) * 100
            if abs(change) >= 20:
                finding(
                    "large_quote_change",
                    "warning",
                    (
                        "The quote differs from its previous close by at least 20%; "
                        "verify the price and possible corporate actions."
                    ),
                    symbol=symbol,
                    price=valor.quote.price,
                    previous_close=previous,
                    change_pct=change,
                    threshold=20,
                )
    conflicts = opening_balance_conflicts(data)
    for conflict in conflicts:
        finding(
            "opening_units_conflict",
            "warning",
            "Documented opening purchases exceed configured opening units.",
            **conflict,
        )
    deficits = [
        (day, amount)
        for day, amount in cash_timeline(data).items()
        if day <= today and amount < -1e-7
    ]
    if deficits:
        first, amount = min(deficits)
        finding(
            "historical_cash_deficit",
            "warning",
            (
                "The recorded cash history contains an unfunded balance; check the "
                "missing funding history."
            ),
            first_date=first.isoformat(),
            first_balance=amount,
            lowest_balance=min(value for _, value in deficits),
        )
    lots = all_lots(data, through=today)
    estimated = [lot[c.LOT_ID] for lot in lots if lot[c.LOT_ESTIMATED]]
    if estimated:
        finding(
            "estimated_purchases",
            "info",
            "Some purchases use estimated historical prices or quantities.",
            lot_ids=estimated,
        )
    duplicates = defaultdict(list)
    for lot in lots:
        key = (lot[c.LOT_SYMBOL], lot[c.LOT_DATE], lot[c.LOT_AMOUNT], lot[c.LOT_UNITS])
        duplicates[key].append(lot[c.LOT_ID])
    for (symbol, day, amount, units), ids in sorted(duplicates.items()):
        if len(ids) > 1:
            finding(
                "possible_duplicate_purchase",
                "warning",
                (
                    "Multiple purchases have the same symbol, date, amount and units. "
                    "They may be legitimate separate transactions; check their source "
                    "records."
                ),
                symbol=symbol,
                date=day,
                amount=amount,
                units=units,
                lot_ids=ids,
            )
    unassigned = [
        row[c.DIVIDEND_ID]
        for row in dividends_from_data(data)
        if not row.get(c.DIVIDEND_SYMBOL)
        and (row.get(c.DIVIDEND_VALUE_DATE) or row[c.DIVIDEND_BOOKING_DATE])
        <= today.isoformat()
    ]
    if unassigned:
        finding(
            "unassigned_dividends",
            "info",
            (
                "Unassigned dividends count toward wallet cash but cannot be "
                "attributed to a position."
            ),
            dividend_ids=unassigned,
        )
    targets = [row.get(c.VALOR_TARGET_SHARE) for row in data[c.CONF_VALORS]]
    target_sum = sum(value for value in targets if value is not None)
    if not any(value is not None for value in targets):
        finding("targets_missing", "info", "No position target shares are configured.")
    elif target_sum < 100 - c.TARGET_SHARE_SUM_TOLERANCE or any(
        value is None for value in targets
    ):
        finding(
            "partial_targets",
            "info",
            (
                "Configured targets do not fully specify the portfolio; allocation "
                "suggestions preserve the unspecified remainder."
            ),
            target_sum=target_sum,
        )
    if current is not None and current.pending_executions:
        finding(
            "pending_plan_executions",
            "warning",
            "Savings-plan executions are awaiting completion.",
            count=len(current.pending_executions),
        )
    projection = target_projection(data, through=today)
    absolute, percentage = target_deviation(total, projection.value)
    return {
        "schema_version": 1,
        "status": "partial" if reason else "ok",
        "reason": reason,
        "as_of": today.isoformat(),
        "sampled_at": current.sampled_at if current is not None else None,
        "currency": data[c.CONF_BASE_CURRENCY],
        "scope": "current_wallet",
        "facts": {
            "total": total,
            "invested": valuation.nominal.cost,
            "cash": cash_balance(data, through=today),
            "dividends": valuation.dividends,
            "profit": valuation.nominal.profit,
            "performance": valuation.nominal.percentage,
            "money_weighted_return": valuation.nominal.annualized,
            "nominal": _performance(valuation.nominal),
            "real": _performance(valuation.real),
        },
        "positions": positions,
        "findings": findings,
        "plans": [
            {
                "id": plan[c.PLAN_ID],
                "name": plan[c.PLAN_NAME],
                "amount": plan[c.PLAN_AMOUNT],
                "enabled": plan[c.PLAN_ENABLED],
                "first_date": plan[c.PLAN_FIRST_DATE],
                "end_date": plan.get(c.PLAN_END_DATE),
            }
            for plan in data.get(c.CONF_SAVINGS_PLANS, [])
        ],
        "target": {
            "value": projection.value,
            "annual_return": projection.annual_return,
            "absolute_deviation": absolute,
            "percentage_deviation": percentage,
            "unavailable_reason": projection.unavailable_reason,
            "basis": "configured_funding_and_constant_return",
        },
        "period": _period_report(data, history, today=today, month=month),
        "assumptions": [
            (
                "Current profits are lifetime figures; calendar-month figures "
                "appear only in period."
            ),
            "Dividends are internal wallet income, not external investor funding.",
            (
                "Findings are deterministic checks with disclosed evidence and "
                "thresholds, not proven errors."
            ),
            "No external news or market-cause claims are inferred from wallet data.",
        ],
    }
