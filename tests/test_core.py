"""Regression tests for ledger, plans, performance, and market helpers."""

from __future__ import annotations

import math
import unittest
from datetime import UTC, date, datetime
from types import SimpleNamespace

from tests.bootstrap import install_stubs

install_stubs()

from custom_components.my_wallet.const import (  # noqa: E402
    ALLOCATION_MODE_FIXED,
    ALLOCATION_MODE_PERCENTAGE,
    ALLOCATION_SYMBOL,
    ALLOCATION_VALUE,
    CONF_CONTRIBUTIONS,
)
from custom_components.my_wallet.contributions import (  # noqa: E402
    all_lots,
    attach_lot,
    cashflows,
    invested_total,
    make_contribution,
    make_lot,
    xirr,
)
from custom_components.my_wallet.dividends import (  # noqa: E402
    attributed_dividend_flows,
    make_dividend,
    reinvestable_cash,
)
from custom_components.my_wallet.models import ValorData, WalletData  # noqa: E402
from custom_components.my_wallet.plans import (  # noqa: E402
    allocation_amounts,
    due_dates,
    make_plan,
    next_due_date,
)
from custom_components.my_wallet.yahoo import (  # noqa: E402
    _currency_and_factor,
    _market_date_confirmed,
    _to_float,
)


def allocation(symbol: str, value: float) -> dict[str, object]:
    return {ALLOCATION_SYMBOL: symbol, ALLOCATION_VALUE: value}


class AggregateTests(unittest.TestCase):
    def test_partial_quote_never_becomes_false_total(self) -> None:
        good = ValorData("A", 2, 2, quote=SimpleNamespace(price=10), fx_rate=1)
        missing = ValorData("B", 1, 1)
        wallet = WalletData(valors={"A": good, "B": missing}, cash_balance=0.01)
        self.assertIsNone(wallet.securities_total)
        self.assertIsNone(wallet.total)
        self.assertEqual(good.value, 20)

    def test_complete_total_includes_cash(self) -> None:
        valor = ValorData("A", 2, 2, quote=SimpleNamespace(price=10), fx_rate=1.2)
        wallet = WalletData(valors={"A": valor}, cash_balance=0.01)
        self.assertAlmostEqual(wallet.securities_total or 0, 24)
        self.assertAlmostEqual(wallet.total or 0, 24.01)


class PlanTests(unittest.TestCase):
    def _plan(self, first: str, **extra: object) -> dict[str, object]:
        return make_plan(
            name="Monthly",
            first_date=first,
            allocation_mode=ALLOCATION_MODE_FIXED,
            allocations=[allocation("A", 25), allocation("B", 25), allocation("C", 25)],
            plan_id="p1",
            **extra,
        )

    def test_editing_day_does_not_rebook_old_months(self) -> None:
        contributions = [
            make_contribution(
                75,
                f"2026-{month:02d}-20",
                plan_id="p1",
                scheduled_date=f"2026-{month:02d}-20",
            )
            for month in (1, 2)
        ]
        self.assertEqual(
            due_dates(self._plan("2026-01-15"), contributions, date(2026, 3, 31)),
            [date(2026, 3, 15)],
        )

    def test_skipped_month_and_day_one_next_date(self) -> None:
        plan = self._plan("2026-01-01", skipped_periods=["2026-01"])
        self.assertEqual(next_due_date(plan, [], date(2026, 1, 1)), date(2026, 2, 1))

    def test_broker_rounding_example(self) -> None:
        amounts = allocation_amounts(self._plan("2026-01-20"), available_amount=75.10)
        self.assertEqual(amounts, {"A": 25.03, "B": 25.03, "C": 25.03})
        self.assertAlmostEqual(75.10 - sum(amounts.values()), 0.01)

    def test_tiny_percentage_plan_has_no_zero_or_negative_lot(self) -> None:
        plan = make_plan(
            name="Tiny",
            first_date="2026-01-01",
            allocation_mode=ALLOCATION_MODE_PERCENTAGE,
            amount=0.02,
            allocations=[allocation("A", 99), allocation("B", 1)],
        )
        self.assertEqual(allocation_amounts(plan), {"A": 0.01, "B": 0.01})


