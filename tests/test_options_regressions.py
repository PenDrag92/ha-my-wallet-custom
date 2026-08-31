"""Focused regression tests for wallet option-flow persistence and validation."""

from __future__ import annotations

import asyncio
import sys
import types
import unittest
from datetime import datetime
from typing import Any

from tests.bootstrap import install_stubs

install_stubs()


class _Schema:
    def __init__(self, schema: dict[Any, Any]) -> None:
        self.schema = schema

    def extend(self, extra: dict[Any, Any]) -> _Schema:
        return _Schema({**self.schema, **extra})


vol = types.ModuleType("voluptuous")
vol.Marker = object
vol.Schema = _Schema
vol.Required = lambda key, **kwargs: key
vol.Optional = lambda key, **kwargs: key
vol.Any = lambda *values: values
sys.modules["voluptuous"] = vol


class _FlowBase:
    def async_show_progress(self, **kwargs):
        return {"type": "progress", **kwargs}

    def async_show_progress_done(self, **kwargs):
        return {"type": "progress_done", **kwargs}

    def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "form", **kwargs}

    def async_show_menu(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "menu", **kwargs}

    def async_create_entry(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "create_entry", **kwargs}

    def async_abort(self, **kwargs: Any) -> dict[str, Any]:
        return {"type": "abort", **kwargs}


class _ConfigFlow(_FlowBase):
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__()


class _OptionsFlow(_FlowBase):
    def __init__(self, entry: Any) -> None:
        self._config_entry = entry

    @property
    def config_entry(self) -> Any:
        return self._config_entry


config_entries = types.ModuleType("homeassistant.config_entries")
config_entries.ConfigEntry = object
config_entries.ConfigFlow = _ConfigFlow
config_entries.OptionsFlowWithConfigEntry = _OptionsFlow
sys.modules["homeassistant.config_entries"] = config_entries

core = types.ModuleType("homeassistant.core")
core.HomeAssistant = object
core.callback = lambda function: function
sys.modules["homeassistant.core"] = core

data_entry_flow = types.ModuleType("homeassistant.data_entry_flow")
data_entry_flow.FlowResult = dict
sys.modules["homeassistant.data_entry_flow"] = data_entry_flow


class _SelectorConfig(dict):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(kwargs)


class _Selector:
    def __init__(self, config: Any = None) -> None:
        self.config = config


selector = types.ModuleType("homeassistant.helpers.selector")
for name in ("SelectSelectorConfig", "NumberSelectorConfig"):
    setattr(selector, name, _SelectorConfig)
for name in ("SelectSelector", "NumberSelector", "DateSelector"):
    setattr(selector, name, _Selector)
selector.SelectSelectorMode = types.SimpleNamespace(DROPDOWN="dropdown")
selector.NumberSelectorMode = types.SimpleNamespace(BOX="box")

helpers = types.ModuleType("homeassistant.helpers")
helpers.selector = selector
sys.modules["homeassistant.helpers"] = helpers
sys.modules["homeassistant.helpers.selector"] = selector

aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
aiohttp_client.async_get_clientsession = lambda hass: object()
sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client

dt_module = types.ModuleType("homeassistant.util.dt")
dt_module.now = lambda: datetime(2026, 8, 31, 12)
util = types.ModuleType("homeassistant.util")
util.dt = dt_module
sys.modules["homeassistant.util"] = util
sys.modules["homeassistant.util.dt"] = dt_module

homeassistant = sys.modules["homeassistant"]
homeassistant.config_entries = config_entries
homeassistant.helpers = helpers

