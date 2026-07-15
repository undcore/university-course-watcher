from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from bs4 import BeautifulSoup

from .apply_portal import fetch_portal_items
from .attachment_parser import AttachmentParser
from .board_crawler import HTML_PARSER, BoardCrawler, CrawledNotice
from .http_state import HttpStateCache
from .recency import notice_max_age_days
from .storage import GraduateAdmissionStorage
from .utils import CONFIG_DIR, DATA_DIR, load_json, normalize_space, now_kst

LOGGER = logging.getLogger(__name__)


TARGET_YEARS = ["2026", "2027"]
# 전기/후기 구분 없이 모집 차수(1차/2차/추가모집 등)를 함께 추적
TERM_KEYWORDS = ["전기", "후기", "추가모집", "추가 모집", "1차", "2차", "3차"]


@dataclass
class GraduateAdmissionMatch:
    checked_at: str
    university_name: str
    region: str
    city: str
    board_type: str
    title: str
    url: str
    notice_date: str
    grade: str
    matched_keywords: list[str]
    reason: str
    attachment_urls: list[str]
    is_new: bool = False

    def as_dict(self) -> dict:
        return {
            "checked_at": self.checked_at,
            "university_name": self.university_name,
            "region": self.region,
            "city": self.city,
            "board_type": self.board_type,
            "title": self.title,
            "url": self.url,
            "notice_date": self.notice_date,
            "grade": self.grade,
            "matched_keywords": self.matched_keywords,
            "reason": self.reason,
            "attachment_urls": self.attachment_urls,
            "is_new": self.is_new,
        }


