"""Financial and workflow regressions for 1.3.3 (synthetic data only)."""

from __future__ import annotations

import copy
import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

from tests.bootstrap import install_stubs

install_stubs()

from custom_components.my_wallet import const as c
from custom_components.my_wallet import executions, history_import
from custom_components.my_wallet.contributions import (
    all_lots,
    invested_total,
    make_contribution,
    make_lot,
)
from custom_components.my_wallet.dividends import cash_balance
from custom_components.my_wallet.history import build_history, latest_close
from custom_components.my_wallet.plans import (
    change_plan_definition,
    due_dates,
    is_scheduled_period,
    make_plan,
    reactivate_matching_plan,
    rule_for_date,
    scale_fixed_allocations,
)
from custom_components.my_wallet.yahoo import HistoricalQuote
from tests.test_options_regressions import _flow


def wallet(*, plans=(), rows=(), symbols=("AAA", "BBB")):
    return {
        c.CONF_WALLET_NAME: "Synthetic test wallet",
        c.CONF_BASE_CURRENCY: "EUR",
        c.CONF_SCAN_INTERVAL: 60,
        c.CONF_VALORS: [{"symbol": symbol, "amount": 0} for symbol in symbols],
        c.CONF_SAVINGS_PLANS: list(plans),
        c.CONF_CONTRIBUTIONS: list(rows),
        c.CONF_DIVIDENDS: [],
    }


def plan(amount=75, *, symbol="AAA", first="2026-01-20", end="2026-02-20"):
    return make_plan(
        plan_id="plan",
        name="Test plan",
        first_date=first,
        end_date=end,
        amount=amount,
        allocation_mode="percentage",
        use_cash_balance=False,
        allocations=[{"symbol": symbol, "value": 100}],
    )


def execution(day, *, amount=75, edited=False, identifier="old"):
    return make_contribution(
        amount,
        day,
        contribution_id=identifier,
        source=c.CONTRIBUTION_SOURCE_PLAN,
        plan_id="plan",
        scheduled_date=day,
        manually_edited=edited,
        lots=[
            make_lot(
                symbol="AAA",
                execution_date=day,
                amount=amount,
                unit_price=10,
                quote_currency="EUR",
                lot_id=f"lot-{identifier}",
            )
        ],
    )


def statement(*, manual=True):
    """A fictitious two-period account; unrelated to the user's statement."""
    result = {
        "format": "my_wallet_history",
        "version": 1,
        "batch_id": "synthetic-test",
        "wallet_name": "Synthetic import",
        "base_currency": "EUR",
        "assets": [{"symbol": "AAA"}, {"symbol": "BBB"}],
        "plans": [
            {
                "id": "old-plan",
                "name": "Earlier plan",
                "first_date": "2026-01-20",
                "end_date": "2026-01-31",
                "allocation_mode": "fixed",
                "allocations": [{"symbol": "AAA", "value": 30}],
            },
            {
                "id": "new-plan",
                "name": "Later plan",
                "first_date": "2026-02-20",
                "allocation_mode": "fixed",
                "allocations": [{"symbol": "BBB", "value": 50}],
            },
        ],
        "deposits": [
            {
                "id": "deposit-one",
                "date": "2026-01-15",
                "amount": 30,
                "plan_id": "old-plan",
                "scheduled_date": "2026-01-20",
                "purchases": [
                    {
                        "id": "purchase-one",
                        "date": "2026-01-21",
                        "amount": 30,
                        "symbol": "AAA",
                    }
                ],
            },
            {
                "id": "deposit-two",
                "date": "2026-02-15",
                "amount": 50,
                "plan_id": "new-plan",
                "scheduled_date": "2026-02-20",
                "purchases": [
                    {
                        "id": "purchase-two",
                        "date": "2026-02-21",
                        "amount": 50.20,
                        "symbol": "BBB",
                    }
                ],
            },
        ],
        "dividends": [
            {
                "id": "credit",
                "booking_date": "2026-02-17",
                "amount": 0.20,
                "symbol": "AAA",
            }
        ],
    }
    if manual:
        for row in result["deposits"]:
            row["purchases"][0]["unit_price"] = 10
    return result


