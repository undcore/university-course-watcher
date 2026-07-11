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


class GraduateAdmissionNotifierTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
