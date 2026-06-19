from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.attachment_parser import AttachmentParser


class AttachmentParserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = AttachmentParser()

    def test_detects_pdf_from_content_type(self) -> None:
        response = SimpleNamespace(headers={"Content-Type": "application/pdf; charset=binary"})

        sSuffix = self.parser._detect_suffix("https://example.com/download?id=1", response)

        self.assertEqual(".pdf", sSuffix)

    def test_detects_docx_from_content_disposition(self) -> None:
        response = SimpleNamespace(
            headers={"Content-Disposition": 'attachment; filename="application.docx"'},
        )

        sSuffix = self.parser._detect_suffix("https://example.com/download?id=2", response)

        self.assertEqual(".docx", sSuffix)


if __name__ == "__main__":
    unittest.main()
