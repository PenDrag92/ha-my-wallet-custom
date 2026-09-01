"""Regressions for the 1.8 purchasing-power view."""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

from tests.bootstrap import install_stubs

install_stubs()

from custom_components.my_wallet import const as c  # noqa: E402
from custom_components.my_wallet.contributions import make_contribution  # noqa: E402
from custom_components.my_wallet.display import (  # noqa: E402
    position_label,
    position_options,
)
from custom_components.my_wallet.history import build_history  # noqa: E402
from custom_components.my_wallet.inflation import (  # noqa: E402
    InflationSeries,
    future_inflation_factor,
    parse_eurostat_hicp,
    purchasing_power,
)
from custom_components.my_wallet.inflation_client import (  # noqa: E402
    InflationDataClient,
)
from tests.test_options_regressions import _flow  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def wallet() -> dict:
    return {
        c.CONF_WALLET_NAME: "Wallet",
        c.CONF_BASE_CURRENCY: "EUR",
        c.CONF_SCAN_INTERVAL: 30,
        c.CONF_EXPECTED_ANNUAL_RETURN: 0,
        c.CONF_EXPECTED_ANNUAL_INFLATION: 10,
        c.CONF_INFLATION_SOURCE: c.INFLATION_SOURCE_EUROSTAT_DE,
        c.CONF_VALORS: [
            {
                c.VALOR_SYMBOL: "AAA",
                c.VALOR_ALIAS: "World fund",
                c.VALOR_AMOUNT: 0,
            }
        ],
        c.CONF_CONTRIBUTIONS: [make_contribution(100, "2026-01-01")],
        c.CONF_DIVIDENDS: [],
        c.CONF_SAVINGS_PLANS: [],
        c.CONF_RETIRED_SAVINGS_PLANS: [],
    }


class InflationCalculationTests(unittest.TestCase):
    def test_eurostat_json_stat_is_parsed_by_time_index(self) -> None:
        payload = {
            "id": ["freq", "unit", "coicop18", "geo", "time"],
            "size": [1, 1, 1, 1, 2],
            "dimension": {
                "time": {"category": {"index": {"2026-01": 0, "2026-02": 1}}}
            },
            "value": {"0": 100.0, "1": 110.0},
        }

        series = parse_eurostat_hicp(
            payload,
            source=c.INFLATION_SOURCE_EUROSTAT_DE,
            region="DE",
            fetched_at="2026-03-01",
        )

        self.assertEqual(series.latest_month, "2026-02")
        self.assertEqual(series.factor(date(2026, 1, 1), date(2026, 2, 1)), 1.1)
        self.assertAlmostEqual(
            series.adjust(100, date(2026, 1, 1), date(2026, 2, 1)), 110
        )

    def test_future_inflation_uses_a_geometric_annual_factor(self) -> None:
        start = date(2026, 1, 1)
        end = date(2027, 1, 1)

        factor = future_inflation_factor(10, start, end)

        self.assertAlmostEqual(factor, 1.1 ** (365 / 365.2425))
        self.assertAlmostEqual(
            purchasing_power(110, today=start, through=end, annual_percent=10),
            110 / factor,
        )

    def test_history_and_forecast_expose_nominal_and_real_values(self) -> None:
        today = date(2026, 2, 1)
        series = InflationSeries(
            c.INFLATION_SOURCE_EUROSTAT_DE,
            "DE",
            {"2025-12": 100, "2026-01": 100, "2026-02": 110},
        )

        result = build_history(
            wallet(), {}, today=today, forecast_years=1, inflation=series
        )

        current = result["points"][-1]
        self.assertEqual(current["value"], 100)
        self.assertEqual(current["real_invested"], 110)
        self.assertEqual(current["real_profit"], -10)
        forecast = result["target"]["forecasts"]["1"]
        self.assertEqual(forecast["value"], 100)
        self.assertLess(forecast["real_value"], forecast["value"])
        self.assertGreater(forecast["inflation_effect"], 0)
        self.assertIsNotNone(result["summaries_real"])


class InflationClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_daily_fetch_uses_cache_and_marks_failed_refresh_stale(self) -> None:
        series = InflationSeries(
            c.INFLATION_SOURCE_EUROSTAT_DE,
            "DE",
            {"2026-01": 100},
            fetched_at="2026-03-01",
        )
        fetch = AsyncMock(side_effect=[series, ValueError("offline")])
        client = InflationDataClient(object(), "wallet")

        with patch(
            "custom_components.my_wallet.inflation_client.fetch_eurostat_hicp",
            fetch,
        ):
            first = await client.async_get(
                object(),
                source=c.INFLATION_SOURCE_EUROSTAT_DE,
                today=date(2026, 3, 1),
            )
            cached = await client.async_get(
                object(),
                source=c.INFLATION_SOURCE_EUROSTAT_DE,
                today=date(2026, 3, 1),
            )
            with self.assertLogs(
                "custom_components.my_wallet.inflation_client", level="WARNING"
            ):
                stale = await client.async_get(
                    object(),
                    source=c.INFLATION_SOURCE_EUROSTAT_DE,
                    today=date(2026, 3, 2),
                )
            repeated = await client.async_get(
                object(),
                source=c.INFLATION_SOURCE_EUROSTAT_DE,
                today=date(2026, 3, 2),
            )

        self.assertIs(first, series)
        self.assertIs(cached, series)
        self.assertTrue(stale.stale)
        self.assertTrue(repeated.stale)
        self.assertEqual(fetch.await_count, 2)


class InflationOptionsTests(unittest.IsolatedAsyncioTestCase):
    async def test_settings_persist_and_validate_future_inflation(self) -> None:
        flow, entry, manager = _flow()

        result = await flow.async_step_settings(
            {
                c.CONF_WALLET_NAME: "Wallet",
                c.CONF_BASE_CURRENCY: "EUR",
                c.CONF_SCAN_INTERVAL: 30,
                c.CONF_INFLATION_SOURCE: c.INFLATION_SOURCE_EUROSTAT_DE,
                c.CONF_EXPECTED_ANNUAL_INFLATION: 2.5,
            }
        )

        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(entry.data[c.CONF_EXPECTED_ANNUAL_INFLATION], 2.5)
        self.assertEqual(
            entry.data[c.CONF_INFLATION_SOURCE], c.INFLATION_SOURCE_EUROSTAT_DE
        )
        self.assertEqual((manager.updates, manager.reloads), (1, 1))

        invalid_flow, invalid_entry, invalid_manager = _flow(entry.data)
        invalid = await invalid_flow.async_step_settings(
            {
                c.CONF_WALLET_NAME: "Wallet",
                c.CONF_BASE_CURRENCY: "EUR",
                c.CONF_SCAN_INTERVAL: 30,
                c.CONF_INFLATION_SOURCE: c.INFLATION_SOURCE_EUROSTAT_DE,
                c.CONF_EXPECTED_ANNUAL_INFLATION: 100.1,
            }
        )

        self.assertEqual(
            invalid["errors"][c.CONF_EXPECTED_ANNUAL_INFLATION], "invalid_number"
        )
        self.assertEqual(invalid_entry.data[c.CONF_EXPECTED_ANNUAL_INFLATION], 2.5)
        self.assertEqual((invalid_manager.updates, invalid_manager.reloads), (0, 0))


class AliasConsistencyTests(unittest.TestCase):
    def test_alias_labels_keep_the_stable_symbol_as_the_value(self) -> None:
        valors = wallet()[c.CONF_VALORS]

        self.assertEqual(position_label(valors, "AAA"), "World fund (AAA)")
        self.assertEqual(
            position_options(valors),
            [{"value": "AAA", "label": "World fund (AAA)"}],
        )

    def test_dashboard_contains_the_real_value_switch_and_real_series(self) -> None:
        source = (
            ROOT / "custom_components" / "my_wallet" / "frontend" / "my-wallet-panel.js"
        ).read_text(encoding="utf-8")

        for fragment in (
            'purchasingPower: "Kaufkraftbereinigt"',
            "wallet.real_money_weighted_return",
            "point.real_value",
            "this._history.summaries_real",
            "forecast.real_positions",
        ):
            self.assertIn(fragment, source)
