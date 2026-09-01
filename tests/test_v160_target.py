"""Regressions for the 1.6 compound target and forecast."""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from tests.bootstrap import install_stubs

install_stubs()

from custom_components.my_wallet import const as c  # noqa: E402
from custom_components.my_wallet.contributions import (  # noqa: E402
    make_contribution,
)
from custom_components.my_wallet.history import build_history  # noqa: E402
from custom_components.my_wallet.plans import (  # noqa: E402
    change_plan_definition,
    make_plan,
)
from custom_components.my_wallet.target import (  # noqa: E402
    add_years,
    documented_wallet_start_date,
    target_allocation_forecast,
    target_cash_flows,
    target_contributed_capital,
    target_contribution_series,
    target_deviation,
    target_projection,
    target_series,
)

ROOT = Path(__file__).resolve().parents[1]


def plan(
    plan_id: str,
    first: str,
    amount: float,
    *,
    enabled: bool = True,
    skipped: list[str] | None = None,
) -> dict:
    return make_plan(
        plan_id=plan_id,
        name=plan_id,
        first_date=first,
        allocation_mode=c.ALLOCATION_MODE_FIXED,
        allocations=[{c.ALLOCATION_SYMBOL: "AAA", c.ALLOCATION_VALUE: amount}],
        enabled=enabled,
        skipped_periods=skipped,
    )


def wallet(
    *,
    contributions: list[dict],
    plans: list[dict] | None = None,
    retired: list[dict] | None = None,
    opening: float = 0,
    annual_return: float = 7,
) -> dict:
    return {
        c.CONF_WALLET_NAME: "Wallet",
        c.CONF_BASE_CURRENCY: "EUR",
        c.CONF_SCAN_INTERVAL: 30,
        c.CONF_EXPECTED_ANNUAL_RETURN: annual_return,
        c.CONF_VALORS: [{c.VALOR_SYMBOL: "AAA", c.VALOR_AMOUNT: opening}],
        c.CONF_CONTRIBUTIONS: contributions,
        c.CONF_DIVIDENDS: [],
        c.CONF_SAVINGS_PLANS: plans or [],
        c.CONF_RETIRED_SAVINGS_PLANS: retired or [],
    }


