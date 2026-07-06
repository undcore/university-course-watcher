from __future__ import annotations

import argparse
import logging
import os
from datetime import date

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is still listed for normal installs
    def load_dotenv() -> None:
        return None

from src.attachment_parser import AttachmentParser
from src.board_crawler import BoardCrawler
from src.classifier import classify
from src.course_finder import CourseFinder
from src.date_parser import parse_notice_dates
from src.graduate_admission_watcher import GraduateAdmissionWatcher
from src.notifier import GraduateAdmissionNotifier, TelegramNotifier
from src.report_builder import build_graduate_admission_report, build_report
from src.storage import Storage
from src.utils import CONFIG_DIR, ensure_dirs, load_json, now_kst, setup_logging

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
    parser.add_argument("--telegram-test-success", action="store_true", help="2026 후기 일반대학원 후보 발견 텔레그램 테스트 메시지를 보냅니다.")
    parser.add_argument("--telegram-test-empty", action="store_true", help="2026 후기 일반대학원 신규 없음 텔레그램 테스트 메시지를 보냅니다.")
    return parser.parse_args()


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
        sent = notifier.send_candidates(items, dry_run=args.dry_run, send_empty_summary=send_empty_summary)

        if not args.dry_run:
            build_graduate_admission_report(items)
            watcher.mark_sent(sent)
            if notifier.summary_sent:
                watcher.mark_empty_summary_sent(items, active_count, disabled_count)
        else:
            for item in items:
                print(f"[{item['grade']}] {item['university_name']} {item['title']} {item['url']}")

        LOGGER.info("Done. graduate_admission_candidates=%d notifications=%d", len(items), len(sent))
        return 0

    universities = load_json(CONFIG_DIR / "universities.json", [])
    boards = load_json(CONFIG_DIR / "board_urls.json", [])
    keywords = load_json(CONFIG_DIR / "keywords.json", {})
    storage = Storage()
    storage.ensure_empty_files()

    if args.region:
        universities = [u for u in universities if u.get("region") == args.region]
    university_map = {u["name"]: u for u in universities}
    boards = [b for b in boards if b.get("university_name") in university_map]

    LOGGER.info("Crawling %d boards for %d universities without search APIs.", len(boards), len(university_map))
    crawler = BoardCrawler(timeout=5, max_links_per_board=2, allow_board_overrides=False) if args.smoke_test else BoardCrawler()
    attachment_parser = AttachmentParser()
    course_finder = CourseFinder(keywords)
    crawled = crawler.crawl_boards(boards, university_map, keyword_hint=args.keyword)

    checked_at = now_kst().isoformat(timespec="seconds")
    today = date.today()
    items: list[dict] = []
    for notice in crawled:
        university = university_map.get(notice.university_name, {})
        attachment_texts = {} if args.smoke_test else attachment_parser.extract_texts(notice.attachment_urls)
        combined_text = "\n".join([notice.body_text] + list(attachment_texts.values()))
        dates = parse_notice_dates(notice.title, combined_text, notice.notice_date, today)
        cls = classify(notice.title, combined_text, dates, keywords)
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
            "registration_score": cls.registration_score,
            "external_score": cls.external_score,
            "computer_score": cls.computer_score,
            "freshness_score": cls.freshness_score,
            "grade": cls.grade,
            "external_applicant_status": cls.external_applicant_status,
            "computer_course_status": cls.computer_course_status,
            "possible_departments": [],
            "possible_computer_courses": [],
            "course_evidence_url": "",
            "course_evidence_text": "",
            "attachment_urls": notice.attachment_urls,
            "matched_keywords": cls.matched_keywords,
            "reason": cls.reason,
            "is_new": False,
        }
        if item["grade"] in {"A", "B", "C"} and not args.smoke_test:
            item = course_finder.enrich(item, university)
        items.append(item)

    items = storage.dedupe(items)
    items = storage.mark_is_new(items)
    if args.grade:
        rank = {"A": 0, "B": 1, "C": 2, "D": 3}
        items = [i for i in items if rank.get(i.get("grade"), 9) <= rank[args.grade]]

    if not args.dry_run:
        storage.save_results([i for i in items if i.get("grade") != "D"], debug_items=items if debug else None)
        build_report(items)
        sent = TelegramNotifier().send_candidates(items, dry_run=False)
        storage.update_seen(sent)
    else:
        for item in items:
            if item.get("grade") != "D" or debug:
                print(f"[{item['grade']}] {item['university_name']} {item['title']} {item['url']}")

    LOGGER.info("Done. candidates=%d public=%d", len(items), len([i for i in items if i.get("grade") != "D"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
