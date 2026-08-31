"""Regressions for plan booking and defensive Yahoo parsing."""

from __future__ import annotations

import asyncio
import sys
import types
import unittest
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

from tests.bootstrap import install_stubs

install_stubs()


def _install_coordinator_stubs() -> None:
    """Install the small Home Assistant surface needed to import coordinator."""
    config_entries = types.ModuleType("homeassistant.config_entries")
    core = types.ModuleType("homeassistant.core")
    helpers = types.ModuleType("homeassistant.helpers")
    aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")
    util = types.ModuleType("homeassistant.util")
    dt_module = types.ModuleType("homeassistant.util.dt")

    class ConfigEntry:
        pass

    class HomeAssistant:
        pass

    class DataUpdateCoordinator:
        @classmethod
        def __class_getitem__(cls, _: object) -> type[DataUpdateCoordinator]:
            return cls

        def __init__(self, hass: Any, _logger: Any, *, name: str, **_: Any) -> None:
            self.hass = hass
            self.name = name

    class UpdateFailed(Exception):
        pass

    config_entries.ConfigEntry = ConfigEntry
    core.HomeAssistant = HomeAssistant
    aiohttp_client.async_get_clientsession = lambda hass: hass.session
    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator.UpdateFailed = UpdateFailed
    dt_module.now = lambda: datetime.now(UTC)
    util.dt = dt_module

    modules = {
        "homeassistant.config_entries": config_entries,
        "homeassistant.core": core,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.aiohttp_client": aiohttp_client,
        "homeassistant.helpers.update_coordinator": update_coordinator,
        "homeassistant.util": util,
        "homeassistant.util.dt": dt_module,
    }
    for name, module in modules.items():
        sys.modules.setdefault(name, module)


_install_coordinator_stubs()

from custom_components.my_wallet import coordinator as coordinator_module  # noqa: E402
from custom_components.my_wallet import yahoo as yahoo_module  # noqa: E402
from custom_components.my_wallet.const import (  # noqa: E402
    ALLOCATION_MODE_FIXED,
    ALLOCATION_MODE_PERCENTAGE,
    ALLOCATION_SYMBOL,
    ALLOCATION_VALUE,
    CONF_BASE_CURRENCY,
    CONF_CONTRIBUTIONS,
    CONF_SAVINGS_PLANS,
    CONF_VALORS,
    CONF_WALLET_NAME,
    PLAN_ENABLED,
    VALOR_AMOUNT,
    VALOR_SYMBOL,
)
from custom_components.my_wallet.contributions import (  # noqa: E402
    make_contribution,
    make_lot,
)
from custom_components.my_wallet.coordinator import (  # noqa: E402
    WalletCoordinator,
    _close_date_bounds,
    _execution_sort_key,
    _included_opening_overflows,
)
from custom_components.my_wallet.plans import make_plan, normalize_plan  # noqa: E402
from custom_components.my_wallet.yahoo import (  # noqa: E402
    HistoricalQuote,
    Quote,
    YahooError,
    fetch_histories,
    fetch_history,
    fetch_quote,
    fetch_quotes,
)


def _allocation(symbol: str, value: float) -> dict[str, object]:
    return {ALLOCATION_SYMBOL: symbol, ALLOCATION_VALUE: value}


class _ConfigEntries:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    def async_update_entry(self, entry: Any, *, data: dict[str, Any]) -> None:
        self.updates.append(data)
        entry.data = data


class _Response:
    def __init__(self, payload: Any = None, *, json_error: Exception | None = None):
        self.status = 200
        self._payload = payload
        self._json_error = json_error

    async def __aenter__(self) -> _Response:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def json(self) -> Any:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class _Session:
    def __init__(self, response: _Response):
        self.response = response

    def get(self, *_: object, **__: object) -> _Response:
        return self.response


class PlanNormalizationTests(unittest.TestCase):
    def test_disabled_tiny_percentage_plan_normalizes_but_cannot_activate(self) -> None:
        disabled = make_plan(
            name="Migrated tiny plan",
            first_date="2026-01-20",
            allocation_mode=ALLOCATION_MODE_PERCENTAGE,
            amount=0.01,
            allocations=[_allocation("A", 50), _allocation("B", 50)],
            enabled=False,
        )

        self.assertFalse(normalize_plan(disabled)[PLAN_ENABLED])
        with self.assertRaisesRegex(ValueError, "too small"):
            normalize_plan({**disabled, PLAN_ENABLED: True})


