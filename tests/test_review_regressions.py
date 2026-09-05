"""Reproduce the financial and cross-component failures found in the 1.10.1 review."""

from __future__ import annotations

import unittest
from copy import deepcopy
from datetime import date, datetime
from time import monotonic
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tests.bootstrap import install_stubs
from tests.test_options_regressions import _flow
from tests.test_panel_regressions import Connection, hass_with, panel
from tests.test_v140_features import statement, wallet

install_stubs()

from custom_components.my_wallet import const as c
from custom_components.my_wallet.accounting import ACCOUNTING_REVISIONS
from custom_components.my_wallet.backup import create_backup, prepare_backup
from custom_components.my_wallet.contributions import (
    all_lots,
    make_contribution,
    make_lot,
    xirr,
)
from custom_components.my_wallet.dividends import cash_balance, make_dividend
from custom_components.my_wallet.executions import async_prepare_executions
from custom_components.my_wallet.followup_import import (
    IMPORT_LINKS,
    add_initial_import_metadata,
    async_prepare_followup,
)
from custom_components.my_wallet.history_import import async_prepare_import
from custom_components.my_wallet.plans import change_plan_definition, make_plan
from custom_components.my_wallet.recorded_history import accounting_snapshot
from custom_components.my_wallet.yahoo import HistoricalQuote

TODAY = date(2026, 2, 28)


def purchase(identifier="purchase1", day="2026-01-01", amount=50, units=5):
    return {
        "id": identifier,
        "date": day,
        "symbol": "AAA",
        "amount": amount,
        "units": units,
    }


def document(batch, purchases=(), amount=100):
    return {
        "format": "my_wallet_history",
        "version": 1,
        "batch_id": batch,
        "wallet_name": "Review",
        "base_currency": "EUR",
        "assets": [{"symbol": "AAA"}],
        "plans": [],
        "dividends": [],
        "deposits": [
            {
                "id": "deposit",
                "date": "2026-01-01",
                "amount": amount,
                "purchases": list(purchases),
            }
        ],
    }


def plan(symbol="AAA", first="2026-01-20"):
    return make_plan(
        name="Monthly",
        first_date=first,
        allocation_mode="fixed",
        allocations=[{"symbol": symbol, "value": 100}],
        plan_id="plan",
    )


def funded_wallet(*, spending=100, dividend=0):
    lot = make_lot(
        symbol="AAA",
        execution_date="2026-01-01",
        amount=spending,
        units=10,
        unit_price=spending / 10,
        quote_currency="EUR",
        lot_id="lot",
    )
    return wallet(
        [make_contribution(100, "2026-01-01", lots=[lot], contribution_id="deposit")],
        dividends=[
            make_dividend(
                booking_date="2026-01-01",
                amount=dividend,
                symbol="AAA",
                dividend_id="div",
            )
        ]
        if dividend
        else [],
    )


