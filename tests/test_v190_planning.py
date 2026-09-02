"""Cash conservation, date boundaries and zero targets for future planning."""

from __future__ import annotations

import copy
import unittest
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tests.bootstrap import install_stubs

install_stubs()

from custom_components.my_wallet import const as c
from custom_components.my_wallet.backup import create_backup, prepare_backup
from custom_components.my_wallet.contributions import (
    all_lots,
    invested_total,
    make_contribution,
    make_lot,
)
from custom_components.my_wallet.dividends import cash_balance
from custom_components.my_wallet.executions import async_prepare_executions
from custom_components.my_wallet.history import build_history
from custom_components.my_wallet.inflation import InflationSeries
from custom_components.my_wallet.models import ValorData
from custom_components.my_wallet.planning import (
    change_planned_deposit,
    next_cash_investment,
    planned_contributions,
)
from custom_components.my_wallet.plans import make_plan
from custom_components.my_wallet.target import (
    target_allocation_forecast,
    target_projection,
)
from custom_components.my_wallet.yahoo import HistoricalQuote, Quote
from tests.test_market_regressions import WalletCoordinator
from tests.test_options_regressions import _flow, config_flow
from tests.test_panel_regressions import Connection, hass_with, panel

TODAY = date(2026, 8, 31)
PAYMENT = date(2027, 3, 15)


def wallet(*, planned=True, plans=(), payment=PAYMENT, annual_return=0):
    initial = make_contribution(
        100,
        "2026-08-01",
        contribution_id="initial",
        lots=[
            make_lot(
                symbol="AAA",
                execution_date="2026-08-01",
                amount=100,
                unit_price=10,
                quote_currency="EUR",
            )
        ],
    )
    return {
        c.CONF_WALLET_NAME: "Test wallet",
        c.CONF_BASE_CURRENCY: "EUR",
        c.CONF_SCAN_INTERVAL: 30,
        c.CONF_EXPECTED_ANNUAL_RETURN: annual_return,
        c.CONF_VALORS: [
            {c.VALOR_SYMBOL: "AAA", c.VALOR_AMOUNT: 0, c.VALOR_TARGET_SHARE: 0},
            {c.VALOR_SYMBOL: "BBB", c.VALOR_AMOUNT: 0, c.VALOR_TARGET_SHARE: 100},
        ],
        c.CONF_CONTRIBUTIONS: [
            initial,
            *(
                [make_contribution(10_000, payment, contribution_id="future")]
                if planned
                else []
            ),
        ],
        c.CONF_SAVINGS_PLANS: list(plans),
        c.CONF_RETIRED_SAVINGS_PLANS: [],
        c.CONF_DIVIDENDS: [],
    }


def savings_plan(
    *,
    plan_id="a",
    first=PAYMENT,
    cash=True,
    enabled=True,
    skips=(),
    end=None,
    weights=(75, 25),
):
    return make_plan(
        name=f"Plan {plan_id}",
        plan_id=plan_id,
        first_date=first,
        allocation_mode=c.ALLOCATION_MODE_PERCENTAGE,
        amount=100,
        allocations=[
            {c.ALLOCATION_SYMBOL: symbol, c.ALLOCATION_VALUE: weight}
            for symbol, weight in zip(("AAA", "BBB"), weights, strict=True)
            if weight
        ],
        use_cash_balance=cash,
        enabled=enabled,
        skipped_periods=skips,
        end_date=end,
    )


def forecast(data, through=PAYMENT, today=TODAY, cash=0):
    return target_allocation_forecast(
        target_projection(data, through=through),
        current_date=today,
        through=through,
        positions={"AAA": 100, "BBB": 0},
        cash=cash,
    )


