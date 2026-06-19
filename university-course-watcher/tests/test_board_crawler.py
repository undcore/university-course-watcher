from __future__ import annotations

import sys
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
