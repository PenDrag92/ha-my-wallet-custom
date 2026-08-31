"""Test authentication and import ownership at the WebSocket boundary."""

from __future__ import annotations

import sys
import types
import unittest
from time import monotonic
from unittest.mock import AsyncMock

from tests.test_options_regressions import config_flow as config_flow  # Test stubs.

components = sys.modules.setdefault(
    "homeassistant.components", types.ModuleType("homeassistant.components")
)
custom = types.ModuleType("homeassistant.components.panel_custom")
custom.async_register_panel = AsyncMock()
websocket = types.ModuleType("homeassistant.components.websocket_api")
websocket.websocket_command = lambda schema: lambda function: function
websocket.async_response = lambda function: function
websocket.async_register_command = lambda hass, command: None
http = types.ModuleType("homeassistant.components.http")
http.StaticPathConfig = lambda path, directory, cache: (path, directory, cache)
for module in (custom, websocket, http):
    sys.modules[module.__name__] = module
components.panel_custom = custom
components.websocket_api = websocket

from custom_components.my_wallet import panel


class Connection:
    def __init__(self, *, admin=True, user_id="user-a"):
        self.user = types.SimpleNamespace(is_admin=admin, id=user_id)
        self.errors = []
        self.results = []

    def send_error(self, *args):
        self.errors.append(args)

    def send_result(self, *args):
        self.results.append(args)


def hass_with(entries=()):
    return types.SimpleNamespace(
        data={},
        config_entries=types.SimpleNamespace(
            async_entries=lambda domain: list(entries),
            flow=types.SimpleNamespace(async_init=AsyncMock()),
        ),
        http=types.SimpleNamespace(async_register_static_paths=AsyncMock()),
    )


class PanelTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_financial_endpoint_requires_an_administrator(self):
        hass = hass_with()
        for command in (
            panel.ws_wallets,
            panel.ws_history,
            panel.ws_import_preview,
            panel.ws_import_commit,
        ):
            with self.subTest(command=command.__name__):
                connection = Connection(admin=False)
                result = command(hass, connection, {"id": 1})
                if command is not panel.ws_wallets:
                    await result
                self.assertEqual(connection.errors[0][1], "unauthorized")
                self.assertEqual(connection.results, [])
        self.assertEqual(hass.data, {})
        hass.config_entries.flow.async_init.assert_not_awaited()

    async def test_panel_registers_once_and_is_admin_only(self):
        hass = hass_with()
        custom.async_register_panel.reset_mock()
        await panel.async_setup_panel(hass)
        await panel.async_setup_panel(hass)
        self.assertEqual(hass.http.async_register_static_paths.await_count, 1)
        custom.async_register_panel.assert_awaited_once()
        self.assertTrue(custom.async_register_panel.call_args.kwargs["require_admin"])
        self.assertIn(
            "/my_wallet_static/",
            custom.async_register_panel.call_args.kwargs["module_url"],
        )

    def test_preview_is_bound_to_its_user_and_consumed_only_once(self):
        hass = hass_with()
        data = {"import_batch": "test", "valors": []}
        previews = panel._state(hass)["previews"]
        previews["token"] = {
            "data": data,
            "user_id": "user-a",
            "expires": monotonic() + 60,
        }
        with self.assertRaisesRegex(ValueError, "import_expired"):
            panel.consume_import(hass, "token", "user-b")
        self.assertIn("token", previews)
        self.assertIs(panel.consume_import(hass, "token", "user-a"), data)
        with self.assertRaisesRegex(ValueError, "import_expired"):
            panel.consume_import(hass, "token", "user-a")

    def test_expired_and_duplicate_previews_cannot_create_a_wallet(self):
        existing = types.SimpleNamespace(data={"import_batch": "same", "valors": []})
        hass = hass_with([existing])
        previews = panel._state(hass)["previews"]
        previews["token"] = {
            "data": {"import_batch": "same"},
            "user_id": "user-a",
            "expires": monotonic() + 60,
        }
        with self.assertRaisesRegex(ValueError, "already_imported"):
            panel.consume_import(hass, "token", "user-a")
        previews["token"]["expires"] = monotonic() - 1
        with self.assertRaisesRegex(ValueError, "import_expired"):
            panel.consume_import(hass, "token", "user-a")
        self.assertFalse(
            panel._batch_exists(
                hass_with([types.SimpleNamespace(data={"valors": []})]), None
            )
        )

    async def test_commit_without_explicit_confirmation_cannot_write(self):
        hass = hass_with()
        connection = Connection()
        await panel.ws_import_commit(
            hass, connection, {"id": 1, "confirm": False, "token": "token"}
        )
        self.assertEqual(connection.errors[0][1], "confirmation_required")
        hass.config_entries.flow.async_init.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
