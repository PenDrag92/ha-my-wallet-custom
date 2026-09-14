"""Validate the document bridge against real Home Assistant and Voluptuous.

Run separately from the stubbed unit suite. No provider or network is contacted.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import voluptuous as vol
import voluptuous_openapi
from homeassistant.components import ai_task

from custom_components.my_wallet.document_api import _extract_with_ai


class DocumentAISmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_signature_nested_schema_and_no_wallet_tool_access(self):
        result = {
            "complete": True,
            "warnings": [],
            "rows": [
                {
                    "id": "synthetic-1",
                    "type": "purchase",
                    "date": "2026-01-03",
                    "amount": "50",
                    "currency": "EUR",
                    "symbol": "AAA",
                    "units": "5",
                    "value_date": "",
                    "note": "",
                    "page": 1,
                    "quote": "synthetic-1 purchase AAA 03.01.2026 5 units EUR 50",
                }
            ],
        }
        with patch.object(ai_task, "async_generate_data", autospec=True) as provider:
            provider.return_value = SimpleNamespace(data=result)
            actual = await _extract_with_ai(
                object(),
                pages=[result["rows"][0]["quote"]],
                entity_id="ai_task.synthetic",
            )
            self.assertEqual(actual, result)
            fields = provider.call_args.kwargs
            self.assertNotIn("llm_api", fields)
            self.assertNotIn("attachments", fields)
            self.assertEqual(fields["entity_id"], "ai_task.synthetic")
            self.assertEqual(fields["structure"](result), result)
            schema = voluptuous_openapi.convert(fields["structure"])
            self.assertEqual(schema["properties"]["rows"]["type"], "array")
            provider.return_value = SimpleNamespace(data={**result, "complete": "yes"})
            with self.assertRaises(vol.Invalid):
                await _extract_with_ai(
                    object(), pages=["synthetic"], entity_id="ai_task.synthetic"
                )


if __name__ == "__main__":
    unittest.main()
