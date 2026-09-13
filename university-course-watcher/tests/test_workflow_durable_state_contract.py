from __future__ import annotations

import re
import unittest
import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "daily-check.yml"

DURABLE_COURSE_STATE = (
    "university-course-watcher/data/seen_urls.json",
    "university-course-watcher/data/notice_state.json",
    "university-course-watcher/data/course_delivery_outbox.json",
)
DURABLE_GRADUATE_STATE = (
    "university-course-watcher/data/seen_graduate_admission_urls.json",
    "university-course-watcher/data/graduate_admission_summary_state.json",
    "university-course-watcher/data/graduate_delivery_outbox.json",
)
COURSE_HTTP_STATE = "university-course-watcher/data/course_http_state.json"
GRADUATE_HTTP_STATE = "university-course-watcher/data/graduate_http_state.json"


class WorkflowDurableStateContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.cache_blocks = re.findall(
            r"uses: actions/cache@[^\s]+(?:\s+#\s+v[^\s]+)?\n"
            r"(?P<block>(?:\s{8,}.*\n)+)",
            self.workflow_text,
        )

    def test_notification_history_is_not_stored_in_an_actions_cache(self) -> None:
        cache_text = "\n".join(self.cache_blocks)

        for state_path in DURABLE_GRADUATE_STATE:
            self.assertNotIn(state_path, cache_text)

        self.assertIn(GRADUATE_HTTP_STATE, cache_text)

    def test_only_weekday_schedule_and_manual_dispatch_can_trigger(self) -> None:
        self.assertIn('cron: "37 23 * * 0-4"', self.workflow_text)
        self.assertIn('cron: "37 9 * * 1-5"', self.workflow_text)
        self.assertIn("workflow_dispatch:", self.workflow_text)
        self.assertNotRegex(self.workflow_text, r"(?m)^\s{2}push:")
        self.assertNotRegex(self.workflow_text, r"(?m)^\s{2}pull_request:")

    def test_runtime_window_gates_the_graduate_watcher(self) -> None:
        self.assertIn("graduate-admission-check:\n    needs: run-window\n", self.workflow_text)
        self.assertEqual(
            1,
            self.workflow_text.count("needs.run-window.outputs.should_run == 'true'"),
        )

    def test_stopped_course_watcher_no_longer_touches_course_state(self) -> None:
        for state_path in (*DURABLE_COURSE_STATE, COURSE_HTTP_STATE):
            self.assertNotIn(state_path, self.workflow_text)
        self.assertNotIn("university-course-watcher/data/university_history.csv", self.workflow_text)
        self.assertNotIn("tesseract-ocr", self.workflow_text)

    def test_workflow_and_publish_concurrency_are_serialized_without_cancellation(self) -> None:
        self.assertIn("group: university-notice-check-${{ github.ref }}", self.workflow_text)
        self.assertEqual(
            1,
            self.workflow_text.count("group: watcher-report-publish-${{ github.ref }}"),
        )
        self.assertEqual(2, self.workflow_text.count("cancel-in-progress: false"))

    def test_permissions_and_job_timeouts_are_explicit(self) -> None:
        self.assertIn("permissions:\n  contents: read", self.workflow_text)
        self.assertEqual(2, self.workflow_text.count("      contents: write"))
        self.assertEqual(4, self.workflow_text.count("timeout-minutes:"))

    def test_graduate_state_is_uploaded_and_committed_with_results(self) -> None:
        for state_path in DURABLE_GRADUATE_STATE:
            self.assertGreaterEqual(self.workflow_text.count(state_path), 3)

    def test_queued_runs_refresh_state_from_the_latest_branch_tip(self) -> None:
        self.assertGreaterEqual(
            self.workflow_text.count('git fetch origin "${GITHUB_REF_NAME}"'),
            2,
        )
        self.assertEqual(1, self.workflow_text.count('git checkout "origin/${GITHUB_REF_NAME}" --'))
        self.assertIn(
            'git checkout "origin/${GITHUB_REF_NAME}" -- \\\n'
            "            university-course-watcher/data/seen_graduate_admission_urls.json",
            self.workflow_text,
        )

    def test_partial_delivery_state_is_published_after_watcher_failure(self) -> None:
        self.assertIn(
            "if: always() && (needs.graduate-admission-check.result == 'success' || "
            "needs.graduate-admission-check.result == 'failure')",
            self.workflow_text,
        )
        self.assertGreaterEqual(self.workflow_text.count("if: always() && (github.event_name"), 1)

    def test_skipped_weekend_checks_cannot_start_publish_jobs(self) -> None:
        self.assertNotIn("result != 'cancelled'", self.workflow_text)
        self.assertIn("needs.graduate-admission-check.result == 'success' || needs.graduate-admission-check.result == 'failure'", self.workflow_text)

    def test_read_only_jobs_do_not_retain_checkout_credentials(self) -> None:
        self.assertEqual(1, self.workflow_text.count("persist-credentials: false"))

    def test_delivery_state_is_pushed_before_telegram_delivery(self) -> None:
        self.assertEqual(1, self.workflow_text.count('DELIVERY_STATE_PUSH_ENABLED: "true"'))
        self.assertIn(
            "graduate-admission-check:\n    needs: run-window\n"
            "    if: needs.run-window.outputs.should_run == 'true'\n"
            "    permissions:\n      contents: write",
            self.workflow_text,
        )

    def test_result_artifacts_fail_closed_and_expire(self) -> None:
        self.assertEqual(2, self.workflow_text.count("if-no-files-found: error"))
        self.assertEqual(2, self.workflow_text.count("retention-days: 14"))

    def test_failure_notification_does_not_retry_ambiguous_post(self) -> None:
        self.assertNotIn("--retry-all-errors", self.workflow_text)
        self.assertIn("--connect-timeout 10 --max-time 30", self.workflow_text)

    def test_graduate_bootstrap_state_covers_the_published_result_snapshot(self) -> None:
        data_dir = REPOSITORY_ROOT / "university-course-watcher" / "data"
        results = json.loads(
            (data_dir / "graduate_admission_results.json").read_text(encoding="utf-8-sig")
        )
        seen_fingerprints = json.loads(
            (data_dir / "seen_graduate_admission_urls.json").read_text(encoding="utf-8")
        )
        summary_state = json.loads(
            (data_dir / "graduate_admission_summary_state.json").read_text(encoding="utf-8")
        )

        self.assertGreaterEqual(len(seen_fingerprints), len(results))
        self.assertEqual(len(results), summary_state["candidate_count"])
        self.assertIn("fingerprint", summary_state)


if __name__ == "__main__":
    unittest.main()
