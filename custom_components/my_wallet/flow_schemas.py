"""Shared form schemas and input parsing, independent of flow controllers."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from math import isfinite
from typing import Any

import voluptuous as vol
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .const import (
    ALLOCATION_MODE_FIXED,
    ALLOCATION_MODE_PERCENTAGE,
    ALLOCATION_SYMBOL,
    ALLOCATION_VALUE,
    COMMON_CURRENCIES,
    CONF_BASE_CURRENCY,
    CONF_EXPECTED_ANNUAL_INFLATION,
    CONF_EXPECTED_ANNUAL_RETURN,
    CONF_INFLATION_SOURCE,
    CONF_SCAN_INTERVAL,
    CONF_WALLET_NAME,
    CONTRIBUTION_AMOUNT,
    CONTRIBUTION_DATE,
    CONTRIBUTION_NOTE,
    DEFAULT_BASE_CURRENCY,
    DEFAULT_EXPECTED_ANNUAL_INFLATION,
    DEFAULT_EXPECTED_ANNUAL_RETURN,
    DEFAULT_INFLATION_SOURCE,
    DEFAULT_SCAN_INTERVAL,
    DIVIDEND_AMOUNT,
    DIVIDEND_BOOKING_DATE,
    DIVIDEND_NOTE,
    DIVIDEND_SYMBOL,
    DIVIDEND_VALUE_DATE,
    INFLATION_SOURCE_DISABLED,
    INFLATION_SOURCE_EUROSTAT_DE,
    LOT_AMOUNT,
    LOT_DATE,
    LOT_INCLUDED_IN_OPENING,
    LOT_SYMBOL,
    LOT_UNIT_PRICE,
    LOT_UNITS,
    MAX_EXPECTED_ANNUAL_INFLATION,
    MAX_EXPECTED_ANNUAL_RETURN,
    MAX_SCAN_INTERVAL,
    MIN_EXPECTED_ANNUAL_INFLATION,
    MIN_EXPECTED_ANNUAL_RETURN,
    MIN_SCAN_INTERVAL,
    PLAN_ALLOCATION_MODE,
    PLAN_AMOUNT,
    PLAN_ENABLED,
    PLAN_END_DATE,
    PLAN_FIRST_DATE,
    PLAN_NAME,
    PLAN_OPENING_CUTOFF_DATE,
    PLAN_USE_CASH_BALANCE,
    TARGET_SHARE_SUM_TOLERANCE,
    VALOR_AMOUNT,
    VALOR_SYMBOL,
    VALOR_TARGET_SHARE,
)

_CURRENCY_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=COMMON_CURRENCIES,
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)

_AMOUNT_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=0,
        max=10_000_000_000,
        step=0.01,
        mode=selector.NumberSelectorMode.BOX,
    )
)

_CONTRIBUTION_AMOUNT_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=0.01,
        max=10_000_000_000,
        step=0.01,
        mode=selector.NumberSelectorMode.BOX,
    )
)

_UNITS_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=0.000001,
        max=10_000_000_000,
        step="any",
        mode=selector.NumberSelectorMode.BOX,
    )
)

_PRICE_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=0.000001,
        max=10_000_000_000,
        step="any",
        mode=selector.NumberSelectorMode.BOX,
    )
)

_PERCENT_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=0.01,
        max=100,
        step=0.01,
        unit_of_measurement="%",
        mode=selector.NumberSelectorMode.BOX,
    )
)

_DATE_SELECTOR = selector.DateSelector()

_INTERVAL_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=MIN_SCAN_INTERVAL,
        max=MAX_SCAN_INTERVAL,
        step=1,
        unit_of_measurement="min",
        mode=selector.NumberSelectorMode.BOX,
    )
)

_EXPECTED_RETURN_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=MIN_EXPECTED_ANNUAL_RETURN,
        max=MAX_EXPECTED_ANNUAL_RETURN,
        step=0.1,
        unit_of_measurement="%",
        mode=selector.NumberSelectorMode.BOX,
    )
)

_EXPECTED_INFLATION_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=MIN_EXPECTED_ANNUAL_INFLATION,
        max=MAX_EXPECTED_ANNUAL_INFLATION,
        step=0.1,
        unit_of_measurement="%",
        mode=selector.NumberSelectorMode.BOX,
    )
)

_INFLATION_SOURCE_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[INFLATION_SOURCE_EUROSTAT_DE, INFLATION_SOURCE_DISABLED],
        mode=selector.SelectSelectorMode.DROPDOWN,
        translation_key="inflation_source",
    )
)

_TARGET_SHARE_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=0,
        max=100,
        step=0.01,
        unit_of_measurement="%",
        mode=selector.NumberSelectorMode.BOX,
    )
)

_ALLOCATION_MODE_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[ALLOCATION_MODE_PERCENTAGE, ALLOCATION_MODE_FIXED],
        mode=selector.SelectSelectorMode.DROPDOWN,
        translation_key="allocation_mode",
    )
)

_MAX_NUMBER = 10_000_000_000.0


def _finite_number(
    value: Any,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    """Return a finite in-range number, or None for invalid flow input."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(number):
        return None
    if minimum is not None and number < minimum:
        return None
    if maximum is not None and number > maximum:
        return None
    return number


