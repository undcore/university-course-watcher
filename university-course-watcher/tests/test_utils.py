from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils import DurableStateError, load_durable_json, load_json, save_json


class JsonStateTest(unittest.TestCase):
    def test_corrupt_json_falls_back_to_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text('{"unfinished":', encoding="utf-8")

            self.assertEqual({}, load_json(path, {}))

    def test_surrogate_text_is_replaced_and_saved_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"

            save_json(path, {"text": "broken-\ud800-value"})

            loaded = load_json(path, {})
            self.assertIn("broken-", loaded["text"])
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_corrupt_durable_state_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "seen_urls.json"
            path.write_text('["sent",', encoding="utf-8")

            with self.assertRaisesRegex(DurableStateError, "unreadable"):
                load_durable_json(path, [], list)

    def test_invalid_durable_state_structure_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notice_state.json"
            path.write_text("[]", encoding="utf-8")

            with self.assertRaisesRegex(DurableStateError, "invalid structure"):
                load_durable_json(path, {}, dict)


if __name__ == "__main__":
    unittest.main()
