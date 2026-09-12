"""Component reads share a window, preserve isolation and remain bounded."""

from __future__ import annotations

import asyncio
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

# Install the Home Assistant test stubs before importing the output adapters.
from tests.test_v190_planning import wallet

# isort: split
from custom_components.my_wallet import recorded_history as history
from tests.test_panel_regressions import Connection, hass_with, panel


class ComponentTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_window_bounded_reads_and_one_failed_position(self):
        data = wallet()
        data["valors"] = [{"symbol": f"ASSET{i}"} for i in range(7)]
        entry = SimpleNamespace(entry_id="wallet", data=data)
        calls, active, maximum = [], 0, 0

        async def read(hass, actual_entry, *, period, symbol, end):
            nonlocal active, maximum
            self.assertIs(actual_entry, entry)
            self.assertEqual(period, "week")
            active += 1
            maximum = max(maximum, active)
            calls.append((symbol, end))
            await asyncio.sleep(0)
            active -= 1
            if symbol == "ASSET2":
                raise RuntimeError("Synthetic recorder failure")
            return {"symbol": symbol, "points": [{"value": 5}]}

        with (
            patch.object(history, "async_recorded_history", side_effect=read),
            self.assertLogs(history.__name__, level="ERROR"),
        ):
            result = await history.async_recorded_components(None, entry, period="week")
        self.assertEqual(len(calls), 8)
        self.assertEqual(len({end for _, end in calls}), 1)
        self.assertEqual(maximum, 3)
        self.assertEqual(result["end"], calls[0][1].isoformat())
        self.assertEqual(result["cash"]["symbol"], None)
        self.assertEqual(result["positions"]["ASSET2"]["status"], "history_failed")
        self.assertEqual(result["positions"]["ASSET2"]["points"], [])
        self.assertEqual(result["positions"]["ASSET1"]["symbol"], "ASSET1")

    async def test_component_scope_is_admin_only_and_rejects_a_symbol(self):
        entry = SimpleNamespace(entry_id="wallet", data=wallet())
        with patch.object(
            panel, "async_recorded_components", new_callable=AsyncMock
        ) as read:
            for admin, extra in (
                (False, {}),
                (True, {"entry_id": "another-wallet"}),
                (True, {"symbol": "AAA"}),
                (True, {"period": "month"}),
            ):
                connection = Connection(admin=admin)
                await panel.ws_recorded_history(
                    hass_with([entry]),
                    connection,
                    {
                        "id": 1,
                        "entry_id": "wallet",
                        "period": "day",
                        "components": True,
                        **extra,
                    },
                )
                self.assertTrue(connection.errors)
                self.assertEqual(connection.results, [])
            read.assert_not_awaited()

    async def test_component_cache_does_not_reuse_total_and_rejects_config_changes(
        self,
    ):
        entry = SimpleNamespace(entry_id="wallet", data=wallet())
        hass = hass_with([entry])
        request = {"id": 1, "entry_id": "wallet", "period": "day"}
        with (
            patch.object(
                panel,
                "async_recorded_history",
                new_callable=AsyncMock,
                return_value={"points": []},
            ) as total,
            patch.object(
                panel,
                "async_recorded_components",
                new_callable=AsyncMock,
                return_value={"positions": {}},
            ) as components,
        ):
            await panel.ws_recorded_history(hass, Connection(), request)
            await panel.ws_recorded_history(
                hass, Connection(), {**request, "components": True}
            )
            await panel.ws_recorded_history(
                hass, Connection(), {**request, "components": True}
            )
            self.assertEqual(total.await_count, 1)
            self.assertEqual(components.await_count, 1)
            entry.data = copy.deepcopy(entry.data)

            async def change(*args, **kwargs):
                entry.data = copy.deepcopy(entry.data)
                return {"positions": {}}

            components.side_effect = change
            connection = Connection()
            await panel.ws_recorded_history(
                hass, connection, {**request, "components": True}
            )
            self.assertEqual(connection.errors[0][1], "entry_changed")
            self.assertEqual(connection.results, [])
