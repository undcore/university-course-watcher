from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.storage import GraduateAdmissionStorage, Storage
from src.utils import DurableStateError


class CourseStorageChangeTest(unittest.TestCase):
    def _item(self, fingerprint: str = "fingerprint-1", grade: str = "A") -> dict:
        return {
            "url": "https://example.com/course",
            "content_fingerprint": fingerprint,
            "grade": grade,
            "deadline_status": "모집중",
            "checked_at": "2026-07-15T20:00:00+09:00",
        }

    def test_same_url_content_change_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            original = self._item()
            storage.update_notice_state([original])

            changed = self._item(fingerprint="fingerprint-2")
            storage.mark_changes([changed])

            self.assertEqual("content_changed", changed["change_type"])
            self.assertEqual("A", changed["previous_grade"])

    def test_unchanged_item_is_not_realerted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            original = self._item()
            storage.update_notice_state([original])

            current = self._item()
            storage.mark_changes([current])

            self.assertEqual("unchanged", current["change_type"])

    def test_existing_seen_url_bootstraps_without_duplicate_alert(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            item = self._item()
            storage.update_seen([item])

            storage.mark_changes([item])

            self.assertEqual("unchanged", item["change_type"])

    def test_notice_state_preserves_temporarily_unobserved_items(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            first = self._item()
            first["url"] = "https://example.com/first"
            second = self._item(fingerprint="fingerprint-2")
            second["url"] = "https://example.com/second"
            storage.update_notice_state([first, second])

            refreshed_first = self._item(fingerprint="fingerprint-3")
            refreshed_first["url"] = first["url"]
            storage.update_notice_state([refreshed_first])

            recovered_second = self._item(fingerprint="fingerprint-2")
            recovered_second["url"] = second["url"]
            storage.mark_changes([recovered_second])

            self.assertEqual("unchanged", recovered_second["change_type"])

    def test_notice_state_merge_updates_observed_item(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            original = self._item()
            storage.update_notice_state([original])

            changed = self._item(fingerprint="fingerprint-2")
            storage.update_notice_state([changed])
            storage.mark_changes([changed])

            self.assertEqual("unchanged", changed["change_type"])

    def test_mark_notified_preserves_change_detection_when_seen_write_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            original = self._item()

            def fail_seen_write(items: list[dict]) -> None:
                raise RuntimeError("seen write interrupted")

            storage.update_seen = fail_seen_write

            with self.assertRaisesRegex(RuntimeError, "seen write interrupted"):
                storage.mark_notified([original])

            unchanged = self._item()
            storage.mark_changes([unchanged])
            self.assertEqual("unchanged", unchanged["change_type"])

            changed = self._item(fingerprint="fingerprint-2")
            storage.mark_changes([changed])
            self.assertEqual("content_changed", changed["change_type"])

    def test_corrupt_seen_state_stops_new_item_classification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            storage.seen_path.write_text('["sent",', encoding="utf-8")

            with self.assertRaises(DurableStateError):
                storage.mark_is_new([self._item()])

    def test_semantically_invalid_seen_state_stops_new_item_classification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            storage.seen_path.write_text('["sent", 123]', encoding="utf-8")

            with self.assertRaises(DurableStateError):
                storage.mark_is_new([self._item()])

    def test_corrupt_notice_state_stops_change_classification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            storage.notice_state_path.write_text("[]", encoding="utf-8")

            with self.assertRaises(DurableStateError):
                storage.mark_changes([self._item()])


class CourseStorageHistoryTest(unittest.TestCase):
    def _item(self, url: str, title: str, **changes: object) -> dict:
        item = {
            "university_name": "테스트대학교",
            "region": "서울",
            "title": title,
            "url": url,
            "notice_date": "2026-07-18",
            "application_start_date": "2026-07-20",
            "application_end_date": "2026-07-25",
            "source_type": "board",
            "registration_score": 80,
            "grade": "A",
        }
        item.update(changes)
        return item

    def _read_history(self, storage: Storage) -> list[dict]:
        with storage.history_csv.open("r", encoding="utf-8-sig", newline="") as file:
            return list(csv.DictReader(file))

    def test_history_accumulates_across_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            first = self._item("https://example.com/first", "2026학년도 1학기 모집")
            second = self._item("https://example.com/second", "2026학년도 2학기 모집")

            storage.save_results([first])
            storage.save_results([second])

            rows = self._read_history(storage)
            self.assertEqual(2, len(rows))
            self.assertEqual(
                ["https://example.com/first", "https://example.com/second"],
                [row["url"] for row in rows],
            )

    def test_existing_url_is_updated_instead_of_duplicated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            original = self._item("https://example.com/course", "기존 제목")
            updated = self._item(
                "https://example.com/course",
                "수정된 제목",
                application_end_date="2026-07-31",
            )

            storage.save_results([original])
            storage.save_results([updated])

            rows = self._read_history(storage)
            self.assertEqual(1, len(rows))
            self.assertEqual("수정된 제목", rows[0]["title"])
            self.assertEqual("2026-07-31", rows[0]["application_end_date"])

    def test_title_key_updates_url_less_history_and_empty_run_preserves_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            original = self._item("", "URL 없는 공고", region="서울")
            updated = self._item("", "URL 없는 공고", region="경기")

            storage.save_results([original])
            storage.save_results([updated])
            storage.save_results([])

            rows = self._read_history(storage)
            self.assertEqual(1, len(rows))
            self.assertEqual("경기", rows[0]["region"])

    def test_history_serialization_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as first_directory, tempfile.TemporaryDirectory() as second_directory:
            first_storage = Storage(Path(first_directory))
            second_storage = Storage(Path(second_directory))
            alpha = self._item("https://example.com/a", "A 공고")
            beta = self._item("https://example.com/b", "B 공고")

            first_storage.save_results([beta, alpha, beta])
            second_storage.save_results([alpha, beta])

            self.assertEqual(
                first_storage.history_csv.read_bytes(),
                second_storage.history_csv.read_bytes(),
            )

    def test_external_text_is_neutralized_in_csv_but_preserved_in_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            item = self._item("https://example.com/formula", "=HYPERLINK(\"bad\")")

            storage.save_results([item])

            with storage.results_csv.open("r", encoding="utf-8-sig", newline="") as file:
                csv_item = next(csv.DictReader(file))

            self.assertEqual("'=HYPERLINK(\"bad\")", csv_item["title"])
            self.assertIn('"title": "=HYPERLINK', storage.results_json.read_text(encoding="utf-8"))


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

    def test_corrupt_empty_summary_state_stops_summary_send_decision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = GraduateAdmissionStorage(Path(directory))
            storage.summary_state_path.write_text('{"fingerprint":', encoding="utf-8")

            with self.assertRaises(DurableStateError):
                storage.should_send_empty_summary([], 20, 4)

    def test_portal_item_is_not_new_again_on_the_next_day(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            storage = GraduateAdmissionStorage(Path(directory))
            original = self._item(
                board_type="유웨이어플라이 대학원 원서접수",
                notice_date="2026-07-15",
            )
            storage.update_seen([original])

            next_day = self._item(
                board_type="유웨이어플라이 대학원 원서접수",
                notice_date="2026-07-16",
            )
            storage.mark_is_new([next_day])

            self.assertFalse(next_day["is_new"])


if __name__ == "__main__":
    unittest.main()
