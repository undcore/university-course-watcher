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
)
DURABLE_GRADUATE_STATE = (
    "university-course-watcher/data/seen_graduate_admission_urls.json",
    "university-course-watcher/data/graduate_admission_summary_state.json",
)
REGENERABLE_HTTP_STATE = (
    "university-course-watcher/data/course_http_state.json",
    "university-course-watcher/data/graduate_http_state.json",
)


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

        for state_path in (*DURABLE_COURSE_STATE, *DURABLE_GRADUATE_STATE):
            self.assertNotIn(state_path, cache_text)

        for state_path in REGENERABLE_HTTP_STATE:
            self.assertIn(state_path, cache_text)

    def test_course_state_is_uploaded_and_committed_with_course_results(self) -> None:
        for state_path in DURABLE_COURSE_STATE:
            self.assertGreaterEqual(self.workflow_text.count(state_path), 3)

        self.assertGreaterEqual(
            self.workflow_text.count("university-course-watcher/data/university_history.csv"),
            3,
        )

    def test_graduate_state_is_uploaded_and_committed_with_results(self) -> None:
        for state_path in DURABLE_GRADUATE_STATE:
            self.assertGreaterEqual(self.workflow_text.count(state_path), 3)

    def test_queued_runs_refresh_state_from_the_latest_branch_tip(self) -> None:
        self.assertGreaterEqual(
            self.workflow_text.count('git fetch origin "${GITHUB_REF_NAME}"'),
            2,
        )
        self.assertEqual(2, self.workflow_text.count('git checkout "origin/${GITHUB_REF_NAME}" --'))

    def test_partial_delivery_state_is_published_after_watcher_failure(self) -> None:
        self.assertIn("if: always() && needs.course-check.result != 'cancelled'", self.workflow_text)
        self.assertIn(
            "if: always() && needs.graduate-admission-check.result != 'cancelled'",
            self.workflow_text,
        )
        self.assertGreaterEqual(self.workflow_text.count("if: always() && (github.event_name"), 2)

    def test_course_bootstrap_state_covers_the_published_result_snapshot(self) -> None:
        data_dir = REPOSITORY_ROOT / "university-course-watcher" / "data"
        results = json.loads((data_dir / "results.json").read_text(encoding="utf-8-sig"))
        seen_urls = set(json.loads((data_dir / "seen_urls.json").read_text(encoding="utf-8")))
        notice_state = json.loads((data_dir / "notice_state.json").read_text(encoding="utf-8"))
        result_urls = {item["url"] for item in results if item.get("url")}

        self.assertTrue(result_urls.issubset(seen_urls))
        self.assertTrue(result_urls.issubset(notice_state))

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
