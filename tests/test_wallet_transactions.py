"""Behavioral coverage of the shared ledger and its persistence boundary."""

from __future__ import annotations

import unittest
from copy import deepcopy
from datetime import date, datetime
from unittest.mock import AsyncMock, patch

from custom_components.my_wallet import const as c
from custom_components.my_wallet.accounting import ACCOUNTING_REVISIONS
from custom_components.my_wallet.backup import create_backup, prepare_backup
from custom_components.my_wallet.contributions import (
    all_lots,
    invested_total,
    make_contribution,
    make_lot,
)
from custom_components.my_wallet.corrections import position_units, prepare_correction
from custom_components.my_wallet.dividends import cash_balance, make_dividend
from custom_components.my_wallet.executions import async_prepare_executions
from custom_components.my_wallet.ledger import (
    CashPolicy,
    book_purchase,
    delete_contribution,
    delete_dividend,
    edit_contribution,
    prepare_change,
    put_dividend,
)
from custom_components.my_wallet.plans import change_plan_definition, make_plan
from custom_components.my_wallet.recorded_history import accounting_snapshot
from custom_components.my_wallet.store import commit_wallet_change
from custom_components.my_wallet.yahoo import HistoricalQuote
from tests.test_options_regressions import _flow
from tests.test_v140_features import wallet

TODAY = date(2026, 2, 28)


def lot(identifier="purchase", day="2026-01-02", amount=100, units=10, **extra):
    return make_lot(
        symbol="AAA",
        execution_date=day,
        amount=amount,
        units=units,
        unit_price=amount / units,
        quote_currency="EUR",
        lot_id=identifier,
        **extra,
    )


def plan(identifier="plan", symbol="AAA", **extra):
    return make_plan(
        name="Monthly",
        first_date="2026-02-20",
        amount=100,
        allocation_mode="percentage",
        allocations=[{"symbol": symbol, "value": 100}],
        plan_id=identifier,
        **extra,
    )


