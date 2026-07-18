from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.schedule_policy import should_run


class SchedulePolicyTest(unittest.TestCase):
    def test_friday_to_saturday_kst_boundary(self) -> None:
        friday_2359_kst = datetime(2026, 7, 17, 14, 59, tzinfo=timezone.utc)
        saturday_0000_kst = datetime(2026, 7, 17, 15, 0, tzinfo=timezone.utc)

        self.assertTrue(should_run("schedule", friday_2359_kst))
        self.assertFalse(should_run("schedule", saturday_0000_kst))

    def test_sunday_to_monday_kst_boundary(self) -> None:
        sunday_2359_kst = datetime(2026, 7, 19, 14, 59, tzinfo=timezone.utc)
        monday_0000_kst = datetime(2026, 7, 19, 15, 0, tzinfo=timezone.utc)

        self.assertFalse(should_run("schedule", sunday_2359_kst))
        self.assertTrue(should_run("schedule", monday_0000_kst))

    def test_manual_run_bypasses_weekday_guard(self) -> None:
        saturday_noon_kst = datetime(2026, 7, 18, 3, 0, tzinfo=timezone.utc)

        self.assertTrue(should_run("workflow_dispatch", saturday_noon_kst))

    def test_unexpected_automatic_event_is_rejected(self) -> None:
        monday_noon_kst = datetime(2026, 7, 20, 3, 0, tzinfo=timezone.utc)

        self.assertFalse(should_run("push", monday_noon_kst))

    def test_naive_datetime_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            should_run("schedule", datetime(2026, 7, 20, 0, 0))


if __name__ == "__main__":
    unittest.main()
