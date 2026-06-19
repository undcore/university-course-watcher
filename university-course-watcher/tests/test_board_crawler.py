from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

from bs4 import BeautifulSoup


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.board_crawler import BoardCrawler


class BoardCrawlerLinkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.crawler = BoardCrawler()
        self.sBaseUrl = "https://university.example/notice/list"

    def test_menu_and_board_page_links_are_rejected(self) -> None:
        lstLinks = [
            ("공지사항", "https://university.example/community/notice"),
            ("학사일정", "https://university.example/schedule"),
            ("공지 게시판", self.sBaseUrl),
        ]

        for sTitle, sUrl in lstLinks:
            with self.subTest(sTitle=sTitle):
                self.assertFalse(self.crawler._looks_like_notice_link(sTitle, sUrl, self.sBaseUrl, None))

    def test_detail_and_target_notice_links_are_accepted(self) -> None:
        lstLinks = [
            ("2026학년도 2학기 시간제등록생 모집", "https://university.example/file?id=10"),
            ("2026학년도 학사 안내", "https://university.example/notice?articleNo=20"),
        ]

        for sTitle, sUrl in lstLinks:
            with self.subTest(sTitle=sTitle):
                self.assertTrue(self.crawler._looks_like_notice_link(sTitle, sUrl, self.sBaseUrl, None))

    def test_candidate_dates_are_read_from_each_link_context(self) -> None:
        sHtml = """
        <div class="board-list">
          <div class="row"><a href="?articleNo=1">첫 번째 공고</a><span>2026-06-10</span></div>
          <div class="row"><a href="?articleNo=2">두 번째 공고</a><span>2026-04-03</span></div>
        </div>
        """
        soup = BeautifulSoup(sHtml, "html.parser")

        lstRows = self.crawler._extract_candidate_links(soup, self.sBaseUrl, None)

        self.assertEqual("2026-06-10", lstRows[0][2])
        self.assertEqual("2026-04-03", lstRows[1][2])

    def test_detail_page_uses_only_explicit_notice_date(self) -> None:
        soupLabeled = BeautifulSoup(
            "<div>등록일: 2026-04-03</div><div>접수기간 2026-06-10 ~ 2026-06-20</div>",
            "html.parser",
        )
        soupUnlabeled = BeautifulSoup(
            "<div>접수기간 2026-06-10 ~ 2026-06-20</div>",
            "html.parser",
        )

        self.assertEqual("2026-04-03", self.crawler._extract_notice_date(soupLabeled))
        self.assertEqual("", self.crawler._extract_notice_date(soupUnlabeled))

    def test_candidates_with_dates_are_sorted_newest_first(self) -> None:
        lstCandidates = [
            ("날짜 없음", "https://example.com/0", ""),
            ("오래된 글", "https://example.com/1", "2026-04-03"),
            ("최신 글", "https://example.com/2", "2026-06-20"),
        ]

        lstSelected = self.crawler._select_candidates(lstCandidates)

        self.assertEqual(["최신 글", "오래된 글", "날짜 없음"], [tupleItem[0] for tupleItem in lstSelected])

    def test_all_detail_failures_mark_board_as_failed(self) -> None:
        sListHtml = '<a href="?articleNo=1">2026학년도 시간제등록 모집</a>'
        self.crawler._get_text = Mock(side_effect=[sListHtml, RuntimeError("detail unavailable")])
        dictBoard = {
            "university_name": "테스트대학교",
            "board_type": "공지사항",
            "url": self.sBaseUrl,
        }

        self.crawler.crawl_board(dictBoard)

        self.assertEqual(1, self.crawler.last_stats["details_failed"])
        self.assertIn("All 1 detail pages failed", self.crawler.last_error)


if __name__ == "__main__":
    unittest.main()
