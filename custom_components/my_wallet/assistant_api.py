"""Authenticated WebSocket transport for deterministic and AI wallet assistance."""

from __future__ import annotations

import re

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import callback

from . import assistant_service as service


def _admin(connection, msg) -> bool:
    if connection.user is None or not connection.user.is_admin:
        connection.send_error(
            msg["id"], "unauthorized", "Administrator access required"
        )
        return False
    return True


def _failure(connection, msg, error, *, default="invalid_assistant_request"):
    code = str(error)
    if not isinstance(error, ValueError) or not re.fullmatch(r"[a-z_]{1,64}", code):
        code = default
    connection.send_error(
        msg["id"], code, "Wallet assistant request could not complete"
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "my_wallet/assistant/report",
        vol.Required("entry_id"): str,
        vol.Optional("month"): str,
    }
)
@websocket_api.async_response
async def ws_assistant_report(hass, connection, msg):
    if not _admin(connection, msg):
        return
    try:
        request = service.wallet_request(hass, msg["entry_id"])
        result = await service.async_report(hass, request, month=msg.get("month"))
    except Exception as err:
        _failure(connection, msg, err)
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "my_wallet/assistant/scenario",
        vol.Required("entry_id"): str,
        vol.Required("scenario"): dict,
    }
)
@callback
def ws_assistant_scenario(hass, connection, msg):
    if not _admin(connection, msg):
        return
    try:
        result = service.scenario_result(
            service.wallet_request(hass, msg["entry_id"]), msg["scenario"]
        )
    except Exception as err:
        _failure(connection, msg, err)
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "my_wallet/assistant/allocation",
        vol.Required("entry_id"): str,
        vol.Required("amount"): vol.Any(int, float),
        vol.Optional("use_cash", default=False): bool,
    }
)
@callback
def ws_assistant_allocation(hass, connection, msg):
    if not _admin(connection, msg):
        return
    try:
        result = service.allocation_result(
            service.wallet_request(hass, msg["entry_id"]),
            amount=msg["amount"],
            use_cash=msg.get("use_cash", False),
        )
    except Exception as err:
        _failure(connection, msg, err)
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "my_wallet/assistant/agents",
        vol.Required("entry_id"): str,
    }
)
@callback
def ws_assistant_agents(hass, connection, msg):
    if not _admin(connection, msg):
        return
    try:
        result = service.available_agents(hass, msg["entry_id"])
    except Exception as err:
        _failure(connection, msg, err)
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "my_wallet/assistant/ask",
        vol.Required("entry_id"): str,
        vol.Required("agent_id"): str,
        vol.Required("text"): str,
        vol.Optional("session_id"): str,
        vol.Optional("language"): str,
        vol.Optional("allow_external", default=False): bool,
    }
)
@websocket_api.async_response
async def ws_assistant_ask(hass, connection, msg):
    if not _admin(connection, msg):
        return
    try:
        result = await service.async_ask(
            hass,
            context=connection.context(msg),
            entry_id=msg["entry_id"],
            agent_id=msg["agent_id"],
            text=msg["text"],
            session_id=msg.get("session_id"),
            language=msg.get("language"),
            allow_external=msg.get("allow_external", False),
        )
    except Exception as err:
        _failure(connection, msg, err, default="assistant_provider_failed")
        return
    connection.send_result(msg["id"], result)


ASSISTANT_COMMANDS = (
    ws_assistant_report,
    ws_assistant_scenario,
    ws_assistant_allocation,
    ws_assistant_agents,
    ws_assistant_ask,
)


@callback
def register_assistant_commands(hass):
    """Register once, alongside the existing panel commands."""
    for command in ASSISTANT_COMMANDS:
        websocket_api.async_register_command(hass, command)
