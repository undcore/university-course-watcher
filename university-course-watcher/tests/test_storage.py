from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.storage import GraduateAdmissionStorage


class GraduateAdmissionStorageTest(unittest.TestCase):
    def _item(self, **changes: object) -> dict:
        item = {
            "checked_at": "2026-07-15T20:00:00+09:00",
            "university_name": "테스트대학교",
            "region": "서울",
            "city": "서울",
            "board_type": "일반대학원 모집요강",
            "title": "2026학년도 후기 일반대학원 모집요강",
            "url": "https://example.com/admission",
            "notice_date": "2026-07-15",
            "grade": "A",
            "matched_keywords": ["2026", "후기", "일반대학원", "모집요강"],
            "reason": "테스트",
            "attachment_urls": ["https://example.com/2026.pdf"],
            "is_new": True,
        }
        item.update(changes)
        return item

    def test_same_content_with_new_url_is_not_new(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = GraduateAdmissionStorage(Path(directory))
            original = self._item()
            storage.update_seen([original])

            moved = self._item(url="https://example.com/admission?article=2")
            storage.mark_is_new([moved])

            self.assertFalse(moved["is_new"])

    def test_changed_content_at_same_url_is_new(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = GraduateAdmissionStorage(Path(directory))
            original = self._item()
            storage.save_results([original])
            storage.update_seen([original])

            changed = self._item(
                title="2027학년도 전기 일반대학원 모집요강",
                notice_date="2026-07-16",
                matched_keywords=["2027", "전기", "일반대학원", "모집요강"],
                attachment_urls=["https://example.com/2027.pdf"],
            )
            storage.mark_is_new([changed])

            self.assertTrue(changed["is_new"])

    def test_unchanged_empty_summary_is_suppressed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = GraduateAdmissionStorage(Path(directory))
            items = [self._item()]

            self.assertTrue(storage.should_send_empty_summary(items, 20, 4))
            storage.update_empty_summary_state(items, 20, 4)
            self.assertFalse(storage.should_send_empty_summary(items, 20, 4))
            self.assertTrue(storage.should_send_empty_summary(items, 21, 3))


if __name__ == "__main__":
    unittest.main()
