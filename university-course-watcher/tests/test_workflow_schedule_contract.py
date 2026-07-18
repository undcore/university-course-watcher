from __future__ import annotations

import re
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "daily-check.yml"
KST = ZoneInfo("Asia/Seoul")


class WorkflowScheduleContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_only_schedule_and_manual_events_can_start_the_watcher(self) -> None:
        trigger_section = self.workflow_text.split("permissions:", maxsplit=1)[0]

        self.assertNotRegex(trigger_section, r"(?m)^  push:")
        self.assertRegex(trigger_section, r"(?m)^  schedule:")
        self.assertRegex(trigger_section, r"(?m)^  workflow_dispatch:")

    def test_crons_resolve_to_weekday_0900_and_1900_kst(self) -> None:
        cron_matches = re.findall(r'cron: "(\d+) (\d+) \* \* (\d+)-(\d+)"', self.workflow_text)
        actual_run_times = set()
        monday_utc = datetime(2026, 7, 20, tzinfo=timezone.utc)

        for minute_text, hour_text, first_day_text, last_day_text in cron_matches:
            for day_number in range(int(first_day_text), int(last_day_text) + 1):
                run_utc = monday_utc + timedelta(
                    days=day_number - 1,
                    hours=int(hour_text),
                    minutes=int(minute_text),
                )
                run_kst = run_utc.astimezone(KST)
                actual_run_times.add((run_kst.weekday(), run_kst.hour, run_kst.minute))

        expected_run_times = {
            (weekday, hour, 0)
            for weekday in range(0, 5)
            for hour in (9, 19)
        }
        self.assertEqual(expected_run_times, actual_run_times)

    def test_both_watcher_jobs_depend_on_runtime_guard(self) -> None:
        self.assertIn("python university-course-watcher/src/schedule_policy.py", self.workflow_text)
        self.assertIn("course-check:\n    needs: run-window", self.workflow_text)
        self.assertIn("      - run-window\n      - publish-course-results", self.workflow_text)
        self.assertGreaterEqual(
            self.workflow_text.count("needs.run-window.outputs.should_run == 'true'"),
            2,
        )

    def test_overlapping_workflow_runs_are_serialized(self) -> None:
        self.assertIn("group: university-notice-check-${{ github.ref }}", self.workflow_text)
        self.assertIn("cancel-in-progress: false", self.workflow_text)

    def test_write_permission_is_limited_to_state_and_publish_jobs(self) -> None:
        self.assertIn("permissions:\n  contents: read", self.workflow_text)
        self.assertEqual(4, self.workflow_text.count("      contents: write"))

    def test_failure_notification_rejects_http_errors(self) -> None:
        self.assertIn("curl --fail-with-body", self.workflow_text)


if __name__ == "__main__":
    unittest.main()