class GraduateAdmissionWatcher:
    def __init__(self, smoke_test: bool = False):
        intMaxLinks = 3 if smoke_test else 12
        intTimeout = 5 if smoke_test else 8

        self.smoke_test = smoke_test
        self.http_state = HttpStateCache(DATA_DIR / "graduate_http_state.json")
        self.storage = GraduateAdmissionStorage()
        self.crawler = BoardCrawler(
            timeout=intTimeout,
            max_links_per_board=intMaxLinks,
            state_cache=self.http_state,
            # 모집요강은 같은 URL에서 학년도와 첨부가 교체되므로 URL만으로 사전 제외하지 않는다.
            skip_urls=set(),
            max_notice_age_days=notice_max_age_days(),
        )
        self.attachment_parser = AttachmentParser(state_cache=self.http_state)

    def run(self, region: str | None = None, dry_run: bool = False) -> list[dict]:
        universities = load_json(CONFIG_DIR / "universities.json", [])
        graduate_boards = load_json(CONFIG_DIR / "graduate_admission_boards.json", [])

        if region:
            universities = [university for university in universities if university.get("region") == region]

        university_map = {university["name"]: university for university in universities}
        boards = self._select_boards(graduate_boards, university_map)

        LOGGER.info("Crawling %d graduate admission boards for 일반대학원 모집 notices.", len(boards))
        notices = self._scan_direct_pages(boards)
        notices.extend(self.crawler.crawl_boards(boards, university_map, keyword_hint="2026"))
        items = self._build_items(notices, university_map)

        if not self.smoke_test:
            portal_items = fetch_portal_items()
            for item in portal_items:
                if region and item["university_name"] not in university_map:
                    continue
                university = university_map.get(item["university_name"], {})
                item["region"] = university.get("region_name", university.get("region", ""))
                item["city"] = university.get("city", "")
                items.append(item)
        items = self.storage.dedupe(items)
        items = self.storage.mark_is_new(items)

        if not dry_run:
            self.storage.save_results(items)

        return items

    def mark_sent(self, sent_items: list[dict]) -> None:
        self.storage.update_seen(sent_items)

    def should_send_empty_summary(self, items: list[dict], active_count: int, disabled_count: int) -> bool:
        return self.storage.should_send_empty_summary(items, active_count, disabled_count)

    def mark_empty_summary_sent(self, items: list[dict], active_count: int, disabled_count: int) -> None:
        self.storage.update_empty_summary_state(items, active_count, disabled_count)

    def _select_boards(self, graduate_boards: list[dict], university_map: dict[str, dict]) -> list[dict]:
        boards: list[dict] = []

        for board in graduate_boards:
            if not board.get("enabled", True):
                continue
            if board.get("university_name") not in university_map:
                continue
            boards.append(board)

        return boards

    def _scan_direct_pages(self, boards: list[dict]) -> list[CrawledNotice]:
        lstScanBoards = [board for board in boards if board.get("scan_page")]

        if not lstScanBoards:
            return []

        iWorkerCount = min(8, len(lstScanBoards))

        with ThreadPoolExecutor(max_workers=iWorkerCount) as executor:
            lstResults = list(executor.map(self._scan_direct_page, lstScanBoards))

        return [notice for notice in lstResults if notice is not None]

    def _scan_direct_page(self, board: dict) -> CrawledNotice | None:
        sUrl = board["url"]

        try:
            html = self.crawler._get_text(sUrl)
        except Exception as exc:
            LOGGER.warning("Direct admission page fetch failed: %s %s", sUrl, exc)
            return None

        soup = BeautifulSoup(html, HTML_PARSER)
        title = self._extract_page_title(soup, board)
        body_text = self.crawler._extract_body_text(soup)
        attachment_urls = self.crawler._extract_attachment_urls(soup, sUrl)

        return CrawledNotice(
            university_name=board["university_name"],
            board_type=board["board_type"],
            title=title,
            url=sUrl,
            notice_date="__DIRECT_PAGE__",
            body_text=body_text,
            attachment_urls=attachment_urls,
        )

    def _extract_page_title(self, soup: BeautifulSoup, board: dict) -> str:
        for selector in ["h1", "h2", ".title", ".tit", "title"]:
            node = soup.select_one(selector)
            if node:
                sTitle = normalize_space(node.get_text(" "))
                if sTitle:
                    return sTitle[:250]

        return f"{board.get('university_name', '')} {board.get('board_type', '')}"

    def _build_items(self, notices: list[CrawledNotice], university_map: dict[str, dict]) -> list[dict]:
        checked_at = now_kst().isoformat(timespec="seconds")
        items: list[dict] = []
        lstAttachmentUrls: list[str] = []

        if not self.smoke_test:
            for notice in notices:
                bStrictTitle = not self._is_direct_page_notice(notice)
                sGrade, _, _ = self._classify_notice(notice.title, notice.body_text, strict_title=bStrictTitle)

                if sGrade != "D":
                    lstAttachmentUrls.extend(notice.attachment_urls)

        lstUniqueAttachmentUrls = list(dict.fromkeys(lstAttachmentUrls))
        dictAttachmentTexts = self.attachment_parser.extract_texts(lstUniqueAttachmentUrls)

        for notice in notices:
            university = university_map.get(notice.university_name, {})
            attachment_texts = {
                sUrl: dictAttachmentTexts.get(sUrl, "")
                for sUrl in notice.attachment_urls
                if sUrl in dictAttachmentTexts
            }

            combined_text = "\n".join([notice.body_text] + list(attachment_texts.values()))
            strict_title = not self._is_direct_page_notice(notice)
            grade, matched_keywords, reason = self._classify_notice(notice.title, combined_text, strict_title=strict_title)

            if grade == "D":
                continue
            if self._is_direct_page_notice(notice) and not any(year in notice.title for year in TARGET_YEARS):
                # 상시 안내/메뉴 페이지는 수집원으로만 사용하고 공고 결과로 노출하지 않는다.
                continue

            item = GraduateAdmissionMatch(
                checked_at=checked_at,
                university_name=notice.university_name,
                region=university.get("region_name", university.get("region", "")),
                city=university.get("city", ""),
                board_type=notice.board_type,
                title=notice.title,
                url=notice.url,
                notice_date="" if self._is_direct_page_notice(notice) else notice.notice_date,
                grade=grade,
                matched_keywords=matched_keywords,
                reason=reason,
                attachment_urls=notice.attachment_urls,
            )
            items.append(item.as_dict())

        return items

    def _is_direct_page_notice(self, notice: CrawledNotice) -> bool:
        return notice.notice_date == "__DIRECT_PAGE__"

    def _classify_notice(self, title: str, text: str, strict_title: bool = True) -> tuple[str, list[str], str]:
        normalized_title = normalize_space(title)
        normalized_text = normalize_space(f"{title}\n{text}")
        lowered_title = normalized_title.lower()
        lowered_text = normalized_text.lower()

        year_keywords = TARGET_YEARS + [f"{sYear}학년도" for sYear in TARGET_YEARS]
        school_keywords = ["일반대학원", "대학원"]
        admission_keywords = ["모집요강", "신입생 모집", "신입생모집", "입학전형", "전형일정", "원서접수", "특별전형", "추가모집"]
        negative_keywords = ["학부", "편입", "재외국민", "특수대학원", "전문대학원", "교육대학원", "경영전문대학원"]
        excluded_title_keywords = ["합격자", "등록금", "면접", "수험생", "계약학과", "학석사", "외국인"]

        matched_keywords: list[str] = []

        if any(keyword in lowered_title for keyword in excluded_title_keywords):
            return "D", matched_keywords, "모집 공고가 아닌 합격·등록·면접·별도 전형 안내로 판단되어 제외했습니다."

        title_has_year = self._collect_matches(lowered_title, year_keywords, matched_keywords)
        title_admission_keywords = admission_keywords + ["학생모집", "일반전형"]
        title_has_admission = any(keyword in lowered_title for keyword in title_admission_keywords)
        has_year = title_has_year or any(keyword.lower() in lowered_text for keyword in year_keywords)
        has_school = self._collect_matches(lowered_text, school_keywords, matched_keywords)
        has_admission = self._collect_matches(lowered_text, admission_keywords, matched_keywords)
        has_negative = self._collect_matches(lowered_text, negative_keywords, matched_keywords)
        # 차수(전기/후기/1차/2차/추가모집)는 필터가 아니라 표시용으로 수집
        self._collect_matches(lowered_title, TERM_KEYWORDS, matched_keywords)

        if strict_title and (not title_has_year or not title_has_admission):
            return "D", matched_keywords, "제목에 학년도와 모집 신호가 함께 없어 메뉴/상시 안내 페이지로 판단했습니다."

        if has_negative and "일반대학원" not in lowered_text:
            return "D", matched_keywords, "일반대학원보다 특수/전문대학원 또는 학부 전형일 가능성이 높습니다."

        if has_year and "일반대학원" in lowered_text and has_admission:
            return "A", matched_keywords, "일반대학원 모집 공고로 판단됩니다."

        if has_year and has_school and has_admission:
            return "B", matched_keywords, "대학원 모집 공고이며 일반대학원 여부 추가 확인이 필요합니다."

        return "D", matched_keywords, "일반대학원 모집요강 조건을 충족하지 않습니다."

    def _collect_matches(self, text: str, keywords: list[str], matched_keywords: list[str]) -> bool:
        found = False

        for keyword in keywords:
            if keyword.lower() in text:
                matched_keywords.append(keyword)
                found = True

        return found
