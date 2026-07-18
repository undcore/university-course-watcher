from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.notifier import GraduateAdmissionNotifier, TelegramNotifier
from src.delivery_outbox import DeliveryOutbox


class TelegramNotifierTest(unittest.TestCase):
    def test_candidate_failure_is_recorded_after_other_messages_continue(self) -> None:
        notifier = TelegramNotifier()
        notifier.token = "token"
        notifier.chat_id = "chat"
        notifier._send = Mock(side_effect=[RuntimeError("temporary failure"), None])
        sToday = date.today().isoformat()
        lstItems = [
            {"url": "https://example.com/1", "grade": "A", "is_new": True, "deadline_status": "모집중", "notice_date": sToday},
            {"url": "https://example.com/2", "grade": "B", "is_new": True, "deadline_status": "모집중", "notice_date": sToday},
        ]

        lstSentItems = notifier.send_candidates(lstItems)

        self.assertEqual(["https://example.com/2"], [dictItem["url"] for dictItem in lstSentItems])
        self.assertEqual(1, len(notifier.delivery_failures))

    def test_stale_candidate_is_not_sent(self) -> None:
        notifier = TelegramNotifier()
        notifier.token = "token"
        notifier.chat_id = "chat"
        notifier._send = Mock()
        lstItems = [
            {
                "url": "https://example.com/old",
                "grade": "A",
                "is_new": True,
                "deadline_status": "모집중",
                "notice_date": "2026-04-01",
            },
        ]

        lstSentItems = notifier.send_candidates(lstItems)

        self.assertEqual([], lstSentItems)
        notifier._send.assert_not_called()

    def test_changed_content_at_seen_url_is_sent(self) -> None:
        notifier = TelegramNotifier()
        notifier.token = "token"
        notifier.chat_id = "chat"
        notifier._send = Mock()
        item = {
            "url": "https://example.com/changed",
            "grade": "A",
            "is_new": False,
            "change_type": "content_changed",
            "deadline_status": "모집중",
            "notice_date": date.today().isoformat(),
        }

        sent_items = notifier.send_candidates([item])

        self.assertEqual([item], sent_items)
        notifier._send.assert_called_once()

    def test_successful_candidate_is_persisted_immediately(self) -> None:
        notifier = TelegramNotifier()
        notifier.token = "token"
        notifier.chat_id = "chat"
        notifier._send = Mock()
        on_sent = Mock()
        item = {
            "url": "https://example.com/new",
            "grade": "A",
            "is_new": True,
            "deadline_status": "open",
            "notice_date": date.today().isoformat(),
        }

        sent_items = notifier.send_candidates([item], on_sent=on_sent)

        self.assertEqual([item], sent_items)
        on_sent.assert_called_once_with([item])

    def test_persistence_failure_is_not_recorded_as_delivery_failure(self) -> None:
        notifier = TelegramNotifier()
        notifier.token = "token"
        notifier.chat_id = "chat"
        notifier._send = Mock()
        on_sent = Mock(side_effect=RuntimeError("state write failed"))
        item = {
            "url": "https://example.com/new",
            "grade": "A",
            "is_new": True,
            "deadline_status": "open",
            "notice_date": date.today().isoformat(),
        }

        with self.assertRaisesRegex(RuntimeError, "state write failed"):
            notifier.send_candidates([item], on_sent=on_sent)

        self.assertEqual([], notifier.delivery_failures)

    def test_confirmed_delivery_repairs_state_without_resending_after_callback_crash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outbox_path = Path(temp_dir) / "course_delivery_outbox.json"
            item = {
                "url": "https://example.com/recover",
                "grade": "A",
                "is_new": True,
                "deadline_status": "open",
                "notice_date": date.today().isoformat(),
            }
            first_notifier = TelegramNotifier(DeliveryOutbox(outbox_path))
            first_notifier.token = "token"
            first_notifier.chat_id = "chat"
            first_notifier._send = Mock(return_value={"message_id": 42})
            failed_persistence = Mock(side_effect=RuntimeError("state write interrupted"))

            with self.assertRaisesRegex(RuntimeError, "state write interrupted"):
                first_notifier.send_candidates([item], on_sent=failed_persistence)

            repaired_persistence = Mock()
            recovered_notifier = TelegramNotifier(DeliveryOutbox(outbox_path))
            recovered_notifier.token = "token"
            recovered_notifier.chat_id = "chat"
            recovered_notifier._send = Mock()

            sent_items = recovered_notifier.send_candidates([item], on_sent=repaired_persistence)

            self.assertEqual([item], sent_items)
            recovered_notifier._send.assert_not_called()
            repaired_persistence.assert_called_once_with([item])


