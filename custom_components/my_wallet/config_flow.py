"""Config flow for My Wallet."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .const import (
    ALLOCATION_SYMBOL,
    CONF_BASE_CURRENCY,
    CONF_CONTRIBUTIONS,
    CONF_DIVIDENDS,
    CONF_EXPECTED_ANNUAL_INFLATION,
    CONF_EXPECTED_ANNUAL_RETURN,
    CONF_INFLATION_SOURCE,
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
    LOT_ID,
    LOT_INCLUDED_IN_OPENING,
    LOT_SYMBOL,
    LOT_UNITS,
    MAX_EXPECTED_ANNUAL_INFLATION,
    MAX_EXPECTED_ANNUAL_RETURN,
    MAX_SCAN_INTERVAL,
    MIN_EXPECTED_ANNUAL_INFLATION,
    MIN_EXPECTED_ANNUAL_RETURN,
    MIN_SCAN_INTERVAL,
    PLAN_ALLOCATIONS,
    PLAN_AMOUNT,
    PLAN_FIRST_DATE,
    PLAN_ID,
    PLAN_NAME,
    PLAN_SKIPPED_PERIODS,
    VALOR_AMOUNT,
    VALOR_SYMBOL,
    VALOR_TARGET_SHARE,
)
from .contributions import (
    all_lots,
    contributions_from_data,
    opening_balance_conflicts,
)
from .display import position_label, position_options
from .display import text as display_text
from .dividends import (
    dividends_from_data,
)
from .flow_schemas import (
    _CONTRIBUTION_AMOUNT_SELECTOR,
    _DATE_SELECTOR,
    _MAX_NUMBER,
    _UNITS_SELECTOR,
    _contribution_schema,
    _dividend_schema,
    _finite_number,
    _normalize_target_share,
    _settings_schema,
    _target_sum_exceeded,
    _valor_fields_schema,
    _valor_schema,
)
from .investment_options import InvestmentOptionsMixin
from .ledger import (
    CashPolicy,
    delete_contribution,
    delete_dividend,
    edit_contribution,
    edit_lot,
    put_dividend,
)
from .plan_options import PlanOptionsMixin
from .planning import is_plannable_deposit
from .plans import (
    execution_rules,
    is_scheduled_period,
    normalize_plan,
)
from .store import commit_wallet_change


def _booking_errors(error, fields=None):
    """Translate domain failures into existing form error keys."""
    reason = str(error)
    if reason == "future_date" and fields:
        errors = {
            key: reason
            for key in (
                DIVIDEND_BOOKING_DATE,
                DIVIDEND_VALUE_DATE,
                LOT_DATE,
                CONTRIBUTION_DATE,
            )
            if str(fields.get(key) or "") > dt_util.now().date().isoformat()
        }
        if errors:
            return errors
    return {
        "base": reason
        if reason
        in {
            "cash_conflict",
            "future_date",
            "invalid_symbol",
            "included_units_exceeded",
            "entry_changed",
            "stale_selection",
        }
        else "invalid_input"
    }


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
        cash_policy: CashPolicy = CashPolicy.PRESERVE,
        **extra: Any,
    ) -> None:
        snapshot = self.config_entry.data
        data = {**snapshot, **extra}
        if valors is not None:
            data[CONF_VALORS] = valors
        commit_wallet_change(
            self.hass,
            self.config_entry,
            data,
            snapshot=snapshot,
            today=dt_util.now().date(),
            title=entry_title,
            cash_policy=cash_policy,
        )

    async def _save(
        self,
        valors: list[dict[str, Any]],
        *,
        entry_title: str | None = None,
        cash_policy: CashPolicy = CashPolicy.PRESERVE,
        **extra: Any,
    ) -> FlowResult:
        self._update_entry(
            valors, entry_title=entry_title, cash_policy=cash_policy, **extra
        )
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
                        proposal = put_dividend(
                            self.config_entry.data,
                            {
                                "booking_date": user_input[DIVIDEND_BOOKING_DATE],
                                "value_date": user_input.get(DIVIDEND_VALUE_DATE),
                                "amount": amount,
                                "symbol": None if symbol == "__wallet__" else symbol,
                                "note": user_input.get(DIVIDEND_NOTE),
                            },
                            today=dt_util.now().date(),
                        )
                    except (TypeError, ValueError) as err:
                        errors.update(_booking_errors(err, user_input))
                    else:
                        return await self._save(**proposal)
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
                        proposal = put_dividend(
                            self.config_entry.data,
                            {
                                "booking_date": user_input[DIVIDEND_BOOKING_DATE],
                                "value_date": user_input.get(DIVIDEND_VALUE_DATE),
                                "amount": amount,
                                "symbol": None if symbol == "__wallet__" else symbol,
                                "note": user_input.get(DIVIDEND_NOTE),
                            },
                            today=dt_util.now().date(),
                            dividend_id=dividend_id,
                        )
                    except (TypeError, ValueError) as err:
                        errors.update(_booking_errors(err, user_input))
                    else:
                        return await self._save(**proposal)
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
        errors: dict[str, str] = {}
        if user_input is not None:
            dividend_id = user_input[DIVIDEND_ID]
            if not any(item[DIVIDEND_ID] == dividend_id for item in dividends):
                return self.async_abort(reason="stale_selection")
            try:
                proposal = delete_dividend(
                    self.config_entry.data, dividend_id, today=dt_util.now().date()
                )
            except ValueError as err:
                errors.update(_booking_errors(err))
            else:
                return await self._save(**proposal)
        return self.async_show_form(
            step_id="remove_dividend",
            errors=errors,
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
                    proposal = edit_contribution(
                        self.config_entry.data,
                        contribution_id,
                        amount=amount,
                        execution_date=execution_date,
                        note=user_input.get(CONTRIBUTION_NOTE),
                        today=dt_util.now().date(),
                    )
                except (TypeError, ValueError) as err:
                    errors.update(_booking_errors(err, user_input))
                else:
                    return await self._save(**proposal)
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
            try:
                proposal = delete_contribution(
                    self.config_entry.data, contribution_id, today=dt_util.now().date()
                )
            except ValueError as err:
                return self.async_show_form(
                    step_id="confirm_remove_contribution",
                    data_schema=vol.Schema(
                        {vol.Required("confirm", default=False): bool}
                    ),
                    errors=_booking_errors(err),
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
            return await self._save(**proposal)
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
                try:
                    proposal = edit_lot(
                        self.config_entry.data,
                        lot_id,
                        amount=amount,
                        units=units,
                        execution_date=user_input[LOT_DATE],
                        included_in_opening=bool(user_input[LOT_INCLUDED_IN_OPENING]),
                        today=dt_util.now().date(),
                    )
                except (TypeError, ValueError, ZeroDivisionError) as err:
                    field = {
                        "included_units_exceeded": LOT_UNITS,
                        "legacy_opening_required": LOT_INCLUDED_IN_OPENING,
                        "contribution_date_after_lot": LOT_DATE,
                    }.get(str(err))
                    if field:
                        errors[field] = str(err)
                    else:
                        errors.update(_booking_errors(err, user_input))
                else:
                    return await self._save(**proposal)

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
                    for plan in [*self._plans(), *self._retired_plans()]
                    for rule in execution_rules(plan)
                    for allocation in rule[PLAN_ALLOCATIONS]
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
