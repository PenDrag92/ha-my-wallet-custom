"""Fetch and persist the official Eurostat inflation series."""

from __future__ import annotations

import logging
from datetime import date

import aiohttp
from homeassistant.helpers.storage import Store

from . import const as c
from .inflation import InflationSeries, parse_eurostat_hicp

_LOGGER = logging.getLogger(__name__)
_URL = (
    "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_minr"
)
_FIRST_MONTH = "1996-01"


class InflationDataClient:
    """Daily-refreshing official data with a persistent offline fallback."""

    def __init__(self, hass, entry_id: str) -> None:
        self._store = Store(hass, 1, f"{c.DOMAIN}.inflation.{entry_id}")
        self._loaded = False
        self._cached: InflationSeries | None = None
        self._attempted: tuple[str, str] | None = None

    async def _async_load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            self._cached = InflationSeries.from_storage(await self._store.async_load())
        except Exception:  # pragma: no cover - corrupted storage is non-fatal
            _LOGGER.warning("Could not load the cached inflation series", exc_info=True)

    async def async_get(
        self,
        session: aiohttp.ClientSession,
        *,
        source: str,
        today: date,
    ) -> InflationSeries | None:
        """Return current official data or the last validated cached series."""
        if source == c.INFLATION_SOURCE_DISABLED:
            return None
        if source != c.INFLATION_SOURCE_EUROSTAT_DE:
            raise ValueError("unsupported_inflation_source")
        await self._async_load()
        if (
            self._cached is not None
            and self._cached.source == source
            and self._cached.fetched_at == today.isoformat()
        ):
            return self._cached
        attempt = (source, today.isoformat())
        if self._attempted == attempt:
            return (
                self._cached.with_stale()
                if self._cached is not None and self._cached.source == source
                else None
            )
        self._attempted = attempt
        try:
            series = await fetch_eurostat_hicp(
                session,
                region="DE",
                source=source,
                fetched_at=today.isoformat(),
            )
        except (aiohttp.ClientError, TimeoutError, ValueError):
            _LOGGER.warning(
                "Official inflation data are unavailable; using the last cache",
                exc_info=True,
            )
            if self._cached is not None and self._cached.source == source:
                return self._cached.with_stale()
            return None
        self._cached = series
        try:
            await self._store.async_save(series.as_storage())
        except Exception:  # pragma: no cover - data remain usable in memory
            _LOGGER.warning("Could not persist the inflation cache", exc_info=True)
        return series


async def fetch_eurostat_hicp(
    session: aiohttp.ClientSession,
    *,
    region: str,
    source: str,
    fetched_at: str | None,
) -> InflationSeries:
    """Download one filtered all-items HICP index without an API key."""
    params = {
        "lang": "EN",
        "freq": "M",
        "unit": "I25",
        "coicop18": "TOTAL",
        "geo": region,
        "sinceTimePeriod": _FIRST_MONTH,
    }
    timeout = aiohttp.ClientTimeout(total=30)
    async with session.get(_URL, params=params, timeout=timeout) as response:
        if response.status != 200:
            raise aiohttp.ClientError(
                f"Eurostat inflation request returned HTTP {response.status}"
            )
        payload = await response.json(content_type=None)
    return parse_eurostat_hicp(
        payload, source=source, region=region, fetched_at=fetched_at
    )
