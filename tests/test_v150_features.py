"""Regressions for the 1.5 dashboard, details and backup features."""

from __future__ import annotations

import unittest
from copy import deepcopy
from datetime import UTC, date, datetime
from pathlib import Path
from struct import unpack

from tests.bootstrap import install_stubs

install_stubs()

from custom_components.my_wallet import const as c
from custom_components.my_wallet.backup import (
    BACKUP_RESTORE_ID,
    create_backup,
    prepare_backup,
)
from custom_components.my_wallet.contributions import make_contribution, make_lot
from custom_components.my_wallet.corrections import UNIT_CORRECTIONS
from custom_components.my_wallet.dividends import make_dividend
from custom_components.my_wallet.followup_import import (
    IMPORT_LINKS,
    IMPORT_RECORDS,
)
from custom_components.my_wallet.history_import import IMPORT_BATCH
from custom_components.my_wallet.plans import make_plan

ROOT = Path(__file__).resolve().parents[1]


def wallet_data() -> dict:
    plan = make_plan(
        plan_id="plan",
        name="Monthly",
        first_date="2026-01-20",
        allocation_mode="fixed",
        allocations=[{"symbol": "AAA", "value": 100}],
    )
    lot = make_lot(
        symbol="AAA",
        execution_date="2026-01-20",
        amount=100,
        unit_price=10,
        quote_currency="EUR",
        units=10.123456789,
        estimated=False,
        lot_id="lot",
    )
    contribution = make_contribution(
        100,
        "2026-01-20",
        contribution_id="deposit",
        lots=[lot],
        plan_id="plan",
        scheduled_date="2026-01-20",
    )
    return {
        c.CONF_WALLET_NAME: "Long-term wallet",
        c.CONF_BASE_CURRENCY: "EUR",
        c.CONF_SCAN_INTERVAL: 30,
        c.CONF_EXPECTED_ANNUAL_RETURN: 6.5,
        c.CONF_VALORS: [
            {
                c.VALOR_SYMBOL: "AAA",
                c.VALOR_AMOUNT: 0,
                c.VALOR_ALIAS: "World ETF",
                c.VALOR_TARGET_SHARE: 75,
            }
        ],
        c.CONF_CONTRIBUTIONS: [contribution],
        c.CONF_DIVIDENDS: [
            make_dividend(
                booking_date="2026-02-01",
                amount=1.23,
                symbol="AAA",
                dividend_id="dividend",
            )
        ],
        c.CONF_SAVINGS_PLANS: [plan],
        c.CONF_RETIRED_SAVINGS_PLANS: [],
        IMPORT_BATCH: "original-import",
        IMPORT_RECORDS: [
            {
                "batch_id": "original-import",
                "fingerprint": "a" * 64,
                "date": "2026-01-20",
            }
        ],
        IMPORT_LINKS: {
            "plans": {"source-plan": "plan"},
            "contributions": {"source-deposit": "deposit"},
            "lots": {"source-lot": "lot"},
            "dividends": {"source-dividend": "dividend"},
        },
        UNIT_CORRECTIONS: [{"id": "correction", "note": "Broker statement"}],
    }


class BackupTests(unittest.TestCase):
    def test_backup_round_trip_preserves_financial_state_and_metadata(self):
        original = wallet_data()
        document = create_backup(
            original,
            title="Renamed wallet",
            created_at=datetime(2026, 9, 1, 8, tzinfo=UTC),
        )

        restored, summary = prepare_backup(document, today=date(2026, 9, 1))

        self.assertEqual(restored[c.CONF_VALORS], original[c.CONF_VALORS])
        self.assertEqual(restored[c.CONF_WALLET_NAME], "Renamed wallet")
        self.assertEqual(
            restored[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_LOTS][0][c.LOT_UNITS],
            10.123456789,
        )
        self.assertEqual(restored[c.CONF_DIVIDENDS], original[c.CONF_DIVIDENDS])
        self.assertEqual(restored[c.CONF_SAVINGS_PLANS], original[c.CONF_SAVINGS_PLANS])
        self.assertEqual(restored[c.CONF_EXPECTED_ANNUAL_RETURN], 6.5)
        self.assertEqual(restored[IMPORT_LINKS], original[IMPORT_LINKS])
        self.assertEqual(restored[UNIT_CORRECTIONS], original[UNIT_CORRECTIONS])
        self.assertEqual(restored[BACKUP_RESTORE_ID], document["backup_id"])
        self.assertTrue(summary["backup"])
        self.assertEqual((summary["purchases"], summary["dividends"]), (1, 1))

    def test_backup_rejects_unknown_symbols_without_writing(self):
        document = create_backup(
            wallet_data(),
            title="Wallet",
            created_at=datetime(2026, 9, 1, tzinfo=UTC),
        )
        document = deepcopy(document)
        document["wallet"]["data"][c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_LOTS][0][
            c.LOT_SYMBOL
        ] = "MISSING"

        with self.assertRaisesRegex(ValueError, "invalid_backup"):
            prepare_backup(document, today=date(2026, 9, 1))

    def test_backup_rejects_future_financial_events(self):
        document = create_backup(
            wallet_data(),
            title="Wallet",
            created_at=datetime(2026, 9, 1, tzinfo=UTC),
        )
        document = deepcopy(document)
        document["wallet"]["data"][c.CONF_DIVIDENDS][0][c.DIVIDEND_BOOKING_DATE] = (
            "2026-09-02"
        )

        with self.assertRaisesRegex(ValueError, "future_date"):
            prepare_backup(document, today=date(2026, 9, 1))


class DashboardReleaseTests(unittest.TestCase):
    def test_dashboard_exposes_allocation_details_starts_and_both_exports(self):
        source = (
            ROOT / "custom_components/my_wallet/frontend/my-wallet-panel.js"
        ).read_text(encoding="utf-8")
        for fragment in (
            'portfolioStart: "Depotstart"',
            'positionStart: "Positionsstart"',
            "_renderAllocation(parent, wallet)",
            "const total = forecast ? "
            "(real ? forecast.real_total : forecast.total) : wallet.total",
            "_renderPositionDetails(parent, position, currency)",
            'this._call("backup"',
            'aliasPlaceholder: "z. B. Welt-ETF"',
            ".stat>span{display:block;min-height:3em",
        ):
            self.assertIn(fragment, source)
        self.assertLess(
            source.index("this._renderAllocation(main, wallet);"),
            source.index("this._renderPositions(main, wallet);"),
        )

    def test_local_brand_icon_has_the_hacs_required_dimensions(self):
        icon = ROOT / "custom_components/my_wallet/brand/icon.png"
        content = icon.read_bytes()
        self.assertEqual(content[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(unpack(">II", content[16:24]), (256, 256))


if __name__ == "__main__":
    unittest.main()