class TargetCalculationTests(unittest.TestCase):
    def test_annual_return_is_converted_geometrically(self) -> None:
        data = wallet(
            contributions=[make_contribution(1_000, "2025-09-01")],
            annual_return=7,
        )

        result = target_projection(data, through=date(2026, 9, 1))

        self.assertAlmostEqual(result.monthly_return, (1.07 ** (1 / 12) - 1) * 100)
        self.assertAlmostEqual(
            result.value or 0,
            1_000 * 1.07 ** (365 / 365.2425),
        )

    def test_interest_is_applied_before_each_days_cash_flow(self) -> None:
        data = wallet(
            contributions=[
                make_contribution(100, "2026-01-01"),
                make_contribution(50, "2026-02-01"),
            ]
        )

        result = target_projection(data, through=date(2026, 2, 1))

        self.assertAlmostEqual(
            result.value or 0,
            100 * 1.07 ** (31 / 365.2425) + 50,
        )

    def test_planned_rates_replace_booked_rows_and_include_due_months(self) -> None:
        monthly = plan("monthly", "2026-01-15", 100)
        booked = make_contribution(
            105,
            "2026-01-15",
            plan_id="monthly",
            scheduled_date="2026-01-15",
            source=c.CONTRIBUTION_SOURCE_PLAN,
        )
        data = wallet(contributions=[booked], plans=[monthly])

        flows = target_cash_flows(data, through=date(2026, 3, 15))

        self.assertEqual(
            [(flow.date.isoformat(), flow.amount) for flow in flows],
            [
                ("2026-01-15", 100),
                ("2026-02-15", 100),
                ("2026-03-15", 100),
            ],
        )

    def test_multiple_plans_and_skipped_periods_are_combined(self) -> None:
        first = plan("first", "2026-01-10", 100, skipped=["2026-02"])
        second = plan("second", "2026-02-20", 50)
        data = wallet(
            contributions=[make_contribution(1, "2026-01-01")],
            plans=[first, second],
        )

        flows = target_cash_flows(data, through=date(2026, 3, 20))

        self.assertEqual(
            [(flow.date.isoformat(), flow.amount) for flow in flows],
            [
                ("2026-01-01", 1),
                ("2026-01-10", 100),
                ("2026-02-20", 50),
                ("2026-03-10", 100),
                ("2026-03-20", 50),
            ],
        )

    def test_historical_rate_change_and_pause_are_respected(self) -> None:
        old = plan("monthly", "2026-01-15", 100)
        increased = plan("monthly", "2026-01-15", 200)
        changed = change_plan_definition(
            old, increased, today=date(2026, 1, 31), recalculate=False
        )
        changed_flows = target_cash_flows(
            wallet(
                contributions=[make_contribution(1, "2026-01-01")],
                plans=[changed],
            ),
            through=date(2026, 3, 15),
        )
        paused = change_plan_definition(
            old,
            plan("monthly", "2026-01-15", 100, enabled=False),
            today=date(2026, 1, 31),
            recalculate=False,
        )
        paused_flows = target_cash_flows(
            wallet(contributions=[make_contribution(1, "2026-01-01")], plans=[paused]),
            through=date(2026, 3, 15),
        )

        self.assertEqual(
            [flow.amount for flow in changed_flows if flow.plan_id], [100, 200, 200]
        )
        self.assertEqual(
            [flow.date.isoformat() for flow in paused_flows if flow.plan_id],
            ["2026-01-15"],
        )

    def test_retired_plan_only_uses_its_documented_execution(self) -> None:
        retired = plan("retired", "2026-01-15", 100)
        booked = make_contribution(
            98,
            "2026-02-15",
            plan_id="retired",
            scheduled_date="2026-02-15",
            source=c.CONTRIBUTION_SOURCE_PLAN,
        )

        flows = target_cash_flows(
            wallet(contributions=[booked], retired=[retired]),
            through=date(2026, 4, 30),
        )

        self.assertEqual(
            [(flow.date.isoformat(), flow.amount) for flow in flows],
            [("2026-02-15", 100)],
        )

    def test_unknown_opening_balance_disables_target_instead_of_guessing(self) -> None:
        data = wallet(
            opening=1,
            contributions=[make_contribution(100, "2026-01-15")],
        )

        result = target_projection(data, through=date(2026, 9, 1))

        self.assertIsNone(documented_wallet_start_date(data, through=date(2026, 9, 1)))
        self.assertIsNone(result.value)
        self.assertEqual(result.unavailable_reason, "unknown_start")

    def test_forecast_continues_open_ended_plan_and_exposes_daily_series(self) -> None:
        data = wallet(
            contributions=[make_contribution(100, "2026-01-01")],
            plans=[plan("monthly", "2026-02-01", 100)],
        )
        through = add_years(date(2026, 9, 1), 3)

        projection = target_projection(data, through=through)
        series = target_series(projection, start=date(2025, 12, 31), through=through)

        self.assertEqual(series["2025-12-31"], 0)
        self.assertIn(through.isoformat(), series)
        self.assertGreater(projection.value or 0, 4_400)
        self.assertEqual(target_contributed_capital(projection, through=through), 4_500)
        contributions = target_contribution_series(
            projection, start=date(2026, 9, 1), through=through
        )
        self.assertEqual(contributions[through.isoformat()], 4_500)

    def test_deviation_uses_actual_minus_target(self) -> None:
        absolute, percentage = target_deviation(110, 100)
        self.assertEqual(absolute, 10)
        self.assertEqual(percentage, 10)

    def test_allocation_forecast_applies_future_plan_allocations(self) -> None:
        monthly = make_plan(
            plan_id="split",
            name="split",
            first_date="2026-10-01",
            allocation_mode=c.ALLOCATION_MODE_FIXED,
            allocations=[
                {c.ALLOCATION_SYMBOL: "AAA", c.ALLOCATION_VALUE: 60},
                {c.ALLOCATION_SYMBOL: "BBB", c.ALLOCATION_VALUE: 40},
            ],
        )
        data = wallet(
            contributions=[make_contribution(100, "2026-01-01")],
            plans=[monthly],
            annual_return=0,
        )
        data[c.CONF_VALORS].append({c.VALOR_SYMBOL: "BBB", c.VALOR_AMOUNT: 0})
        through = date(2027, 9, 1)
        projection = target_projection(data, through=through)

        forecast = target_allocation_forecast(
            projection,
            current_date=date(2026, 9, 1),
            through=through,
            positions={"AAA": 80, "BBB": 20},
            cash=0,
        )

        self.assertEqual(
            forecast,
            {
                "date": "2027-09-01",
                "positions": {"AAA": 800, "BBB": 500},
                "cash": 0,
                "total": 1_300,
            },
        )

    def test_allocation_forecast_applies_percentage_allocations(self) -> None:
        monthly = make_plan(
            plan_id="percentage-split",
            name="percentage split",
            first_date="2026-10-01",
            allocation_mode=c.ALLOCATION_MODE_PERCENTAGE,
            amount=100,
            allocations=[
                {c.ALLOCATION_SYMBOL: "AAA", c.ALLOCATION_VALUE: 75},
                {c.ALLOCATION_SYMBOL: "BBB", c.ALLOCATION_VALUE: 25},
            ],
        )
        data = wallet(
            contributions=[make_contribution(100, "2026-01-01")],
            plans=[monthly],
            annual_return=0,
        )
        data[c.CONF_VALORS].append({c.VALOR_SYMBOL: "BBB", c.VALOR_AMOUNT: 0})
        through = date(2027, 9, 1)

        forecast = target_allocation_forecast(
            target_projection(data, through=through),
            current_date=date(2026, 9, 1),
            through=through,
            positions={"AAA": 80, "BBB": 20},
            cash=0,
        )

        self.assertEqual(
            forecast,
            {
                "date": "2027-09-01",
                "positions": {"AAA": 980, "BBB": 320},
                "cash": 0,
                "total": 1_300,
            },
        )


