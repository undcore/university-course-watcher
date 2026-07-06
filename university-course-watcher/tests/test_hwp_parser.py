from __future__ import annotations

import io
import sys
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.attachment_parser import AttachmentParser
from src.hwp_parser import (
    HWPTAG_PARA_TEXT,
    _decode_para_text,
    _hwp_section_paragraphs,
    extract_hwp_text,
    extract_hwpx_text,
)


def _para_record(text: str) -> bytes:
    payload = text.encode("utf-16-le")
    header = HWPTAG_PARA_TEXT | (0 << 10) | (len(payload) << 20)
    return header.to_bytes(4, "little") + payload


def _build_hwpx(*paragraphs: str) -> bytes:
    runs = "".join(
        f"<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>" for text in paragraphs
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<hml xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
        f"{runs}</hml>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Contents/section0.xml", xml)
    return buffer.getvalue()


class HwpxTest(unittest.TestCase):
    def test_extracts_paragraph_text(self) -> None:
        data = _build_hwpx("2026학년도 후기 일반대학원 모집요강", "원서접수 안내")

        text = extract_hwpx_text(data)

        self.assertIn("2026학년도 후기 일반대학원 모집요강", text)
        self.assertIn("원서접수 안내", text)

    def test_non_zip_returns_empty(self) -> None:
        self.assertEqual("", extract_hwpx_text(b"not a zip"))

    def test_extract_text_pipes_hwpx_through_parser(self) -> None:
        data = _build_hwpx("2026 후기 일반대학원 모집요강")
        url = "https://example.com/notice/guide.hwpx"
        response = SimpleNamespace(
            headers={},
            raise_for_status=lambda: None,
            raw=SimpleNamespace(read=lambda *a, **k: data),
        )
        parser = AttachmentParser()
        parser.session = Mock()
        parser.session.get.return_value = response

        text = parser.extract_text(url)

        self.assertIn("2026 후기 일반대학원 모집요강", text)


class HwpBinaryTest(unittest.TestCase):
    def test_para_text_record_decoded(self) -> None:
        stream = _para_record("모집요강")

        self.assertEqual(["모집요강"], _hwp_section_paragraphs(stream))

    def test_long_control_bytes_are_skipped(self) -> None:
        payload = "시간제".encode("utf-16-le") + (4).to_bytes(2, "little") + b"\x00" * 14
        payload += "등록".encode("utf-16-le")

        self.assertEqual("시간제등록", _decode_para_text(payload))

    def test_paragraph_break_becomes_newline(self) -> None:
        payload = "가".encode("utf-16-le") + (13).to_bytes(2, "little") + "나".encode("utf-16-le")

        self.assertEqual("가\n나", _decode_para_text(payload))

    def test_invalid_ole_returns_empty(self) -> None:
        self.assertEqual("", extract_hwp_text(b"garbage-not-ole"))


if __name__ == "__main__":
    unittest.main()
