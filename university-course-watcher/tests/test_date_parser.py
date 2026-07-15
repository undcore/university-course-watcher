from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.date_parser import parse_notice_dates, parse_notice_dates_from_sources


class NoticeDateParserTest(unittest.TestCase):
    def test_application_date_is_not_used_as_notice_date(self) -> None:
        dictDates = parse_notice_dates(
            "시간제등록 모집",
            "접수기간 2026-06-10 ~ 2026-06-20",
            "",
            date(2026, 6, 19),
        )

        self.assertEqual("", dictDates["notice_date"])
        self.assertEqual("2026-06-10", dictDates["application_start_date"])
        self.assertEqual("2026-06-20", dictDates["application_end_date"])

    def test_explicit_notice_date_is_preserved(self) -> None:
        dictDates = parse_notice_dates(
            "시간제등록 모집",
            "접수기간 2026-06-10 ~ 2026-06-20",
            "2026-04-03",
            date(2026, 6, 19),
        )

        self.assertEqual("2026-04-03", dictDates["notice_date"])

    def test_unrelated_dates_are_not_used_as_application_period(self) -> None:
        dictDates = parse_notice_dates(
            "시간제등록 모집",
            "게시일 2026-04-03. 설명회 2026-06-10. 개강일 2026-06-20.",
            "2026-04-03",
            date(2026, 6, 19),
        )

        self.assertEqual("", dictDates["application_start_date"])
        self.assertEqual("", dictDates["application_end_date"])

    def test_date_source_is_reported_for_selected_period(self) -> None:
        dates = parse_notice_dates_from_sources(
            "시간제등록생 모집",
            [
                ("본문", "접수기간 2026-06-24 ~ 2026-07-03"),
                ("이미지 OCR", "원서접수 2026-06-24 ~ 2026-07-03"),
            ],
            "2026-06-20",
            date(2026, 6, 22),
        )

        self.assertEqual("본문, 이미지 OCR", dates["date_source"])
        self.assertFalse(dates["date_conflict"])

    def test_date_conflict_between_body_and_ocr_is_reported(self) -> None:
        dates = parse_notice_dates_from_sources(
            "시간제등록생 모집",
            [
                ("본문", "접수기간 2026-06-24 ~ 2026-07-03"),
                ("이미지 OCR", "접수기간 2026-06-25 ~ 2026-07-04"),
            ],
            "2026-06-20",
            date(2026, 6, 22),
        )

        self.assertEqual("2026-06-24", dates["application_start_date"])
        self.assertEqual("본문", dates["date_source"])
        self.assertTrue(dates["date_conflict"])

    def test_reversed_application_period_is_rejected(self) -> None:
        dictDates = parse_notice_dates(
            "시간제등록 모집",
            "접수기간 2026-06-20 ~ 2026-01-01",
            "2026-04-03",
            date(2026, 6, 19),
        )

        self.assertEqual("", dictDates["application_start_date"])
        self.assertEqual("", dictDates["application_end_date"])


if __name__ == "__main__":
    unittest.main()
