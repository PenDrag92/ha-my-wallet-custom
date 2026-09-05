"""Exercise real Voluptuous defaults, separate from the dependency-stub tests."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import patch

import voluptuous as real_vol

from custom_components.my_wallet import flow_schemas


def main():
    flow_schemas.vol = real_vol
    flow_schemas._DATE_SELECTOR = lambda value: date.fromisoformat(value).isoformat()
    flow_schemas._CONTRIBUTION_AMOUNT_SELECTOR = lambda value: float(value)
    flow_schemas._ALLOCATION_MODE_SELECTOR = str
    with patch.object(flow_schemas.dt_util, "now", return_value=datetime(2026, 8, 31)):
        schema = flow_schemas._plan_schema()
        result = schema({"name": "Default date check", "amount": 75})
        assert result["first_date"] == "2026-08-31"
        assert "end_date" not in result
        assert result["opening_included"] is False
        contribution = flow_schemas._contribution_schema()({"amount": 75})
        assert contribution["date"] == "2026-08-31"
    print(
        "Real Voluptuous: required date defaults are populated; "
        "optional dates stay empty."
    )


if __name__ == "__main__":
    main()
