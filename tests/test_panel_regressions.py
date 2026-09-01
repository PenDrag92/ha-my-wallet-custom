"""Test authentication and import ownership at the WebSocket boundary."""

from __future__ import annotations

import inspect
import sys
import types
import unittest
from time import monotonic
from unittest.mock import AsyncMock, Mock

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
    manager = types.SimpleNamespace(
        async_entries=lambda domain: list(entries),
        flow=types.SimpleNamespace(async_init=AsyncMock()),
        async_update_entry=Mock(),
        async_schedule_reload=Mock(),
    )
    return types.SimpleNamespace(
        data={},
        config_entries=manager,
        http=types.SimpleNamespace(async_register_static_paths=AsyncMock()),
    )


class PanelTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_financial_endpoint_requires_an_administrator(self):
        hass = hass_with()
        for command in (
            panel.ws_wallets,
            panel.ws_position_aliases,
            panel.ws_backup,
            panel.ws_history,
            panel.ws_import_preview,
            panel.ws_import_commit,
            panel.ws_correction_preview,
            panel.ws_correction_commit,
        ):
            with self.subTest(command=command.__name__):
                connection = Connection(admin=False)
                result = command(hass, connection, {"id": 1})
                if inspect.isawaitable(result):
                    await result
                self.assertEqual(connection.errors[0][1], "unauthorized")
                self.assertEqual(connection.results, [])
        self.assertEqual(hass.data, {})
        hass.config_entries.flow.async_init.assert_not_awaited()

    def test_wallet_selector_uses_current_entry_title(self):
        entry = types.SimpleNamespace(
            entry_id="wallet",
            title="Renamed wallet",
            data={
                "wallet_name": "Old wallet name",
                "base_currency": "EUR",
                "valors": [{"symbol": "AAA", "amount": 0, "alias": "Amundi"}],
                "contributions": [],
                "dividends": [],
                "savings_plans": [],
                "retired_savings_plans": [],
            },
            runtime_data=None,
        )
        connection = Connection()
        panel.ws_wallets(hass_with([entry]), connection, {"id": 1})
        self.assertEqual(
            connection.results[0][1]["wallets"][0]["name"], "Renamed wallet"
        )
        self.assertEqual(
            connection.results[0][1]["wallets"][0]["positions"][0]["alias"],
            "Amundi",
        )

    def test_wallet_and_position_start_dates_and_lot_details_are_documented(self):
        from custom_components.my_wallet.contributions import (
            make_contribution,
            make_lot,
        )
        from custom_components.my_wallet.dividends import make_dividend
        from custom_components.my_wallet.models import ValorData, WalletData
        from custom_components.my_wallet.yahoo import Quote

        data = {
            "wallet_name": "Wallet",
            "base_currency": "EUR",
            "scan_interval": 30,
            "valors": [{"symbol": "AAA", "amount": 0, "alias": "World ETF"}],
            "contributions": [
                make_contribution(
                    110,
                    "2026-01-15",
                    contribution_id="deposit",
                    lots=[
                        make_lot(
                            symbol="AAA",
                            execution_date="2026-01-15",
                            amount=100,
                            unit_price=10,
                            quote_currency="EUR",
                            units=10,
                            estimated=False,
                            lot_id="lot",
                        )
                    ],
                )
            ],
            "dividends": [
                make_dividend(
                    booking_date="2026-02-01",
                    amount=10,
                    symbol="AAA",
                    dividend_id="income",
                )
            ],
            "savings_plans": [],
            "retired_savings_plans": [],
        }
        current = WalletData(
            valors={
                "AAA": ValorData(
                    symbol="AAA",
                    amount=10,
                    opening_amount=0,
                    quote=Quote("AAA", 12, "EUR"),
                    fx_rate=1,
                )
            },
            cash_balance=20,
        )
        entry = types.SimpleNamespace(
            entry_id="wallet",
            title="Wallet",
            data=data,
            runtime_data=types.SimpleNamespace(
                data=current,
                last_update_success=True,
            ),
        )
        connection = Connection()

        panel.ws_wallets(hass_with([entry]), connection, {"id": 1})

        wallet = connection.results[0][1]["wallets"][0]
        position = wallet["positions"][0]
        self.assertEqual(wallet["start_date"], "2026-01-15")
        self.assertEqual(position["start_date"], "2026-01-15")
        self.assertAlmostEqual(position["share"], 120 / 140 * 100)
        self.assertEqual(position["lots"][0]["purchase_price"], 10)
        self.assertEqual(position["lots"][0]["current_value"], 120)
        self.assertEqual(position["lots"][0]["dividends"], 10)
        self.assertEqual(position["lots"][0]["profit"], 30)

    def test_unknown_opening_holding_does_not_invent_a_later_wallet_start(self):
        from custom_components.my_wallet.contributions import make_contribution

        entry = types.SimpleNamespace(
            entry_id="wallet",
            title="Wallet",
            data={
                "wallet_name": "Wallet",
                "base_currency": "EUR",
                "scan_interval": 30,
                "valors": [{"symbol": "AAA", "amount": 1}],
                "contributions": [
                    make_contribution(100, "2026-01-15", contribution_id="deposit")
                ],
                "dividends": [],
                "savings_plans": [],
                "retired_savings_plans": [],
            },
            runtime_data=None,
        )
        connection = Connection()

        panel.ws_wallets(hass_with([entry]), connection, {"id": 1})

        wallet = connection.results[0][1]["wallets"][0]
        self.assertIsNone(wallet["start_date"])
        self.assertIsNone(wallet["positions"][0]["start_date"])

    def test_backup_endpoint_returns_a_versioned_detached_document(self):
        data = {
            "wallet_name": "Wallet",
            "base_currency": "EUR",
            "scan_interval": 30,
            "valors": [{"symbol": "AAA", "amount": 0, "alias": "World ETF"}],
            "contributions": [],
            "dividends": [],
            "savings_plans": [],
            "retired_savings_plans": [],
        }
        entry = types.SimpleNamespace(
            entry_id="wallet", title="Renamed wallet", data=data
        )
        connection = Connection()

        panel.ws_backup(hass_with([entry]), connection, {"id": 1, "entry_id": "wallet"})

        document = connection.results[0][1]["document"]
        self.assertEqual(
            (document["format"], document["version"]), ("my_wallet_backup", 1)
        )
        self.assertEqual(document["wallet"]["title"], "Renamed wallet")
        self.assertEqual(document["wallet"]["data"]["valors"][0]["alias"], "World ETF")
        self.assertIsNot(document["wallet"]["data"], data)

    def test_position_aliases_are_trimmed_and_persisted_without_a_reload(self):
        data = {
            "wallet_name": "Wallet",
            "base_currency": "EUR",
            "valors": [
                {"symbol": "AAA", "amount": 1, "target_share": 60},
                {"symbol": "BBB", "amount": 2, "alias": "Old name"},
            ],
            "contributions": [],
            "dividends": [],
            "savings_plans": [],
            "retired_savings_plans": [],
        }
        entry = types.SimpleNamespace(entry_id="wallet", title="Wallet", data=data)
        hass = hass_with([entry])
        connection = Connection()

        panel.ws_position_aliases(
            hass,
            connection,
            {
                "id": 1,
                "entry_id": "wallet",
                "aliases": {"AAA": "  Amundi   Prime  ", "BBB": ""},
            },
        )

        saved = hass.config_entries.async_update_entry.call_args.kwargs["data"]
        self.assertEqual(
            saved["valors"],
            [
                {
                    "symbol": "AAA",
                    "amount": 1,
                    "target_share": 60,
                    "alias": "Amundi Prime",
                },
                {"symbol": "BBB", "amount": 2},
            ],
        )
        self.assertIs(saved["contributions"], data["contributions"])
        hass.config_entries.async_schedule_reload.assert_not_called()
        self.assertEqual(
            connection.results[0][1]["aliases"],
            {"AAA": "Amundi Prime", "BBB": ""},
        )

    def test_position_aliases_reject_unknown_symbols_and_long_values(self):
        entry = types.SimpleNamespace(
            entry_id="wallet",
            title="Wallet",
            data={
                "wallet_name": "Wallet",
                "base_currency": "EUR",
                "valors": [{"symbol": "AAA", "amount": 1}],
            },
        )
        for aliases in ({"BBB": "Unknown"}, {"AAA": "x" * 81}, {"AAA": 12}):
            with self.subTest(aliases=aliases):
                hass = hass_with([entry])
                connection = Connection()
                panel.ws_position_aliases(
                    hass,
                    connection,
                    {"id": 1, "entry_id": "wallet", "aliases": aliases},
                )
                self.assertEqual(connection.errors[0][1], "invalid_alias")
                hass.config_entries.async_update_entry.assert_not_called()

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

    async def test_backup_restore_uses_a_one_time_unique_id_not_config_data(self):
        from custom_components.my_wallet.backup import BACKUP_RESTORE_ID

        hass = hass_with()
        data = {
            "wallet_name": "Restored wallet",
            "base_currency": "EUR",
            "scan_interval": 30,
            "valors": [{"symbol": "AAA", "amount": 0}],
            "contributions": [],
            "dividends": [],
            "savings_plans": [],
            "retired_savings_plans": [],
            BACKUP_RESTORE_ID: "backup-id",
        }
        panel._state(hass)["previews"]["token"] = {
            "data": data,
            "user_id": "user-a",
            "expires": monotonic() + 60,
        }
        flow = config_flow.MyWalletConfigFlow()
        flow.hass = hass
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = Mock()

        result = await flow.async_step_import({"token": "token", "user_id": "user-a"})

        flow.async_set_unique_id.assert_awaited_once_with("import:backup-id")
        self.assertEqual(result["type"], "create_entry")
        self.assertNotIn(BACKUP_RESTORE_ID, result["data"])

    def test_correction_commit_is_user_bound_and_rejects_a_stale_wallet(self):
        from custom_components.my_wallet.contributions import (
            make_contribution,
            make_lot,
        )

        data = {
            "wallet_name": "Synthetic wallet",
            "base_currency": "EUR",
            "valors": [{"symbol": "AAA", "amount": 0}],
            "contributions": [
                make_contribution(
                    100,
                    "2026-01-20",
                    contribution_id="deposit",
                    source="import",
                    lots=[
                        make_lot(
                            symbol="AAA",
                            execution_date="2026-01-20",
                            amount=100,
                            unit_price=10,
                            quote_currency="EUR",
                            lot_id="lot",
                        )
                    ],
                )
            ],
            "dividends": [],
            "savings_plans": [],
            "retired_savings_plans": [],
        }
        entry = types.SimpleNamespace(entry_id="wallet", title="Wallet", data=data)
        hass = hass_with([entry])
        connection = Connection()
        panel.ws_correction_preview(
            hass,
            connection,
            {
                "id": 1,
                "entry_id": "wallet",
                "correction": {
                    "symbol": "AAA",
                    "target": "lot",
                    "mode": "position",
                    "units": 10.5,
                },
            },
        )
        token = connection.results[0][1]["token"]
        other = Connection(user_id="user-b")
        panel.ws_correction_commit(
            hass, other, {"id": 2, "token": token, "confirm": True}
        )
        self.assertEqual(other.errors[0][1], "import_expired")
        entry.data = dict(entry.data)
        panel.ws_correction_commit(
            hass, connection, {"id": 3, "token": token, "confirm": True}
        )
        self.assertEqual(connection.errors[0][1], "entry_changed")
        hass.config_entries.async_update_entry.assert_not_called()

        connection.results.clear()
        panel.ws_correction_preview(
            hass,
            connection,
            {
                "id": 4,
                "entry_id": "wallet",
                "correction": {
                    "symbol": "AAA",
                    "target": "lot",
                    "mode": "position",
                    "units": 10.5,
                },
            },
        )
        fresh = connection.results[0][1]["token"]
        panel.ws_correction_commit(
            hass, connection, {"id": 5, "token": fresh, "confirm": True}
        )
        hass.config_entries.async_update_entry.assert_called_once()
        hass.config_entries.async_schedule_reload.assert_called_once_with("wallet")


if __name__ == "__main__":
    unittest.main()
