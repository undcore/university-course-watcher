from __future__ import annotations

import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import timedelta
from itertools import zip_longest
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from requests.exceptions import SSLError
from urllib3.exceptions import InsecureRequestWarning
from urllib3.util.retry import Retry

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

from .http_state import HttpStateCache
from .utils import DATA_DIR, normalize_space, now_kst

LOGGER = logging.getLogger(__name__)
HTML_PARSER = "lxml"

BOARD_WORKER_CAP = 8
DETAIL_WORKER_CAP = 12
PER_HOST_CONCURRENCY = 2


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
    def __init__(
        self,
        timeout: int = 8,
        max_links_per_board: int = 15,
        state_cache: HttpStateCache | None = None,
        skip_urls: set[str] | None = None,
        max_notice_age_days: int | None = None,
    ):
        self.timeout = timeout
        self.max_links_per_board = max_links_per_board
        self.state_cache = state_cache or HttpStateCache(DATA_DIR / "course_http_state.json")
        self.skip_urls = set(skip_urls or ())
        self.max_notice_age_days = max_notice_age_days
        self.last_error = ""
        self.last_stats = self._empty_stats()
        self._thread_local = threading.local()
        self._host_semaphores: dict[str, threading.BoundedSemaphore] = {}
        self._host_semaphore_lock = threading.Lock()

    def _empty_stats(self) -> dict:
        return {
            "boards_total": 0,
            "boards_succeeded": 0,
            "boards_failed": 0,
            "boards_skipped": 0,
            "details_total": 0,
            "details_failed": 0,
            "details_skipped": 0,
            "failed_boards": [],
            "failed_details": [],
        }

    def _session(self) -> requests.Session:
        session = getattr(self._thread_local, "session", None)

        if session is None:
            session = requests.Session()
            session.headers.update(
                {
                    "User-Agent": "Mozilla/5.0 university-course-watcher/1.0 (official-board-crawler)",
                    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
                }
            )
            retry = Retry(
                total=2,
                connect=1,
                read=1,
                status=2,
                backoff_factor=0.5,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET"],
                raise_on_status=False,
            )
            session.mount("http://", HTTPAdapter(max_retries=retry))
            session.mount("https://", HTTPAdapter(max_retries=retry))
            self._thread_local.session = session

        return session

    def _host_semaphore(self, url: str) -> threading.BoundedSemaphore:
        sHost = urlparse(url).netloc

        with self._host_semaphore_lock:
            semaphore = self._host_semaphores.get(sHost)
            if semaphore is None:
                semaphore = threading.BoundedSemaphore(PER_HOST_CONCURRENCY)
                self._host_semaphores[sHost] = semaphore

        return semaphore

    def crawl_boards(self, boards: list[dict], universities: dict[str, dict], keyword_hint: str | None = None) -> list[CrawledNotice]:
        self.last_stats = self._empty_stats()
        lstActiveBoards: list[dict] = []

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

            lstActiveBoards.append(board)

        if not lstActiveBoards:
            return []

        iBoardWorkerCount = min(BOARD_WORKER_CAP, len(lstActiveBoards))

        with ThreadPoolExecutor(max_workers=iBoardWorkerCount) as executor:
            lstCollected = list(executor.map(
                lambda dictBoard: self._collect_board_candidates(dictBoard, keyword_hint),
                lstActiveBoards,
            ))

        lstJobGroups: list[list[tuple[int, dict, tuple[str, str, str]]]] = []

        for iBoardIndex, (dictBoard, (lstCandidates, sBoardError)) in enumerate(zip(lstActiveBoards, lstCollected)):
            if sBoardError:
                self.last_stats["boards_failed"] += 1
                self.last_stats["failed_boards"].append({
                    "university_name": dictBoard.get("university_name", ""),
                    "board_type": dictBoard.get("board_type", ""),
                    "url": dictBoard.get("url", ""),
                    "error": sBoardError,
                })
                continue

            lstJobGroups.append([
                (iBoardIndex, dictBoard, tupleCandidate)
                for tupleCandidate in lstCandidates
            ])

        lstDetailJobs = [
            tupleJob
            for tupleRound in zip_longest(*lstJobGroups)
            for tupleJob in tupleRound
            if tupleJob is not None
        ] if lstJobGroups else []

        lstDetailResults: list[tuple[CrawledNotice, bool, str]] = []

        if lstDetailJobs:
            iDetailWorkerCount = min(DETAIL_WORKER_CAP, len(lstDetailJobs))

            with ThreadPoolExecutor(max_workers=iDetailWorkerCount) as executor:
                lstDetailResults = list(executor.map(
                    lambda tupleJob: self._fetch_detail(tupleJob[1], *tupleJob[2]),
                    lstDetailJobs,
                ))

        dictBoardNotices: dict[int, list[CrawledNotice]] = {}
        dictBoardSuccessCounts: dict[int, int] = {}

        for (iBoardIndex, dictBoard, _), (notice, bSucceeded, sDetailError) in zip(lstDetailJobs, lstDetailResults):
            self.last_stats["details_total"] += 1

            if bSucceeded:
                dictBoardSuccessCounts[iBoardIndex] = dictBoardSuccessCounts.get(iBoardIndex, 0) + 1
            else:
                self.last_stats["details_failed"] += 1
                self.last_stats["failed_details"].append({
                    "university_name": dictBoard.get("university_name", ""),
                    "board_type": dictBoard.get("board_type", ""),
                    "url": notice.url,
                    "error": sDetailError,
                })

            dictBoardNotices.setdefault(iBoardIndex, []).append(notice)

        notices: list[CrawledNotice] = []

        for iBoardIndex, (dictBoard, (lstCandidates, sBoardError)) in enumerate(zip(lstActiveBoards, lstCollected)):
            if sBoardError:
                continue

            if lstCandidates and dictBoardSuccessCounts.get(iBoardIndex, 0) == 0:
                self.last_stats["boards_failed"] += 1
                self.last_stats["failed_boards"].append({
                    "university_name": dictBoard.get("university_name", ""),
                    "board_type": dictBoard.get("board_type", ""),
                    "url": dictBoard.get("url", ""),
                    "error": f"All {len(lstCandidates)} detail pages failed.",
                })
            else:
                self.last_stats["boards_succeeded"] += 1

            notices.extend(dictBoardNotices.get(iBoardIndex, []))

        self.state_cache.save()
        return notices

    def crawl_board(self, board: dict, keyword_hint: str | None = None) -> list[CrawledNotice]:
        self.last_error = ""
        candidates, sBoardError = self._collect_board_candidates(board, keyword_hint)

        if sBoardError:
            self.last_error = sBoardError
            return []

        notices: list[CrawledNotice] = []
        iDetailSuccessCount = 0

        for tupleCandidate in candidates:
            self.last_stats["details_total"] += 1
            notice, bSucceeded, sDetailError = self._fetch_detail(board, *tupleCandidate)

            if bSucceeded:
                iDetailSuccessCount += 1
            else:
                self.last_stats["details_failed"] += 1
                self.last_stats["failed_details"].append({
                    "university_name": board.get("university_name", ""),
                    "board_type": board.get("board_type", ""),
                    "url": notice.url,
                    "error": sDetailError,
                })

            notices.append(notice)

        if candidates and iDetailSuccessCount == 0:
            self.last_error = f"All {len(candidates)} detail pages failed."

        return notices

    def _collect_board_candidates(
        self,
        board: dict,
        keyword_hint: str | None,
    ) -> tuple[list[tuple[str, str, str]], str]:
        url = board["url"]

        try:
            html = self._get_text(url)
        except Exception as exc:
            LOGGER.warning("Board fetch failed: %s %s", url, exc)
            return [], str(exc)

        soup = BeautifulSoup(html, HTML_PARSER)
        candidates = self._extract_candidate_links(soup, url, keyword_hint)
        candidates = self._select_candidates(candidates)
        candidates = self._filter_candidates(candidates)
        return candidates[: self.max_links_per_board], ""

    def _filter_candidates(self, candidates: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
        sCutoffDate = ""

        if self.max_notice_age_days is not None:
            sCutoffDate = (now_kst().date() - timedelta(days=self.max_notice_age_days)).isoformat()

        lstFiltered: list[tuple[str, str, str]] = []

        for tupleCandidate in candidates:
            sCandidateUrl = tupleCandidate[1]
            sCandidateDate = tupleCandidate[2]

            if sCandidateUrl in self.skip_urls:
                self.last_stats["details_skipped"] += 1
                continue

            if sCutoffDate and sCandidateDate and sCandidateDate < sCutoffDate:
                self.last_stats["details_skipped"] += 1
                continue

            lstFiltered.append(tupleCandidate)

        return lstFiltered

    def _fetch_detail(
        self,
        board: dict,
        title: str,
        detail_url: str,
        notice_date: str,
    ) -> tuple[CrawledNotice, bool, str]:
        bSucceeded = True
        sDetailError = ""

        try:
            detail_html = self._get_text(detail_url)
            detail_soup = BeautifulSoup(detail_html, HTML_PARSER)
            sDetailNoticeDate = self._extract_notice_date(detail_soup)
            if sDetailNoticeDate:
                notice_date = sDetailNoticeDate
            body_text = self._extract_body_text(detail_soup)
            attachments = self._extract_attachment_urls(detail_soup, detail_url)
        except Exception as exc:
            LOGGER.warning("Detail fetch failed: %s %s", detail_url, exc)
            bSucceeded = False
            sDetailError = str(exc)
            body_text = ""
            attachments = []

        notice = CrawledNotice(
            university_name=board["university_name"],
            board_type=board["board_type"],
            title=title,
            url=detail_url,
            notice_date=notice_date,
            body_text=body_text,
            attachment_urls=attachments,
        )
        return notice, bSucceeded, sDetailError

    def _select_candidates(self, candidates: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
        lstDatedCandidates: list[tuple[str, str, str]] = []
        lstUndatedCandidates: list[tuple[str, str, str]] = []

        for tupleCandidate in candidates:
            if tupleCandidate[2]:
                lstDatedCandidates.append(tupleCandidate)
            else:
                lstUndatedCandidates.append(tupleCandidate)

        lstDatedCandidates.sort(key=lambda tupleCandidate: tupleCandidate[2], reverse=True)
        return lstDatedCandidates + lstUndatedCandidates

    def _get_text(self, url: str) -> str:
        dictHeaders = self.state_cache.conditional_headers(url)
        session = self._session()

        with self._host_semaphore(url):
            try:
                response = session.get(url, headers=dictHeaders, timeout=(4, self.timeout))
            except SSLError:
                LOGGER.info("SSL verification failed; retrying without verification: %s", url)
                response = session.get(url, headers=dictHeaders, timeout=(4, self.timeout), verify=False)

            if response.status_code == 304:
                sCachedHtml = self.state_cache.cached_value(url, "html")
                if sCachedHtml:
                    return sCachedHtml

                response = session.get(url, timeout=(4, self.timeout))

        response.raise_for_status()
        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding
        sHtml = response.text
        self.state_cache.update(url, response.headers, response.content, html=sHtml)
        return sHtml

    def _extract_candidate_links(self, soup: BeautifulSoup, base_url: str, keyword_hint: str | None) -> list[tuple[str, str, str]]:
        rows: list[tuple[str, str, str]] = []
        seen: set[str] = set()

        for a in soup.find_all("a", href=True):
            full_url = urljoin(base_url, a.get("href", ""))
            key = full_url.split("#")[0]
            if key in seen:
                continue

            sContextText = self._link_context_text(a)
            title = normalize_space(a.get_text(" ") or a.get("title") or sContextText)
            if not self._looks_like_notice_link(title, full_url, base_url, keyword_hint):
                continue

            seen.add(key)
            sNoticeDate = self._find_date(sContextText)
            rows.append((title[:250], key, sNoticeDate))

        return rows

    def _link_context_text(self, link) -> str:
        nodeContext = link.find_parent(["tr", "li", "article"])

        if nodeContext is not None:
            return normalize_space(nodeContext.get_text(" "))

        nodeContext = link.parent

        for iDepth in range(0, 3):
            if nodeContext is None:
                break

            iLinkCount = len(nodeContext.find_all("a", href=True))
            if iLinkCount < 3:
                return normalize_space(nodeContext.get_text(" "))

            nodeContext = nodeContext.parent

        return ""

    def _extract_notice_date(self, soup: BeautifulSoup) -> str:
        lstMetaSelectors = [
            "meta[property='article:published_time']",
            "meta[name='date']",
            "meta[name='publish-date']",
        ]

        for sSelector in lstMetaSelectors:
            nodeDate = soup.select_one(sSelector)
            if nodeDate is None:
                continue

            sDate = self._find_date(nodeDate.get("content", ""))
            if sDate:
                return sDate

        for nodeDate in soup.select("time[datetime], .regdate, .write-date, .view-date, .board-date"):
            sDateText = nodeDate.get("datetime", "") or nodeDate.get_text(" ")
            sDate = self._find_date(sDateText)
            if sDate:
                return sDate

        sPageText = normalize_space(soup.get_text(" "))
        match = re.search(r"(?:게시일|작성일|등록일|작성일자)\s*[:：]?\s*((?:19|20)\d{2}\D{0,5}\d{1,2}\D{0,5}\d{1,2})", sPageText)

        if match:
            return self._find_date(match.group(1))

        return ""

    def _looks_like_notice_link(self, title: str, url: str, base_url: str, keyword_hint: str | None) -> bool:
        if not title or len(title) < 3:
            return False
        if len(title) > 180:
            return False

        sNormalizedTitle = normalize_space(title).lower()
        parsedCandidateUrl = urlparse(url)
        parsedBoardUrl = urlparse(base_url)
        sCandidatePath = parsedCandidateUrl.path.rstrip("/")
        sBoardPath = parsedBoardUrl.path.rstrip("/")
        bIsSamePage = (
            parsedCandidateUrl.netloc == parsedBoardUrl.netloc
            and sCandidatePath == sBoardPath
            and parsedCandidateUrl.query == parsedBoardUrl.query
        )
        setMenuTitles = {
            "학사일정", "커뮤니티", "대학소개", "학사안내", "학사행정", "신입학", "편입학",
            "공지사항", "동문소식", "모집안내", "입학안내", "학사자료실", "교직과공지",
            "대학전체", "사회과학대학", "정보기술대학", "사범대학", "more view",
        }
        lstTargetWords = ["시간제", "등록생", "학점은행", "비학위", "모집요강", "수강"]
        bHasKeywordHint = bool(keyword_hint and keyword_hint.lower() in sNormalizedTitle)
        bHasTargetTitle = any(sWord in sNormalizedTitle for sWord in lstTargetWords)
        bHasDetailUrl = bool(re.search(
            r"(article(no)?=|artclview|bbs|board/info|encmenuboardseq|mode=(view|download)|ntt|seq=|wr_id=|/view\.do)",
            url.lower(),
        ))

        if bIsSamePage or sNormalizedTitle in setMenuTitles:
            return False
        if not bHasKeywordHint and not bHasTargetTitle and not bHasDetailUrl:
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
        if re.search(r"rss(list)?\b|/rss", lowered):
            return False
        if keyword_hint and keyword_hint.lower() in title.lower():
            return True
        # 목록 페이지의 첨부파일 링크(제목이 파일명)는 본문 공지와 중복
        if re.search(r"\.(pdf|hwpx?|docx?|xlsx?|zip)\s*$", sNormalizedTitle):
            return False
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
