"""Sensor platform for wallet value, savings plans, and performance."""

from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import MyWalletConfigEntry
from .const import (
    ALLOCATION_SYMBOL,
    ALLOCATION_VALUE,
    ATTR_AMOUNT,
    ATTR_ANNUALIZED_PERFORMANCE_PCT,
    ATTR_CASH_BALANCE,
    ATTR_CONTRIBUTION_COUNT,
    ATTR_CONTRIBUTIONS,
    ATTR_DAY_CHANGE,
    ATTR_DAY_CHANGE_PCT,
    ATTR_DIVIDEND_COUNT,
    ATTR_DIVIDEND_TOTAL,
    ATTR_DIVIDENDS,
    ATTR_FIRST_CONTRIBUTION_DATE,
    ATTR_FX_RATE,
    ATTR_INVESTED,
    ATTR_LAST_CONTRIBUTION_DATE,
    ATTR_LOTS,
    ATTR_NEXT_EXECUTION_DATE,
    ATTR_OPENING_UNITS,
    ATTR_PENDING_EXECUTIONS,
    ATTR_PERFORMANCE_PCT,
    ATTR_PREVIOUS_CLOSE,
    ATTR_PROFIT,
    ATTR_QUOTE_CURRENCY,
    ATTR_REBALANCE_AMOUNT,
    ATTR_SAVINGS_PLANS,
    ATTR_SECURITIES_TOTAL,
    ATTR_SHARE,
    ATTR_SHARE_DEVIATION,
    ATTR_SHORT_NAME,
    ATTR_SYMBOL,
    ATTR_TARGET_SHARE,
    ATTR_TOTAL,
    ATTR_TRACKED_INVESTED,
    ATTR_TRACKED_UNITS,
    ATTR_TRACKED_VALUE,
    ATTR_UNIT_PRICE,
    ATTR_VALUE,
    CONF_SAVINGS_PLANS,
    CONF_VALORS,
    CONF_WALLET_NAME,
    CONTRIBUTION_AMOUNT,
    CONTRIBUTION_DATE,
    CONTRIBUTION_LOTS,
    CONTRIBUTION_SCHEDULED_DATE,
    CONTRIBUTION_SOURCE,
    DIVIDEND_AMOUNT,
    DIVIDEND_BOOKING_DATE,
    DIVIDEND_NOTE,
    DIVIDEND_SYMBOL,
    DIVIDEND_VALUE_DATE,
    DOMAIN,
    LOT_AMOUNT,
    LOT_DATE,
    LOT_ESTIMATED,
    LOT_FX_RATE,
    LOT_ID,
    LOT_INCLUDED_IN_OPENING,
    LOT_QUOTE_CURRENCY,
    LOT_UNIT_PRICE,
    LOT_UNITS,
    PLAN_ALLOCATION_MODE,
    PLAN_ALLOCATIONS,
    PLAN_AMOUNT,
    PLAN_ENABLED,
    PLAN_END_DATE,
    PLAN_FIRST_DATE,
    PLAN_ID,
    PLAN_NAME,
    PLAN_OPENING_CUTOFF_DATE,
    PLAN_SKIPPED_PERIODS,
    PLAN_USE_CASH_BALANCE,
    SERVICE_REFRESH,
    VALOR_SYMBOL,
)
from .contributions import (
    contributions_from_data,
    invested_total,
    lot_metrics,
    lots_for_symbol,
    money_weighted_return,
    xirr,
)
from .coordinator import WalletCoordinator
from .dividends import (
    attributed_dividend_flows,
    dividend_total,
    dividends_from_data,
)
from .models import ValorData, WalletData
from .plans import next_due_date, normalize_plan

_REFRESH_SCHEMA: dict[str, Any] = {}


def _invested_amount(entry: ConfigEntry) -> float | None:
    return invested_total(entry.data, through=dt_util.now().date())