class WalletTransactionTests(unittest.IsolatedAsyncioTestCase):
    def save(self, flow, entry, candidate, **kwargs):
        return commit_wallet_change(
            flow.hass, entry, candidate, snapshot=entry.data, today=TODAY, **kwargs
        )

    async def test_deposit_purchase_dividend_reinvestment_correction_backup_restore(
        self,
    ):
        flow, entry, manager = _flow(wallet())
        original_entry_id = entry.entry_id
        result = await flow.async_step_add_contribution(
            {"amount": 100, "date": "2026-01-01"}
        )
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(cash_balance(entry.data), 100)
        deposit_id = entry.data[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_ID]
        self.save(
            flow,
            entry,
            book_purchase(entry.data, lot(), today=TODAY, funding_id=deposit_id),
        )
        self.assertEqual(cash_balance(entry.data), 0)
        self.save(
            flow,
            entry,
            put_dividend(
                entry.data,
                {"booking_date": "2026-01-15", "amount": 10, "symbol": "AAA"},
                today=TODAY,
            ),
        )
        dividend_id = entry.data[c.CONF_DIVIDENDS][0][c.DIVIDEND_ID]
        self.save(
            flow,
            entry,
            book_purchase(
                entry.data, lot("reinvested", "2026-01-16", 10, 1), today=TODAY
            ),
        )
        self.assertEqual(
            (invested_total(entry.data), cash_balance(entry.data)), (100, 0)
        )
        self.assertEqual(position_units(entry.data, "AAA", TODAY), 11)
        before = entry.data
        with self.assertRaisesRegex(ValueError, "cash_conflict"):
            delete_dividend(before, dividend_id, today=TODAY)
        corrected, _ = prepare_correction(
            before,
            {"symbol": "AAA", "target": "purchase", "mode": "lot", "units": 9.5},
            today=TODAY,
        )
        prepared_revision = corrected[ACCOUNTING_REVISIONS]
        self.save(flow, entry, corrected)
        self.assertEqual(entry.data[ACCOUNTING_REVISIONS], prepared_revision)
        self.assertEqual(entry.entry_id, original_entry_id)
        self.assertEqual(position_units(entry.data, "AAA", TODAY), 10.5)
        self.assertEqual(
            (invested_total(entry.data), cash_balance(entry.data)), (100, 0)
        )
        self.assertNotEqual(
            accounting_snapshot(before, today=TODAY)["revision"],
            accounting_snapshot(entry.data, today=TODAY)["revision"],
        )
        restored, _ = prepare_backup(
            create_backup(
                entry.data, title=entry.title, created_at=datetime(2026, 2, 28)
            ),
            today=TODAY,
        )
        for key in (
            c.CONF_VALORS,
            c.CONF_CONTRIBUTIONS,
            c.CONF_DIVIDENDS,
            ACCOUNTING_REVISIONS,
        ):
            self.assertEqual(restored[key], entry.data[key])
        for symbol in (None, "AAA"):
            self.assertEqual(
                accounting_snapshot(restored, today=TODAY, symbol=symbol),
                accounting_snapshot(entry.data, today=TODAY, symbol=symbol),
            )
        self.assertEqual((manager.updates, manager.reloads), (5, 5))

    def test_commit_rejects_intermediate_deficit_even_if_current_cash_is_positive(self):
        data = wallet(
            [
                make_contribution(
                    100, "2026-01-01", contribution_id="early", lots=[lot()]
                ),
                make_contribution(200, "2026-02-01", contribution_id="late"),
            ]
        )
        flow, entry, manager = _flow(data)
        candidate = deepcopy(data)
        candidate[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_AMOUNT] = 50
        self.assertEqual(cash_balance(candidate), 150)
        with self.assertRaisesRegex(ValueError, "cash_conflict"):
            self.save(flow, entry, candidate)
        self.assertIs(entry.data, data)
        self.assertEqual((manager.updates, manager.reloads), (0, 0))

    def test_stale_async_candidate_cannot_overwrite_a_newer_commit(self):
        flow, entry, manager = _flow(wallet())
        snapshot = entry.data
        self.save(flow, entry, {**snapshot, c.CONF_WALLET_NAME: "New name"})
        with self.assertRaisesRegex(ValueError, "entry_changed"):
            commit_wallet_change(
                flow.hass, entry, snapshot, snapshot=snapshot, today=TODAY
            )
        self.assertEqual(entry.data[c.CONF_WALLET_NAME], "New name")
        self.assertEqual(manager.updates, 1)

    def test_commit_detaches_nested_data_and_unchanged_retry_does_not_reload(self):
        flow, entry, manager = _flow(wallet())
        candidate = {
            **entry.data,
            c.CONF_CONTRIBUTIONS: [make_contribution(100, "2026-01-01")],
        }
        self.save(flow, entry, candidate)
        candidate[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_AMOUNT] = 1
        self.assertEqual(invested_total(entry.data), 100)
        self.assertFalse(self.save(flow, entry, deepcopy(entry.data)))
        self.assertEqual((manager.updates, manager.reloads), (1, 1))

    def test_all_writers_reject_duplicate_ids_missing_references_future_events_and_nan(
        self,
    ):
        original = wallet([make_contribution(100, "2026-01-01", lots=[lot()])])
        candidates = []
        candidate = deepcopy(original)
        candidate[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_LOTS].append(lot())
        candidates.append(candidate)
        candidates.append({**original, c.CONF_VALORS: []})
        candidates.append(
            {
                **original,
                c.CONF_DIVIDENDS: [make_dividend(booking_date="2026-03-01", amount=10)],
            }
        )
        candidate = deepcopy(original)
        candidate[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_AMOUNT] = float("nan")
        candidates.append(candidate)
        candidate = deepcopy(original)
        candidate[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_AMOUNT] = True
        candidates.append(candidate)
        candidates.append(
            {
                **original,
                c.CONF_SAVINGS_PLANS: [plan()],
                c.CONF_RETIRED_SAVINGS_PLANS: [plan()],
            }
        )
        old_rule = plan(symbol="BBB")
        changed = change_plan_definition(
            old_rule, plan(), today=TODAY, recalculate=False
        )
        candidates.append({**original, c.CONF_RETIRED_SAVINGS_PLANS: [changed]})
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                flow, entry, manager = _flow(original)
                with self.assertRaises(ValueError):
                    self.save(flow, entry, candidate)
                self.assertIs(entry.data, original)
                self.assertEqual(manager.updates, 0)

    def test_cash_exception_only_accepts_added_purchases(self):
        original = wallet()
        purchase = lot()
        with self.assertRaisesRegex(ValueError, "cash_conflict"):
            book_purchase(original, purchase, today=TODAY)
        candidate = book_purchase(
            original, purchase, today=TODAY, cash_policy=CashPolicy.CONFIRMED_PURCHASE
        )
        flow, entry, _ = _flow(original)
        self.save(flow, entry, candidate, cash_policy=CashPolicy.CONFIRMED_PURCHASE)
        self.assertEqual(cash_balance(entry.data), -100)
        tampered = deepcopy(candidate)
        tampered[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_LOTS][0][c.LOT_AMOUNT] = 200
        with self.assertRaises(ValueError):
            prepare_change(
                candidate,
                tampered,
                today=TODAY,
                cash_policy=CashPolicy.CONFIRMED_PURCHASE,
            )

    def test_cash_exception_cannot_move_existing_lots_between_funding_groups(self):
        original = wallet(
            [
                make_contribution(
                    100,
                    None,
                    contribution_id="legacy",
                    source=c.CONTRIBUTION_SOURCE_LEGACY,
                    lots=[lot(included_in_opening=True)],
                ),
                make_contribution(1, "2026-01-01", contribution_id="deposit"),
            ],
            opening=10,
        )
        candidate = deepcopy(original)
        candidate[c.CONF_CONTRIBUTIONS][1][c.CONTRIBUTION_LOTS] = [
            *candidate[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_LOTS],
            lot("new", amount=1, units=1),
        ]
        candidate[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_LOTS] = []
        with self.assertRaisesRegex(ValueError, "invalid_input"):
            prepare_change(
                original,
                candidate,
                today=TODAY,
                cash_policy=CashPolicy.CONFIRMED_PURCHASE,
            )

    def test_legacy_deficit_can_be_kept_or_reduced_and_survives_backup(self):
        original = wallet(
            [
                make_contribution(
                    50, "2026-01-01", contribution_id="deposit", lots=[lot()]
                )
            ]
        )
        self.assertEqual(cash_balance(original), -50)
        renamed = prepare_change(
            original, {**original, c.CONF_WALLET_NAME: "Renamed"}, today=TODAY
        )
        repaired = edit_contribution(
            renamed,
            "deposit",
            amount=75,
            execution_date="2026-01-01",
            note=None,
            today=TODAY,
        )
        self.assertEqual(cash_balance(repaired), -25)
        with self.assertRaisesRegex(ValueError, "cash_conflict"):
            edit_contribution(
                repaired,
                "deposit",
                amount=60,
                execution_date="2026-01-01",
                note=None,
                today=TODAY,
            )
        restored, _ = prepare_backup(
            create_backup(repaired, title="Legacy", created_at=datetime(2026, 2, 28)),
            today=TODAY,
        )
        self.assertEqual(cash_balance(restored), -25)

    def test_revision_is_stable_for_preview_commit_and_unrelated_edits(self):
        original = wallet(
            [make_contribution(100, "2026-01-01", contribution_id="deposit")]
        )
        prepared = edit_contribution(
            original,
            "deposit",
            amount=90,
            execution_date="2026-01-01",
            note=None,
            today=TODAY,
        )
        self.assertEqual(prepare_change(original, prepared, today=TODAY), prepared)
        fields_only = deepcopy(prepared)
        fields_only.pop(ACCOUNTING_REVISIONS)
        fields_only[c.CONF_WALLET_NAME] = "Alias"
        self.assertEqual(
            prepare_change(prepared, fields_only, today=TODAY)[ACCOUNTING_REVISIONS],
            prepared[ACCOUNTING_REVISIONS],
        )
        reversed_edit = edit_contribution(
            prepared,
            "deposit",
            amount=100,
            execution_date="2026-01-01",
            note=None,
            today=TODAY,
        )
        self.assertNotEqual(
            prepared[ACCOUNTING_REVISIONS], reversed_edit[ACCOUNTING_REVISIONS]
        )

    async def test_plan_reinvestment_commit_delete_and_rerun_do_not_rebook(self):
        data = wallet(dividends=[make_dividend(booking_date="2026-02-01", amount=10)])
        data[c.CONF_SAVINGS_PLANS] = [plan(use_cash_balance=True)]
        flow, entry, manager = _flow(data)
        prices = {"AAA": [HistoricalQuote("AAA", date(2026, 2, 20), 10, "EUR")]}
        with patch(
            "custom_components.my_wallet.executions.fetch_histories",
            AsyncMock(return_value=prices),
        ):
            candidate, report = await async_prepare_executions(
                entry.data, session=None, today=TODAY
            )
            self.assertEqual(report["created"], 1)
            self.save(flow, entry, candidate, reload=False)
            self.assertEqual(
                (invested_total(entry.data), cash_balance(entry.data)), (100, 0)
            )
            self.assertEqual(all_lots(entry.data)[0][c.LOT_UNITS], 11)
            identifier = entry.data[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_ID]
            self.save(
                flow, entry, delete_contribution(entry.data, identifier, today=TODAY)
            )
            self.assertEqual(
                entry.data[c.CONF_SAVINGS_PLANS][0][c.PLAN_SKIPPED_PERIODS], ["2026-02"]
            )
            candidate, report = await async_prepare_executions(
                entry.data, session=None, today=TODAY
            )
        self.assertEqual(report["created"], 0)
        self.assertEqual(all_lots(candidate), [])
        self.assertEqual((manager.updates, manager.reloads), (2, 1))
