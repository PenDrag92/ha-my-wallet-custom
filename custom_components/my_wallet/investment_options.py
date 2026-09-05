"""Deposit-and-invest workflow and purchases from already available cash."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from . import const as c
from . import flow_schemas as ui
from .contributions import (
    make_contribution,
    make_lot,
    normalize_contributions,
)
from .dividends import cash_balance, reinvestable_cash
from .executions import (
    _included_opening_overflows,
    async_purchase_lot,
)
from .ledger import CashPolicy, book_purchase, prepare_change, worsened_cash_history
from .plans import allocation_amounts, make_plan

_LOGGER = logging.getLogger(__name__)


class InvestmentOptionsMixin:
    _investment_deposit: dict[str, Any] | None = None
    _investment_fields: dict[str, Any] | None = None
    _investment_rows: list[dict[str, Any]] | None = None
    _investment_index: int = 0
    _investment_task: asyncio.Task | None = None
    _investment_error: str | None = None
    _investment_snapshot: Any = None
    _investment_proposal: dict[str, Any] | None = None
    _lot_snapshot: Any = None
    _lot_proposal: dict[str, Any] | None = None
    _lot_to_confirm: dict[str, Any] | None = None

    async def async_step_add_contribution(self, user_input=None):
        return await self._async_contribution(user_input, planned=False)

    async def async_step_plan_contribution(self, user_input=None):
        return await self._async_contribution(user_input, planned=True)

    async def _async_contribution(self, user_input=None, *, planned=False):
        today = dt_util.now().date()
        default_date = today + timedelta(days=1) if planned else today
        currency = self.config_entry.data[c.CONF_BASE_CURRENCY]
        if self._pending_base_currency is None:
            self._pending_base_currency = currency
        errors = {}
        if user_input is not None:
            amount = ui._finite_number(
                user_input.get(c.CONTRIBUTION_AMOUNT),
                minimum=0.01,
                maximum=ui._MAX_NUMBER,
            )
            try:
                day = date.fromisoformat(
                    str(user_input.get(c.CONTRIBUTION_DATE) or default_date.isoformat())
                )
                if planned and day <= today:
                    errors[c.CONTRIBUTION_DATE] = "planned_date_required"
                if day > today and user_input.get("invest_now"):
                    errors["invest_now"] = "planned_investment"
            except ValueError:
                errors[c.CONTRIBUTION_DATE] = "invalid_input"
            if amount is None:
                errors[c.CONTRIBUTION_AMOUNT] = "invalid_number"
            if not errors:
                if self._pending_base_currency != currency:
                    return self.async_abort(reason="entry_changed")
                row = make_contribution(
                    amount, day, note=user_input.get(c.CONTRIBUTION_NOTE)
                )
                if user_input.get("invest_now"):
                    self._investment_deposit = row
                    self._investment_fields = None
                    self._investment_rows = []
                    self._investment_index = 0
                    self._investment_error = None
                    return await self.async_step_contribution_investment()
                self._pending_contributions = [
                    *(self._pending_contributions or []),
                    row,
                ]
                if user_input.get("add_another"):
                    return await self._async_contribution(planned=planned)
                rows = normalize_contributions(
                    [*self._contributions(), *self._pending_contributions]
                )
                self._pending_contributions = None
                self._pending_base_currency = None
                return await self._save(self._valors(), **{c.CONF_CONTRIBUTIONS: rows})
        values = user_input or {}
        schema = ui._contribution_schema(
            values.get(c.CONTRIBUTION_DATE, default_date.isoformat()),
            values.get(c.CONTRIBUTION_AMOUNT),
            values.get(c.CONTRIBUTION_NOTE),
        ).extend(
            {
                **(
                    {vol.Optional("invest_now", default=False): bool}
                    if not planned
                    else {}
                ),
                vol.Optional("add_another", default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="plan_contribution" if planned else "add_contribution",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_contribution_investment(self, user_input=None):
        if self._investment_deposit is None:
            return self.async_abort(reason="stale_selection")
        symbols = [valor[c.VALOR_SYMBOL] for valor in self._valors()]
        if not symbols:
            return self.async_abort(reason="no_valors")
        errors = {}
        values = user_input or self._investment_fields or {}
        if user_input is not None:
            chosen = list(dict.fromkeys(user_input.get("symbols", [])))
            if not chosen or any(symbol not in symbols for symbol in chosen):
                errors["symbols"] = "invalid_symbol"
            try:
                day = date.fromisoformat(
                    str(
                        user_input.get("execution_date")
                        or self._investment_deposit[c.CONTRIBUTION_DATE]
                    )
                )
                if day > dt_util.now().date():
                    errors["execution_date"] = "future_date"
                elif day.isoformat() < self._investment_deposit[c.CONTRIBUTION_DATE]:
                    errors["execution_date"] = "contribution_date_after_lot"
            except ValueError:
                errors["execution_date"] = "invalid_input"
            if user_input.get(c.PLAN_ALLOCATION_MODE) not in (
                c.ALLOCATION_MODE_PERCENTAGE,
                c.ALLOCATION_MODE_FIXED,
            ):
                errors[c.PLAN_ALLOCATION_MODE] = "invalid_input"
            if not errors:
                self._investment_fields = {
                    **user_input,
                    "symbols": chosen,
                    "execution_date": day.isoformat(),
                }
                self._investment_rows = []
                self._investment_index = 0
                return await self.async_step_contribution_allocation()
        schema = vol.Schema(
            {
                vol.Required(
                    "symbols", default=values.get("symbols", [])
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=self._position_options(symbols),
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    c.PLAN_ALLOCATION_MODE,
                    default=values.get(
                        c.PLAN_ALLOCATION_MODE, c.ALLOCATION_MODE_PERCENTAGE
                    ),
                ): ui._ALLOCATION_MODE_SELECTOR,
                vol.Required(
                    "execution_date",
                    default=values.get(
                        "execution_date", self._investment_deposit[c.CONTRIBUTION_DATE]
                    ),
                ): ui._DATE_SELECTOR,
                vol.Optional(
                    c.PLAN_USE_CASH_BALANCE,
                    default=values.get(c.PLAN_USE_CASH_BALANCE, False),
                ): bool,
                vol.Required(
                    c.LOT_INCLUDED_IN_OPENING,
                    default=values.get(c.LOT_INCLUDED_IN_OPENING, False),
                ): bool,
            }
        )
        return self.async_show_form(
            step_id="contribution_investment", data_schema=schema, errors=errors
        )

    async def async_step_contribution_allocation(self, user_input=None):
        fields = self._investment_fields
        if not fields:
            return self.async_abort(reason="stale_selection")
        symbols = fields["symbols"]
        if user_input and user_input.get("back_to_symbol") in symbols:
            self._investment_index = symbols.index(user_input["back_to_symbol"])
            return await self.async_step_contribution_allocation()
        symbol = symbols[self._investment_index]
        mode = fields[c.PLAN_ALLOCATION_MODE]
        rows = list(self._investment_rows or [])
        values = (
            user_input
            if user_input is not None
            else rows[self._investment_index]
            if self._investment_index < len(rows)
            else {}
        )
        errors = {"base": self._investment_error} if self._investment_error else {}
        self._investment_error = None
        if user_input is not None:
            errors = {}
            value = ui._finite_number(
                user_input.get(c.ALLOCATION_VALUE),
                minimum=0.01,
                maximum=100 if mode == c.ALLOCATION_MODE_PERCENTAGE else ui._MAX_NUMBER,
            )
            if value is None:
                errors[c.ALLOCATION_VALUE] = "invalid_number"
            try:
                day = date.fromisoformat(
                    str(user_input.get(c.LOT_DATE) or fields["execution_date"])
                )
                if day > dt_util.now().date():
                    errors[c.LOT_DATE] = "future_date"
                elif day.isoformat() < self._investment_deposit[c.CONTRIBUTION_DATE]:
                    errors[c.LOT_DATE] = "contribution_date_after_lot"
            except ValueError:
                errors[c.LOT_DATE] = "invalid_input"
            manual = {}
            for key in (c.LOT_UNIT_PRICE, c.LOT_UNITS):
                if user_input.get(key) not in (None, ""):
                    manual[key] = ui._finite_number(
                        user_input[key], minimum=0.000001, maximum=ui._MAX_NUMBER
                    )
                    if manual[key] is None:
                        errors[key] = "invalid_number"
            if len(manual) > 1:
                errors[c.LOT_UNITS] = "price_or_units"
            if not errors:
                row = {
                    c.ALLOCATION_SYMBOL: symbol,
                    c.ALLOCATION_VALUE: value,
                    c.LOT_DATE: day.isoformat(),
                    **manual,
                }
                if self._investment_index < len(rows):
                    rows[self._investment_index] = row
                else:
                    rows.append(row)
                total = sum(
                    row[c.ALLOCATION_VALUE]
                    for row in rows[: self._investment_index + 1]
                )
                if mode == c.ALLOCATION_MODE_PERCENTAGE and (
                    total > 100.005
                    or self._investment_index + 1 == len(symbols)
                    and abs(total - 100) > 0.005
                ):
                    errors[c.ALLOCATION_VALUE] = "allocation_total_mismatch"
                else:
                    self._investment_rows = rows
                    if self._investment_index + 1 == len(symbols):
                        self._investment_snapshot = self.config_entry.data
                        self._investment_task = None
                        return await self.async_step_investment_progress()
                    self._investment_index += 1
                    return await self.async_step_contribution_allocation()
        marker = vol.Required(c.ALLOCATION_VALUE)
        if (
            ui._finite_number(
                values.get(c.ALLOCATION_VALUE),
                minimum=0.01,
                maximum=100 if mode == c.ALLOCATION_MODE_PERCENTAGE else ui._MAX_NUMBER,
            )
            is not None
        ):
            marker = vol.Required(
                c.ALLOCATION_VALUE, default=values[c.ALLOCATION_VALUE]
            )
        schema = vol.Schema(
            {
                marker: ui._PERCENT_SELECTOR
                if mode == c.ALLOCATION_MODE_PERCENTAGE
                else ui._CONTRIBUTION_AMOUNT_SELECTOR,
                vol.Required(
                    c.LOT_DATE, default=values.get(c.LOT_DATE, fields["execution_date"])
                ): ui._DATE_SELECTOR,
                vol.Optional(
                    c.LOT_UNIT_PRICE,
                    description={"suggested_value": values.get(c.LOT_UNIT_PRICE)},
                ): vol.Any(None, ui._PRICE_SELECTOR),
                vol.Optional(
                    c.LOT_UNITS,
                    description={"suggested_value": values.get(c.LOT_UNITS)},
                ): vol.Any(None, ui._UNITS_SELECTOR),
                vol.Optional("back_to_symbol"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=self._position_options(symbols),
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="contribution_allocation",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "symbol": self._position_label(symbol),
                "index": str(self._investment_index + 1),
                "count": str(len(symbols)),
                "unit": "%"
                if mode == c.ALLOCATION_MODE_PERCENTAGE
                else self.config_entry.data[c.CONF_BASE_CURRENCY],
            },
        )

    async def _async_prepare_investment(self):
        rows = self._investment_rows
        fields = self._investment_fields
        deposit = self._investment_deposit
        data = self._investment_snapshot
        if self._pending_base_currency != data[c.CONF_BASE_CURRENCY] or any(
            symbol not in {valor[c.VALOR_SYMBOL] for valor in self._valors()}
            for symbol in fields["symbols"]
        ):
            return "entry_changed"
        base_rows = [*self._contributions(), *(self._pending_contributions or [])]
        base_data = {**data, c.CONF_CONTRIBUTIONS: base_rows}
        plan = make_plan(
            name="Allocation",
            first_date=deposit[c.CONTRIBUTION_DATE],
            amount=deposit[c.CONTRIBUTION_AMOUNT],
            allocation_mode=fields[c.PLAN_ALLOCATION_MODE],
            allocations=rows,
        )
        amounts = allocation_amounts(plan)
        session = async_get_clientsession(self.hass)
        async with asyncio.timeout(90):
            results = await asyncio.gather(
                *(
                    async_purchase_lot(
                        session=session,
                        symbol=row[c.ALLOCATION_SYMBOL],
                        requested_date=date.fromisoformat(row[c.LOT_DATE]),
                        amount=amounts[row[c.ALLOCATION_SYMBOL]],
                        base_currency=data[c.CONF_BASE_CURRENCY],
                        today=dt_util.now().date(),
                        included_in_opening=fields[c.LOT_INCLUDED_IN_OPENING],
                        manual_price=row.get(c.LOT_UNIT_PRICE),
                        units=row.get(c.LOT_UNITS),
                    )
                    for row in rows
                ),
                return_exceptions=True,
            )
        for index, result in enumerate(results):
            if isinstance(result, Exception):
                self._investment_index = index
                return (
                    str(result)
                    if isinstance(result, ValueError)
                    and str(result)
                    in {
                        "historical_price_unavailable",
                        "historical_fx_unavailable",
                        "future_date",
                        "price_or_units",
                    }
                    else "booking_failed"
                )
        earliest = min(date.fromisoformat(lot[c.LOT_DATE]) for lot in results)
        available = deposit[c.CONTRIBUTION_AMOUNT]
        if fields.get(c.PLAN_USE_CASH_BALANCE):
            available += reinvestable_cash(
                base_data, execution_through=earliest, today=dt_util.now().date()
            )
        if fields[c.PLAN_ALLOCATION_MODE] == c.ALLOCATION_MODE_PERCENTAGE:
            amounts = allocation_amounts(plan, available_amount=available)
        if sum(amounts.values()) > available + 1e-7:
            return "insufficient_cash"
        lots = []
        for row, quote in zip(rows, results, strict=True):
            amount = amounts[row[c.ALLOCATION_SYMBOL]]
            units = row.get(c.LOT_UNITS)
            lots.append(
                make_lot(
                    symbol=quote[c.LOT_SYMBOL],
                    execution_date=quote[c.LOT_DATE],
                    amount=amount,
                    unit_price=amount / units
                    if units is not None
                    else quote[c.LOT_UNIT_PRICE],
                    quote_currency=quote[c.LOT_QUOTE_CURRENCY],
                    fx_rate=quote[c.LOT_FX_RATE],
                    units=units,
                    included_in_opening=quote[c.LOT_INCLUDED_IN_OPENING],
                    estimated=quote[c.LOT_ESTIMATED],
                    lot_id=quote[c.LOT_ID],
                )
            )
        if _included_opening_overflows(data[c.CONF_VALORS], base_rows, lots):
            return "included_units_exceeded"
        combined = make_contribution(
            deposit[c.CONTRIBUTION_AMOUNT],
            deposit[c.CONTRIBUTION_DATE],
            contribution_id=deposit[c.CONTRIBUTION_ID],
            lots=lots,
            note=deposit.get(c.CONTRIBUTION_NOTE),
        )
        proposed = {
            **data,
            c.CONF_CONTRIBUTIONS: normalize_contributions([*base_rows, combined]),
        }
        if worsened_cash_history(base_data, proposed, dt_util.now().date()):
            return "insufficient_cash"
        self._investment_deposit = combined
        self._investment_proposal = prepare_change(
            data, proposed, today=dt_util.now().date()
        )
        return None

    async def async_step_investment_progress(self, user_input=None):
        if self._investment_task is None:
            self._investment_task = self.hass.async_create_task(
                self._async_prepare_investment()
            )
        if not self._investment_task.done():
            return self.async_show_progress(
                step_id="investment_progress",
                progress_action="prepare_purchases",
                progress_task=self._investment_task,
            )
        try:
            error = self._investment_task.result()
        except Exception:
            _LOGGER.exception("Could not prepare the investment transaction")
            error = "booking_failed"
        if (
            self.config_entry.data is not self._investment_snapshot
            or error == "entry_changed"
        ):
            return self.async_show_progress_done(next_step_id="investment_changed")
        if error:
            self._investment_error = error
            return self.async_show_progress_done(next_step_id="contribution_allocation")
        return self.async_show_progress_done(next_step_id="contribution_confirm")

    async def async_step_investment_changed(self, user_input=None):
        return self.async_abort(reason="entry_changed")

    async def async_step_contribution_confirm(self, user_input=None):
        if self._investment_proposal is None:
            return self.async_abort(reason="stale_selection")
        if user_input is not None and user_input.get("confirm"):
            if self.config_entry.data is not self._investment_snapshot:
                return self.async_abort(reason="entry_changed")
            self._pending_contributions = None
            self._pending_base_currency = None
            return await self._save(
                self._valors(),
                **{
                    c.CONF_CONTRIBUTIONS: self._investment_proposal[
                        c.CONF_CONTRIBUTIONS
                    ]
                },
            )
        currency = self.config_entry.data[c.CONF_BASE_CURRENCY]
        cash = cash_balance(self._investment_proposal, through=dt_util.now().date())
        return self.async_show_form(
            step_id="contribution_confirm",
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
            errors={"confirm": "confirmation_required"}
            if user_input is not None
            else {},
            description_placeholders={
                "deposit": self._contribution_label(self._investment_deposit),
                "lots": "\n".join(
                    f"- {self._position_label(lot[c.LOT_SYMBOL])} · "
                    f"{lot[c.LOT_DATE]} · "
                    f"{lot[c.LOT_AMOUNT]:.2f} {currency} · "
                    f"{lot[c.LOT_UNITS]:.6f} "
                    f"{self._text('estimated') if lot[c.LOT_ESTIMATED] else ''}"
                    for lot in self._investment_deposit[c.CONTRIBUTION_LOTS]
                ),
                "cash": f"{cash:.2f} {currency}",
            },
        )

    async def async_step_add_lot(self, user_input=None):
        symbols = [valor[c.VALOR_SYMBOL] for valor in self._valors()]
        if not symbols:
            return self.async_abort(reason="no_valors")
        errors = {}
        if user_input is not None:
            snapshot = self.config_entry.data
            symbol = user_input.get(c.LOT_SYMBOL)
            if symbol not in symbols:
                errors[c.LOT_SYMBOL] = "invalid_symbol"
            amount = ui._finite_number(
                user_input.get(c.LOT_AMOUNT), minimum=0.01, maximum=ui._MAX_NUMBER
            )
            if amount is None:
                errors[c.LOT_AMOUNT] = "invalid_number"
            try:
                day = date.fromisoformat(
                    str(user_input.get(c.LOT_DATE) or dt_util.now().date().isoformat())
                )
                if day > dt_util.now().date():
                    errors[c.LOT_DATE] = "future_date"
            except ValueError:
                errors[c.LOT_DATE] = "invalid_input"
            manual = {}
            for key in (c.LOT_UNIT_PRICE, c.LOT_UNITS):
                if user_input.get(key) not in (None, ""):
                    manual[key] = ui._finite_number(
                        user_input[key], minimum=0.000001, maximum=ui._MAX_NUMBER
                    )
                    if manual[key] is None:
                        errors[key] = "invalid_number"
            if len(manual) > 1:
                errors[c.LOT_UNITS] = "price_or_units"
            if not errors:
                try:
                    lot = await async_purchase_lot(
                        session=async_get_clientsession(self.hass),
                        symbol=symbol,
                        requested_date=day,
                        amount=amount,
                        base_currency=snapshot[c.CONF_BASE_CURRENCY],
                        today=dt_util.now().date(),
                        included_in_opening=bool(
                            user_input.get(c.LOT_INCLUDED_IN_OPENING, True)
                        ),
                        manual_price=manual.get(c.LOT_UNIT_PRICE),
                        units=manual.get(c.LOT_UNITS),
                    )
                except ValueError as err:
                    errors[c.LOT_UNIT_PRICE] = (
                        str(err)
                        if str(err)
                        in {
                            "historical_price_unavailable",
                            "historical_fx_unavailable",
                            "price_or_units",
                        }
                        else "invalid_input"
                    )
                else:
                    if self.config_entry.data is not snapshot:
                        return self.async_abort(reason="entry_changed")
                    if _included_opening_overflows(
                        self._valors(), self._contributions(), [lot]
                    ):
                        errors[c.LOT_INCLUDED_IN_OPENING] = "included_units_exceeded"
                    else:
                        funding = user_input.get("funding_contribution")
                        try:
                            proposal = book_purchase(
                                snapshot,
                                lot,
                                funding_id=funding,
                                today=dt_util.now().date(),
                                cash_policy=CashPolicy.CONFIRMED_PURCHASE,
                            )
                        except ValueError:
                            errors["funding_contribution"] = (
                                "funding_contribution_invalid"
                            )
                        else:
                            self._lot_snapshot = snapshot
                            self._lot_to_confirm = lot
                            self._lot_proposal = proposal
                            return await self.async_step_lot_confirm()
        return self.async_show_form(
            step_id="add_lot",
            data_schema=ui._manual_lot_schema(
                symbols,
                self._contribution_options(),
                user_input,
                self._position_options(symbols),
            ),
            errors=errors,
        )

    async def async_step_lot_confirm(self, user_input=None):
        if self._lot_proposal is None:
            return self.async_abort(reason="stale_selection")
        if user_input is not None and user_input.get("confirm"):
            if self.config_entry.data is not self._lot_snapshot:
                return self.async_abort(reason="entry_changed")
            return await self._save(
                self._valors(),
                cash_policy=CashPolicy.CONFIRMED_PURCHASE,
                **{c.CONF_CONTRIBUTIONS: self._lot_proposal[c.CONF_CONTRIBUTIONS]},
            )
        cash = cash_balance(self._lot_proposal, through=dt_util.now().date())
        estimate = (
            self._text("estimated") if self._lot_to_confirm[c.LOT_ESTIMATED] else ""
        )
        return self.async_show_form(
            step_id="lot_confirm",
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
            errors={"confirm": "confirmation_required"}
            if user_input is not None
            else {},
            description_placeholders={
                "lot": (
                    f"{self._position_label(self._lot_to_confirm[c.LOT_SYMBOL])} · "
                    f"{self._lot_to_confirm[c.LOT_DATE]} · "
                    f"{self._lot_to_confirm[c.LOT_AMOUNT]:.2f} "
                    f"{self.config_entry.data[c.CONF_BASE_CURRENCY]} · "
                    f"{self._lot_to_confirm[c.LOT_UNITS]:.6f} "
                    f"{estimate}"
                ),
                "cash": f"{cash:.2f} {self.config_entry.data[c.CONF_BASE_CURRENCY]}",
                "warning": self._text("cash_history_warning")
                if worsened_cash_history(
                    self._lot_snapshot, self._lot_proposal, dt_util.now().date()
                )
                else "",
            },
        )