class CoordinatorRegressionTests(unittest.TestCase):
    def _coordinator(self, data: dict[str, Any]) -> tuple[WalletCoordinator, Any]:
        manager = _ConfigEntries()
        hass = SimpleNamespace(config_entries=manager)
        entry = SimpleNamespace(data=data, title="Fallback wallet")
        return WalletCoordinator(hass, entry), entry

    def test_name_uses_wallet_name_key(self) -> None:
        coordinator, _ = self._coordinator(
            {CONF_BASE_CURRENCY: "EUR", CONF_WALLET_NAME: "Family"}
        )
        self.assertEqual(coordinator.name, "my_wallet_Family")

    def test_mixed_close_bounds_are_stable_and_conservative(self) -> None:
        self.assertEqual(
            _close_date_bounds(
                [date(2026, 1, 22), date(2026, 1, 20), date(2026, 1, 21)]
            ),
            (date(2026, 1, 20), date(2026, 1, 22)),
        )

    def test_execution_order_uses_schedule_as_stable_tie_break(self) -> None:
        executions = [
            ([date(2026, 1, 20), date(2026, 1, 21)], date(2026, 1, 15), "b"),
            ([date(2026, 1, 20), date(2026, 1, 25)], date(2026, 1, 10), "z"),
            ([date(2026, 1, 19), date(2026, 1, 26)], date(2026, 1, 18), "a"),
        ]
        self.assertEqual(
            sorted(
                executions,
                key=lambda item: _execution_sort_key(item[0], item[1], item[2]),
            ),
            [executions[2], executions[1], executions[0]],
        )

    def test_shared_cash_uses_earliest_selected_close(self) -> None:
        plan = make_plan(
            name="Monthly",
            first_date="2026-01-20",
            allocation_mode=ALLOCATION_MODE_FIXED,
            allocations=[_allocation("A", 25), _allocation("B", 25)],
            plan_id="plan",
            use_cash_balance=True,
        )
        coordinator, _ = self._coordinator(
            {
                CONF_BASE_CURRENCY: "EUR",
                CONF_WALLET_NAME: "Family",
                CONF_SAVINGS_PLANS: [plan],
                CONF_VALORS: [
                    {VALOR_SYMBOL: "A", VALOR_AMOUNT: 0},
                    {VALOR_SYMBOL: "B", VALOR_AMOUNT: 0},
                ],
            }
        )
        seen_dates: list[date] = []

        async def fake_histories(
            _session: Any,
            symbols: list[str],
            _start: date,
            _end: date,
        ) -> dict[str, list[HistoricalQuote]]:
            closes = {"A": date(2026, 1, 20), "B": date(2026, 1, 22)}
            return {
                symbol: [HistoricalQuote(symbol, closes[symbol], 10, "EUR")]
                for symbol in symbols
            }

        def fake_cash(
            _data: dict[str, Any],
            *,
            execution_through: date,
            today: date,
            reserved: float = 0,
        ) -> float:
            del today, reserved
            seen_dates.append(execution_through)
            return 0

        original_histories = coordinator_module.fetch_histories
        original_cash = coordinator_module.reinvestable_cash
        coordinator_module.fetch_histories = fake_histories
        coordinator_module.reinvestable_cash = fake_cash
        try:
            pending = asyncio.run(
                coordinator._async_book_due_plans(object(), {}, date(2026, 1, 31))
            )
        finally:
            coordinator_module.fetch_histories = original_histories
            coordinator_module.reinvestable_cash = original_cash

        self.assertEqual(pending, [])
        self.assertEqual(seen_dates, [date(2026, 1, 20)])

    def test_opening_overflow_counts_existing_and_proposed_lots(self) -> None:
        existing = make_lot(
            symbol="A",
            execution_date="2025-12-20",
            amount=20,
            unit_price=10,
            quote_currency="EUR",
            included_in_opening=True,
        )
        proposed = make_lot(
            symbol="A",
            execution_date="2026-01-20",
            amount=20,
            unit_price=10,
            quote_currency="EUR",
            included_in_opening=True,
        )
        self.assertEqual(
            _included_opening_overflows(
                [{VALOR_SYMBOL: "A", VALOR_AMOUNT: 3}],
                [make_contribution(20, "2025-12-20", lots=[existing])],
                [proposed],
            ),
            ["A"],
        )

    def test_opening_overflow_leaves_whole_execution_pending(self) -> None:
        existing_lot = make_lot(
            symbol="A",
            execution_date="2025-12-20",
            amount=20,
            unit_price=10,
            quote_currency="EUR",
            included_in_opening=True,
        )
        existing_contribution = make_contribution(20, "2025-12-20", lots=[existing_lot])
        plan = make_plan(
            name="Monthly",
            first_date="2026-01-20",
            allocation_mode=ALLOCATION_MODE_FIXED,
            allocations=[_allocation("A", 20)],
            plan_id="plan",
            use_cash_balance=False,
            opening_cutoff_date="2026-01-31",
        )
        coordinator, entry = self._coordinator(
            {
                CONF_BASE_CURRENCY: "EUR",
                CONF_CONTRIBUTIONS: [existing_contribution],
                CONF_SAVINGS_PLANS: [plan],
                CONF_VALORS: [{VALOR_SYMBOL: "A", VALOR_AMOUNT: 3}],
            }
        )

        async def fake_histories(
            _session: Any,
            symbols: list[str],
            _start: date,
            _end: date,
        ) -> dict[str, list[HistoricalQuote]]:
            return {
                symbol: [HistoricalQuote(symbol, date(2026, 1, 20), 10, "EUR")]
                for symbol in symbols
            }

        original_histories = coordinator_module.fetch_histories
        coordinator_module.fetch_histories = fake_histories
        try:
            pending = asyncio.run(
                coordinator._async_book_due_plans(object(), {}, date(2026, 1, 31))
            )
        finally:
            coordinator_module.fetch_histories = original_histories

        self.assertEqual(len(entry.data[CONF_CONTRIBUTIONS]), 1)
        self.assertEqual(pending[0]["reason"], "included_units_exceeded")
        self.assertTrue(pending[0]["repair_required"])
        self.assertEqual(pending[0]["affected_symbols"], ["A"])


