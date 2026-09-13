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

    def test_delayed_friday_evening_run_still_counts_as_friday(self) -> None:
        # 2026-08-28(금) 19:00 KST 예약이 토요일 06:08 KST에 시작돼 통째로 건너뛰어진 사례
        saturday_0608_kst = datetime(2026, 8, 28, 21, 8, tzinfo=timezone.utc)

        self.assertFalse(should_run("schedule", saturday_0608_kst))
        self.assertTrue(should_run("schedule", saturday_0608_kst, schedule="0 10 * * 1-5"))

    def test_delayed_monday_morning_run_keeps_monday_slot(self) -> None:
        monday_1110_kst = datetime(2026, 9, 14, 2, 10, tzinfo=timezone.utc)

        self.assertTrue(should_run("schedule", monday_1110_kst, schedule="0 0 * * 1-5"))

    def test_0837_kst_slot_scheduled_on_previous_utc_day_counts_as_kst_weekday(self) -> None:
        cron_0837_kst = "37 23 * * 0-4"
        # 월 08:37 KST 예약(일 23:37 UTC)이 월 10:10 KST에 늦게 시작
        monday_1010_kst = datetime(2026, 9, 14, 1, 10, tzinfo=timezone.utc)
        # 금 08:37 KST 예약(목 23:37 UTC)이 금 23:50 KST까지 밀림
        friday_2350_kst = datetime(2026, 9, 18, 14, 50, tzinfo=timezone.utc)

        self.assertTrue(should_run("schedule", monday_1010_kst, schedule=cron_0837_kst))
        self.assertTrue(should_run("schedule", friday_2350_kst, schedule=cron_0837_kst))

    def test_delayed_1837_kst_friday_slot_counts_as_friday(self) -> None:
        saturday_0310_kst = datetime(2026, 9, 18, 18, 10, tzinfo=timezone.utc)

        self.assertTrue(should_run("schedule", saturday_0310_kst, schedule="37 9 * * 1-5"))

    def test_unparseable_schedule_falls_back_to_start_time(self) -> None:
        saturday_noon_kst = datetime(2026, 7, 18, 3, 0, tzinfo=timezone.utc)

        self.assertFalse(should_run("schedule", saturday_noon_kst, schedule="*/5 * * * *"))

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
