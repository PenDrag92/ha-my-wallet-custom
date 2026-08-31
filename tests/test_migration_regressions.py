"""Regression tests for config-entry migration hardening."""

from __future__ import annotations

import copy
import importlib.machinery
import importlib.util
import sys
import types
import unittest
from datetime import UTC, datetime
from typing import Any

from tests.bootstrap import PACKAGE, install_stubs

install_stubs()


class _ConfigEntry:
    @classmethod
    def __class_getitem__(cls, _item: object) -> type[_ConfigEntry]:
        return cls


class _HomeAssistant:
    pass


config_entries_module = types.ModuleType("homeassistant.config_entries")
config_entries_module.ConfigEntry = _ConfigEntry
core_module = types.ModuleType("homeassistant.core")
core_module.HomeAssistant = _HomeAssistant
dt_module = types.ModuleType("homeassistant.util.dt")
dt_module.now = lambda: datetime(2026, 8, 31, 12, tzinfo=UTC)
util_module = types.ModuleType("homeassistant.util")
util_module.dt = dt_module
coordinator_module = types.ModuleType("custom_components.my_wallet.coordinator")
coordinator_module.WalletCoordinator = type("WalletCoordinator", (), {})

sys.modules["homeassistant.config_entries"] = config_entries_module
sys.modules["homeassistant.core"] = core_module
sys.modules["homeassistant.util"] = util_module
sys.modules["homeassistant.util.dt"] = dt_module
sys.modules["custom_components.my_wallet.coordinator"] = coordinator_module

module_name = "custom_components.my_wallet._migration_test_subject"
loader = importlib.machinery.SourceFileLoader(module_name, str(PACKAGE / "__init__.py"))
spec = importlib.util.spec_from_loader(module_name, loader, is_package=False)
assert spec is not None and spec.loader is not None
migration = importlib.util.module_from_spec(spec)
sys.modules[module_name] = migration
spec.loader.exec_module(migration)


class _Entry:
    def __init__(self, version: int, data: dict[str, Any]) -> None:
        self.version = version
        self.data = data


class _ConfigEntriesManager:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], int]] = []

    def async_update_entry(
        self, entry: _Entry, *, data: dict[str, Any], version: int
    ) -> None:
        self.calls.append((data, version))
        entry.data = data
        entry.version = version


class _Hass:
    def __init__(self) -> None:
        self.config_entries = _ConfigEntriesManager()


def _plan(
    *,
    amount: float = 10,
    allocations: list[dict[str, Any]] | None = None,
    cutoff: str | None = None,
) -> dict[str, Any]:
    return {
        "id": "plan-1",
        "name": "Monthly",
        "enabled": True,
        "first_date": "2026-01-20",
        "end_date": None,
        "allocation_mode": "percentage",
        "amount": amount,
        "allocations": allocations
        or [
            {"symbol": "AAA", "value": 50},
            {"symbol": "BBB", "value": 50},
        ],
        "use_cash_balance": True,
        "opening_cutoff_date": cutoff,
    }


def _valors() -> list[dict[str, Any]]:
    return [
        {"symbol": "AAA", "amount": 10},
        {"symbol": "BBB", "amount": 10},
    ]


class MigrationRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_v1_legacy_amount_migrates_directly_to_version_six(self) -> None:
        hass = _Hass()
        entry = _Entry(
            1,
            {
                "invested_amount": 123.45,
                "savings_plans": [],
                "unrelated": "preserved",
            },
        )

        self.assertTrue(await migration.async_migrate_entry(hass, entry))

        self.assertEqual(entry.version, 6)
        self.assertNotIn("invested_amount", entry.data)
        self.assertEqual(entry.data["unrelated"], "preserved")
        self.assertEqual(entry.data["dividends"], [])
        self.assertEqual(entry.data["savings_plans"], [])
        self.assertEqual(entry.data["retired_savings_plans"], [])
        self.assertEqual(len(entry.data["contributions"]), 1)
        contribution = entry.data["contributions"][0]
        self.assertEqual(contribution["id"], "legacy_invested_amount")
        self.assertEqual(contribution["amount"], 123.45)
        self.assertEqual(contribution["source"], "legacy")
        self.assertIsNone(contribution["date"])
        self.assertEqual(len(hass.config_entries.calls), 1)

    async def test_v3_mini_plan_is_preserved_but_safely_disabled(self) -> None:
        hass = _Hass()
        allocations = [
            {"symbol": "AAA", "value": 50},
            {"symbol": "BBB", "value": 50},
        ]
        entry = _Entry(
            3,
            {
                "contributions": [],
                "dividends": [],
                "valors": _valors(),
                "savings_plans": [
                    _plan(amount=0.01, allocations=copy.deepcopy(allocations))
                ],
            },
        )

        with self.assertLogs(migration._LOGGER.name, level="WARNING") as logs:
            result = await migration.async_migrate_entry(hass, entry)

        self.assertTrue(result)
        self.assertEqual(entry.version, 6)
        migrated = entry.data["savings_plans"][0]
        self.assertEqual(migrated["id"], "plan-1")
        self.assertEqual(migrated["amount"], 0.01)
        self.assertEqual(migrated["allocations"], allocations)
        self.assertFalse(migrated["enabled"])
        self.assertIn("Disabled legacy savings plan", "\n".join(logs.output))

    async def test_v4_future_opening_cutoff_is_clamped_and_idempotent(self) -> None:
        hass = _Hass()
        entry = _Entry(
            4,
            {
                "contributions": [],
                "dividends": [],
                "valors": _valors(),
                "savings_plans": [_plan(cutoff="2099-12-31")],
                "retired_savings_plans": [
                    {
                        **_plan(cutoff="2026-01-01"),
                        "id": "retired-plan",
                        "skipped_periods": ["2026-02"],
                    }
                ],
                "unrelated": {"keep": True},
            },
        )

        self.assertTrue(await migration.async_migrate_entry(hass, entry))

        self.assertEqual(entry.version, 6)
        self.assertEqual(
            entry.data["savings_plans"][0]["opening_cutoff_date"], "2026-08-31"
        )
        self.assertEqual(entry.data["retired_savings_plans"][0]["id"], "retired-plan")
        self.assertEqual(
            entry.data["retired_savings_plans"][0]["skipped_periods"],
            ["2026-02"],
        )
        self.assertEqual(entry.data["unrelated"], {"keep": True})
        migrated_once = copy.deepcopy(entry.data)
        self.assertTrue(await migration.async_migrate_entry(hass, entry))
        self.assertEqual(entry.data, migrated_once)
        self.assertEqual(len(hass.config_entries.calls), 1)

    async def test_invalid_nonlegacy_plan_fails_without_mutating_entry(self) -> None:
        hass = _Hass()
        data = {
            "contributions": [],
            "dividends": [],
            "valors": _valors(),
            "savings_plans": [
                _plan(
                    allocations=[
                        {"symbol": "AAA", "value": 60},
                        {"symbol": "BBB", "value": 30},
                    ]
                )
            ],
        }
        original = copy.deepcopy(data)
        entry = _Entry(3, data)

        with self.assertLogs(migration._LOGGER.name, level="ERROR") as logs:
            result = await migration.async_migrate_entry(hass, entry)

        self.assertFalse(result)
        self.assertEqual(entry.version, 3)
        self.assertEqual(entry.data, original)
        self.assertEqual(hass.config_entries.calls, [])
        self.assertIn("Failed to migrate", "\n".join(logs.output))

    async def test_v6_entry_is_a_noop_even_with_opaque_data(self) -> None:
        hass = _Hass()
        entry = _Entry(6, {"opaque": ["leave", "untouched"]})
        original = copy.deepcopy(entry.data)

        self.assertTrue(await migration.async_migrate_entry(hass, entry))

        self.assertEqual(entry.version, 6)
        self.assertEqual(entry.data, original)
        self.assertEqual(hass.config_entries.calls, [])

    async def test_v4_invalid_lot_funding_fails_atomically(self) -> None:
        base_lot = {
            "id": "lot-1",
            "symbol": "AAA",
            "date": "2026-01-20",
            "amount": 50,
            "unit_price": 10,
            "quote_currency": "EUR",
            "fx_rate": 1,
            "units": 5,
            "estimated": False,
        }
        invalid_rows = [
            {
                "id": "legacy",
                "date": None,
                "amount": 50,
                "source": "legacy",
                "lots": [{**base_lot, "included_in_opening": False}],
            },
            {
                "id": "late-funding",
                "date": "2026-02-01",
                "amount": 50,
                "source": "manual",
                "lots": [{**base_lot, "included_in_opening": True}],
            },
        ]

        for invalid in invalid_rows:
            with self.subTest(contribution=invalid["id"]):
                hass = _Hass()
                data = {
                    "contributions": [invalid],
                    "dividends": [],
                    "savings_plans": [],
                }
                original = copy.deepcopy(data)
                entry = _Entry(4, data)

                with self.assertLogs(migration._LOGGER.name, level="ERROR"):
                    result = await migration.async_migrate_entry(hass, entry)

                self.assertFalse(result)
                self.assertEqual(entry.version, 4)
                self.assertEqual(entry.data, original)
                self.assertEqual(hass.config_entries.calls, [])

    async def test_v4_opening_unit_overflow_fails_atomically(self) -> None:
        data = {
            "valors": [{"symbol": "AAA", "amount": 1}],
            "contributions": [
                {
                    "id": "funding",
                    "date": "2026-01-20",
                    "amount": 20,
                    "source": "manual",
                    "lots": [
                        {
                            "id": "lot-1",
                            "symbol": "AAA",
                            "date": "2026-01-20",
                            "amount": 20,
                            "unit_price": 10,
                            "quote_currency": "EUR",
                            "fx_rate": 1,
                            "units": 2,
                            "included_in_opening": True,
                            "estimated": False,
                        }
                    ],
                }
            ],
            "dividends": [],
            "savings_plans": [],
        }
        original = copy.deepcopy(data)
        hass = _Hass()
        entry = _Entry(4, data)

        with self.assertLogs(migration._LOGGER.name, level="ERROR") as logs:
            result = await migration.async_migrate_entry(hass, entry)

        self.assertFalse(result)
        self.assertEqual(entry.version, 4)
        self.assertEqual(entry.data, original)
        self.assertEqual(hass.config_entries.calls, [])
        self.assertIn("exceed configured units", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
