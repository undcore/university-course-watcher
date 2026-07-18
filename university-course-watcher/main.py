from __future__ import annotations

import argparse
import hashlib
import logging
import os
from datetime import date

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is still listed for normal installs
    def load_dotenv() -> None:
        return None

from src.attachment_parser import AttachmentParser
from src.board_crawler import BoardCrawler, CrawledNotice, validate_crawl_health
from src.classifier import classify
from src.course_finder import CourseFinder
from src.date_parser import parse_notice_dates, parse_notice_dates_from_sources
from src.graduate_admission_watcher import GraduateAdmissionWatcher
from src.http_state import HttpStateCache
from src.notifier import GraduateAdmissionNotifier, TelegramNotifier
from src.recency import is_recent_notice, is_stale_notice, notice_max_age_days
from src.report_builder import build_graduate_admission_report, build_report
from src.storage import Storage
from src.utils import CONFIG_DIR, DATA_DIR, ensure_dirs, load_json, now_kst, setup_logging

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="수도권 대학 시간제등록/외부 수강 공고 직접 크롤러")
    parser.add_argument("--once", action="store_true", help="한 번만 실행합니다.")
    parser.add_argument("--region", choices=["seoul", "gyeonggi", "incheon"], help="특정 지역만 검색합니다.")
    parser.add_argument("--grade", choices=["A", "B", "C", "D"], help="지정 등급 이상만 출력/저장합니다.")
    parser.add_argument("--keyword", help="특정 키워드 중심으로 후보 링크를 우선 탐색합니다.")
    parser.add_argument("--watch", choices=["course", "graduate-admission"], default="course", help="실행할 감시 대상을 선택합니다.")
    parser.add_argument("--dry-run", action="store_true", help="저장과 텔레그램 알림 없이 결과만 출력합니다.")
    parser.add_argument("--debug", action="store_true", help="D등급과 상세 로그를 저장합니다.")
    parser.add_argument("--smoke-test", action="store_true", help="CI용 빠른 동작 확인 모드입니다.")
    parser.add_argument("--telegram-test-success", action="store_true", help="일반대학원 후보 발견 텔레그램 테스트 메시지를 보냅니다.")
    parser.add_argument("--telegram-test-empty", action="store_true", help="일반대학원 신규 없음 텔레그램 테스트 메시지를 보냅니다.")
    return parser.parse_args()


