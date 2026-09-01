"""Load pure integration modules without installing Home Assistant."""

from __future__ import annotations

import enum
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "custom_components" / "my_wallet"


def install_stubs() -> None:
    """Install only the package and dependency stubs used by pure tests."""
    custom_components = types.ModuleType("custom_components")
    custom_components.__path__ = [str(ROOT / "custom_components")]
    wallet = types.ModuleType("custom_components.my_wallet")
    wallet.__path__ = [str(PACKAGE)]
    sys.modules.setdefault("custom_components", custom_components)
    sys.modules.setdefault("custom_components.my_wallet", wallet)

    homeassistant = types.ModuleType("homeassistant")
    ha_const = types.ModuleType("homeassistant.const")

    class Platform(enum.StrEnum):
        SENSOR = "sensor"

    ha_const.Platform = Platform
    sys.modules.setdefault("homeassistant", homeassistant)
    sys.modules.setdefault("homeassistant.const", ha_const)

    storage = types.ModuleType("homeassistant.helpers.storage")

    class Store:
        def __init__(self, *_: object, **__: object) -> None:
            self.value = None

        async def async_load(self):
            return self.value

        async def async_save(self, value) -> None:
            self.value = value

    storage.Store = Store
    sys.modules.setdefault("homeassistant.helpers.storage", storage)

    if "aiohttp" not in sys.modules:
        aiohttp = types.ModuleType("aiohttp")

        class ClientError(Exception):
            pass

        class ClientSession:
            pass

        class ClientTimeout:
            def __init__(self, **_: object) -> None:
                pass

        aiohttp.ClientError = ClientError
        aiohttp.ClientSession = ClientSession
        aiohttp.ClientTimeout = ClientTimeout
        sys.modules["aiohttp"] = aiohttp
