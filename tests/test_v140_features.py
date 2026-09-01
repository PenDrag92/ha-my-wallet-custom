"""Financial regressions for dashboard and reconciliation features."""

from __future__ import annotations

import unittest
from datetime import date

from tests.bootstrap import install_stubs

install_stubs()

from custom_components.my_wallet import const as c
from custom_components.my_wallet.contributions import make_contribution, make_lot
from custom_components.my_wallet.corrections import UNIT_CORRECTIONS, prepare_correction
from custom_components.my_wallet.dividends import cash_balance, make_dividend
from custom_components.my_wallet.followup_import import (
    add_initial_import_metadata,
    async_prepare_followup,
)
from custom_components.my_wallet.history import build_history
from custom_components.my_wallet.history_import import async_prepare_import
from custom_components.my_wallet.yahoo import HistoricalQuote


def wallet(rows=(), *, opening=0.0, dividends=()):
    return {
        c.CONF_WALLET_NAME: "Synthetic wallet",
        c.CONF_BASE_CURRENCY: "EUR",
        c.CONF_SCAN_INTERVAL: 60,
        c.CONF_VALORS: [{c.VALOR_SYMBOL: "AAA", c.VALOR_AMOUNT: opening}],
        c.CONF_CONTRIBUTIONS: list(rows),
        c.CONF_DIVIDENDS: list(dividends),
        c.CONF_SAVINGS_PLANS: [],
        c.CONF_RETIRED_SAVINGS_PLANS: [],
    }


def contribution(day="2026-01-15", *, units=10.0, estimated=True, included=False):
    return make_contribution(
        100,
        day,
        contribution_id="deposit",
        source="import",
        lots=[
            make_lot(
                symbol="AAA",
                execution_date=day,
                amount=100,
                unit_price=100 / units,
                quote_currency="EUR",
                units=units,
                included_in_opening=included,
                estimated=estimated,
                lot_id="lot",
            )
        ],
    )


def statement(batch, months):
    return {
        "format": "my_wallet_history",
        "version": 1,
        "batch_id": batch,
        "wallet_name": "Synthetic import",
        "base_currency": "EUR",
        "assets": [{"symbol": "AAA"}],
        "plans": [
            {
                "id": "monthly-plan",
                "name": "Monthly plan",
                "first_date": "2026-01-20",
                "allocation_mode": "fixed",
                "allocations": [{"symbol": "AAA", "value": 100}],
            }
        ],
        "deposits": [
            {
                "id": f"deposit-{month}",
                "date": f"2026-{month}-20",
                "amount": 100,
                "plan_id": "monthly-plan",
                "scheduled_date": f"2026-{month}-20",
                "purchases": [
                    {
                        "id": f"purchase-{month}",
                        "date": f"2026-{month}-20",
                        "symbol": "AAA",
                        "amount": 100,
                        "units": 10,
                    }
                ],
            }
            for month in months
        ],
        "dividends": [],
    }


class DashboardTests(unittest.TestCase):
    def test_history_starts_at_zero_only_without_an_opening_holding(self):
        data = wallet([contribution()])
        quotes = {
            "AAA": [
                HistoricalQuote("AAA", date(2026, 1, day), 10, "EUR")
                for day in range(15, 18)
            ]
        }
        result = build_history(data, quotes, today=date(2026, 1, 17))
        self.assertEqual(result["points"][0]["date"], "2026-01-14")
        self.assertEqual(result["points"][0]["value"], 0)
        self.assertTrue(result["points"][0]["baseline"])
        self.assertFalse(result["range_limited"])

        opening = wallet([contribution(included=True)], opening=10)
        result = build_history(opening, quotes, today=date(2026, 1, 17))
        self.assertEqual(result["points"][0]["date"], "2026-01-15")
        self.assertFalse(result["points"][0]["baseline"])

    def test_monthly_wallet_and_position_performance_separate_cash_flows(self):
        dividend = make_dividend(
            booking_date="2026-01-17", amount=5, symbol="AAA", dividend_id="income"
        )
        data = wallet([contribution()], dividends=[dividend])
        quotes = {
            "AAA": [
                HistoricalQuote(
                    "AAA", date(2026, 1, day), 10 if day < 17 else 11, "EUR"
                )
                for day in range(15, 19)
            ]
        }
        result = build_history(data, quotes, today=date(2026, 1, 18))
        whole = result["summaries"]["wallet"]["monthly"][0]
        position = result["summaries"]["positions"]["AAA"]["monthly"][0]
        self.assertEqual(
            (whole["deposits"], whole["dividends"], whole["gain"]), (100, 5, 15)
        )
        self.assertAlmostEqual(whole["return"], 15)
        self.assertEqual(
            (position["purchases"], position["dividends"], position["gain"]),
            (100, 5, 15),
        )
        self.assertAlmostEqual(position["return"], 15)