def _plan_field_errors(fields: dict[str, Any]) -> dict[str, str]:
    """Validate plan fields that must be rejected before allocation entry."""
    errors: dict[str, str] = {}
    if not str(fields.get(PLAN_NAME) or "").strip():
        errors[PLAN_NAME] = "invalid_name"
    try:
        first = date.fromisoformat(str(fields.get(PLAN_FIRST_DATE)))
        if (
            fields.get(PLAN_END_DATE)
            and date.fromisoformat(str(fields[PLAN_END_DATE])) < first
        ):
            errors[PLAN_END_DATE] = "invalid_input"
    except ValueError:
        errors[PLAN_FIRST_DATE] = "invalid_input"
    amount = fields.get(PLAN_AMOUNT)
    if fields.get(PLAN_ALLOCATION_MODE) == ALLOCATION_MODE_PERCENTAGE and amount in (
        None,
        "",
    ):
        errors[PLAN_AMOUNT] = "invalid_number"
    if (
        amount not in (None, "")
        and _finite_number(amount, minimum=0.01, maximum=_MAX_NUMBER) is None
    ):
        errors[PLAN_AMOUNT] = "invalid_number"

    cutoff = fields.get(PLAN_OPENING_CUTOFF_DATE)
    if cutoff not in (None, ""):
        try:
            cutoff_date = date.fromisoformat(str(cutoff))
        except ValueError:
            errors[PLAN_OPENING_CUTOFF_DATE] = "invalid_input"
        else:
            if cutoff_date > dt_util.now().date():
                errors[PLAN_OPENING_CUTOFF_DATE] = "opening_cutoff_future"
    return errors


