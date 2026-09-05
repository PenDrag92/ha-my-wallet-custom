"""Track revisions of existing financial events separately from new cash flows."""

import hashlib
import json

from . import const as c
from .contributions import all_lots, contributions_from_data
from .dividends import dividends_from_data

ACCOUNTING_REVISIONS = "accounting_revisions"
WALLET_REVISION = "__wallet__"


def mark_accounting_changes(before, after):
    """Mark replaced/deleted events; new purchases and deposits keep the basis."""
    changed = set()
    events = []
    new_lots = {lot[c.LOT_ID]: lot for lot in all_lots(after)}
    lot_fields = (
        c.LOT_SYMBOL,
        c.LOT_DATE,
        c.LOT_AMOUNT,
        c.LOT_UNITS,
        c.LOT_INCLUDED_IN_OPENING,
    )
    for old in all_lots(before):
        new = new_lots.get(old[c.LOT_ID], {})
        if any(old.get(key) != new.get(key) for key in lot_fields):
            events.append(["lot", old[c.LOT_ID], [new.get(key) for key in lot_fields]])
            changed.add(old[c.LOT_SYMBOL])
            if new:
                changed.add(new[c.LOT_SYMBOL])
    new_rows = {row[c.CONTRIBUTION_ID]: row for row in contributions_from_data(after)}
    for old in contributions_from_data(before):
        new = new_rows.get(old[c.CONTRIBUTION_ID], {})
        if any(
            old.get(key) != new.get(key)
            for key in (c.CONTRIBUTION_DATE, c.CONTRIBUTION_AMOUNT)
        ):
            events.append(
                [
                    "contribution",
                    old[c.CONTRIBUTION_ID],
                    new.get(c.CONTRIBUTION_DATE),
                    new.get(c.CONTRIBUTION_AMOUNT),
                ]
            )
            changed.add(WALLET_REVISION)
    new_dividends = {row[c.DIVIDEND_ID]: row for row in dividends_from_data(after)}
    for old in dividends_from_data(before):
        new = new_dividends.get(old[c.DIVIDEND_ID], {})
        if any(
            old.get(key) != new.get(key)
            for key in (
                c.DIVIDEND_AMOUNT,
                c.DIVIDEND_BOOKING_DATE,
                c.DIVIDEND_VALUE_DATE,
                c.DIVIDEND_SYMBOL,
            )
        ):
            events.append(
                [
                    "dividend",
                    old[c.DIVIDEND_ID],
                    *[
                        new.get(key)
                        for key in (
                            c.DIVIDEND_AMOUNT,
                            c.DIVIDEND_BOOKING_DATE,
                            c.DIVIDEND_VALUE_DATE,
                            c.DIVIDEND_SYMBOL,
                        )
                    ],
                ]
            )
            changed.add(old.get(c.DIVIDEND_SYMBOL) or WALLET_REVISION)
            changed.add(new.get(c.DIVIDEND_SYMBOL) or WALLET_REVISION)
    if changed:
        revisions = dict(before.get(ACCOUNTING_REVISIONS, {}))
        # Preparing the same edit twice (preview and commit) has the same basis.
        # The previous revisions make a later reversal a distinct correction.
        revision = hashlib.sha256(
            json.dumps(
                [revisions, sorted(events)], sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()[:32]
        revisions.update(dict.fromkeys(changed | {WALLET_REVISION}, revision))
        after[ACCOUNTING_REVISIONS] = revisions