class UnitCorrectionTests(unittest.TestCase):
    def test_total_correction_changes_one_chosen_lot_but_no_payment(self):
        original = wallet([contribution()])
        candidate, summary = prepare_correction(
            original,
            {"symbol": "AAA", "target": "lot", "mode": "position", "units": 10.25},
            today=date(2026, 1, 31),
        )
        changed = candidate[c.CONF_CONTRIBUTIONS][0]
        self.assertEqual(changed[c.CONTRIBUTION_LOTS][0][c.LOT_UNITS], 10.25)
        self.assertEqual(changed[c.CONTRIBUTION_LOTS][0][c.LOT_AMOUNT], 100)
        self.assertFalse(changed[c.CONTRIBUTION_LOTS][0][c.LOT_ESTIMATED])
        self.assertTrue(changed[c.CONTRIBUTION_MANUALLY_EDITED])
        self.assertEqual(cash_balance(candidate), cash_balance(original))
        self.assertEqual((summary["before_total"], summary["after_total"]), (10, 10.25))
        self.assertEqual(len(candidate[UNIT_CORRECTIONS]), 1)
        self.assertEqual(
            original[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_LOTS][0][c.LOT_UNITS], 10
        )

    def test_included_lot_correction_keeps_opening_quantity_consistent(self):
        data = wallet([contribution(included=True)], opening=10)
        candidate, _ = prepare_correction(
            data,
            {"symbol": "AAA", "target": "lot", "mode": "position", "units": 9.75},
            today=date(2026, 1, 31),
        )
        self.assertEqual(candidate[c.CONF_VALORS][0][c.VALOR_AMOUNT], 9.75)


class FollowupImportTests(unittest.IsolatedAsyncioTestCase):
    async def test_overlap_is_not_duplicated_and_new_month_is_added(self):
        first = statement("first-batch", ["01"])
        existing, _ = await async_prepare_import(
            first, session=object(), today=date(2026, 1, 31)
        )
        existing = add_initial_import_metadata(first, existing, today=date(2026, 1, 31))
        candidate, summary = await async_prepare_followup(
            statement("second-batch", ["01", "02"]),
            existing,
            session=object(),
            today=date(2026, 2, 28),
        )
        self.assertEqual(len(candidate[c.CONF_CONTRIBUTIONS]), 2)
        self.assertEqual(summary["added"]["deposits"], 1)
        self.assertEqual(summary["unchanged"], 1)
        self.assertNotIn(
            "2026-02", candidate[c.CONF_SAVINGS_PLANS][0][c.PLAN_SKIPPED_PERIODS]
        )

    async def test_explicit_units_upgrade_an_estimate_without_changing_cash(self):
        first = statement("first-batch", ["01"])
        existing, _ = await async_prepare_import(
            first, session=object(), today=date(2026, 1, 31)
        )
        # Model an older estimate; reconciliation itself performs no guessing.
        lot = existing[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_LOTS][0]
        lot[c.LOT_UNITS] = 9.5
        lot[c.LOT_ESTIMATED] = True
        existing = add_initial_import_metadata(first, existing, today=date(2026, 1, 31))
        candidate, summary = await async_prepare_followup(
            statement("second-batch", ["01", "02"]),
            existing,
            session=object(),
            today=date(2026, 2, 28),
        )
        updated = candidate[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_LOTS][0]
        self.assertEqual(updated[c.LOT_UNITS], 10)
        self.assertFalse(updated[c.LOT_ESTIMATED])
        self.assertEqual(cash_balance(candidate), cash_balance(existing))
        self.assertEqual(summary["updated"], 1)

    async def test_confirmed_difference_requires_a_visible_decision(self):
        first = statement("first-batch", ["01"])
        existing, _ = await async_prepare_import(
            first, session=object(), today=date(2026, 1, 31)
        )
        existing = add_initial_import_metadata(first, existing, today=date(2026, 1, 31))
        changed = statement("second-batch", ["01"])
        changed["deposits"][0]["amount"] = 101
        candidate, summary = await async_prepare_followup(
            changed, existing, session=object(), today=date(2026, 1, 31)
        )
        self.assertIsNone(candidate)
        self.assertEqual(summary["choices"][0]["kind"], "protected")

        kept, _ = await async_prepare_followup(
            changed,
            existing,
            session=object(),
            today=date(2026, 1, 31),
            decisions={"deposit-01": "keep"},
        )
        self.assertEqual(kept[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_AMOUNT], 100)
        merged, _ = await async_prepare_followup(
            changed,
            existing,
            session=object(),
            today=date(2026, 1, 31),
            decisions={"deposit-01": "merge"},
        )
        self.assertEqual(merged[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_AMOUNT], 101)
        self.assertEqual(cash_balance(merged), 1)


if __name__ == "__main__":
    unittest.main()
