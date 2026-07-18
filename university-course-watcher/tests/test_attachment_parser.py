from __future__ import annotations

import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from requests.exceptions import SSLError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.attachment_parser import AttachmentParser
from src.http_state import HttpStateCache


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

    def test_uses_cached_text_for_not_modified_attachment(self) -> None:
        with tempfile.TemporaryDirectory() as sTempDirectory:
            cache = HttpStateCache(Path(sTempDirectory) / "state.json")
            sUrl = "https://example.com/download?id=3"
            cache.update(sUrl, {"ETag": '"v1"'}, b"old", extracted_text="cached text")
            parser = AttachmentParser(state_cache=cache)
            response = SimpleNamespace(status_code=304)
            session = Mock()
            session.get.return_value = response
            parser._session = Mock(return_value=session)

            sText = parser.extract_text(sUrl)

        self.assertEqual("cached text", sText)
        self.assertEqual('"v1"', session.get.call_args.kwargs["headers"]["If-None-Match"])

    def test_pdf_parser_limits_pages_to_configured_window(self) -> None:
        lstPages = []

        for iPageIndex in range(0, 10):
            page = Mock()
            page.extract_text.return_value = f"page-{iPageIndex}"
            lstPages.append(page)

        reader = SimpleNamespace(pages=lstPages)

        with patch("src.attachment_parser.PdfReader", return_value=reader):
            sText = self.parser._pdf_text(BytesIO(b"pdf"))

        self.assertIn("page-0", sText)
        self.assertIn("page-9", sText)
        self.assertNotIn("page-6", sText)
        self.assertNotIn("page-7", sText)

    def test_image_ocr_is_skipped_when_tesseract_binary_is_unavailable(self) -> None:
        class TesseractNotFoundError(Exception):
            pass

        response = Mock()
        response.raw.read.return_value = b"image bytes"
        image = SimpleNamespace(width=800, height=600, load=Mock())
        session = Mock()
        session.get.return_value = response
        fake_tesseract = SimpleNamespace(
            image_to_string=Mock(side_effect=TesseractNotFoundError("missing binary")),
        )
        fake_image_module = SimpleNamespace(open=Mock(return_value=image))
        self.parser._session = Mock(return_value=session)

        with patch("src.attachment_parser.pytesseract", fake_tesseract), patch(
            "src.attachment_parser.Image",
            fake_image_module,
        ):
            text = self.parser.extract_image_text("https://example.com/schedule.jpg")

        self.assertEqual("", text)

    def test_image_ocr_batch_contains_failure_without_aborting_other_images(self) -> None:
        self.parser.extract_image_text = Mock(side_effect=[RuntimeError("bad image"), "접수기간"])

        texts = self.parser.extract_image_texts([
            "https://example.com/bad.jpg",
            "https://example.com/good.jpg",
        ])

        self.assertEqual("", texts["https://example.com/bad.jpg"])
        self.assertEqual("접수기간", texts["https://example.com/good.jpg"])

    def test_attachment_ssl_verification_failure_is_not_retried_insecurely(self) -> None:
        sUrl = "https://example.com/schedule.pdf"
        session = Mock()
        session.get.side_effect = SSLError("certificate verify failed")
        self.parser._session = Mock(return_value=session)

        with self.assertRaisesRegex(SSLError, "certificate verify failed"):
            self.parser.extract_text(sUrl)

        session.get.assert_called_once_with(
            sUrl,
            headers={},
            timeout=(4, self.parser.timeout),
            stream=True,
        )

    def test_image_ssl_verification_failure_is_not_retried_insecurely(self) -> None:
        sUrl = "https://example.com/schedule.jpg"
        session = Mock()
        session.get.side_effect = SSLError("certificate verify failed")
        self.parser._session = Mock(return_value=session)

        with patch("src.attachment_parser.pytesseract", Mock()), patch(
            "src.attachment_parser.Image",
            Mock(),
        ), self.assertRaisesRegex(SSLError, "certificate verify failed"):
            self.parser.extract_image_text(sUrl)

        session.get.assert_called_once_with(
            sUrl,
            timeout=(4, self.parser.timeout),
            stream=True,
        )


if __name__ == "__main__":
    unittest.main()