class ReviewImportTests(unittest.IsolatedAsyncioTestCase):
    async def initial(self, doc):
        data, _ = await async_prepare_import(doc, session=None, today=TODAY)
        return add_initial_import_metadata(doc, data, today=TODAY)

    async def test_distinct_purchases_survive_overlap_even_with_identical_trade_details(
        self,
    ):
        first = document("first", [purchase()])
        original = await self.initial(first)
        for day in ("2026-01-01", "2026-01-15"):
            for reverse in (False, True):
                with self.subTest(day=day, reverse=reverse):
                    purchases = [purchase(), purchase("purchase2", day)]
                    if reverse:
                        purchases.reverse()
                    candidate, summary = await async_prepare_followup(
                        document("second", purchases),
                        original,
                        session=None,
                        today=TODAY,
                        decisions={"deposit": "merge"},
                    )
                    self.assertEqual(len(all_lots(candidate)), 2)
                    self.assertEqual(
                        sum(lot[c.LOT_UNITS] for lot in all_lots(candidate)), 10
                    )
                    self.assertEqual(cash_balance(candidate), 0)
                    self.assertEqual(summary["added"]["purchases"], 1)
                    self.assertEqual(
                        len(set(candidate[IMPORT_LINKS]["lots"].values())), 2
                    )
        self.assertEqual(len(all_lots(original)), 1)

    async def test_confirmed_quantity_change_requires_keep_or_merge(self):
        original = await self.initial(document("first", [purchase()]))
        changed = document("changed", [purchase(units=4)])
        pending, summary = await async_prepare_followup(
            changed, original, session=None, today=TODAY
        )
        self.assertIsNone(pending)
        self.assertEqual(summary["choices"][0]["kind"], "protected")
        for decision, units in (("keep", 5), ("merge", 4)):
            candidate, _ = await async_prepare_followup(
                changed,
                original,
                session=None,
                today=TODAY,
                decisions={"deposit": decision},
            )
            self.assertEqual(all_lots(candidate)[0][c.LOT_UNITS], units)
            self.assertEqual(cash_balance(candidate), 50)
        self.assertEqual(all_lots(original)[0][c.LOT_UNITS], 5)

    async def test_ambiguous_purchase_requires_explicit_lot_selection(self):
        original = await self.initial(
            document("first", [purchase(), purchase("purchase2")])
        )
        # Older manually entered lots have no stable source-ID links.
        original[IMPORT_LINKS]["lots"] = {}
        incoming = document("second", [purchase("unknown-id")])
        pending, summary = await async_prepare_followup(
            incoming,
            original,
            session=None,
            today=TODAY,
            decisions={"deposit": "merge"},
        )
        self.assertIsNone(pending)
        choice = summary["choices"][0]
        self.assertEqual(choice["id"], "unknown-id")
        self.assertEqual(len(choice["options"]), 2)
        selected = choice["options"][0]["id"]
        candidate, _ = await async_prepare_followup(
            incoming,
            original,
            session=None,
            today=TODAY,
            decisions={"deposit": "merge", "unknown-id": selected},
        )
        self.assertEqual(candidate[IMPORT_LINKS]["lots"]["unknown-id"], selected)
        self.assertEqual(len(all_lots(candidate)), 2)

    async def test_new_source_id_does_not_consume_an_omitted_existing_purchase(self):
        original = await self.initial(document("first", [purchase()]))
        candidate, summary = await async_prepare_followup(
            document("second", [purchase("purchase2")]),
            original,
            session=None,
            today=TODAY,
        )
        self.assertEqual(len(all_lots(candidate)), 2)
        self.assertEqual(summary["added"]["purchases"], 1)
        self.assertEqual(cash_balance(candidate), 0)

    async def test_swapped_quantities_between_linked_lots_still_require_confirmation(
        self,
    ):
        original = await self.initial(
            document("first", [purchase(units=4), purchase("purchase2", units=5)])
        )
        changed = document(
            "second", [purchase(units=5), purchase("purchase2", units=4)]
        )
        candidate, summary = await async_prepare_followup(
            changed, original, session=None, today=TODAY
        )
        self.assertIsNone(candidate)
        self.assertEqual(summary["choices"][0]["kind"], "protected")

    async def test_followup_uses_existing_cash_but_cannot_spend_future_funding(self):
        incoming = document("second", [purchase(amount=150, units=15)])
        with self.assertRaisesRegex(ValueError, "import_cash_conflict"):
            await async_prepare_import(incoming, session=None, today=TODAY)
        for funding_date, allowed in (("2025-12-31", True), ("2026-01-02", False)):
            existing = wallet(
                [make_contribution(50, funding_date, contribution_id="earlier")]
            )
            if allowed:
                candidate, _ = await async_prepare_followup(
                    incoming, existing, session=None, today=TODAY
                )
                self.assertEqual(cash_balance(candidate), 0)
            else:
                with self.assertRaisesRegex(ValueError, "import_cash_conflict"):
                    await async_prepare_followup(
                        incoming, existing, session=None, today=TODAY
                    )

    async def test_only_existing_booking_changes_revise_the_accounting_basis(
        self,
    ):
        first = statement("first", ["01"])
        del first["deposits"][0]["purchases"][0]["units"]
        with patch(
            "custom_components.my_wallet.history_import.fetch_histories",
            new=AsyncMock(
                return_value={
                    "AAA": [HistoricalQuote("AAA", date(2026, 1, 20), 100 / 9.5, "EUR")]
                },
            ),
        ):
            original = await self.initial(first)
        original[c.CONF_VALORS].append({"symbol": "BBB", "amount": 0})
        candidate, _ = await async_prepare_followup(
            statement("confirmed", ["01"]),
            original,
            session=None,
            today=TODAY,
        )
        self.assertEqual(all_lots(candidate)[0][c.LOT_UNITS], 10)
        for symbol in (None, "AAA"):
            before = accounting_snapshot(original, today=TODAY, symbol=symbol)
            after = accounting_snapshot(candidate, today=TODAY, symbol=symbol)
            self.assertNotEqual(before["revision"], after["revision"])
            self.assertEqual(before["capital"], after["capital"])
        self.assertEqual(
            accounting_snapshot(original, today=TODAY, symbol="BBB"),
            accounting_snapshot(candidate, today=TODAY, symbol="BBB"),
        )
        extended, _ = await async_prepare_followup(
            statement("next-month", ["01", "02"]),
            candidate,
            session=None,
            today=TODAY,
        )
        self.assertEqual(
            candidate[ACCOUNTING_REVISIONS], extended[ACCOUNTING_REVISIONS]
        )
        restored, _ = prepare_backup(
            create_backup(candidate, title="Review", created_at=datetime(2026, 2, 28)),
            today=TODAY,
        )
        self.assertEqual(
            accounting_snapshot(candidate, today=TODAY),
            accounting_snapshot(restored, today=TODAY),
        )