class YahooRegressionTests(unittest.TestCase):
    def test_invalid_json_becomes_yahoo_error(self) -> None:
        with self.assertRaises(YahooError):
            asyncio.run(
                fetch_quote(
                    _Session(_Response(json_error=ValueError("broken json"))), "BAD"
                )
            )

    def test_invalid_history_timestamp_is_skipped(self) -> None:
        valid_timestamp = datetime(2026, 1, 2, tzinfo=UTC).timestamp()
        payload = {
            "chart": {
                "result": [
                    {
                        "meta": {"currency": "EUR", "exchangeTimezoneName": "UTC"},
                        "timestamp": ["invalid", 1e300, valid_timestamp],
                        "indicators": {"quote": [{"close": [10, 11, 12]}]},
                    }
                ]
            }
        }
        history = asyncio.run(
            fetch_history(
                _Session(_Response(payload)),
                "A",
                date(2026, 1, 1),
                date(2026, 1, 3),
            )
        )
        self.assertEqual(history, [HistoricalQuote("A", date(2026, 1, 2), 12, "EUR")])

    def test_invalid_quote_timestamp_returns_unconfirmed_quote(self) -> None:
        payload = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "currency": "EUR",
                            "regularMarketPrice": 12,
                            "regularMarketTime": 1e300,
                        }
                    }
                ]
            }
        }
        quote = asyncio.run(fetch_quote(_Session(_Response(payload)), "A"))
        self.assertIsNone(quote.market_date)
        self.assertFalse(quote.market_closed)

    def test_unexpected_symbol_failure_does_not_break_gathers(self) -> None:
        async def fake_quote(_session: Any, symbol: str) -> Quote:
            if symbol == "BAD":
                raise RuntimeError("unexpected quote failure")
            return Quote(symbol, 1, "EUR")

        async def fake_history(
            _session: Any, symbol: str, _start: date, _end: date
        ) -> list[HistoricalQuote]:
            if symbol == "BAD":
                raise RuntimeError("unexpected history failure")
            return [HistoricalQuote(symbol, date(2026, 1, 2), 1, "EUR")]

        original_quote = yahoo_module.fetch_quote
        original_history = yahoo_module.fetch_history
        yahoo_module.fetch_quote = fake_quote
        yahoo_module.fetch_history = fake_history
        try:
            with self.assertLogs(yahoo_module._LOGGER.name, level="ERROR") as logs:
                quotes = asyncio.run(fetch_quotes(object(), ["GOOD", "BAD"]))
                histories = asyncio.run(
                    fetch_histories(
                        object(),
                        ["GOOD", "BAD"],
                        date(2026, 1, 1),
                        date(2026, 1, 3),
                    )
                )
        finally:
            yahoo_module.fetch_quote = original_quote
            yahoo_module.fetch_history = original_history

        self.assertIsInstance(quotes["GOOD"], Quote)
        self.assertIsNone(quotes["BAD"])
        self.assertEqual(len(histories["GOOD"]), 1)
        self.assertEqual(histories["BAD"], [])
        self.assertEqual(len(logs.output), 2)


if __name__ == "__main__":
    unittest.main()
