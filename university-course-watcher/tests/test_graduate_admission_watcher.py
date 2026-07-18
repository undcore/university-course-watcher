from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.board_crawler import CrawledNotice, CrawlHealthError
from src.graduate_admission_watcher import GraduateAdmissionWatcher


class GraduateAdmissionClassificationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.watcher = GraduateAdmissionWatcher.__new__(GraduateAdmissionWatcher)

    def test_2027_first_round_recruitment_is_accepted(self) -> None:
        grade, _, _ = self.watcher._classify_notice(
            "2027학년도 전기 일반대학원 신입생 모집요강",
            "일반대학원 원서접수 및 입학전형 안내",
        )

        self.assertEqual("A", grade)

    def test_post_recruitment_and_separate_program_notices_are_excluded(self) -> None:
        titles = [
            "2026학년도 후기 일반대학원 합격자 등록금 안내",
            "2026학년도 후기 일반대학원 면접 일정",
            "2026학년도 후기 추가모집 대학원 수험생 안내문",
            "2026학년도 전반기 계약학과 모집요강",
            "2027학년도 전기 일반대학원 학석사연계과정 모집요강",
        ]

        for title in titles:
            with self.subTest(title=title):
                grade, _, _ = self.watcher._classify_notice(
                    title,
                    "일반대학원 모집요강 원서접수 입학전형",
                )
                self.assertEqual("D", grade)

    def test_unhealthy_board_crawl_is_rejected(self) -> None:
        self.watcher.crawler = SimpleNamespace(
            last_stats={"boards_succeeded": 0, "boards_failed": 2}
        )

        with self.assertRaises(CrawlHealthError):
            self.watcher._trusted_board_notices([])

    def test_failed_detail_is_excluded_from_graduate_results(self) -> None:
        successful = CrawledNotice("A", "board", "ok", "https://example.com/ok", "", "body", [])
        failed = CrawledNotice(
            "B",
            "board",
            "failed",
            "https://example.com/failed",
            "",
            "",
            [],
            detail_succeeded=False,
        )
        self.watcher.crawler = SimpleNamespace(
            last_stats={"boards_succeeded": 2, "boards_failed": 0}
        )

        trusted = self.watcher._trusted_board_notices([successful, failed])

        self.assertEqual([successful], trusted)


if __name__ == "__main__":
    unittest.main()
