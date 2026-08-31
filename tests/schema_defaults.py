"""Exercise real Voluptuous defaults, separate from the dependency-stub tests."""

from __future__ import annotations

from datetime import date

import voluptuous as real_vol

from tests.test_options_regressions import config_flow


def main():
    config_flow.vol = real_vol
    config_flow._DATE_SELECTOR = lambda value: date.fromisoformat(value).isoformat()
    config_flow._CONTRIBUTION_AMOUNT_SELECTOR = lambda value: float(value)
    config_flow._ALLOCATION_MODE_SELECTOR = str
    schema = config_flow._plan_schema()
    result = schema({"name": "Default date check", "amount": 75})
    assert result["first_date"] == "2026-08-31"
    assert "end_date" not in result
    assert result["opening_included"] is False
    contribution = config_flow._contribution_schema()({"amount": 75})
    assert contribution["date"] == "2026-08-31"
    print(
        "Real Voluptuous: required date defaults are populated; "
        "optional dates stay empty."
    )


if __name__ == "__main__":
    main()
