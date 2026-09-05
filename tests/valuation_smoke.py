"""Check actual Home Assistant sensor classes against the dashboard contract.

Run separately from tests that replace Home Assistant modules with test doubles.
Market data is synthetic; no network requests or live wallet are needed.
"""

from __future__ import annotations

import unittest
from copy import deepcopy
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from custom_components.my_wallet import const as c
from custom_components.my_wallet import panel, sensor
from custom_components.my_wallet.contributions import make_contribution, make_lot
from custom_components.my_wallet.corrections import position_units
from custom_components.my_wallet.dividends import cash_balance, make_dividend
from custom_components.my_wallet.inflation import InflationSeries
from custom_components.my_wallet.models import ValorData, WalletData
from custom_components.my_wallet.valuation import position_valuation, wallet_valuation
from custom_components.my_wallet.yahoo import Quote

TODAY = date(2026, 2, 28)


def fixture(*, opening=0, inflation=True, fx=False):
    lots = [
        make_lot(
            symbol="AAA",
            execution_date=day,
            amount=amount,
            units=units,
            unit_price=amount / units,
            quote_currency="EUR",
            lot_id=identifier,
        )
        for identifier, day, amount, units in (
            ("first", "2026-01-02", 60, 6),
            ("reinvested", "2026-01-16", 6, 0.5),
        )
    ]
    data = {
        c.CONF_WALLET_NAME: "Fixture",
        c.CONF_BASE_CURRENCY: "EUR",
        c.CONF_VALORS: [{c.VALOR_SYMBOL: "AAA", c.VALOR_AMOUNT: opening}],
        c.CONF_CONTRIBUTIONS: [
            make_contribution(
                100, "2026-01-01", contribution_id="deposit", lots=[lots[0]]
            ),
            make_contribution(
                0,
                "2026-01-16",
                contribution_id="purchase",
                source=c.CONTRIBUTION_SOURCE_PURCHASE,
                lots=[lots[1]],
            ),
            make_contribution(500, "2027-01-01", contribution_id="future"),
        ],
        c.CONF_DIVIDENDS: [
            make_dividend(booking_date="2026-01-15", amount=6, symbol="AAA")
        ],
        c.CONF_SAVINGS_PLANS: [],
        c.CONF_RETIRED_SAVINGS_PLANS: [],
    }
    current = WalletData(
        valors={
            "AAA": ValorData(
                "AAA",
                position_units(data, "AAA", TODAY),
                opening,
                Quote("AAA", 15 if fx else 12, "USD" if fx else "EUR"),
                0.8 if fx else 1,
            )
        },
        cash_balance=cash_balance(data, through=TODAY),
        inflation=InflationSeries("test", "DE", {"2026-01": 100, "2026-02": 110})
        if inflation
        else None,
    )
    coordinator = SimpleNamespace(
        data=current, base_currency="EUR", last_update_success=True
    )
    entry = SimpleNamespace(
        entry_id="stable-entry", title="Fixture", data=data, runtime_data=coordinator
    )
    return entry, coordinator


def payload(entry):
    results = []
    connection = SimpleNamespace(
        user=SimpleNamespace(is_admin=True),
        send_result=lambda message_id, result: results.append(result),
    )
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_entries=lambda domain: [entry])
    )
    panel.ws_wallets(hass, connection, {"id": 1})
    return results[-1]["wallets"][0]


class RealSensorValuationTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch.object(
            panel.dt_util, "now", return_value=datetime(2026, 2, 28, tzinfo=UTC)
        )
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def test_wallet_and_position_metrics_match_actual_sensors_and_known_balances(self):
        for fx in (False, True):
            with self.subTest(fx=fx):
                entry, coordinator = fixture(fx=fx)
                result = payload(entry)
                self.assertEqual(
                    (result["invested"], result["cash"], result["total"]),
                    (100, 40, 118),
                )
                self.assertAlmostEqual(result["profit"], 18)
                self.assertAlmostEqual(result["real_profit"], 8)
                self.assertAlmostEqual(result["positions"][0]["real_profit"], 12)
                for cls, key, suffix in (
                    (sensor.WalletTotalSensor, "total", "total"),
                    (sensor.WalletProfitSensor, "profit", "profit"),
                    (sensor.WalletProfitPctSensor, "performance", "profit_pct"),
                    (
                        sensor.WalletMoneyWeightedReturnSensor,
                        "money_weighted_return",
                        "money_weighted_return",
                    ),
                ):
                    entity = cls(coordinator, entry)
                    self.assertEqual(entity.unique_id, f"stable-entry_{suffix}")
                    self.assertEqual(entity.native_value, round(result[key], 2))
                for cls, key, suffix in (
                    (sensor.ValorProfitSensor, "profit", "profit"),
                    (sensor.ValorPerformanceSensor, "performance", "performance"),
                ):
                    entity = cls(coordinator, entry, "AAA")
                    self.assertEqual(entity.unique_id, f"stable-entry_AAA_{suffix}")
                    self.assertEqual(
                        entity.native_value, round(result["positions"][0][key], 2)
                    )
                    self.assertAlmostEqual(
                        entity.extra_state_attributes[c.ATTR_REAL_PROFIT], 12
                    )
                rows = sensor._lot_rows(entry, coordinator.data.valors["AAA"], TODAY)
                for actual, expected in zip(
                    rows, result["positions"][0]["lots"], strict=True
                ):
                    self.assertEqual(
                        actual[c.ATTR_PROFIT], round(expected["profit"], 2)
                    )
                    self.assertEqual(
                        actual[c.ATTR_ANNUALIZED_PERFORMANCE_PCT],
                        round(expected["annualized_performance"], 2),
                    )

    def test_unknown_opening_cost_does_not_erase_tracked_lot_performance(self):
        entry, coordinator = fixture(opening=5)
        result = payload(entry)
        position = result["positions"][0]
        self.assertFalse(position["cost_complete"])
        self.assertIsNone(position["cost"])
        self.assertIsNone(position["profit"])
        self.assertIsNone(position["real_profit"])
        tracked = position_valuation(
            entry.data,
            "AAA",
            today=TODAY,
            valor=coordinator.data.valors["AAA"],
            inflation=coordinator.data.inflation,
        )
        entity = sensor.ValorProfitSensor(coordinator, entry, "AAA")
        self.assertEqual(entity.native_value, round(tracked.tracked.profit, 2))
        self.assertGreater(entity.native_value, 0)
        self.assertLess(
            entity.native_value, 18
        )  # Dividends also belong to opening units.

    def test_missing_quote_keeps_total_unknown_and_preserves_healthy_position(self):
        entry, coordinator = fixture()
        entry.data[c.CONF_VALORS].append({c.VALOR_SYMBOL: "BBB", c.VALOR_AMOUNT: 2})
        coordinator.data.valors["BBB"] = ValorData("BBB", 2, 2)
        result = payload(entry)
        self.assertIsNone(result["total"])
        self.assertIsNone(result["profit"])
        self.assertEqual(result["positions"][0]["profit"], 18)
        self.assertIsNone(sensor.WalletProfitSensor(coordinator, entry).native_value)
        self.assertEqual(
            sensor.ValorProfitSensor(coordinator, entry, "AAA").native_value, 18
        )

    def test_unavailable_tracked_sensors_still_expose_safe_attributes(self):
        entry, coordinator = fixture()
        coordinator.data.valors["AAA"].quote = None
        for cls in (
            sensor.ValorProfitSensor,
            sensor.ValorPerformanceSensor,
            sensor.ValorAnnualizedPerformanceSensor,
        ):
            entity = cls(coordinator, entry, "AAA")
            self.assertFalse(entity.available)
            self.assertIsNone(entity.native_value)
            attributes = entity.extra_state_attributes
            self.assertEqual(attributes[c.ATTR_TRACKED_INVESTED], 66)
            self.assertIsNone(attributes[c.ATTR_TRACKED_VALUE])
            self.assertIsNone(attributes[c.ATTR_PROFIT])

    def test_missing_inflation_does_not_invent_real_values(self):
        for inflation in (None, InflationSeries("test", "DE", {"2026-02": 110})):
            entry, coordinator = fixture(inflation=False)
            coordinator.data.inflation = inflation
            result = payload(entry)
            self.assertEqual(result["profit"], 18)
            self.assertIsNone(result["real_profit"])
            self.assertIsNone(result["positions"][0]["real_profit"])
            self.assertIsNone(
                sensor.WalletProfitSensor(coordinator, entry).extra_state_attributes[
                    c.ATTR_REAL_PROFIT
                ]
            )
            self.assertIsNone(
                sensor.ValorProfitSensor(
                    coordinator, entry, "AAA"
                ).extra_state_attributes[c.ATTR_REAL_PROFIT]
            )

    def test_valuation_leaves_ledger_and_quote_cache_unchanged(self):
        entry, coordinator = fixture()
        before_data, before_current = deepcopy(entry.data), deepcopy(coordinator.data)
        self.assertEqual(
            wallet_valuation(entry.data, coordinator.data, today=TODAY).nominal.profit,
            18,
        )
        payload(entry)
        self.assertEqual(
            sensor.ValorProfitSensor(coordinator, entry, "AAA").extra_state_attributes[
                c.ATTR_PROFIT
            ],
            18,
        )
        self.assertEqual(entry.data, before_data)
        self.assertEqual(coordinator.data, before_current)


if __name__ == "__main__":
    unittest.main()
