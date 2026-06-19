from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.notifier import TelegramNotifier


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


if __name__ == "__main__":
    unittest.main()
