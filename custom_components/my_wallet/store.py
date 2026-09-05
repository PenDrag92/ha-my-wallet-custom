"""The Home Assistant persistence boundary for existing wallets."""

from __future__ import annotations

from .ledger import CashPolicy, prepare_change


def commit_wallet_change(
    hass,
    entry,
    candidate,
    *,
    snapshot,
    today,
    title=None,
    reload=True,
    cash_policy=CashPolicy.PRESERVE,
):
    """Validate and commit atomically on HA's event loop, with no await in between.

    Callers that perform asynchronous work must supply the snapshot they used.
    Config-entry migrations and creation of a validated backup are separate
    lifecycle operations; ordinary edits always pass through this boundary.
    """
    if entry.data is not snapshot:
        raise ValueError("entry_changed")
    data = prepare_change(snapshot, candidate, today=today, cash_policy=cash_policy)
    if data == snapshot and (title is None or title == entry.title):
        return False
    kwargs = {"data": data}
    if title is not None:
        kwargs["title"] = title
    changed = hass.config_entries.async_update_entry(entry, **kwargs)
    if changed and reload:
        hass.config_entries.async_schedule_reload(entry.entry_id)
    return changed