from custom_components.my_wallet import config_flow
from custom_components.my_wallet.const import (
    ALLOCATION_SYMBOL,
    ALLOCATION_VALUE,
    CONF_BASE_CURRENCY,
    CONF_CONTRIBUTIONS,
    CONF_DIVIDENDS,
    CONF_RETIRED_SAVINGS_PLANS,
    CONF_SAVINGS_PLANS,
    CONF_SCAN_INTERVAL,
    CONF_VALORS,
    CONF_WALLET_NAME,
    CONTRIBUTION_AMOUNT,
    CONTRIBUTION_DATE,
    CONTRIBUTION_ID,
    CONTRIBUTION_SOURCE_LEGACY,
    CONTRIBUTION_SOURCE_PLAN,
    LOT_AMOUNT,
    LOT_DATE,
    LOT_INCLUDED_IN_OPENING,
    LOT_SYMBOL,
    LOT_UNIT_PRICE,
    PLAN_ALLOCATION_MODE,
    PLAN_AMOUNT,
    PLAN_ENABLED,
    PLAN_FIRST_DATE,
    PLAN_ID,
    PLAN_NAME,
    PLAN_OPENING_CUTOFF_DATE,
    PLAN_SKIPPED_PERIODS,
    PLAN_USE_CASH_BALANCE,
    VALOR_AMOUNT,
    VALOR_SYMBOL,
)
from custom_components.my_wallet.contributions import make_contribution, make_lot
from custom_components.my_wallet.plans import make_plan


class _Entry:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.title = "Old wallet"
        self.entry_id = "entry-id"


class _EntryManager:
    def __init__(self) -> None:
        self.updates = 0
        self.reloads = 0

    def async_update_entry(
        self, entry: _Entry, *, data: dict[str, Any], title: str | None = None
    ) -> bool:
        self.updates += 1
        entry.data = data
        if title is not None:
            entry.title = title
        return True

    def async_schedule_reload(self, entry_id: str) -> None:
        self.reloads += 1


def _flow(data: dict[str, Any] | None = None) -> tuple[Any, _Entry, _EntryManager]:
    entry = _Entry(
        data
        or {
            CONF_WALLET_NAME: "Old wallet",
            CONF_BASE_CURRENCY: "EUR",
            CONF_SCAN_INTERVAL: 60,
            CONF_VALORS: [{VALOR_SYMBOL: "AAA", VALOR_AMOUNT: 10.0}],
            CONF_CONTRIBUTIONS: [],
            CONF_SAVINGS_PLANS: [],
            CONF_DIVIDENDS: [],
        }
    )
    manager = _EntryManager()
    flow = config_flow.MyWalletOptionsFlow(entry)
    flow.hass = types.SimpleNamespace(
        config_entries=manager,
        async_create_task=asyncio.create_task,
        config=types.SimpleNamespace(language="en"),
    )
    return flow, entry, manager


