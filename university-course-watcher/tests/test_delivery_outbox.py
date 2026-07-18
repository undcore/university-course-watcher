from __future__ import annotations

import sys
import tempfile
import unittest
import json
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.delivery_outbox import AmbiguousDeliveryError, DeliveryOutbox
from src.utils import DurableStateError


class DeliveryOutboxTest(unittest.TestCase):
    def test_sending_state_is_published_before_caller_can_send(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "outbox.json"
            published_statuses: list[str] = []

            def publish_state(state_path: Path) -> None:
                entries = json.loads(state_path.read_text(encoding="utf-8"))
                published_statuses.append(next(iter(entries.values()))["status"])

            outbox = DeliveryOutbox(path, state_publisher=publish_state)
            delivery_id = outbox.delivery_id("chat", "message")

            self.assertTrue(outbox.begin(delivery_id))

            self.assertEqual(["sending"], published_statuses)

    def test_publish_failure_blocks_begin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "outbox.json"

            def reject_publish(state_path: Path) -> None:
                raise RuntimeError(f"remote unavailable: {state_path.name}")

            outbox = DeliveryOutbox(path, state_publisher=reject_publish)
            delivery_id = outbox.delivery_id("chat", "message")

            with self.assertRaisesRegex(RuntimeError, "remote unavailable"):
                outbox.begin(delivery_id)

    def test_confirmed_delivery_is_not_sent_again(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "outbox.json"
            outbox = DeliveryOutbox(path)
            delivery_id = outbox.delivery_id("chat", "message")

            self.assertTrue(outbox.begin(delivery_id))
            outbox.confirm(delivery_id, {"message_id": 42})

            recovered_outbox = DeliveryOutbox(path)
            self.assertFalse(recovered_outbox.begin(delivery_id))

    def test_interrupted_sending_is_quarantined_instead_of_resent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "outbox.json"
            outbox = DeliveryOutbox(path)
            delivery_id = outbox.delivery_id("chat", "message")

            self.assertTrue(outbox.begin(delivery_id))

            recovered_outbox = DeliveryOutbox(path)
            with self.assertRaisesRegex(AmbiguousDeliveryError, "automatic resend is blocked"):
                recovered_outbox.begin(delivery_id)

    def test_http_client_rejection_can_be_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outbox = DeliveryOutbox(Path(temp_dir) / "outbox.json")
            delivery_id = outbox.delivery_id("chat", "message")
            response = requests.Response()
            response.status_code = 400
            error = requests.HTTPError("server rejected request", response=response)

            self.assertTrue(outbox.begin(delivery_id))
            outbox.record_failure(delivery_id, error)

            self.assertTrue(outbox.begin(delivery_id))

    def test_http_server_failure_is_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outbox = DeliveryOutbox(Path(temp_dir) / "outbox.json")
            delivery_id = outbox.delivery_id("chat", "message")
            response = requests.Response()
            response.status_code = 503
            error = requests.HTTPError("upstream failed", response=response)

            self.assertTrue(outbox.begin(delivery_id))
            outbox.record_failure(delivery_id, error)

            with self.assertRaises(AmbiguousDeliveryError):
                outbox.begin(delivery_id)

    def test_connect_timeout_can_be_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outbox = DeliveryOutbox(Path(temp_dir) / "outbox.json")
            delivery_id = outbox.delivery_id("chat", "message")

            self.assertTrue(outbox.begin(delivery_id))
            outbox.record_failure(delivery_id, requests.ConnectTimeout("connect failed"))

            self.assertTrue(outbox.begin(delivery_id))

    def test_network_failure_is_ambiguous_and_not_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outbox = DeliveryOutbox(Path(temp_dir) / "outbox.json")
            delivery_id = outbox.delivery_id("chat", "message")

            self.assertTrue(outbox.begin(delivery_id))
            outbox.record_failure(delivery_id, requests.Timeout("response lost"))

            with self.assertRaises(AmbiguousDeliveryError):
                outbox.begin(delivery_id)

    def test_operator_can_resolve_ambiguous_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outbox = DeliveryOutbox(Path(temp_dir) / "outbox.json")
            delivery_id = outbox.delivery_id("chat", "message")
            self.assertTrue(outbox.begin(delivery_id))

            outbox.resolve(delivery_id, "delivered")

            self.assertFalse(outbox.begin(delivery_id))

    def test_pruning_keeps_ambiguous_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outbox = DeliveryOutbox(Path(temp_dir) / "outbox.json", max_delivered_entries=1)
            ambiguous_id = outbox.delivery_id("chat", "ambiguous")
            first_id = outbox.delivery_id("chat", "first")
            second_id = outbox.delivery_id("chat", "second")
            self.assertTrue(outbox.begin(ambiguous_id, "course:url", "Candidate message"))
            self.assertTrue(outbox.begin(first_id))
            outbox.confirm(first_id, {"message_id": 1})
            self.assertTrue(outbox.begin(second_id))
            outbox.confirm(second_id, {"message_id": 2})

            unresolved = outbox.unresolved()

            self.assertEqual(
                {
                    "delivery_id": ambiguous_id,
                    "status": "sending",
                    "logical_key": "course:url",
                    "message_preview": "Candidate message",
                },
                {key: value for key, value in unresolved[0].items() if key != "updated_at"},
            )

    def test_unresolved_delivery_includes_safe_reconciliation_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outbox = DeliveryOutbox(Path(temp_dir) / "outbox.json")
            delivery_id = outbox.delivery_id("chat", "course:https://example.com/notice")
            long_message = "Candidate\n" + ("detail " * 80)

            self.assertTrue(
                outbox.begin(
                    delivery_id,
                    "course:https://example.com/notice",
                    long_message,
                )
            )
            unresolved = outbox.unresolved()

            self.assertEqual("course:https://example.com/notice", unresolved[0]["logical_key"])
            self.assertTrue(unresolved[0]["message_preview"].startswith("Candidate detail"))
            self.assertLessEqual(len(unresolved[0]["message_preview"]), 240)

    def test_corrupt_outbox_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "outbox.json"
            path.write_text("not-json", encoding="utf-8")
            outbox = DeliveryOutbox(path)

            with self.assertRaises(DurableStateError):
                outbox.unresolved()

    def test_invalid_nested_entry_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "outbox.json"
            delivery_id = "a" * 64
            path.write_text(json.dumps({delivery_id: {"status": "delivered"}}), encoding="utf-8")
            outbox = DeliveryOutbox(path)

            with self.assertRaisesRegex(DurableStateError, "attempt count"):
                outbox.unresolved()


if __name__ == "__main__":
    unittest.main()
