from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from main import items_to_mark_seen, report_preview_items


class DailyReportTest(unittest.TestCase):
    def test_preview_contains_only_new_public_items(self) -> None:
        lstItems = [
            {"grade": "A", "is_new": False, "title": "existing A"},
            {"grade": "B", "is_new": True, "title": "new B"},
            {"grade": "C", "is_new": True, "title": "new C"},
            {"grade": "D", "is_new": True, "title": "new D"},
        ]

        lstPreview = report_preview_items(lstItems)

        self.assertEqual(["new B", "new C"], [dictItem["title"] for dictItem in lstPreview])

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


if __name__ == "__main__":
    unittest.main()
