"""Run against real Home Assistant in CI, separately from the stubbed unit tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory

from homeassistant import bootstrap, loader
from homeassistant.components.recorder import get_instance
from homeassistant.core import HomeAssistant

from custom_components.my_wallet.recorded_history import (
    SNAPSHOT_ATTRIBUTE,
    _read_recordings,
    _state_record,
)

ENTITY = "sensor.synthetic_wallet_total"


async def exercise(hass: HomeAssistant) -> None:
    """Check the actual SQL reader, lazy attributes and attribute-only updates."""
    recorder = get_instance(hass)
    await recorder.async_recorder_ready.wait()

    async def sample(value, capital):
        now = datetime.now(UTC)
        hass.states.async_set(
            ENTITY,
            value,
            {
                "unit_of_measurement": "EUR",
                "cash_balance": 0,
                SNAPSHOT_ATTRIBUTE: {
                    "capital": capital,
                    "income": 0,
                    "revision": "synthetic-basis",
                    "sampled_at": now.isoformat(),
                },
            },
        )
        await hass.async_block_till_done()
        await recorder.async_block_till_done()

    await sample(100, 100)
    # The reader must recover the state immediately before the selected period.
    start = datetime.now(UTC)
    await sample(100, 100)  # Same value; only the poll timestamp changes.
    await sample(155, 150)

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
    assert [p["value"] for p in result["points"]][:3] == [100, 100, 155], result
    assert result["points"][-1]["invested"] == 150, result
    assert result["last_polled_at"], result
    assert not result["has_gaps"], result

    await sample("unavailable", 150)
    await sample(160, 150)
    result = await read()
    assert result["has_gaps"], result
    assert any(p.get("value") is None for p in result["points"]), result
    assert result["points"][-1]["value"] == 160, result
    print("Real HA Recorder: start state, poll-only updates, cash basis and gaps OK.")


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