class TargetHistoryTests(unittest.TestCase):
    def test_history_contains_current_target_and_future_projection(self) -> None:
        data = wallet(
            contributions=[make_contribution(100, "2026-08-01")],
            plans=[plan("monthly", "2026-09-01", 100)],
        )

        history = build_history(data, {}, today=date(2026, 9, 1))

        self.assertEqual(history["points"][0]["target"], 0)
        self.assertEqual(
            history["points"][-1]["target"], history["target"]["current_value"]
        )
        self.assertEqual(history["target"]["forecasts"]["20"]["date"], "2046-09-01")
        self.assertEqual(history["target_forecast"][-1]["date"], "2046-09-01")
        self.assertEqual(history["target_forecast"][-1]["invested"], 24_200)
        self.assertEqual(history["target"]["contributions"], 200)
        self.assertEqual(
            history["target"]["growth"],
            round(history["target"]["current_value"] - 200, 2),
        )
        forecast = history["target"]["forecasts"]["20"]
        self.assertEqual(forecast["contributions"], 24_200)
        self.assertEqual(forecast["additional_contributions"], 24_000)
        self.assertEqual(forecast["growth"], round(forecast["value"] - 24_200, 2))


class TargetDashboardTests(unittest.TestCase):
    def test_dashboard_exposes_target_toggle_comparison_and_forecasts(self) -> None:
        source = (
            ROOT / "custom_components/my_wallet/frontend/my-wallet-panel.js"
        ).read_text(encoding="utf-8")
        for fragment in (
            'targetComparison: "Soll-Ist-Vergleich"',
            'targetLine: "Sollkurve anzeigen"',
            'targetContributions: "Einzahlungen bis dahin"',
            'futureContributions: "Davon ab heute geplant"',
            'targetGrowth: "Erwarteter Wertzuwachs"',
            'forecastAllocation: "Prognostizierte Depotaufteilung"',
            'forecastAllocationHint: "Mathematische Hochrechnung',
            'portfolioForecast: "Depotprognose"',
            "for (const years of [0, 1, 3, 5, 10, 20])",
            '"stats target-stats"',
            'stats.classList.add("overview-stats")',
            "wallet.target?.allocation_forecasts",
            '...(showProjection ? ["projected"] : [])',
            '"stroke-dasharray": "7 5"',
            "this._history.target_forecast",
            "this._renderTargetSummary(main, wallet)",
        ):
            self.assertIn(fragment, source)


if __name__ == "__main__":
    unittest.main()