def count_by_key(items: list[dict], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}

    for item in items:
        value = str(item.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1

    return counts


def is_changed_candidate(item: dict) -> bool:
    change_type = item.get("change_type", "")
    if change_type:
        return change_type in {"new", "content_changed", "grade_changed", "deadline_changed"}
    return bool(item.get("is_new"))


def build_content_fingerprint(parts: list[str]) -> str:
    fingerprint_text = "\n".join(parts)
    fingerprint_bytes = fingerprint_text.encode("utf-8", errors="replace")
    return hashlib.sha256(fingerprint_bytes).hexdigest()


def trusted_crawled_notices(notices: list[CrawledNotice], stats: dict) -> list[CrawledNotice]:
    validate_crawl_health(stats)
    return [notice for notice in notices if notice.detail_succeeded]


def is_course_candidate_target(item: dict) -> bool:
    return (
        is_changed_candidate(item)
        and item.get("grade") in {"A", "B"}
        and item.get("deadline_status") != "마감됨"
        and is_recent_notice(item)
    )


def count_candidate_targets(items: list[dict]) -> int:
    count = 0

    for item in items:
        if is_course_candidate_target(item):
            count += 1

    return count


def github_actions_run_url() -> str:
    server_url = os.getenv("GITHUB_SERVER_URL", "")
    repository = os.getenv("GITHUB_REPOSITORY", "")
    run_id = os.getenv("GITHUB_RUN_ID", "")

    if not server_url or not repository or not run_id:
        return ""

    return f"{server_url}/{repository}/actions/runs/{run_id}"


def report_preview_items(items: list[dict], limit: int = 5) -> list[dict]:
    preview: list[dict] = []
    rank = {"A": 0, "B": 1, "C": 2, "D": 3}
    sorted_items = sorted(items, key=lambda item: rank.get(item.get("grade"), 9))

    for item in sorted_items:
        # C등급은 참고용 노이즈가 많아 보고서 미리보기에서 제외
        change_type = item.get("change_type", "")
        if item.get("grade") not in {"A", "B"} or not is_changed_candidate(item) or not is_recent_notice(item):
            continue

        preview.append({
            "grade": item.get("grade", ""),
            "university_name": item.get("university_name", ""),
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "reason": item.get("reason", ""),
            "is_new": item.get("is_new", False),
            "change_type": change_type,
        })

        if len(preview) >= limit:
            break

    return preview


def items_to_mark_seen(items: list[dict], sent_items: list[dict]) -> list[dict]:
    lstSeenItems = list(sent_items)
    setSeenUrls = {dictItem.get("url", "") for dictItem in sent_items}

    for dictItem in items:
        sUrl = dictItem.get("url", "")
        sGrade = dictItem.get("grade", "")
        bIsNew = bool(dictItem.get("is_new"))

        bShouldMarkSeen = sGrade == "C" or is_stale_notice(dictItem)

        if not bIsNew or not bShouldMarkSeen or not sUrl:
            continue
        if sUrl in setSeenUrls:
            continue

        lstSeenItems.append(dictItem)
        setSeenUrls.add(sUrl)

    return lstSeenItems


def items_to_update_notice_state(items: list[dict], sent_items: list[dict]) -> list[dict]:
    sent_urls = {item.get("url", "") for item in sent_items}
    state_items: list[dict] = []

    for item in items:
        item_url = item.get("url", "")

        if is_course_candidate_target(item) and item_url not in sent_urls:
            continue

        state_items.append(item)

    return state_items


def normalize_weak_candidate(item: dict) -> dict:
    if item.get("grade") != "C":
        return item

    sTitle = str(item.get("title", "")).lower()
    lstTargetWords = [
        "시간제", "등록생", "학점은행", "비학위", "외부 수강", "타교생", "일반인 수강",
    ]
    bHasTargetTitle = any(sWord in sTitle for sWord in lstTargetWords)

    if bHasTargetTitle:
        return item

    item["grade"] = "D"
    item["reason"] = "C등급 약한 후보이지만 제목에 시간제등록 또는 외부 수강 신호가 없어 제외했습니다."
    return item


def should_parse_course_attachments(sTitle: str, sPreliminaryGrade: str) -> bool:
    if sPreliminaryGrade in {"A", "B", "C"}:
        return True

    sLoweredTitle = sTitle.lower()
    lstTargetWords = ["시간제", "등록생", "학점은행", "비학위", "외부 수강", "타교생"]
    return any(sWord in sLoweredTitle for sWord in lstTargetWords)


def main() -> int:
    load_dotenv()
    args = parse_args()
    debug = args.debug or os.getenv("DEBUG", "false").lower() == "true"
    setup_logging(debug)
    ensure_dirs()

    if args.telegram_test_success:
        notifier = GraduateAdmissionNotifier()
        notifier.send_test_success()
        LOGGER.info("Graduate admission success telegram test sent.")
        return 0

    if args.telegram_test_empty:
        notifier = GraduateAdmissionNotifier()
        notifier.send_test_empty()
        LOGGER.info("Graduate admission empty telegram test sent.")
        return 0

    if args.watch == "graduate-admission":
        graduate_boards = load_json(CONFIG_DIR / "graduate_admission_boards.json", [])
        active_count = len([board for board in graduate_boards if board.get("enabled", True)])
        disabled_count = len(graduate_boards) - active_count
        os.environ["GRADUATE_ADMISSION_ACTIVE_BOARD_COUNT"] = str(active_count)
        os.environ["GRADUATE_ADMISSION_DISABLED_BOARD_COUNT"] = str(disabled_count)

        watcher = GraduateAdmissionWatcher(smoke_test=args.smoke_test)
        items = watcher.run(region=args.region, dry_run=args.dry_run)
        send_empty_summary = watcher.should_send_empty_summary(items, active_count, disabled_count)
        notifier = GraduateAdmissionNotifier()
        sent = notifier.send_candidates(
            items,
            dry_run=args.dry_run,
            send_empty_summary=send_empty_summary,
        )

        if not args.dry_run:
            build_graduate_admission_report(items)
            watcher.mark_sent(items_to_mark_seen(items, sent))
            if notifier.summary_sent:
                watcher.mark_empty_summary_sent(items, active_count, disabled_count)
        else:
            for item in items:
                print(f"[{item['grade']}] {item['university_name']} {item['title']} {item['url']}")

        if notifier.delivery_failures:
            raise RuntimeError(f"Telegram delivery failed {len(notifier.delivery_failures)} time(s).")

        LOGGER.info("Done. graduate_admission_candidates=%d notifications=%d", len(items), len(sent))
        return 0

    universities = load_json(CONFIG_DIR / "universities.json", [])
    boards = load_json(CONFIG_DIR / "board_urls.json", [])
    keywords = load_json(CONFIG_DIR / "keywords.json", {})
    storage = Storage()
    storage.ensure_empty_files()

    if args.region:
        universities = [university for university in universities if university.get("region") == args.region]

    university_map = {university["name"]: university for university in universities}
    boards = [board for board in boards if board.get("university_name") in university_map]
    board_count = len(boards)
    university_count = len(university_map)

    LOGGER.info("Crawling %d boards for %d universities without search APIs.", board_count, university_count)
    httpState = HttpStateCache(DATA_DIR / "course_http_state.json")
    crawler_options = {
        "state_cache": httpState,
        "max_notice_age_days": notice_max_age_days(),
    }
    crawler = BoardCrawler(timeout=5, max_links_per_board=2, **crawler_options) if args.smoke_test else BoardCrawler(**crawler_options)
    attachment_parser = AttachmentParser(state_cache=httpState)
    course_finder = CourseFinder(keywords)
    crawled = crawler.crawl_boards(boards, university_map, keyword_hint=args.keyword)
    crawled = trusted_crawled_notices(crawled, crawler.last_stats)
    crawled_count = len(crawled)

    checked_at = now_kst().isoformat(timespec="seconds")
    today = date.today()
    items: list[dict] = []

    lstPreliminaries: list[tuple] = []
    lstAttachmentUrls: list[str] = []

    for notice in crawled:
        preliminary_dates = parse_notice_dates(notice.title, notice.body_text, notice.notice_date, today)
        preliminary_classification = classify(notice.title, notice.body_text, preliminary_dates, keywords)
        bParseAttachments = should_parse_course_attachments(notice.title, preliminary_classification.grade)
        lstPreliminaries.append((notice, preliminary_dates, preliminary_classification, bParseAttachments))

        if not args.smoke_test and bParseAttachments:
            lstAttachmentUrls.extend(notice.attachment_urls)

    dictAttachmentTexts = attachment_parser.extract_texts(list(dict.fromkeys(lstAttachmentUrls)))

    for notice, preliminary_dates, preliminary_classification, bParseAttachments in lstPreliminaries:
        university = university_map.get(notice.university_name, {})
        attachment_texts = {}
        image_texts: dict[str, str] = {}
        ocr_checked = False

        if bParseAttachments:
            attachment_texts = {
                sUrl: dictAttachmentTexts[sUrl]
                for sUrl in notice.attachment_urls
                if dictAttachmentTexts.get(sUrl)
            }

        text_sources = [("본문", notice.body_text)]
        text_sources.extend(
            (f"첨부:{url}", text)
            for url, text in attachment_texts.items()
        )
        combined_text = "\n".join(text for _, text in text_sources)
        dates = parse_notice_dates_from_sources(notice.title, text_sources, notice.notice_date, today)
        classification = classify(notice.title, combined_text, dates, keywords)

        if classification.grade in {"A", "B"} and not args.smoke_test and notice.image_urls:
            ocr_checked = True
            image_texts = attachment_parser.extract_image_texts(notice.image_urls)
            image_sources = [
                (f"이미지 OCR:{url}", text)
                for url, text in image_texts.items()
                if text
            ]

            if image_sources:
                text_sources.extend(image_sources)
                combined_text = "\n".join(text for _, text in text_sources)
                dates = parse_notice_dates_from_sources(notice.title, text_sources, notice.notice_date, today)
                classification = classify(notice.title, combined_text, dates, keywords)

        fingerprint_parts = [
            notice.title,
            combined_text,
            *sorted(notice.attachment_urls),
            *sorted(notice.image_urls),
        ]
        content_fingerprint = build_content_fingerprint(fingerprint_parts)

        item = {
            "checked_at": checked_at,
            "university_name": notice.university_name,
            "region": university.get("region_name", university.get("region", "")),
            "city": university.get("city", ""),
            "title": notice.title,
            "url": notice.url,
            "source_type": "대학 공식 게시판 직접 크롤링",
            "source_query": notice.board_type,
            **dates,
            "registration_score": classification.registration_score,
            "external_score": classification.external_score,
            "computer_score": classification.computer_score,
            "freshness_score": classification.freshness_score,
            "grade": classification.grade,
            "external_applicant_status": classification.external_applicant_status,
            "computer_course_status": classification.computer_course_status,
            "possible_departments": [],
            "possible_computer_courses": [],
            "course_evidence_url": "",
            "course_evidence_text": "",
            "attachment_urls": notice.attachment_urls,
            "image_urls": notice.image_urls,
            "ocr_checked": ocr_checked,
            "ocr_text_found": any(image_texts.values()),
            "ocr_evidence": {url: text[:1000] for url, text in image_texts.items() if text},
            "matched_keywords": classification.matched_keywords,
            "reason": classification.reason,
            "content_fingerprint": content_fingerprint,
            "change_type": "",
            "previous_grade": "",
            "is_new": False,
        }

        item = normalize_weak_candidate(item)

        if item["grade"] in {"A", "B", "C"} and not args.smoke_test:
            item = course_finder.enrich(item, university)

        items.append(item)

    items = storage.dedupe(items)
    items = storage.mark_is_new(items)
    items = storage.mark_changes(items)
    state_items = list(items)
    deduped_count = len(items)

    if args.grade:
        rank = {"A": 0, "B": 1, "C": 2, "D": 3}
        items = [item for item in items if rank.get(item.get("grade"), 9) <= rank[args.grade]]

    public_count = len([item for item in items if item.get("grade") != "D"])
    candidate_count = count_candidate_targets(items)

    if not args.dry_run:
        storage.save_results([item for item in items if item.get("grade") != "D"], debug_items=items if debug else None)
        build_report(items)
        notifier = TelegramNotifier()
        sent = notifier.send_candidates(items, dry_run=False)
        lstSeenItems = items_to_mark_seen(items, sent)
        storage.update_seen(lstSeenItems)
        storage.update_notice_state(items_to_update_notice_state(state_items, sent))
        summary = {
            "checked_at": checked_at,
            "university_count": university_count,
            "board_count": board_count,
            "board_success_count": crawler.last_stats.get("boards_succeeded", 0),
            "board_failure_count": crawler.last_stats.get("boards_failed", 0),
            "board_skip_count": crawler.last_stats.get("boards_skipped", 0),
            "detail_count": crawler.last_stats.get("details_total", 0),
            "detail_failure_count": crawler.last_stats.get("details_failed", 0),
            "crawled_count": crawled_count,
            "deduped_count": deduped_count,
            "public_count": public_count,
            "candidate_count": candidate_count,
            "sent_count": len(sent),
            "grade_counts": count_by_key(items, "grade"),
            "status_counts": count_by_key(items, "deadline_status"),
            "preview_items": report_preview_items(items),
            "failed_boards": crawler.last_stats.get("failed_boards", []),
            "failed_details": crawler.last_stats.get("failed_details", []),
            "actions_run_url": github_actions_run_url(),
            "artifact_name": "course-watcher-results",
            "report_html_url": os.getenv("REPORT_HTML_URL", ""),
        }
        report_sent = notifier.send_daily_report(summary, dry_run=False)
        LOGGER.info("Daily Telegram report sent=%s", report_sent)

        # 실제 발송 실패는 delivery_failures에 기록됨; 토큰 미설정은 실패가 아님
        if notifier.delivery_failures:
            raise RuntimeError(f"Telegram delivery failed {len(notifier.delivery_failures)} time(s).")

    else:
        for item in items:
            if item.get("grade") != "D" or debug:
                print(f"[{item['grade']}] {item['university_name']} {item['title']} {item['url']}")

    LOGGER.info("Done. candidates=%d public=%d", len(items), public_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
