"""Transparent monthly and yearly performance summaries."""

from __future__ import annotations

from collections import defaultdict
from math import prod


def _value(point, symbol):
    if symbol is None:
        return point["value"]
    return point.get("positions", {}).get(symbol, 0.0)


def _cost(point, symbol):
    if symbol is None:
        return point["invested"]
    return point.get("position_costs", {}).get(symbol, 0.0)


def period_summaries(points, ledger, *, symbol=None):
    """Calculate absolute gain and linked daily returns for calendar periods.

    Wallet deposits are external flows. Position purchases are capital flows and
    position dividends are distributed income. A percentage stays unavailable
    until a valid opening value exists and every required price is present.
    """
    result = {}
    for size in (7, 4):
        grouped = defaultdict(list)
        for index, point in enumerate(points):
            grouped[point["date"][:size]].append((index, point))
        event_groups = defaultdict(list)
        for event in ledger:
            event_date = event.get("date") or ""
            if event_date and (symbol is None or event.get("symbol") == symbol):
                event_groups[event_date[:size]].append(event)
        rows = []
        for key, indexed_group in sorted(grouped.items()):
            first_index = indexed_group[0][0]
            group = [item[1] for item in indexed_group]
            if all(point.get("baseline") for point in group):
                continue
            previous = (
                points[first_index - 1]
                if first_index
                else group[0]
                if group[0].get("baseline")
                else None
            )
            start_value = _value(previous, symbol) if previous is not None else None
            end_value = _value(group[-1], symbol)
            events = event_groups[key]
            deposits = sum(
                row["amount"]
                for row in events
                if row["type"] in ({"deposit", "opening"} if symbol is None else set())
            )
            purchases = sum(
                -row["amount"] for row in events if row["type"] == "purchase"
            )
            dividends = sum(
                row["amount"] for row in events if row["type"] == "dividend"
            )
            capital = deposits if symbol is None else purchases
            gain = (
                end_value
                - start_value
                - capital
                + (dividends if symbol is not None else 0)
                if start_value is not None and end_value is not None
                else None
            )
            by_day = defaultdict(lambda: {"capital": 0.0, "income": 0.0})
            for event in events:
                if symbol is None and event["type"] in {"deposit", "opening"}:
                    by_day[event["date"]]["capital"] += event["amount"]
                elif symbol is not None and event["type"] == "purchase":
                    by_day[event["date"]]["capital"] += -event["amount"]
                elif symbol is not None and event["type"] == "dividend":
                    by_day[event["date"]]["income"] += event["amount"]
            chain, measurable, complete = [], False, previous is not None
            prior = start_value
            for point in group:
                current = _value(point, symbol)
                flow = by_day[point["date"]]
                if current is None or prior is None:
                    complete = False
                elif prior > 1e-10:
                    chain.append((current - flow["capital"] + flow["income"]) / prior)
                    measurable = True
                elif flow["capital"] > 1e-10:
                    chain.append((current + flow["income"]) / flow["capital"])
                    measurable = True
                elif abs(current + flow["income"]) > 0.005:
                    complete = False
                prior = current
            linked_return = (prod(chain) - 1) * 100 if complete and measurable else None
            rows.append(
                {
                    "period": key,
                    "start": group[0]["date"],
                    "end": group[-1]["date"],
                    "start_value": start_value,
                    "end_value": end_value,
                    "end_cost": _cost(group[-1], symbol),
                    "deposits": round(deposits, 2),
                    "purchases": round(purchases, 2),
                    "dividends": round(dividends, 2),
                    "gain": round(gain, 2) if gain is not None else None,
                    "return": round(linked_return, 4)
                    if linked_return is not None
                    else None,
                    "complete": gain is not None and complete,
                }
            )
        result["monthly" if size == 7 else "yearly"] = rows
    return result
