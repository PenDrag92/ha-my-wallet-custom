"""Authenticated, automatically registered wallet history and import panel."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from time import monotonic
from uuid import uuid4

import voluptuous as vol
from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from . import const as c
from .contributions import invested_total, opening_balance_conflicts
from .dividends import cash_balance, dividend_total
from .history import async_history
from .history_import import IMPORT_BATCH, async_prepare_import

_LOGGER = logging.getLogger(__name__)
_STATE = "my_wallet_panel"
_MAX_DOCUMENT_BYTES = 2_000_000


def _state(hass):
    return hass.data.setdefault(_STATE, {"cache": {}, "locks": {}, "previews": {}})


def _admin(connection, msg) -> bool:
    if connection.user is None or not connection.user.is_admin:
        connection.send_error(
            msg["id"], "unauthorized", "Administrator access required"
        )
        return False
    return True


def _entries(hass):
    return [
        entry
        for entry in hass.config_entries.async_entries(c.DOMAIN)
        if c.CONF_VALORS in entry.data
    ]


def _batch_exists(hass, batch):
    return batch is not None and any(
        entry.data.get(IMPORT_BATCH) == batch for entry in _entries(hass)
    )


def consume_import(hass, token: str, user_id: str):
    """Consume only a server-prepared preview, never arbitrary flow input."""
    previews = _state(hass)["previews"]
    preview = previews.get(token)
    if (
        preview is None
        or preview["user_id"] != user_id
        or monotonic() > preview["expires"]
    ):
        raise ValueError("import_expired")
    if _batch_exists(hass, preview["data"][IMPORT_BATCH]):
        raise ValueError("already_imported")
    previews.pop(token)
    return preview["data"]


async def async_setup_panel(hass):
    state = _state(hass)
    if state.get("registered"):
        return
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                "/my_wallet_static", str(Path(__file__).parent / "frontend"), False
            )
        ]
    )
    for command in (ws_wallets, ws_history, ws_import_preview, ws_import_commit):
        websocket_api.async_register_command(hass, command)
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path="my-wallet",
        webcomponent_name="my-wallet-panel",
        sidebar_title="My Wallet",
        sidebar_icon="mdi:chart-timeline-variant",
        module_url="/my_wallet_static/my-wallet-panel.js?v=1.3.4",
        embed_iframe=False,
        require_admin=True,
    )
    state["registered"] = True


@websocket_api.websocket_command({vol.Required("type"): "my_wallet/wallets"})
@callback
def ws_wallets(hass, connection, msg):
    if not _admin(connection, msg):
        return
    today = dt_util.now().date()
    wallets = []
    for entry in _entries(hass):
        coordinator = getattr(entry, "runtime_data", None)
        current = getattr(coordinator, "data", None)
        wallets.append(
            {
                "entry_id": entry.entry_id,
                "name": entry.data.get(c.CONF_WALLET_NAME, entry.title),
                "currency": entry.data[c.CONF_BASE_CURRENCY],
                "invested": invested_total(entry.data, through=today),
                "cash": cash_balance(entry.data, through=today),
                "dividends": dividend_total(entry.data, through=today),
                "total": current.total
                if current is not None
                and getattr(coordinator, "last_update_success", True)
                else None,
                "pending": current.pending_executions if current is not None else [],
                "plans": entry.data.get(c.CONF_SAVINGS_PLANS, []),
                "opening_conflicts": opening_balance_conflicts(entry.data),
            }
        )
    connection.send_result(msg["id"], {"wallets": wallets})


@websocket_api.websocket_command(
    {vol.Required("type"): "my_wallet/history", vol.Required("entry_id"): str}
)
@websocket_api.async_response
async def ws_history(hass, connection, msg):
    if not _admin(connection, msg):
        return
    entry = next(
        (entry for entry in _entries(hass) if entry.entry_id == msg["entry_id"]), None
    )
    if entry is None:
        connection.send_error(msg["id"], "not_found", "Wallet not found")
        return
    state = _state(hass)
    async with state["locks"].setdefault(entry.entry_id, asyncio.Lock()):
        snapshot = entry.data
        today = dt_util.now().date()
        cached = state["cache"].get(entry.entry_id)
        if (
            cached
            and cached["snapshot"] is snapshot
            and cached["day"] == today
            and cached["expires"] > monotonic()
        ):
            result = cached["result"]
        else:
            try:
                async with asyncio.timeout(90):
                    result = await async_history(
                        snapshot, session=async_get_clientsession(hass), today=today
                    )
            except Exception:
                _LOGGER.exception("Could not reconstruct wallet history")
                connection.send_error(
                    msg["id"], "history_failed", "History could not be loaded"
                )
                return
            if entry.data is not snapshot:
                connection.send_error(
                    msg["id"], "entry_changed", "Wallet changed; reload history"
                )
                return
            state["cache"][entry.entry_id] = {
                "snapshot": snapshot,
                "day": today,
                "expires": monotonic() + 300,
                "result": result,
            }
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {vol.Required("type"): "my_wallet/import_preview", vol.Required("document"): dict}
)
@websocket_api.async_response
async def ws_import_preview(hass, connection, msg):
    if not _admin(connection, msg):
        return
    document = msg["document"]
    if (
        len(json.dumps(document, ensure_ascii=False).encode("utf-8"))
        > _MAX_DOCUMENT_BYTES
    ):
        connection.send_error(msg["id"], "import_too_large", "Import file exceeds 2 MB")
        return
    if _batch_exists(hass, document.get("batch_id")):
        connection.send_error(
            msg["id"], "already_imported", "This statement was already imported"
        )
        return
    try:
        async with asyncio.timeout(90):
            data, summary = await async_prepare_import(
                document,
                session=async_get_clientsession(hass),
                today=dt_util.now().date(),
            )
    except (ValueError, KeyError, TypeError, OverflowError) as err:
        code = str(err) if str(err).replace("_", "").isalpha() else "invalid_import"
        connection.send_error(
            msg["id"], code, "Statement validation failed; no data was written"
        )
        return
    except Exception:
        _LOGGER.exception("Could not prepare a wallet import")
        connection.send_error(
            msg["id"], "import_failed", "Import preparation failed; no data was written"
        )
        return
    state = _state(hass)
    state["previews"] = {
        key: value
        for key, value in state["previews"].items()
        if value["expires"] > monotonic() and value["user_id"] != connection.user.id
    }
    token = None
    if data is not None:
        token = uuid4().hex
        state["previews"][token] = {
            "user_id": connection.user.id,
            "expires": monotonic() + 600,
            "data": data,
        }
    connection.send_result(msg["id"], {"token": token, "summary": summary})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "my_wallet/import_commit",
        vol.Required("token"): str,
        vol.Required("confirm"): bool,
    }
)
@websocket_api.async_response
async def ws_import_commit(hass, connection, msg):
    if not _admin(connection, msg):
        return
    if not msg["confirm"]:
        connection.send_error(
            msg["id"], "confirmation_required", "Explicit import confirmation required"
        )
        return
    preview = _state(hass)["previews"].get(msg["token"])
    if (
        preview is None
        or preview["user_id"] != connection.user.id
        or preview["expires"] < monotonic()
    ):
        connection.send_error(
            msg["id"], "import_expired", "Prepare a fresh import preview"
        )
        return
    result = await hass.config_entries.flow.async_init(
        c.DOMAIN,
        context={"source": "import"},
        data={"token": msg["token"], "user_id": connection.user.id},
    )
    if result["type"] != "create_entry":
        connection.send_error(
            msg["id"],
            result.get("reason", "import_failed"),
            "The import did not create a wallet",
        )
        return
    connection.send_result(msg["id"], {"entry_id": result["result"].entry_id})