def _plan_input(
    values: dict[str, Any], previous: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Use real defaults without reviving cleared optional dates."""
    result = dict(values)
    result.setdefault(
        PLAN_FIRST_DATE,
        (previous or {}).get(PLAN_FIRST_DATE) or dt_util.now().date().isoformat(),
    )
    result.setdefault(PLAN_ENABLED, True)
    result.setdefault(PLAN_USE_CASH_BALANCE, True)
    result.setdefault(
        "opening_included", bool((previous or {}).get(PLAN_OPENING_CUTOFF_DATE))
    )
    if result["opening_included"]:
        result.setdefault(
            PLAN_OPENING_CUTOFF_DATE,
            (previous or {}).get(PLAN_OPENING_CUTOFF_DATE),
        )
    elif PLAN_OPENING_CUTOFF_DATE not in values:
        result[PLAN_OPENING_CUTOFF_DATE] = None
    return result


def _valor_schema(
    symbol: str | None = None,
    amount: float | None = None,
    target_share: float | None = None,
) -> vol.Schema:
    safe_amount = _finite_number(amount, minimum=0, maximum=_MAX_NUMBER)
    safe_target = _finite_number(target_share, minimum=0, maximum=100)
    return vol.Schema(
        {
            vol.Required(VALOR_SYMBOL, default=symbol): str,
            vol.Required(VALOR_AMOUNT, default=safe_amount): _AMOUNT_SELECTOR,
            # Suggested value (not default): an empty optional field is then
            # omitted from the submitted data instead of being sent as null.
            vol.Optional(
                VALOR_TARGET_SHARE, description={"suggested_value": safe_target}
            ): vol.Any(None, _TARGET_SHARE_SELECTOR),
        }
    )


def _valor_fields_schema(amount: Any, target_share: Any) -> vol.Schema:
    """Build the editable numeric fields for an existing holding."""
    safe_amount = _finite_number(amount, minimum=0, maximum=_MAX_NUMBER)
    safe_target = _finite_number(target_share, minimum=0, maximum=100)
    return vol.Schema(
        {
            vol.Required(VALOR_AMOUNT, default=safe_amount): _AMOUNT_SELECTOR,
            vol.Optional(
                VALOR_TARGET_SHARE,
                description={"suggested_value": safe_target},
            ): vol.Any(None, _TARGET_SHARE_SELECTOR),
        }
    )


def _normalize_target_share(value: Any) -> float | None:
    """Preserve an explicit zero target; only an empty field removes it."""
    if value is None or value == "":
        return None
    target = _finite_number(value, minimum=0, maximum=100)
    if target is None:
        raise ValueError("Target share must be finite and between 0 and 100")
    return target


def _targets_sum(valors: Iterable[dict[str, Any]]) -> float:
    """Sum of configured target shares."""
    return sum(float(v.get(VALOR_TARGET_SHARE) or 0) for v in valors)


def _target_sum_exceeded(others: Iterable[dict[str, Any]], target: float) -> bool:
    """Whether adding `target` on top of the other valors would exceed 100%."""
    return _targets_sum(others) + target > 100 + TARGET_SHARE_SUM_TOLERANCE


def _settings_schema(
    name: str | None = None,
    currency: str = DEFAULT_BASE_CURRENCY,
    interval: Any = DEFAULT_SCAN_INTERVAL,
    expected_return: Any = DEFAULT_EXPECTED_ANNUAL_RETURN,
    inflation_source: str = DEFAULT_INFLATION_SOURCE,
    expected_inflation: Any = DEFAULT_EXPECTED_ANNUAL_INFLATION,
) -> vol.Schema:
    safe_interval = _finite_number(
        interval, minimum=MIN_SCAN_INTERVAL, maximum=MAX_SCAN_INTERVAL
    )
    safe_return = _finite_number(
        expected_return,
        minimum=MIN_EXPECTED_ANNUAL_RETURN,
        maximum=MAX_EXPECTED_ANNUAL_RETURN,
    )
    safe_inflation = _finite_number(
        expected_inflation,
        minimum=MIN_EXPECTED_ANNUAL_INFLATION,
        maximum=MAX_EXPECTED_ANNUAL_INFLATION,
    )
    if inflation_source not in (
        INFLATION_SOURCE_EUROSTAT_DE,
        INFLATION_SOURCE_DISABLED,
    ):
        inflation_source = DEFAULT_INFLATION_SOURCE
    return vol.Schema(
        {
            vol.Required(CONF_WALLET_NAME, default=name): str,
            vol.Required(CONF_BASE_CURRENCY, default=currency): _CURRENCY_SELECTOR,
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=int(safe_interval)
                if safe_interval is not None
                else DEFAULT_SCAN_INTERVAL,
            ): _INTERVAL_SELECTOR,
            vol.Required(
                CONF_EXPECTED_ANNUAL_RETURN,
                default=(
                    safe_return
                    if safe_return is not None
                    else DEFAULT_EXPECTED_ANNUAL_RETURN
                ),
            ): _EXPECTED_RETURN_SELECTOR,
            vol.Required(
                CONF_INFLATION_SOURCE, default=inflation_source
            ): _INFLATION_SOURCE_SELECTOR,
            vol.Required(
                CONF_EXPECTED_ANNUAL_INFLATION,
                default=(
                    safe_inflation
                    if safe_inflation is not None
                    else DEFAULT_EXPECTED_ANNUAL_INFLATION
                ),
            ): _EXPECTED_INFLATION_SELECTOR,
        }
    )


def _contribution_schema(
    execution_date: str | None = None,
    amount: float | None = None,
    note: str | None = None,
) -> vol.Schema:
    """Build the form for one dated contribution."""
    date_marker: vol.Marker = vol.Required(
        CONTRIBUTION_DATE, default=dt_util.now().date().isoformat()
    )
    amount_marker: vol.Marker = vol.Required(CONTRIBUTION_AMOUNT)
    if execution_date is not None:
        date_marker = vol.Required(CONTRIBUTION_DATE, default=execution_date)
    if (
        safe_amount := _finite_number(amount, minimum=0.01, maximum=_MAX_NUMBER)
    ) is not None:
        amount_marker = vol.Required(CONTRIBUTION_AMOUNT, default=safe_amount)
    return vol.Schema(
        {
            date_marker: _DATE_SELECTOR,
            amount_marker: _CONTRIBUTION_AMOUNT_SELECTOR,
            vol.Optional(CONTRIBUTION_NOTE, description={"suggested_value": note}): str,
        }
    )


def _plan_schema(plan: dict[str, Any] | None = None) -> vol.Schema:
    """Build the common savings-plan settings form."""
    plan = plan or {}
    end_date = plan.get(PLAN_END_DATE)
    amount = _finite_number(plan.get(PLAN_AMOUNT), minimum=0.01, maximum=_MAX_NUMBER)
    return vol.Schema(
        {
            vol.Required(PLAN_NAME, default=plan.get(PLAN_NAME)): str,
            vol.Required(PLAN_ENABLED, default=plan.get(PLAN_ENABLED, True)): bool,
            vol.Required(
                PLAN_FIRST_DATE,
                default=plan.get(PLAN_FIRST_DATE) or dt_util.now().date().isoformat(),
            ): _DATE_SELECTOR,
            vol.Optional(
                PLAN_END_DATE, description={"suggested_value": end_date}
            ): vol.Any(None, _DATE_SELECTOR),
            vol.Required(
                PLAN_ALLOCATION_MODE,
                default=plan.get(PLAN_ALLOCATION_MODE, ALLOCATION_MODE_PERCENTAGE),
            ): _ALLOCATION_MODE_SELECTOR,
            (
                vol.Optional(PLAN_AMOUNT, default=amount)
                if amount is not None
                else vol.Optional(PLAN_AMOUNT)
            ): vol.Any(None, _CONTRIBUTION_AMOUNT_SELECTOR),
            vol.Required(
                PLAN_USE_CASH_BALANCE,
                default=plan.get(PLAN_USE_CASH_BALANCE, True),
            ): bool,
            vol.Optional(
                "opening_included",
                default=plan.get(
                    "opening_included", bool(plan.get(PLAN_OPENING_CUTOFF_DATE))
                ),
            ): bool,
        }
    )


def _allocation_schema(
    symbols: list[str],
    mode: str,
    symbol: str | None = None,
    value: float | None = None,
    options: list[dict[str, str]] | None = None,
) -> vol.Schema:
    """Build one allocation row for a savings plan."""
    value_selector = (
        _PERCENT_SELECTOR
        if mode == ALLOCATION_MODE_PERCENTAGE
        else _CONTRIBUTION_AMOUNT_SELECTOR
    )
    symbol_marker: vol.Marker = vol.Required(ALLOCATION_SYMBOL)
    value_marker: vol.Marker = vol.Required(ALLOCATION_VALUE)
    if symbol in symbols:
        symbol_marker = vol.Required(ALLOCATION_SYMBOL, default=symbol)
    maximum = 100 if mode == ALLOCATION_MODE_PERCENTAGE else _MAX_NUMBER
    if (safe_value := _finite_number(value, minimum=0.01, maximum=maximum)) is not None:
        value_marker = vol.Required(ALLOCATION_VALUE, default=safe_value)
    return vol.Schema(
        {
            symbol_marker: selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options or symbols,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            value_marker: value_selector,
            vol.Optional("add_another", default=True): bool,
        }
    )


def _manual_lot_schema(
    symbols: list[str],
    contribution_options: list[dict[str, str]],
    values: dict[str, Any] | None = None,
    symbol_options: list[dict[str, str]] | None = None,
) -> vol.Schema:
    """Build the form for importing one historical purchase lot."""
    values = values or {}
    amount = _finite_number(values.get(LOT_AMOUNT), minimum=0.01, maximum=_MAX_NUMBER)
    unit_price = _finite_number(
        values.get(LOT_UNIT_PRICE), minimum=0.000001, maximum=_MAX_NUMBER
    )
    selected_symbol = values.get(LOT_SYMBOL)
    if selected_symbol not in symbols:
        selected_symbol = None
    fields: dict[vol.Marker, Any] = {
        vol.Required(LOT_SYMBOL, default=selected_symbol): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=symbol_options or symbols,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(
            LOT_DATE, default=values.get(LOT_DATE) or dt_util.now().date().isoformat()
        ): _DATE_SELECTOR,
        vol.Required(LOT_AMOUNT, default=amount): _CONTRIBUTION_AMOUNT_SELECTOR,
        vol.Optional(
            LOT_UNIT_PRICE,
            description={"suggested_value": unit_price},
        ): vol.Any(None, _PRICE_SELECTOR),
        vol.Optional(
            LOT_UNITS, description={"suggested_value": values.get(LOT_UNITS)}
        ): vol.Any(None, _UNITS_SELECTOR),
        vol.Required(
            LOT_INCLUDED_IN_OPENING,
            default=values.get(LOT_INCLUDED_IN_OPENING, True),
        ): bool,
    }
    if contribution_options:
        fields[
            vol.Optional(
                "funding_contribution",
                description={"suggested_value": values.get("funding_contribution")},
            )
        ] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=contribution_options,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )
    return vol.Schema(fields)


def _dividend_schema(
    symbols: list[str],
    dividend: dict[str, Any] | None = None,
    symbol_options: list[dict[str, str]] | None = None,
) -> vol.Schema:
    """Build the form for one net dividend credit."""
    dividend = dividend or {}
    amount = _finite_number(
        dividend.get(DIVIDEND_AMOUNT), minimum=0.01, maximum=_MAX_NUMBER
    )
    source = dividend.get(DIVIDEND_SYMBOL, "__wallet__")
    if source != "__wallet__" and source not in symbols:
        source = "__wallet__"
    source_options: list[dict[str, str]] = [
        {
            "value": "__wallet__",
            "label": "—",
        }
    ]
    source_options.extend(
        symbol_options or ({"value": symbol, "label": symbol} for symbol in symbols)
    )
    return vol.Schema(
        {
            vol.Required(
                DIVIDEND_BOOKING_DATE,
                default=dividend.get(DIVIDEND_BOOKING_DATE)
                or dt_util.now().date().isoformat(),
            ): _DATE_SELECTOR,
            vol.Optional(
                DIVIDEND_VALUE_DATE,
                description={"suggested_value": dividend.get(DIVIDEND_VALUE_DATE)},
            ): vol.Any(None, _DATE_SELECTOR),
            vol.Required(
                DIVIDEND_AMOUNT,
                default=amount,
            ): _CONTRIBUTION_AMOUNT_SELECTOR,
            vol.Required(DIVIDEND_SYMBOL, default=source): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=source_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                DIVIDEND_NOTE,
                description={"suggested_value": dividend.get(DIVIDEND_NOTE)},
            ): vol.Any(None, str),
        }
    )