class SavingsPlan133Tests(unittest.IsolatedAsyncioTestCase):
    def test_fixed_total_changes_the_actual_euro_allocations(self):
        rows = scale_fixed_allocations(
            [{"symbol": "AAA", "value": 70}, {"symbol": "BBB", "value": 30}], 75
        )
        self.assertEqual([row["value"] for row in rows], [52.5, 22.5])
        self.assertEqual(sum(row["value"] for row in rows), 75)

    def test_future_only_keeps_old_rate_for_unbooked_past_dates(self):
        changed = change_plan_definition(
            plan(100, end=None),
            plan(75, end=None),
            today=date(2026, 2, 25),
            recalculate=False,
        )
        self.assertEqual(rule_for_date(changed, date(2026, 2, 20))[c.PLAN_AMOUNT], 100)
        self.assertEqual(rule_for_date(changed, date(2026, 3, 20))[c.PLAN_AMOUNT], 75)
        self.assertTrue(is_scheduled_period(changed, "2026-01"))
        self.assertEqual(len(due_dates(changed, [], date(2026, 3, 31))), 3)

    def test_day_change_cannot_create_two_executions_in_one_month(self):
        changed = change_plan_definition(
            plan(first="2026-01-20", end=None),
            plan(first="2026-01-27", end=None),
            today=date(2026, 1, 23),
            recalculate=False,
        )
        self.assertEqual(due_dates(changed, [], date(2026, 1, 31)), [date(2026, 1, 20)])

    def test_recreated_plan_keeps_identity_and_previous_rate_history(self):
        current = change_plan_definition(
            plan(100, end=None),
            plan(75, end=None),
            today=date(2026, 2, 25),
            recalculate=False,
        )
        proposed = {**plan(75, end=None), "id": "new-id"}
        restored, retired = reactivate_matching_plan(proposed, [current])
        self.assertEqual(restored["id"], "plan")
        self.assertEqual(retired, [])
        self.assertEqual(rule_for_date(restored, date(2026, 1, 20))["amount"], 100)

    async def test_v5_migration_preserves_bookings_and_unknown_correction_status(self):
        from tests.test_migration_regressions import _Entry, _Hass, migration

        original = wallet(plans=[plan()], rows=[execution("2026-01-20", edited=None)])
        entry = _Entry(5, copy.deepcopy(original))
        self.assertTrue(await migration.async_migrate_entry(_Hass(), entry))
        self.assertEqual(entry.version, 6)
        self.assertEqual(
            entry.data[c.CONF_CONTRIBUTIONS], original[c.CONF_CONTRIBUTIONS]
        )
        self.assertNotIn(
            c.CONTRIBUTION_MANUALLY_EDITED, entry.data[c.CONF_CONTRIBUTIONS][0]
        )

    def test_manual_and_unclassified_legacy_bookings_are_protected(self):
        manual = execution("2026-01-20", edited=True, identifier="manual")
        legacy = execution("2026-02-20", edited=None, identifier="legacy")
        imported = {
            **execution("2026-03-20", identifier="imported"),
            "source": "import",
        }
        self.assertEqual(
            executions.recalculable_ids([manual, legacy, imported], "plan"), set()
        )
        self.assertEqual(
            executions.recalculable_ids(
                [manual, legacy, imported],
                "plan",
                approved_legacy_ids=["manual", "legacy", "imported"],
            ),
            {"legacy"},
        )

    async def test_recalculation_preserves_ids_and_does_not_duplicate(self):
        old = execution("2026-01-20")
        data = wallet(plans=[plan(100, end="2026-01-20")], rows=[old])
        histories = {"AAA": [HistoricalQuote("AAA", date(2026, 1, 20), 10, "EUR")]}
        with patch.object(
            executions, "fetch_histories", AsyncMock(return_value=histories)
        ):
            result, report = await executions.async_prepare_executions(
                data, session=object(), today=date(2026, 1, 31), replace_ids=["old"]
            )
            second, second_report = await executions.async_prepare_executions(
                result, session=object(), today=date(2026, 1, 31)
            )
        row = result[c.CONF_CONTRIBUTIONS][0]
        self.assertEqual(row["id"], "old")
        self.assertEqual(row["lots"][0]["id"], "lot-old")
        self.assertEqual((row["amount"], row["lots"][0]["units"]), (100, 10))
        self.assertEqual(report["recalculated"], 1)
        self.assertEqual(second_report["created"], 0)
        self.assertEqual(second[c.CONF_CONTRIBUTIONS], result[c.CONF_CONTRIBUTIONS])
        self.assertEqual(data[c.CONF_CONTRIBUTIONS], [old])

    async def test_missing_price_rolls_back_every_recalculated_booking(self):
        old = [
            execution("2026-01-20", identifier="jan"),
            execution("2026-02-20", identifier="feb"),
        ]
        data = wallet(plans=[plan(100)], rows=old)
        original = copy.deepcopy(data)
        histories = {"AAA": [HistoricalQuote("AAA", date(2026, 1, 20), 10, "EUR")]}
        with patch.object(
            executions, "fetch_histories", AsyncMock(return_value=histories)
        ):
            result, report = await executions.async_prepare_executions(
                data,
                session=object(),
                today=date(2026, 2, 28),
                replace_ids=["jan", "feb"],
            )
        self.assertEqual(data, original)
        self.assertEqual(result[c.CONF_CONTRIBUTIONS], old)
        self.assertTrue(report["rolled_back"])
        self.assertEqual((report["created"], report["recalculated"]), (0, 0))
        self.assertEqual(report["pending"][0]["reason"], "historical_price_unavailable")

    async def test_manual_correction_is_vetoed_even_if_caller_selects_it(self):
        old = execution("2026-01-20", edited=True)
        data = wallet(plans=[plan(100, end="2026-01-20")], rows=[old])
        with patch.object(executions, "fetch_histories", AsyncMock()) as fetch:
            result, report = await executions.async_prepare_executions(
                data, session=object(), today=date(2026, 1, 31), replace_ids=["old"]
            )
        fetch.assert_not_awaited()
        self.assertEqual(result[c.CONF_CONTRIBUTIONS], [old])
        self.assertEqual(report["recalculated"], 0)

    async def test_final_execution_does_not_use_a_price_several_months_late(self):
        data = wallet(plans=[plan(end="2026-01-20")])
        histories = {"AAA": [HistoricalQuote("AAA", date(2026, 4, 20), 10, "EUR")]}
        with patch.object(
            executions, "fetch_histories", AsyncMock(return_value=histories)
        ):
            result, report = await executions.async_prepare_executions(
                data, session=object(), today=date(2026, 4, 30)
            )
        self.assertEqual(result[c.CONF_CONTRIBUTIONS], [])
        self.assertEqual(report["pending"][0]["scheduled_date"], "2026-01-20")


