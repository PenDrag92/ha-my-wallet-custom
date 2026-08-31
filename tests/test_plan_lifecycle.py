"""Regression tests for savings-plan identity and skipped-period lifecycle."""

from __future__ import annotations

import unittest
from datetime import date

from tests.bootstrap import install_stubs

install_stubs()

from custom_components.my_wallet.const import (  # noqa: E402
    ALLOCATION_MODE_FIXED,
    ALLOCATION_SYMBOL,
    ALLOCATION_VALUE,
    PLAN_ID,
    PLAN_SKIPPED_PERIODS,
)
from custom_components.my_wallet.contributions import make_contribution  # noqa: E402
from custom_components.my_wallet.plans import (  # noqa: E402
    due_dates,
    is_scheduled_period,
    make_plan,
    reactivate_matching_plan,
)


def _plan(
    *,
    plan_id: str,
    amount: float = 25,
    first_date: str = "2026-01-31",
    end_date: str | None = None,
    skipped_periods: list[str] | None = None,
    enabled: bool = True,
) -> dict[str, object]:
    return make_plan(
        name="Monthly",
        first_date=first_date,
        end_date=end_date,
        allocation_mode=ALLOCATION_MODE_FIXED,
        allocations=[
            {ALLOCATION_SYMBOL: "AAA", ALLOCATION_VALUE: amount},
        ],
        plan_id=plan_id,
        skipped_periods=skipped_periods,
        enabled=enabled,
    )


class PlanLifecycleTests(unittest.TestCase):
    def test_identical_recreated_plan_reuses_identity_and_skips(self) -> None:
        retired = _plan(
            plan_id="stable-id",
            skipped_periods=["2026-02"],
        )
        recreated = _plan(plan_id="new-random-id")

        restored, remaining = reactivate_matching_plan(recreated, [retired])

        self.assertEqual(restored[PLAN_ID], "stable-id")
        self.assertEqual(restored[PLAN_SKIPPED_PERIODS], ["2026-02"])
        self.assertEqual(remaining, [])

    def test_changed_definition_stays_a_new_plan(self) -> None:
        retired = _plan(plan_id="old-id", amount=25)
        recreated = _plan(plan_id="new-id", amount=30)

        restored, remaining = reactivate_matching_plan(recreated, [retired])

        self.assertEqual(restored[PLAN_ID], "new-id")
        self.assertEqual([item[PLAN_ID] for item in remaining], ["old-id"])

    def test_paused_plan_can_be_recreated_as_active_without_new_identity(self) -> None:
        retired = _plan(plan_id="stable-id", enabled=False)
        recreated = _plan(plan_id="new-random-id", enabled=True)

        restored, remaining = reactivate_matching_plan(recreated, [retired])

        self.assertEqual(restored[PLAN_ID], "stable-id")
        self.assertTrue(restored["enabled"])
        self.assertEqual(remaining, [])

    def test_recreated_plan_does_not_repeat_booked_or_skipped_months(self) -> None:
        retired = _plan(plan_id="stable-id", skipped_periods=["2026-02"])
        restored, _ = reactivate_matching_plan(
            _plan(plan_id="new-random-id"), [retired]
        )
        contributions = [
            make_contribution(
                25,
                "2026-01-31",
                plan_id="stable-id",
                scheduled_date="2026-01-31",
            )
        ]

        self.assertEqual(
            due_dates(restored, contributions, date(2026, 3, 31)),
            [date(2026, 3, 31)],
        )

    def test_scheduled_period_respects_first_and_end_dates(self) -> None:
        plan = _plan(
            plan_id="bounded",
            first_date="2026-01-31",
            end_date="2026-04-15",
        )

        self.assertFalse(is_scheduled_period(plan, "2025-12"))
        self.assertTrue(is_scheduled_period(plan, "2026-01"))
        self.assertTrue(is_scheduled_period(plan, "2026-02"))
        self.assertTrue(is_scheduled_period(plan, "2026-03"))
        self.assertFalse(is_scheduled_period(plan, "2026-04"))


if __name__ == "__main__":
    unittest.main()
