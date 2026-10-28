"""Access, provider selection and session isolation at the assistant boundary."""

from __future__ import annotations

import asyncio
import inspect
import sys
import types
import unittest
from copy import deepcopy
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from tests.test_panel_regressions import Connection

# isort: split
# The normal unit suite installs HA transport doubles before importing adapters.
from custom_components.my_wallet import assistant_api as api
from custom_components.my_wallet import assistant_service as service
from custom_components.my_wallet import const as c


def result(text="Verified explanation", conversation_id="ha-private-id"):
    return types.SimpleNamespace(
        conversation_id=conversation_id,
        as_dict=lambda: {
            "conversation_id": conversation_id,
            "response": {
                "response_type": "query_answer",
                "speech": {"plain": {"speech": text}},
            },
        },
    )


class AssistantAccessTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        data = {c.CONF_VALORS: [], c.CONF_BASE_CURRENCY: "EUR"}
        self.entry = types.SimpleNamespace(
            entry_id="wallet-a",
            domain=c.DOMAIN,
            data=data,
            runtime_data=types.SimpleNamespace(data=None, last_update_success=True),
        )
        self.user = types.SimpleNamespace(id="admin-a", is_admin=True, is_active=True)
        self.provider = types.SimpleNamespace(
            entry_id="provider",
            domain="openai_conversation",
            subentries={
                "chat": types.SimpleNamespace(
                    subentry_type="conversation",
                    data={"llm_hass_api": [service.wallet_api_id("wallet-a")]},
                )
            },
        )
        self.entries = {"wallet-a": self.entry, "provider": self.provider}
        self.hass = types.SimpleNamespace(
            data={},
            config_entries=types.SimpleNamespace(
                async_get_entry=lambda identifier: self.entries.get(identifier),
                async_update_entry=Mock(),
            ),
            auth=types.SimpleNamespace(
                async_get_user=AsyncMock(return_value=self.user)
            ),
        )
        self.registered = types.SimpleNamespace(
            entity_id="conversation.wallet",
            domain="conversation",
            disabled_by=None,
            platform="openai_conversation",
            config_entry_id="provider",
            config_subentry_id="chat",
        )
        registry = types.SimpleNamespace(
            async_get=lambda identifier: (
                self.registered if identifier == "conversation.wallet" else None
            ),
            entities={"conversation.wallet": self.registered},
        )
        self.agent = types.SimpleNamespace(subentry=self.provider.subentries["chat"])
        self.conversation = types.SimpleNamespace(
            async_converse=AsyncMock(return_value=result()),
            async_get_agent=Mock(return_value=self.agent),
            async_get_agent_info=Mock(
                return_value=types.SimpleNamespace(name="Wallet")
            ),
        )
        for package, name, value in (
            ("homeassistant.components", "conversation", self.conversation),
            (
                "homeassistant.helpers",
                "entity_registry",
                types.SimpleNamespace(async_get=lambda hass: registry),
            ),
        ):
            patcher = patch.object(sys.modules[package], name, value, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)

    def context(self, user_id="admin-a"):
        return types.SimpleNamespace(id=uuid4().hex, user_id=user_id)

    async def ask(self, **overrides):
        args = {
            "context": self.context(),
            "entry_id": "wallet-a",
            "agent_id": "conversation.wallet",
            "text": "Explain my wallet",
            "allow_external": True,
        }
        args.update(overrides)
        return await service.async_ask(self.hass, **args)

    async def test_every_endpoint_checks_admin_before_reading_any_input(self):
        for command in api.ASSISTANT_COMMANDS:
            with self.subTest(command=command.__name__):
                connection = Connection(admin=False)
                pending = command(self.hass, connection, {"id": 1})
                if inspect.isawaitable(pending):
                    await pending
                self.assertEqual(connection.errors[0][1], "unauthorized")
                self.assertFalse(connection.results)
        self.conversation.async_converse.assert_not_called()

    def test_wallet_lookup_rejects_nonwallet_config_entries(self):
        with self.assertRaisesRegex(service.AssistantError, "not_found"):
            service.wallet_request(self.hass, "provider")

    async def test_tools_reject_missing_inactive_or_nonadmin_user(self):
        for context, user in (
            (None, self.user),
            (self.context(), None),
            (self.context(), types.SimpleNamespace(is_admin=False, is_active=True)),
            (self.context(), types.SimpleNamespace(is_admin=True, is_active=False)),
        ):
            with self.subTest(context=context, user=user):
                self.hass.auth.async_get_user.return_value = user
                with self.assertRaisesRegex(service.AssistantError, "unauthorized"):
                    await service.authorized_tool_request(
                        self.hass, context, "wallet-a"
                    )

    async def test_tool_request_cannot_escape_the_bound_wallet_or_edited_snapshot(self):
        context = self.context()
        request = service.wallet_request(self.hass, "wallet-a")
        service.assistant_state(self.hass)["requests"][context.id] = {
            "user_id": "admin-a",
            "request": request,
            "results": [],
        }
        self.assertIs(
            await service.authorized_tool_request(self.hass, context, "wallet-a"),
            request,
        )
        with self.assertRaisesRegex(service.AssistantError, "unauthorized"):
            await service.authorized_tool_request(self.hass, context, "wallet-b")
        self.entry.data = dict(self.entry.data)
        with self.assertRaisesRegex(service.AssistantError, "entry_changed"):
            await service.authorized_tool_request(self.hass, context, "wallet-a")

    def test_only_explicit_wallet_only_agent_is_listed(self):
        self.assertEqual(
            len(service.available_agents(self.hass, "wallet-a")["agents"]), 1
        )
        for selected in (
            None,
            "assist",
            ["assist", "my_wallet_wallet-a"],
            ["my_wallet_wallet-b"],
            ["my_wallet_wallet-a", "other"],
        ):
            with self.subTest(selected=selected):
                self.provider.subentries["chat"].data["llm_hass_api"] = selected
                self.assertEqual(
                    service.available_agents(self.hass, "wallet-a")["agents"], []
                )

    def test_provider_reload_and_unknown_provider_are_not_assumed_safe(self):
        self.agent.subentry = types.SimpleNamespace(data={"llm_hass_api": ["assist"]})
        self.assertEqual(service.available_agents(self.hass, "wallet-a")["agents"], [])
        self.agent.subentry = self.provider.subentries["chat"]
        self.registered.platform = self.provider.domain = "custom_agent"
        self.assertEqual(service.available_agents(self.hass, "wallet-a")["agents"], [])

    async def test_consent_and_invalid_question_prevent_provider_calls(self):
        for args, code in (
            ({"allow_external": False}, "external_consent_required"),
            ({"text": " "}, "invalid_question"),
            ({"text": "x" * 4001}, "invalid_question"),
        ):
            with self.assertRaisesRegex(service.AssistantError, code):
                await self.ask(**args)
        self.conversation.async_converse.assert_not_called()

    async def test_session_is_opaque_and_scoped_to_user_wallet_and_agent(self):
        first = await self.ask()
        self.assertNotIn("ha-private-id", repr(first))
        self.assertIsNone(
            self.conversation.async_converse.call_args.kwargs["conversation_id"]
        )
        await self.ask(session_id=first["session_id"])
        self.assertEqual(
            self.conversation.async_converse.call_args.kwargs["conversation_id"],
            "ha-private-id",
        )
        with self.assertRaisesRegex(
            service.AssistantError, "assistant_session_expired"
        ):
            await self.ask(
                context=self.context("admin-b"), session_id=first["session_id"]
            )
        self.assertEqual(self.conversation.async_converse.await_count, 2)
        with self.assertRaisesRegex(
            service.AssistantError, "assistant_session_expired"
        ):
            service._open_session(
                self.hass,
                user_id="admin-a",
                entry_id="wallet-b",
                agent_id="conversation.wallet",
                session_id=first["session_id"],
            )

    async def test_parallel_turns_on_one_session_do_not_interleave(self):
        first = await self.ask()
        entered, release = asyncio.Event(), asyncio.Event()

        async def waiting(**kwargs):
            entered.set()
            await release.wait()
            return result()

        self.conversation.async_converse.side_effect = waiting
        pending = asyncio.create_task(self.ask(session_id=first["session_id"]))
        await entered.wait()
        try:
            with self.assertRaisesRegex(service.AssistantError, "assistant_busy"):
                await self.ask(session_id=first["session_id"])
        finally:
            release.set()
            await pending
        self.assertEqual(self.conversation.async_converse.await_count, 2)

    async def test_failure_discards_potentially_advanced_provider_conversation(self):
        first = await self.ask()
        self.conversation.async_converse.side_effect = RuntimeError("provider detail")
        with self.assertRaises(RuntimeError):
            await self.ask(session_id=first["session_id"])
        self.assertNotIn(
            first["session_id"], service.assistant_state(self.hass)["sessions"]
        )
        self.assertEqual(service.assistant_state(self.hass)["requests"], {})

    async def test_generated_prose_cannot_replace_authoritative_tool_cards_or_write(
        self,
    ):
        before = deepcopy(self.entry.data)

        async def generated(**kwargs):
            service.remember_tool_result(
                self.hass, kwargs["context"], "report", {"facts": {"total": 123}}
            )
            return result('<img src=x onerror="save()">Your value is 999')

        self.conversation.async_converse.side_effect = generated
        answer = await self.ask()
        self.assertEqual(answer["report"], {"facts": {"total": 123}})
        self.assertEqual(len(answer["results"]), 1)
        self.assertIn("<img", answer["text"])
        self.assertEqual(self.entry.data, before)
        self.hass.config_entries.async_update_entry.assert_not_called()

    async def test_wallet_change_while_waiting_rejects_the_answer(self):
        async def edited(**kwargs):
            self.entry.data = dict(self.entry.data)
            return result()

        self.conversation.async_converse.side_effect = edited
        with self.assertRaisesRegex(service.AssistantError, "entry_changed"):
            await self.ask()
        self.assertEqual(service.assistant_state(self.hass)["sessions"], {})

    async def test_endpoint_hides_arbitrary_provider_exception_details(self):
        connection = Connection()
        connection.context = lambda msg: self.context()
        with patch.object(
            service, "async_ask", side_effect=RuntimeError("secret provider detail")
        ):
            await api.ws_assistant_ask(
                self.hass,
                connection,
                {
                    "id": 1,
                    "entry_id": "wallet-a",
                    "agent_id": "conversation.wallet",
                    "text": "Explain",
                    "allow_external": True,
                },
            )
        self.assertEqual(connection.errors[0][1], "assistant_provider_failed")
        self.assertNotIn("secret", repr(connection.errors))

    async def test_history_failure_retains_current_facts_and_is_cached(self):
        from custom_components.my_wallet import history

        request = service.wallet_request(self.hass, "wallet-a")
        with (
            patch.object(
                history, "async_history", side_effect=RuntimeError("offline")
            ) as fetch,
            patch.object(
                service, "build_wallet_insights", return_value={"facts": {"cash": 0}}
            ) as build,
        ):
            self.assertEqual(
                await service.async_report(self.hass, request), {"facts": {"cash": 0}}
            )
            await service.async_report(self.hass, request)
        self.assertEqual(fetch.await_count, 1)
        self.assertIsNone(build.call_args.kwargs["history"])

    def test_scenario_cannot_smuggle_write_operations(self):
        request = service.wallet_request(self.hass, "wallet-a")
        with self.assertRaisesRegex(service.AssistantError, "invalid_scenario"):
            service.scenario_result(request, {"save": True, "contributions": []})
        self.hass.config_entries.async_update_entry.assert_not_called()

    async def test_unload_revokes_sessions_and_history(self):
        answer = await self.ask()
        service.assistant_state(self.hass)["history"]["wallet-a"] = {}
        service.clear_wallet_assistant(self.hass, "wallet-a")
        self.assertNotIn(
            answer["session_id"], service.assistant_state(self.hass)["sessions"]
        )
        self.assertNotIn("wallet-a", service.assistant_state(self.hass)["history"])

    async def test_unload_during_provider_call_rejects_its_late_answer(self):
        async def unloading(**kwargs):
            service.clear_wallet_assistant(self.hass, "wallet-a")
            return result()

        self.conversation.async_converse.side_effect = unloading
        with self.assertRaisesRegex(
            service.AssistantError, "assistant_session_expired"
        ):
            await self.ask()
        self.assertEqual(service.assistant_state(self.hass)["requests"], {})

    async def test_new_chat_retires_only_an_idle_session_of_the_same_user(self):
        with patch.object(service, "MAX_USER_SESSIONS", 2):
            first = await self.ask()
            second = await self.ask()
            sessions = service.assistant_state(self.hass)["sessions"]
            sessions[first["session_id"]]["busy"] = True
            third = await self.ask()
        self.assertIn(first["session_id"], sessions)
        self.assertNotIn(second["session_id"], sessions)
        self.assertIn(third["session_id"], sessions)
        self.assertEqual(len(sessions), 2)

    async def test_session_limit_never_evicts_someone_elses_session(self):
        first = await self.ask()
        with (
            patch.object(service, "MAX_SESSIONS", 1),
            self.assertRaisesRegex(service.AssistantError, "assistant_session_limit"),
        ):
            await self.ask(context=self.context("admin-b"))
        self.assertIn(
            first["session_id"], service.assistant_state(self.hass)["sessions"]
        )


if __name__ == "__main__":
    unittest.main()
