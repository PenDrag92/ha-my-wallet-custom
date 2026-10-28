"""Prevent source matching from silently discarding equal incoming cash events."""

from __future__ import annotations

import unittest
from copy import deepcopy
from datetime import date

from tests.bootstrap import install_stubs
from tests.test_v140_features import wallet

install_stubs()

from custom_components.my_wallet import const as c
from custom_components.my_wallet.contributions import (
    all_lots,
    invested_total,
    make_contribution,
)
from custom_components.my_wallet.dividends import dividend_total, make_dividend
from custom_components.my_wallet.followup_import import (
    IMPORT_LINKS,
    add_initial_import_metadata,
    async_prepare_followup,
)
from custom_components.my_wallet.history_import import async_prepare_import
from custom_components.my_wallet.statement_documents import (
    parse_csv_document,
    prepare_document,
)

TODAY = date(2026, 9, 14)


def document(batch, *, deposits=None, dividends=None):
    return {
        "format": "my_wallet_history",
        "version": 1,
        "batch_id": batch,
        "wallet_name": "Synthetic",
        "base_currency": "EUR",
        "assets": [{"symbol": "AAA"}],
        "plans": [],
        "deposits": deposits
        if deposits is not None
        else [{"id": "initial", "date": "2026-01-01", "amount": 100}],
        "dividends": dividends or [],
    }


