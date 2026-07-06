from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

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
    def __init__(self, timeout: int = 8, max_links_per_board: int = 15, allow_board_overrides: bool = True):
        self.timeout = timeout
        self.max_links_per_board = max_links_per_board
        self.allow_board_overrides = allow_board_overrides
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 university-course-watcher/1.0 (official-board-crawler)",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
            }
        )

    def crawl_boards(self, boards: list[dict], universities: dict[str, dict], keyword_hint: str | None = None) -> list[CrawledNotice]:
        notices: list[CrawledNotice] = []
        for board in boards:
            if not board.get("enabled", True):
                continue
            university = universities.get(board["university_name"])
            if not university:
                LOGGER.warning("Unknown university in board config: %s", board.get("university_name"))
                continue
            notices.extend(self.crawl_board(board, keyword_hint=keyword_hint))
        return notices

    def crawl_board(self, board: dict, keyword_hint: str | None = None) -> list[CrawledNotice]:
        selectors = self._board_selectors(board)
        max_links = self._board_max_links(board)
        list_urls = self._list_page_urls(board)

        candidates: list[tuple[str, str, str]] = []
        seen_keys: set[str] = set()
        for list_url in list_urls:
            try:
                html = self._get_text(list_url)
            except Exception as exc:
                LOGGER.warning("Board fetch failed: %s %s", list_url, exc)
                continue

            soup = BeautifulSoup(html, HTML_PARSER)
            for candidate in self._extract_candidate_links(soup, list_url, keyword_hint, selectors.get("list")):
                if candidate[1] in seen_keys:
                    continue
                seen_keys.add(candidate[1])
                candidates.append(candidate)

        notices: list[CrawledNotice] = []
        for title, detail_url, notice_date in candidates[:max_links]:
            try:
                detail_html = self._get_text(detail_url)
                detail_soup = BeautifulSoup(detail_html, HTML_PARSER)
                body_text = self._extract_body_text(detail_soup, selectors.get("body"))
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

    def _board_selectors(self, board: dict) -> dict:
        selectors = board.get("selectors")
        return selectors if isinstance(selectors, dict) else {}

    def _board_max_links(self, board: dict) -> int:
        if not self.allow_board_overrides:
            return self.max_links_per_board
        try:
            override = int(board.get("max_links", self.max_links_per_board))
        except (TypeError, ValueError):
            return self.max_links_per_board
        return max(1, override)

    def _list_page_urls(self, board: dict) -> list[str]:
        base = board["url"]
        pagination = board.get("pagination") if self.allow_board_overrides else None

        if isinstance(pagination, dict) and pagination.get("param"):
            try:
                count = max(1, int(pagination.get("count", 1)))
                start = int(pagination.get("start", 1))
                step = int(pagination.get("step", 1))
            except (TypeError, ValueError):
                urls = [base]
            else:
                param = str(pagination["param"])
                urls = [self._set_query_param(base, param, str(start + index * step)) for index in range(count)]
        else:
            urls = [base]

        if self.allow_board_overrides:
            for extra in board.get("list_pages", []) or []:
                urls.append(urljoin(base, str(extra)))

        return list(dict.fromkeys(urls))

    def _set_query_param(self, url: str, key: str, value: str) -> str:
        parsed = urlparse(url)
        query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != key]
        query.append((key, value))
        return urlunparse(parsed._replace(query=urlencode(query)))

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

    def _extract_candidate_links(
        self,
        soup: BeautifulSoup,
        base_url: str,
        keyword_hint: str | None,
        list_selector: str | None = None,
    ) -> list[tuple[str, str, str]]:
        rows: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        container_selector = list_selector or "table tr, ul li, ol li, div, article"
        for container in soup.select(container_selector):
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

    def _extract_body_text(self, soup: BeautifulSoup, body_selector: str | None = None) -> str:
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        selectors = [".view", ".board_view", ".bbs-view", ".article", ".content", "#content", "main"]
        if body_selector:
            selectors = [body_selector] + selectors
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
