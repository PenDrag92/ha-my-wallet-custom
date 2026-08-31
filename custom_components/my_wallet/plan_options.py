"""Guided savings-plan editing, explicit confirmation, and booking progress."""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

import voluptuous as vol
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from . import const as c
from .contributions import contributions_from_data
from .executions import (
    async_prepare_executions,
    is_manually_corrected,
    recalculable_ids,
)
from .plans import (
    change_plan_definition,
    make_plan,
    reactivate_matching_plan,
    scale_fixed_allocations,
)

_LOGGER = logging.getLogger(__name__)


class PlanOptionsMixin:
    """Keep network work out of the final atomic config-entry write."""

    _selected_plan_symbols: list[str] | None = None
    _plan_index: int = 0
    _plan_scope: str = "future"
    _proposed_plan: dict[str, Any] | None = None
    _plan_original: dict[str, Any] | None = None
    _plan_task: asyncio.Task | None = None
    _plan_snapshot: Any = None
    _plan_data: dict[str, Any] | None = None
    _plan_replace_ids: set[str] | None = None
    _plan_report: dict[str, Any] | None = None
    _plan_opening_review: bool = False

    async def async_step_add_plan(self, user_input=None):
        from . import config_flow as ui

        if not self._valors():
            return self.async_abort(reason="no_valors")
        if self._working_base_currency is None:
            self._working_base_currency = self.config_entry.data[c.CONF_BASE_CURRENCY]
        errors = {}
        if user_input is not None:
            fields = ui._plan_input(user_input)
            errors = ui._plan_field_errors(fields)
            if not errors:
                self._working_plan_id = None
                self._working_plan_fields = fields
                self._working_allocations = []
                self._selected_plan_symbols = None
                self._plan_index = 0
                self._plan_opening_review = False
                if fields.get("opening_included"):
                    return await self.async_step_plan_opening()
                return await self.async_step_plan_symbols()
        return self.async_show_form(
            step_id="add_plan", data_schema=ui._plan_schema(user_input), errors=errors
        )

    async def async_step_edit_plan(self, user_input=None):
        if not self._plans():
            return self.async_abort(reason="no_plans")
        if user_input is not None:
            self._working_plan_id = user_input[c.PLAN_ID]
            self._working_base_currency = self.config_entry.data[c.CONF_BASE_CURRENCY]
            return await self.async_step_edit_plan_fields()
        return self.async_show_form(
            step_id="edit_plan",
            data_schema=vol.Schema(
                {
                    vol.Required(c.PLAN_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=self._plan_options(),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_edit_plan_fields(self, user_input=None):
        from . import config_flow as ui

        current = next(
            (
                plan
                for plan in self._plans()
                if plan[c.PLAN_ID] == self._working_plan_id
            ),
            None,
        )
        if current is None:
            return self.async_abort(reason="stale_selection")
        if self._plan_original is None:
            self._plan_original = current
        errors = {}
        keep = True
        if user_input is not None:
            fields = ui._plan_input(user_input, current)
            keep = bool(fields.pop("keep_allocations", True))
            self._plan_scope = fields.pop("update_scope", "future")
            errors = ui._plan_field_errors(fields)
            if self._plan_scope not in ("future", "recalculate"):
                errors["update_scope"] = "invalid_input"
            if not errors:
                self._working_plan_fields = fields
                if (
                    keep
                    and fields[c.PLAN_ALLOCATION_MODE]
                    == current[c.PLAN_ALLOCATION_MODE]
                ):
                    allocations = current[c.PLAN_ALLOCATIONS]
                    try:
                        if (
                            fields[c.PLAN_ALLOCATION_MODE] == c.ALLOCATION_MODE_FIXED
                            and fields.get(c.PLAN_AMOUNT) is not None
                        ):
                            allocations = scale_fixed_allocations(
                                allocations, fields[c.PLAN_AMOUNT]
                            )
                        self._working_allocations = allocations
                        if fields.get("opening_included"):
                            self._plan_opening_review = True
                            return await self.async_step_plan_opening()
                        plan = make_plan(**self._plan_arguments(allocations))
                    except (TypeError, ValueError):
                        errors["base"] = "invalid_plan"
                    else:
                        return await self._save_plan(plan)
                else:
                    self._working_allocations = []
                    self._selected_plan_symbols = [
                        row[c.ALLOCATION_SYMBOL] for row in current[c.PLAN_ALLOCATIONS]
                    ]
                    self._plan_index = 0
                    self._plan_opening_review = False
                    if fields.get("opening_included"):
                        return await self.async_step_plan_opening()
                    return await self.async_step_plan_symbols()
        schema = ui._plan_schema(
            user_input if user_input is not None else current
        ).extend(
            {
                vol.Optional("keep_allocations", default=keep): bool,
                vol.Required(
                    "update_scope", default=self._plan_scope
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["future", "recalculate"],
                        translation_key="update_scope",
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="edit_plan_fields", data_schema=schema, errors=errors
        )

    async def async_step_plan_opening(self, user_input=None):
        from . import config_flow as ui

        fields = self._working_plan_fields
        errors = {}
        default = fields.get(c.PLAN_OPENING_CUTOFF_DATE)
        if user_input is not None:
            default = user_input.get(c.PLAN_OPENING_CUTOFF_DATE)
            try:
                cutoff = date.fromisoformat(str(default))
            except ValueError:
                errors[c.PLAN_OPENING_CUTOFF_DATE] = "invalid_input"
            else:
                if cutoff > dt_util.now().date():
                    errors[c.PLAN_OPENING_CUTOFF_DATE] = "opening_cutoff_future"
                else:
                    fields[c.PLAN_OPENING_CUTOFF_DATE] = cutoff.isoformat()
                    if self._plan_opening_review:
                        return await self._save_plan(
                            make_plan(**self._plan_arguments(self._working_allocations))
                        )
                    return await self.async_step_plan_symbols()
        return self.async_show_form(
            step_id="plan_opening",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        c.PLAN_OPENING_CUTOFF_DATE,
                        default=default or dt_util.now().date().isoformat(),
                    ): ui._DATE_SELECTOR
                }
            ),
            errors=errors,
        )

    async def async_step_plan_symbols(self, user_input=None):
        symbols = [valor[c.VALOR_SYMBOL] for valor in self._valors()]
        errors = {}
        if user_input is not None:
            selected = list(dict.fromkeys(user_input.get("symbols", [])))
            if not selected or any(symbol not in symbols for symbol in selected):
                errors["symbols"] = "invalid_symbol"
            else:
                self._selected_plan_symbols = selected
                self._working_allocations = []
                self._plan_index = 0
                return await self.async_step_plan_allocation()
        return self.async_show_form(
            step_id="plan_symbols",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "symbols", default=self._selected_plan_symbols or []
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=symbols,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            errors=errors,
        )

    def _plan_arguments(self, allocations):
        fields = self._working_plan_fields or {}
        current = next(
            (
                plan
                for plan in self._plans()
                if plan[c.PLAN_ID] == self._working_plan_id
            ),
            None,
        )
        return dict(
            name=fields[c.PLAN_NAME],
            first_date=fields[c.PLAN_FIRST_DATE],
            end_date=fields.get(c.PLAN_END_DATE),
            allocation_mode=fields[c.PLAN_ALLOCATION_MODE],
            amount=fields.get(c.PLAN_AMOUNT),
            allocations=allocations,
            enabled=fields.get(c.PLAN_ENABLED, True),
            plan_id=self._working_plan_id,
            use_cash_balance=fields.get(c.PLAN_USE_CASH_BALANCE, True),
            opening_cutoff_date=fields.get(c.PLAN_OPENING_CUTOFF_DATE),
            skipped_periods=current[c.PLAN_SKIPPED_PERIODS] if current else [],
        )

    async def async_step_plan_allocation(self, user_input=None):
        from . import config_flow as ui

        fields = self._working_plan_fields or {}
        selected = self._selected_plan_symbols or [
            valor[c.VALOR_SYMBOL] for valor in self._valors()
        ]
        if not selected:
            return self.async_abort(reason="entry_changed")
        if user_input and user_input.get("back_to_symbol") in selected:
            self._plan_index = selected.index(user_input["back_to_symbol"])
            return await self.async_step_plan_allocation()
        symbol = selected[self._plan_index]
        allocations = list(self._working_allocations or [])
        mode = fields.get(c.PLAN_ALLOCATION_MODE, c.ALLOCATION_MODE_PERCENTAGE)
        errors = {}
        if user_input is not None:
            submitted_symbol = user_input.get(c.ALLOCATION_SYMBOL, symbol)
            value = ui._finite_number(
                user_input.get(c.ALLOCATION_VALUE),
                minimum=0.01,
                maximum=100 if mode == c.ALLOCATION_MODE_PERCENTAGE else ui._MAX_NUMBER,
            )
            if submitted_symbol != symbol or symbol not in {
                valor[c.VALOR_SYMBOL] for valor in self._valors()
            }:
                errors[c.ALLOCATION_SYMBOL] = "invalid_symbol"
            elif value is None:
                errors[c.ALLOCATION_VALUE] = "invalid_number"
            else:
                row = {c.ALLOCATION_SYMBOL: symbol, c.ALLOCATION_VALUE: value}
                if self._plan_index < len(allocations):
                    allocations[self._plan_index] = row
                else:
                    allocations.append(row)
                if (
                    mode == c.ALLOCATION_MODE_PERCENTAGE
                    and sum(
                        row[c.ALLOCATION_VALUE]
                        for row in allocations[: self._plan_index + 1]
                    )
                    > 100.005
                ):
                    errors[c.ALLOCATION_VALUE] = "allocation_sum_exceeded"
                elif self._plan_index + 1 < len(selected):
                    self._working_allocations = allocations
                    self._plan_index += 1
                    return await self.async_step_plan_allocation()
                else:
                    try:
                        plan = make_plan(**self._plan_arguments(allocations))
                        if (
                            mode == c.ALLOCATION_MODE_FIXED
                            and fields.get(c.PLAN_AMOUNT) is not None
                            and abs(plan[c.PLAN_AMOUNT] - float(fields[c.PLAN_AMOUNT]))
                            > 0.005
                        ):
                            raise ValueError(
                                "Fixed amounts differ from the entered total"
                            )
                    except (TypeError, ValueError):
                        errors["base"] = "allocation_total_mismatch"
                    else:
                        self._working_allocations = allocations
                        return await self._save_plan(plan)
        default = (user_input or {}).get(c.ALLOCATION_VALUE)
        if default is None and self._plan_index < len(allocations):
            default = allocations[self._plan_index][c.ALLOCATION_VALUE]
        if (
            default is None
            and self._plan_original
            and self._plan_original[c.PLAN_ALLOCATION_MODE] == mode
        ):
            # Carry values over only while their unit (EUR or %) is unchanged.
            default = next(
                (
                    row[c.ALLOCATION_VALUE]
                    for row in self._plan_original[c.PLAN_ALLOCATIONS]
                    if row[c.ALLOCATION_SYMBOL] == symbol
                ),
                None,
            )
        marker = vol.Required(c.ALLOCATION_VALUE)
        if (
            ui._finite_number(
                default,
                minimum=0.01,
                maximum=100 if mode == c.ALLOCATION_MODE_PERCENTAGE else ui._MAX_NUMBER,
            )
            is not None
        ):
            marker = vol.Required(c.ALLOCATION_VALUE, default=default)
        return self.async_show_form(
            step_id="plan_allocation",
            data_schema=vol.Schema(
                {
                    marker: ui._PERCENT_SELECTOR
                    if mode == c.ALLOCATION_MODE_PERCENTAGE
                    else ui._CONTRIBUTION_AMOUNT_SELECTOR,
                    vol.Optional("back_to_symbol"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=selected,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "symbol": symbol,
                "index": str(self._plan_index + 1),
                "count": str(len(selected)),
                "current_total": str(
                    round(sum(row[c.ALLOCATION_VALUE] for row in allocations), 2)
                ),
                "unit": "%"
                if mode == c.ALLOCATION_MODE_PERCENTAGE
                else self.config_entry.data[c.CONF_BASE_CURRENCY],
            },
        )

    async def _save_plan(self, plan):
        """Stage a plan for review; no bookkeeping happens before confirmation."""
        if (
            self._working_base_currency is not None
            and self._working_base_currency
            != self.config_entry.data[c.CONF_BASE_CURRENCY]
        ):
            return self.async_abort(reason="entry_changed")
        if any(
            row[c.ALLOCATION_SYMBOL]
            not in {valor[c.VALOR_SYMBOL] for valor in self._valors()}
            for row in plan[c.PLAN_ALLOCATIONS]
        ):
            return self.async_abort(reason="entry_changed")
        if self._working_plan_id is None:
            plan, _ = reactivate_matching_plan(plan, self._retired_plans())
        elif not any(
            item[c.PLAN_ID] == self._working_plan_id for item in self._plans()
        ):
            return self.async_abort(reason="stale_selection")
        self._proposed_plan = plan
        return await self.async_step_plan_confirm()

    async def async_step_plan_confirm(self, user_input=None):
        plan = self._proposed_plan
        if plan is None:
            return self.async_abort(reason="stale_selection")
        rows = [
            row
            for row in self._contributions()
            if row.get(c.CONTRIBUTION_PLAN_ID) == plan[c.PLAN_ID]
        ]
        legacy = [
            row
            for row in rows
            if row.get(c.CONTRIBUTION_SOURCE) == c.CONTRIBUTION_SOURCE_PLAN
            and c.CONTRIBUTION_MANUALLY_EDITED not in row
            and not is_manually_corrected(row)
        ]
        errors = {}
        if user_input is not None:
            if not user_input.get("confirm"):
                errors["confirm"] = "confirmation_required"
            else:
                snapshot = self.config_entry.data
                current = next(
                    (
                        item
                        for item in self._plans()
                        if item[c.PLAN_ID] == self._working_plan_id
                    ),
                    None,
                )
                if (
                    self._working_base_currency is not None
                    and self._working_base_currency != snapshot[c.CONF_BASE_CURRENCY]
                ):
                    return self.async_abort(reason="entry_changed")
                if self._working_plan_id is not None and (
                    current is None
                    or self._plan_original is not None
                    and current != self._plan_original
                ):
                    return self.async_abort(reason="entry_changed")
                if any(
                    row[c.ALLOCATION_SYMBOL]
                    not in {valor[c.VALOR_SYMBOL] for valor in self._valors()}
                    for row in plan[c.PLAN_ALLOCATIONS]
                ):
                    return self.async_abort(reason="entry_changed")
                approved = user_input.get("legacy_executions", [])
                if not set(approved) <= {row[c.CONTRIBUTION_ID] for row in legacy}:
                    return self.async_abort(reason="stale_selection")
                recalculate = current is not None and self._plan_scope == "recalculate"
                final_plan = (
                    change_plan_definition(
                        current,
                        plan,
                        today=dt_util.now().date(),
                        recalculate=recalculate,
                    )
                    if current is not None
                    else plan
                )
                self._plan_snapshot = snapshot
                plans = [
                    final_plan if item[c.PLAN_ID] == final_plan[c.PLAN_ID] else item
                    for item in self._plans()
                ]
                if current is None:
                    plans.append(final_plan)
                self._plan_data = {
                    **snapshot,
                    c.CONF_SAVINGS_PLANS: plans,
                    c.CONF_RETIRED_SAVINGS_PLANS: [
                        item
                        for item in self._retired_plans()
                        if item[c.PLAN_ID] != final_plan[c.PLAN_ID]
                    ],
                }
                self._plan_replace_ids = (
                    recalculable_ids(
                        rows, plan[c.PLAN_ID], approved_legacy_ids=approved
                    )
                    if recalculate
                    else set()
                )
                self._plan_task = None
                return await self.async_step_plan_progress()
        schema = {vol.Required("confirm", default=False): bool}
        if legacy and self._plan_scope == "recalculate":
            schema[vol.Optional("legacy_executions", default=[])] = (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {
                                "value": row[c.CONTRIBUTION_ID],
                                "label": self._contribution_label(row),
                            }
                            for row in legacy
                        ],
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            )
        currency = self.config_entry.data[c.CONF_BASE_CURRENCY]
        unit = (
            "%"
            if plan[c.PLAN_ALLOCATION_MODE] == c.ALLOCATION_MODE_PERCENTAGE
            else currency
        )
        allocation = "\n".join(
            f"- {row[c.ALLOCATION_SYMBOL]}: {row[c.ALLOCATION_VALUE]:.2f} {unit}"
            for row in plan[c.PLAN_ALLOCATIONS]
        )
        return self.async_show_form(
            step_id="plan_confirm",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={
                "name": plan[c.PLAN_NAME],
                "amount": f"{plan[c.PLAN_AMOUNT]:.2f} {currency}",
                "first_date": plan[c.PLAN_FIRST_DATE],
                "allocations": allocation,
                "existing": str(len(rows)),
                "legacy": str(len(legacy)),
                "protected": str(sum(is_manually_corrected(row) for row in rows)),
                "scope": self._text(
                    "new_plan"
                    if self._working_plan_id is None
                    else "recalculate"
                    if self._plan_scope == "recalculate"
                    else "future"
                ),
            },
        )

    async def _async_plan_transaction(self):
        async with asyncio.timeout(90):
            data, report = await async_prepare_executions(
                self._plan_data,
                session=async_get_clientsession(self.hass),
                today=dt_util.now().date(),
                only_plan_id=self._proposed_plan[c.PLAN_ID],
                replace_ids=self._plan_replace_ids or (),
            )
        if self.config_entry.data is not self._plan_snapshot:
            raise ValueError("entry_changed")
        rows = contributions_from_data(self._plan_snapshot)
        report["protected"] = sum(
            row.get(c.CONTRIBUTION_PLAN_ID) == self._proposed_plan[c.PLAN_ID]
            and row[c.CONTRIBUTION_ID] not in (self._plan_replace_ids or ())
            for row in rows
        )
        data[c.CONF_LAST_PLAN_RESULT] = report
        self._update_entry(**data)
        return report

    async def async_step_plan_progress(self, user_input=None):
        if self._plan_task is None:
            self._plan_task = self.hass.async_create_task(
                self._async_plan_transaction()
            )
        if not self._plan_task.done():
            return self.async_show_progress(
                step_id="plan_progress",
                progress_action="book_plans",
                progress_task=self._plan_task,
            )
        try:
            self._plan_report = self._plan_task.result()
        except ValueError as err:
            self._plan_report = {
                "error": "entry_changed"
                if str(err) == "entry_changed"
                else "booking_failed"
            }
        except Exception:
            _LOGGER.exception("Could not prepare the savings-plan transaction")
            self._plan_report = {"error": "booking_failed"}
        return self.async_show_progress_done(next_step_id="plan_result")

    async def async_step_plan_result(self, user_input=None):
        report = self._plan_report or {}
        if "error" in report:
            return self.async_abort(reason=report["error"])
        if user_input is not None:
            return self.async_create_entry(title="", data={})
        details = (
            "\n".join(
                f"- {item.get('plan_name', self._proposed_plan[c.PLAN_NAME])} · "
                f"{item['scheduled_date']} · "
                f"{self._text(item.get('reason', 'booking_failed'))}"
                + (
                    " · "
                    + ", ".join(item.get("affected_symbols") or item["missing_symbols"])
                    if item.get("affected_symbols") or item.get("missing_symbols")
                    else ""
                )
                for item in report.get("pending", [])
            )
            or "—"
        )
        return self.async_show_form(
            step_id="plan_result",
            data_schema=vol.Schema({}),
            description_placeholders={
                "created": str(report.get("created", 0)),
                "recalculated": str(report.get("recalculated", 0)),
                "protected": str(report.get("protected", 0)),
                "pending": str(len(report.get("pending", []))),
                "failed": str(report.get("failed", 0)),
                "details": details,
                "rollback": self._text("rolled_back")
                if report.get("rolled_back")
                else "",
            },
        )
