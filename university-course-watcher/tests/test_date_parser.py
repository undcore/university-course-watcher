from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.date_parser import parse_notice_dates


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


if __name__ == "__main__":
    unittest.main()
