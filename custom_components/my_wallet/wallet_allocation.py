"""Conservative buy-only allocation of a bounded cash budget to stated targets."""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal, InvalidOperation

from . import const as c
from .wallet_snapshot import valuation_unavailable_reason, wallet_with_saved_units

_CENT = Decimal("0.01")


def _money(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as err:
        raise ValueError("invalid_allocation_amount") from err
    if (
        isinstance(value, bool)
        or not amount.is_finite()
        or not 0 <= amount <= 10_000_000_000
        or amount != amount.quantize(_CENT)
    ):
        raise ValueError("invalid_allocation_amount")
    return amount


def _cents(value):
    return int((value * 100).to_integral_value(rounding=ROUND_DOWN))


def allocate_deposit(data, current, *, today, amount, use_cash=False, available=True):
    """Fill stated target shortfalls proportionally, with exact cent budgets.

    Targets use total wallet value after the new deposit. Unspecified and zero
    targets receive no purchases. Partial target sums are never normalized to
    100%; money beyond the stated shortfalls stays in settlement cash.
    """
    deposit = _money(amount)
    if not isinstance(use_cash, bool):
        raise ValueError("invalid_allocation_cash")
    current = wallet_with_saved_units(data, current, today=today)
    reason = valuation_unavailable_reason(current, available=available)
    if reason is None and current.cash_balance < 0:
        reason = "cash_deficit"
    result = {
        "schema_version": 1,
        "status": "unavailable" if reason else "ok",
        "reason": reason,
        "as_of": today.isoformat(),
        "sampled_at": current.sampled_at if current is not None else None,
        "currency": data[c.CONF_BASE_CURRENCY],
        "method": "proportional_target_shortfall",
        "objective": (
            "Reduce absolute currency deviations from the user's targets "
            "without selling or overshooting any target."
        ),
        "new_deposit": float(deposit),
        "use_cash": use_cash,
        "cash_used": None,
        "budget": None,
        "invested": None,
        "unallocated": None,
        "remaining_cash": None,
        "allocations": [],
        "assumptions": [
            (
                "Targets are percentages of the complete wallet value after the "
                "new deposit, including cash."
            ),
            (
                "Existing cash is available only when explicitly selected; the new "
                "deposit is spent first."
            ),
            (
                "Unspecified and zero targets receive no purchases; partial "
                "targets are not rescaled."
            ),
            (
                "Budget is shared proportionally among target shortfalls, rounded "
                "down to cents with deterministic largest remainders."
            ),
            (
                "Any amount beyond the stated target shortfalls remains cash; "
                "prices and fees are not execution quotes."
            ),
        ],
    }
    if reason:
        return result
    targets = {}
    try:
        for row in data[c.CONF_VALORS]:
            raw = row.get(c.VALOR_TARGET_SHARE)
            if raw is None:
                continue
            value = Decimal(str(raw))
            if isinstance(raw, bool) or not value.is_finite() or not 0 <= value <= 100:
                raise ValueError("invalid_targets")
            targets[row[c.VALOR_SYMBOL]] = value
        if sum(targets.values()) > Decimal("100.00001"):
            raise ValueError("invalid_targets")
    except (InvalidOperation, TypeError, ValueError):
        return {**result, "status": "unavailable", "reason": "invalid_targets"}
    if not targets:
        return {**result, "status": "unavailable", "reason": "targets_missing"}
    cash = Decimal(str(current.cash_balance))
    total = sum(Decimal(str(v.value)) for v in current.valors.values()) + cash
    after_total = total + deposit
    budget = _cents(deposit) + (_cents(cash) if use_cash else 0)
    deficits = {
        symbol: max(
            Decimal(0),
            after_total * target / 100 - Decimal(str(current.valors[symbol].value)),
        )
        for symbol, target in targets.items()
        if target > 0
    }
    caps = {symbol: _cents(shortfall) for symbol, shortfall in deficits.items()}
    spend = min(budget, sum(caps.values()))
    purchases = dict.fromkeys(deficits, 0)
    total_shortfall = sum(deficits.values())
    if spend and total_shortfall:
        exact = {
            symbol: Decimal(spend) * shortfall / total_shortfall
            for symbol, shortfall in deficits.items()
        }
        purchases = {
            symbol: min(caps[symbol], int(value)) for symbol, value in exact.items()
        }
        remaining = spend - sum(purchases.values())
        for symbol in sorted(
            exact, key=lambda key: (-(exact[key] - int(exact[key])), key)
        ):
            if remaining and purchases[symbol] < caps[symbol]:
                purchases[symbol] += 1
                remaining -= 1
        # Caps can consume several remainders when some targets are sub-cent.
        # Fill the remaining bounded budget deterministically without overshoot.
        for symbol in sorted(purchases):
            top_up = min(remaining, caps[symbol] - purchases[symbol])
            purchases[symbol] += top_up
            remaining -= top_up
    invested = sum(purchases.values())
    before_error = after_error = Decimal(0)
    rows = []
    for symbol, valor in sorted(current.valors.items()):
        value = Decimal(str(valor.value))
        buy = Decimal(purchases.get(symbol, 0)) / 100
        target = targets.get(symbol)
        if target is not None:
            target_value = after_total * target / 100
            before_error += abs(value - target_value)
            after_error += abs(value + buy - target_value)
        rows.append(
            {
                "symbol": symbol,
                "amount": float(buy),
                "current_value": float(value),
                "after_value": float(value + buy),
                "target_share": float(target) if target is not None else None,
                "before_share": float(value / total * 100) if total > 0 else None,
                "after_share": float((value + buy) / after_total * 100)
                if after_total > 0
                else None,
            }
        )
    result.update(
        {
            "budget": budget / 100,
            "invested": invested / 100,
            "cash_used": max(0, invested - _cents(deposit)) / 100,
            "unallocated": (budget - invested) / 100,
            "cash_before": float(cash),
            "remaining_cash": float(cash + deposit - Decimal(invested) / 100),
            "target_sum": float(sum(targets.values())),
            "before_target_error": float(before_error),
            "after_target_error": float(after_error),
            "total_after_deposit": float(after_total),
            "allocations": rows,
        }
    )
    return result
