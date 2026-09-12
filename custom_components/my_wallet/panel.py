"""Authenticated, automatically registered wallet history and import panel."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import replace
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
    opening_balance_conflicts,
)
from .corrections import correction_choices, position_units, prepare_correction
from .dividends import (
    cash_balance,
)
from .followup_import import (
    add_initial_import_metadata,
    async_prepare_followup,
    has_import,
)
from .history import async_history
from .history_import import IMPORT_BATCH, async_prepare_import
from .inflation import (
    expected_annual_inflation,
    future_inflation_factor,
)
from .models import ValorData
from .planning import change_planned_deposit, planned_deposit_summaries
from .recorded_history import (
    PERIOD_DAYS,
    async_recorded_components,
    async_recorded_history,
)
from .store import commit_wallet_change
from .target import (
    FORECAST_YEARS,
    MAX_FORECAST_YEARS,
    MIN_FORECAST_YEARS,
    add_years,
    documented_wallet_start_date,
    target_allocation_forecast,
    target_deviation,
    target_projection,
)
from .valuation import position_valuation, wallet_valuation

_LOGGER = logging.getLogger(__name__)
_STATE = "my_wallet_panel"
_MAX_DOCUMENT_BYTES = 2_000_000
_MAX_ALIAS_LENGTH = 80


def _forecast_years(value) -> int:
    """Validate the bounded custom dashboard forecast horizon."""
    try:
        number = float(value)
    except (TypeError, ValueError) as err:
        raise vol.Invalid("forecast_years must be an integer") from err
    if isinstance(value, bool) or not number.is_integer():
        raise vol.Invalid("forecast_years must be an integer")
    years = int(number)
    if not MIN_FORECAST_YEARS <= years <= MAX_FORECAST_YEARS:
        raise vol.Invalid("forecast_years must be between 1 and 50")
    return years


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
        ws_planned_deposit,
        ws_backup,
        ws_history,
        ws_recorded_history,
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
        module_url="/my_wallet_static/my-wallet-panel.js?v=1.12.0",
        embed_iframe=False,
        require_admin=True,
    )
    state["registered"] = True


def _wallet_with_saved_units(data, current, *, today):
    """Value saved holdings using cached quotes while a reload is still pending."""
    if current is None:
        return None
    valors = {}
    for valor in data[c.CONF_VALORS]:
        symbol = valor[c.VALOR_SYMBOL]
        previous = current.valors.get(symbol) or ValorData(symbol, 0, 0)
        valors[symbol] = replace(
            previous,
            amount=position_units(data, symbol, today),
            opening_amount=float(valor[c.VALOR_AMOUNT]),
            target_share=valor.get(c.VALOR_TARGET_SHARE),
        )
    return replace(
        current, valors=valors, cash_balance=cash_balance(data, through=today)
    )


def _position_payload(data, configured, current, *, today, total):
    """Serialize shared full-precision results for the panel contract."""
    symbol = configured[c.VALOR_SYMBOL]
    valor = current.valors.get(symbol) if current is not None else None
    result = position_valuation(
        data,
        symbol,
        today=today,
        valor=valor,
        inflation=current.inflation if current is not None else None,
    )
    value = result.nominal.value
    return {
        "symbol": symbol,
        "alias": configured.get(c.VALOR_ALIAS),
        "units": position_units(data, symbol, today),
        "price": valor.quote.price * valor.fx_rate
        if valor is not None and valor.available
        else None,
        "value": value,
        "cost": result.nominal.cost,
        "dividends": result.nominal.income,
        "profit": result.nominal.profit,
        "performance": result.nominal.percentage,
        "real_cost": result.real.cost,
        "real_dividends": result.real.income,
        "real_profit": result.real.profit,
        "real_performance": result.real.percentage,
        "share": value / total * 100
        if value is not None and total and total > 0
        else None,
        "target": configured.get(c.VALOR_TARGET_SHARE),
        "cost_complete": result.cost_complete,
        "start_date": result.start_date,
        "lots": [_lot_payload(item) for item in result.lots],
    }


def _lot_payload(item):
    lot = item.lot
    return {
        "id": lot[c.LOT_ID],
        "date": lot[c.LOT_DATE],
        "price_date": lot.get("price_date", lot[c.LOT_DATE]),
        "amount": lot[c.LOT_AMOUNT],
        "units": lot[c.LOT_UNITS],
        "purchase_price": lot[c.LOT_AMOUNT] / lot[c.LOT_UNITS],
        "current_value": item.nominal.value,
        "dividends": item.nominal.income,
        "profit": item.nominal.profit,
        "performance": item.nominal.percentage,
        "annualized_performance": item.nominal.annualized,
        "real_cost": item.real.cost,
        "real_dividends": item.real.income,
        "real_profit": item.real.profit,
        "real_performance": item.real.percentage,
        "real_annualized_performance": item.real.annualized,
        "included_in_opening": lot[c.LOT_INCLUDED_IN_OPENING],
        "estimated": lot[c.LOT_ESTIMATED],
    }


@websocket_api.websocket_command(
    {
        vol.Required("type"): "my_wallet/wallets",
        vol.Optional("forecast_years"): _forecast_years,
    }
)
@callback
def ws_wallets(hass, connection, msg):
    if not _admin(connection, msg):
        return
    today = dt_util.now().date()
    forecast_years = int(msg.get("forecast_years", max(FORECAST_YEARS)))
    forecast_horizons = tuple(sorted({*FORECAST_YEARS, forecast_years}))
    wallets = []
    for entry in _entries(hass):
        coordinator = getattr(entry, "runtime_data", None)
        current = _wallet_with_saved_units(
            entry.data, getattr(coordinator, "data", None), today=today
        )
        valuation = wallet_valuation(
            entry.data,
            current,
            today=today,
            available=getattr(coordinator, "last_update_success", True),
        )
        total = valuation.nominal.value
        inflation = current.inflation if current is not None else None
        expected_inflation = expected_annual_inflation(entry.data)
        start = documented_wallet_start_date(entry.data, through=today)
        start_date = start.isoformat() if start else None
        positions = [
            _position_payload(entry.data, valor, current, today=today, total=total)
            for valor in entry.data[c.CONF_VALORS]
        ]
        current_cash = cash_balance(entry.data, through=today)
        target = target_projection(entry.data, through=today)
        target_absolute, target_percentage = target_deviation(total, target.value)
        forecast_projection = target_projection(
            entry.data, through=add_years(today, max(forecast_horizons))
        )
        allocation_forecasts = {
            str(years): forecast
            for years in forecast_horizons
            if (
                forecast := target_allocation_forecast(
                    forecast_projection,
                    current_date=today,
                    through=add_years(today, years),
                    positions={item["symbol"]: item["value"] for item in positions},
                    cash=current_cash,
                )
            )
            is not None
        }
        for years, forecast in allocation_forecasts.items():
            horizon = add_years(today, int(years))
            price_factor = future_inflation_factor(expected_inflation, today, horizon)
            forecast["inflation_factor"] = round(price_factor, 8)
            forecast["real_positions"] = {
                symbol: round(value / price_factor, 2)
                for symbol, value in forecast["positions"].items()
            }
            forecast["real_cash"] = round(forecast["cash"] / price_factor, 2)
            forecast["real_total"] = round(forecast["total"] / price_factor, 2)
            forecast["inflation_effect"] = round(
                forecast["total"] - forecast["real_total"], 2
            )
        wallets.append(
            {
                "entry_id": entry.entry_id,
                "as_of": today.isoformat(),
                "name": entry.title or entry.data.get(c.CONF_WALLET_NAME, "My Wallet"),
                "currency": entry.data[c.CONF_BASE_CURRENCY],
                "start_date": start_date,
                "invested": valuation.nominal.cost,
                "cash": current_cash,
                "dividends": valuation.dividends,
                "real_dividends": valuation.real_dividends,
                "total": total,
                "profit": valuation.nominal.profit,
                "performance": valuation.nominal.percentage,
                "money_weighted_return": valuation.nominal.annualized,
                "real_invested": valuation.real.cost,
                "real_profit": valuation.real.profit,
                "real_performance": valuation.real.percentage,
                "real_money_weighted_return": valuation.real.annualized,
                "inflation": {
                    "available": inflation is not None,
                    "source": inflation.source if inflation is not None else None,
                    "region": inflation.region if inflation is not None else None,
                    "latest_month": (
                        inflation.latest_month if inflation is not None else None
                    ),
                    "stale": inflation.stale if inflation is not None else False,
                    "expected_annual_inflation": expected_inflation,
                },
                "target": {
                    "value": round(target.value, 2)
                    if target.value is not None
                    else None,
                    "annual_return": target.annual_return,
                    "expected_annual_inflation": expected_inflation,
                    "monthly_return": target.monthly_return,
                    "absolute_deviation": round(target_absolute, 2)
                    if target_absolute is not None
                    else None,
                    "percentage_deviation": round(target_percentage, 2)
                    if target_percentage is not None
                    else None,
                    "start_date": target.start_date.isoformat()
                    if target.start_date
                    else None,
                    "date": today.isoformat(),
                    "unavailable_reason": target.unavailable_reason,
                    "calculation_basis": "planned_savings_rates",
                    "allocation_forecasts": allocation_forecasts,
                },
                "positions": positions,
                "correction_choices": correction_choices(entry.data, today=today),
                "pending": current.pending_executions if current is not None else [],
                "plans": entry.data.get(c.CONF_SAVINGS_PLANS, []),
                "planned_deposits": planned_deposit_summaries(entry.data, today=today),
                "opening_conflicts": opening_balance_conflicts(entry.data),
            }
        )
    connection.send_result(msg["id"], {"wallets": wallets})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "my_wallet/planned_deposit",
        vol.Required("entry_id"): str,
        vol.Required("deposit_id"): str,
        vol.Required("action"): vol.Any("save", "delete"),
        vol.Optional("amount"): vol.Any(int, float),
        vol.Optional("date"): str,
        vol.Optional("note"): str,
    }
)
@callback
def ws_planned_deposit(hass, connection, msg):
    """Create, edit or cancel a future deposit without changing past bookings."""
    if not _admin(connection, msg):
        return
    entry = next(
        (item for item in _entries(hass) if item.entry_id == msg["entry_id"]), None
    )
    if entry is None:
        connection.send_error(msg["id"], "not_found", "Wallet not found")
        return
    try:
        data = change_planned_deposit(
            entry.data,
            today=dt_util.now().date(),
            deposit_id=msg["deposit_id"],
            action=msg["action"],
            amount=msg.get("amount"),
            deposit_date=msg.get("date"),
            note=msg.get("note", ""),
        )
    except ValueError as err:
        connection.send_error(
            msg["id"], str(err), "The planned deposit was not changed"
        )
        return
    if data != entry.data:
        try:
            commit_wallet_change(
                hass, entry, data, snapshot=entry.data, today=dt_util.now().date()
            )
        except ValueError as err:
            connection.send_error(msg["id"], str(err), "Wallet was not changed")
            return
        _state(hass)["cache"].pop(entry.entry_id, None)
    connection.send_result(msg["id"], {"saved": True})


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
        try:
            commit_wallet_change(
                hass, entry, data, snapshot=entry.data, today=dt_util.now().date()
            )
        except ValueError as err:
            connection.send_error(msg["id"], str(err), "Wallet was not changed")
            return
        _state(hass)["cache"].pop(entry.entry_id, None)
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
    {
        vol.Required("type"): "my_wallet/recorded_history",
        vol.Required("entry_id"): str,
        vol.Required("period"): vol.Any(*PERIOD_DAYS),
        vol.Optional("symbol"): str,
        vol.Optional("components", default=False): bool,
    }
)
@websocket_api.async_response
async def ws_recorded_history(hass, connection, msg):
    """Expose only this wallet's recorded states to an authenticated admin."""
    if not _admin(connection, msg):
        return
    entry = next(
        (entry for entry in _entries(hass) if entry.entry_id == msg["entry_id"]), None
    )
    if entry is None:
        connection.send_error(msg["id"], "entry_not_found", "Wallet not found")
        return
    symbol, period = msg.get("symbol"), msg["period"]
    components = msg.get("components", False)
    if (
        (components and symbol is not None)
        or period not in PERIOD_DAYS
        or (
            symbol is not None
            and symbol not in {v[c.VALOR_SYMBOL] for v in entry.data[c.CONF_VALORS]}
        )
    ):
        connection.send_error(
            msg["id"], "invalid_recorded_history", "Invalid history selection"
        )
        return
    state = _state(hass)
    lock = state["locks"].setdefault(("recorded", entry.entry_id), asyncio.Lock())
    async with lock:
        snapshot = entry.data
        cache = state.setdefault("recorded_cache", {})
        cached = cache.get(entry.entry_id)
        if (
            cached
            and cached["snapshot"] is snapshot
            and cached["selection"] == (period, symbol, components)
            and monotonic() < cached["expires"]
        ):
            connection.send_result(msg["id"], cached["result"])
            return
        try:
            result = (
                await async_recorded_components(hass, entry, period=period)
                if components
                else await async_recorded_history(
                    hass, entry, period=period, symbol=symbol
                )
            )
        except Exception:
            _LOGGER.exception("Could not read My Wallet Recorder history")
            connection.send_error(
                msg["id"],
                "recorded_history_failed",
                "Recorded history could not be loaded",
            )
            return
        if entry.data is not snapshot:
            connection.send_error(
                msg["id"], "entry_changed", "Wallet changed; reload history"
            )
            return
        cache[entry.entry_id] = {
            "snapshot": snapshot,
            "selection": (period, symbol, components),
            "expires": monotonic() + 30,
            "result": result,
        }
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "my_wallet/history",
        vol.Required("entry_id"): str,
        vol.Optional("forecast_years"): _forecast_years,
    }
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
        coordinator = getattr(entry, "runtime_data", None)
        current = getattr(coordinator, "data", None)
        inflation = current.inflation if current is not None else None
        today = dt_util.now().date()
        forecast_years = int(msg.get("forecast_years", max(FORECAST_YEARS)))
        entry_cache = state["cache"].setdefault(entry.entry_id, {})
        cached = entry_cache.get(forecast_years)
        if (
            cached
            and cached["snapshot"] is snapshot
            and cached.get("inflation") is inflation
            and cached["day"] == today
            and cached["expires"] > monotonic()
        ):
            result = cached["result"]
        else:
            try:
                async with asyncio.timeout(90):
                    result = await async_history(
                        snapshot,
                        session=async_get_clientsession(hass),
                        today=today,
                        forecast_years=forecast_years,
                        inflation=inflation,
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
            entry_cache[forecast_years] = {
                "snapshot": snapshot,
                "inflation": inflation,
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
    connection.send_result(
        msg["id"],
        {
            "token": token,
            "summary": summary,
            "entry_id": target.entry_id if target is not None else None,
            "target_name": target.title if target is not None else None,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "my_wallet/import_commit",
        vol.Required("token"): str,
        vol.Required("confirm"): bool,
        vol.Optional("entry_id"): str,
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
        if msg.get("entry_id") != preview["entry_id"]:
            connection.send_error(
                msg["id"], "entry_changed", "Import target differs from the preview"
            )
            return
        entry = next(
            (item for item in _entries(hass) if item.entry_id == preview["entry_id"]),
            None,
        )
        if entry is None or entry.data is not preview["snapshot"]:
            connection.send_error(
                msg["id"], "entry_changed", "Wallet changed; preview again"
            )
            return
        try:
            commit_wallet_change(
                hass,
                entry,
                preview["data"],
                snapshot=preview["snapshot"],
                today=dt_util.now().date(),
            )
        except ValueError as err:
            connection.send_error(msg["id"], str(err), "Wallet was not changed")
            return
        _state(hass)["previews"].pop(msg["token"], None)
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
    try:
        commit_wallet_change(
            hass,
            entry,
            preview["data"],
            snapshot=preview["snapshot"],
            today=dt_util.now().date(),
        )
    except ValueError as err:
        connection.send_error(msg["id"], str(err), "Wallet was not changed")
        return
    _state(hass)["previews"].pop(msg["token"], None)
    _state(hass)["cache"].pop(entry.entry_id, None)
    connection.send_result(msg["id"], {"entry_id": entry.entry_id})