class PlanningCalculations(unittest.TestCase):
    def test_future_deposit_is_not_current_cash_or_capital_and_becomes_due_once(self):
        data = wallet()
        self.assertEqual(invested_total(data, through=TODAY), 100)
        self.assertEqual(cash_balance(data, through=TODAY), 0)
        self.assertEqual(len(planned_contributions(data, today=TODAY)), 1)
        self.assertEqual(invested_total(data, through=PAYMENT), 10_100)
        self.assertEqual(cash_balance(data, through=PAYMENT), 10_000)
        self.assertEqual(planned_contributions(data, today=PAYMENT), [])
        self.assertEqual(len(data[c.CONF_CONTRIBUTIONS]), 2)

    def test_save_retry_edit_and_cancel_do_not_touch_past_rows(self):
        data = wallet(planned=False)
        original = copy.deepcopy(data)
        args = dict(
            today=TODAY,
            deposit_id="future",
            action="save",
            amount=10_000,
            deposit_date=PAYMENT.isoformat(),
            note="Planned transfer",
        )
        saved = change_planned_deposit(data, **args)
        retry = change_planned_deposit(saved, **args)
        self.assertEqual(data, original)
        self.assertEqual(saved, retry)
        moved = change_planned_deposit(
            saved, **{**args, "amount": 12_000, "deposit_date": "2027-04-01"}
        )
        self.assertEqual(
            moved[c.CONF_CONTRIBUTIONS][0], original[c.CONF_CONTRIBUTIONS][0]
        )
        self.assertEqual(planned_contributions(moved, today=TODAY)[0]["amount"], 12_000)
        cancelled = change_planned_deposit(
            moved, today=TODAY, deposit_id="future", action="delete"
        )
        self.assertEqual(cancelled, original)
        self.assertEqual(
            change_planned_deposit(
                cancelled, today=TODAY, deposit_id="future", action="delete"
            ),
            cancelled,
        )

    def test_planning_rejects_invalid_input_and_cannot_modify_due_or_booked_deposits(
        self,
    ):
        data = wallet()
        args = dict(
            today=TODAY,
            deposit_id="new",
            action="save",
            amount=100,
            deposit_date=PAYMENT.isoformat(),
        )
        for fields in (
            {"amount": -1},
            {"amount": True},
            {"amount": float("nan")},
            {"amount": float("inf")},
            {"deposit_date": "bad"},
            {"deposit_date": TODAY.isoformat()},
            {"note": "a" * 501},
            {"deposit_id": "../bad"},
        ):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                change_planned_deposit(data, **{**args, **fields})
        for deposit_id, today in (("initial", TODAY), ("future", PAYMENT)):
            for action in ("save", "delete"):
                with (
                    self.subTest(deposit_id=deposit_id, action=action),
                    self.assertRaisesRegex(ValueError, "planned_deposit_locked"),
                ):
                    change_planned_deposit(
                        data,
                        **{
                            **args,
                            "deposit_id": deposit_id,
                            "today": today,
                            "action": action,
                        },
                    )

    def test_same_month_plans_are_excluded_from_ledger_and_nominal_and_real_summaries(
        self,
    ):
        today = date(2026, 8, 10)
        data = wallet(payment=date(2026, 8, 20))
        histories = {
            "AAA": [
                HistoricalQuote("AAA", date(2026, 8, 1), 10, "EUR"),
                HistoricalQuote("AAA", today, 10, "EUR"),
            ]
        }
        history = build_history(
            data,
            histories,
            today=today,
            inflation=InflationSeries(
                c.INFLATION_SOURCE_EUROSTAT_DE, "DE", {"2026-07": 100, "2026-08": 100}
            ),
        )
        self.assertEqual(
            [row["type"] for row in history["ledger"]], ["deposit", "purchase"]
        )
        for key in ("summaries", "summaries_real"):
            self.assertEqual(history[key]["wallet"]["monthly"][-1]["deposits"], 100)
            self.assertEqual(history[key]["wallet"]["monthly"][-1]["gain"], 0)
        self.assertEqual(history["points"][-1]["invested"], 100)
        self.assertEqual(history["target"]["forecasts"]["1"]["contributions"], 10_100)

    def test_cash_waits_for_plan_date_then_is_invested_without_extra_capital(self):
        plan = savings_plan(first=date(2027, 3, 20))
        data = wallet(plans=[plan])
        before = forecast(data)
        self.assertEqual(before["cash"], 10_000)
        self.assertEqual(before["positions"], {"AAA": 100, "BBB": 0})
        after = forecast(data, date(2027, 3, 20))
        self.assertEqual(after["cash"], 0)
        self.assertEqual(after["positions"], {"AAA": 7_675, "BBB": 2_525})
        self.assertEqual(after["total"], 10_200)

    def test_same_day_deposit_precedes_plans_and_multiple_plans_do_not_share_cash_twice(
        self,
    ):
        data = wallet(
            plans=[savings_plan(plan_id="z", weights=(0, 100)), savings_plan()]
        )
        result = forecast(data)
        self.assertEqual(result["positions"], {"AAA": 7_675, "BBB": 2_625})
        self.assertEqual(result["total"], 10_300)
        self.assertEqual(result["cash"], 0)
        self.assertEqual(
            next_cash_investment(data, on_or_after=PAYMENT)["plan_id"], "a"
        )

    def test_disabled_cash_reinvestment_and_skipped_or_ended_plans_are_respected(self):
        plans = [
            savings_plan(plan_id="off", cash=False),
            savings_plan(plan_id="paused", enabled=False),
            savings_plan(plan_id="ended", first=date(2027, 2, 15), end="2027-02-15"),
            savings_plan(plan_id="skipped", skips=["2027-03"]),
        ]
        data = wallet(plans=plans)
        result = forecast(data)
        self.assertEqual(result["cash"], 10_000)
        self.assertEqual(
            next_cash_investment(data, on_or_after=PAYMENT),
            {"date": "2027-04-15", "plan_id": "skipped", "plan_name": "Plan skipped"},
        )
        after = forecast(data, date(2027, 4, 15))
        self.assertEqual(after["cash"], 0)
        only_cash = wallet(plans=[savings_plan(cash=False)])
        self.assertIsNone(next_cash_investment(only_cash, on_or_after=PAYMENT))
        self.assertEqual(forecast(only_cash)["cash"], 10_000)

    def test_forecast_total_conserves_funding_with_growth_and_cent_remainders(self):
        data = wallet(plans=[savings_plan(weights=(33.33, 66.67))], annual_return=7)
        projection = target_projection(data, through=date(2027, 6, 20))
        today = date(2026, 8, 1)
        result = forecast(data, date(2027, 6, 20), today=today)
        self.assertAlmostEqual(result["total"], projection.value, delta=0.01)
        self.assertAlmostEqual(
            sum(result["positions"].values()) + result["cash"],
            result["total"],
            delta=0.011,
        )
        self.assertGreaterEqual(result["cash"], 0)
        self.assertLess(result["cash"], 0.05)

    def test_backup_round_trip_retains_planning_and_zero_target(self):
        data = wallet(plans=[savings_plan()])
        document = create_backup(
            data, title="Test wallet", created_at=datetime(2026, 8, 31, tzinfo=UTC)
        )
        restored, summary = prepare_backup(document, today=TODAY)
        self.assertEqual(restored[c.CONF_CONTRIBUTIONS], data[c.CONF_CONTRIBUTIONS])
        self.assertEqual(restored[c.CONF_VALORS][0][c.VALOR_TARGET_SHARE], 0)
        self.assertEqual(summary["deposits"], 1)
        self.assertEqual(summary["planned_deposits"], 1)
        self.assertEqual(summary["capital"], 100)


class PlanningExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_due_execution_matches_forecast_and_retries_do_not_book_twice(self):
        data = wallet(plans=[savings_plan(weights=(33.33, 66.67))])
        original = copy.deepcopy(data)
        prices = {
            symbol: [HistoricalQuote(symbol, PAYMENT, 10, "EUR")]
            for symbol in ("AAA", "BBB")
        }
        with patch(
            "custom_components.my_wallet.executions.fetch_histories",
            new=AsyncMock(return_value=prices),
        ) as history:
            not_due, report = await async_prepare_executions(
                data, session=object(), today=TODAY
            )
            self.assertEqual(not_due, data)
            history.assert_not_awaited()
            booked, report = await async_prepare_executions(
                data, session=object(), today=PAYMENT
            )
            self.assertEqual(report["created"], 1)
            retried, report = await async_prepare_executions(
                booked, session=object(), today=PAYMENT
            )
            self.assertEqual(report["created"], 0)
        self.assertEqual(data, original)
        self.assertEqual(booked, retried)
        self.assertEqual(invested_total(booked, through=PAYMENT), 10_200)
        result = forecast(data)
        positions = {
            symbol: round(
                sum(
                    lot[c.LOT_UNITS] * 10
                    for lot in all_lots(booked, through=PAYMENT)
                    if lot[c.LOT_SYMBOL] == symbol
                ),
                2,
            )
            for symbol in ("AAA", "BBB")
        }
        self.assertEqual(positions, result["positions"])
        self.assertAlmostEqual(
            cash_balance(booked, through=PAYMENT), result["cash"], places=2
        )

    async def test_zero_target_survives_options_and_computed_state(self):
        data = wallet(planned=False)
        flow, entry, _ = _flow(data)
        flow._edit_symbol = "AAA"
        result = await flow.async_step_edit_valor_fields(
            {c.VALOR_AMOUNT: 0, c.VALOR_TARGET_SHARE: 0}
        )
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(entry.data[c.CONF_VALORS][0][c.VALOR_TARGET_SHARE], 0)
        self.assertTrue(ValorData("AAA", 1, 1, target_share=0).has_target)
        self.assertIsNone(config_flow._normalize_target_share(None))
        self.assertIsNone(config_flow._normalize_target_share(""))
        entry.entry_id = "wallet"
        coordinator = WalletCoordinator(SimpleNamespace(session=object()), entry)
        coordinator._inflation.async_get = AsyncMock(return_value=None)
        coordinator._async_book_due_plans = AsyncMock(return_value=[])
        with patch.dict(
            WalletCoordinator._async_update_data.__globals__,
            {
                "fetch_quotes": AsyncMock(
                    return_value={
                        "AAA": Quote("AAA", 10, "EUR"),
                        "BBB": Quote("BBB", 10, "EUR"),
                    }
                )
            },
        ):
            computed = await coordinator._async_update_data()
        self.assertEqual(computed.valors["AAA"].target_share, 0)
        self.assertTrue(computed.valors["AAA"].has_target)

    async def test_options_plan_future_cash_and_reject_immediate_future_purchase(self):
        flow, entry, manager = _flow(wallet(planned=False))
        rejected = await flow.async_step_add_contribution(
            {"date": "2027-03-15", "amount": 10_000, "invest_now": True}
        )
        self.assertEqual(rejected["errors"]["invest_now"], "planned_investment")
        self.assertEqual(manager.updates, 0)
        result = await flow.async_step_plan_contribution(
            {"date": "2027-03-15", "amount": 10_000}
        )
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(manager.updates, 1)
        self.assertEqual(cash_balance(entry.data, through=TODAY), 0)

    async def test_correction_cannot_move_used_cash_into_the_future_or_remove_it(self):
        data = wallet(planned=False)
        deposit = make_contribution(100, "2026-08-02", contribution_id="cash")
        purchase = make_contribution(
            0,
            "2026-08-03",
            source=c.CONTRIBUTION_SOURCE_PURCHASE,
            lots=[
                make_lot(
                    symbol="AAA",
                    execution_date="2026-08-03",
                    amount=100,
                    unit_price=10,
                    quote_currency="EUR",
                )
            ],
        )
        data[c.CONF_CONTRIBUTIONS].extend([deposit, purchase])
        flow, entry, manager = _flow(data)
        await flow.async_step_edit_contribution({"id": "cash"})
        result = await flow.async_step_edit_contribution_fields(
            {"amount": 100, "date": "2027-03-15"}
        )
        self.assertEqual(result["errors"]["base"], "cash_conflict")
        await flow.async_step_remove_contribution({"id": "cash"})
        result = await flow.async_step_confirm_remove_contribution({"confirm": True})
        self.assertEqual(result["errors"]["base"], "cash_conflict")
        self.assertEqual(manager.updates, 0)
        self.assertEqual(entry.data, data)