class ImportMatchingRegressions(unittest.IsolatedAsyncioTestCase):
    async def initial(self, doc):
        data, _ = await async_prepare_import(doc, session=None, today=TODAY)
        return add_initial_import_metadata(doc, data, today=TODAY)

    async def test_equal_new_deposits_and_dividends_do_not_match_each_other(self):
        before = await self.initial(document("initial"))
        for reverse in (False, True):
            deposits = [
                {"id": f"deposit-{i}", "date": "2026-02-01", "amount": 20}
                for i in range(2)
            ]
            dividends = [
                {
                    "id": f"dividend-{i}",
                    "booking_date": "2026-02-01",
                    "amount": 10,
                    "symbol": "AAA",
                }
                for i in range(2)
            ]
            if reverse:
                deposits.reverse()
                dividends.reverse()
            result, summary = await async_prepare_followup(
                document("new", deposits=deposits, dividends=dividends),
                before,
                session=None,
                today=TODAY,
            )
            self.assertEqual(
                (invested_total(result), dividend_total(result)), (140, 20)
            )
            self.assertEqual(
                (summary["added"]["deposits"], summary["added"]["dividends"]), (2, 2)
            )

    async def test_later_stable_id_is_reserved_against_earlier_fallback(self):
        original = document(
            "initial",
            dividends=[
                {
                    "id": "known-div",
                    "booking_date": "2026-01-02",
                    "amount": 10,
                    "symbol": "AAA",
                }
            ],
        )
        before = await self.initial(original)
        incoming = deepcopy(original)
        incoming["batch_id"] = "next"
        incoming["deposits"].insert(
            0, {"id": "new-deposit", "date": "2026-01-01", "amount": 100}
        )
        incoming["dividends"].insert(
            0,
            {
                "id": "new-div",
                "booking_date": "2026-01-02",
                "amount": 10,
                "symbol": "AAA",
            },
        )
        result, summary = await async_prepare_followup(
            incoming, before, session=None, today=TODAY
        )
        self.assertEqual((invested_total(result), dividend_total(result)), (200, 20))
        self.assertEqual(
            result[IMPORT_LINKS]["contributions"]["initial"],
            before[IMPORT_LINKS]["contributions"]["initial"],
        )
        self.assertEqual(summary["added"]["dividends"], 1)

    async def test_ambiguous_dividends_require_explicit_selection(self):
        before = wallet(
            [make_contribution(100, "2026-01-01")],
            dividends=[
                make_dividend(
                    amount=10,
                    booking_date="2026-01-02",
                    symbol="AAA",
                    dividend_id=f"manual-{i}",
                )
                for i in range(2)
            ],
        )
        incoming = document(
            "next",
            dividends=[
                {
                    "id": "unlinked",
                    "booking_date": "2026-01-02",
                    "amount": 10,
                    "symbol": "AAA",
                }
            ],
        )
        result, summary = await async_prepare_followup(
            incoming, before, session=None, today=TODAY
        )
        self.assertIsNone(result)
        self.assertEqual(summary["choices"][0]["id"], "unlinked")
        self.assertEqual(len(summary["choices"][0]["options"]), 2)
        result, _ = await async_prepare_followup(
            incoming,
            before,
            session=None,
            today=TODAY,
            decisions={"unlinked": "manual-1"},
        )
        self.assertEqual(dividend_total(result), 20)
        self.assertEqual(result[IMPORT_LINKS]["dividends"]["unlinked"], "manual-1")

    async def test_changed_dividend_with_stable_id_requires_keep_or_merge(self):
        original = document(
            "initial",
            dividends=[
                {
                    "id": "income",
                    "booking_date": "2026-01-02",
                    "amount": 10,
                    "symbol": "AAA",
                }
            ],
        )
        before = await self.initial(original)
        changed = deepcopy(original)
        changed["batch_id"] = "changed"
        changed["dividends"][0]["amount"] = 12
        pending, preview = await async_prepare_followup(
            changed, before, session=None, today=TODAY
        )
        self.assertIsNone(pending)
        self.assertEqual(preview["choices"][0]["kind"], "protected")
        for choice, total in (("keep", 10), ("merge", 12)):
            result, _ = await async_prepare_followup(
                changed, before, session=None, today=TODAY, decisions={"income": choice}
            )
            self.assertEqual(dividend_total(result), total)
            self.assertEqual(
                result[c.CONF_DIVIDENDS][0][c.DIVIDEND_ID],
                before[c.CONF_DIVIDENDS][0][c.DIVIDEND_ID],
            )

    async def test_document_to_json_overlap_reviews_independent_cash_and_purchase(self):
        csv = (
            "type,id,date,amount,currency,symbol,units\n"
            "deposit,initial,2026-01-01,100,EUR,,\n"
            "purchase,buy,2026-01-02,50,EUR,AAA,5\n"
            "dividend,income,2026-01-03,5,EUR,AAA,\n"
        )
        draft = parse_csv_document(csv, filename="source.csv", source_id="Broker")
        before, _ = prepare_document(draft, wallet(), today=TODAY)
        incoming = document(
            "json",
            dividends=[
                {
                    "id": "income",
                    "booking_date": "2026-01-03",
                    "amount": 5,
                    "symbol": "AAA",
                }
            ],
        )
        incoming["deposits"][0]["purchases"] = [
            {
                "id": "buy",
                "date": "2026-01-02",
                "amount": 50,
                "symbol": "AAA",
                "units": 5,
            }
        ]
        pending, preview = await async_prepare_followup(
            incoming, before, session=None, today=TODAY
        )
        self.assertIsNone(pending)
        choices = {row["id"]: row["options"][0]["id"] for row in preview["choices"]}
        # After selecting the existing standalone purchase, the actual deposit
        # can also be matched without inventing a second funding event.
        pending, preview = await async_prepare_followup(
            incoming, before, session=None, today=TODAY, decisions=choices
        )
        choices.update(
            {row["id"]: row["options"][0]["id"] for row in preview["choices"]}
        )
        candidate, _ = await async_prepare_followup(
            incoming, before, session=None, today=TODAY, decisions=choices
        )
        self.assertEqual(
            (invested_total(candidate), dividend_total(candidate)), (100, 5)
        )
        self.assertEqual(len(all_lots(candidate)), 1)
        later = deepcopy(incoming)
        later["batch_id"] = "json-again"
        later["wallet_name"] = "Different name ensures fingerprint differs"
        replay, _ = await async_prepare_followup(
            later, candidate, session=None, today=TODAY
        )
        self.assertEqual(len(all_lots(replay)), 1)
        self.assertEqual(invested_total(replay), 100)


if __name__ == "__main__":
    unittest.main()
