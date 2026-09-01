"""Official consumer-price data and purchasing-power calculations."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from math import isfinite
from typing import Any

from . import const as c

_DAYS_PER_YEAR = 365.2425


@dataclass(frozen=True)
class InflationSeries:
    """A validated monthly official consumer-price index."""

    source: str
    region: str
    values: dict[str, float]
    fetched_at: str | None = None
    stale: bool = False

    @property
    def months(self) -> tuple[str, ...]:
        return tuple(sorted(self.values))

    @property
    def latest_month(self) -> str | None:
        return self.months[-1] if self.values else None

    def index_for(self, value: date) -> float | None:
        """Return the latest monthly index available on or before a date."""
        months = self.months
        if not months:
            return None
        key = value.strftime("%Y-%m")
        position = bisect_right(months, key) - 1
        return self.values[months[position]] if position >= 0 else None

    def factor(self, start: date, end: date) -> float | None:
        """Return the official price-level factor between two dates."""
        start_index = self.index_for(start)
        end_index = self.index_for(end)
        if start_index is None or end_index is None or start_index <= 0:
            return None
        return end_index / start_index

    def adjust(self, amount: float, start: date, end: date) -> float | None:
        """Express one dated nominal amount in the purchasing power at `end`."""
        factor = self.factor(start, end)
        return float(amount) * factor if factor is not None else None

    def with_stale(self, stale: bool = True) -> InflationSeries:
        return replace(self, stale=stale)

    def as_storage(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "region": self.region,
            "values": dict(self.values),
            "fetched_at": self.fetched_at,
        }

    @classmethod
    def from_storage(cls, raw: Any) -> InflationSeries | None:
        if not isinstance(raw, Mapping):
            return None
        source = raw.get("source")
        region = raw.get("region")
        values = raw.get("values")
        if not isinstance(source, str) or not isinstance(region, str):
            return None
        if not isinstance(values, Mapping):
            return None
        normalized: dict[str, float] = {}
        for month, value in values.items():
            try:
                parsed = float(value)
                date.fromisoformat(f"{month}-01")
            except (TypeError, ValueError):
                return None
            if not isfinite(parsed) or parsed <= 0:
                return None
            normalized[str(month)] = parsed
        if not normalized:
            return None
        fetched = raw.get("fetched_at")
        if fetched is not None and not isinstance(fetched, str):
            return None
        return cls(source, region, normalized, fetched)


def expected_annual_inflation(data: Mapping[str, Any]) -> float:
    """Return the configured future inflation assumption in percent."""
    try:
        value = float(
            data.get(
                c.CONF_EXPECTED_ANNUAL_INFLATION,
                c.DEFAULT_EXPECTED_ANNUAL_INFLATION,
            )
        )
    except (TypeError, ValueError):
        return c.DEFAULT_EXPECTED_ANNUAL_INFLATION
    if (
        not isfinite(value)
        or value < c.MIN_EXPECTED_ANNUAL_INFLATION
        or value > c.MAX_EXPECTED_ANNUAL_INFLATION
    ):
        return c.DEFAULT_EXPECTED_ANNUAL_INFLATION
    return value


def future_inflation_factor(annual_percent: float, start: date, end: date) -> float:
    """Return a geometric price-level factor for a future scenario."""
    annual_factor = 1 + float(annual_percent) / 100
    if annual_factor <= 0:
        raise ValueError("Inflation assumption must be greater than -100%")
    return annual_factor ** ((end - start).days / _DAYS_PER_YEAR)


def purchasing_power(
    amount: float, *, today: date, through: date, annual_percent: float
) -> float:
    """Express a future nominal amount in today's purchasing power."""
    return float(amount) / future_inflation_factor(annual_percent, today, through)


def parse_eurostat_hicp(
    payload: Mapping[str, Any], *, source: str, region: str, fetched_at: str | None
) -> InflationSeries:
    """Parse the filtered Eurostat JSON-stat response defensively."""
    dimensions = payload.get("id")
    sizes = payload.get("size")
    if not isinstance(dimensions, Sequence) or isinstance(dimensions, (str, bytes)):
        raise ValueError("invalid_inflation_data")
    if not isinstance(sizes, Sequence) or len(dimensions) != len(sizes):
        raise ValueError("invalid_inflation_data")
    if "time" not in dimensions or any(
        int(size) != 1
        for dimension, size in zip(dimensions, sizes, strict=True)
        if dimension != "time"
    ):
        raise ValueError("invalid_inflation_data")

    dimension_data = payload.get("dimension")
    if not isinstance(dimension_data, Mapping):
        raise ValueError("invalid_inflation_data")
    time_data = dimension_data.get("time")
    if not isinstance(time_data, Mapping):
        raise ValueError("invalid_inflation_data")
    category = time_data.get("category")
    positions = category.get("index") if isinstance(category, Mapping) else None
    if not isinstance(positions, Mapping):
        raise ValueError("invalid_inflation_data")

    raw_values = payload.get("value")
    if not isinstance(raw_values, (Mapping, Sequence)) or isinstance(
        raw_values, (str, bytes)
    ):
        raise ValueError("invalid_inflation_data")
    values: dict[str, float] = {}
    for month, position in positions.items():
        try:
            date.fromisoformat(f"{month}-01")
            raw = (
                raw_values.get(str(position))
                if isinstance(raw_values, Mapping)
                else raw_values[int(position)]
            )
            number = float(raw)
        except (IndexError, TypeError, ValueError):
            continue
        if isfinite(number) and number > 0:
            values[str(month)] = number
    if not values:
        raise ValueError("invalid_inflation_data")
    return InflationSeries(source, region, values, fetched_at)


def adjusted_flows(
    flows: Sequence[tuple[date, float]],
    *,
    through: date,
    series: InflationSeries,
) -> list[tuple[date, float]] | None:
    """Convert dated cash flows to the purchasing power at `through`."""
    result: list[tuple[date, float]] = []
    for flow_date, amount in flows:
        adjusted = series.adjust(amount, flow_date, through)
        if adjusted is None:
            return None
        result.append((flow_date, adjusted))
    return result


def real_return(nominal_percent: float, price_factor: float) -> float | None:
    """Convert one comparable nominal return to a real return."""
    if price_factor <= 0:
        return None
    return ((1 + nominal_percent / 100) / price_factor - 1) * 100