class InvestmentFlow133Tests(unittest.IsolatedAsyncioTestCase):
    async def test_editing_fixed_plan_total_reaches_the_review_with_new_amounts(self):
        fixed = make_plan(
            name="Fixed plan",
            plan_id="fixed",
            first_date="2026-01-20",
            allocation_mode="fixed",
            allocations=[
                {"symbol": "AAA", "value": 70},
                {"symbol": "BBB", "value": 30},
            ],
        )
        flow, _, manager = _flow(wallet(plans=[fixed]))
        await flow.async_step_edit_plan({"id": "fixed"})
        result = await flow.async_step_edit_plan_fields(
            {
                "name": "Fixed plan",
                "first_date": "2026-01-20",
                "allocation_mode": "fixed",
                "amount": 75,
                "keep_allocations": True,
                "update_scope": "future",
            }
        )
        self.assertEqual(result["step_id"], "plan_confirm")
        self.assertEqual(flow._proposed_plan["amount"], 75)
        self.assertEqual(
            [row["value"] for row in flow._proposed_plan["allocations"]], [52.5, 22.5]
        )
        self.assertEqual(manager.updates, 0)

    async def test_deposit_and_distinct_purchase_dates_are_saved_once(self):
        flow, entry, manager = _flow(wallet())
        await flow.async_step_add_contribution(
            {
                "date": "2026-02-10",
                "amount": 60,
                "note": "Test deposit",
                "invest_now": True,
            }
        )
        await flow.async_step_contribution_investment(
            {
                "symbols": ["AAA", "BBB"],
                "allocation_mode": "fixed",
                "execution_date": "2026-02-11",
                "included_in_opening": False,
                "use_cash_balance": False,
            }
        )
        await flow.async_step_contribution_allocation(
            {"value": 20, "date": "2026-02-11", "units": 2}
        )
        progress = await flow.async_step_contribution_allocation(
            {"value": 30, "date": "2026-02-12", "unit_price": 10}
        )
        self.assertEqual(progress["type"], "progress")
        await flow._investment_task
        result = await flow.async_step_investment_progress()
        self.assertEqual(result["next_step_id"], "contribution_confirm")
        self.assertEqual(manager.updates, 0)
        await flow.async_step_contribution_confirm({"confirm": True})
        self.assertEqual((manager.updates, manager.reloads), (1, 1))
        self.assertEqual(invested_total(entry.data), 60)
        self.assertEqual(cash_balance(entry.data), 10)
        self.assertEqual(
            [lot["date"] for lot in all_lots(entry.data)], ["2026-02-11", "2026-02-12"]
        )
        self.assertEqual(entry.data[c.CONF_CONTRIBUTIONS][0]["note"], "Test deposit")

    async def test_standalone_purchase_uses_cash_without_another_deposit(self):
        flow, entry, manager = _flow(
            wallet(rows=[make_contribution(100, "2026-02-10")])
        )
        result = await flow.async_step_add_lot(
            {
                "symbol": "AAA",
                "date": "2026-02-11",
                "amount": 30,
                "units": 3,
                "included_in_opening": False,
            }
        )
        self.assertEqual(result["step_id"], "lot_confirm")
        self.assertEqual(manager.updates, 0)
        await flow.async_step_lot_confirm({"confirm": True})
        self.assertEqual(invested_total(entry.data), 100)
        self.assertEqual(cash_balance(entry.data), 70)

    async def test_future_manual_deposit_and_purchase_are_rejected(self):
        flow, _, manager = _flow(wallet())
        deposit = await flow.async_step_add_contribution(
            {"amount": 20, "date": "2026-09-01"}
        )
        purchase = await flow.async_step_add_lot(
            {
                "symbol": "AAA",
                "amount": 20,
                "date": "2026-09-01",
                "units": 2,
                "included_in_opening": False,
            }
        )
        self.assertEqual(deposit["errors"]["date"], "future_date")
        self.assertEqual(purchase["errors"]["date"], "future_date")
        self.assertEqual(manager.updates, 0)

    async def test_deposit_edit_marks_correction_and_preserves_lots(self):
        row = execution("2026-01-20")
        flow, entry, _ = _flow(wallet(rows=[row]))
        await flow.async_step_edit_contribution({"id": row["id"]})
        await flow.async_step_edit_contribution_fields(
            {"amount": 80, "date": "2026-01-20", "note": "Corrected"}
        )
        updated = entry.data[c.CONF_CONTRIBUTIONS][0]
        self.assertTrue(updated[c.CONTRIBUTION_MANUALLY_EDITED])
        self.assertEqual(updated["lots"], row["lots"])
        self.assertEqual(updated["note"], "Corrected")

    async def test_imported_plan_execution_deletion_stays_skipped(self):
        row = {**execution("2026-01-20"), "source": "import"}
        flow, entry, manager = _flow(wallet(plans=[plan()], rows=[row]))
        await flow.async_step_remove_contribution({"id": row["id"]})
        self.assertEqual(manager.updates, 0)
        await flow.async_step_confirm_remove_contribution({"confirm": True})
        self.assertEqual(
            entry.data[c.CONF_SAVINGS_PLANS][0][c.PLAN_SKIPPED_PERIODS], ["2026-01"]
        )

    async def test_stale_purchase_confirmation_does_not_overwrite_another_edit(self):
        flow, entry, manager = _flow(
            wallet(rows=[make_contribution(100, "2026-02-10")])
        )
        await flow.async_step_add_lot(
            {
                "symbol": "AAA",
                "date": "2026-02-11",
                "amount": 30,
                "units": 3,
                "included_in_opening": False,
            }
        )
        changed = {**entry.data, c.CONF_WALLET_NAME: "Changed elsewhere"}
        entry.data = changed
        result = await flow.async_step_lot_confirm({"confirm": True})
        self.assertEqual(result["reason"], "entry_changed")
        self.assertIs(entry.data, changed)
        self.assertEqual(manager.updates, 0)


