from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.http_state import HttpStateCache


class HttpStateCacheTest(unittest.TestCase):
    def test_persists_conditional_headers_and_cached_value(self) -> None:
        with tempfile.TemporaryDirectory() as sTempDirectory:
            pathState = Path(sTempDirectory) / "http_state.json"
            cache = HttpStateCache(pathState)
            cache.update(
                "https://example.com/file",
                {"ETag": '"abc"', "Last-Modified": "Fri, 20 Jun 2026 00:00:00 GMT"},
                b"content",
                extracted_text="cached text",
            )
            cache.save()

            restored = HttpStateCache(pathState)

        self.assertEqual(
            {"If-None-Match": '"abc"', "If-Modified-Since": "Fri, 20 Jun 2026 00:00:00 GMT"},
            restored.conditional_headers("https://example.com/file"),
        )
        self.assertEqual("cached text", restored.cached_value("https://example.com/file", "extracted_text"))
        self.assertTrue(restored.content_matches("https://example.com/file", b"content"))
        self.assertFalse(restored.content_matches("https://example.com/file", b"changed"))


if __name__ == "__main__":
    unittest.main()