def _contribution_attributes(entry: ConfigEntry) -> dict[str, Any]:
    contributions = contributions_from_data(entry.data)
    dates = [
        item[CONTRIBUTION_DATE]
        for item in contributions
        if item[CONTRIBUTION_DATE] is not None
    ]
    return {
        ATTR_CONTRIBUTION_COUNT: len(contributions),
        ATTR_CONTRIBUTIONS: [
            {
                CONTRIBUTION_DATE: item[CONTRIBUTION_DATE],
                CONTRIBUTION_SCHEDULED_DATE: item.get(CONTRIBUTION_SCHEDULED_DATE),
                CONTRIBUTION_AMOUNT: round(item[CONTRIBUTION_AMOUNT], 2),
                CONTRIBUTION_SOURCE: item[CONTRIBUTION_SOURCE],
                "lot_count": len(item[CONTRIBUTION_LOTS]),
            }
            for item in contributions
        ],
        ATTR_FIRST_CONTRIBUTION_DATE: min(dates) if dates else None,
        ATTR_LAST_CONTRIBUTION_DATE: max(dates) if dates else None,
    }


def _dividend_attributes(entry: ConfigEntry) -> dict[str, Any]:
    dividends = dividends_from_data(entry.data)
    return {
        ATTR_DIVIDEND_COUNT: len(dividends),
        ATTR_DIVIDEND_TOTAL: round(
            dividend_total(entry.data, through=dt_util.now().date()), 2
        ),
        ATTR_DIVIDENDS: [
            {
                DIVIDEND_BOOKING_DATE: item[DIVIDEND_BOOKING_DATE],
                DIVIDEND_VALUE_DATE: item.get(DIVIDEND_VALUE_DATE),
                DIVIDEND_AMOUNT: round(item[DIVIDEND_AMOUNT], 2),
                DIVIDEND_SYMBOL: item.get(DIVIDEND_SYMBOL),
                DIVIDEND_NOTE: item.get(DIVIDEND_NOTE),
            }
            for item in dividends
        ],
    }


def _symbol_dividend_total(entry: ConfigEntry, symbol: str) -> float:
    today = dt_util.now().date()
    return sum(
        float(item[DIVIDEND_AMOUNT])
        for item in dividends_from_data(entry.data)
        if item.get(DIVIDEND_SYMBOL) == symbol
        and date.fromisoformat(
            item.get(DIVIDEND_VALUE_DATE) or item[DIVIDEND_BOOKING_DATE]
        )
        <= today
    )


def _share(valor: ValorData, total: float | None) -> float | None:
    if total is None or valor.value is None or total <= 0:
        return None
    return round(valor.value / total * 100, 2)


def _lot_rows(
    entry: ConfigEntry,
    valor: ValorData | None,
    as_of: date,
) -> list[dict[str, Any]]:
    """Return display-ready performance rows for one symbol."""
    if valor is None or not valor.available:
        return []
    current_base_price = valor.quote.price * valor.fx_rate
    rows: list[dict[str, Any]] = []
    lots = lots_for_symbol(entry.data, valor.symbol, through=as_of)
    dividend_flows = attributed_dividend_flows(
        entry.data,
        symbol=valor.symbol,
        opening_units=valor.opening_amount,
        through=as_of,
    )

    for lot in lots:
        income_flows = dividend_flows[lot[LOT_ID]]
        income = sum(amount for _, amount in income_flows)
        metrics = lot_metrics(lot, current_base_price, as_of, income)
        annualized = xirr(
            [
                (date.fromisoformat(lot[LOT_DATE]), -float(lot[LOT_AMOUNT])),
                *income_flows,
                (as_of, float(metrics["current_value"])),
            ]
        )
        rows.append(
            {
                LOT_DATE: lot[LOT_DATE],
                LOT_AMOUNT: round(lot[LOT_AMOUNT], 2),
                LOT_UNITS: round(lot[LOT_UNITS], 6),
                LOT_UNIT_PRICE: round(lot[LOT_UNIT_PRICE], 6),
                LOT_QUOTE_CURRENCY: lot[LOT_QUOTE_CURRENCY],
                LOT_FX_RATE: round(lot[LOT_FX_RATE], 6),
                "current_value": round(metrics["current_value"], 2),
                ATTR_DIVIDEND_TOTAL: round(income, 4),
                ATTR_PROFIT: round(metrics["profit"], 2),
                ATTR_PERFORMANCE_PCT: round(metrics["performance_pct"], 2),
                ATTR_ANNUALIZED_PERFORMANCE_PCT: (
                    round(annualized * 100, 2) if annualized is not None else None
                ),
                "age_days": int(metrics["age_days"]),
                LOT_INCLUDED_IN_OPENING: lot[LOT_INCLUDED_IN_OPENING],
                LOT_ESTIMATED: lot[LOT_ESTIMATED],
                "_raw_amount": float(lot[LOT_AMOUNT]),
                "_raw_value": float(metrics["current_value"]),
                "_raw_income": income,
                "_income_flows": income_flows,
            }
        )
    return sorted(rows, key=lambda item: item[LOT_DATE])