class PlanningEndpointTests(unittest.TestCase):
    def test_admin_save_invalidates_cache_once_and_rejects_past_rows(self):
        entry = SimpleNamespace(entry_id="wallet", data=wallet(planned=False))
        hass = hass_with([entry])

        def update(target, *, data):
            target.data = data
            return True

        hass.config_entries.async_update_entry.side_effect = update
        panel._state(hass)["cache"]["wallet"] = {"old": True}
        connection = Connection()
        message = {
            "id": 1,
            "entry_id": "wallet",
            "deposit_id": "future",
            "action": "save",
            "date": "2027-03-15",
            "amount": 10_000,
        }
        panel.ws_planned_deposit(hass, connection, message)
        panel.ws_planned_deposit(hass, connection, message)
        self.assertEqual(connection.errors, [])
        self.assertEqual(hass.config_entries.async_update_entry.call_count, 1)
        hass.config_entries.async_schedule_reload.assert_called_once_with("wallet")
        self.assertNotIn("wallet", panel._state(hass)["cache"])
        panel.ws_planned_deposit(
            hass, connection, {**message, "deposit_id": "initial", "action": "delete"}
        )
        self.assertEqual(connection.errors[-1][1], "planned_deposit_locked")
        self.assertEqual(hass.config_entries.async_update_entry.call_count, 1)
