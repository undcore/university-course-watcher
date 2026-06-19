from __future__ import annotations

import os
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.recency import is_recent_notice, is_stale_notice


class NoticeRecencyTest(unittest.TestCase):
    def test_notice_within_seven_days_is_recent(self) -> None:
        dictItem = {"notice_date": "2026-06-14"}

        self.assertTrue(is_recent_notice(dictItem, date(2026, 6, 20)))
        self.assertFalse(is_stale_notice(dictItem, date(2026, 6, 20)))

    def test_march_and_april_notices_are_stale(self) -> None:
        for sNoticeDate in ["2026-03-31", "2026-04-15"]:
            with self.subTest(sNoticeDate=sNoticeDate):
                dictItem = {"notice_date": sNoticeDate}
                self.assertFalse(is_recent_notice(dictItem, date(2026, 6, 20)))
                self.assertTrue(is_stale_notice(dictItem, date(2026, 6, 20)))

    def test_unknown_and_future_dates_are_not_recent(self) -> None:
        self.assertFalse(is_recent_notice({"notice_date": ""}, date(2026, 6, 20)))
        self.assertFalse(is_recent_notice({"notice_date": "2026-06-21"}, date(2026, 6, 20)))

    def test_max_age_is_configurable(self) -> None:
        with patch.dict(os.environ, {"NOTICE_MAX_AGE_DAYS": "3"}):
            self.assertFalse(is_recent_notice({"notice_date": "2026-06-16"}, date(2026, 6, 20)))


if __name__ == "__main__":
    unittest.main()
