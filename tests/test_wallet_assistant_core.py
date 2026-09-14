"""Financial invariants across assistant snapshots, reports and previews."""

from __future__ import annotations

import copy
import json
import unittest
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from tests.bootstrap import install_stubs

install_stubs()

from custom_components.my_wallet import const as c
from custom_components.my_wallet.contributions import make_contribution, make_lot
from custom_components.my_wallet.dividends import make_dividend
from custom_components.my_wallet.history import build_history
from custom_components.my_wallet.models import ValorData, WalletData
from custom_components.my_wallet.plans import make_plan
from custom_components.my_wallet.wallet_allocation import allocate_deposit
from custom_components.my_wallet.wallet_insights import build_wallet_insights
from custom_components.my_wallet.wallet_scenarios import build_wallet_scenario
from custom_components.my_wallet.wallet_snapshot import wallet_with_saved_units
from custom_components.my_wallet.yahoo import HistoricalQuote

TODAY = date(2026, 9, 14)


def wallet(*, prices=(12, 10), targets=(60, 40), cash=100):
    """1000 deposited, 900 spent; quotes are deliberately separate from books."""
    lots = [
        make_lot(
            symbol=symbol,
            execution_date="2026-01-01",
            amount=amount,
            unit_price=10,
            quote_currency="EUR",
            lot_id=f"lot-{symbol}",
            estimated=False,
        )
        for symbol, amount in (("AAA", 600), ("BBB", 300))
    ]
    data = {
        c.CONF_BASE_CURRENCY: "EUR",
        c.CONF_VALORS: [
            {c.VALOR_SYMBOL: symbol, c.VALOR_AMOUNT: 0, c.VALOR_TARGET_SHARE: target}
            for symbol, target in zip(("AAA", "BBB"), targets, strict=True)
        ],
        c.CONF_CONTRIBUTIONS: [
            make_contribution(
                900 + cash, "2026-01-01", lots=lots, contribution_id="funding"
            )
        ],
        c.CONF_DIVIDENDS: [],
        c.CONF_SAVINGS_PLANS: [],
        c.CONF_EXPECTED_ANNUAL_RETURN: 0,
    }
    current = WalletData(
        valors={
            symbol: ValorData(
                symbol,
                999,
                0,
                quote=SimpleNamespace(price=price, previous_close=None),
                fx_rate=1,
            )
            for symbol, price in zip(("AAA", "BBB"), prices, strict=True)
        },
        cash_balance=999,
        sampled_at="2026-09-14T10:00:00+00:00",
    )
    return data, current


def savings_plan(*, amount=100, first="2026-10-01", end=None, skipped=()):
    return make_plan(
        name="Monthly",
        first_date=first,
        end_date=end,
        plan_id="plan-a",
        allocation_mode=c.ALLOCATION_MODE_PERCENTAGE,
        amount=amount,
        allocations=[{c.ALLOCATION_SYMBOL: "AAA", c.ALLOCATION_VALUE: 100}],
        skipped_periods=skipped,
    )


def monthly_history(*, gap=False, unknown=False):
    """AAA rises 20 and pays 5; new funding/purchase of BBB earns zero."""
    points = []
    day = date(2026, 8, 31)
    while day <= TODAY:
        after = day >= date(2026, 9, 1)
        a = 100 + (20 * (day - date(2026, 8, 31)).days / 14)
        points.append(
            {
                "date": day.isoformat(),
                "value": a + 50 + (105 if after else 0),
                "invested": 200 if after else 100,
                "positions": {"AAA": a, "BBB": 100 if after else 0},
                "position_costs": {"AAA": 100, "BBB": 100 if after else 0},
                "position_dividends": {"AAA": 5 if after else 0, "BBB": 0},
            }
        )
        day += timedelta(days=1)
    if gap:
        points[5]["value"] = None
        points[5]["positions"]["AAA"] = None
    return {
        "points": points,
        "ledger": [
            {"id": "dep", "date": "2026-09-01", "type": "deposit", "amount": 100},
            {
                "id": "buy",
                "date": "2026-09-01",
                "type": "purchase",
                "amount": -100,
                "symbol": "BBB",
            },
            {
                "id": "div",
                "date": "2026-09-01",
                "type": "dividend",
                "amount": 5,
                "symbol": "AAA",
            },
        ],
        "unknown_opening": ["AAA"] if unknown else [],
        "estimated": False,
    }


