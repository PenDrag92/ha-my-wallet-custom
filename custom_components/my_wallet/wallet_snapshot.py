"""Reconcile saved holdings and cached market data for every read adapter."""

from __future__ import annotations

from dataclasses import replace
from math import isfinite

from . import const as c
from .corrections import position_units
from .dividends import cash_balance
from .models import ValorData


def wallet_with_saved_units(data, current, *, today):
    """Value saved holdings using cached quotes while a reload is pending.

    Neither the config-entry snapshot nor the coordinator result is mutated.
    Quotes retain their original sampling time; this is not a market refresh.
    """
    if current is None:
        return None
    valors = {}
    for valor in data[c.CONF_VALORS]:
        symbol = valor[c.VALOR_SYMBOL]
        previous = current.valors.get(symbol) or ValorData(symbol, 0, 0)
        valors[symbol] = replace(
            previous,
            amount=position_units(data, symbol, today),
            opening_amount=float(valor[c.VALOR_AMOUNT]),
            target_share=valor.get(c.VALOR_TARGET_SHARE),
        )
    return replace(
        current, valors=valors, cash_balance=cash_balance(data, through=today)
    )


def valuation_unavailable_reason(current, *, available=True):
    """Do not turn failed, incomplete or invalid market data into a total."""
    if not available:
        return "refresh_failed"
    if current is None or not current.all_available:
        return "missing_market_data"
    values = [current.cash_balance]
    for valor in current.valors.values():
        values.extend((valor.amount, valor.quote.price, valor.fx_rate, valor.value))
        if valor.quote.price <= 0 or valor.fx_rate <= 0 or valor.amount < 0:
            return "invalid_market_data"
    if any(value is None or not isfinite(value) for value in values):
        return "invalid_market_data"
    if current.total is None or not isfinite(current.total) or current.total < 0:
        return "invalid_market_data"
    return None