class GraduateAdmissionNotifierTest(unittest.TestCase):
    def _portal_items(self, count: int) -> list[dict]:
        today = date.today().isoformat()
        return [
            {
                "url": f"https://apply.example.com/{index}",
                "grade": "A",
                "is_new": True,
                "board_type": "유웨이어플라이 대학원 전기",
                "title": f"대학 {index} 일반대학원",
                "notice_date": today,
            }
            for index in range(0, count)
        ]

    def _sorted_portal_items(
        self,
        notifier: GraduateAdmissionNotifier,
        items: list[dict],
    ) -> list[dict]:
        return sorted(
            items,
            key=lambda item: notifier._candidate_delivery_key("graduate-portal", item),
        )

    def test_unchanged_empty_summary_is_not_sent(self) -> None:
        notifier = GraduateAdmissionNotifier()
        notifier.token = "token"
        notifier.chat_id = "chat"
        notifier._send = Mock()

        sent = notifier.send_candidates([], send_empty_summary=False)

        self.assertEqual([], sent)
        self.assertFalse(notifier.summary_sent)
        notifier._send.assert_not_called()

    def test_portal_items_are_bundled_into_digest(self) -> None:
        notifier = GraduateAdmissionNotifier()
        notifier.token = "token"
        notifier.chat_id = "chat"
        notifier._send = Mock()
        sToday = date.today().isoformat()
        lstItems = [
            {"url": f"https://apply.example.com/{i}", "grade": "A", "is_new": True,
             "board_type": "유웨이어플라이 대학원 후기", "title": f"대학{i} 일반대학원", "notice_date": sToday}
            for i in range(30)
        ] + [
            {"url": "https://univ.example.com/board", "grade": "A", "is_new": True,
             "board_type": "대학원 입학 공지", "title": "일반대학원 모집요강", "notice_date": sToday},
        ]

        lstSentItems = notifier.send_candidates(lstItems)

        # 게시판 1건 개별 + 포털 30건은 다이제스트 2통(25건 단위 분할) = 총 3회 발송
        self.assertEqual(31, len(lstSentItems))
        self.assertEqual(3, notifier._send.call_count)

    def test_only_successful_portal_digest_batch_is_returned(self) -> None:
        notifier = GraduateAdmissionNotifier()
        notifier.token = "token"
        notifier.chat_id = "chat"
        notifier._send = Mock(side_effect=[None, RuntimeError("second batch failed")])
        items = self._portal_items(30)

        sent_items = notifier.send_candidates(items)

        expected_items = self._sorted_portal_items(notifier, items)
        self.assertEqual(expected_items[:25], sent_items)
        self.assertEqual(["second batch failed"], notifier.delivery_failures)
        self.assertEqual(2, notifier._send.call_count)

    def test_later_portal_digest_batch_continues_after_earlier_failure(self) -> None:
        notifier = GraduateAdmissionNotifier()
        notifier.token = "token"
        notifier.chat_id = "chat"
        notifier._send = Mock(side_effect=[RuntimeError("first batch failed"), None])
        items = self._portal_items(30)

        sent_items = notifier.send_candidates(items)

        expected_items = self._sorted_portal_items(notifier, items)
        self.assertEqual(expected_items[25:], sent_items)
        self.assertEqual(["first batch failed"], notifier.delivery_failures)
        self.assertEqual(2, notifier._send.call_count)

    def test_successful_portal_batches_are_persisted_individually(self) -> None:
        notifier = GraduateAdmissionNotifier()
        notifier.token = "token"
        notifier.chat_id = "chat"
        notifier._send = Mock()
        on_sent = Mock()
        items = self._portal_items(30)

        sent_items = notifier.send_candidates(items, on_sent=on_sent)

        expected_items = self._sorted_portal_items(notifier, items)
        self.assertEqual(expected_items, sent_items)
        self.assertEqual(2, on_sent.call_count)
        self.assertEqual(expected_items[:25], on_sent.call_args_list[0].args[0])
        self.assertEqual(expected_items[25:], on_sent.call_args_list[1].args[0])

    def test_portal_delivery_key_ignores_volatile_notice_date(self) -> None:
        notifier = GraduateAdmissionNotifier()
        first_item = self._portal_items(1)[0]
        second_item = dict(first_item)
        second_item["notice_date"] = "2099-12-31"

        first_key = notifier._candidate_delivery_key("graduate-portal", first_item)
        second_key = notifier._candidate_delivery_key("graduate-portal", second_item)

        self.assertEqual(first_key, second_key)

    def test_portal_digest_batching_is_independent_of_source_order(self) -> None:
        items = self._portal_items(30)
        forward_notifier = GraduateAdmissionNotifier()
        forward_notifier.token = "token"
        forward_notifier.chat_id = "chat"
        forward_notifier._deliver_once = Mock()
        reverse_notifier = GraduateAdmissionNotifier()
        reverse_notifier.token = "token"
        reverse_notifier.chat_id = "chat"
        reverse_notifier._deliver_once = Mock()

        forward_notifier.send_candidates(items)
        reverse_notifier.send_candidates(list(reversed(items)))

        self.assertEqual(
            forward_notifier._deliver_once.call_args_list,
            reverse_notifier._deliver_once.call_args_list,
        )

    def test_confirmed_portal_digest_repairs_state_without_resending(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outbox_path = Path(temp_dir) / "graduate_delivery_outbox.json"
            items = self._portal_items(2)
            first_notifier = GraduateAdmissionNotifier(DeliveryOutbox(outbox_path))
            first_notifier.token = "token"
            first_notifier.chat_id = "chat"
            first_notifier._send = Mock(return_value={"message_id": 77})

            with self.assertRaisesRegex(RuntimeError, "state write interrupted"):
                first_notifier.send_candidates(
                    items,
                    on_sent=Mock(side_effect=RuntimeError("state write interrupted")),
                )

            recovered_items = [dict(item) for item in items]
            repaired_persistence = Mock()
            recovered_notifier = GraduateAdmissionNotifier(DeliveryOutbox(outbox_path))
            recovered_notifier.token = "token"
            recovered_notifier.chat_id = "chat"
            recovered_notifier._send = Mock()

            sent_items = recovered_notifier.send_candidates(
                recovered_items,
                on_sent=repaired_persistence,
            )

            self.assertEqual(recovered_items, sent_items)
            recovered_notifier._send.assert_not_called()
            repaired_persistence.assert_called_once_with(recovered_items)

    def test_empty_summary_uses_stable_external_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outbox_path = Path(temp_dir) / "graduate_delivery_outbox.json"
            item = {
                "url": "https://example.com/reference",
                "grade": "C",
                "is_new": False,
                "checked_at": "2026-07-18T09:00:00+09:00",
            }
            first_notifier = GraduateAdmissionNotifier(DeliveryOutbox(outbox_path))
            first_notifier.token = "token"
            first_notifier.chat_id = "chat"
            first_notifier._send = Mock(return_value={"message_id": 88})
            first_notifier.send_candidates([item], summary_delivery_key="graduate-empty:stable")

            recovered_item = dict(item, checked_at="2026-07-19T09:00:00+09:00")
            recovered_notifier = GraduateAdmissionNotifier(DeliveryOutbox(outbox_path))
            recovered_notifier.token = "token"
            recovered_notifier.chat_id = "chat"
            recovered_notifier._send = Mock()

            recovered_notifier.send_candidates(
                [recovered_item],
                summary_delivery_key="graduate-empty:stable",
            )

            recovered_notifier._send.assert_not_called()
            self.assertTrue(recovered_notifier.summary_sent)

    def test_failed_portal_digest_batch_can_be_retried_without_resending_successes(self) -> None:
        items = self._portal_items(30)
        first_notifier = GraduateAdmissionNotifier()
        first_notifier.token = "token"
        first_notifier.chat_id = "chat"
        first_notifier._send = Mock(side_effect=[None, RuntimeError("temporary failure")])

        first_sent = first_notifier.send_candidates(items)
        retry_items = [item for item in items if item not in first_sent]

        retry_notifier = GraduateAdmissionNotifier()
        retry_notifier.token = "token"
        retry_notifier.chat_id = "chat"
        retry_notifier._send = Mock()
        retry_sent = retry_notifier.send_candidates(retry_items)

        expected_items = self._sorted_portal_items(first_notifier, items)
        self.assertEqual(expected_items[:25], first_sent)
        expected_retry_urls = {item["url"] for item in expected_items[25:]}
        actual_retry_urls = {item["url"] for item in retry_items}
        self.assertEqual(expected_retry_urls, actual_retry_urls)
        self.assertEqual(expected_items[25:], retry_sent)
        retry_notifier._send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
