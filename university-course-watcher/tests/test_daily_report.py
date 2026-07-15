from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from main import (
    build_content_fingerprint,
    items_to_mark_seen,
    normalize_weak_candidate,
    report_preview_items,
    should_parse_course_attachments,
)
from src.report_builder import build_graduate_admission_report
from src.storage import Storage


class DailyReportTest(unittest.TestCase):
    def test_content_fingerprint_replaces_invalid_unicode_surrogates(self) -> None:
        fingerprint = build_content_fingerprint(["정상 본문", "손상 문자 \udcff 포함"])

        self.assertEqual(64, len(fingerprint))

    def test_preview_contains_only_new_public_items(self) -> None:
        sToday = date.today().isoformat()
        lstItems = [
            {"grade": "A", "is_new": False, "title": "existing A", "notice_date": sToday},
            {"grade": "B", "is_new": True, "title": "new B", "notice_date": sToday},
            {"grade": "C", "is_new": True, "title": "new C", "notice_date": sToday},
            {"grade": "D", "is_new": True, "title": "new D", "notice_date": sToday},
        ]

        lstPreview = report_preview_items(lstItems)

        self.assertEqual(["new B"], [dictItem["title"] for dictItem in lstPreview])

    def test_seen_items_include_sent_candidates_and_new_grade_c(self) -> None:
        dictSentB = {"url": "https://example.com/b", "grade": "B", "is_new": True}
        dictNewC = {"url": "https://example.com/c", "grade": "C", "is_new": True}
        lstItems = [
            dictSentB,
            dictNewC,
            {"url": "https://example.com/old-c", "grade": "C", "is_new": False},
            {"url": "https://example.com/failed-a", "grade": "A", "is_new": True},
        ]

        lstSeenItems = items_to_mark_seen(lstItems, [dictSentB])

        self.assertEqual(
            ["https://example.com/b", "https://example.com/c"],
            [dictItem["url"] for dictItem in lstSeenItems],
        )

    def test_previous_grade_c_results_are_used_as_seen_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as sTempDirectory:
            pathData = Path(sTempDirectory)
            pathData.joinpath("results.json").write_text(
                '[{"url":"https://example.com/c","grade":"C"},'
                '{"url":"https://example.com/b","grade":"B"}]',
                encoding="utf-8",
            )
            pathData.joinpath("seen_urls.json").write_text("[]", encoding="utf-8")

            setSeenUrls = Storage(pathData).load_seen()

        self.assertEqual({"https://example.com/c"}, setSeenUrls)

    def test_stale_grade_a_and_b_items_are_marked_seen_without_delivery(self) -> None:
        lstItems = [
            {"url": "https://example.com/a", "grade": "A", "is_new": True, "notice_date": "2026-03-01"},
            {"url": "https://example.com/b", "grade": "B", "is_new": True, "notice_date": "2026-04-01"},
        ]

        lstSeenItems = items_to_mark_seen(lstItems, [])

        self.assertEqual(2, len(lstSeenItems))

    def test_weak_grade_c_requires_target_signal_in_title(self) -> None:
        dictNoise = normalize_weak_candidate({"grade": "C", "title": "2026학년도 인턴십 학생모집"})
        dictTarget = normalize_weak_candidate({"grade": "C", "title": "2026학년도 시간제등록 안내"})

        self.assertEqual("D", dictNoise["grade"])
        self.assertEqual("C", dictTarget["grade"])

    def test_attachments_are_skipped_for_irrelevant_low_score_notice(self) -> None:
        self.assertFalse(should_parse_course_attachments("일반 행사 안내", "D"))
        self.assertTrue(should_parse_course_attachments("시간제등록 안내", "D"))
        self.assertTrue(should_parse_course_attachments("관련 내용", "B"))

    def test_graduate_admission_html_report_is_generated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "graduate_admission_report.html"
            items = [{
                "checked_at": "2026-07-15T20:00:00+09:00",
                "university_name": "테스트대학교",
                "region": "서울",
                "city": "서울",
                "board_type": "모집요강",
                "title": "2027학년도 전기 일반대학원 모집요강",
                "url": "https://example.com/admission",
                "notice_date": "2026-07-15",
                "grade": "A",
                "matched_keywords": ["2027", "전기"],
                "reason": "일반대학원 모집 공고",
                "attachment_urls": [],
                "is_new": True,
            }]

            build_graduate_admission_report(items, path)
            content = path.read_text(encoding="utf-8")

            self.assertIn("2027학년도 전기 일반대학원 모집요강", content)
            self.assertIn("전체 후보 1건", content)


if __name__ == "__main__":
    unittest.main()
