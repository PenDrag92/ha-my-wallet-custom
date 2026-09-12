"""Run against real Home Assistant in CI, separately from the stubbed unit tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from homeassistant import bootstrap, loader
from homeassistant.components.recorder import get_instance
from homeassistant.core import HomeAssistant

from custom_components.my_wallet.recorded_history import (
    SNAPSHOT_ATTRIBUTE,
    _read_recordings,
    _state_record,
    async_recorded_components,
)

ENTITY = "sensor.synthetic_wallet_total"


async def exercise(hass: HomeAssistant) -> None:
    """Check the actual SQL reader, lazy attributes and attribute-only updates."""
    recorder = get_instance(hass)
    await recorder.async_recorder_ready.wait()

    async def sample(value, capital, financial_revision=None, *, entity=ENTITY):
        now = datetime.now(UTC)
        hass.states.async_set(
            entity,
            value,
            {
                "unit_of_measurement": "EUR",
                "cash_balance": 0,
                SNAPSHOT_ATTRIBUTE: {
                    "capital": capital,
                    "income": 0,
                    "revision": "synthetic-basis",
                    **(
                        {"financial_revision": financial_revision}
                        if financial_revision
                        else {}
                    ),
                    "sampled_at": now.isoformat(),
                },
            },
        )
        await hass.async_block_till_done()
        await recorder.async_block_till_done()

    await sample(100, 100)
    # The reader must recover the state immediately before the selected period.
    start = datetime.now(UTC)
    await sample(100, 100, "financial-a")  # Upgrade with unchanged accounting.
    await sample(100, 100, "financial-a")  # Only the poll timestamp changes.
    await sample(155, 150, "financial-a")

    async def read():
        state = hass.states.get(ENTITY)
        live = {**_state_record(state), "reported": state.last_reported}
        return await recorder.async_add_executor_job(
            partial(
                _read_recordings,
                hass,
                ENTITY,
                None,
                start=start,
                end=datetime.now(UTC),
                currency="EUR",
                live=live,
            )
        )

    result = await read()
    assert result["status"] == "ok", result
    assert result["points"][0]["timestamp"] == start.isoformat(), result
    assert [p["value"] for p in result["points"]][:4] == [100, 100, 100, 155], result
    assert result["points"][-1]["invested"] == 150, result
    assert result["points"][0]["financial_revision"] is None, result
    assert result["points"][-1]["financial_revision"] == "financial-a", result
    assert all(p["revision"] == "synthetic-basis" for p in result["points"]), result
    assert result["last_polled_at"], result
    assert not result["has_gaps"], result

    await sample("unavailable", 150)
    await sample(160, 150)
    result = await read()
    assert result["has_gaps"], result
    assert any(p.get("value") is None for p in result["points"]), result
    assert result["points"][-1]["value"] == 160, result
    await sample(60, 50, "position-a", entity="sensor.synthetic_position")
    entry = SimpleNamespace(
        entry_id="synthetic",
        data={"base_currency": "EUR", "valors": [{"symbol": "AAA"}, {"symbol": "BBB"}]},
    )

    def entities(_hass, _entry, symbol):
        if symbol == "BBB":
            return None, None, "entity_missing"
        return ENTITY if symbol is None else "sensor.synthetic_position", None, None

    with patch(
        "custom_components.my_wallet.recorded_history._history_entities",
        side_effect=entities,
    ):
        components = await async_recorded_components(hass, entry, period="day")
    for part in (components["cash"], *components["positions"].values()):
        assert part["start"] == components["start"], part
        assert part["end"] == components["end"], part
    assert components["cash"]["points"][-1]["value"] == 160, components
    position = components["positions"]["AAA"]["points"][-1]
    assert position["value"] == 60 and position["invested"] == 50, position
    assert position["financial_revision"] == "position-a", position
    assert components["positions"]["BBB"]["status"] == "entity_missing", components
    print("Real HA Recorder: snapshots, gaps and independent component windows OK.")


async def main() -> None:
    with TemporaryDirectory(prefix="my-wallet-recorder-") as directory:
        hass = HomeAssistant(directory)
        loader.async_setup(hass)
        config = {
            "homeassistant": {
                "name": "Synthetic recorder test",
                "latitude": 0,
                "longitude": 0,
                "elevation": 0,
                "unit_system": "metric",
                "time_zone": "Europe/Berlin",
            },
            "recorder": {
                "db_url": f"sqlite:///{Path(directory) / 'history.db'}",
                "auto_purge": False,
                "auto_repack": False,
                "commit_interval": 0,
            },
        }
        try:
            async with asyncio.timeout(120):
                assert await bootstrap.async_from_config_dict(config, hass) is hass
                await hass.async_start()
                await exercise(hass)
        finally:
            await hass.async_stop(force=True)


if __name__ == "__main__":
    asyncio.run(main())