class LedgerTests(unittest.TestCase):
    def test_lot_can_reuse_existing_contribution_without_doubling(self) -> None:
        contribution = make_contribution(50, "2026-01-20", contribution_id="deposit")
        lot = make_lot(
            symbol="A",
            execution_date="2026-01-20",
            amount=20,
            unit_price=10,
            quote_currency="EUR",
        )
        data = {CONF_CONTRIBUTIONS: attach_lot([contribution], "deposit", lot)}
        self.assertEqual(invested_total(data), 50)
        self.assertEqual(len(all_lots(data)), 1)

    def test_future_records_are_excluded_until_their_date(self) -> None:
        lot = make_lot(
            symbol="A",
            execution_date="2026-02-01",
            amount=50,
            unit_price=10,
            quote_currency="EUR",
        )
        data = {
            CONF_CONTRIBUTIONS: [
                make_contribution(50, "2026-01-01"),
                make_contribution(50, "2026-02-01", lots=[lot]),
            ]
        }
        self.assertEqual(invested_total(data, through=date(2026, 1, 31)), 50)
        self.assertEqual(len(cashflows(data, through=date(2026, 1, 31)) or []), 1)
        self.assertEqual(all_lots(data, through=date(2026, 1, 31)), [])
        self.assertEqual(invested_total(data, through=date(2026, 2, 1)), 100)

    def test_nonfinite_input_is_rejected(self) -> None:
        for value in (math.nan, math.inf, -math.inf):
            with self.assertRaises(ValueError):
                make_contribution(value, "2026-01-01")
            with self.assertRaises(ValueError):
                make_lot(
                    symbol="A",
                    execution_date="2026-01-01",
                    amount=10,
                    unit_price=value,
                    quote_currency="EUR",
                )
            with self.assertRaises(ValueError):
                make_dividend(booking_date="2026-01-01", amount=value)
        self.assertIsNone(xirr([(date(2025, 1, 1), math.nan), (date(2026, 1, 1), 1)]))

    def test_known_xirr(self) -> None:
        result = xirr([(date(2025, 1, 1), -100), (date(2026, 1, 1), 110)])
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result or 0, 0.10, delta=0.001)
        self.assertIsNone(xirr([(date(2026, 1, 1), -100), (date(2026, 1, 1), 110)]))


class DividendTests(unittest.TestCase):
    def test_retroactive_execution_cannot_reuse_already_spent_cash(self) -> None:
        later_lot = make_lot(
            symbol="A",
            execution_date="2026-02-01",
            amount=1.10,
            unit_price=1.10,
            quote_currency="EUR",
        )
        data = {
            CONF_CONTRIBUTIONS: [make_contribution(1, "2026-02-01", lots=[later_lot])],
            "dividends": [make_dividend(booking_date="2026-01-01", amount=0.10)],
        }
        self.assertEqual(
            reinvestable_cash(
                data,
                execution_through=date(2026, 1, 20),
                today=date(2026, 2, 2),
            ),
            0,
        )

    def test_untracked_opening_units_remain_in_denominator(self) -> None:
        lot = make_lot(
            symbol="A",
            execution_date="2026-01-01",
            amount=20,
            unit_price=10,
            quote_currency="EUR",
            units=2,
            included_in_opening=True,
            lot_id="lot-a",
        )
        data = {
            CONF_CONTRIBUTIONS: [make_contribution(20, "2026-01-01", lots=[lot])],
            "dividends": [
                make_dividend(booking_date="2026-04-02", amount=1, symbol="A")
            ],
        }
        flows = attributed_dividend_flows(
            data, symbol="A", opening_units=10, through=date(2026, 4, 2)
        )
        self.assertAlmostEqual(sum(value for _, value in flows["lot-a"]), 0.2)


class YahooHelperTests(unittest.TestCase):
    def test_market_close_and_exchange_timezone(self) -> None:
        before = datetime(2026, 8, 31, 14, tzinfo=UTC).timestamp()
        end = datetime(2026, 8, 31, 20, tzinfo=UTC).timestamp()
        after = datetime(2026, 8, 31, 21, tzinfo=UTC).timestamp()
        self.assertFalse(
            _market_date_confirmed(
                date(2026, 8, 31), "America/New_York", end, now_timestamp=before
            )
        )
        self.assertTrue(
            _market_date_confirmed(
                date(2026, 8, 31), "America/New_York", end, now_timestamp=after
            )
        )
        self.assertTrue(
            _market_date_confirmed(
                date(2026, 8, 28), "America/New_York", end, now_timestamp=after
            )
        )

    def test_minor_currency_and_nonfinite_values(self) -> None:
        self.assertEqual(_currency_and_factor("GBp"), ("GBP", 0.01))
        self.assertEqual(_currency_and_factor("USD"), ("USD", 1.0))
        self.assertIsNone(_to_float(math.nan))
        self.assertIsNone(_to_float(math.inf))


if __name__ == "__main__":
    unittest.main()