def _tracked_totals(
    rows: list[dict[str, Any]], dividends: float = 0.0
) -> tuple[float, float, float]:
    invested = sum(row.get("_raw_amount", row[LOT_AMOUNT]) for row in rows)
    value = sum(row.get("_raw_value", row["current_value"]) for row in rows)
    return invested, value, value + dividends - invested


def _tracked_dividend_total(rows: list[dict[str, Any]]) -> float:
    """Return dividends attributed to the tracked lots in display rows."""
    return sum(float(row.get("_raw_income", row[ATTR_DIVIDEND_TOTAL])) for row in rows)


def _public_lot_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hide internal full-precision fields from Home Assistant attributes."""
    return [
        {key: value for key, value in row.items() if not key.startswith("_")}
        for row in rows
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyWalletConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create all sensors for a wallet."""
    coordinator: WalletCoordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        WalletTotalSensor(coordinator, entry),
        WalletInvestedSensor(coordinator, entry),
        WalletProfitSensor(coordinator, entry),
        WalletProfitPctSensor(coordinator, entry),
        WalletMoneyWeightedReturnSensor(coordinator, entry),
        WalletCashBalanceSensor(coordinator, entry),
        WalletDividendSensor(coordinator, entry),
        WalletNextExecutionSensor(coordinator, entry),
    ]
    for valor in coordinator.valors:
        symbol = valor[VALOR_SYMBOL]
        entities.extend(
            [
                ValorSensor(coordinator, entry, symbol),
                ValorDeviationSensor(coordinator, entry, symbol),
                ValorProfitSensor(coordinator, entry, symbol),
                ValorPerformanceSensor(coordinator, entry, symbol),
                ValorAnnualizedPerformanceSensor(coordinator, entry, symbol),
            ]
        )
    async_add_entities(entities)
    _cleanup_orphaned_entities(hass, entry)

    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        platform = entity_platform.async_get_current_platform()
        platform.async_register_entity_service(
            SERVICE_REFRESH, _REFRESH_SCHEMA, "async_refresh_wallet"
        )


def _cleanup_orphaned_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    registry = er.async_get(hass)
    valid_symbols = {valor[VALOR_SYMBOL] for valor in entry.data.get(CONF_VALORS, [])}
    valid_unique_ids = {
        f"{entry.entry_id}_{symbol}{suffix}"
        for symbol in valid_symbols
        for suffix in (
            "",
            "_deviation",
            "_profit",
            "_performance",
            "_annualized_performance",
        )
    }
    valid_unique_ids.update(
        {
            f"{entry.entry_id}_total",
            f"{entry.entry_id}_invested",
            f"{entry.entry_id}_profit",
            f"{entry.entry_id}_profit_pct",
            f"{entry.entry_id}_money_weighted_return",
            f"{entry.entry_id}_cash_balance",
            f"{entry.entry_id}_dividends",
            f"{entry.entry_id}_next_execution",
        }
    )
    for entity_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity_entry.unique_id not in valid_unique_ids:
            registry.async_remove(entity_entry.entity_id)


