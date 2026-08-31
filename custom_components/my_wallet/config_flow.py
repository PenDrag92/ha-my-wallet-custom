"""Config flow for My Wallet."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
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
    CONF_INVESTED_AMOUNT,
    CONF_SAVINGS_PLANS,
    CONF_SCAN_INTERVAL,
    CONF_VALORS,
    CONF_WALLET_NAME,
    CONTRIBUTION_AMOUNT,
    CONTRIBUTION_DATE,
    CONTRIBUTION_ID,
    CONTRIBUTION_LOTS,
    CONTRIBUTION_PLAN_ID,
    CONTRIBUTION_SCHEDULED_DATE,
    CONTRIBUTION_SOURCE,
    DEFAULT_BASE_CURRENCY,
    DEFAULT_SCAN_INTERVAL,
    DIVIDEND_AMOUNT,
    DIVIDEND_BOOKING_DATE,
    DIVIDEND_ID,
    DIVIDEND_NOTE,
    DIVIDEND_SYMBOL,
    DIVIDEND_VALUE_DATE,
    DOMAIN,
    LOT_AMOUNT,
    LOT_DATE,
    LOT_FX_RATE,
    LOT_ID,
    LOT_INCLUDED_IN_OPENING,
    LOT_QUOTE_CURRENCY,
    LOT_SYMBOL,
    LOT_UNIT_PRICE,
    LOT_UNITS,
    MAX_SCAN_INTERVAL,
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
)
from .dividends import (
    dividends_from_data,
    make_dividend,
    normalize_dividends,
)
from .plans import make_plan, normalize_plan
from .yahoo import YahooError, fetch_history, fx_symbol

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
        options=[
            {
                "value": ALLOCATION_MODE_PERCENTAGE,
                "label": "Percentage / Prozentual",
            },
            {
                "value": ALLOCATION_MODE_FIXED,
                "label": "Fixed amounts / Feste Beträge",
            },
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)


def _valor_schema(
    symbol: str | None = None,
    amount: float | None = None,
    target_share: float | None = None,
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(VALOR_SYMBOL, default=symbol): str,
            vol.Required(VALOR_AMOUNT, default=amount): _AMOUNT_SELECTOR,
            # Suggested value (not default): an empty optional field is then
            # omitted from the submitted data instead of being sent as null.
            vol.Optional(
                VALOR_TARGET_SHARE, description={"suggested_value": target_share}
            ): vol.Any(None, _TARGET_SHARE_SELECTOR),
        }
    )


def _normalize_target_share(value: Any) -> float | None:
    """Return a target share in (0, 100] or None when no target is set."""
    if value is None:
        return None
    target = float(value)
    return target if target > 0 else None


def _targets_sum(valors: Iterable[dict[str, Any]]) -> float:
    """Sum of configured target shares."""
    return sum(float(v.get(VALOR_TARGET_SHARE) or 0) for v in valors)


def _target_sum_exceeded(others: Iterable[dict[str, Any]], target: float) -> bool:
    """Whether adding `target` on top of the other valors would exceed 100%."""
    return _targets_sum(others) + target > 100 + TARGET_SHARE_SUM_TOLERANCE


def _settings_schema(
    name: str | None = None,
    currency: str = DEFAULT_BASE_CURRENCY,
    interval: int = DEFAULT_SCAN_INTERVAL,
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_WALLET_NAME, default=name): str,
            vol.Required(CONF_BASE_CURRENCY, default=currency): _CURRENCY_SELECTOR,
            vol.Required(CONF_SCAN_INTERVAL, default=interval): _INTERVAL_SELECTOR,
        }
    )


def _contribution_schema(
    execution_date: str | None = None,
    amount: float | None = None,
) -> vol.Schema:
    """Build the form for one dated contribution."""
    date_marker: vol.Marker = vol.Required(CONTRIBUTION_DATE)
    amount_marker: vol.Marker = vol.Required(CONTRIBUTION_AMOUNT)
    if execution_date is not None:
        date_marker = vol.Required(CONTRIBUTION_DATE, default=execution_date)
    if amount is not None:
        amount_marker = vol.Required(CONTRIBUTION_AMOUNT, default=amount)
    return vol.Schema(
        {
            date_marker: _DATE_SELECTOR,
            amount_marker: _CONTRIBUTION_AMOUNT_SELECTOR,
        }
    )


def _plan_schema(plan: dict[str, Any] | None = None) -> vol.Schema:
    """Build the common savings-plan settings form."""
    is_new = plan is None
    plan = plan or {}
    end_date = plan.get(PLAN_END_DATE)
    amount = plan.get(PLAN_AMOUNT)
    return vol.Schema(
        {
            vol.Required(PLAN_NAME, default=plan.get(PLAN_NAME)): str,
            vol.Required(PLAN_ENABLED, default=plan.get(PLAN_ENABLED, True)): bool,
            vol.Required(
                PLAN_FIRST_DATE,
                default=plan.get(PLAN_FIRST_DATE),
            ): _DATE_SELECTOR,
            vol.Optional(
                PLAN_END_DATE, description={"suggested_value": end_date}
            ): vol.Any(None, _DATE_SELECTOR),
            vol.Required(
                PLAN_ALLOCATION_MODE,
                default=plan.get(PLAN_ALLOCATION_MODE, ALLOCATION_MODE_PERCENTAGE),
            ): _ALLOCATION_MODE_SELECTOR,
            vol.Optional(PLAN_AMOUNT, description={"suggested_value": amount}): vol.Any(
                None, _CONTRIBUTION_AMOUNT_SELECTOR
            ),
            vol.Required(
                PLAN_USE_CASH_BALANCE,
                default=plan.get(PLAN_USE_CASH_BALANCE, True),
            ): bool,
            vol.Optional(
                PLAN_OPENING_CUTOFF_DATE,
                description={
                    "suggested_value": plan.get(PLAN_OPENING_CUTOFF_DATE)
                    if not is_new
                    else dt_util.now().date().isoformat()
                },
            ): vol.Any(None, _DATE_SELECTOR),
        }
    )


def _allocation_schema(
    symbols: list[str],
    mode: str,
    symbol: str | None = None,
    value: float | None = None,
) -> vol.Schema:
    """Build one allocation row for a savings plan."""
    value_selector = (
        _PERCENT_SELECTOR
        if mode == ALLOCATION_MODE_PERCENTAGE
        else _CONTRIBUTION_AMOUNT_SELECTOR
    )
    symbol_marker: vol.Marker = vol.Required(ALLOCATION_SYMBOL)
    value_marker: vol.Marker = vol.Required(ALLOCATION_VALUE)
    if symbol is not None:
        symbol_marker = vol.Required(ALLOCATION_SYMBOL, default=symbol)
    if value is not None:
        value_marker = vol.Required(ALLOCATION_VALUE, default=value)
    return vol.Schema(
        {
            symbol_marker: selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=symbols,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            value_marker: value_selector,
            vol.Optional("add_another", default=True): bool,
        }
    )


def _manual_lot_schema(
    symbols: list[str], values: dict[str, Any] | None = None
) -> vol.Schema:
    """Build the form for importing one historical purchase lot."""
    values = values or {}
    return vol.Schema(
        {
            vol.Required(
                LOT_SYMBOL, default=values.get(LOT_SYMBOL)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=symbols,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(LOT_DATE, default=values.get(LOT_DATE)): _DATE_SELECTOR,
            vol.Required(
                LOT_AMOUNT, default=values.get(LOT_AMOUNT)
            ): _CONTRIBUTION_AMOUNT_SELECTOR,
            vol.Optional(
                LOT_UNIT_PRICE,
                description={"suggested_value": values.get(LOT_UNIT_PRICE)},
            ): vol.Any(None, _PRICE_SELECTOR),
            vol.Required(
                LOT_INCLUDED_IN_OPENING,
                default=values.get(LOT_INCLUDED_IN_OPENING, True),
            ): bool,
        }
    )


def _dividend_schema(
    symbols: list[str], dividend: dict[str, Any] | None = None
) -> vol.Schema:
    """Build the form for one net dividend credit."""
    dividend = dividend or {}
    source = dividend.get(DIVIDEND_SYMBOL, "__wallet__")
    source_options: list[dict[str, str]] = [
        {
            "value": "__wallet__",
            "label": "Portfolio / Quelle unbekannt",
        }
    ]
    source_options.extend({"value": symbol, "label": symbol} for symbol in symbols)
    return vol.Schema(
        {
            vol.Required(
                DIVIDEND_BOOKING_DATE,
                default=dividend.get(DIVIDEND_BOOKING_DATE),
            ): _DATE_SELECTOR,
            vol.Optional(
                DIVIDEND_VALUE_DATE,
                description={"suggested_value": dividend.get(DIVIDEND_VALUE_DATE)},
            ): vol.Any(None, _DATE_SELECTOR),
            vol.Required(
                DIVIDEND_AMOUNT,
                default=dividend.get(DIVIDEND_AMOUNT),
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

    VERSION = 3

    def __init__(self) -> None:
        self._valors: list[dict[str, Any]] = []
        self._name: str | None = None
        self._currency: str = DEFAULT_BASE_CURRENCY
        self._interval: int = DEFAULT_SCAN_INTERVAL

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: basic wallet settings."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_WALLET_NAME].strip()
            if not name:
                errors[CONF_WALLET_NAME] = "invalid_name"
            else:
                self._name = name
                self._currency = user_input[CONF_BASE_CURRENCY]
                self._interval = user_input[CONF_SCAN_INTERVAL]
                return await self.async_step_valor()
        return self.async_show_form(
            step_id="user",
            data_schema=_settings_schema(self._name, self._currency, self._interval),
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
            float(user_input[VALOR_AMOUNT]) if user_input else None,
            user_input.get(VALOR_TARGET_SHARE) if user_input else None,
        ).extend({vol.Optional("add_another", default=True): bool})
        if user_input is not None:
            symbol = user_input[VALOR_SYMBOL].strip().upper()
            amount = float(user_input[VALOR_AMOUNT])
            target = _normalize_target_share(user_input.get(VALOR_TARGET_SHARE))
            if not symbol:
                errors[VALOR_SYMBOL] = "invalid_symbol"
            elif any(v[VALOR_SYMBOL] == symbol for v in self._valors):
                errors[VALOR_SYMBOL] = "symbol_exists"
            elif target is not None and _target_sum_exceeded(self._valors, target):
                errors[VALOR_TARGET_SHARE] = "target_sum_exceeded"
            else:
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
            CONF_VALORS: self._valors,
            CONF_CONTRIBUTIONS: [],
            CONF_SAVINGS_PLANS: [],
            CONF_DIVIDENDS: [],
        }
        return self.async_create_entry(title=self._name or "Wallet", data=data)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> MyWalletOptionsFlow:
        return MyWalletOptionsFlow(config_entry)


class MyWalletOptionsFlow(config_entries.OptionsFlowWithConfigEntry):
    """Manage wallet settings, contributions, and valors."""

    _edit_symbol: str | None = None
    _edit_contribution_id: str | None = None
    _edit_lot_id: str | None = None
    _edit_dividend_id: str | None = None
    _working_plan_id: str | None = None
    _working_plan_fields: dict[str, Any] | None = None
    _working_allocations: list[dict[str, Any]] | None = None

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
        menu_options = [
            "settings",
            "add_contribution",
            "add_lot",
            "add_dividend",
        ]
        contributions = self._contributions()
        if contributions:
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
        menu_options.extend(["add_valor", "edit_valor", "remove_valor"])
        return self.async_show_menu(step_id="init", menu_options=menu_options)

    def _valors(self) -> list[dict[str, Any]]:
        return list(self.config_entry.data.get(CONF_VALORS, []))

    def _contributions(self) -> list[dict[str, Any]]:
        return contributions_from_data(self.config_entry.data)

    def _plans(self) -> list[dict[str, Any]]:
        return [
            normalize_plan(item)
            for item in self.config_entry.data.get(CONF_SAVINGS_PLANS, [])
        ]

    def _dividends(self) -> list[dict[str, Any]]:
        return dividends_from_data(self.config_entry.data)

    def _contribution_options(self) -> list[dict[str, str]]:
        currency = self.config_entry.data.get(CONF_BASE_CURRENCY, DEFAULT_BASE_CURRENCY)
        return [
            {
                "value": item[CONTRIBUTION_ID],
                "label": (
                    f"{item[CONTRIBUTION_DATE] or '—'} · "
                    f"{item[CONTRIBUTION_AMOUNT]:.2f} {currency}"
                ),
            }
            for item in self._contributions()
        ]

    def _lot_options(self) -> list[dict[str, str]]:
        currency = self.config_entry.data.get(CONF_BASE_CURRENCY, DEFAULT_BASE_CURRENCY)
        return [
            {
                "value": lot[LOT_ID],
                "label": (
                    f"{lot[LOT_DATE]} · {lot[LOT_SYMBOL]} · "
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
                    f"ab {plan[PLAN_FIRST_DATE]}"
                ),
            }
            for plan in self._plans()
        ]

    def _dividend_options(self) -> list[dict[str, str]]:
        currency = self.config_entry.data.get(CONF_BASE_CURRENCY, DEFAULT_BASE_CURRENCY)
        return [
            {
                "value": item[DIVIDEND_ID],
                "label": (
                    f"{item[DIVIDEND_BOOKING_DATE]} · "
                    f"{item.get(DIVIDEND_SYMBOL, 'Portfolio')} · "
                    f"{item[DIVIDEND_AMOUNT]:.2f} {currency}"
                ),
            }
            for item in self._dividends()
        ]

    def _update_entry(
        self, valors: list[dict[str, Any]] | None = None, **extra: Any
    ) -> None:
        """Write config-entry data and trigger the integration's reload listener."""
        data = dict(self.config_entry.data)
        if valors is not None:
            data[CONF_VALORS] = valors
        data.update(extra)
        if CONF_CONTRIBUTIONS in extra:
            data.pop(CONF_INVESTED_AMOUNT, None)
        self.hass.config_entries.async_update_entry(self.config_entry, data=data)

    async def _save(self, valors: list[dict[str, Any]], **extra: Any) -> FlowResult:
        self._update_entry(valors, **extra)
        return self.async_create_entry(title="", data={})

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_WALLET_NAME].strip()
            if not name:
                errors[CONF_WALLET_NAME] = "invalid_name"
            elif user_input[CONF_BASE_CURRENCY] != self.config_entry.data.get(
                CONF_BASE_CURRENCY, DEFAULT_BASE_CURRENCY
            ) and (self._contributions() or self._plans() or self._dividends()):
                errors[CONF_BASE_CURRENCY] = "currency_change_blocked"
            else:
                return await self._save(
                    self._valors(),
                    **{
                        CONF_WALLET_NAME: name,
                        CONF_BASE_CURRENCY: user_input[CONF_BASE_CURRENCY],
                        CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    },
                )
        data = self.config_entry.data
        return self.async_show_form(
            step_id="settings",
            data_schema=_settings_schema(
                data.get(CONF_WALLET_NAME, self.config_entry.title),
                data.get(CONF_BASE_CURRENCY, DEFAULT_BASE_CURRENCY),
                data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ),
            errors=errors,
        )

    async def async_step_add_dividend(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Record a net dividend credit on the broker cash account."""
        if user_input is not None:
            symbol = user_input.get(DIVIDEND_SYMBOL)
            dividend = make_dividend(
                booking_date=user_input[DIVIDEND_BOOKING_DATE],
                value_date=user_input.get(DIVIDEND_VALUE_DATE),
                amount=user_input[DIVIDEND_AMOUNT],
                symbol=None if symbol == "__wallet__" else symbol,
                note=user_input.get(DIVIDEND_NOTE),
            )
            return await self._save(
                self._valors(),
                **{CONF_DIVIDENDS: normalize_dividends([*self._dividends(), dividend])},
            )
        return self.async_show_form(
            step_id="add_dividend",
            data_schema=_dividend_schema(
                [valor[VALOR_SYMBOL] for valor in self._valors()]
            ),
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
        current = next(item for item in dividends if item[DIVIDEND_ID] == dividend_id)
        if user_input is not None:
            symbol = user_input.get(DIVIDEND_SYMBOL)
            replacement = make_dividend(
                booking_date=user_input[DIVIDEND_BOOKING_DATE],
                value_date=user_input.get(DIVIDEND_VALUE_DATE),
                amount=user_input[DIVIDEND_AMOUNT],
                symbol=None if symbol == "__wallet__" else symbol,
                note=user_input.get(DIVIDEND_NOTE),
                dividend_id=dividend_id,
            )
            return await self._save(
                self._valors(),
                **{
                    CONF_DIVIDENDS: normalize_dividends(
                        [
                            replacement if item[DIVIDEND_ID] == dividend_id else item
                            for item in dividends
                        ]
                    )
                },
            )
        return self.async_show_form(
            step_id="edit_dividend_fields",
            data_schema=_dividend_schema(
                [valor[VALOR_SYMBOL] for valor in self._valors()], current
            ),
            description_placeholders={
                "dividend": (
                    f"{current[DIVIDEND_BOOKING_DATE]} · {current[DIVIDEND_AMOUNT]:.2f}"
                )
            },
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

    async def async_step_add_contribution(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add one or more dated cash contributions."""
        schema = _contribution_schema(
            str(user_input[CONTRIBUTION_DATE])
            if user_input and user_input.get(CONTRIBUTION_DATE)
            else None,
            float(user_input[CONTRIBUTION_AMOUNT])
            if user_input and user_input.get(CONTRIBUTION_AMOUNT) is not None
            else None,
        ).extend({vol.Optional("add_another", default=False): bool})
        if user_input is not None:
            contribution = make_contribution(
                user_input[CONTRIBUTION_AMOUNT], user_input[CONTRIBUTION_DATE]
            )
            contributions = normalize_contributions(
                [*self._contributions(), contribution]
            )
            self._update_entry(self._valors(), **{CONF_CONTRIBUTIONS: contributions})
            if not user_input.get("add_another"):
                return self.async_create_entry(title="", data={})
            return self.async_show_form(
                step_id="add_contribution",
                data_schema=_contribution_schema().extend(
                    {vol.Optional("add_another", default=False): bool}
                ),
            )
        return self.async_show_form(step_id="add_contribution", data_schema=schema)

    async def async_step_edit_contribution(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Choose a contribution to edit."""
        if not self._contributions():
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
                            options=self._contribution_options(),
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
            item for item in contributions if item[CONTRIBUTION_ID] == contribution_id
        )
        if user_input is not None:
            replacement = make_contribution(
                user_input[CONTRIBUTION_AMOUNT],
                user_input[CONTRIBUTION_DATE],
                contribution_id=contribution_id,
                source=current[CONTRIBUTION_SOURCE],
                lots=current[CONTRIBUTION_LOTS],
                plan_id=current.get(CONTRIBUTION_PLAN_ID),
                scheduled_date=current.get(CONTRIBUTION_SCHEDULED_DATE),
            )
            updated = normalize_contributions(
                [
                    replacement if item[CONTRIBUTION_ID] == contribution_id else item
                    for item in contributions
                ]
            )
            return await self._save(self._valors(), **{CONF_CONTRIBUTIONS: updated})
        return self.async_show_form(
            step_id="edit_contribution_fields",
            data_schema=_contribution_schema(
                current[CONTRIBUTION_DATE], current[CONTRIBUTION_AMOUNT]
            ),
            description_placeholders={
                "contribution": (
                    f"{current[CONTRIBUTION_DATE] or '—'} · "
                    f"{current[CONTRIBUTION_AMOUNT]:.2f}"
                )
            },
        )

    async def async_step_remove_contribution(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Remove one dated contribution."""
        contributions = self._contributions()
        if not contributions:
            return self.async_abort(reason="no_contributions")
        if user_input is not None:
            contribution_id = user_input[CONTRIBUTION_ID]
            updated = [
                item
                for item in contributions
                if item[CONTRIBUTION_ID] != contribution_id
            ]
            return await self._save(self._valors(), **{CONF_CONTRIBUTIONS: updated})
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

    async def async_step_add_lot(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Import one historical purchase lot using Yahoo close or a manual price."""
        symbols = [valor[VALOR_SYMBOL] for valor in self._valors()]
        if not symbols:
            return self.async_abort(reason="no_valors")
        errors: dict[str, str] = {}
        if user_input is not None:
            symbol = user_input[LOT_SYMBOL]
            requested_date = date.fromisoformat(str(user_input[LOT_DATE]))
            amount = float(user_input[LOT_AMOUNT])
            manual_price = user_input.get(LOT_UNIT_PRICE)
            quote_date = requested_date
            quote_currency = self.config_entry.data.get(
                CONF_BASE_CURRENCY, DEFAULT_BASE_CURRENCY
            )
            fx_rate = 1.0
            estimated = manual_price is None
            unit_price = float(manual_price) if manual_price is not None else None

            if unit_price is None:
                today = dt_util.now().date()
                end_date = min(today, requested_date + timedelta(days=14))
                session = async_get_clientsession(self.hass)
                try:
                    history = await fetch_history(
                        session, symbol, requested_date, end_date
                    )
                except YahooError:
                    history = []
                if not history:
                    errors[LOT_UNIT_PRICE] = "historical_price_unavailable"
                else:
                    quote = history[0]
                    quote_date = quote.date
                    quote_currency = quote.currency
                    unit_price = quote.close
                    base_currency = self.config_entry.data.get(
                        CONF_BASE_CURRENCY, DEFAULT_BASE_CURRENCY
                    )
                    if quote_currency != base_currency:
                        try:
                            direct = await fetch_history(
                                session,
                                fx_symbol(quote_currency, base_currency),
                                quote_date,
                                min(today, quote_date + timedelta(days=7)),
                            )
                            inverse = await fetch_history(
                                session,
                                fx_symbol(base_currency, quote_currency),
                                quote_date,
                                min(today, quote_date + timedelta(days=7)),
                            )
                        except YahooError:
                            direct, inverse = [], []
                        if direct:
                            fx_rate = direct[0].close
                        elif inverse and inverse[0].close:
                            fx_rate = 1 / inverse[0].close
                        else:
                            errors[LOT_UNIT_PRICE] = "historical_fx_unavailable"

            if not errors and unit_price is not None:
                lot = make_lot(
                    symbol=symbol,
                    execution_date=quote_date,
                    amount=amount,
                    unit_price=unit_price,
                    quote_currency=quote_currency,
                    fx_rate=fx_rate,
                    included_in_opening=bool(user_input[LOT_INCLUDED_IN_OPENING]),
                    estimated=estimated,
                )
                contribution = make_contribution(
                    None,
                    quote_date,
                    lots=[lot],
                )
                return await self._save(
                    self._valors(),
                    **{
                        CONF_CONTRIBUTIONS: normalize_contributions(
                            [*self._contributions(), contribution]
                        )
                    },
                )

        return self.async_show_form(
            step_id="add_lot",
            data_schema=_manual_lot_schema(symbols, user_input),
            errors=errors,
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
            lot
            for contribution in contributions
            for lot in contribution[CONTRIBUTION_LOTS]
            if lot[LOT_ID] == lot_id
        )
        if user_input is not None:
            amount = float(user_input[LOT_AMOUNT])
            units = float(user_input[LOT_UNITS])
            fx_rate = float(current[LOT_FX_RATE])
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
            updated: list[dict[str, Any]] = []
            for contribution in contributions:
                lots = contribution[CONTRIBUTION_LOTS]
                if not any(lot[LOT_ID] == lot_id for lot in lots):
                    updated.append(contribution)
                    continue
                new_lots = [
                    replacement if lot[LOT_ID] == lot_id else lot for lot in lots
                ]
                updated.append(
                    make_contribution(
                        contribution[CONTRIBUTION_AMOUNT],
                        contribution[CONTRIBUTION_DATE],
                        contribution_id=contribution[CONTRIBUTION_ID],
                        source=contribution[CONTRIBUTION_SOURCE],
                        lots=new_lots,
                        plan_id=contribution.get(CONTRIBUTION_PLAN_ID),
                        scheduled_date=contribution.get(CONTRIBUTION_SCHEDULED_DATE),
                    )
                )
            return await self._save(
                self._valors(),
                **{CONF_CONTRIBUTIONS: normalize_contributions(updated)},
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
                "lot": f"{current[LOT_DATE]} · {current[LOT_SYMBOL]}"
            },
        )

    async def async_step_add_plan(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Start creating a monthly savings plan."""
        if not self._valors():
            return self.async_abort(reason="no_valors")
        if user_input is not None:
            self._working_plan_id = None
            self._working_plan_fields = dict(user_input)
            self._working_allocations = []
            return await self.async_step_plan_allocation()
        return self.async_show_form(step_id="add_plan", data_schema=_plan_schema())

    async def async_step_edit_plan(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Choose a savings plan to edit."""
        if not self._plans():
            return self.async_abort(reason="no_plans")
        if user_input is not None:
            self._working_plan_id = user_input[PLAN_ID]
            return await self.async_step_edit_plan_fields()
        return self.async_show_form(
            step_id="edit_plan",
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

    async def async_step_edit_plan_fields(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit settings and optionally rebuild plan allocations."""
        current = next(
            plan for plan in self._plans() if plan[PLAN_ID] == self._working_plan_id
        )
        if user_input is not None:
            keep_allocations = bool(user_input.pop("keep_allocations")) and (
                user_input[PLAN_ALLOCATION_MODE] == current[PLAN_ALLOCATION_MODE]
            )
            self._working_plan_fields = dict(user_input)
            if keep_allocations:
                try:
                    plan = make_plan(**self._plan_arguments(current[PLAN_ALLOCATIONS]))
                except ValueError:
                    return self.async_show_form(
                        step_id="edit_plan_fields",
                        data_schema=_plan_schema(self._working_plan_fields).extend(
                            {vol.Optional("keep_allocations", default=True): bool}
                        ),
                        errors={"base": "invalid_plan"},
                    )
                return await self._save_plan(plan)
            self._working_allocations = []
            return await self.async_step_plan_allocation()
        return self.async_show_form(
            step_id="edit_plan_fields",
            data_schema=_plan_schema(current).extend(
                {vol.Optional("keep_allocations", default=True): bool}
            ),
        )

    def _plan_arguments(self, allocations: list[dict[str, Any]]) -> dict[str, Any]:
        """Build validated make_plan keyword arguments from flow state."""
        fields = self._working_plan_fields or {}
        return {
            "name": fields[PLAN_NAME],
            "first_date": fields[PLAN_FIRST_DATE],
            "end_date": fields.get(PLAN_END_DATE),
            "allocation_mode": fields[PLAN_ALLOCATION_MODE],
            "amount": fields.get(PLAN_AMOUNT),
            "allocations": allocations,
            "enabled": bool(fields[PLAN_ENABLED]),
            "plan_id": self._working_plan_id,
            "use_cash_balance": bool(fields[PLAN_USE_CASH_BALANCE]),
            "opening_cutoff_date": fields.get(PLAN_OPENING_CUTOFF_DATE),
        }

    async def _save_plan(self, plan: dict[str, Any]) -> FlowResult:
        plans = self._plans()
        if self._working_plan_id is None:
            plans.append(plan)
        else:
            plans = [
                plan if item[PLAN_ID] == self._working_plan_id else item
                for item in plans
            ]
        return await self._save(self._valors(), **{CONF_SAVINGS_PLANS: plans})

    async def async_step_plan_allocation(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Collect one allocation row at a time and save the plan."""
        fields = self._working_plan_fields or {}
        allocations = self._working_allocations or []
        errors: dict[str, str] = {}
        if user_input is not None:
            symbol = user_input[ALLOCATION_SYMBOL]
            value = float(user_input[ALLOCATION_VALUE])
            if any(item[ALLOCATION_SYMBOL] == symbol for item in allocations):
                errors[ALLOCATION_SYMBOL] = "allocation_exists"
            elif (
                fields[PLAN_ALLOCATION_MODE] == ALLOCATION_MODE_PERCENTAGE
                and sum(item[ALLOCATION_VALUE] for item in allocations) + value
                > 100.005
            ):
                errors[ALLOCATION_VALUE] = "allocation_sum_exceeded"
            else:
                allocations.append(
                    {
                        ALLOCATION_SYMBOL: symbol,
                        ALLOCATION_VALUE: value,
                    }
                )
                self._working_allocations = allocations
                remaining_symbols = [
                    valor[VALOR_SYMBOL]
                    for valor in self._valors()
                    if valor[VALOR_SYMBOL]
                    not in {item[ALLOCATION_SYMBOL] for item in allocations}
                ]
                percentage_complete = (
                    fields[PLAN_ALLOCATION_MODE] == ALLOCATION_MODE_PERCENTAGE
                    and abs(sum(item[ALLOCATION_VALUE] for item in allocations) - 100)
                    <= 0.005
                )
                should_finish = (
                    not user_input.get("add_another")
                    or not remaining_symbols
                    or percentage_complete
                )
                if should_finish:
                    try:
                        plan = make_plan(**self._plan_arguments(allocations))
                    except ValueError:
                        errors["base"] = "invalid_plan"
                    else:
                        return await self._save_plan(plan)
                if not errors:
                    return self.async_show_form(
                        step_id="plan_allocation",
                        data_schema=_allocation_schema(
                            remaining_symbols,
                            fields[PLAN_ALLOCATION_MODE],
                        ),
                        description_placeholders={
                            "current_total": str(
                                round(
                                    sum(item[ALLOCATION_VALUE] for item in allocations),
                                    2,
                                )
                            )
                        },
                    )
        available_symbols = [
            valor[VALOR_SYMBOL]
            for valor in self._valors()
            if valor[VALOR_SYMBOL]
            not in {item[ALLOCATION_SYMBOL] for item in allocations}
        ]
        if not available_symbols and errors:
            return self.async_abort(reason="invalid_plan")
        prefill = (
            user_input
            if user_input
            and (ALLOCATION_SYMBOL in errors or ALLOCATION_VALUE in errors)
            else None
        )
        return self.async_show_form(
            step_id="plan_allocation",
            data_schema=_allocation_schema(
                available_symbols,
                fields.get(PLAN_ALLOCATION_MODE, ALLOCATION_MODE_PERCENTAGE),
                prefill.get(ALLOCATION_SYMBOL) if prefill else None,
                float(prefill[ALLOCATION_VALUE])
                if prefill and prefill.get(ALLOCATION_VALUE) is not None
                else None,
            ),
            errors=errors,
            description_placeholders={
                "current_total": str(
                    round(
                        sum(item[ALLOCATION_VALUE] for item in allocations),
                        2,
                    )
                )
            },
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
            return await self._save(
                self._valors(),
                **{
                    CONF_SAVINGS_PLANS: [
                        plan for plan in plans if plan[PLAN_ID] != plan_id
                    ]
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

    async def async_step_add_valor(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        valors = self._valors()
        schema = _valor_schema(
            user_input.get(VALOR_SYMBOL) if user_input else None,
            float(user_input[VALOR_AMOUNT]) if user_input else None,
            user_input.get(VALOR_TARGET_SHARE) if user_input else None,
        )
        if user_input is not None:
            symbol = user_input[VALOR_SYMBOL].strip().upper()
            if not symbol:
                errors[VALOR_SYMBOL] = "invalid_symbol"
            elif any(v[VALOR_SYMBOL] == symbol for v in valors):
                errors[VALOR_SYMBOL] = "symbol_exists"
            else:
                target = _normalize_target_share(user_input.get(VALOR_TARGET_SHARE))
                if target is not None and _target_sum_exceeded(valors, target):
                    errors[VALOR_TARGET_SHARE] = "target_sum_exceeded"
                else:
                    valor: dict[str, Any] = {
                        VALOR_SYMBOL: symbol,
                        VALOR_AMOUNT: float(user_input[VALOR_AMOUNT]),
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
                            options=[v[VALOR_SYMBOL] for v in valors],
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
            current = next(v for v in valors if v[VALOR_SYMBOL] == self._edit_symbol)
            return self.async_show_form(
                step_id="edit_valor_fields",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            VALOR_AMOUNT, default=current[VALOR_AMOUNT]
                        ): _AMOUNT_SELECTOR,
                        # Clearing the field removes the target share.
                        vol.Optional(
                            VALOR_TARGET_SHARE,
                            description={
                                "suggested_value": current.get(VALOR_TARGET_SHARE)
                            },
                        ): vol.Any(None, _TARGET_SHARE_SELECTOR),
                    }
                ),
                description_placeholders={VALOR_SYMBOL: self._edit_symbol},
            )
        return self.async_show_form(
            step_id="edit_valor",
            data_schema=vol.Schema(
                {
                    vol.Required(VALOR_SYMBOL): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[v[VALOR_SYMBOL] for v in valors],
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
        target = _normalize_target_share(user_input.get(VALOR_TARGET_SHARE))
        others = (v for v in valors if v[VALOR_SYMBOL] != symbol)
        if target is not None and _target_sum_exceeded(others, target):
            return self.async_show_form(
                step_id="edit_valor_fields",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            VALOR_AMOUNT, default=float(user_input[VALOR_AMOUNT])
                        ): _AMOUNT_SELECTOR,
                        vol.Optional(
                            VALOR_TARGET_SHARE,
                            description={
                                "suggested_value": user_input.get(VALOR_TARGET_SHARE)
                            },
                        ): vol.Any(None, _TARGET_SHARE_SELECTOR),
                    }
                ),
                description_placeholders={VALOR_SYMBOL: symbol},
                errors={VALOR_TARGET_SHARE: "target_sum_exceeded"},
            )
        new_valors = []
        for v in valors:
            if v[VALOR_SYMBOL] != symbol:
                new_valors.append(v)
                continue
            item = dict(v)  # preserve keys we do not edit
            item[VALOR_AMOUNT] = float(user_input[VALOR_AMOUNT])
            if target is not None:
                item[VALOR_TARGET_SHARE] = target
            else:
                item.pop(VALOR_TARGET_SHARE, None)
            new_valors.append(item)
        return await self._save(new_valors)
