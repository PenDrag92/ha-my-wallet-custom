"""Authenticated, automatically registered wallet history and import panel."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
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
from .backup import (
    create_backup,
    is_backup,
    prepare_backup,
)
from .contributions import (
    all_lots,
    invested_total,
    lot_metrics,
    lots_for_symbol,
    money_weighted_return,
    opening_balance_conflicts,
    xirr,
)
from .corrections import correction_choices, prepare_correction
from .dividends import (
    attributed_dividend_flows,
    cash_balance,
    dividend_total,
    dividends_from_data,
)
from .followup_import import (
    add_initial_import_metadata,
    async_prepare_followup,
    has_import,
)
from .history import async_history, ledger_rows
from .history_import import IMPORT_BATCH, async_prepare_import

_LOGGER = logging.getLogger(__name__)
_STATE = "my_wallet_panel"
_MAX_DOCUMENT_BYTES = 2_000_000
_MAX_ALIAS_LENGTH = 80


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
        has_import(entry.data, batch) for entry in _entries(hass)
    )


def consume_import(hass, token: str, user_id: str):
    """Consume only a server-prepared preview, never arbitrary flow input."""
    previews = _state(hass)["previews"]
    preview = previews.get(token)
    if (
        preview is None
        or preview.get("kind", "new") != "new"
        or preview["user_id"] != user_id
        or monotonic() > preview["expires"]
    ):
        raise ValueError("import_expired")
    batch = preview["data"].get(IMPORT_BATCH)
    if batch is not None and _batch_exists(hass, batch):
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
    for command in (
        ws_wallets,
        ws_position_aliases,
        ws_backup,
        ws_history,
        ws_import_preview,
        ws_import_commit,
        ws_correction_preview,
        ws_correction_commit,
    ):
        websocket_api.async_register_command(hass, command)
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path="my-wallet",
        webcomponent_name="my-wallet-panel",
        sidebar_title="My Wallet",
        sidebar_icon="mdi:chart-timeline-variant",
        module_url="/my_wallet_static/my-wallet-panel.js?v=1.5.0",
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
        invested = invested_total(entry.data, through=today)
        total = (
            current.total
            if current is not None and getattr(coordinator, "last_update_success", True)
            else None
        )
        positions = []
        included = {}
        costs = {}
        for lot in all_lots(entry.data, through=today):
            symbol = lot[c.LOT_SYMBOL]
            costs[symbol] = costs.get(symbol, 0.0) + lot[c.LOT_AMOUNT]
            if lot[c.LOT_INCLUDED_IN_OPENING]:
                included[symbol] = included.get(symbol, 0.0) + lot[c.LOT_UNITS]
        events = ledger_rows(entry.data)
        has_unknown_opening = any(
            abs(included.get(valor[c.VALOR_SYMBOL], 0.0) - float(valor[c.VALOR_AMOUNT]))
            > 1e-8
            for valor in entry.data[c.CONF_VALORS]
        ) or any(row["type"] == "opening" and row["date"] is None for row in events)
        dated_events = [
            row["date"]
            for row in events
            if row["date"] and row["date"] <= today.isoformat()
        ]
        start_date = (
            min(dated_events) if dated_events and not has_unknown_opening else None
        )
        income = {}
        for dividend in dividends_from_data(entry.data):
            symbol = dividend.get(c.DIVIDEND_SYMBOL)
            if symbol:
                income[symbol] = income.get(symbol, 0.0) + dividend[c.DIVIDEND_AMOUNT]
        for valor in entry.data[c.CONF_VALORS]:
            symbol = valor[c.VALOR_SYMBOL]
            item = current.valors.get(symbol) if current is not None else None
            value = item.value if item is not None else None
            opening = float(valor[c.VALOR_AMOUNT])
            cost_complete = abs(included.get(symbol, 0.0) - opening) <= 1e-8
            symbol_lots = lots_for_symbol(entry.data, symbol, through=today)
            position_start = (
                min(lot[c.LOT_DATE] for lot in symbol_lots)
                if symbol_lots and cost_complete
                else None
            )
            profit = (
                value + income.get(symbol, 0.0) - costs.get(symbol, 0.0)
                if value is not None and cost_complete
                else None
            )
            details = []
            dividend_flows = attributed_dividend_flows(
                entry.data, symbol=symbol, opening_units=opening, through=today
            )
            current_base_price = (
                item.quote.price * item.fx_rate
                if item is not None and item.available
                else None
            )
            for lot in symbol_lots:
                income_flows = dividend_flows.get(lot[c.LOT_ID], [])
                lot_income = sum(amount for _, amount in income_flows)
                metrics = (
                    lot_metrics(lot, current_base_price, today, lot_income)
                    if current_base_price is not None
                    else None
                )
                annualized = (
                    xirr(
                        [
                            (
                                date.fromisoformat(lot[c.LOT_DATE]),
                                -float(lot[c.LOT_AMOUNT]),
                            ),
                            *income_flows,
                            (today, float(metrics["current_value"])),
                        ]
                    )
                    if metrics is not None
                    else None
                )
                details.append(
                    {
                        "id": lot[c.LOT_ID],
                        "date": lot[c.LOT_DATE],
                        "price_date": lot.get("price_date", lot[c.LOT_DATE]),
                        "amount": lot[c.LOT_AMOUNT],
                        "units": lot[c.LOT_UNITS],
                        "purchase_price": lot[c.LOT_AMOUNT] / lot[c.LOT_UNITS],
                        "current_value": metrics["current_value"]
                        if metrics is not None
                        else None,
                        "dividends": lot_income,
                        "profit": metrics["profit"] if metrics is not None else None,
                        "performance": metrics["performance_pct"]
                        if metrics is not None
                        else None,
                        "annualized_performance": annualized * 100
                        if annualized is not None
                        else None,
                        "included_in_opening": lot[c.LOT_INCLUDED_IN_OPENING],
                        "estimated": lot[c.LOT_ESTIMATED],
                    }
                )
            positions.append(
                {
                    "symbol": symbol,
                    "alias": valor.get(c.VALOR_ALIAS),
                    "units": item.amount if item is not None else None,
                    "price": item.quote.price * item.fx_rate
                    if item is not None and item.available
                    else None,
                    "value": value,
                    "cost": costs.get(symbol, 0.0) if cost_complete else None,
                    "dividends": income.get(symbol, 0.0),
                    "profit": profit,
                    "performance": profit / costs[symbol] * 100
                    if profit is not None and costs.get(symbol, 0.0) > 0
                    else None,
                    "share": value / total * 100
                    if value is not None and total and total > 0
                    else None,
                    "target": valor.get(c.VALOR_TARGET_SHARE),
                    "cost_complete": cost_complete,
                    "start_date": position_start,
                    "lots": details,
                }
            )
        profit = (
            total - invested if total is not None and invested is not None else None
        )
        wallets.append(
            {
                "entry_id": entry.entry_id,
                "name": entry.title or entry.data.get(c.CONF_WALLET_NAME, "My Wallet"),
                "currency": entry.data[c.CONF_BASE_CURRENCY],
                "start_date": start_date,
                "invested": invested,
                "cash": cash_balance(entry.data, through=today),
                "dividends": dividend_total(entry.data, through=today),
                "total": total,
                "profit": profit,
                "performance": profit / invested * 100
                if profit is not None and invested and invested > 0
                else None,
                "money_weighted_return": money_weighted_return(entry.data, total, today)
                if total is not None
                else None,
                "positions": positions,
                "correction_choices": correction_choices(entry.data, today=today),
                "pending": current.pending_executions if current is not None else [],
                "plans": entry.data.get(c.CONF_SAVINGS_PLANS, []),
                "opening_conflicts": opening_balance_conflicts(entry.data),
            }
        )
    connection.send_result(msg["id"], {"wallets": wallets})


def _normalize_alias(value) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid_alias")
    alias = " ".join(value.split())
    if len(alias) > _MAX_ALIAS_LENGTH:
        raise ValueError("invalid_alias")
    return alias


@websocket_api.websocket_command(
    {
        vol.Required("type"): "my_wallet/position_aliases",
        vol.Required("entry_id"): str,
        vol.Required("aliases"): dict,
    }
)
@callback
def ws_position_aliases(hass, connection, msg):
    """Persist optional display names without changing financial identifiers."""
    if not _admin(connection, msg):
        return
    entry = next(
        (item for item in _entries(hass) if item.entry_id == msg["entry_id"]), None
    )
    if entry is None:
        connection.send_error(msg["id"], "not_found", "Wallet not found")
        return
    symbols = {item[c.VALOR_SYMBOL] for item in entry.data[c.CONF_VALORS]}
    raw_aliases = msg["aliases"]
    if any(
        not isinstance(symbol, str) or symbol not in symbols for symbol in raw_aliases
    ):
        connection.send_error(msg["id"], "invalid_alias", "Unknown position")
        return
    try:
        aliases = {
            symbol: _normalize_alias(value) for symbol, value in raw_aliases.items()
        }
    except ValueError:
        connection.send_error(
            msg["id"], "invalid_alias", "Aliases must be at most 80 characters"
        )
        return

    valors = []
    for current in entry.data[c.CONF_VALORS]:
        item = dict(current)
        symbol = item[c.VALOR_SYMBOL]
        if symbol in aliases:
            if aliases[symbol]:
                item[c.VALOR_ALIAS] = aliases[symbol]
            else:
                item.pop(c.VALOR_ALIAS, None)
        valors.append(item)
    data = {**entry.data, c.CONF_VALORS: valors}
    if data != entry.data:
        hass.config_entries.async_update_entry(entry, data=data)
    connection.send_result(
        msg["id"],
        {
            "entry_id": entry.entry_id,
            "aliases": {
                item[c.VALOR_SYMBOL]: item.get(c.VALOR_ALIAS, "") for item in valors
            },
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "my_wallet/backup",
        vol.Required("entry_id"): str,
    }
)
@callback
def ws_backup(hass, connection, msg):
    """Return a portable backup only to an authenticated administrator."""
    if not _admin(connection, msg):
        return
    entry = next(
        (item for item in _entries(hass) if item.entry_id == msg["entry_id"]), None
    )
    if entry is None:
        connection.send_error(msg["id"], "not_found", "Wallet not found")
        return
    document = create_backup(
        entry.data,
        title=entry.title or entry.data.get(c.CONF_WALLET_NAME, "My Wallet"),
        created_at=dt_util.now(),
    )
    encoded = json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(encoded) > _MAX_DOCUMENT_BYTES:
        connection.send_error(msg["id"], "backup_too_large", "Backup exceeds 2 MB")
        return
    connection.send_result(msg["id"], {"document": document})


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
    {
        vol.Required("type"): "my_wallet/import_preview",
        vol.Required("document"): dict,
        vol.Optional("entry_id"): str,
        vol.Optional("decisions", default={}): dict,
    }
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
    target = next(
        (entry for entry in _entries(hass) if entry.entry_id == msg.get("entry_id")),
        None,
    )
    if msg.get("entry_id") and target is None:
        connection.send_error(msg["id"], "not_found", "Wallet not found")
        return
    if target is None and _batch_exists(hass, document.get("batch_id")):
        connection.send_error(
            msg["id"], "already_imported", "This statement was already imported"
        )
        return
    try:
        async with asyncio.timeout(90):
            today = dt_util.now().date()
            snapshot = target.data if target is not None else None
            if is_backup(document):
                if target is not None:
                    raise ValueError("backup_new_only")
                data, summary = prepare_backup(document, today=today)
            elif target is None:
                data, summary = await async_prepare_import(
                    document, session=async_get_clientsession(hass), today=today
                )
                if data is not None:
                    data = add_initial_import_metadata(document, data, today=today)
            else:
                data, summary = await async_prepare_followup(
                    document,
                    snapshot,
                    session=async_get_clientsession(hass),
                    today=today,
                    decisions=msg["decisions"],
                )
                if target.data is not snapshot:
                    raise ValueError("entry_changed")
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
            "kind": "followup" if target is not None else "new",
            "entry_id": target.entry_id if target is not None else None,
            "snapshot": snapshot,
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
    if preview.get("kind") == "followup":
        entry = next(
            (item for item in _entries(hass) if item.entry_id == preview["entry_id"]),
            None,
        )
        if entry is None or entry.data is not preview["snapshot"]:
            connection.send_error(
                msg["id"], "entry_changed", "Wallet changed; preview again"
            )
            return
        _state(hass)["previews"].pop(msg["token"], None)
        hass.config_entries.async_update_entry(entry, data=preview["data"])
        hass.config_entries.async_schedule_reload(entry.entry_id)
        _state(hass)["cache"].pop(entry.entry_id, None)
        connection.send_result(msg["id"], {"entry_id": entry.entry_id})
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


@websocket_api.websocket_command(
    {
        vol.Required("type"): "my_wallet/correction_preview",
        vol.Required("entry_id"): str,
        vol.Required("correction"): dict,
    }
)
@callback
def ws_correction_preview(hass, connection, msg):
    if not _admin(connection, msg):
        return
    entry = next(
        (item for item in _entries(hass) if item.entry_id == msg["entry_id"]), None
    )
    if entry is None:
        connection.send_error(msg["id"], "not_found", "Wallet not found")
        return
    snapshot = entry.data
    try:
        data, summary = prepare_correction(
            snapshot, msg["correction"], today=dt_util.now().date()
        )
    except (KeyError, TypeError, ValueError, OverflowError) as err:
        code = str(err) if str(err).replace("_", "").isalpha() else "invalid_correction"
        connection.send_error(msg["id"], code, "Unit correction validation failed")
        return
    token = uuid4().hex
    _state(hass)["previews"][token] = {
        "user_id": connection.user.id,
        "expires": monotonic() + 600,
        "data": data,
        "kind": "correction",
        "entry_id": entry.entry_id,
        "snapshot": snapshot,
    }
    connection.send_result(msg["id"], {"token": token, "summary": summary})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "my_wallet/correction_commit",
        vol.Required("token"): str,
        vol.Required("confirm"): bool,
    }
)
@callback
def ws_correction_commit(hass, connection, msg):
    if not _admin(connection, msg):
        return
    preview = _state(hass)["previews"].get(msg["token"])
    if not msg["confirm"]:
        connection.send_error(
            msg["id"], "confirmation_required", "Confirmation required"
        )
        return
    if (
        preview is None
        or preview.get("kind") != "correction"
        or preview["user_id"] != connection.user.id
        or preview["expires"] < monotonic()
    ):
        connection.send_error(msg["id"], "import_expired", "Prepare a fresh preview")
        return
    entry = next(
        (item for item in _entries(hass) if item.entry_id == preview["entry_id"]), None
    )
    if entry is None or entry.data is not preview["snapshot"]:
        connection.send_error(
            msg["id"], "entry_changed", "Wallet changed; preview again"
        )
        return
    _state(hass)["previews"].pop(msg["token"], None)
    hass.config_entries.async_update_entry(entry, data=preview["data"])
    hass.config_entries.async_schedule_reload(entry.entry_id)
    _state(hass)["cache"].pop(entry.entry_id, None)
    connection.send_result(msg["id"], {"entry_id": entry.entry_id})
