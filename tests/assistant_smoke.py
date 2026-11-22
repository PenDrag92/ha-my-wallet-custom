"""Verify real HA LLM contracts without model calls, credentials or a live wallet.

Run separately from the dependency-stub unit suite: python -m tests.assistant_smoke.
CI pins Home Assistant 2026.8.3, including Conversation subentry configuration.
"""

from __future__ import annotations

import asyncio
import unittest
from contextlib import suppress
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm
from mcp import ClientSession
from mcp.shared.exceptions import MCPError
from mcp.shared.memory import create_client_server_memory_streams

from custom_components.my_wallet import assistant_service as service
from custom_components.my_wallet import const as c
from custom_components.my_wallet import llm as wallet_llm


class HassFixture:
    """HA singleton helpers key their state by a hashable instance."""

    def __init__(self, **attributes):
        self.__dict__.update(attributes)


class RealHomeAssistantLLMTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user = SimpleNamespace(id="admin", is_admin=True, is_active=True)
        self.unload = []
        self.entry = SimpleNamespace(
            entry_id="wallet-a",
            title="Synthetic wallet",
            domain=c.DOMAIN,
            data={c.CONF_VALORS: [], c.CONF_BASE_CURRENCY: "EUR"},
            runtime_data=None,
            async_on_unload=self.unload.append,
        )
        self.hass = HassFixture(
            data={},
            auth=SimpleNamespace(async_get_user=AsyncMock(return_value=self.user)),
            config_entries=SimpleNamespace(
                async_get_entry=lambda identifier: (
                    self.entry if identifier == "wallet-a" else None
                ),
                async_update_entry=Mock(),
            ),
        )
        self.context = llm.LLMContext(
            platform="openai_conversation",
            context=Context(user_id="admin"),
            language="de",
            assistant="conversation",
            device_id=None,
        )
        self.api = wallet_llm.WalletAPI(self.hass, "wallet-a", "Synthetic wallet")

    async def test_registration_is_explicit_scoped_and_unregistered_on_unload(self):
        wallet_llm.async_setup_wallet_api(self.hass, self.entry)
        apis = llm.async_get_apis(self.hass)
        self.assertEqual([api.id for api in apis], ["my_wallet_wallet-a"])
        instance = await llm.async_get_api(
            self.hass, "my_wallet_wallet-a", self.context
        )
        self.assertIsInstance(instance, llm.APIInstance)
        self.assertEqual(
            {tool.name for tool in instance.tools},
            {
                "WalletReport",
                "WalletScenario",
                "WalletAllocation",
            },
        )
        self.assertIsNone(wallet_llm.async_get_tools(self.hass, self.context, "assist"))
        self.assertIsNone(
            wallet_llm.async_get_tools(self.hass, self.context, "my_wallet_wallet-a")
        )
        for cleanup in self.unload:
            cleanup()
        self.assertEqual(llm.async_get_apis(self.hass), [])

    async def test_api_and_each_tool_require_current_admin_context(self):
        instance = await self.api.async_get_api_instance(self.context)
        self.user.is_admin = False
        with self.assertRaises(HomeAssistantError):
            await self.api.async_get_api_instance(self.context)
        for tool in instance.tools:
            with self.subTest(tool=tool.name), self.assertRaises(HomeAssistantError):
                await tool.async_call(
                    self.hass,
                    llm.ToolInput(tool_name=tool.name, tool_args={}),
                    self.context,
                )

    async def test_actual_voluptuous_schema_rejects_unknown_tool_fields(self):
        instance = await self.api.async_get_api_instance(self.context)
        for tool in instance.tools:
            with self.subTest(tool=tool.name), self.assertRaises(HomeAssistantError):
                await tool.async_call(
                    self.hass,
                    llm.ToolInput(
                        tool_name=tool.name, tool_args={"entry_id": "wallet-b"}
                    ),
                    self.context,
                )

    async def test_tool_outputs_use_the_application_service_and_do_not_write(self):
        before = deepcopy(self.entry.data)
        expected = {"status": "ok", "facts": {"total": 123.45}}
        with patch.object(service, "async_report", return_value=expected) as report:
            value = await wallet_llm.WalletReportTool("wallet-a").async_call(
                self.hass,
                llm.ToolInput(tool_name="WalletReport", tool_args={"month": "2026-08"}),
                self.context,
            )
        self.assertEqual(getattr(value, "data", value), expected)
        self.assertEqual(report.call_args.kwargs["month"], "2026-08")
        self.assertIs(report.call_args.args[1].data, self.entry.data)
        self.assertEqual(self.entry.data, before)
        self.hass.config_entries.async_update_entry.assert_not_called()

    async def test_native_mcp_lists_wallet_tools_and_runs_a_read_only_calculation(self):
        from homeassistant.components.mcp_server.server import create_server

        wallet_llm.async_setup_wallet_api(self.hass, self.entry)
        self.context.platform = "mcp_server"
        options = (
            {"read_only": True, "base_url": "http://example.invalid"}
            if hasattr(llm, "ToolAnnotations")
            else {}
        )
        server = await create_server(self.hass, self.api.id, self.context, **options)
        async with create_client_server_memory_streams() as (client_io, server_io):
            task = asyncio.create_task(
                server.run(*server_io, server.create_initialization_options())
            )
            try:
                async with asyncio.timeout(15), ClientSession(*client_io) as client:
                    await client.initialize()
                    await self.check_mcp_tools(client)
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        self.hass.config_entries.async_update_entry.assert_not_called()

    async def check_mcp_tools(self, client):
        self.assertEqual(
            {tool.name for tool in (await client.list_tools()).tools},
            {"WalletReport", "WalletScenario", "WalletAllocation"},
        )
        with patch.object(
            service, "allocation_result", return_value={"remaining_cash": 50}
        ) as allocate:
            result = await client.call_tool("WalletAllocation", {"amount": 50})
        self.assertFalse(result.model_dump(by_alias=True)["isError"], result)
        self.assertEqual(allocate.call_args.kwargs, {"amount": 50, "use_cash": False})
        self.assertIs(allocate.call_args.args[0].data, self.entry.data)
        self.user.is_admin = False
        with patch.object(service, "allocation_result") as denied_allocation:
            try:
                denied = await client.call_tool("WalletAllocation", {"amount": 50})
            except MCPError:
                pass  # Protocol-level rejection also blocks the tool.
            else:
                self.assertTrue(denied.model_dump(by_alias=True)["isError"])
        denied_allocation.assert_not_called()

    async def test_tool_error_does_not_echo_unexpected_internal_details(self):
        with (
            patch.object(
                service, "async_report", side_effect=RuntimeError("private detail")
            ),
            self.assertRaises(HomeAssistantError) as raised,
        ):
            await wallet_llm.WalletReportTool("wallet-a").async_call(
                self.hass,
                llm.ToolInput(tool_name="WalletReport", tool_args={}),
                self.context,
            )
        self.assertNotIn("private", str(raised.exception))

    async def test_missing_user_context_cannot_obtain_a_wallet_api(self):
        self.context.context = None
        with self.assertRaises(HomeAssistantError):
            await self.api.async_get_api_instance(self.context)
        self.hass.auth.async_get_user.assert_not_called()


if __name__ == "__main__":
    unittest.main()
