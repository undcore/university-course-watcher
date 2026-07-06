from __future__ import annotations

import sys
import unittest
from pathlib import Path

from bs4 import BeautifulSoup


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.board_crawler import BoardCrawler


class BoardCrawlerConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.crawler = BoardCrawler()
        self.base_url = "https://university.example/notice/list"

    def test_pagination_config_expands_list_pages(self) -> None:
        board = {
            "url": "https://university.example/notice/list?bbsNo=1000",
            "pagination": {"param": "page", "start": 1, "count": 3},
        }

        urls = self.crawler._list_page_urls(board)

        self.assertEqual(3, len(urls))
        self.assertIn("page=1", urls[0])
        self.assertIn("page=3", urls[2])
        self.assertIn("bbsNo=1000", urls[0])

    def test_offset_pagination_preserves_existing_query(self) -> None:
        board = {
            "url": "https://university.example/list.do?menu=5",
            "pagination": {"param": "offset", "start": 0, "step": 10, "count": 2},
        }

        urls = self.crawler._list_page_urls(board)

        self.assertIn("menu=5", urls[0])
        self.assertIn("offset=0", urls[0])
        self.assertIn("offset=10", urls[1])

    def test_explicit_list_pages_are_appended(self) -> None:
        board = {
            "url": "https://university.example/notice/list",
            "list_pages": ["list?page=2", "https://university.example/notice/list?page=3"],
        }

        urls = self.crawler._list_page_urls(board)

        self.assertEqual(
            [
                "https://university.example/notice/list",
                "https://university.example/notice/list?page=2",
                "https://university.example/notice/list?page=3",
            ],
            urls,
        )

    def test_per_board_max_links_override(self) -> None:
        self.assertEqual(30, self.crawler._board_max_links({"max_links": 30}))
        self.assertEqual(self.crawler.max_links_per_board, self.crawler._board_max_links({}))

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

        text = self.crawler._extract_body_text(soup, ".custom")

        self.assertIn("모집요강 상세 본문", text)

    def test_list_selector_override_scopes_candidates(self) -> None:
        html = """
        <div class="menu"><a href="?articleNo=1">2026학년도 시간제등록 모집</a></div>
        <div class="board"><a href="?articleNo=2">2026학년도 2학기 시간제등록생 모집</a></div>
        """
        soup = BeautifulSoup(html, "html.parser")

        rows = self.crawler._extract_candidate_links(soup, self.base_url, None, ".board")

        self.assertTrue(rows)
        self.assertTrue(all("articleNo=2" in row[1] for row in rows))


if __name__ == "__main__":
    unittest.main()