class WalletBaseSensor(CoordinatorEntity[WalletCoordinator], SensorEntity):
    """Common base for monetary wallet sensors."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator: WalletCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_native_unit_of_measurement = coordinator.base_currency

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.data.get(CONF_WALLET_NAME, self._entry.title),
            manufacturer="My Wallet",
            model="Investment wallet",
        )

    async def async_refresh_wallet(self) -> None:
        await self.coordinator.async_request_refresh()


class ValorSensor(WalletBaseSensor):
    """Current total value of one market instrument."""

    _attr_icon = "mdi:chart-box-outline"

    def __init__(
        self, coordinator: WalletCoordinator, entry: ConfigEntry, symbol: str
    ) -> None:
        super().__init__(coordinator, entry)
        self._symbol = symbol
        self._attr_unique_id = f"{entry.entry_id}_{symbol}"
        self._attr_translation_key = "valor"
        self._attr_translation_placeholders = {"symbol": symbol}

    @property
    def data(self) -> WalletData:
        return self.coordinator.data

    @property
    def native_value(self) -> float | None:
        valor = self.data.valors.get(self._symbol)
        return round(valor.value, 2) if valor and valor.value is not None else None

    @property
    def available(self) -> bool:
        valor = self.data.valors.get(self._symbol)
        return super().available and valor is not None and valor.available

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        valor = self.data.valors.get(self._symbol)
        if valor is None or valor.quote is None:
            return {ATTR_SYMBOL: self._symbol}
        quote = valor.quote
        rows = _lot_rows(self._entry, valor, dt_util.now().date())
        attributes: dict[str, Any] = {
            ATTR_SYMBOL: self._symbol,
            ATTR_AMOUNT: valor.amount,
            ATTR_OPENING_UNITS: valor.opening_amount,
            ATTR_TRACKED_UNITS: round(valor.amount - valor.opening_amount, 6),
            ATTR_UNIT_PRICE: quote.price,
            ATTR_QUOTE_CURRENCY: quote.currency,
            ATTR_FX_RATE: valor.fx_rate,
            ATTR_PREVIOUS_CLOSE: quote.previous_close,
            ATTR_DAY_CHANGE: quote.day_change,
            ATTR_DAY_CHANGE_PCT: quote.day_change_pct,
            "tracked_lot_count": len(rows),
            ATTR_DIVIDEND_TOTAL: round(
                _symbol_dividend_total(self._entry, self._symbol), 2
            ),
        }
        if quote.short_name:
            attributes[ATTR_SHORT_NAME] = quote.short_name
        share = _share(valor, self.data.total)
        if share is not None:
            attributes[ATTR_SHARE] = share
            if valor.has_target:
                attributes[ATTR_SHARE_DEVIATION] = round(share - valor.target_share, 2)
                attributes[ATTR_REBALANCE_AMOUNT] = round(
                    self.data.total * valor.target_share / 100 - valor.value, 2
                )
        if valor.has_target:
            attributes[ATTR_TARGET_SHARE] = valor.target_share
        if valor.error:
            attributes["error"] = valor.error
        return attributes


class ValorDeviationSensor(WalletBaseSensor):
    """Actual share minus target share, in percentage points."""

    _attr_icon = "mdi:target-variant"

    def __init__(
        self, coordinator: WalletCoordinator, entry: ConfigEntry, symbol: str
    ) -> None:
        super().__init__(coordinator, entry)
        self._symbol = symbol
        self._attr_unique_id = f"{entry.entry_id}_{symbol}_deviation"
        self._attr_translation_key = "valor_deviation"
        self._attr_translation_placeholders = {"symbol": symbol}
        self._attr_device_class = None
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "%"

    @property
    def native_value(self) -> float | None:
        valor = self.coordinator.data.valors.get(self._symbol)
        total = self.coordinator.data.total
        if not valor or not valor.has_target or valor.value is None or not total:
            return None
        return round(valor.value / total * 100 - valor.target_share, 2)

    @property
    def available(self) -> bool:
        valor = self.coordinator.data.valors.get(self._symbol)
        return bool(
            super().available
            and valor
            and valor.available
            and valor.has_target
            and self.coordinator.data.total
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        valor = self.coordinator.data.valors.get(self._symbol)
        total = self.coordinator.data.total
        attributes: dict[str, Any] = {ATTR_SYMBOL: self._symbol}
        if not valor or not valor.has_target:
            return attributes
        attributes[ATTR_TARGET_SHARE] = valor.target_share
        if valor.value is not None and total:
            attributes[ATTR_SHARE] = _share(valor, total)
            attributes[ATTR_VALUE] = round(valor.value, 2)
            attributes[ATTR_REBALANCE_AMOUNT] = round(
                total * valor.target_share / 100 - valor.value, 2
            )
        return attributes


class ValorTrackedBaseSensor(WalletBaseSensor):
    """Base for performance sensors backed by tracked lots."""

    def __init__(
        self, coordinator: WalletCoordinator, entry: ConfigEntry, symbol: str
    ) -> None:
        super().__init__(coordinator, entry)
        self._symbol = symbol

    @property
    def _rows(self) -> list[dict[str, Any]]:
        return _lot_rows(
            self._entry,
            self.coordinator.data.valors.get(self._symbol),
            dt_util.now().date(),
        )

    @property
    def available(self) -> bool:
        return super().available and bool(self._rows)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        rows = self._rows
        dividends = _tracked_dividend_total(rows)
        invested, value, profit = _tracked_totals(rows, dividends)
        return {
            ATTR_SYMBOL: self._symbol,
            ATTR_TRACKED_INVESTED: round(invested, 2),
            ATTR_TRACKED_VALUE: round(value, 2),
            ATTR_PROFIT: round(profit, 2),
            ATTR_DIVIDEND_TOTAL: round(dividends, 2),
            ATTR_LOTS: _public_lot_rows(rows),
        }


class ValorProfitSensor(ValorTrackedBaseSensor):
    _attr_icon = "mdi:cash-plus"

    def __init__(
        self, coordinator: WalletCoordinator, entry: ConfigEntry, symbol: str
    ) -> None:
        super().__init__(coordinator, entry, symbol)
        self._attr_unique_id = f"{entry.entry_id}_{symbol}_profit"
        self._attr_translation_key = "valor_profit"
        self._attr_translation_placeholders = {"symbol": symbol}

    @property
    def native_value(self) -> float | None:
        if not self._rows:
            return None
        rows = self._rows
        return round(_tracked_totals(rows, _tracked_dividend_total(rows))[2], 2)


class ValorPerformanceSensor(ValorTrackedBaseSensor):
    _attr_icon = "mdi:percent-outline"

    def __init__(
        self, coordinator: WalletCoordinator, entry: ConfigEntry, symbol: str
    ) -> None:
        super().__init__(coordinator, entry, symbol)
        self._attr_unique_id = f"{entry.entry_id}_{symbol}_performance"
        self._attr_translation_key = "valor_performance"
        self._attr_translation_placeholders = {"symbol": symbol}
        self._attr_device_class = None
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "%"

    @property
    def native_value(self) -> float | None:
        rows = self._rows
        invested, _, profit = _tracked_totals(rows, _tracked_dividend_total(rows))
        return round(profit / invested * 100, 2) if invested else None


class ValorAnnualizedPerformanceSensor(ValorTrackedBaseSensor):
    _attr_icon = "mdi:chart-timeline-variant-shimmer"

    def __init__(
        self, coordinator: WalletCoordinator, entry: ConfigEntry, symbol: str
    ) -> None:
        super().__init__(coordinator, entry, symbol)
        self._attr_unique_id = f"{entry.entry_id}_{symbol}_annualized_performance"
        self._attr_translation_key = "valor_annualized_performance"
        self._attr_translation_placeholders = {"symbol": symbol}
        self._attr_device_class = None
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "%"

    @property
    def native_value(self) -> float | None:
        rows = self._rows
        if not rows:
            return None
        today = dt_util.now().date()
        flows = [
            (date.fromisoformat(row[LOT_DATE]), -float(row["_raw_amount"]))
            for row in rows
        ]
        flows.extend(flow for row in rows for flow in row["_income_flows"])
        current_value = sum(float(row["_raw_value"]) for row in rows)
        result = xirr([*flows, (today, current_value)])
        return round(result * 100, 2) if result is not None else None


class WalletTotalSensor(WalletBaseSensor):
    _attr_icon = "mdi:wallet-outline"

    def __init__(self, coordinator: WalletCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_total"
        self._attr_translation_key = "wallet_total"

    @property
    def native_value(self) -> float | None:
        total = self.coordinator.data.total
        return round(total, 2) if total is not None else None

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.total is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {
            ATTR_SECURITIES_TOTAL: data.securities_total,
            ATTR_CASH_BALANCE: data.cash_balance,
            "valors": {
                symbol: {
                    "amount": valor.amount,
                    ATTR_OPENING_UNITS: valor.opening_amount,
                    ATTR_TRACKED_UNITS: round(valor.amount - valor.opening_amount, 6),
                    "value": valor.value,
                    "unit_price": valor.quote.price if valor.quote else None,
                    "quote_currency": valor.quote.currency if valor.quote else None,
                    "fx_rate": valor.fx_rate,
                    "share": _share(valor, data.total),
                    "target_share": valor.target_share,
                }
                for symbol, valor in data.valors.items()
            },
            "unavailable_valors": sorted(
                symbol for symbol, valor in data.valors.items() if not valor.available
            ),
        }


class WalletInvestedSensor(WalletBaseSensor):
    _attr_icon = "mdi:cash-lock"

    def __init__(self, coordinator: WalletCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_invested"
        self._attr_translation_key = "wallet_invested"

    @property
    def native_value(self) -> float | None:
        return _invested_amount(self._entry)

    @property
    def available(self) -> bool:
        return _invested_amount(self._entry) is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return _contribution_attributes(self._entry)


class WalletProfitSensor(WalletBaseSensor):
    _attr_icon = "mdi:chart-line"

    def __init__(self, coordinator: WalletCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_profit"
        self._attr_translation_key = "wallet_profit"

    @property
    def native_value(self) -> float | None:
        invested = _invested_amount(self._entry)
        total = self.coordinator.data.total
        return (
            round(total - invested, 2)
            if invested is not None and total is not None
            else None
        )

    @property
    def available(self) -> bool:
        return bool(
            super().available
            and _invested_amount(self._entry) is not None
            and self.coordinator.data.total is not None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            ATTR_INVESTED: _invested_amount(self._entry),
            ATTR_TOTAL: self.coordinator.data.total,
            ATTR_SECURITIES_TOTAL: self.coordinator.data.securities_total,
            ATTR_CASH_BALANCE: self.coordinator.data.cash_balance,
            ATTR_DIVIDEND_TOTAL: round(
                dividend_total(self._entry.data, through=dt_util.now().date()), 2
            ),
            **_contribution_attributes(self._entry),
        }


class WalletProfitPctSensor(WalletBaseSensor):
    _attr_icon = "mdi:percent"

    def __init__(self, coordinator: WalletCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_profit_pct"
        self._attr_translation_key = "wallet_profit_pct"
        self._attr_device_class = None
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "%"

    @property
    def native_value(self) -> float | None:
        invested = _invested_amount(self._entry)
        total = self.coordinator.data.total
        return (
            round((total - invested) / invested * 100, 2)
            if invested and total is not None
            else None
        )

    @property
    def available(self) -> bool:
        return bool(
            super().available
            and _invested_amount(self._entry)
            and self.coordinator.data.total is not None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            ATTR_INVESTED: _invested_amount(self._entry),
            ATTR_TOTAL: self.coordinator.data.total,
            ATTR_SECURITIES_TOTAL: self.coordinator.data.securities_total,
            ATTR_CASH_BALANCE: self.coordinator.data.cash_balance,
            ATTR_DIVIDEND_TOTAL: round(
                dividend_total(self._entry.data, through=dt_util.now().date()), 2
            ),
            **_contribution_attributes(self._entry),
        }


class WalletMoneyWeightedReturnSensor(WalletBaseSensor):
    """Annual XIRR that accounts for the timing of every contribution."""

    _attr_icon = "mdi:finance"

    def __init__(self, coordinator: WalletCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_money_weighted_return"
        self._attr_translation_key = "wallet_money_weighted_return"
        self._attr_device_class = None
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "%"

    @property
    def native_value(self) -> float | None:
        total = self.coordinator.data.total
        if total is None:
            return None
        result = money_weighted_return(self._entry.data, total, dt_util.now().date())
        return round(result, 2) if result is not None else None

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            ATTR_INVESTED: _invested_amount(self._entry),
            ATTR_TOTAL: self.coordinator.data.total,
            "method": "XIRR",
            ATTR_CASH_BALANCE: self.coordinator.data.cash_balance,
            ATTR_DIVIDEND_TOTAL: round(
                dividend_total(self._entry.data, through=dt_util.now().date()), 2
            ),
        }


class WalletCashBalanceSensor(WalletBaseSensor):
    """Cash awaiting investment on the broker settlement account."""

    _attr_icon = "mdi:cash-multiple"

    def __init__(self, coordinator: WalletCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_cash_balance"
        self._attr_translation_key = "wallet_cash_balance"

    @property
    def native_value(self) -> float:
        return round(self.coordinator.data.cash_balance, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            ATTR_DIVIDEND_TOTAL: round(
                dividend_total(self._entry.data, through=dt_util.now().date()), 2
            ),
            **_contribution_attributes(self._entry),
        }


class WalletDividendSensor(WalletBaseSensor):
    """Cumulative net dividends credited by the broker."""

    _attr_icon = "mdi:cash-plus"

    def __init__(self, coordinator: WalletCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_dividends"
        self._attr_translation_key = "wallet_dividends"

    @property
    def native_value(self) -> float:
        return round(dividend_total(self._entry.data, through=dt_util.now().date()), 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return _dividend_attributes(self._entry)


class WalletNextExecutionSensor(CoordinatorEntity[WalletCoordinator], SensorEntity):
    """Next or currently pending savings-plan execution date."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.DATE
    _attr_icon = "mdi:calendar-sync"

    def __init__(self, coordinator: WalletCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_next_execution"
        self._attr_translation_key = "wallet_next_execution"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.data.get(CONF_WALLET_NAME, self._entry.title),
            manufacturer="My Wallet",
            model="Investment wallet",
        )

    @property
    def native_value(self) -> date | None:
        pending = self.coordinator.data.pending_executions
        if pending:
            return min(date.fromisoformat(item["scheduled_date"]) for item in pending)
        today = dt_util.now().date()
        dates = [
            next_due_date(
                normalize_plan(plan), contributions_from_data(self._entry.data), today
            )
            for plan in self._entry.data.get(CONF_SAVINGS_PLANS, [])
        ]
        dates = [item for item in dates if item is not None]
        return min(dates) if dates else None

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        today = dt_util.now().date()
        plans = [
            normalize_plan(plan)
            for plan in self._entry.data.get(CONF_SAVINGS_PLANS, [])
        ]
        return {
            ATTR_NEXT_EXECUTION_DATE: (
                self.native_value.isoformat() if self.native_value else None
            ),
            ATTR_SAVINGS_PLANS: [
                {
                    PLAN_ID: plan[PLAN_ID],
                    PLAN_NAME: plan[PLAN_NAME],
                    PLAN_ENABLED: plan[PLAN_ENABLED],
                    PLAN_FIRST_DATE: plan[PLAN_FIRST_DATE],
                    PLAN_END_DATE: plan[PLAN_END_DATE],
                    PLAN_AMOUNT: plan[PLAN_AMOUNT],
                    PLAN_ALLOCATION_MODE: plan[PLAN_ALLOCATION_MODE],
                    PLAN_ALLOCATIONS: [
                        {
                            ALLOCATION_SYMBOL: allocation[ALLOCATION_SYMBOL],
                            ALLOCATION_VALUE: allocation[ALLOCATION_VALUE],
                        }
                        for allocation in plan[PLAN_ALLOCATIONS]
                    ],
                    PLAN_USE_CASH_BALANCE: plan[PLAN_USE_CASH_BALANCE],
                    PLAN_OPENING_CUTOFF_DATE: plan[PLAN_OPENING_CUTOFF_DATE],
                    PLAN_SKIPPED_PERIODS: plan[PLAN_SKIPPED_PERIODS],
                    ATTR_NEXT_EXECUTION_DATE: (
                        next_date.isoformat()
                        if (
                            next_date := next_due_date(
                                plan,
                                contributions_from_data(self._entry.data),
                                today,
                            )
                        )
                        else None
                    ),
                }
                for plan in plans
            ],
            ATTR_PENDING_EXECUTIONS: self.coordinator.data.pending_executions,
        }

    async def async_refresh_wallet(self) -> None:
        await self.coordinator.async_request_refresh()
