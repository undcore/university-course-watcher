from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.exceptions import SSLError
from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

from .utils import normalize_space

LOGGER = logging.getLogger(__name__)
HTML_PARSER = "html.parser"


@dataclass
class CrawledNotice:
    university_name: str
    board_type: str
    title: str
    url: str
    notice_date: str
    body_text: str
    attachment_urls: list[str]


class BoardCrawler:
    def __init__(self, timeout: int = 8, max_links_per_board: int = 15):
        self.timeout = timeout
        self.max_links_per_board = max_links_per_board
        self.session = requests.Session()
        self.last_error = ""
        self.last_stats = {
            "boards_total": 0,
            "boards_succeeded": 0,
            "boards_failed": 0,
            "boards_skipped": 0,
            "failed_boards": [],
        }
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 university-course-watcher/1.0 (official-board-crawler)",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
            }
        )

    def crawl_boards(self, boards: list[dict], universities: dict[str, dict], keyword_hint: str | None = None) -> list[CrawledNotice]:
        notices: list[CrawledNotice] = []
        self.last_stats = {
            "boards_total": 0,
            "boards_succeeded": 0,
            "boards_failed": 0,
            "boards_skipped": 0,
            "failed_boards": [],
        }

        for board in boards:
            self.last_stats["boards_total"] += 1

            if not board.get("enabled", True):
                self.last_stats["boards_skipped"] += 1
                continue

            university = universities.get(board["university_name"])
            if not university:
                LOGGER.warning("Unknown university in board config: %s", board.get("university_name"))
                self.last_stats["boards_skipped"] += 1
                continue

            board_notices = self.crawl_board(board, keyword_hint=keyword_hint)

            if self.last_error:
                self.last_stats["boards_failed"] += 1
                self.last_stats["failed_boards"].append({
                    "university_name": board.get("university_name", ""),
                    "board_type": board.get("board_type", ""),
                    "url": board.get("url", ""),
                    "error": self.last_error,
                })
            else:
                self.last_stats["boards_succeeded"] += 1

            notices.extend(board_notices)

        return notices

    def crawl_board(self, board: dict, keyword_hint: str | None = None) -> list[CrawledNotice]:
        url = board["url"]
        self.last_error = ""

        try:
            html = self._get_text(url)
        except Exception as exc:
            self.last_error = str(exc)
            LOGGER.warning("Board fetch failed: %s %s", url, exc)
            return []

        soup = BeautifulSoup(html, HTML_PARSER)
        candidates = self._extract_candidate_links(soup, url, keyword_hint)
        notices: list[CrawledNotice] = []
        for title, detail_url, notice_date in candidates[: self.max_links_per_board]:
            try:
                detail_html = self._get_text(detail_url)
                detail_soup = BeautifulSoup(detail_html, HTML_PARSER)
                body_text = self._extract_body_text(detail_soup)
                attachments = self._extract_attachment_urls(detail_soup, detail_url)
            except Exception as exc:
                LOGGER.debug("Detail fetch failed: %s %s", detail_url, exc)
                body_text = ""
                attachments = []
            notices.append(
                CrawledNotice(
                    university_name=board["university_name"],
                    board_type=board["board_type"],
                    title=title,
                    url=detail_url,
                    notice_date=notice_date,
                    body_text=body_text,
                    attachment_urls=attachments,
                )
            )
        return notices

    def _get_text(self, url: str) -> str:
        try:
            response = self.session.get(url, timeout=self.timeout)
        except SSLError:
            LOGGER.info("SSL verification failed; retrying without verification: %s", url)
            response = self.session.get(url, timeout=self.timeout, verify=False)
        response.raise_for_status()
        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding
        return response.text

    def _extract_candidate_links(self, soup: BeautifulSoup, base_url: str, keyword_hint: str | None) -> list[tuple[str, str, str]]:
        rows: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for container in soup.select("table tr, ul li, ol li, div, article"):
            links = container.find_all("a", href=True)
            if not links:
                continue
            text = normalize_space(container.get_text(" "))
            date = self._find_date(text)
            for a in links:
                title = normalize_space(a.get_text(" ") or a.get("title") or text)
                href = a.get("href", "")
                full_url = urljoin(base_url, href)
                if not self._looks_like_notice_link(title, full_url, base_url, keyword_hint):
                    continue
                key = full_url.split("#")[0]
                if key in seen:
                    continue
                seen.add(key)
                rows.append((title[:250], key, date))

        if rows:
            return rows

        for a in soup.find_all("a", href=True):
            title = normalize_space(a.get_text(" ") or a.get("title"))
            full_url = urljoin(base_url, a["href"])
            if self._looks_like_notice_link(title, full_url, base_url, keyword_hint):
                rows.append((title[:250], full_url.split("#")[0], ""))
        return rows

    def _looks_like_notice_link(self, title: str, url: str, base_url: str, keyword_hint: str | None) -> bool:
        if not title or len(title) < 3:
            return False
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        if urlparse(base_url).netloc not in parsed.netloc and not parsed.netloc.endswith(urlparse(base_url).netloc):
            return False
        lowered = url.lower()
        if any(ext in lowered for ext in [".pdf", ".hwp", ".hwpx", ".doc", ".docx", ".xls", ".xlsx", ".zip"]):
            return False
        noisy = ["로그인", "회원가입", "개인정보", "이메일", "사이트맵", "찾아오시는", "facebook", "instagram"]
        if any(word.lower() in title.lower() for word in noisy):
            return False
        if keyword_hint and keyword_hint.lower() in title.lower():
            return True
        return bool(re.search(r"(notice|board|bbs|article|view|ntt|seq|mode=view|wr_id|공지|모집|학사|입학)", lowered + " " + title))

    def _extract_body_text(self, soup: BeautifulSoup) -> str:
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        selectors = [".view", ".board_view", ".bbs-view", ".article", ".content", "#content", "main"]
        for selector in selectors:
            node = soup.select_one(selector)
            if node:
                text = normalize_space(node.get_text(" "))
                if len(text) > 80:
                    return text[:10000]
        return normalize_space(soup.get_text(" "))[:10000]

    def _extract_attachment_urls(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        urls: list[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = normalize_space(a.get_text(" "))
            lowered = (href + " " + text).lower()
            if any(ext in lowered for ext in [".pdf", ".hwp", ".hwpx", ".doc", ".docx", ".xls", ".xlsx", ".zip", "download"]):
                urls.append(urljoin(base_url, href))
        return list(dict.fromkeys(urls))

    def _find_date(self, text: str) -> str:
        match = re.search(r"(20\d{2})[.\-/년 ]+\s*(\d{1,2})[.\-/월 ]+\s*(\d{1,2})", text)
        if match:
            y, m, d = match.groups()
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        match = re.search(r"(\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})", text)
        if match:
            y, m, d = match.groups()
            return f"20{int(y):02d}-{int(m):02d}-{int(d):02d}"
        return ""
