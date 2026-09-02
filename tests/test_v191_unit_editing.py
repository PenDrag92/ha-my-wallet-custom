"""Saved unit corrections must be visible before the coordinator reloads."""

from __future__ import annotations

import unittest
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from tests.bootstrap import install_stubs

install_stubs()

from custom_components.my_wallet import const as c
from custom_components.my_wallet.contributions import make_contribution
from custom_components.my_wallet.corrections import prepare_correction
from custom_components.my_wallet.models import ValorData, WalletData
from custom_components.my_wallet.yahoo import Quote
from tests.test_panel_regressions import Connection, hass_with, panel
from tests.test_v140_features import contribution, wallet


class SavedUnitDisplayTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 2, 1)
        self.data = wallet([contribution()])
        self.cached = WalletData(
            valors={"AAA": ValorData("AAA", 10, 0, Quote("AAA", 20, "EUR"), 1)}
        )

    def payload(self, data, current):
        entry = SimpleNamespace(
            entry_id="wallet",
            title="Wallet",
            data=data,
            runtime_data=SimpleNamespace(data=current, last_update_success=True),
        )
        connection = Connection()
        with patch.object(
            panel.dt_util, "now", return_value=datetime(2026, 2, 1, tzinfo=UTC)
        ):
            panel.ws_wallets(hass_with([entry]), connection, {"id": 1})
        return connection.results[-1][1]["wallets"][0]

    def test_correction_revalues_saved_units_without_mutating_cached_quotes(self):
        corrected, _ = prepare_correction(
            self.data,
            {"symbol": "AAA", "target": "lot", "mode": "position", "units": 9.5},
            today=self.today,
        )
        result = self.payload(corrected, self.cached)
        position = result["positions"][0]
        self.assertEqual(position["units"], 9.5)
        self.assertEqual(position["value"], 190)
        self.assertEqual(position["cost"], 100)
        self.assertEqual(result["total"], 190)
        self.assertEqual((result["invested"], result["cash"]), (100, 0))
        self.assertEqual(self.cached.valors["AAA"].amount, 10)
        self.assertEqual(self.cached.total, 200)

    def test_current_cash_uses_saved_rows_but_not_future_deposits(self):
        self.data[c.CONF_CONTRIBUTIONS].extend(
            [
                make_contribution(25, "2026-02-01", contribution_id="now"),
                make_contribution(500, "2027-03-01", contribution_id="later"),
            ]
        )
        result = self.payload(self.data, self.cached)
        self.assertEqual((result["total"], result["cash"]), (225, 25))
        self.assertEqual(result["invested"], 125)
        self.assertEqual(self.cached.cash_balance, 0)

    def test_missing_quotes_keep_known_units_without_a_partial_portfolio_total(self):
        self.data[c.CONF_VALORS].append(
            {c.VALOR_SYMBOL: "BBB", c.VALOR_AMOUNT: 2, c.VALOR_TARGET_SHARE: 0}
        )
        result = self.payload(self.data, self.cached)
        self.assertIsNone(result["total"])
        second = result["positions"][1]
        self.assertEqual(second["units"], 2)
        self.assertEqual(second["target"], 0)
        self.assertIsNone(second["value"])
        without_quotes = self.payload(self.data, None)
        self.assertEqual(without_quotes["positions"][0]["units"], 10)
        self.assertEqual(without_quotes["positions"][1]["units"], 2)
        self.assertIsNone(without_quotes["total"])
