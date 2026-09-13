from __future__ import annotations

import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.board_crawler import CrawledNotice, CrawlHealthError
from src.graduate_admission_watcher import (
    GraduateAdmissionWatcher,
    recruitment_year_hint,
    select_region_universities,
    target_years,
)
from src.utils import CONFIG_DIR, load_json

KST = ZoneInfo("Asia/Seoul")


class GraduateAdmissionClassificationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.watcher = GraduateAdmissionWatcher.__new__(GraduateAdmissionWatcher)
        now_patch = patch(
            "src.graduate_admission_watcher.now_kst",
            return_value=datetime(2026, 9, 14, 9, 0, tzinfo=KST),
        )
        now_patch.start()
        self.addCleanup(now_patch.stop)

    def test_2027_first_round_recruitment_is_accepted(self) -> None:
        grade, _, _ = self.watcher._classify_notice(
            "2027학년도 전기 일반대학원 신입생 모집요강",
            "일반대학원 원서접수 및 입학전형 안내",
        )

        self.assertEqual("A", grade)

    def test_catholic_songsim_recruitment_titles_are_accepted(self) -> None:
        # gs.catholic.ac.kr 모집요강 게시판에서 실제로 쓰인 제목 형식들 (띄어쓰기 변형 포함)
        titles = [
            "[모집요강] 2027학년도 전기 1차 일반전형 신입생 모집안내",
            "2027학년도 전기 1차 일반 전형 모집 요강",
            "2027학년도 전기 2차 일반전형 모집요강",
        ]

        for title in titles:
            with self.subTest(title=title):
                grade, _, _ = self.watcher._classify_notice(title, "가톨릭대학교 일반대학원 입학 안내")
                self.assertEqual("A", grade)

    def test_target_years_follow_the_calendar(self) -> None:
        self.assertEqual(["2026", "2027"], target_years(date(2026, 9, 14)))
        self.assertEqual(["2027", "2028"], target_years(date(2027, 9, 1)))
        self.assertEqual("2027", recruitment_year_hint(date(2026, 9, 14)))
        self.assertEqual("2027", recruitment_year_hint(date(2027, 3, 2)))

    def test_always_watched_university_survives_region_filter(self) -> None:
        universities = [
            {"name": "서울대학교", "region": "seoul"},
            {"name": "아주대학교", "region": "gyeonggi"},
            {"name": "가톨릭대학교", "region": "gyeonggi", "graduate_watch_always": True},
        ]

        selected = select_region_universities(universities, "seoul")

        self.assertEqual(["서울대학교", "가톨릭대학교"], [item["name"] for item in selected])

    def test_catholic_university_is_configured_for_graduate_watch(self) -> None:
        universities = load_json(CONFIG_DIR / "universities.json", [])
        boards = load_json(CONFIG_DIR / "graduate_admission_boards.json", [])
        catholic = [item for item in universities if item["name"] == "가톨릭대학교"]
        catholic_boards = [
            board for board in boards
            if board["university_name"] == "가톨릭대학교" and board.get("enabled", True)
        ]

        self.assertTrue(catholic and catholic[0].get("graduate_watch_always"))
        self.assertEqual(
            {
                "https://gs.catholic.ac.kr/gs/admission/recruitment.do",
                "https://gs.catholic.ac.kr/gs/graduate/notice.do",
            },
            {board["url"] for board in catholic_boards},
        )

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
