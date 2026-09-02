"""Config flow for My Wallet."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from math import isfinite
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .const import (
    ALLOCATION_MODE_FIXED,
    ALLOCATION_MODE_PERCENTAGE,
    ALLOCATION_SYMBOL,
    ALLOCATION_VALUE,
    COMMON_CURRENCIES,
    CONF_BASE_CURRENCY,
    CONF_CONTRIBUTIONS,
    CONF_DIVIDENDS,
    CONF_EXPECTED_ANNUAL_INFLATION,
    CONF_EXPECTED_ANNUAL_RETURN,
    CONF_INFLATION_SOURCE,
    CONF_INVESTED_AMOUNT,
    CONF_RETIRED_SAVINGS_PLANS,
    CONF_SAVINGS_PLANS,
    CONF_SCAN_INTERVAL,
    CONF_VALORS,
    CONF_WALLET_NAME,
    CONTRIBUTION_AMOUNT,
    CONTRIBUTION_DATE,
    CONTRIBUTION_ID,
    CONTRIBUTION_LOTS,
    CONTRIBUTION_MANUALLY_EDITED,
    CONTRIBUTION_NOTE,
    CONTRIBUTION_PLAN_ID,
    CONTRIBUTION_PLAN_NAME,
    CONTRIBUTION_SCHEDULED_DATE,
    CONTRIBUTION_SOURCE,
    CONTRIBUTION_SOURCE_LEGACY,
    CONTRIBUTION_SOURCE_PURCHASE,
    DEFAULT_BASE_CURRENCY,
    DEFAULT_EXPECTED_ANNUAL_INFLATION,
    DEFAULT_EXPECTED_ANNUAL_RETURN,
    DEFAULT_INFLATION_SOURCE,
    DEFAULT_SCAN_INTERVAL,
    DIVIDEND_AMOUNT,
    DIVIDEND_BOOKING_DATE,
    DIVIDEND_ID,
    DIVIDEND_NOTE,
    DIVIDEND_SYMBOL,
    DIVIDEND_VALUE_DATE,
    DOMAIN,
    INFLATION_SOURCE_DISABLED,
    INFLATION_SOURCE_EUROSTAT_DE,
    LOT_AMOUNT,
    LOT_DATE,
    LOT_FX_RATE,
    LOT_ID,
    LOT_INCLUDED_IN_OPENING,
    LOT_QUOTE_CURRENCY,
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
    TARGET_SHARE_SUM_TOLERANCE,
    VALOR_AMOUNT,
    VALOR_SYMBOL,
    VALOR_TARGET_SHARE,
)
from .contributions import (
    all_lots,
    contributions_from_data,
    make_contribution,
    make_lot,
    normalize_contributions,
    opening_balance_conflicts,
)
from .display import position_label, position_options
from .display import text as display_text
from .dividends import (
    dividends_from_data,
    make_dividend,
    normalize_dividends,
)
from .executions import _worsened_cash_history
from .investment_options import InvestmentOptionsMixin
from .plan_options import PlanOptionsMixin
from .planning import is_plannable_deposit
from .plans import (
    is_scheduled_period,
    normalize_plan,
    schedule_period,
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


class MyWalletConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial creation of a wallet."""

    VERSION = 7

    def __init__(self) -> None:
        self._valors: list[dict[str, Any]] = []
        self._name: str | None = None
        self._currency: str = DEFAULT_BASE_CURRENCY
        self._interval: int = DEFAULT_SCAN_INTERVAL
        self._expected_return: float = DEFAULT_EXPECTED_ANNUAL_RETURN
        self._inflation_source: str = DEFAULT_INFLATION_SOURCE
        self._expected_inflation: float = DEFAULT_EXPECTED_ANNUAL_INFLATION

    async def async_step_import(self, user_input):
        """Create a separate wallet from a confirmed server-side preview."""
        from .backup import BACKUP_RESTORE_ID
        from .history_import import IMPORT_BATCH
        from .panel import consume_import

        try:
            data = consume_import(self.hass, user_input["token"], user_input["user_id"])
        except (KeyError, ValueError) as err:
            return self.async_abort(
                reason=str(err) if isinstance(err, ValueError) else "import_expired"
            )
        restore_id = data.pop(BACKUP_RESTORE_ID, None)
        import_id = restore_id or data.get(IMPORT_BATCH)
        if not import_id:
            return self.async_abort(reason="invalid_import")
        await self.async_set_unique_id(f"import:{import_id}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=data[CONF_WALLET_NAME], data=data)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: basic wallet settings."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_WALLET_NAME].strip()
            interval = _finite_number(
                user_input.get(CONF_SCAN_INTERVAL),
                minimum=MIN_SCAN_INTERVAL,
                maximum=MAX_SCAN_INTERVAL,
            )
            expected_return = _finite_number(
                user_input.get(
                    CONF_EXPECTED_ANNUAL_RETURN, DEFAULT_EXPECTED_ANNUAL_RETURN
                ),
                minimum=MIN_EXPECTED_ANNUAL_RETURN,
                maximum=MAX_EXPECTED_ANNUAL_RETURN,
            )
            expected_inflation = _finite_number(
                user_input.get(
                    CONF_EXPECTED_ANNUAL_INFLATION,
                    DEFAULT_EXPECTED_ANNUAL_INFLATION,
                ),
                minimum=MIN_EXPECTED_ANNUAL_INFLATION,
                maximum=MAX_EXPECTED_ANNUAL_INFLATION,
            )
            inflation_source = user_input.get(
                CONF_INFLATION_SOURCE, DEFAULT_INFLATION_SOURCE
            )
            if not name:
                errors[CONF_WALLET_NAME] = "invalid_name"
            elif interval is None or not interval.is_integer():
                errors[CONF_SCAN_INTERVAL] = "invalid_number"
            elif expected_return is None:
                errors[CONF_EXPECTED_ANNUAL_RETURN] = "invalid_number"
            elif expected_inflation is None:
                errors[CONF_EXPECTED_ANNUAL_INFLATION] = "invalid_number"
            elif inflation_source not in (
                INFLATION_SOURCE_EUROSTAT_DE,
                INFLATION_SOURCE_DISABLED,
            ):
                errors[CONF_INFLATION_SOURCE] = "invalid_input"
            else:
                self._name = name
                self._currency = user_input[CONF_BASE_CURRENCY]
                self._interval = int(interval)
                self._expected_return = expected_return
                self._inflation_source = inflation_source
                self._expected_inflation = expected_inflation
                return await self.async_step_valor()
        return self.async_show_form(
            step_id="user",
            data_schema=_settings_schema(
                self._name,
                self._currency,
                self._interval,
                self._expected_return,
                self._inflation_source,
                self._expected_inflation,
            ),
            errors=errors,
        )

    async def async_step_valor(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2..n: add valors one by one until the user stops."""
        errors: dict[str, str] = {}
        # Re-submit the entered values when the form is shown again after an error.
        schema = _valor_schema(
            user_input.get(VALOR_SYMBOL) if user_input else None,
            user_input.get(VALOR_AMOUNT) if user_input else None,
            user_input.get(VALOR_TARGET_SHARE) if user_input else None,
        ).extend({vol.Optional("add_another", default=True): bool})
        if user_input is not None:
            symbol = user_input[VALOR_SYMBOL].strip().upper()
            amount = _finite_number(
                user_input.get(VALOR_AMOUNT), minimum=0, maximum=_MAX_NUMBER
            )
            try:
                target = _normalize_target_share(user_input.get(VALOR_TARGET_SHARE))
            except ValueError:
                target = None
                errors[VALOR_TARGET_SHARE] = "invalid_number"
            if not symbol:
                errors[VALOR_SYMBOL] = "invalid_symbol"
            elif amount is None:
                errors[VALOR_AMOUNT] = "invalid_number"
            elif any(v[VALOR_SYMBOL] == symbol for v in self._valors):
                errors[VALOR_SYMBOL] = "symbol_exists"
            elif (
                not errors
                and target is not None
                and _target_sum_exceeded(self._valors, target)
            ):
                errors[VALOR_TARGET_SHARE] = "target_sum_exceeded"
            elif not errors:
                valor: dict[str, Any] = {VALOR_SYMBOL: symbol, VALOR_AMOUNT: amount}
                if target is not None:
                    valor[VALOR_TARGET_SHARE] = target
                self._valors.append(valor)
                if not user_input.get("add_another"):
                    return self._create_entry()
                # Re-show an empty form for the next valor.
                return self.async_show_form(
                    step_id="valor",
                    data_schema=_valor_schema().extend(
                        {vol.Optional("add_another", default=True): bool}
                    ),
                    errors=errors,
                )
        return self.async_show_form(step_id="valor", data_schema=schema, errors=errors)

    def _create_entry(self) -> FlowResult:
        data: dict[str, Any] = {
            CONF_WALLET_NAME: self._name,
            CONF_BASE_CURRENCY: self._currency,
            CONF_SCAN_INTERVAL: self._interval,
            CONF_EXPECTED_ANNUAL_RETURN: self._expected_return,
            CONF_INFLATION_SOURCE: self._inflation_source,
            CONF_EXPECTED_ANNUAL_INFLATION: self._expected_inflation,
            CONF_VALORS: self._valors,
            CONF_CONTRIBUTIONS: [],
            CONF_SAVINGS_PLANS: [],
            CONF_RETIRED_SAVINGS_PLANS: [],
            CONF_DIVIDENDS: [],
        }
        return self.async_create_entry(title=self._name or "Wallet", data=data)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> MyWalletOptionsFlow:
        return MyWalletOptionsFlow(config_entry)


class MyWalletOptionsFlow(
    PlanOptionsMixin, InvestmentOptionsMixin, config_entries.OptionsFlowWithConfigEntry
):
    """Manage wallet settings, contributions, and valors."""

    _edit_symbol: str | None = None
    _edit_contribution_id: str | None = None
    _edit_lot_id: str | None = None
    _edit_dividend_id: str | None = None
    _working_plan_id: str | None = None
    _working_plan_fields: dict[str, Any] | None = None
    _working_allocations: list[dict[str, Any]] | None = None
    _working_base_currency: str | None = None
    _pending_contributions: list[dict[str, Any]] | None = None
    _pending_base_currency: str | None = None
    _delete_contribution_id: str | None = None
    _delete_contribution_snapshot: dict[str, Any] | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the management menu."""
        self._edit_symbol = None
        self._edit_contribution_id = None
        self._edit_lot_id = None
        self._edit_dividend_id = None
        self._working_plan_id = None
        self._working_plan_fields = None
        self._working_allocations = None
        self._working_base_currency = None
        self._pending_contributions = None
        self._pending_base_currency = None
        self._delete_contribution_id = None
        self._delete_contribution_snapshot = None
        self._selected_plan_symbols = None
        self._plan_index = 0
        self._plan_scope = "future"
        self._proposed_plan = None
        self._plan_original = None
        self._plan_task = None
        menu_options = [
            "settings",
            "add_contribution",
            "plan_contribution",
            "add_lot",
            "add_dividend",
        ]
        contributions = self._contributions()
        if any(row[CONTRIBUTION_AMOUNT] > 0 for row in contributions):
            menu_options.append("edit_contribution")
        if contributions:
            menu_options.append("remove_contribution")
        if all_lots(self.config_entry.data):
            menu_options.append("edit_lot")
        if self._dividends():
            menu_options.extend(["edit_dividend", "remove_dividend"])
        menu_options.append("add_plan")
        if self._plans():
            menu_options.extend(["edit_plan", "remove_plan"])
        if any(
            is_scheduled_period(plan, period)
            for plan in self._plans()
            for period in plan[PLAN_SKIPPED_PERIODS]
        ):
            menu_options.append("restore_execution")
        menu_options.extend(["add_valor", "edit_valor", "remove_valor"])
        conflicts = opening_balance_conflicts(self.config_entry.data)
        warning = ""
        if conflicts:
            warning = (
                self._text("opening_balance_conflict")
                + "\n\n"
                + "\n".join(
                    f"- {self._position_label(item['symbol'])}: "
                    f"{self._text('configured_units')} "
                    f"{item['configured_units']:.12g}; {self._text('included_units')} "
                    f"{item['included_units']:.12g}"
                    for item in conflicts
                )
            )
        return self.async_show_menu(
            step_id="init",
            menu_options=menu_options,
            description_placeholders={"opening_conflict": warning},
        )

    def _valors(self) -> list[dict[str, Any]]:
        return list(self.config_entry.data.get(CONF_VALORS, []))

    def _position_label(self, symbol: str) -> str:
        """Show an alias together with its stable technical symbol."""
        return position_label(self._valors(), symbol)

    def _position_options(
        self, symbols: Iterable[str] | None = None
    ) -> list[dict[str, str]]:
        """Build labeled choices whose stored values remain stable symbols."""
        return position_options(self._valors(), symbols)

    def _contributions(self) -> list[dict[str, Any]]:
        return contributions_from_data(self.config_entry.data)

    def _plans(self) -> list[dict[str, Any]]:
        return [
            normalize_plan(item)
            for item in self.config_entry.data.get(CONF_SAVINGS_PLANS, [])
        ]

    def _retired_plans(self) -> list[dict[str, Any]]:
        """Return inert plan identities retained for duplicate prevention."""
        return [
            normalize_plan(item)
            for item in self.config_entry.data.get(CONF_RETIRED_SAVINGS_PLANS, [])
        ]

    def _dividends(self) -> list[dict[str, Any]]:
        return dividends_from_data(self.config_entry.data)

    def _included_lot_units(
        self, symbol: str, *, exclude_lot_id: str | None = None
    ) -> float:
        """Return units represented by opening-balance purchase lots."""
        return sum(
            float(lot[LOT_UNITS])
            for lot in all_lots(self.config_entry.data)
            if lot[LOT_SYMBOL] == symbol
            and lot[LOT_INCLUDED_IN_OPENING]
            and lot[LOT_ID] != exclude_lot_id
        )

    def _opening_units(self, symbol: str) -> float:
        """Return the configured opening units for one symbol."""
        return float(
            next(
                valor[VALOR_AMOUNT]
                for valor in self._valors()
                if valor[VALOR_SYMBOL] == symbol
            )
        )

    def _contribution_options(
        self, *, deposits_only: bool = False
    ) -> list[dict[str, str]]:
        return [
            {
                "value": item[CONTRIBUTION_ID],
                "label": self._contribution_label(item),
            }
            for item in self._contributions()
            if not deposits_only or item[CONTRIBUTION_AMOUNT] > 0
        ]

    def _text(self, key: str) -> str:
        language = getattr(getattr(self.hass, "config", None), "language", "en")
        return display_text(key, language)

    def _contribution_label(self, item: dict[str, Any]) -> str:
        plan = next(
            (
                plan
                for plan in [*self._plans(), *self._retired_plans()]
                if plan[PLAN_ID] == item.get(CONTRIBUTION_PLAN_ID)
            ),
            None,
        )
        name = plan[PLAN_NAME] if plan else item.get(CONTRIBUTION_PLAN_NAME)
        if not name:
            name = item.get(CONTRIBUTION_NOTE) or self._text(
                "purchase"
                if item[CONTRIBUTION_SOURCE] == CONTRIBUTION_SOURCE_PURCHASE
                else "opening"
                if item[CONTRIBUTION_SOURCE] == CONTRIBUTION_SOURCE_LEGACY
                else "deposit"
            )
        currency = self.config_entry.data.get(CONF_BASE_CURRENCY, DEFAULT_BASE_CURRENCY)
        amount = (
            sum(lot[LOT_AMOUNT] for lot in item[CONTRIBUTION_LOTS])
            if item[CONTRIBUTION_SOURCE] == CONTRIBUTION_SOURCE_PURCHASE
            else item[CONTRIBUTION_AMOUNT]
        )
        label = f"{name} · {item[CONTRIBUTION_DATE] or '—'} · {amount:.2f} {currency}"
        if (
            item[CONTRIBUTION_DATE]
            and item[CONTRIBUTION_DATE] > dt_util.now().date().isoformat()
        ):
            label = f"{self._text('planned_deposit')} · {label}"
        if item.get(CONTRIBUTION_MANUALLY_EDITED):
            label += f" · {self._text('corrected')}"
        return label

    def _lot_options(self) -> list[dict[str, str]]:
        currency = self.config_entry.data.get(CONF_BASE_CURRENCY, DEFAULT_BASE_CURRENCY)
        return [
            {
                "value": lot[LOT_ID],
                "label": (
                    f"{lot[LOT_DATE]} · {self._position_label(lot[LOT_SYMBOL])} · "
                    f"{lot[LOT_AMOUNT]:.2f} {currency}"
                ),
            }
            for lot in all_lots(self.config_entry.data)
        ]

    def _plan_options(self) -> list[dict[str, str]]:
        currency = self.config_entry.data.get(CONF_BASE_CURRENCY, DEFAULT_BASE_CURRENCY)
        return [
            {
                "value": plan[PLAN_ID],
                "label": (
                    f"{plan[PLAN_NAME]} · {plan[PLAN_AMOUNT]:.2f} {currency} · "
                    f"{plan[PLAN_FIRST_DATE]}"
                ),
            }
            for plan in self._plans()
        ]

    def _dividend_options(self) -> list[dict[str, str]]:
        currency = self.config_entry.data.get(CONF_BASE_CURRENCY, DEFAULT_BASE_CURRENCY)
        options = []
        for item in self._dividends():
            symbol = item.get(DIVIDEND_SYMBOL)
            position = self._position_label(symbol) if symbol else "Portfolio"
            options.append(
                {
                    "value": item[DIVIDEND_ID],
                    "label": (
                        f"{item[DIVIDEND_BOOKING_DATE]} · {position} · "
                        f"{item[DIVIDEND_AMOUNT]:.2f} {currency}"
                    ),
                }
            )
        return options

    def _update_entry(
        self,
        valors: list[dict[str, Any]] | None = None,
        *,
        entry_title: str | None = None,
        **extra: Any,
    ) -> None:
        """Write user-originated config data and schedule one reload."""
        data = dict(self.config_entry.data)
        if valors is not None:
            data[CONF_VALORS] = valors
        data.update(extra)
        if CONF_CONTRIBUTIONS in extra:
            data.pop(CONF_INVESTED_AMOUNT, None)
        if entry_title is None:
            changed = self.hass.config_entries.async_update_entry(
                self.config_entry, data=data
            )
        else:
            changed = self.hass.config_entries.async_update_entry(
                self.config_entry, data=data, title=entry_title
            )
        if changed:
            self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)

    async def _save(
        self,
        valors: list[dict[str, Any]],
        *,
        entry_title: str | None = None,
        **extra: Any,
    ) -> FlowResult:
        self._update_entry(valors, entry_title=entry_title, **extra)
        return self.async_create_entry(title="", data={})

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_WALLET_NAME].strip()
            interval = _finite_number(
                user_input.get(CONF_SCAN_INTERVAL),
                minimum=MIN_SCAN_INTERVAL,
                maximum=MAX_SCAN_INTERVAL,
            )
            expected_return = _finite_number(
                user_input.get(
                    CONF_EXPECTED_ANNUAL_RETURN,
                    self.config_entry.data.get(
                        CONF_EXPECTED_ANNUAL_RETURN,
                        DEFAULT_EXPECTED_ANNUAL_RETURN,
                    ),
                ),
                minimum=MIN_EXPECTED_ANNUAL_RETURN,
                maximum=MAX_EXPECTED_ANNUAL_RETURN,
            )
            expected_inflation = _finite_number(
                user_input.get(
                    CONF_EXPECTED_ANNUAL_INFLATION,
                    self.config_entry.data.get(
                        CONF_EXPECTED_ANNUAL_INFLATION,
                        DEFAULT_EXPECTED_ANNUAL_INFLATION,
                    ),
                ),
                minimum=MIN_EXPECTED_ANNUAL_INFLATION,
                maximum=MAX_EXPECTED_ANNUAL_INFLATION,
            )
            inflation_source = user_input.get(
                CONF_INFLATION_SOURCE,
                self.config_entry.data.get(
                    CONF_INFLATION_SOURCE, DEFAULT_INFLATION_SOURCE
                ),
            )
            if not name:
                errors[CONF_WALLET_NAME] = "invalid_name"
            elif interval is None or not interval.is_integer():
                errors[CONF_SCAN_INTERVAL] = "invalid_number"
            elif expected_return is None:
                errors[CONF_EXPECTED_ANNUAL_RETURN] = "invalid_number"
            elif expected_inflation is None:
                errors[CONF_EXPECTED_ANNUAL_INFLATION] = "invalid_number"
            elif inflation_source not in (
                INFLATION_SOURCE_EUROSTAT_DE,
                INFLATION_SOURCE_DISABLED,
            ):
                errors[CONF_INFLATION_SOURCE] = "invalid_input"
            elif user_input[CONF_BASE_CURRENCY] != self.config_entry.data.get(
                CONF_BASE_CURRENCY, DEFAULT_BASE_CURRENCY
            ) and (self._contributions() or self._plans() or self._dividends()):
                errors[CONF_BASE_CURRENCY] = "currency_change_blocked"
            else:
                return await self._save(
                    self._valors(),
                    entry_title=name,
                    **{
                        CONF_WALLET_NAME: name,
                        CONF_BASE_CURRENCY: user_input[CONF_BASE_CURRENCY],
                        CONF_SCAN_INTERVAL: int(interval),
                        CONF_EXPECTED_ANNUAL_RETURN: expected_return,
                        CONF_INFLATION_SOURCE: inflation_source,
                        CONF_EXPECTED_ANNUAL_INFLATION: expected_inflation,
                    },
                )
        data = self.config_entry.data
        return self.async_show_form(
            step_id="settings",
            data_schema=_settings_schema(
                self.config_entry.title or data.get(CONF_WALLET_NAME, "Wallet"),
                data.get(CONF_BASE_CURRENCY, DEFAULT_BASE_CURRENCY),
                data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                data.get(
                    CONF_EXPECTED_ANNUAL_RETURN,
                    DEFAULT_EXPECTED_ANNUAL_RETURN,
                ),
                data.get(CONF_INFLATION_SOURCE, DEFAULT_INFLATION_SOURCE),
                data.get(
                    CONF_EXPECTED_ANNUAL_INFLATION,
                    DEFAULT_EXPECTED_ANNUAL_INFLATION,
                ),
            ),
            errors=errors,
        )

    async def async_step_add_dividend(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Record a net dividend credit on the broker cash account."""
        errors: dict[str, str] = {}
        if user_input is not None:
            amount = _finite_number(
                user_input.get(DIVIDEND_AMOUNT),
                minimum=0.01,
                maximum=_MAX_NUMBER,
            )
            if amount is None:
                errors[DIVIDEND_AMOUNT] = "invalid_number"
            else:
                symbol = user_input.get(DIVIDEND_SYMBOL)
                configured = {valor[VALOR_SYMBOL] for valor in self._valors()}
                if symbol != "__wallet__" and symbol not in configured:
                    errors[DIVIDEND_SYMBOL] = "invalid_symbol"
                if not errors:
                    try:
                        dividend = make_dividend(
                            booking_date=user_input[DIVIDEND_BOOKING_DATE],
                            value_date=user_input.get(DIVIDEND_VALUE_DATE),
                            amount=amount,
                            symbol=None if symbol == "__wallet__" else symbol,
                            note=user_input.get(DIVIDEND_NOTE),
                        )
                    except (TypeError, ValueError):
                        errors["base"] = "invalid_input"
                    else:
                        return await self._save(
                            self._valors(),
                            **{
                                CONF_DIVIDENDS: normalize_dividends(
                                    [*self._dividends(), dividend]
                                )
                            },
                        )
        return self.async_show_form(
            step_id="add_dividend",
            data_schema=_dividend_schema(
                [valor[VALOR_SYMBOL] for valor in self._valors()],
                user_input,
                self._position_options(),
            ),
            errors=errors,
        )

    async def async_step_edit_dividend(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Choose a dividend credit to edit."""
        if not self._dividends():
            return self.async_abort(reason="no_dividends")
        if user_input is not None:
            self._edit_dividend_id = user_input[DIVIDEND_ID]
            return await self.async_step_edit_dividend_fields()
        return self.async_show_form(
            step_id="edit_dividend",
            data_schema=vol.Schema(
                {
                    vol.Required(DIVIDEND_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=self._dividend_options(),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_edit_dividend_fields(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit one dividend credit."""
        dividend_id = self._edit_dividend_id
        dividends = self._dividends()
        current = next(
            (item for item in dividends if item[DIVIDEND_ID] == dividend_id), None
        )
        if current is None:
            return self.async_abort(reason="stale_selection")
        errors: dict[str, str] = {}
        if user_input is not None:
            amount = _finite_number(
                user_input.get(DIVIDEND_AMOUNT),
                minimum=0.01,
                maximum=_MAX_NUMBER,
            )
            if amount is None:
                errors[DIVIDEND_AMOUNT] = "invalid_number"
            else:
                symbol = user_input.get(DIVIDEND_SYMBOL)
                configured = {valor[VALOR_SYMBOL] for valor in self._valors()}
                if symbol != "__wallet__" and symbol not in configured:
                    errors[DIVIDEND_SYMBOL] = "invalid_symbol"
                if not errors:
                    try:
                        replacement = make_dividend(
                            booking_date=user_input[DIVIDEND_BOOKING_DATE],
                            value_date=user_input.get(DIVIDEND_VALUE_DATE),
                            amount=amount,
                            symbol=None if symbol == "__wallet__" else symbol,
                            note=user_input.get(DIVIDEND_NOTE),
                            dividend_id=dividend_id,
                        )
                    except (TypeError, ValueError):
                        errors["base"] = "invalid_input"
                    else:
                        return await self._save(
                            self._valors(),
                            **{
                                CONF_DIVIDENDS: normalize_dividends(
                                    [
                                        replacement
                                        if item[DIVIDEND_ID] == dividend_id
                                        else item
                                        for item in dividends
                                    ]
                                )
                            },
                        )
        shown = user_input if user_input is not None else current
        return self.async_show_form(
            step_id="edit_dividend_fields",
            data_schema=_dividend_schema(
                [valor[VALOR_SYMBOL] for valor in self._valors()],
                shown,
                self._position_options(),
            ),
            description_placeholders={
                "dividend": (
                    f"{current[DIVIDEND_BOOKING_DATE]} · {current[DIVIDEND_AMOUNT]:.2f}"
                )
            },
            errors=errors,
        )

    async def async_step_remove_dividend(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Remove one dividend credit."""
        dividends = self._dividends()
        if not dividends:
            return self.async_abort(reason="no_dividends")
        if user_input is not None:
            dividend_id = user_input[DIVIDEND_ID]
            if not any(item[DIVIDEND_ID] == dividend_id for item in dividends):
                return self.async_abort(reason="stale_selection")
            return await self._save(
                self._valors(),
                **{
                    CONF_DIVIDENDS: [
                        item for item in dividends if item[DIVIDEND_ID] != dividend_id
                    ]
                },
            )
        return self.async_show_form(
            step_id="remove_dividend",
            data_schema=vol.Schema(
                {
                    vol.Required(DIVIDEND_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=self._dividend_options(),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_edit_contribution(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Choose a contribution to edit."""
        if not any(row[CONTRIBUTION_AMOUNT] > 0 for row in self._contributions()):
            return self.async_abort(reason="no_contributions")
        if user_input is not None:
            self._edit_contribution_id = user_input[CONTRIBUTION_ID]
            return await self.async_step_edit_contribution_fields()
        return self.async_show_form(
            step_id="edit_contribution",
            data_schema=vol.Schema(
                {
                    vol.Required(CONTRIBUTION_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=self._contribution_options(deposits_only=True),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_edit_contribution_fields(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit the amount and execution date of one contribution."""
        contribution_id = self._edit_contribution_id
        contributions = self._contributions()
        current = next(
            (
                item
                for item in contributions
                if item[CONTRIBUTION_ID] == contribution_id
            ),
            None,
        )
        if current is None or current[CONTRIBUTION_AMOUNT] == 0:
            return self.async_abort(reason="stale_selection")
        errors: dict[str, str] = {}
        if user_input is not None:
            amount = _finite_number(
                user_input.get(CONTRIBUTION_AMOUNT),
                minimum=0.01,
                maximum=_MAX_NUMBER,
            )
            try:
                execution_date = date.fromisoformat(
                    str(
                        user_input.get(CONTRIBUTION_DATE)
                        or current[CONTRIBUTION_DATE]
                        or dt_util.now().date().isoformat()
                    )
                )
            except ValueError:
                errors[CONTRIBUTION_DATE] = "invalid_input"
            else:
                if execution_date > dt_util.now().date() and not is_plannable_deposit(
                    current
                ):
                    errors[CONTRIBUTION_DATE] = "future_date"
                elif any(
                    date.fromisoformat(str(lot[LOT_DATE])) < execution_date
                    for lot in current[CONTRIBUTION_LOTS]
                ):
                    errors[CONTRIBUTION_DATE] = "contribution_date_after_lot"
            if amount is None:
                errors[CONTRIBUTION_AMOUNT] = "invalid_number"
            if not errors:
                try:
                    replacement = make_contribution(
                        amount,
                        execution_date,
                        contribution_id=contribution_id,
                        source=current[CONTRIBUTION_SOURCE],
                        lots=current[CONTRIBUTION_LOTS],
                        plan_id=current.get(CONTRIBUTION_PLAN_ID),
                        scheduled_date=current.get(CONTRIBUTION_SCHEDULED_DATE),
                        note=user_input.get(CONTRIBUTION_NOTE),
                        plan_name=current.get(CONTRIBUTION_PLAN_NAME),
                        manually_edited=True,
                    )
                except (TypeError, ValueError):
                    errors["base"] = "invalid_input"
                else:
                    updated = normalize_contributions(
                        [
                            replacement
                            if item[CONTRIBUTION_ID] == contribution_id
                            else item
                            for item in contributions
                        ]
                    )
                    if _worsened_cash_history(
                        self.config_entry.data,
                        {**self.config_entry.data, CONF_CONTRIBUTIONS: updated},
                        dt_util.now().date(),
                    ):
                        errors["base"] = "cash_conflict"
                    else:
                        return await self._save(
                            self._valors(), **{CONF_CONTRIBUTIONS: updated}
                        )
        shown = user_input if user_input is not None else current
        return self.async_show_form(
            step_id="edit_contribution_fields",
            data_schema=_contribution_schema(
                shown.get(CONTRIBUTION_DATE),
                shown[CONTRIBUTION_AMOUNT],
                shown.get(CONTRIBUTION_NOTE),
            ),
            description_placeholders={
                "contribution": self._contribution_label(current),
                "lots": "\n".join(
                    f"- {self._position_label(lot[LOT_SYMBOL])} · "
                    f"{lot[LOT_DATE]} · {lot[LOT_AMOUNT]:.2f}"
                    for lot in current[CONTRIBUTION_LOTS]
                )
                or "—",
            },
            errors=errors,
        )

    async def async_step_remove_contribution(self, user_input=None):
        contributions = self._contributions()
        if not contributions:
            return self.async_abort(reason="no_contributions")
        if user_input is not None:
            self._delete_contribution_id = user_input[CONTRIBUTION_ID]
            self._delete_contribution_snapshot = next(
                (
                    item
                    for item in contributions
                    if item[CONTRIBUTION_ID] == self._delete_contribution_id
                ),
                None,
            )
            return await self.async_step_confirm_remove_contribution()
        return self.async_show_form(
            step_id="remove_contribution",
            data_schema=vol.Schema(
                {
                    vol.Required(CONTRIBUTION_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=self._contribution_options(),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_confirm_remove_contribution(self, user_input=None):
        contributions = self._contributions()
        contribution_id = self._delete_contribution_id
        removed = next(
            (
                item
                for item in contributions
                if item[CONTRIBUTION_ID] == contribution_id
            ),
            None,
        )
        if removed is None or removed != self._delete_contribution_snapshot:
            return self.async_abort(reason="stale_selection")
        if user_input is not None and user_input.get("confirm"):
            updated = [
                item
                for item in contributions
                if item[CONTRIBUTION_ID] != contribution_id
            ]
            if _worsened_cash_history(
                self.config_entry.data,
                {**self.config_entry.data, CONF_CONTRIBUTIONS: updated},
                dt_util.now().date(),
            ):
                return self.async_show_form(
                    step_id="confirm_remove_contribution",
                    data_schema=vol.Schema(
                        {vol.Required("confirm", default=False): bool}
                    ),
                    errors={"base": "cash_conflict"},
                    description_placeholders={
                        "contribution": self._contribution_label(removed),
                        "count": str(len(removed[CONTRIBUTION_LOTS])),
                        "lots": "\n".join(
                            f"- {self._position_label(lot[LOT_SYMBOL])} · "
                            f"{lot[LOT_DATE]} · {lot[LOT_AMOUNT]:.2f}"
                            for lot in removed[CONTRIBUTION_LOTS]
                        )
                        or "—",
                    },
                )
            extra: dict[str, Any] = {CONF_CONTRIBUTIONS: updated}
            if removed.get(CONTRIBUTION_PLAN_ID) and removed.get(
                CONTRIBUTION_SCHEDULED_DATE
            ):
                plan_id = removed[CONTRIBUTION_PLAN_ID]
                period = schedule_period(removed[CONTRIBUTION_SCHEDULED_DATE])
                for key, plans in (
                    (CONF_SAVINGS_PLANS, self._plans()),
                    (CONF_RETIRED_SAVINGS_PLANS, self._retired_plans()),
                ):
                    if not any(plan[PLAN_ID] == plan_id for plan in plans):
                        continue
                    extra[key] = [
                        normalize_plan(
                            {
                                **plan,
                                PLAN_SKIPPED_PERIODS: [
                                    *plan[PLAN_SKIPPED_PERIODS],
                                    period,
                                ],
                            }
                        )
                        if plan[PLAN_ID] == plan_id
                        else plan
                        for plan in plans
                    ]
            return await self._save(self._valors(), **extra)
        return self.async_show_form(
            step_id="confirm_remove_contribution",
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
            errors={"confirm": "confirmation_required"}
            if user_input is not None
            else {},
            description_placeholders={
                "contribution": self._contribution_label(removed),
                "count": str(len(removed[CONTRIBUTION_LOTS])),
                "lots": "\n".join(
                    f"- {self._position_label(lot[LOT_SYMBOL])} · "
                    f"{lot[LOT_DATE]} · {lot[LOT_AMOUNT]:.2f}"
                    for lot in removed[CONTRIBUTION_LOTS]
                )
                or "—",
            },
        )

    async def async_step_edit_lot(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Choose an automatically or manually tracked purchase lot."""
        if not all_lots(self.config_entry.data):
            return self.async_abort(reason="no_lots")
        if user_input is not None:
            self._edit_lot_id = user_input[LOT_ID]
            return await self.async_step_edit_lot_fields()
        return self.async_show_form(
            step_id="edit_lot",
            data_schema=vol.Schema(
                {
                    vol.Required(LOT_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=self._lot_options(),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_edit_lot_fields(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Correct execution date, invested amount, or purchased units."""
        lot_id = self._edit_lot_id
        contributions = self._contributions()
        current = next(
            (
                lot
                for contribution in contributions
                for lot in contribution[CONTRIBUTION_LOTS]
                if lot[LOT_ID] == lot_id
            ),
            None,
        )
        if current is None:
            return self.async_abort(reason="stale_selection")
        if current[LOT_SYMBOL] not in {valor[VALOR_SYMBOL] for valor in self._valors()}:
            return self.async_abort(reason="entry_changed")
        errors: dict[str, str] = {}
        if user_input is not None:
            amount = _finite_number(
                user_input.get(LOT_AMOUNT), minimum=0.01, maximum=_MAX_NUMBER
            )
            units = _finite_number(
                user_input.get(LOT_UNITS), minimum=0.000001, maximum=_MAX_NUMBER
            )
            try:
                if date.fromisoformat(str(user_input[LOT_DATE])) > dt_util.now().date():
                    errors[LOT_DATE] = "future_date"
            except (KeyError, ValueError):
                errors[LOT_DATE] = "invalid_input"
            if amount is None:
                errors[LOT_AMOUNT] = "invalid_number"
            if units is None:
                errors[LOT_UNITS] = "invalid_number"
            if not errors:
                fx_rate = float(current[LOT_FX_RATE])
                try:
                    replacement = make_lot(
                        symbol=current[LOT_SYMBOL],
                        execution_date=user_input[LOT_DATE],
                        amount=amount,
                        unit_price=amount / (units * fx_rate),
                        quote_currency=current[LOT_QUOTE_CURRENCY],
                        fx_rate=fx_rate,
                        units=units,
                        included_in_opening=bool(user_input[LOT_INCLUDED_IN_OPENING]),
                        estimated=False,
                        lot_id=lot_id,
                    )
                except (TypeError, ValueError, ZeroDivisionError):
                    errors["base"] = "invalid_input"
                else:
                    if replacement[LOT_INCLUDED_IN_OPENING] and (
                        self._included_lot_units(
                            replacement[LOT_SYMBOL], exclude_lot_id=lot_id
                        )
                        + float(replacement[LOT_UNITS])
                        > max(
                            self._opening_units(replacement[LOT_SYMBOL]),
                            self._included_lot_units(replacement[LOT_SYMBOL]),
                        )
                        + 1e-9
                    ):
                        errors[LOT_UNITS] = "included_units_exceeded"
                    else:
                        funding = next(
                            contribution
                            for contribution in contributions
                            if any(
                                lot[LOT_ID] == lot_id
                                for lot in contribution[CONTRIBUTION_LOTS]
                            )
                        )
                        funding_date = funding[CONTRIBUTION_DATE]
                        if (
                            funding[CONTRIBUTION_SOURCE] == CONTRIBUTION_SOURCE_LEGACY
                            and not replacement[LOT_INCLUDED_IN_OPENING]
                        ):
                            errors[LOT_INCLUDED_IN_OPENING] = "legacy_opening_required"
                        elif (
                            funding[CONTRIBUTION_SOURCE] != CONTRIBUTION_SOURCE_PURCHASE
                            and funding_date is not None
                            and date.fromisoformat(funding_date)
                            > date.fromisoformat(replacement[LOT_DATE])
                        ):
                            errors[LOT_DATE] = "contribution_date_after_lot"
                    if not errors:
                        try:
                            updated = normalize_contributions(
                                [
                                    {
                                        **contribution,
                                        CONTRIBUTION_LOTS: [
                                            replacement
                                            if lot[LOT_ID] == lot_id
                                            else lot
                                            for lot in contribution[CONTRIBUTION_LOTS]
                                        ],
                                        CONTRIBUTION_MANUALLY_EDITED: True,
                                        **(
                                            {
                                                CONTRIBUTION_DATE: min(
                                                    lot[LOT_DATE]
                                                    for lot in [
                                                        replacement
                                                        if lot[LOT_ID] == lot_id
                                                        else lot
                                                        for lot in contribution[
                                                            CONTRIBUTION_LOTS
                                                        ]
                                                    ]
                                                )
                                            }
                                            if contribution[CONTRIBUTION_SOURCE]
                                            == CONTRIBUTION_SOURCE_PURCHASE
                                            else {}
                                        ),
                                    }
                                    if contribution[CONTRIBUTION_ID]
                                    == funding[CONTRIBUTION_ID]
                                    else contribution
                                    for contribution in contributions
                                ]
                            )
                        except (TypeError, ValueError):
                            errors["base"] = "invalid_input"
                        else:
                            return await self._save(
                                self._valors(), **{CONF_CONTRIBUTIONS: updated}
                            )

        return self.async_show_form(
            step_id="edit_lot_fields",
            data_schema=vol.Schema(
                {
                    vol.Required(LOT_DATE, default=current[LOT_DATE]): _DATE_SELECTOR,
                    vol.Required(
                        LOT_AMOUNT, default=current[LOT_AMOUNT]
                    ): _CONTRIBUTION_AMOUNT_SELECTOR,
                    vol.Required(
                        LOT_UNITS, default=current[LOT_UNITS]
                    ): _UNITS_SELECTOR,
                    vol.Required(
                        LOT_INCLUDED_IN_OPENING,
                        default=current[LOT_INCLUDED_IN_OPENING],
                    ): bool,
                }
            ),
            description_placeholders={
                "lot": (
                    f"{current[LOT_DATE]} · {self._position_label(current[LOT_SYMBOL])}"
                )
            },
            errors=errors,
        )

    async def async_step_remove_plan(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Remove a plan without deleting its historical executions."""
        plans = self._plans()
        if not plans:
            return self.async_abort(reason="no_plans")
        if user_input is not None:
            plan_id = user_input[PLAN_ID]
            removed = next((plan for plan in plans if plan[PLAN_ID] == plan_id), None)
            if removed is None:
                return self.async_abort(reason="stale_selection")
            retired = [
                plan for plan in self._retired_plans() if plan[PLAN_ID] != plan_id
            ]
            retired.append(removed)
            return await self._save(
                self._valors(),
                **{
                    CONF_SAVINGS_PLANS: [
                        plan for plan in plans if plan[PLAN_ID] != plan_id
                    ],
                    CONF_RETIRED_SAVINGS_PLANS: retired,
                },
            )
        return self.async_show_form(
            step_id="remove_plan",
            data_schema=vol.Schema(
                {
                    vol.Required(PLAN_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=self._plan_options(),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_restore_execution(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Restore a previously skipped automatic monthly execution."""
        plans = self._plans()
        options = [
            {
                "value": f"{plan[PLAN_ID]}|{period}",
                "label": f"{plan[PLAN_NAME]} · {period}",
            }
            for plan in plans
            for period in plan[PLAN_SKIPPED_PERIODS]
            if is_scheduled_period(plan, period)
        ]
        if not options:
            return self.async_abort(reason="no_skipped_executions")
        if user_input is not None:
            valid_executions = {item["value"] for item in options}
            if user_input.get("execution") not in valid_executions:
                return self.async_show_form(
                    step_id="restore_execution",
                    data_schema=vol.Schema(
                        {
                            vol.Required("execution"): selector.SelectSelector(
                                selector.SelectSelectorConfig(
                                    options=options,
                                    mode=selector.SelectSelectorMode.DROPDOWN,
                                )
                            )
                        }
                    ),
                    errors={"execution": "invalid_plan"},
                )
            plan_id, period = str(user_input["execution"]).split("|", 1)
            updated = [
                normalize_plan(
                    {
                        **plan,
                        PLAN_SKIPPED_PERIODS: [
                            item
                            for item in plan[PLAN_SKIPPED_PERIODS]
                            if item != period
                        ],
                    }
                )
                if plan[PLAN_ID] == plan_id
                else plan
                for plan in plans
            ]
            return await self._save(self._valors(), **{CONF_SAVINGS_PLANS: updated})
        return self.async_show_form(
            step_id="restore_execution",
            data_schema=vol.Schema(
                {
                    vol.Required("execution"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_add_valor(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        valors = self._valors()
        schema = _valor_schema(
            user_input.get(VALOR_SYMBOL) if user_input else None,
            user_input.get(VALOR_AMOUNT) if user_input else None,
            user_input.get(VALOR_TARGET_SHARE) if user_input else None,
        )
        if user_input is not None:
            symbol = user_input[VALOR_SYMBOL].strip().upper()
            amount = _finite_number(
                user_input.get(VALOR_AMOUNT), minimum=0, maximum=_MAX_NUMBER
            )
            try:
                target = _normalize_target_share(user_input.get(VALOR_TARGET_SHARE))
            except ValueError:
                target = None
                errors[VALOR_TARGET_SHARE] = "invalid_number"
            if not symbol:
                errors[VALOR_SYMBOL] = "invalid_symbol"
            elif amount is None:
                errors[VALOR_AMOUNT] = "invalid_number"
            elif any(v[VALOR_SYMBOL] == symbol for v in valors):
                errors[VALOR_SYMBOL] = "symbol_exists"
            elif not errors:
                if target is not None and _target_sum_exceeded(valors, target):
                    errors[VALOR_TARGET_SHARE] = "target_sum_exceeded"
                else:
                    valor: dict[str, Any] = {
                        VALOR_SYMBOL: symbol,
                        VALOR_AMOUNT: amount,
                    }
                    if target is not None:
                        valor[VALOR_TARGET_SHARE] = target
                    valors.append(valor)
                    return await self._save(valors)
        return self.async_show_form(
            step_id="add_valor", data_schema=schema, errors=errors
        )

    async def async_step_remove_valor(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        valors = self._valors()
        if not valors:
            return self.async_abort(reason="no_valors")
        errors: dict[str, str] = {}
        if user_input is not None:
            symbol = user_input[VALOR_SYMBOL]
            if not any(valor[VALOR_SYMBOL] == symbol for valor in valors):
                return self.async_abort(reason="stale_selection")
            referenced = (
                any(
                    lot[LOT_SYMBOL] == symbol
                    for lot in all_lots(self.config_entry.data)
                )
                or any(
                    allocation[ALLOCATION_SYMBOL] == symbol
                    for plan in self._plans()
                    for allocation in plan[PLAN_ALLOCATIONS]
                )
                or any(
                    dividend.get(DIVIDEND_SYMBOL) == symbol
                    for dividend in self._dividends()
                )
            )
            if referenced:
                errors["base"] = "valor_in_use"
            else:
                return await self._save(
                    [v for v in valors if v[VALOR_SYMBOL] != symbol]
                )
        return self.async_show_form(
            step_id="remove_valor",
            data_schema=vol.Schema(
                {
                    vol.Required(VALOR_SYMBOL): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=self._position_options(),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_edit_valor(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask which valor to edit, then delegate to the fields step."""
        valors = self._valors()
        if not valors:
            return self.async_abort(reason="no_valors")
        if user_input is not None:
            self._edit_symbol = user_input[VALOR_SYMBOL]
            current = next(
                (v for v in valors if v[VALOR_SYMBOL] == self._edit_symbol), None
            )
            if current is None:
                return self.async_abort(reason="stale_selection")
            return self.async_show_form(
                step_id="edit_valor_fields",
                data_schema=_valor_fields_schema(
                    current[VALOR_AMOUNT], current.get(VALOR_TARGET_SHARE)
                ),
                description_placeholders={
                    VALOR_SYMBOL: self._position_label(self._edit_symbol)
                },
            )
        return self.async_show_form(
            step_id="edit_valor",
            data_schema=vol.Schema(
                {
                    vol.Required(VALOR_SYMBOL): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=self._position_options(),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_edit_valor_fields(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Apply the new amount / target share for the previously selected valor."""
        symbol = self._edit_symbol
        valors = self._valors()
        if not any(v[VALOR_SYMBOL] == symbol for v in valors):
            return self.async_abort(reason="stale_selection")
        if user_input is None:
            current = next(v for v in valors if v[VALOR_SYMBOL] == symbol)
            return self.async_show_form(
                step_id="edit_valor_fields",
                data_schema=_valor_fields_schema(
                    current[VALOR_AMOUNT], current.get(VALOR_TARGET_SHARE)
                ),
                description_placeholders={
                    VALOR_SYMBOL: self._position_label(str(symbol))
                },
            )
        amount = _finite_number(
            user_input.get(VALOR_AMOUNT), minimum=0, maximum=_MAX_NUMBER
        )
        if amount is None:
            return self.async_show_form(
                step_id="edit_valor_fields",
                data_schema=_valor_fields_schema(
                    user_input.get(VALOR_AMOUNT),
                    user_input.get(VALOR_TARGET_SHARE),
                ),
                description_placeholders={
                    VALOR_SYMBOL: self._position_label(str(symbol))
                },
                errors={VALOR_AMOUNT: "invalid_number"},
            )
        # A legacy conflict may need several corrections. Permit each step
        # that preserves or reduces it, but never create or enlarge a conflict.
        if amount + 1e-9 < min(
            self._included_lot_units(str(symbol)), self._opening_units(str(symbol))
        ):
            return self.async_show_form(
                step_id="edit_valor_fields",
                data_schema=_valor_fields_schema(
                    amount, user_input.get(VALOR_TARGET_SHARE)
                ),
                description_placeholders={
                    VALOR_SYMBOL: self._position_label(str(symbol))
                },
                errors={VALOR_AMOUNT: "included_units_exceeded"},
            )
        try:
            target = _normalize_target_share(user_input.get(VALOR_TARGET_SHARE))
        except ValueError:
            return self.async_show_form(
                step_id="edit_valor_fields",
                data_schema=_valor_fields_schema(
                    amount, user_input.get(VALOR_TARGET_SHARE)
                ),
                description_placeholders={
                    VALOR_SYMBOL: self._position_label(str(symbol))
                },
                errors={VALOR_TARGET_SHARE: "invalid_number"},
            )
        others = (v for v in valors if v[VALOR_SYMBOL] != symbol)
        if target is not None and _target_sum_exceeded(others, target):
            return self.async_show_form(
                step_id="edit_valor_fields",
                data_schema=_valor_fields_schema(
                    amount, user_input.get(VALOR_TARGET_SHARE)
                ),
                description_placeholders={
                    VALOR_SYMBOL: self._position_label(str(symbol))
                },
                errors={VALOR_TARGET_SHARE: "target_sum_exceeded"},
            )
        new_valors = []
        for v in valors:
            if v[VALOR_SYMBOL] != symbol:
                new_valors.append(v)
                continue
            item = dict(v)  # preserve keys we do not edit
            item[VALOR_AMOUNT] = amount
            if target is not None:
                item[VALOR_TARGET_SHARE] = target
            else:
                item.pop(VALOR_TARGET_SHARE, None)
            new_valors.append(item)
        return await self._save(new_valors)
