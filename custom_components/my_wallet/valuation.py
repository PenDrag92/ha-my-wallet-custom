"""Full-precision performance results shared by sensors and the dashboard.

Whole-position performance requires a documented opening cost. Tracked-lot
performance covers only the recorded purchases and their attributed dividends.
Adapters choose the appropriate scope and round only when publishing values.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from . import const as c
from .contributions import cashflows, invested_total, lots_for_symbol, xirr
from .dividends import attributed_dividend_flows, dividends_from_data
from .inflation import InflationSeries, adjusted_flows

CashFlows = list[tuple[date, float]]


@dataclass(frozen=True)
class Performance:
    cost: float | None
    income: float | None
    value: float | None
    annualized: float | None = None

    @property
    def profit(self) -> float | None:
        if self.cost is None or self.income is None or self.value is None:
            return None
        return self.value + self.income - self.cost

    @property
    def percentage(self) -> float | None:
        profit = self.profit
        return (
            profit / self.cost * 100
            if profit is not None and self.cost and self.cost > 0
            else None
        )


@dataclass(frozen=True)
class LotValuation:
    lot: Mapping[str, Any]
    nominal: Performance
    real: Performance
    income_flows: CashFlows
    real_income_flows: CashFlows | None
    age_days: int


@dataclass(frozen=True)
class PositionValuation:
    nominal: Performance
    real: Performance
    tracked: Performance
    tracked_real: Performance
    lots: list[LotValuation]
    cost_complete: bool
    start_date: str | None


@dataclass(frozen=True)
class WalletValuation:
    nominal: Performance
    real: Performance
    dividends: float
    real_dividends: float | None


def _annualized(flows, value, today):
    if not flows or value is None:
        return None
    result = xirr([*flows, (today, value)])
    return result * 100 if result is not None else None


def _adjust(flows, today, inflation):
    return (
        adjusted_flows(flows, through=today, series=inflation)
        if inflation is not None and flows is not None
        else None
    )


def _sum(flows):
    return sum(amount for _, amount in flows) if flows is not None else None


def dividend_flows(data, *, today, symbol=None):
    return [
        (effective, float(item[c.DIVIDEND_AMOUNT]))
        for item in dividends_from_data(data)
        if (symbol is None or item.get(c.DIVIDEND_SYMBOL) == symbol)
        and (
            effective := date.fromisoformat(
                item.get(c.DIVIDEND_VALUE_DATE) or item[c.DIVIDEND_BOOKING_DATE]
            )
        )
        <= today
    ]


def wallet_valuation(data, current, *, today: date, available=True) -> WalletValuation:
    """Dividends stay internal to the wallet, so they are not external returns."""
    value = current.total if current is not None and available else None
    inflation = current.inflation if current is not None else None
    flows = cashflows(data, through=today)
    real_flows = _adjust(flows, today, inflation)
    real_capital = -_sum(real_flows) if real_flows is not None else None
    income = dividend_flows(data, today=today)
    return WalletValuation(
        nominal=Performance(
            invested_total(data, through=today),
            0.0,
            value,
            _annualized(flows, value if value and value > 0 else None, today),
        ),
        real=Performance(
            real_capital,
            0.0,
            value,
            _annualized(real_flows, value if value and value > 0 else None, today),
        ),
        dividends=_sum(income),
        real_dividends=_sum(_adjust(income, today, inflation)),
    )


def position_valuation(
    data,
    symbol: str,
    *,
    today: date,
    valor=None,
    inflation: InflationSeries | None = None,
) -> PositionValuation:
    """Evaluate both the full holding and the explicitly documented purchases."""
    opening = next(
        (
            float(row[c.VALOR_AMOUNT])
            for row in data.get(c.CONF_VALORS, [])
            if row[c.VALOR_SYMBOL] == symbol
        ),
        0.0,
    )
    base_price = (
        valor.quote.price * valor.fx_rate
        if valor is not None and valor.available
        else None
    )
    value = valor.value if valor is not None else None
    flows_by_lot = attributed_dividend_flows(
        data, symbol=symbol, opening_units=opening, through=today
    )
    lots = []
    for lot in lots_for_symbol(data, symbol, through=today):
        day = date.fromisoformat(lot[c.LOT_DATE])
        cost = float(lot[c.LOT_AMOUNT])
        lot_value = (
            float(lot[c.LOT_UNITS]) * base_price if base_price is not None else None
        )
        flows = flows_by_lot[lot[c.LOT_ID]]
        real_flows = _adjust(flows, today, inflation)
        real_cost = (
            inflation.adjust(cost, day, today) if inflation is not None else None
        )
        lots.append(
            LotValuation(
                lot=lot,
                nominal=Performance(
                    cost,
                    _sum(flows),
                    lot_value,
                    _annualized([(day, -cost), *flows], lot_value, today),
                ),
                real=Performance(
                    real_cost,
                    _sum(real_flows),
                    lot_value,
                    _annualized([(day, -real_cost), *real_flows], lot_value, today)
                    if real_cost is not None and real_flows is not None
                    else None,
                ),
                income_flows=flows,
                real_income_flows=real_flows,
                age_days=(today - day).days,
            )
        )
    complete = (
        abs(
            sum(
                item.lot[c.LOT_UNITS]
                for item in lots
                if item.lot[c.LOT_INCLUDED_IN_OPENING]
            )
            - opening
        )
        <= 1e-8
    )
    tracked = _tracked_performance(lots, today=today)
    tracked_real = _tracked_performance(lots, today=today, real=True)
    income = dividend_flows(data, today=today, symbol=symbol)
    real_income = _adjust(income, today, inflation)
    # An empty documented holding has zero cost; absent inflation remains unknown.
    real_cost = tracked_real.cost if lots else (0.0 if inflation is not None else None)
    return PositionValuation(
        nominal=Performance(tracked.cost if complete else None, _sum(income), value),
        real=Performance(real_cost if complete else None, _sum(real_income), value),
        tracked=tracked,
        tracked_real=tracked_real,
        lots=lots,
        cost_complete=complete,
        start_date=min(item.lot[c.LOT_DATE] for item in lots)
        if lots and complete
        else None,
    )


def _tracked_performance(lots, *, today, real=False):
    metrics = [item.real if real else item.nominal for item in lots]
    cost = (
        sum(item.cost for item in metrics)
        if all(item.cost is not None for item in metrics)
        else None
    )
    income = (
        sum(item.income for item in metrics)
        if all(item.income is not None for item in metrics)
        else None
    )
    value = (
        sum(item.value for item in metrics)
        if all(item.value is not None for item in metrics)
        else None
    )
    flows = []
    if cost is not None and income is not None:
        for item, metric in zip(lots, metrics, strict=True):
            flows.append((date.fromisoformat(item.lot[c.LOT_DATE]), -metric.cost))
            flows.extend(item.real_income_flows if real else item.income_flows)
    return Performance(cost, income, value, _annualized(flows, value, today))