class SnapshotAndInsightTests(unittest.TestCase):
    def test_reconstructed_history_pipeline_ignores_gaps_outside_report_month(self):
        data, current = wallet()
        histories = {"AAA": [], "BBB": []}
        day = date(2026, 8, 31)
        while day <= TODAY:
            for symbol in histories:
                price = 12 if symbol == "AAA" and day == TODAY else 10
                histories[symbol].append(HistoricalQuote(symbol, day, price, "EUR"))
            day += timedelta(days=1)
        history = build_history(data, histories, today=TODAY)
        self.assertTrue(history["missing_history"])
        report = build_wallet_insights(data, current, today=TODAY, history=history)
        self.assertEqual(report["period"]["status"], "ok")
        self.assertEqual(report["period"]["wallet"]["gain"], 120)
        self.assertEqual(report["period"]["reconciliation"]["position_gain"], 120)

    def test_saved_units_and_cash_replace_stale_coordinator_without_mutation(self):
        data, current = wallet()
        original = copy.deepcopy(data)
        refreshed = wallet_with_saved_units(data, current, today=TODAY)
        self.assertEqual(refreshed.valors["AAA"].amount, 60)
        self.assertEqual(refreshed.total, 1120)
        self.assertEqual(refreshed.cash_balance, 100)
        self.assertEqual(current.valors["AAA"].amount, 999)
        self.assertEqual(current.cash_balance, 999)
        self.assertEqual(data, original)
        self.assertEqual(refreshed.sampled_at, current.sampled_at)

    def test_current_facts_use_shared_valuation_and_internal_dividends(self):
        data, current = wallet()
        data[c.CONF_DIVIDENDS] = [
            make_dividend(
                booking_date="2026-09-01", amount=20, symbol="AAA", dividend_id="div"
            )
        ]
        report = build_wallet_insights(data, current, today=TODAY)
        self.assertEqual(report["facts"]["total"], 1140)
        self.assertEqual(report["facts"]["profit"], 140)
        self.assertEqual(report["facts"]["invested"], 1000)
        self.assertEqual(report["facts"]["dividends"], 20)
        self.assertEqual(report["facts"]["nominal"]["income"], 0)
        self.assertIsNone(report["facts"]["real"]["profit"])
        self.assertEqual(report["period"]["reason"], "history_unavailable")
        json.dumps(report, allow_nan=False)

    def test_failed_or_missing_quotes_do_not_produce_partial_wallet_total(self):
        for mode in ("failed", "missing", "nan"):
            with self.subTest(mode=mode):
                data, current = wallet()
                if mode == "missing":
                    current.valors["BBB"].quote = None
                if mode == "nan":
                    current.valors["BBB"].quote.price = float("nan")
                report = build_wallet_insights(
                    data, current, today=TODAY, available=mode != "failed"
                )
                self.assertIsNone(report["facts"]["total"])
                self.assertIsNone(report["facts"]["profit"])
                json.dumps(report, allow_nan=False)

    def test_unknown_opening_cost_stays_unknown(self):
        data, current = wallet()
        data[c.CONF_VALORS][0][c.VALOR_AMOUNT] = 10
        report = build_wallet_insights(data, current, today=TODAY)
        position = report["positions"][0]
        self.assertIsNone(position["nominal"]["cost"])
        self.assertIsNone(position["nominal"]["profit"])
        self.assertIsNotNone(position["tracked"]["profit"])
        self.assertIn(
            "incomplete_opening_cost", [f["code"] for f in report["findings"]]
        )

    def test_duplicate_detection_is_suspected_and_preserves_both_records(self):
        data, current = wallet()
        duplicate = copy.deepcopy(data[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_LOTS][0])
        duplicate[c.LOT_ID] = "another-order"
        data[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_LOTS].append(duplicate)
        before = copy.deepcopy(data)
        report = build_wallet_insights(data, current, today=TODAY)
        duplicate_findings = [
            f for f in report["findings"] if f["code"] == "possible_duplicate_purchase"
        ]
        self.assertEqual(len(duplicate_findings), 1)
        self.assertEqual(
            set(duplicate_findings[0]["evidence"]["lot_ids"]),
            {"lot-AAA", "another-order"},
        )
        self.assertEqual(data, before)

    def test_monthly_attribution_reconciles_deposits_purchases_and_dividends(self):
        data, current = wallet()
        report = build_wallet_insights(
            data, current, today=TODAY, history=monthly_history()
        )
        period = report["period"]
        self.assertEqual(period["status"], "ok")
        self.assertEqual(period["wallet"]["gain"], 25)
        self.assertEqual(period["positions"][0]["symbol"], "AAA")
        self.assertEqual(period["positions"][0]["gain"], 25)
        self.assertEqual(period["positions"][1]["gain"], 0)
        self.assertTrue(period["reconciliation"]["complete"])
        self.assertNotEqual(period["wallet"]["gain"], report["facts"]["profit"])

    def test_period_quote_gap_suppresses_endpoint_gain_and_return(self):
        data, current = wallet()
        report = build_wallet_insights(
            data, current, today=TODAY, history=monthly_history(gap=True)
        )
        self.assertEqual(report["period"]["reason"], "incomplete_period_history")
        self.assertIsNone(report["period"]["wallet"]["gain"])
        self.assertIsNone(
            next(p for p in report["period"]["positions"] if p["symbol"] == "AAA")[
                "gain"
            ]
        )

    def test_unknown_opening_blocks_position_attribution(self):
        data, current = wallet()
        report = build_wallet_insights(
            data, current, today=TODAY, history=monthly_history(unknown=True)
        )
        self.assertIsNone(
            next(p for p in report["period"]["positions"] if p["symbol"] == "AAA")[
                "gain"
            ]
        )
        self.assertEqual(report["period"]["status"], "unavailable")

    def test_no_opening_boundary_is_not_a_full_month(self):
        data, current = wallet()
        history = monthly_history()
        history["points"] = history["points"][1:]
        report = build_wallet_insights(data, current, today=TODAY, history=history)
        self.assertIsNone(report["period"]["wallet"]["gain"])

    def test_unassigned_dividend_reconciles_to_cash_component(self):
        data, current = wallet()
        history = monthly_history()
        history["ledger"][2].pop("symbol")
        period = build_wallet_insights(data, current, today=TODAY, history=history)[
            "period"
        ]
        self.assertEqual(period["reconciliation"]["position_gain"], 20)
        self.assertEqual(period["reconciliation"]["unassigned_dividends"], 5)
        self.assertTrue(period["reconciliation"]["complete"])

    def test_plan_identifiers_are_discoverable_and_invalid_month_rejected(self):
        data, current = wallet()
        data[c.CONF_SAVINGS_PLANS] = [savings_plan()]
        self.assertEqual(
            build_wallet_insights(data, current, today=TODAY)["plans"][0]["id"],
            "plan-a",
        )
        for month in ("2026-13", "2027-01", "2026-9", "bad", True):
            with (
                self.subTest(month=month),
                self.assertRaisesRegex(ValueError, "invalid_report_month"),
            ):
                build_wallet_insights(data, current, today=TODAY, month=month)


