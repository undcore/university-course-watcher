from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.storage import HISTORY_FIELDS, Storage


class HistoryAccumulationTest(unittest.TestCase):
    def _item(self, url: str, title: str, checked_at: str, **overrides) -> dict:
        item = {
            "university_name": "테스트대학교",
            "region": "서울",
            "title": title,
            "url": url,
            "notice_date": "2026-06-10",
            "application_start_date": "",
            "application_end_date": "",
            "source_type": "대학 공식 게시판 직접 크롤링",
            "registration_score": 60,
            "checked_at": checked_at,
        }
        item.update(overrides)
        return item

    def _read(self, storage: Storage) -> list[dict]:
        with storage.history_csv.open("r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def test_history_accumulates_across_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp))
            storage._save_history([self._item("https://u/1", "첫 공고", "2026-06-01T09:00:00")])
            storage._save_history([self._item("https://u/2", "둘째 공고", "2026-06-02T09:00:00")])

            rows = self._read(storage)

        self.assertEqual(["https://u/1", "https://u/2"], [r["url"] for r in rows])
        self.assertEqual("2026-06-01T09:00:00", rows[0]["first_seen_at"])

    def test_existing_notice_updates_last_seen_and_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp))
            storage._save_history([self._item("https://u/1", "공고", "2026-06-01T09:00:00")])
            storage._save_history([
                self._item("https://u/1", "공고", "2026-06-05T09:00:00",
                           application_start_date="2026-07-01"),
            ])

            rows = self._read(storage)

        self.assertEqual(1, len(rows))
        self.assertEqual("2026-06-01T09:00:00", rows[0]["first_seen_at"])
        self.assertEqual("2026-06-05T09:00:00", rows[0]["last_seen_at"])
        self.assertEqual("2026-07-01", rows[0]["application_start_date"])

    def test_low_score_items_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp))
            storage._save_history([self._item("https://u/1", "낮은 점수", "2026-06-01T09:00:00",
                                              registration_score=10)])

            self.assertFalse(storage.history_csv.exists())

    def test_header_uses_history_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp))
            storage.ensure_empty_files()
            with storage.history_csv.open("r", encoding="utf-8-sig", newline="") as f:
                header = next(csv.reader(f))

        self.assertEqual(HISTORY_FIELDS, header)


if __name__ == "__main__":
    unittest.main()
