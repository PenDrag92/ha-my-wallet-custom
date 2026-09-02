"""Read bounded intraday snapshots from Recorder; never write historical states."""

from __future__ import annotations

import asyncio
import hashlib
import json
from bisect import bisect_right
from datetime import UTC, date, datetime, timedelta
from math import isfinite

from homeassistant.util import dt as dt_util

from . import const as c
from .contributions import all_lots, contributions_from_data, invested_total
from .dividends import dividend_total, dividends_from_data

SNAPSHOT_ATTRIBUTE = "history_snapshot"
MAX_RECORDINGS = 10_000
PERIOD_DAYS = {"day": 1, "week": 7}


def accounting_snapshot(data, *, today: date, symbol=None, sampled_at=None):
    """Keep flows and valuation together so later edits cannot rewrite a sample."""
    lots = [
        lot
        for lot in all_lots(data, through=today)
        if symbol is None or lot[c.LOT_SYMBOL] == symbol
    ]
    if symbol is None:
        capital = invested_total(data, through=today)
        income = dividend_total(data, through=today)
    else:
        valor = next(
            (v for v in data[c.CONF_VALORS] if v[c.VALOR_SYMBOL] == symbol), None
        )
        included = sum(
            lot[c.LOT_UNITS] for lot in lots if lot[c.LOT_INCLUDED_IN_OPENING]
        )
        known = (
            valor is not None and abs(float(valor[c.VALOR_AMOUNT]) - included) < 1e-8
        )
        capital = sum(lot[c.LOT_AMOUNT] for lot in lots) if known else None
        income = sum(
            row[c.DIVIDEND_AMOUNT]
            for row in dividends_from_data(data)
            if row.get(c.DIVIDEND_SYMBOL) == symbol
            and (row.get(c.DIVIDEND_VALUE_DATE) or row[c.DIVIDEND_BOOKING_DATE])
            <= today.isoformat()
        )
    # New purchases/deposits do not change the basis. Explicit edits do.
    basis = {
        "opening": {
            v[c.VALOR_SYMBOL]: v[c.VALOR_AMOUNT]
            for v in data[c.CONF_VALORS]
            if (symbol is None or v[c.VALOR_SYMBOL] == symbol) and v[c.VALOR_AMOUNT]
        },
        "corrections": [
            row
            for row in data.get("unit_corrections", [])
            if symbol is None or row.get("symbol") == symbol
        ],
        "edits": [
            row
            for row in contributions_from_data(data)
            if row.get(c.CONTRIBUTION_MANUALLY_EDITED)
            and (
                symbol is None
                or any(lot[c.LOT_SYMBOL] == symbol for lot in row[c.CONTRIBUTION_LOTS])
            )
        ],
    }
    revision = hashlib.sha256(
        json.dumps(basis, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:20]
    return {
        "capital": capital,
        "income": income,
        "revision": revision,
        "sampled_at": sampled_at,
    }


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if isfinite(result) else None


def _timestamp(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime) or value.tzinfo is None:
        return None
    return value.astimezone(UTC)


def _state_record(state):
    """Materialize lazy database states while still in the Recorder executor."""
    return {
        "time": state.last_updated,
        "state": state.state,
        "attributes": dict(state.attributes),
    }


def _legacy_accounting(record, auxiliary, auxiliary_times, *, symbol, value):
    """Use the old performance sensor only when its valuation matches."""
    # Sensors from one coordinator update are written a few milliseconds apart.
    index = bisect_right(auxiliary_times, record["time"] + timedelta(seconds=2)) - 1
    if index < 0 or value is None:
        return {}
    other = auxiliary[index]
    attrs = other["attributes"]
    if _number(other["state"]) is None:
        return {}
    total = _number(attrs.get(c.ATTR_TRACKED_VALUE if symbol else c.ATTR_TOTAL))
    if total is None or abs(total - value) > 0.011:
        return {}
    if attrs.get("unit_of_measurement") != record["attributes"].get(
        "unit_of_measurement"
    ):
        return {}
    if symbol:
        units = _number(record["attributes"].get(c.ATTR_AMOUNT))
        rows = attrs.get(c.ATTR_LOTS, [])
        if (
            not isinstance(rows, list)
            or not rows
            or units is None
            or any(not isinstance(row, dict) for row in rows)
        ):
            return {}
        tracked = [_number(row.get(c.LOT_UNITS)) for row in rows]
        # Legacy profit sensors rounded each lot to six decimal places.
        tolerance = len(rows) * 0.0000005 + 1e-8
        if (
            any(item is None for item in tracked)
            or abs(sum(tracked) - units) > tolerance
        ):
            return {}
    return {
        "capital": attrs.get(c.ATTR_TRACKED_INVESTED if symbol else c.ATTR_INVESTED),
        "income": record["attributes"].get(c.ATTR_DIVIDEND_TOTAL)
        if symbol
        else attrs.get(c.ATTR_DIVIDEND_TOTAL),
    }


def build_recorded_history(
    records,
    auxiliary,
    *,
    start,
    end,
    currency,
    symbol=None,
    interval=30,
    live=None,
    inflation=None,
    corrections=(),
):
    """Preserve unknown values and gaps; do not invent prices between samples."""
    result = {
        "source": "recorder",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "symbol": symbol,
        "currency": currency,
        "points": [],
        "status": "no_history",
        "last_recorded_at": None,
        "last_polled_at": None,
        "has_gaps": False,
        "partial": False,
        "accounting_changed": False,
    }
    records = sorted(
        (r for r in records if start <= r["time"] <= end), key=lambda r: r["time"]
    )
    if not records:
        return result
    if len(records) > MAX_RECORDINGS:
        return {**result, "status": "too_many_points"}
    auxiliary = sorted(auxiliary, key=lambda r: r["time"])
    auxiliary_times = [r["time"] for r in auxiliary]
    result["last_recorded_at"] = next(
        (r["time"].isoformat() for r in reversed(records) if r["time"] > start), None
    )
    if live and records[-1]["time"] < live["time"] <= end:
        records.append(live)
    points = []
    tolerance = timedelta(minutes=max(15, interval * 3))
    previous_sample = None
    for record in records:
        attrs = record["attributes"]
        value = _number(record["state"])
        same_currency = attrs.get("unit_of_measurement") == currency
        if not same_currency or (value is not None and value < 0):
            value = None
        snapshot = attrs.get(SNAPSHOT_ATTRIBUTE)
        if not isinstance(snapshot, dict):
            snapshot = _legacy_accounting(
                record, auxiliary, auxiliary_times, symbol=symbol, value=value
            )
        sampled = _timestamp(snapshot.get("sampled_at"))
        if sampled and sampled > record["time"] + timedelta(seconds=2):
            sampled = None
        if sampled and record["time"] - sampled > tolerance:
            value = None
        if previous_sample and sampled and sampled - previous_sample > tolerance:
            gap = min(
                record["time"] - timedelta(microseconds=1), previous_sample + tolerance
            )
            if points[-1]["timestamp"] < gap.isoformat():
                points.append({"timestamp": gap.isoformat(), "value": None})
        previous_sample = sampled
        if sampled:
            result["last_polled_at"] = sampled.isoformat()
        factor = (
            inflation.factor(
                dt_util.as_local(record["time"]).date(), dt_util.as_local(end).date()
            )
            if inflation
            else None
        )
        cash = (
            None
            if symbol or not same_currency
            else _number(attrs.get(c.ATTR_CASH_BALANCE))
        )
        points.append(
            {
                "timestamp": record["time"].isoformat(),
                "value": value,
                "invested": _number(snapshot.get("capital")) if same_currency else None,
                "dividends": _number(snapshot.get("income")) if same_currency else None,
                "cash": cash,
                "units": _number(attrs.get(c.ATTR_AMOUNT)) if symbol else None,
                "revision": snapshot.get("revision"),
                "factor": factor,
                "real_value": value * factor
                if value is not None and factor is not None
                else None,
                "real_cash": cash * factor
                if cash is not None and factor is not None
                else None,
            }
        )
    if points[0]["timestamp"] != start.isoformat():
        points.insert(0, {"timestamp": start.isoformat(), "value": None})
        result["partial"] = True
    # A boundary holds the last known state, not a fictitious fresh quote.
    last_reported = _timestamp(live.get("reported")) if live else None
    if last_reported and last_reported > end + timedelta(seconds=2):
        last_reported = None
    fresh = last_reported or _timestamp(result["last_polled_at"])
    current_valid = (
        live is not None
        and _number(live["state"]) is not None
        and _number(live["state"]) >= 0
        and live["attributes"].get("unit_of_measurement") == currency
    )
    stale = fresh is None or end - fresh > tolerance or not current_valid
    if points[-1]["timestamp"] != end.isoformat():
        points.append(
            {"timestamp": end.isoformat(), "value": None}
            if stale
            else {**points[-1], "timestamp": end.isoformat(), "boundary": True}
        )
    result["points"] = points
    result["has_gaps"] = any(p.get("value") is None for p in points)
    result["status"] = "stale" if stale else "partial" if result["partial"] else "ok"
    # Legacy samples cannot prove that a same-day manual correction was a return.
    legacy = any(
        p.get("revision") is None and p.get("value") is not None for p in points
    )
    result["accounting_changed"] = legacy and any(
        (symbol is None or row.get("symbol") == symbol)
        and dt_util.as_local(start).date().isoformat()
        <= row.get("recorded_date", "")
        <= dt_util.as_local(end).date().isoformat()
        for row in corrections
    )
    return result


def _recorder_instance(hass):
    from homeassistant.components.recorder import get_instance

    return get_instance(hass)


def _history_entities(hass, entry, symbol):
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    prefix = f"{entry.entry_id}_{symbol}" if symbol else entry.entry_id
    main_id = registry.async_get_entity_id(
        "sensor", c.DOMAIN, prefix if symbol else f"{prefix}_total"
    )
    auxiliary_id = registry.async_get_entity_id("sensor", c.DOMAIN, f"{prefix}_profit")
    primary = registry.async_get(main_id) if main_id else None
    if primary is None or primary.config_entry_id != entry.entry_id:
        return None, None, "entity_missing"
    if primary.disabled_by:
        return main_id, None, "entity_disabled"
    auxiliary = registry.async_get(auxiliary_id) if auxiliary_id else None
    if (
        auxiliary is None
        or auxiliary.config_entry_id != entry.entry_id
        or auxiliary.disabled_by
    ):
        auxiliary_id = None
    return main_id, auxiliary_id, None


def _read_recordings(hass, main_id, auxiliary_id, *, start, end, **kwargs):
    from homeassistant.components.recorder.history import get_significant_states

    states = get_significant_states(
        hass,
        start,
        end,
        [item for item in (main_id, auxiliary_id) if item],
        include_start_time_state=True,
        significant_changes_only=False,
        minimal_response=False,
        no_attributes=False,
    )
    return build_recorded_history(
        [_state_record(state) for state in states.get(main_id, [])],
        [_state_record(state) for state in states.get(auxiliary_id, [])],
        start=start,
        end=end,
        **kwargs,
    )


async def async_recorded_history(hass, entry, *, period, symbol=None):
    """Read at most two entities belonging to this config entry for 1 or 7 days."""
    end = datetime.now(UTC)
    start = end - timedelta(days=PERIOD_DAYS[period])
    currency = entry.data[c.CONF_BASE_CURRENCY]
    empty = build_recorded_history(
        [], [], start=start, end=end, currency=currency, symbol=symbol
    )
    try:
        recorder = _recorder_instance(hass)
    except (ImportError, KeyError):
        return {**empty, "status": "recorder_missing"}
    if not recorder.is_running or not recorder.async_db_ready.done():
        return {**empty, "status": "recorder_unavailable"}
    main_id, auxiliary_id, problem = _history_entities(hass, entry, symbol)
    if problem:
        return {**empty, "status": problem}
    if recorder.entity_filter and not recorder.entity_filter(main_id):
        return {**empty, "status": "entity_excluded"}
    if (
        auxiliary_id
        and recorder.entity_filter
        and not recorder.entity_filter(auxiliary_id)
    ):
        auxiliary_id = None
    state = hass.states.get(main_id)
    live = _state_record(state) if state else None
    if live:
        live["reported"] = getattr(state, "last_reported", state.last_updated)
    current = getattr(getattr(entry, "runtime_data", None), "data", None)
    from functools import partial

    query = partial(
        _read_recordings,
        hass,
        main_id,
        auxiliary_id,
        start=start,
        end=end,
        currency=currency,
        symbol=symbol,
        live=live,
        interval=int(entry.data.get(c.CONF_SCAN_INTERVAL, c.DEFAULT_SCAN_INTERVAL)),
        inflation=getattr(current, "inflation", None),
        corrections=entry.data.get("unit_corrections", []),
    )
    async with asyncio.timeout(25):
        result = await recorder.async_add_executor_job(query)
    if not recorder.enabled:
        result["status"] = "recorder_disabled"
    return result
