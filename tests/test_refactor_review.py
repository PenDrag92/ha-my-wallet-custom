"""Reproduce regressions found during the 1.11.0 refactor review."""

from __future__ import annotations

import unittest
from copy import deepcopy
from datetime import date, timedelta
from itertools import permutations

from tests.bootstrap import install_stubs

install_stubs()

from custom_components.my_wallet import const as c
from custom_components.my_wallet.contributions import (
    all_lots,
    invested_total,
    make_contribution,
    make_lot,
)
from custom_components.my_wallet.dividends import (
    cash_balance,
    cash_timeline,
    dividend_total,
)
from custom_components.my_wallet.followup_import import (
    IMPORT_LINKS,
    add_initial_import_metadata,
    async_prepare_followup,
)
from custom_components.my_wallet.history_import import _uid, async_prepare_import
from custom_components.my_wallet.ledger import prepare_change
from tests.test_v140_features import statement

TODAY = date(2026, 2, 28)


class ImportOrderReviewTests(unittest.IsolatedAsyncioTestCase):
    async def initial(self, document):
        data, _ = await async_prepare_import(document, session=None, today=TODAY)
        return add_initial_import_metadata(document, data, today=TODAY)

    def assert_source_links(self, document, data):
        links = data[IMPORT_LINKS]
        batch = document["batch_id"]
        for raw in document["deposits"]:
            self.assertEqual(links["contributions"][raw["id"]], _uid(batch, raw["id"]))
            for purchase in raw["purchases"]:
                self.assertEqual(
                    links["lots"][purchase["id"]], _uid(batch, purchase["id"])
                )
        for raw in document["dividends"]:
            self.assertEqual(links["dividends"][raw["id"]], _uid(batch, raw["id"]))

    async def test_initial_import_latest_first_with_different_purchase_counts(self):
        document = statement("reverse", ["02", "01"])
        document["deposits"][0]["purchases"].append(
            {
                "id": "second-february-purchase",
                "date": "2026-02-20",
                "symbol": "AAA",
                "amount": 10,
                "units": 1,
            }
        )
        document["deposits"][0]["amount"] += 10
        result = await self.initial(document)
        self.assert_source_links(document, result)
        self.assertEqual(len(all_lots(result)), 3)
        self.assertEqual((invested_total(result), cash_balance(result)), (210, 0))

    async def test_same_day_deposits_and_dividends_keep_links_in_every_order(self):
        original = statement("same-day", ["01"])
        original["plans"] = []
        rows = []
        for number in range(3):
            row = deepcopy(original["deposits"][0])
            row.pop("plan_id")
            row.pop("scheduled_date")
            row["id"] = f"deposit-{number}"
            row["purchases"][0]["id"] = f"purchase-{number}"
            rows.append(row)
        dividends = [
            {
                "id": f"dividend-{number}",
                "booking_date": "2026-01-21",
                "amount": number + 1,
                "symbol": "AAA",
            }
            for number in range(3)
        ]
        for order in permutations(range(3)):
            with self.subTest(order=order):
                document = {
                    **original,
                    "deposits": [rows[i] for i in order],
                    "dividends": [dividends[i] for i in order],
                }
                result = await self.initial(document)
                self.assert_source_links(document, result)

    async def test_reversed_followup_confirms_estimate_and_adds_only_new_month(self):
        before = await self.initial(statement("old", ["01"]))
        purchase = before[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_LOTS][0]
        purchase[c.LOT_ESTIMATED] = True
        purchase[c.LOT_UNITS] = 9.5
        candidate, summary = await async_prepare_followup(
            statement("next", ["02", "01"]),
            before,
            session=None,
            today=TODAY,
        )
        self.assertIsNotNone(candidate)
        self.assertEqual(summary["choices"], [])
        self.assertEqual(summary["added"]["deposits"], 1)
        self.assertEqual(summary["added"]["purchases"], 1)
        self.assertEqual(
            [(lot[c.LOT_DATE], lot[c.LOT_UNITS]) for lot in all_lots(candidate)],
            [("2026-01-20", 10), ("2026-02-20", 10)],
        )
        self.assertEqual((invested_total(candidate), cash_balance(candidate)), (200, 0))
        links = candidate[IMPORT_LINKS]["contributions"]
        self.assertEqual(links["deposit-01"], _uid("old", "deposit-01"))
        self.assertEqual(links["deposit-02"], _uid("next", "deposit-02"))
        self.assertEqual(purchase[c.LOT_UNITS], 9.5)

    async def test_reversed_dividends_in_followup_do_not_suppress_new_income(self):
        original = statement("old", ["01"])
        january = {
            "id": "january-income",
            "booking_date": "2026-01-21",
            "amount": 1,
            "symbol": "AAA",
        }
        february = {
            "id": "february-income",
            "booking_date": "2026-02-21",
            "amount": 2,
            "symbol": "AAA",
        }
        original["dividends"] = [january]
        before = await self.initial(original)
        incoming = statement("next", ["01", "02"])
        incoming["dividends"] = [february, january]
        candidate, summary = await async_prepare_followup(
            incoming, before, session=None, today=TODAY
        )
        self.assertIsNotNone(candidate)
        self.assertEqual(summary["added"]["dividends"], 1)
        self.assertEqual(dividend_total(candidate), 3)
        self.assertEqual(cash_balance(candidate), 3)
        links = candidate[IMPORT_LINKS]["dividends"]
        self.assertEqual(links["january-income"], _uid("old", "january-income"))
        self.assertEqual(links["february-income"], _uid("next", "february-income"))


class CashPrecisionReviewTests(unittest.TestCase):
    def funded_purchase(self):
        start = date(2025, 1, 1)
        initial = 1_000_000_000
        deposits = [make_contribution(initial, start, contribution_id="initial")]
        deposits.extend(
            make_contribution(
                0.01, start + timedelta(days=day), contribution_id=f"credit-{day}"
            )
            for day in range(1, 101)
        )
        before = {
            c.CONF_VALORS: [{c.VALOR_SYMBOL: "AAA", c.VALOR_AMOUNT: 0}],
            c.CONF_CONTRIBUTIONS: deposits,
        }
        execution = start + timedelta(days=101)
        purchase = make_lot(
            symbol="AAA",
            execution_date=execution,
            amount=initial + 1,
            unit_price=1,
            quote_currency="EUR",
            lot_id="purchase",
        )
        after = {
            **before,
            c.CONF_CONTRIBUTIONS: [
                *deposits,
                make_contribution(
                    0,
                    execution,
                    source=c.CONTRIBUTION_SOURCE_PURCHASE,
                    lots=[purchase],
                    contribution_id="purchase-record",
                ),
            ],
        }
        return before, after, execution

    def test_each_closing_balance_matches_full_cash_sum(self):
        _, data, execution = self.funded_purchase()
        self.assertEqual(cash_balance(data), 0)
        timeline = cash_timeline(data)
        self.assertEqual(len(timeline), 102)
        for day, balance in timeline.items():
            with self.subTest(day=day):
                self.assertEqual(balance, cash_balance(data, through=day))
        self.assertEqual(timeline[execution], 0)

    def test_small_credits_fund_purchase_without_allowing_a_real_deficit(self):
        before, after, execution = self.funded_purchase()
        prepared = prepare_change(before, after, today=execution)
        self.assertEqual(cash_balance(prepared), 0)
        self.assertEqual(cash_balance(before), 1_000_000_001)

        short = deepcopy(after)
        short[c.CONF_CONTRIBUTIONS].pop(1)
        with self.assertRaisesRegex(ValueError, "cash_conflict"):
            prepare_change(before, short, today=execution)