class OptionsFlowRegressionTests(unittest.IsolatedAsyncioTestCase):
    def test_flow_version_and_number_guard(self) -> None:
        self.assertEqual(config_flow.MyWalletConfigFlow.VERSION, 6)
        self.assertIsNone(config_flow._finite_number(float("nan")))
        self.assertIsNone(config_flow._finite_number(float("inf")))

    async def test_rename_updates_entry_title_once(self) -> None:
        flow, entry, manager = _flow()
        await flow.async_step_settings(
            {
                CONF_WALLET_NAME: "New wallet",
                CONF_BASE_CURRENCY: "EUR",
                CONF_SCAN_INTERVAL: 30,
            }
        )
        self.assertEqual(entry.title, "New wallet")
        self.assertEqual(entry.data[CONF_WALLET_NAME], "New wallet")
        self.assertEqual((manager.updates, manager.reloads), (1, 1))

    async def test_add_another_buffers_until_one_final_write(self) -> None:
        flow, entry, manager = _flow()
        first = await flow.async_step_add_contribution(
            {
                CONTRIBUTION_DATE: "2026-01-20",
                CONTRIBUTION_AMOUNT: 50,
                "add_another": True,
            }
        )
        self.assertEqual(first["type"], "form")
        self.assertEqual(entry.data[CONF_CONTRIBUTIONS], [])
        self.assertEqual((manager.updates, manager.reloads), (0, 0))

        await flow.async_step_add_contribution(
            {
                CONTRIBUTION_DATE: "2026-02-20",
                CONTRIBUTION_AMOUNT: 75,
                "add_another": False,
            }
        )
        self.assertEqual(len(entry.data[CONF_CONTRIBUTIONS]), 2)
        self.assertEqual((manager.updates, manager.reloads), (1, 1))

    async def test_invalid_contribution_number_is_a_form_error(self) -> None:
        flow, _, manager = _flow()
        result = await flow.async_step_add_contribution(
            {
                CONTRIBUTION_DATE: "2026-01-20",
                CONTRIBUTION_AMOUNT: float("nan"),
                "add_another": False,
            }
        )
        self.assertEqual(result["errors"][CONTRIBUTION_AMOUNT], "invalid_number")
        self.assertEqual((manager.updates, manager.reloads), (0, 0))

    async def test_contribution_date_cannot_move_after_retained_lot(self) -> None:
        lot = make_lot(
            symbol="AAA",
            execution_date="2026-01-10",
            amount=10,
            unit_price=1,
            quote_currency="EUR",
        )
        contribution = make_contribution(50, "2026-01-01", lots=[lot])
        flow, _, manager = _flow(
            {
                CONF_WALLET_NAME: "Wallet",
                CONF_BASE_CURRENCY: "EUR",
                CONF_SCAN_INTERVAL: 60,
                CONF_VALORS: [{VALOR_SYMBOL: "AAA", VALOR_AMOUNT: 10.0}],
                CONF_CONTRIBUTIONS: [contribution],
                CONF_SAVINGS_PLANS: [],
                CONF_DIVIDENDS: [],
            }
        )
        flow._edit_contribution_id = contribution[CONTRIBUTION_ID]
        result = await flow.async_step_edit_contribution_fields(
            {CONTRIBUTION_DATE: "2026-01-11", CONTRIBUTION_AMOUNT: 50}
        )
        self.assertEqual(
            result["errors"][CONTRIBUTION_DATE], "contribution_date_after_lot"
        )
        self.assertEqual((manager.updates, manager.reloads), (0, 0))

    async def test_add_lot_turns_attach_error_into_form_error(self) -> None:
        flow, _, manager = _flow()
        result = await flow.async_step_add_lot(
            {
                LOT_SYMBOL: "AAA",
                LOT_DATE: "2026-01-10",
                LOT_AMOUNT: 10,
                LOT_UNIT_PRICE: 1,
                LOT_INCLUDED_IN_OPENING: False,
                "funding_contribution": "missing",
            }
        )
        self.assertEqual(
            result["errors"]["funding_contribution"],
            "funding_contribution_invalid",
        )
        self.assertEqual((manager.updates, manager.reloads), (0, 0))

    async def test_future_opening_cutoff_is_rejected_for_new_plan(self) -> None:
        flow, _, manager = _flow()
        result = await flow.async_step_add_plan(
            {
                PLAN_NAME: "Plan",
                PLAN_ENABLED: True,
                PLAN_FIRST_DATE: "2026-09-20",
                PLAN_ALLOCATION_MODE: "percentage",
                PLAN_USE_CASH_BALANCE: True,
                PLAN_OPENING_CUTOFF_DATE: "2026-09-01",
            }
        )
        self.assertEqual(
            result["errors"][PLAN_OPENING_CUTOFF_DATE], "opening_cutoff_future"
        )
        self.assertEqual((manager.updates, manager.reloads), (0, 0))

    async def test_future_opening_cutoff_is_rejected_for_edited_plan(self) -> None:
        plan = make_plan(
            name="Plan",
            first_date="2026-01-20",
            allocation_mode="percentage",
            amount=50,
            allocations=[{ALLOCATION_SYMBOL: "AAA", ALLOCATION_VALUE: 100}],
            opening_cutoff_date="2026-01-01",
        )
        flow, _, manager = _flow(
            {
                CONF_WALLET_NAME: "Wallet",
                CONF_BASE_CURRENCY: "EUR",
                CONF_SCAN_INTERVAL: 60,
                CONF_VALORS: [{VALOR_SYMBOL: "AAA", VALOR_AMOUNT: 10.0}],
                CONF_CONTRIBUTIONS: [],
                CONF_SAVINGS_PLANS: [plan],
                CONF_DIVIDENDS: [],
            }
        )
        flow._working_plan_id = plan[PLAN_ID]
        result = await flow.async_step_edit_plan_fields(
            {
                PLAN_NAME: "Plan",
                PLAN_ENABLED: True,
                PLAN_FIRST_DATE: "2026-01-20",
                PLAN_ALLOCATION_MODE: "percentage",
                PLAN_AMOUNT: 50,
                PLAN_USE_CASH_BALANCE: True,
                PLAN_OPENING_CUTOFF_DATE: "2026-09-01",
                "keep_allocations": True,
            }
        )
        self.assertEqual(
            result["errors"][PLAN_OPENING_CUTOFF_DATE], "opening_cutoff_future"
        )
        self.assertEqual((manager.updates, manager.reloads), (0, 0))

    async def test_nonfinite_plan_allocation_is_a_form_error(self) -> None:
        flow, _, manager = _flow()
        flow._working_plan_fields = {
            PLAN_NAME: "Plan",
            PLAN_ENABLED: True,
            PLAN_FIRST_DATE: "2026-09-20",
            PLAN_ALLOCATION_MODE: "percentage",
            PLAN_AMOUNT: 50,
            PLAN_USE_CASH_BALANCE: True,
        }
        flow._working_allocations = []
        result = await flow.async_step_plan_allocation(
            {
                ALLOCATION_SYMBOL: "AAA",
                ALLOCATION_VALUE: float("nan"),
                "add_another": False,
            }
        )
        self.assertEqual(result["errors"][ALLOCATION_VALUE], "invalid_number")
        self.assertEqual((manager.updates, manager.reloads), (0, 0))

    async def test_removed_plan_keeps_identity_when_execution_is_deleted(self) -> None:
        plan = make_plan(
            name="Plan",
            first_date="2026-01-20",
            allocation_mode="percentage",
            amount=50,
            allocations=[{ALLOCATION_SYMBOL: "AAA", ALLOCATION_VALUE: 100}],
            plan_id="stable-plan-id",
        )
        contribution = make_contribution(
            50,
            "2026-01-20",
            source=CONTRIBUTION_SOURCE_PLAN,
            plan_id="stable-plan-id",
            scheduled_date="2026-01-20",
        )
        flow, entry, manager = _flow(
            {
                CONF_WALLET_NAME: "Wallet",
                CONF_BASE_CURRENCY: "EUR",
                CONF_SCAN_INTERVAL: 60,
                CONF_VALORS: [{VALOR_SYMBOL: "AAA", VALOR_AMOUNT: 10.0}],
                CONF_CONTRIBUTIONS: [contribution],
                CONF_SAVINGS_PLANS: [plan],
                CONF_RETIRED_SAVINGS_PLANS: [],
                CONF_DIVIDENDS: [],
            }
        )

        await flow.async_step_remove_plan({PLAN_ID: "stable-plan-id"})
        await flow.async_step_remove_contribution(
            {CONTRIBUTION_ID: contribution[CONTRIBUTION_ID]}
        )
        self.assertEqual(len(entry.data[CONF_CONTRIBUTIONS]), 1)
        await flow.async_step_confirm_remove_contribution({"confirm": True})

        self.assertEqual(entry.data[CONF_SAVINGS_PLANS], [])
        retired = entry.data[CONF_RETIRED_SAVINGS_PLANS]
        self.assertEqual(retired[0][PLAN_SKIPPED_PERIODS], ["2026-01"])

        flow._working_plan_id = None
        await flow._save_plan(
            make_plan(
                name="Plan",
                first_date="2026-01-20",
                allocation_mode="percentage",
                amount=50,
                allocations=[{ALLOCATION_SYMBOL: "AAA", ALLOCATION_VALUE: 100}],
                plan_id="new-random-id",
            )
        )
        self.assertEqual(entry.data[CONF_SAVINGS_PLANS], [])
        from unittest.mock import AsyncMock, patch

        from custom_components.my_wallet import plan_options

        async def prepare(data, **kwargs):
            return data, {"created": 0, "recalculated": 0, "pending": [], "failed": 0}

        with patch.object(
            plan_options, "async_prepare_executions", AsyncMock(side_effect=prepare)
        ):
            await flow.async_step_plan_confirm({"confirm": True})
            await flow._plan_task
            await flow.async_step_plan_progress()
        restored = entry.data[CONF_SAVINGS_PLANS][0]
        self.assertEqual(restored[PLAN_ID], "stable-plan-id")
        self.assertEqual(restored[PLAN_SKIPPED_PERIODS], ["2026-01"])
        self.assertEqual(entry.data[CONF_RETIRED_SAVINGS_PLANS], [])
        self.assertEqual((manager.updates, manager.reloads), (3, 3))

    async def test_edit_legacy_lot_cannot_clear_opening_marker(self) -> None:
        lot = make_lot(
            symbol="AAA",
            execution_date="2026-01-20",
            amount=50,
            unit_price=10,
            quote_currency="EUR",
            included_in_opening=True,
        )
        contribution = make_contribution(
            50,
            None,
            source=CONTRIBUTION_SOURCE_LEGACY,
            lots=[lot],
        )
        flow, _, manager = _flow(
            {
                CONF_WALLET_NAME: "Wallet",
                CONF_BASE_CURRENCY: "EUR",
                CONF_SCAN_INTERVAL: 60,
                CONF_VALORS: [{VALOR_SYMBOL: "AAA", VALOR_AMOUNT: 10.0}],
                CONF_CONTRIBUTIONS: [contribution],
                CONF_SAVINGS_PLANS: [],
                CONF_DIVIDENDS: [],
            }
        )
        flow._edit_lot_id = lot["id"]

        result = await flow.async_step_edit_lot_fields(
            {
                LOT_DATE: "2026-01-20",
                LOT_AMOUNT: 50,
                "units": 5,
                LOT_INCLUDED_IN_OPENING: False,
            }
        )

        self.assertEqual(
            result["errors"][LOT_INCLUDED_IN_OPENING], "legacy_opening_required"
        )
        self.assertEqual((manager.updates, manager.reloads), (0, 0))

    async def test_edit_lot_cannot_precede_funding_contribution(self) -> None:
        lot = make_lot(
            symbol="AAA",
            execution_date="2026-02-01",
            amount=50,
            unit_price=10,
            quote_currency="EUR",
        )
        contribution = make_contribution(50, "2026-02-01", lots=[lot])
        flow, _, manager = _flow(
            {
                CONF_WALLET_NAME: "Wallet",
                CONF_BASE_CURRENCY: "EUR",
                CONF_SCAN_INTERVAL: 60,
                CONF_VALORS: [{VALOR_SYMBOL: "AAA", VALOR_AMOUNT: 10.0}],
                CONF_CONTRIBUTIONS: [contribution],
                CONF_SAVINGS_PLANS: [],
                CONF_DIVIDENDS: [],
            }
        )
        flow._edit_lot_id = lot["id"]

        result = await flow.async_step_edit_lot_fields(
            {
                LOT_DATE: "2026-01-20",
                LOT_AMOUNT: 50,
                "units": 5,
                LOT_INCLUDED_IN_OPENING: False,
            }
        )

        self.assertEqual(result["errors"][LOT_DATE], "contribution_date_after_lot")
        self.assertEqual((manager.updates, manager.reloads), (0, 0))

    async def test_buffered_contributions_abort_after_currency_change(self) -> None:
        flow, entry, manager = _flow()
        await flow.async_step_add_contribution(
            {
                CONTRIBUTION_DATE: "2026-01-20",
                CONTRIBUTION_AMOUNT: 50,
                "add_another": True,
            }
        )
        concurrent = config_flow.MyWalletOptionsFlow(entry)
        concurrent.hass = types.SimpleNamespace(config_entries=manager)
        await concurrent.async_step_settings(
            {
                CONF_WALLET_NAME: "Wallet",
                CONF_BASE_CURRENCY: "USD",
                CONF_SCAN_INTERVAL: 60,
            }
        )

        result = await flow.async_step_add_contribution(
            {
                CONTRIBUTION_DATE: "2026-02-20",
                CONTRIBUTION_AMOUNT: 75,
                "add_another": False,
            }
        )

        self.assertEqual(result, {"type": "abort", "reason": "entry_changed"})
        self.assertEqual(entry.data[CONF_BASE_CURRENCY], "USD")
        self.assertEqual(entry.data[CONF_CONTRIBUTIONS], [])
        self.assertEqual((manager.updates, manager.reloads), (1, 1))

    async def test_stale_plan_allocation_symbol_is_rejected(self) -> None:
        flow, entry, manager = _flow()
        await flow.async_step_add_plan(
            {
                PLAN_NAME: "Plan",
                PLAN_ENABLED: True,
                PLAN_FIRST_DATE: "2026-09-20",
                PLAN_ALLOCATION_MODE: "percentage",
                PLAN_AMOUNT: 50,
                PLAN_USE_CASH_BALANCE: True,
            }
        )
        entry.data = {
            **entry.data,
            CONF_VALORS: [{VALOR_SYMBOL: "BBB", VALOR_AMOUNT: 10.0}],
        }

        result = await flow.async_step_plan_allocation(
            {
                ALLOCATION_SYMBOL: "AAA",
                ALLOCATION_VALUE: 100,
                "add_another": False,
            }
        )

        self.assertEqual(result["errors"][ALLOCATION_SYMBOL], "invalid_symbol")
        self.assertEqual(entry.data[CONF_SAVINGS_PLANS], [])
        self.assertEqual((manager.updates, manager.reloads), (0, 0))

    async def test_stale_lot_symbol_is_rejected(self) -> None:
        flow, entry, manager = _flow()
        entry.data = {
            **entry.data,
            CONF_VALORS: [{VALOR_SYMBOL: "BBB", VALOR_AMOUNT: 10.0}],
        }

        result = await flow.async_step_add_lot(
            {
                LOT_SYMBOL: "AAA",
                LOT_DATE: "2026-01-20",
                LOT_AMOUNT: 50,
                LOT_UNIT_PRICE: 10,
                LOT_INCLUDED_IN_OPENING: False,
            }
        )

        self.assertEqual(result["errors"][LOT_SYMBOL], "invalid_symbol")
        self.assertEqual(entry.data[CONF_CONTRIBUTIONS], [])
        self.assertEqual((manager.updates, manager.reloads), (0, 0))

    async def test_stale_remove_plan_id_aborts_without_writing(self) -> None:
        active = make_plan(
            name="Still active",
            first_date="2026-01-20",
            allocation_mode="percentage",
            amount=50,
            allocations=[{ALLOCATION_SYMBOL: "AAA", ALLOCATION_VALUE: 100}],
            plan_id="active-id",
        )
        flow, entry, manager = _flow(
            {
                CONF_WALLET_NAME: "Wallet",
                CONF_BASE_CURRENCY: "EUR",
                CONF_SCAN_INTERVAL: 60,
                CONF_VALORS: [{VALOR_SYMBOL: "AAA", VALOR_AMOUNT: 10.0}],
                CONF_CONTRIBUTIONS: [],
                CONF_SAVINGS_PLANS: [active],
                CONF_DIVIDENDS: [],
            }
        )

        result = await flow.async_step_remove_plan({PLAN_ID: "already-removed"})

        self.assertEqual(result, {"type": "abort", "reason": "stale_selection"})
        self.assertEqual(entry.data[CONF_SAVINGS_PLANS], [active])
        self.assertEqual((manager.updates, manager.reloads), (0, 0))


if __name__ == "__main__":
    unittest.main()
