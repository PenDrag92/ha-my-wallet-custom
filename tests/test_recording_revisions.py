"""Recorded accounting distinguishes metadata, new flows and financial edits."""

import unittest
from copy import deepcopy
from datetime import date

from tests.bootstrap import install_stubs
from tests.test_v190_planning import wallet

install_stubs()

from custom_components.my_wallet import const as c
from custom_components.my_wallet.contributions import make_contribution, make_lot
from custom_components.my_wallet.corrections import prepare_correction
from custom_components.my_wallet.dividends import make_dividend
from custom_components.my_wallet.ledger import (
    book_purchase,
    edit_contribution,
    prepare_change,
)
from custom_components.my_wallet.recorded_history import accounting_snapshot

TODAY = date(2026, 9, 9)


def snapshot(data, symbol=None):
    return accounting_snapshot(data, today=TODAY, symbol=symbol)


class RecordingRevisionTests(unittest.TestCase):
    def corrected(self):
        data = wallet(planned=False)
        lot = data[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_LOTS][0]
        corrected, _ = prepare_correction(
            data,
            {
                "symbol": "AAA",
                "mode": "lot",
                "target": lot[c.LOT_ID],
                "units": 11,
                "note": "Exact quantity",
            },
            today=TODAY,
        )
        return corrected

    def test_note_edit_on_corrected_purchase_keeps_financial_revision(self):
        data = self.corrected()
        original = deepcopy(data)
        edited = edit_contribution(
            data,
            "initial",
            amount=100,
            execution_date="2026-08-01",
            note="New description only",
            today=TODAY,
        )
        for symbol in (None, "AAA"):
            before, after = snapshot(data, symbol), snapshot(edited, symbol)
            # Reproduce the false alarm in the old, metadata-sensitive marker.
            self.assertNotEqual(before["revision"], after["revision"])
            self.assertEqual(before["financial_revision"], after["financial_revision"])
            self.assertEqual(before["capital"], after["capital"])
        self.assertEqual(data, original)

    def test_aliases_and_correction_notes_are_not_financial_edits(self):
        data = self.corrected()
        candidate = deepcopy(data)
        candidate[c.CONF_WALLET_NAME] = "Renamed wallet"
        candidate[c.CONF_VALORS][0][c.VALOR_ALIAS] = "World ETF"
        candidate["unit_corrections"][0]["note"] = "Corrected spelling"
        candidate = prepare_change(data, candidate, today=TODAY)
        for symbol in (None, "AAA", "BBB"):
            self.assertEqual(
                snapshot(data, symbol)["financial_revision"],
                snapshot(candidate, symbol)["financial_revision"],
            )

    def test_new_purchase_on_edited_deposit_is_still_an_ordinary_cash_flow(self):
        data = wallet(planned=False)
        data = edit_contribution(
            data,
            "initial",
            amount=200,
            execution_date="2026-08-01",
            note="Funding",
            today=TODAY,
        )
        purchased = book_purchase(
            data,
            make_lot(
                symbol="AAA",
                execution_date="2026-09-09",
                amount=50,
                unit_price=10,
                quote_currency="EUR",
            ),
            today=TODAY,
            funding_id="initial",
        )
        for symbol in (None, "AAA"):
            self.assertNotEqual(
                snapshot(data, symbol)["revision"],
                snapshot(purchased, symbol)["revision"],
            )
            self.assertEqual(
                snapshot(data, symbol)["financial_revision"],
                snapshot(purchased, symbol)["financial_revision"],
            )
        self.assertEqual(
            snapshot(purchased, "AAA")["capital"] - snapshot(data, "AAA")["capital"], 50
        )
        candidate = deepcopy(purchased)
        candidate[c.CONF_CONTRIBUTIONS].append(make_contribution(25, TODAY))
        candidate[c.CONF_DIVIDENDS].append(
            make_dividend(booking_date=TODAY, amount=2, symbol="AAA")
        )
        added = prepare_change(purchased, candidate, today=TODAY)
        self.assertEqual(
            snapshot(purchased)["financial_revision"],
            snapshot(added)["financial_revision"],
        )
        self.assertEqual(snapshot(added)["income"], 2)

    def test_real_correction_and_reversal_remain_visible_and_position_scoped(self):
        data = wallet(planned=False)
        corrected = self.corrected()
        for symbol in (None, "AAA"):
            self.assertNotEqual(
                snapshot(data, symbol)["financial_revision"],
                snapshot(corrected, symbol)["financial_revision"],
            )
        self.assertEqual(
            snapshot(data, "BBB")["financial_revision"],
            snapshot(corrected, "BBB")["financial_revision"],
        )
        edited = edit_contribution(
            corrected,
            "initial",
            amount=120,
            execution_date="2026-08-01",
            note=None,
            today=TODAY,
        )
        reversed_edit = edit_contribution(
            edited,
            "initial",
            amount=100,
            execution_date="2026-08-01",
            note=None,
            today=TODAY,
        )
        self.assertEqual(
            len(
                {
                    snapshot(row)["financial_revision"]
                    for row in (corrected, edited, reversed_edit)
                }
            ),
            3,
        )
        self.assertEqual(
            snapshot(corrected, "AAA")["financial_revision"],
            snapshot(edited, "AAA")["financial_revision"],
        )

    def test_opening_units_are_tracked_without_numeric_format_false_positives(self):
        data = wallet(planned=False)
        data[c.CONF_VALORS][1][c.VALOR_AMOUNT] = 2
        other = deepcopy(data)
        other[c.CONF_VALORS][1][c.VALOR_AMOUNT] = 2.0
        self.assertEqual(
            snapshot(data)["financial_revision"], snapshot(other)["financial_revision"]
        )
        other[c.CONF_VALORS][1][c.VALOR_AMOUNT] = 3
        self.assertNotEqual(
            snapshot(data)["financial_revision"], snapshot(other)["financial_revision"]
        )
        self.assertEqual(
            snapshot(data, "AAA")["financial_revision"],
            snapshot(other, "AAA")["financial_revision"],
        )
