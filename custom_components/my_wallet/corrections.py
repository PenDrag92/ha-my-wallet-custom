"""Preview explicit unit corrections without changing recorded cash flows."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from math import isclose
from uuid import uuid4

from . import const as c
from .contributions import (
    additional_units,
    all_lots,
    contributions_from_data,
    normalize_lot,
)
from .history_import import _number
from .ledger import prepare_change

UNIT_CORRECTIONS = "unit_corrections"


def position_units(data, symbol: str, today: date) -> float:
    opening = next(
        float(valor[c.VALOR_AMOUNT])
        for valor in data[c.CONF_VALORS]
        if valor[c.VALOR_SYMBOL] == symbol
    )
    return opening + additional_units(data, symbol, through=today)


def prepare_correction(data, request, *, today: date):
    """Correct a chosen purchase or opening holding, never an invented trade.

    A total-position correction must name the purchase/opening holding that
    explains the discrepancy. Its historical date and every payment stay intact.
    Included opening lots move the configured opening total by the same delta,
    preserving any other (possibly undated) opening holdings.
    """
    symbol = request.get("symbol")
    if symbol not in {valor[c.VALOR_SYMBOL] for valor in data[c.CONF_VALORS]}:
        raise ValueError("not_found")
    mode, target = request.get("mode"), request.get("target")
    if mode not in {"lot", "position"} or not isinstance(target, str):
        raise ValueError("invalid_correction")
    units = _number(request.get("units"), allow_zero=True)
    note = request.get("note", "")
    if not isinstance(note, str) or len(note) > 500:
        raise ValueError("invalid_correction")
    candidate = deepcopy(dict(data))
    valors = candidate[c.CONF_VALORS]
    valor = next(item for item in valors if item[c.VALOR_SYMBOL] == symbol)
    total_before = position_units(data, symbol, today)
    opening_before = float(valor[c.VALOR_AMOUNT])
    contribution_id, effective = None, None
    if target == "opening":
        before = opening_before
        after = units if mode == "lot" else before + units - total_before
        if after < 0:
            raise ValueError("correction_negative_units")
        valor[c.VALOR_AMOUNT] = after
    else:
        rows = contributions_from_data(data)
        matches = [
            (row, lot)
            for row in rows
            for lot in row[c.CONTRIBUTION_LOTS]
            if lot[c.LOT_ID] == target and lot[c.LOT_SYMBOL] == symbol
        ]
        if len(matches) != 1:
            raise ValueError("not_found")
        row, lot = matches[0]
        if lot[c.LOT_DATE] > today.isoformat():
            raise ValueError("future_date")
        before = lot[c.LOT_UNITS]
        after = units if mode == "lot" else before + units - total_before
        if after <= 0:
            raise ValueError("correction_negative_units")
        contribution_id, effective = row[c.CONTRIBUTION_ID], lot[c.LOT_DATE]
        replacement = normalize_lot(
            {
                **lot,
                c.LOT_UNITS: after,
                c.LOT_UNIT_PRICE: lot[c.LOT_AMOUNT] / (after * lot[c.LOT_FX_RATE]),
                c.LOT_ESTIMATED: False,
                "price_date": lot[c.LOT_DATE],
            }
        )
        row[c.CONTRIBUTION_LOTS] = [
            replacement if item[c.LOT_ID] == target else item
            for item in row[c.CONTRIBUTION_LOTS]
        ]
        row[c.CONTRIBUTION_MANUALLY_EDITED] = True
        candidate[c.CONF_CONTRIBUTIONS] = rows
        if lot[c.LOT_INCLUDED_IN_OPENING]:
            valor[c.VALOR_AMOUNT] += after - before
            if valor[c.VALOR_AMOUNT] < 0:
                raise ValueError("correction_negative_units")
    if isclose(before, after, abs_tol=1e-12, rel_tol=1e-12):
        raise ValueError("correction_unchanged")
    summary = {
        "symbol": symbol,
        "target": target,
        "contribution_id": contribution_id,
        "effective_date": effective,
        "before_units": before,
        "after_units": after,
        "before_total": total_before,
        "after_total": position_units(candidate, symbol, today),
        "before_opening": opening_before,
        "after_opening": valor[c.VALOR_AMOUNT],
        "currency": data[c.CONF_BASE_CURRENCY],
        "note": note.strip(),
    }
    candidate[UNIT_CORRECTIONS] = [
        *data.get(UNIT_CORRECTIONS, []),
        {**summary, "id": uuid4().hex, "recorded_date": today.isoformat()},
    ]
    return prepare_change(data, candidate, today=today), summary


def correction_choices(data, *, today: date):
    """Return the exact, unrounded editable quantities for the admin panel."""
    return [
        {
            "symbol": valor[c.VALOR_SYMBOL],
            "units": position_units(data, valor[c.VALOR_SYMBOL], today),
            "opening_units": valor[c.VALOR_AMOUNT],
            "lots": [
                {
                    "id": lot[c.LOT_ID],
                    "date": lot[c.LOT_DATE],
                    "units": lot[c.LOT_UNITS],
                    "amount": lot[c.LOT_AMOUNT],
                    "estimated": lot[c.LOT_ESTIMATED],
                    "included_in_opening": lot[c.LOT_INCLUDED_IN_OPENING],
                }
                for lot in all_lots(data, through=today)
                if lot[c.LOT_SYMBOL] == valor[c.VALOR_SYMBOL]
            ],
        }
        for valor in data[c.CONF_VALORS]
    ]
