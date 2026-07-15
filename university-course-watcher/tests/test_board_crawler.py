from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

from bs4 import BeautifulSoup


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.board_crawler import BoardCrawler
from src.utils import now_kst


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

    def test_bbs_menu_links_without_detail_identity_are_rejected(self) -> None:
        lstLinks = [
            ("교육과정", "https://university.example/bbs/graduate/curriculum"),
            ("등록 및 장학", "https://university.example/bbs/graduate/scholarship"),
            ("자료실", "https://university.example/bbs/graduate/resources"),
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

    def test_javascript_attachment_links_are_not_requested(self) -> None:
        soup = BeautifulSoup(
            '<a href="javascript:multi_down(51059);">2027 모집요강.hwp</a>'
            '<a href="/files/guide.pdf">모집요강 PDF</a>',
            "html.parser",
        )

        urls = self.crawler._extract_attachment_urls(soup, "https://university.example/notice")

        self.assertEqual(["https://university.example/files/guide.pdf"], urls)

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

        def collect(dictBoard, keyword_hint):
            sUrl = f"https://example.com/{dictBoard['university_name']}"
            return [("시간제등록 모집", sUrl, "2026-06-20")], ""

        def fetch(dictBoard, sTitle, sUrl, sNoticeDate):
            return self._notice(dictBoard["university_name"]), True, ""

        self.crawler._collect_board_candidates = Mock(side_effect=collect)
        self.crawler._fetch_detail = Mock(side_effect=fetch)
        self.crawler.state_cache = Mock()

        lstNotices = self.crawler.crawl_boards(lstBoards, dictUniversities)

        self.assertEqual(["첫째대학교", "둘째대학교"], [notice.university_name for notice in lstNotices])
        self.assertEqual(2, self.crawler.last_stats["boards_succeeded"])
        self.assertEqual(2, self.crawler.last_stats["details_total"])

    def test_board_with_all_failed_details_is_counted_failed_in_crawl_boards(self) -> None:
        lstBoards = [{"university_name": "첫째대학교", "board_type": "공지", "url": "https://first.example"}]
        dictUniversities = {"첫째대학교": {"name": "첫째대학교"}}

        self.crawler._collect_board_candidates = Mock(return_value=([("공고", "https://example.com/1", "")], ""))
        self.crawler._fetch_detail = Mock(return_value=(self._notice("첫째대학교"), False, "detail unavailable"))
        self.crawler.state_cache = Mock()

        lstNotices = self.crawler.crawl_boards(lstBoards, dictUniversities)

        self.assertEqual(1, len(lstNotices))
        self.assertEqual(1, self.crawler.last_stats["boards_failed"])
        self.assertEqual(1, self.crawler.last_stats["details_failed"])
        self.assertIn("All 1 detail pages failed", self.crawler.last_stats["failed_boards"][0]["error"])

    def test_seen_and_stale_candidates_are_skipped_before_fetch(self) -> None:
        crawler = BoardCrawler(skip_urls={"https://example.com/seen"}, max_notice_age_days=7)
        sTodayDate = now_kst().date().isoformat()
        lstCandidates = [
            ("새 공고", "https://example.com/new", sTodayDate),
            ("본 공고", "https://example.com/seen", sTodayDate),
            ("오래된 공고", "https://example.com/old", "2020-01-01"),
            ("날짜 없는 공고", "https://example.com/undated", ""),
        ]

        lstFiltered = crawler._filter_candidates(lstCandidates)

        self.assertEqual(["새 공고", "날짜 없는 공고"], [tupleItem[0] for tupleItem in lstFiltered])
        self.assertEqual(2, crawler.last_stats["details_skipped"])

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
