from __future__ import annotations

import io
import logging
from urllib.parse import urlparse

import requests
from requests.exceptions import SSLError

try:
    from docx import Document
except ImportError:  # pragma: no cover
    Document = None

try:
    from openpyxl import load_workbook
except ImportError:  # pragma: no cover
    load_workbook = None

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None

LOGGER = logging.getLogger(__name__)


class AttachmentParser:
    def __init__(self, timeout: int = 20, max_bytes: int = 8_000_000):
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 university-course-watcher/1.0"})

    def extract_texts(self, urls: list[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        for url in urls:
            try:
                result[url] = self.extract_text(url)
            except Exception as exc:
                LOGGER.info("Attachment parse skipped: %s %s", url, exc)
                result[url] = ""
        return result

    def extract_text(self, url: str) -> str:
        suffix = self._suffix(url)
        if suffix in {".hwp", ".hwpx", ".zip"}:
            return ""
        try:
            response = self.session.get(url, timeout=self.timeout, stream=True)
        except SSLError:
            response = self.session.get(url, timeout=self.timeout, stream=True, verify=False)
        response.raise_for_status()
        content = response.raw.read(self.max_bytes + 1, decode_content=True)
        if len(content) > self.max_bytes:
            LOGGER.info("Attachment too large, skipped text extraction: %s", url)
            return ""
        data = io.BytesIO(content)
        if suffix == ".pdf":
            if PdfReader is None:
                return ""
            return self._pdf_text(data)
        if suffix == ".docx":
            if Document is None:
                return ""
            return self._docx_text(data)
        if suffix == ".xlsx":
            if load_workbook is None:
                return ""
            return self._xlsx_text(data)
        return ""

    def _suffix(self, url: str) -> str:
        path = urlparse(url).path.lower()
        for suffix in [".pdf", ".hwp", ".hwpx", ".doc", ".docx", ".xls", ".xlsx", ".zip"]:
            if path.endswith(suffix):
                return suffix
        return ""

    def _pdf_text(self, data: io.BytesIO) -> str:
        reader = PdfReader(data)
        return "\n".join(page.extract_text() or "" for page in reader.pages)[:12000]

    def _docx_text(self, data: io.BytesIO) -> str:
        doc = Document(data)
        return "\n".join(p.text for p in doc.paragraphs)[:12000]

    def _xlsx_text(self, data: io.BytesIO) -> str:
        wb = load_workbook(data, read_only=True, data_only=True)
        values: list[str] = []
        for ws in wb.worksheets[:5]:
            for row in ws.iter_rows(max_row=200, values_only=True):
                values.extend(str(cell) for cell in row if cell is not None)
        return "\n".join(values)[:12000]
