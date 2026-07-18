from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Callable
from typing import Any

import requests

from .utils import DurableStateError, load_durable_json, save_json


class AmbiguousDeliveryError(RuntimeError):
    """Raised when Telegram may have accepted a message but no receipt was saved."""


class DeliveryOutbox:
    def __init__(
        self,
        path: Path,
        max_delivered_entries: int = 2000,
        state_publisher: Callable[[Path], None] | None = None,
    ):
        self.path = path
        self.max_delivered_entries = max_delivered_entries
        self.state_publisher = state_publisher

    def delivery_id(self, chat_id: str, logical_key: str) -> str:
        identity = f"{chat_id}\n{logical_key}"
        return hashlib.sha256(identity.encode("utf-8", errors="replace")).hexdigest()

    def begin(
        self,
        delivery_id: str,
        logical_key: str = "",
        message_preview: str = "",
    ) -> bool:
        entries = self._load_entries()
        entry = entries.get(delivery_id, {})
        status = entry.get("status", "")

        if status == "delivered":
            return False
        if status in {"sending", "uncertain"}:
            raise AmbiguousDeliveryError(
                f"Telegram delivery {delivery_id} is ambiguous; automatic resend is blocked."
            )

        attempt_count = int(entry.get("attempt_count", 0)) + 1
        entries[delivery_id] = {
            "status": "sending",
            "attempt_count": attempt_count,
            "logical_key": logical_key,
            "message_preview": self._preview(message_preview),
            "updated_at": self._now_iso(),
        }
        self._save_entries(entries)
        return True

    def confirm(self, delivery_id: str, receipt: dict[str, Any] | None) -> None:
        entries = self._load_entries()
        entry = entries.get(delivery_id, {})
        message_id = receipt.get("message_id") if isinstance(receipt, dict) else None

        entry.update({
            "status": "delivered",
            "message_id": message_id,
            "updated_at": self._now_iso(),
        })
        entries[delivery_id] = entry
        self._prune_delivered(entries)
        self._save_entries(entries)

    def record_failure(self, delivery_id: str, error: Exception) -> None:
        entries = self._load_entries()
        entry = entries.get(delivery_id, {})
        retry_is_safe = self._is_definite_pre_delivery_failure(error)

        entry.update({
            "status": "failed" if retry_is_safe else "uncertain",
            "error_type": type(error).__name__,
            "updated_at": self._now_iso(),
        })
        entries[delivery_id] = entry
        self._save_entries(entries)

    def resolve(self, delivery_id: str, outcome: str) -> None:
        entries = self._load_entries()
        entry = entries.get(delivery_id)
        if entry is None:
            raise KeyError(f"Unknown delivery id: {delivery_id}")
        if outcome not in {"delivered", "retry"}:
            raise ValueError("Outcome must be 'delivered' or 'retry'.")

        entry["status"] = "delivered" if outcome == "delivered" else "failed"
        entry["resolved_at"] = self._now_iso()
        entry["updated_at"] = entry["resolved_at"]
        self._save_entries(entries)

    def unresolved(self) -> list[dict[str, str]]:
        entries = self._load_entries()
        return [
            {
                "delivery_id": delivery_id,
                "status": str(entry.get("status", "")),
                "logical_key": str(entry.get("logical_key", "")),
                "message_preview": str(entry.get("message_preview", "")),
                "updated_at": str(entry.get("updated_at", "")),
            }
            for delivery_id, entry in sorted(entries.items())
            if entry.get("status") in {"sending", "uncertain"}
        ]

    def _load_entries(self) -> dict[str, dict]:
        data = load_durable_json(self.path, {}, dict)
        allowed_statuses = {"sending", "uncertain", "failed", "delivered"}

        for delivery_id, entry in data.items():
            if not isinstance(delivery_id, str) or re.fullmatch(r"[0-9a-f]{64}", delivery_id) is None:
                raise DurableStateError(f"Delivery outbox has an invalid id: {self.path}")
            if not isinstance(entry, dict):
                raise DurableStateError(f"Delivery outbox has an invalid entry: {self.path}")
            if entry.get("status") not in allowed_statuses:
                raise DurableStateError(f"Delivery outbox has an invalid status: {self.path}")
            attempt_count = entry.get("attempt_count")
            if not isinstance(attempt_count, int) or isinstance(attempt_count, bool) or attempt_count < 1:
                raise DurableStateError(f"Delivery outbox has an invalid attempt count: {self.path}")
            if not isinstance(entry.get("updated_at"), str) or not entry["updated_at"]:
                raise DurableStateError(f"Delivery outbox has an invalid timestamp: {self.path}")
            for metadata_key in ("logical_key", "message_preview"):
                metadata_value = entry.get(metadata_key, "")
                if not isinstance(metadata_value, str):
                    raise DurableStateError(
                        f"Delivery outbox has invalid {metadata_key}: {self.path}"
                    )

        return data

    def _save_entries(self, entries: dict[str, dict]) -> None:
        save_json(self.path, entries)
        if self.state_publisher is not None:
            self.state_publisher(self.path)

    def _is_definite_pre_delivery_failure(self, error: Exception) -> bool:
        if isinstance(error, requests.ConnectTimeout):
            return True
        if isinstance(error, requests.HTTPError):
            response = error.response
            return response is not None and 400 <= response.status_code < 500
        if isinstance(error, requests.ConnectionError):
            error_text = str(error).lower()
            pre_connect_markers = (
                "failed to establish a new connection",
                "name resolution",
                "nodename nor servname",
                "connection refused",
            )
            return any(marker in error_text for marker in pre_connect_markers)
        return False

    def _prune_delivered(self, entries: dict[str, dict]) -> None:
        delivered_ids = [
            delivery_id
            for delivery_id, entry in entries.items()
            if entry.get("status") == "delivered"
        ]
        delivered_ids.sort(key=lambda delivery_id: str(entries[delivery_id].get("updated_at", "")))
        remove_count = len(delivered_ids) - self.max_delivered_entries

        for index in range(0, max(0, remove_count)):
            del entries[delivered_ids[index]]

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _preview(self, message: str, limit: int = 240) -> str:
        normalized_message = " ".join(message.split())
        return normalized_message[:limit]
