"""Recover conflicting legacy quantities without inventing or deleting holdings."""

from __future__ import annotations

import copy
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tests.bootstrap import install_stubs

install_stubs()

from custom_components.my_wallet import executions
from custom_components.my_wallet.contributions import (
    additional_units,
    all_lots,
    make_contribution,
    make_lot,
    opening_balance_conflicts,
)
from custom_components.my_wallet.dividends import cash_balance
from custom_components.my_wallet.history import build_history
from custom_components.my_wallet.plans import make_plan
from custom_components.my_wallet.yahoo import HistoricalQuote

try:
    from test_market_regressions import WalletCoordinator
except ModuleNotFoundError:  # Package-style test invocation.
    from tests.test_market_regressions import WalletCoordinator
try:
    from test_migration_regressions import _Entry, _Hass, migration
    from test_options_regressions import _flow
    from test_panel_regressions import Connection, hass_with, panel
except ModuleNotFoundError:  # Package-style test invocation.
    from tests.test_migration_regressions import _Entry, _Hass, migration
    from tests.test_options_regressions import _flow
    from tests.test_panel_regressions import Connection, hass_with, panel


def conflicting_wallet():
    """Synthetic old wallet: two included lots exceed the recorded opening."""
    return {
        "wallet_name": "Synthetic recovery example",
        "base_currency": "EUR",
        "valors": [{"symbol": "AAA", "amount": 2.0}],
        "dividends": [],
        "contributions": [
            make_contribution(
                40,
                None,
                contribution_id="funding",
                source="legacy",
                lots=[
                    make_lot(
                        symbol="AAA",
                        execution_date=f"2026-01-{day}",
                        amount=20,
                        unit_price=10,
                        units=2,
                        quote_currency="EUR",
                        included_in_opening=True,
                        estimated=False,
                        lot_id=f"lot-{index}",
                    )
                    for index, day in enumerate((20, 21))
                ],
            )
        ],
        "savings_plans": [
            make_plan(
                plan_id="plan",
                name="Synthetic monthly plan",
                first_date="2026-02-20",
                end_date="2026-02-20",
                amount=10,
                allocation_mode="percentage",
                allocations=[{"symbol": "AAA", "value": 100}],
                use_cash_balance=False,
            )
        ],
    }


class OpeningRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_automatic_refresh_keeps_every_record_and_pauses_booking(self):
        data = conflicting_wallet()
        original = copy.deepcopy(data)
        manager = SimpleNamespace(
            async_update_entry=lambda *_a, **_k: self.fail("Unexpected write")
        )
        entry = SimpleNamespace(entry_id="wallet", data=data, title="Synthetic wallet")
        coordinator = WalletCoordinator(SimpleNamespace(config_entries=manager), entry)
        with patch.object(executions, "fetch_histories", AsyncMock()) as fetch:
            pending = await coordinator._async_book_due_plans(
                object(), {}, date(2026, 2, 20)
            )
        fetch.assert_not_awaited()
        self.assertIs(entry.data, data)
        self.assertEqual(entry.data, original)
        self.assertEqual(additional_units(data, "AAA"), 0)
        self.assertEqual(cash_balance(data), 0)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["reason"], "opening_balance_conflict")
        self.assertEqual(pending[0]["affected_symbols"], ["AAA"])
        self.assertTrue(pending[0]["repair_required"])

    async def test_recalculation_cannot_delete_conflicting_old_rows(self):
        data = conflicting_wallet()
        data["savings_plans"][0]["first_date"] = "2026-01-20"
        data["savings_plans"][0]["end_date"] = "2026-01-20"
        row = data["contributions"][0]
        row.update(
            source="savings_plan",
            date="2026-01-20",
            plan_id="plan",
            scheduled_date="2026-01-20",
            manually_edited=False,
        )
        for lot in row["lots"]:
            lot["estimated"] = True
        original = copy.deepcopy(data)
        with patch.object(executions, "fetch_histories", AsyncMock()) as fetch:
            result, report = await executions.async_prepare_executions(
                data,
                session=object(),
                today=date(2026, 2, 20),
                only_plan_id="plan",
                replace_ids=["funding"],
            )
        fetch.assert_not_awaited()
        self.assertEqual(result, original)
        self.assertEqual(data, original)
        self.assertTrue(report["rolled_back"])
        self.assertEqual(report["created"], 0)
        self.assertEqual(report["recalculated"], 0)

    async def test_incremental_lot_corrections_resolve_conflict_and_resume_booking(
        self,
    ):
        flow, entry, manager = _flow(conflicting_wallet())
        for index, day in enumerate((20, 21)):
            flow._edit_lot_id = f"lot-{index}"
            result = await flow.async_step_edit_lot_fields(
                {
                    "date": f"2026-01-{day}",
                    "amount": 20,
                    "units": 1,
                    "included_in_opening": True,
                }
            )
            self.assertEqual(result["type"], "create_entry")
            if index == 0:
                self.assertEqual(
                    opening_balance_conflicts(entry.data)[0]["included_units"], 3
                )
        self.assertEqual(opening_balance_conflicts(entry.data), [])
        self.assertEqual(entry.data["valors"][0]["amount"], 2)
        self.assertEqual(entry.data["contributions"][0]["amount"], 40)
        self.assertEqual(manager.updates, 2)
        prices = {"AAA": [HistoricalQuote("AAA", date(2026, 2, 20), 10, "EUR")]}
        with patch.object(
            executions, "fetch_histories", AsyncMock(return_value=prices)
        ):
            booked, report = await executions.async_prepare_executions(
                entry.data, session=object(), today=date(2026, 2, 20)
            )
        self.assertEqual(report["created"], 1)
        self.assertEqual(report["pending"], [])
        self.assertEqual(booked["contributions"][-1], entry.data["contributions"][0])
        self.assertEqual(additional_units(booked, "AAA"), 1)

    async def test_corrections_cannot_increase_an_existing_discrepancy(self):
        flow, entry, manager = _flow(conflicting_wallet())
        original = copy.deepcopy(entry.data)
        flow._edit_lot_id = "lot-0"
        result = await flow.async_step_edit_lot_fields(
            {
                "date": "2026-01-20",
                "amount": 20,
                "units": 3,
                "included_in_opening": True,
            }
        )
        self.assertEqual(result["errors"]["units"], "included_units_exceeded")
        flow._edit_symbol = "AAA"
        result = await flow.async_step_edit_valor_fields({"amount": 1})
        self.assertEqual(result["errors"]["amount"], "included_units_exceeded")
        self.assertEqual(manager.updates, 0)
        self.assertEqual(entry.data, original)

    async def test_confirmed_opening_correction_can_reduce_conflict_in_steps(self):
        flow, entry, _manager = _flow(conflicting_wallet())
        flow._edit_symbol = "AAA"
        result = await flow.async_step_edit_valor_fields({"amount": 3})
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(
            opening_balance_conflicts(entry.data)[0]["configured_units"], 3
        )
        result = await flow.async_step_edit_valor_fields({"amount": 4})
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(opening_balance_conflicts(entry.data), [])

    def test_conflicting_units_never_become_a_fabricated_value_curve(self):
        data = conflicting_wallet()
        original = copy.deepcopy(data)
        prices = {
            "AAA": [
                HistoricalQuote("AAA", date(2026, 1, day), 10, "EUR")
                for day in (20, 21, 22)
            ]
        }
        result = build_history(data, prices, today=date(2026, 1, 22))
        self.assertEqual(
            result["opening_conflicts"],
            [{"symbol": "AAA", "configured_units": 2, "included_units": 4}],
        )
        self.assertTrue(
            all(
                point["value"] is None and point["profit"] is None
                for point in result["points"]
            )
        )
        self.assertEqual(result["points"][-1]["invested"], 40)
        self.assertEqual(result["points"][-1]["cash"], 0)
        self.assertEqual(len(result["ledger"]), 3)
        self.assertEqual(data, original)
        data["valors"][0]["amount"] = 4
        repaired = build_history(data, prices, today=date(2026, 1, 22))
        self.assertEqual(repaired["opening_conflicts"], [])
        self.assertEqual(repaired["points"][-1]["value"], 40)

    async def test_warning_is_visible_without_due_plans_or_market_data(self):
        data = conflicting_wallet()
        data["savings_plans"] = []
        flow, entry, _manager = _flow(data)
        menu = await flow.async_step_init()
        warning = menu["description_placeholders"]["opening_conflict"]
        self.assertIn("AAA", warning)
        self.assertIn("paused", warning)
        self.assertIn("edit_valor", menu["menu_options"])
        self.assertIn("edit_lot", menu["menu_options"])
        connection = Connection()
        panel.ws_wallets(hass_with([entry]), connection, {"id": 1})
        wallet = connection.results[0][1]["wallets"][0]
        self.assertIsNone(wallet["total"])
        self.assertEqual(wallet["opening_conflicts"][0]["included_units"], 4)

    async def test_invalid_symbol_reference_still_fails_migration_atomically(self):
        data = conflicting_wallet()
        data["contributions"][0]["lots"][0]["symbol"] = "MISSING"
        original = copy.deepcopy(data)
        entry, hass = _Entry(4, data), _Hass()
        with self.assertLogs(migration._LOGGER.name, level="ERROR"):
            self.assertFalse(await migration.async_migrate_entry(hass, entry))
        self.assertEqual(entry.data, original)
        self.assertEqual(entry.version, 4)
        self.assertEqual(hass.config_entries.calls, [])

    def test_rounding_noise_and_nonopening_lots_do_not_pause_a_wallet(self):
        data = conflicting_wallet()
        data["valors"][0]["amount"] = 4 - 1e-10
        self.assertEqual(opening_balance_conflicts(data), [])
        data["contributions"].append(
            make_contribution(
                100,
                "2026-02-01",
                lots=[
                    make_lot(
                        symbol="AAA",
                        execution_date="2026-02-01",
                        amount=100,
                        unit_price=10,
                        quote_currency="EUR",
                        units=10,
                    )
                ],
            )
        )
        self.assertEqual(opening_balance_conflicts(data), [])
        self.assertEqual(len(all_lots(data)), 3)


if __name__ == "__main__":
    unittest.main()