class ReviewOptionsTests(unittest.IsolatedAsyncioTestCase):
    async def test_history_and_retired_plans_keep_their_referenced_assets(self):
        old = plan()
        historical = change_plan_definition(
            old, plan("BBB"), today=date(2026, 2, 1), recalculate=False
        )
        for retired in (False, True):
            data = wallet()
            data[c.CONF_VALORS].append({"symbol": "BBB", "amount": 0})
            data[c.CONF_SAVINGS_PLANS] = [
                plan(first="2026-09-20") if retired else historical
            ]
            flow, entry, _ = _flow(data)
            if retired:
                await flow.async_step_remove_plan({"id": "plan"})
            before = deepcopy(entry.data)
            result = await flow.async_step_remove_valor({"symbol": "AAA"})
            self.assertEqual(result["errors"]["base"], "valor_in_use")
            self.assertEqual(entry.data, before)
            restored, _ = prepare_backup(
                create_backup(
                    entry.data, title="Review", created_at=datetime(2026, 8, 31)
                ),
                today=date(2026, 8, 31),
            )
            self.assertEqual(restored[c.CONF_VALORS], before[c.CONF_VALORS])

    async def test_executor_refuses_a_legacy_rule_with_an_unconfigured_symbol(self):
        data = wallet()
        data[c.CONF_VALORS] = [{"symbol": "BBB", "amount": 0}]
        data[c.CONF_SAVINGS_PLANS] = [
            change_plan_definition(
                plan(), plan("BBB"), today=date(2026, 2, 1), recalculate=False
            )
        ]
        before = deepcopy(data)
        with patch(
            "custom_components.my_wallet.executions.fetch_histories", new=AsyncMock()
        ) as fetch:
            result, report = await async_prepare_executions(
                data, session=None, today=TODAY
            )
        fetch.assert_not_awaited()
        self.assertEqual(result, before)
        self.assertEqual(report["pending"][0]["reason"], "unconfigured_symbol")
        self.assertEqual(report["pending"][0]["missing_symbols"], ["AAA"])

    async def test_recalculation_revises_units_without_marking_a_manual_edit(
        self,
    ):
        data = funded_wallet()
        data[c.CONF_SAVINGS_PLANS] = [plan(first="2026-01-01")]
        data[c.CONF_CONTRIBUTIONS][0].update(
            {
                c.CONTRIBUTION_SOURCE: c.CONTRIBUTION_SOURCE_PLAN,
                c.CONTRIBUTION_PLAN_ID: "plan",
                c.CONTRIBUTION_SCHEDULED_DATE: "2026-01-01",
                c.CONTRIBUTION_MANUALLY_EDITED: False,
            }
        )
        with patch(
            "custom_components.my_wallet.executions.fetch_histories",
            new=AsyncMock(
                return_value={
                    "AAA": [HistoricalQuote("AAA", date(2026, 1, 1), 20, "EUR")],
                }
            ),
        ):
            result, report = await async_prepare_executions(
                data, session=None, today=date(2026, 1, 31), replace_ids=["deposit"]
            )
        self.assertEqual(report["recalculated"], 1)
        self.assertEqual(all_lots(result)[0][c.LOT_UNITS], 5)
        self.assertFalse(
            result[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_MANUALLY_EDITED]
        )
        self.assertNotEqual(
            accounting_snapshot(data, today=TODAY)["revision"],
            accounting_snapshot(result, today=TODAY)["revision"],
        )

    async def test_increased_purchase_amount_is_rejected_without_changing_the_wallet(
        self,
    ):
        flow, entry, manager = _flow(funded_wallet())
        before = deepcopy(entry.data)
        flow._edit_lot_id = "lot"
        result = await flow.async_step_edit_lot_fields(
            {
                c.LOT_DATE: "2026-01-01",
                c.LOT_AMOUNT: 200,
                c.LOT_UNITS: 10,
                c.LOT_INCLUDED_IN_OPENING: False,
            }
        )
        self.assertEqual(result["errors"]["base"], "cash_conflict")
        self.assertEqual(entry.data, before)
        self.assertEqual(manager.updates, 0)

    async def test_spent_dividends_cannot_be_removed_reduced_or_moved_past_the_purchase(
        self,
    ):
        for operation in ("delete", "reduce", "move"):
            flow, entry, manager = _flow(funded_wallet(spending=110, dividend=10))
            before = deepcopy(entry.data)
            if operation == "delete":
                result = await flow.async_step_remove_dividend({"id": "div"})
            else:
                flow._edit_dividend_id = "div"
                result = await flow.async_step_edit_dividend_fields(
                    {
                        c.DIVIDEND_BOOKING_DATE: "2026-01-01",
                        c.DIVIDEND_VALUE_DATE: "2026-01-02"
                        if operation == "move"
                        else "2026-01-01",
                        c.DIVIDEND_SYMBOL: "AAA",
                        c.DIVIDEND_AMOUNT: 5 if operation == "reduce" else 10,
                    }
                )
            self.assertEqual(result["errors"]["base"], "cash_conflict")
            self.assertEqual(entry.data, before)
            self.assertEqual(manager.updates, 0)

    async def test_unspent_dividend_can_still_be_removed(self):
        flow, entry, _ = _flow(funded_wallet(spending=100, dividend=10))
        result = await flow.async_step_remove_dividend({"id": "div"})
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(cash_balance(entry.data), 0)

    async def test_future_dividend_dates_are_rejected_at_entry_and_edit(self):
        for editing in (False, True):
            for key in (c.DIVIDEND_BOOKING_DATE, c.DIVIDEND_VALUE_DATE):
                flow, entry, _ = _flow(funded_wallet(dividend=10))
                before = deepcopy(entry.data)
                fields = {
                    c.DIVIDEND_BOOKING_DATE: "2026-01-01",
                    c.DIVIDEND_AMOUNT: 10,
                    c.DIVIDEND_SYMBOL: "AAA",
                    key: "2026-09-20",
                }
                if editing:
                    flow._edit_dividend_id = "div"
                    result = await flow.async_step_edit_dividend_fields(fields)
                else:
                    result = await flow.async_step_add_dividend(fields)
                self.assertEqual(result["errors"][key], "future_date")
                self.assertEqual(entry.data, before)
                prepare_backup(
                    create_backup(
                        entry.data, title="Review", created_at=datetime(2026, 8, 31)
                    ),
                    today=date(2026, 8, 31),
                )

    async def test_backup_round_trip_after_removing_last_unused_asset(self):
        flow, entry, _ = _flow(wallet())
        result = await flow.async_step_remove_valor({"symbol": "AAA"})
        self.assertEqual(result["type"], "create_entry")
        restored, _ = prepare_backup(
            create_backup(entry.data, title="Review", created_at=datetime(2026, 8, 31)),
            today=date(2026, 8, 31),
        )
        self.assertEqual(restored[c.CONF_VALORS], [])


class ReviewBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_import_commit_requires_the_preview_target(
        self,
    ):
        a = SimpleNamespace(entry_id="A", data=wallet())
        b = SimpleNamespace(entry_id="B", data=wallet())
        hass = hass_with([a, b])
        candidate = {**a.data, c.CONF_WALLET_NAME: "Imported"}
        panel._state(hass)["previews"]["token"] = {
            "kind": "followup",
            "entry_id": "A",
            "snapshot": a.data,
            "data": candidate,
            "user_id": "user-a",
            "expires": monotonic() + 60,
        }
        for target in (None, "B"):
            conn = Connection()
            msg = {"id": 1, "token": "token", "confirm": True}
            if target:
                msg["entry_id"] = target
            await panel.ws_import_commit(hass, conn, msg)
            self.assertEqual(conn.errors[0][1], "entry_changed")
            hass.config_entries.async_update_entry.assert_not_called()
        conn = Connection()
        await panel.ws_import_commit(
            hass, conn, {"id": 2, "token": "token", "confirm": True, "entry_id": "A"}
        )
        hass.config_entries.async_update_entry.assert_called_once_with(
            a, data=candidate
        )
        self.assertEqual(conn.results[0][1]["entry_id"], "A")

    def test_xirr_handles_decades_and_extreme_cashflow_scales(self):
        start, end = date(1970, 1, 1), date(2026, 9, 4)
        expected = 2 ** (365.2425 / (end - start).days) - 1
        for scale in (1e-200, 1, 1e200):
            self.assertAlmostEqual(
                xirr([(start, -100 * scale), (end, 200 * scale)]), expected, places=10
            )
