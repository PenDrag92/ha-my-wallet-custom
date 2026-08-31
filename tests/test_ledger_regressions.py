"""Regression tests for historical cash-ledger invariants."""

from __future__ import annotations

import unittest
from datetime import date

from tests.bootstrap import install_stubs

install_stubs()

from custom_components.my_wallet.const import (  # noqa: E402
    CONF_CONTRIBUTIONS,
    CONF_DIVIDENDS,
    CONTRIBUTION_SOURCE_LEGACY,
)
from custom_components.my_wallet.contributions import (  # noqa: E402
    attach_lot,
    invested_total,
    lot_metrics,
    make_contribution,
    make_lot,
)
from custom_components.my_wallet.dividends import (  # noqa: E402
    cash_balance,
    make_dividend,
    reinvestable_cash,
)


def lot(
    execution_date: str,
    amount: float,
    *,
    included_in_opening: bool = False,
) -> dict[str, object]:
    """Create a compact EUR test lot."""
    return make_lot(
        symbol="A",
        execution_date=execution_date,
        amount=amount,
        unit_price=10,
        quote_currency="EUR",
        included_in_opening=included_in_opening,
    )


class LegacyOpeningLedgerTests(unittest.TestCase):
    def test_legacy_opening_lot_is_cash_neutral(self) -> None:
        legacy = make_contribution(
            75,
            None,
            contribution_id="legacy",
            source=CONTRIBUTION_SOURCE_LEGACY,
        )
        contributions = attach_lot(
            [legacy],
            "legacy",
            lot("2026-01-20", 75, included_in_opening=True),
        )
        data = {CONF_CONTRIBUTIONS: contributions}

        self.assertEqual(invested_total(data), 75)
        self.assertEqual(cash_balance(data, through=date(2026, 1, 31)), 0)

    def test_legacy_rejects_non_opening_lot(self) -> None:
        legacy = make_contribution(
            75,
            None,
            contribution_id="legacy",
            source=CONTRIBUTION_SOURCE_LEGACY,
        )

        with self.assertRaisesRegex(ValueError, "opening-balance"):
            attach_lot([legacy], "legacy", lot("2026-01-20", 25))

    def test_nonlegacy_opening_lot_still_uses_cash(self) -> None:
        funding = make_contribution(75, "2026-01-20", contribution_id="funding")
        contributions = attach_lot(
            [funding],
            "funding",
            lot("2026-01-20", 25, included_in_opening=True),
        )

        self.assertEqual(
            cash_balance(
                {CONF_CONTRIBUTIONS: contributions}, through=date(2026, 1, 20)
            ),
            50,
        )


class FundingDateTests(unittest.TestCase):
    def test_funding_after_lot_date_is_rejected(self) -> None:
        funding = make_contribution(50, "2026-02-01", contribution_id="funding")

        with self.assertRaisesRegex(ValueError, "must not be after"):
            attach_lot([funding], "funding", lot("2026-01-20", 50))

    def test_funding_on_lot_date_is_allowed(self) -> None:
        funding = make_contribution(50, "2026-01-20", contribution_id="funding")

        contributions = attach_lot([funding], "funding", lot("2026-01-20", 50))

        self.assertEqual(
            cash_balance(
                {CONF_CONTRIBUTIONS: contributions}, through=date(2026, 1, 20)
            ),
            0,
        )

    def test_funding_before_lot_date_is_allowed(self) -> None:
        funding = make_contribution(50, "2026-01-15", contribution_id="funding")

        contributions = attach_lot([funding], "funding", lot("2026-01-20", 50))

        self.assertEqual(
            cash_balance(
                {CONF_CONTRIBUTIONS: contributions}, through=date(2026, 1, 19)
            ),
            50,
        )
        self.assertEqual(
            cash_balance(
                {CONF_CONTRIBUTIONS: contributions}, through=date(2026, 1, 20)
            ),
            0,
        )


class ReinvestableCashTests(unittest.TestCase):
    def test_caps_at_minimum_future_running_balance(self) -> None:
        spending = make_contribution(
            75,
            "2026-02-01",
            lots=[lot("2026-02-01", 75.10)],
        )
        replenishment = make_contribution(0.10, "2026-03-01")
        data = {
            CONF_CONTRIBUTIONS: [spending, replenishment],
            CONF_DIVIDENDS: [make_dividend(booking_date="2026-01-01", amount=0.10)],
        }

        self.assertEqual(cash_balance(data, through=date(2026, 1, 20)), 0.10)
        self.assertEqual(cash_balance(data, through=date(2026, 2, 1)), 0)
        self.assertEqual(cash_balance(data, through=date(2026, 3, 2)), 0.10)
        self.assertEqual(
            reinvestable_cash(
                data,
                execution_through=date(2026, 1, 20),
                today=date(2026, 3, 2),
            ),
            0,
        )

    def test_reserved_is_subtracted_after_interval_minimum(self) -> None:
        spending = make_contribution(
            1,
            "2026-02-01",
            lots=[lot("2026-02-01", 2)],
        )
        data = {
            CONF_CONTRIBUTIONS: [spending],
            CONF_DIVIDENDS: [make_dividend(booking_date="2026-01-01", amount=3)],
        }

        self.assertEqual(
            reinvestable_cash(
                data,
                execution_through=date(2026, 1, 20),
                today=date(2026, 2, 2),
                reserved=1.5,
            ),
            0.5,
        )

    def test_events_outside_interval_do_not_lower_available_cash(self) -> None:
        earlier_spending = make_contribution(
            1,
            "2026-01-01",
            lots=[lot("2026-01-01", 1)],
        )
        later_spending = make_contribution(
            1,
            "2026-04-01",
            lots=[lot("2026-04-01", 2)],
        )
        data = {
            CONF_CONTRIBUTIONS: [earlier_spending, later_spending],
            CONF_DIVIDENDS: [make_dividend(booking_date="2026-02-01", amount=1)],
        }

        self.assertEqual(
            reinvestable_cash(
                data,
                execution_through=date(2026, 2, 1),
                today=date(2026, 3, 1),
            ),
            1,
        )


class PerformanceBoundaryTests(unittest.TestCase):
    def test_extreme_short_term_return_does_not_overflow_sensor(self) -> None:
        purchase = make_lot(
            symbol="A",
            execution_date="2026-08-30",
            amount=1,
            unit_price=1,
            quote_currency="EUR",
            units=1,
        )

        metrics = lot_metrics(purchase, 10, date(2026, 8, 31))

        self.assertEqual(metrics["performance_pct"], 900)
        self.assertIsNone(metrics["annualized_performance_pct"])


if __name__ == "__main__":
    unittest.main()
