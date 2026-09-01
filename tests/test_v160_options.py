"""Option-flow regressions for the configurable 1.6 target return."""

from __future__ import annotations

import unittest

from custom_components.my_wallet.const import CONF_EXPECTED_ANNUAL_RETURN
from tests.test_options_regressions import (
    CONF_BASE_CURRENCY,
    CONF_SCAN_INTERVAL,
    CONF_WALLET_NAME,
    _flow,
)


class TargetOptionsTests(unittest.IsolatedAsyncioTestCase):
    async def test_settings_persist_expected_return_and_reject_out_of_range(
        self,
    ) -> None:
        flow, entry, manager = _flow()
        result = await flow.async_step_settings(
            {
                CONF_WALLET_NAME: "Old wallet",
                CONF_BASE_CURRENCY: "EUR",
                CONF_SCAN_INTERVAL: 30,
                CONF_EXPECTED_ANNUAL_RETURN: 6.4,
            }
        )
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(entry.data[CONF_EXPECTED_ANNUAL_RETURN], 6.4)
        self.assertEqual((manager.updates, manager.reloads), (1, 1))

        invalid_flow, invalid_entry, invalid_manager = _flow(entry.data)
        invalid = await invalid_flow.async_step_settings(
            {
                CONF_WALLET_NAME: "Old wallet",
                CONF_BASE_CURRENCY: "EUR",
                CONF_SCAN_INTERVAL: 30,
                CONF_EXPECTED_ANNUAL_RETURN: 100.1,
            }
        )
        self.assertEqual(
            invalid["errors"][CONF_EXPECTED_ANNUAL_RETURN], "invalid_number"
        )
        self.assertEqual(invalid_entry.data[CONF_EXPECTED_ANNUAL_RETURN], 6.4)
        self.assertEqual((invalid_manager.updates, invalid_manager.reloads), (0, 0))


if __name__ == "__main__":
    unittest.main()
