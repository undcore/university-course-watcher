from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.notifier import GraduateAdmissionNotifier, TelegramNotifier


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

        self.assertEqual(items[:25], sent_items)
        self.assertEqual(["second batch failed"], notifier.delivery_failures)
        self.assertEqual(2, notifier._send.call_count)

    def test_later_portal_digest_batch_continues_after_earlier_failure(self) -> None:
        notifier = GraduateAdmissionNotifier()
        notifier.token = "token"
        notifier.chat_id = "chat"
        notifier._send = Mock(side_effect=[RuntimeError("first batch failed"), None])
        items = self._portal_items(30)

        sent_items = notifier.send_candidates(items)

        self.assertEqual(items[25:], sent_items)
        self.assertEqual(["first batch failed"], notifier.delivery_failures)
        self.assertEqual(2, notifier._send.call_count)

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

        self.assertEqual(items[:25], first_sent)
        self.assertEqual(items[25:], retry_items)
        self.assertEqual(items[25:], retry_sent)
        retry_notifier._send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
