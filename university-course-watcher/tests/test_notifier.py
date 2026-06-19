from __future__ import annotations

import sys
import unittest
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
        lstItems = [
            {"url": "https://example.com/1", "grade": "A", "is_new": True, "deadline_status": "모집중"},
            {"url": "https://example.com/2", "grade": "B", "is_new": True, "deadline_status": "모집중"},
        ]

        lstSentItems = notifier.send_candidates(lstItems)

        self.assertEqual(["https://example.com/2"], [dictItem["url"] for dictItem in lstSentItems])
        self.assertEqual(1, len(notifier.delivery_failures))


if __name__ == "__main__":
    unittest.main()