class ScenarioTests(unittest.TestCase):
    def test_undocumented_opening_does_not_prevent_actual_value_scenario(self):
        data, current = wallet()
        data[c.CONF_VALORS][0][c.VALOR_AMOUNT] = 10
        result = build_wallet_scenario(data, current, today=TODAY, years=1)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["baseline"]["initial_value"], 1240)

    def test_historical_plan_definitions_do_not_reapply_past_rates(self):
        data, current = wallet()
        plan = savings_plan(amount=200, first="2026-01-01")
        plan[c.PLAN_EFFECTIVE_FROM] = "2026-09-01"
        plan[c.PLAN_HISTORY] = [
            {
                **savings_plan(amount=100, first="2026-01-01"),
                c.PLAN_VALID_UNTIL: "2026-08-31",
            }
        ]
        data[c.CONF_SAVINGS_PLANS] = [plan]
        result = build_wallet_scenario(data, current, today=TODAY, years=1)
        self.assertEqual(result["baseline"]["future_contributions"], 2400)

    def test_baseline_starts_at_actual_value_not_historical_target(self):
        data, current = wallet()
        result = build_wallet_scenario(data, current, today=TODAY, years=1)
        self.assertEqual(result["baseline"]["initial_value"], 1120)
        self.assertEqual(result["baseline"]["final_value"], 1120)
        self.assertEqual(result["difference"]["final_value"], 0)

    def test_existing_and_additional_funding_are_each_counted_once(self):
        data, current = wallet()
        data[c.CONF_SAVINGS_PLANS] = [savings_plan()]
        data[c.CONF_CONTRIBUTIONS].append(
            make_contribution(250, "2026-12-15", contribution_id="future")
        )
        before = copy.deepcopy(data)
        result = build_wallet_scenario(
            data,
            current,
            today=TODAY,
            years=1,
            monthly_extra=10,
            one_off=50,
            start_date="2026-10-01",
        )
        self.assertEqual(result["baseline"]["future_contributions"], 1450)
        self.assertEqual(result["scenario"]["future_contributions"], 1620)
        self.assertEqual(result["difference"]["final_value"], 170)
        self.assertEqual(data, before)

    def test_schedule_skips_end_dates_and_future_rate_override_are_respected(self):
        data, current = wallet()
        data[c.CONF_SAVINGS_PLANS] = [
            savings_plan(end="2027-03-01", skipped=["2026-11"])
        ]
        result = build_wallet_scenario(
            data,
            current,
            today=TODAY,
            years=1,
            plan_id="plan-a",
            monthly_amount=200,
            start_date="2027-01-01",
        )
        self.assertEqual(result["baseline"]["future_contributions"], 500)
        self.assertEqual(result["scenario"]["future_contributions"], 800)
        self.assertEqual(result["affected_plan_payments"], 3)

    def test_pause_suspends_only_selected_plan_funding_not_manual_deposit(self):
        data, current = wallet()
        data[c.CONF_SAVINGS_PLANS] = [savings_plan()]
        data[c.CONF_CONTRIBUTIONS].append(
            make_contribution(250, "2027-01-15", contribution_id="future")
        )
        result = build_wallet_scenario(
            data,
            current,
            today=TODAY,
            years=1,
            plan_id="plan-a",
            start_date="2027-01-01",
            pause_until="2027-03-01",
        )
        self.assertEqual(result["difference"]["future_contributions"], -300)
        self.assertEqual(result["affected_plan_payments"], 3)
        self.assertEqual(result["scenario"]["future_contributions"], 1150)

    def test_zero_rate_override_is_valid(self):
        data, current = wallet()
        data[c.CONF_SAVINGS_PLANS] = [savings_plan()]
        result = build_wallet_scenario(
            data, current, today=TODAY, years=1, plan_id="plan-a", monthly_amount=0
        )
        self.assertEqual(result["scenario"]["future_contributions"], 0)

    def test_short_month_clipping_does_not_drift(self):
        data, current = wallet()
        result = build_wallet_scenario(
            data,
            current,
            today=TODAY,
            years=1,
            monthly_extra=10,
            start_date="2027-01-31",
        )
        points = {p["date"]: p["contributions"] for p in result["scenario"]["points"]}
        self.assertEqual(points["2027-01-31"], 10)
        self.assertEqual(points["2027-02-28"], 20)
        self.assertEqual(points["2027-03-31"], 30)
        self.assertEqual(result["scenario"]["future_contributions"], 80)

    def test_compounding_uses_actual_day_count_and_changed_rate(self):
        data, current = wallet()
        result = build_wallet_scenario(
            data, current, today=TODAY, years=1, annual_return=10
        )
        expected = round(1120 * 1.1 ** (365 / 365.2425), 2)
        self.assertEqual(result["scenario"]["final_value"], expected)
        self.assertEqual(result["difference"]["growth"], round(expected - 1120, 2))

    def test_missing_market_data_and_failed_refresh_block_scenarios(self):
        data, current = wallet()
        current.valors["BBB"].quote = None
        self.assertEqual(
            build_wallet_scenario(data, current, today=TODAY)["reason"],
            "missing_market_data",
        )
        self.assertIsNone(
            build_wallet_scenario(data, current, today=TODAY, available=False)[
                "scenario"
            ]
        )

    def test_invalid_dates_rates_amounts_and_plan_selection_are_rejected(self):
        data, current = wallet()
        cases = [
            {"years": True},
            {"years": 1.5},
            {"years": 51},
            {"annual_return": float("nan")},
            {"annual_return": -100},
            {"monthly_extra": -1},
            {"one_off": True},
            {"start_date": "2026-09-13"},
            {"pause_until": "2026-08-01"},
            {"plan_id": "wrong"},
            {"monthly_amount": 100},
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                build_wallet_scenario(data, current, today=TODAY, **arguments)


class AllocationTests(unittest.TestCase):
    def test_current_cash_deficit_cannot_fund_an_allocation(self):
        data, current = wallet(cash=-100)
        result = allocate_deposit(data, current, today=TODAY, amount=1000)
        self.assertEqual(result["reason"], "cash_deficit")
        self.assertEqual(result["allocations"], [])

    def test_deposit_is_cent_exact_and_does_not_spend_existing_cash_by_default(self):
        data, current = wallet()
        result = allocate_deposit(data, current, today=TODAY, amount=100)
        allocations = {p["symbol"]: p["amount"] for p in result["allocations"]}
        self.assertEqual(result["budget"], 100)
        self.assertEqual(result["invested"], 100)
        self.assertEqual(result["cash_used"], 0)
        self.assertEqual(result["remaining_cash"], 100)
        self.assertGreater(allocations["BBB"], allocations["AAA"])
        self.assertLess(result["after_target_error"], result["before_target_error"])

    def test_existing_cash_requires_explicit_selection(self):
        data, current = wallet()
        result = allocate_deposit(data, current, today=TODAY, amount=0, use_cash=True)
        self.assertEqual(result["budget"], 100)
        self.assertEqual(result["cash_used"], 100)
        self.assertEqual(result["remaining_cash"], 0)

    def test_partial_and_zero_targets_are_never_rescaled(self):
        data, current = wallet(targets=(0, 40))
        result = allocate_deposit(data, current, today=TODAY, amount=1000)
        allocations = {p["symbol"]: p["amount"] for p in result["allocations"]}
        self.assertEqual(allocations["AAA"], 0)
        self.assertEqual(allocations["BBB"], 548)
        self.assertEqual(result["unallocated"], 452)
        self.assertEqual(result["remaining_cash"], 552)

    def test_unspecified_target_is_not_a_zero_target_purchase(self):
        data, current = wallet(targets=(None, 40))
        result = allocate_deposit(data, current, today=TODAY, amount=1000)
        self.assertEqual(result["allocations"][0]["amount"], 0)
        self.assertIsNone(result["allocations"][0]["target_share"])

    def test_all_zero_targets_preserve_entire_deposit(self):
        data, current = wallet(targets=(0, 0))
        result = allocate_deposit(data, current, today=TODAY, amount=123.45)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["invested"], 0)
        self.assertEqual(result["unallocated"], 123.45)

    def test_missing_targets_or_quotes_are_unavailable(self):
        data, current = wallet(targets=(None, None))
        self.assertEqual(
            allocate_deposit(data, current, today=TODAY, amount=100)["reason"],
            "targets_missing",
        )
        current.valors["AAA"].fx_rate = None
        self.assertEqual(
            allocate_deposit(data, current, today=TODAY, amount=100)["reason"],
            "missing_market_data",
        )

    def test_largest_remainder_tie_break_is_deterministic_by_symbol(self):
        data, current = wallet(prices=(10, 10), targets=(50, 50), cash=0)
        data[c.CONF_CONTRIBUTIONS][0][c.CONTRIBUTION_LOTS][0][c.LOT_UNITS] = 30
        result = allocate_deposit(data, current, today=TODAY, amount=0.03)
        # Each target shortfall is 0.015: no purchase may cross that target.
        self.assertEqual([p["amount"] for p in result["allocations"]], [0.01, 0.01])
        self.assertEqual(result["unallocated"], 0.01)

    def test_many_budgets_conserve_cash_and_do_not_cross_targets(self):
        for pennies in (0, 1, 2, 3, 7, 99, 10001, 99999):
            with self.subTest(pennies=pennies):
                data, current = wallet()
                before = copy.deepcopy(data)
                result = allocate_deposit(
                    data, current, today=TODAY, amount=pennies / 100, use_cash=True
                )
                spent = sum(
                    Decimal(str(row["amount"])) for row in result["allocations"]
                )
                self.assertEqual(
                    spent + Decimal(str(result["unallocated"])),
                    Decimal(str(result["budget"])),
                )
                self.assertGreaterEqual(result["remaining_cash"], 0)
                self.assertLessEqual(
                    result["after_target_error"], result["before_target_error"] + 1e-7
                )
                for row in result["allocations"]:
                    if row["amount"]:
                        self.assertLessEqual(
                            row["after_share"], row["target_share"] + 1e-7
                        )
                self.assertEqual(data, before)

    def test_invalid_money_is_rejected_including_fractional_cents(self):
        data, current = wallet()
        for amount in (True, -1, float("nan"), float("inf"), 0.001, "not-money"):
            with (
                self.subTest(amount=amount),
                self.assertRaisesRegex(ValueError, "invalid_allocation_amount"),
            ):
                allocate_deposit(data, current, today=TODAY, amount=amount)


if __name__ == "__main__":
    unittest.main()