class History133Tests(unittest.IsolatedAsyncioTestCase):
    async def test_two_simple_plans_import_without_rebooking_past_months(self):
        with patch.object(history_import, "fetch_histories", AsyncMock()) as fetch:
            data, summary = await history_import.async_prepare_import(
                statement(), session=object(), today=date(2026, 2, 28)
            )
        fetch.assert_not_awaited()
        self.assertEqual(
            (summary["deposits"], summary["purchases"], summary["dividends"]), (2, 2, 1)
        )
        self.assertEqual(
            (summary["capital"], summary["spending"], summary["cash"]), (80, 80.2, 0)
        )
        self.assertEqual(invested_total(data), 80)
        self.assertAlmostEqual(cash_balance(data), 0)
        for item in data[c.CONF_SAVINGS_PLANS]:
            self.assertEqual(
                due_dates(item, data[c.CONF_CONTRIBUTIONS], date(2026, 2, 28)), []
            )
        self.assertEqual(
            due_dates(
                data[c.CONF_SAVINGS_PLANS][1],
                data[c.CONF_CONTRIBUTIONS],
                date(2026, 3, 21),
            ),
            [date(2026, 3, 20)],
        )

    async def test_import_keeps_bank_dates_and_labels_estimated_units(self):
        quotes = {
            "AAA": [HistoricalQuote("AAA", date(2026, 1, 20), 10, "EUR")],
            "BBB": [HistoricalQuote("BBB", date(2026, 2, 20), 20, "USD")],
            "USDEUR=X": [HistoricalQuote("USDEUR=X", date(2026, 2, 20), 0.8, "EUR")],
        }
        with patch.object(
            history_import, "fetch_histories", AsyncMock(return_value=quotes)
        ):
            data, summary = await history_import.async_prepare_import(
                statement(manual=False), session=object(), today=date(2026, 2, 28)
            )
        lots = all_lots(data)
        self.assertEqual(summary["estimated"], 2)
        self.assertEqual(lots[0]["date"], "2026-01-21")
        self.assertEqual(lots[0]["price_date"], "2026-01-20")
        self.assertAlmostEqual(lots[1]["units"], 50.2 / 16)
        self.assertEqual(data[c.CONF_CONTRIBUTIONS][0]["date"], "2026-01-15")

    async def test_missing_import_prices_never_produce_partial_persistable_data(self):
        with patch.object(
            history_import, "fetch_histories", AsyncMock(return_value={})
        ):
            data, summary = await history_import.async_prepare_import(
                statement(manual=False), session=object(), today=date(2026, 2, 28)
            )
        self.assertIsNone(data)
        self.assertEqual(len(summary["missing"]), 2)
        self.assertEqual(summary["spending"], 80.2)

    async def test_history_uses_cash_event_dates_and_never_adds_dividends_to_capital(
        self,
    ):
        data, _ = await history_import.async_prepare_import(
            statement(), session=object(), today=date(2026, 2, 28)
        )
        quotes = {
            "AAA": [
                HistoricalQuote("AAA", date(2026, 1, 21), 10, "EUR"),
                HistoricalQuote("AAA", date(2026, 2, 21), 10, "EUR"),
            ],
            "BBB": [HistoricalQuote("BBB", date(2026, 2, 21), 10, "EUR")],
        }
        history = build_history(data, quotes, today=date(2026, 2, 28))
        points = {point["date"]: point for point in history["points"]}
        self.assertEqual(points["2026-01-15"]["cash"], 30)
        self.assertEqual(points["2026-01-21"]["cash"], 0)
        self.assertEqual(points["2026-02-17"]["cash"], 50.2)
        self.assertEqual(points["2026-02-28"]["invested"], 80)
        self.assertEqual(points["2026-02-28"]["value"], 80.2)
        self.assertEqual(points["2026-02-28"]["profit"], 0.2)

    def test_untracked_opening_units_do_not_invent_historical_portfolio_values(self):
        data = wallet(rows=[make_contribution(100, "2026-02-10")])
        data[c.CONF_VALORS][0]["amount"] = 4
        history = build_history(data, {}, today=date(2026, 2, 28))
        self.assertEqual(history["unknown_opening"], ["AAA"])
        self.assertTrue(all(point["value"] is None for point in history["points"]))
        self.assertEqual(history["points"][-1]["invested"], 100)

    def test_history_never_uses_future_or_stale_quotes(self):
        quotes = [HistoricalQuote("AAA", date(2026, 2, 20), 10, "EUR")]
        self.assertIsNone(latest_close(quotes, date(2026, 2, 19)))
        self.assertIsNone(latest_close(quotes, date(2026, 2, 28)))
        self.assertEqual(latest_close(quotes, date(2026, 2, 21)).close, 10)

    def test_import_rejects_duplicate_ids_and_future_payments(self):
        document = statement()
        document["deposits"][1]["purchases"][0]["id"] = "purchase-one"
        with self.assertRaisesRegex(ValueError, "duplicate_or_excess"):
            history_import.validate_document(document, today=date(2026, 2, 28))
        document = statement()
        document["deposits"][1]["date"] = "2026-03-01"
        with self.assertRaisesRegex(ValueError, "future_date"):
            history_import.validate_document(document, today=date(2026, 2, 28))

    async def test_import_rejects_an_intermediate_cash_deficit(self):
        document = statement()
        document["deposits"][0]["purchases"][0]["amount"] = 30.2
        document["deposits"][1]["purchases"][0]["amount"] = 50
        with self.assertRaisesRegex(ValueError, "import_cash_conflict"):
            await history_import.async_prepare_import(
                document, session=object(), today=date(2026, 2, 28)
            )


if __name__ == "__main__":
    unittest.main()
