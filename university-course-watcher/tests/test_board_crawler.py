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

    def test_parallel_board_results_preserve_order_and_merge_stats(self) -> None:
        lstBoards = [
            {"university_name": "첫째대학교", "board_type": "공지", "url": "https://first.example"},
            {"university_name": "둘째대학교", "board_type": "공지", "url": "https://second.example"},
        ]
        dictUniversities = {
            "첫째대학교": {"name": "첫째대학교"},
            "둘째대학교": {"name": "둘째대학교"},
        }

        def worker(dictBoard, keyword_hint):
            notice = self._notice(dictBoard["university_name"])
            dictStats = {"details_total": 1, "details_failed": 0, "failed_details": []}
            return [notice], "", dictStats

        self.crawler._crawl_board_worker = Mock(side_effect=worker)

        lstNotices = self.crawler.crawl_boards(lstBoards, dictUniversities)

        self.assertEqual(["첫째대학교", "둘째대학교"], [notice.university_name for notice in lstNotices])
        self.assertEqual(2, self.crawler.last_stats["boards_succeeded"])
        self.assertEqual(2, self.crawler.last_stats["details_total"])

    def test_pagination_config_expands_list_pages(self) -> None:
        board = {
            "url": "https://university.example/notice/list?bbsNo=1000",
            "pagination": {"param": "page", "start": 1, "count": 3},
        }

        lstUrls = self.crawler._list_page_urls(board)

        self.assertEqual(3, len(lstUrls))
        self.assertIn("page=1", lstUrls[0])
        self.assertIn("page=3", lstUrls[2])
        self.assertIn("bbsNo=1000", lstUrls[0])

    def test_explicit_list_pages_are_appended(self) -> None:
        board = {
            "url": "https://university.example/notice/list",
            "list_pages": ["list?page=2", "https://university.example/notice/list?page=3"],
        }

        lstUrls = self.crawler._list_page_urls(board)

        self.assertEqual(
            [
                "https://university.example/notice/list",
                "https://university.example/notice/list?page=2",
                "https://university.example/notice/list?page=3",
            ],
            lstUrls,
        )

    def test_offset_pagination_preserves_existing_query(self) -> None:
        board = {
            "url": "https://university.example/list.do?menu=5",
            "pagination": {"param": "offset", "start": 0, "step": 10, "count": 2},
        }

        lstUrls = self.crawler._list_page_urls(board)

        self.assertIn("menu=5", lstUrls[0])
        self.assertIn("offset=0", lstUrls[0])
        self.assertIn("offset=10", lstUrls[1])

    def test_per_board_max_links_override(self) -> None:
        self.assertEqual(30, self.crawler._board_max_links({"max_links": 30}))
        self.assertEqual(
            self.crawler.max_links_per_board,
            self.crawler._board_max_links({}),
        )

    def test_overrides_disabled_ignores_pagination_and_max_links(self) -> None:
        crawler = BoardCrawler(max_links_per_board=2, allow_board_overrides=False)
        board = {
            "url": "https://university.example/notice/list",
            "pagination": {"param": "page", "start": 1, "count": 5},
            "max_links": 50,
        }

        self.assertEqual(["https://university.example/notice/list"], crawler._list_page_urls(board))
        self.assertEqual(2, crawler._board_max_links(board))

    def test_body_selector_override_is_preferred(self) -> None:
        soup = BeautifulSoup(
            '<div class="custom">모집요강 상세 본문 내용이 충분히 길게 들어 있습니다. 시간제등록 안내.</div>'
            '<div class="content">엉뚱한 본문</div>',
            "html.parser",
        )

        sText = self.crawler._extract_body_text(soup, ".custom")

        self.assertIn("모집요강 상세 본문", sText)

    def test_list_selector_override_scopes_candidates(self) -> None:
        sHtml = """
        <div class="menu"><a href="?articleNo=1">2026학년도 시간제등록 모집</a></div>
        <div class="board"><a href="?articleNo=2">2026학년도 2학기 시간제등록생 모집</a></div>
        """
        soup = BeautifulSoup(sHtml, "html.parser")

        lstRows = self.crawler._extract_candidate_links(soup, self.sBaseUrl, None, ".board")

        self.assertTrue(lstRows)
        self.assertTrue(all("articleNo=2" in row[1] for row in lstRows))

    def _notice(self, sUniversityName):
        from src.board_crawler import CrawledNotice

        return CrawledNotice(
            university_name=sUniversityName,
            board_type="공지",
            title="시간제등록 모집",
            url="https://example.com/article",
            notice_date="2026-06-20",
            body_text="",
            attachment_urls=[],
        )


if __name__ == "__main__":
    unittest.main()
