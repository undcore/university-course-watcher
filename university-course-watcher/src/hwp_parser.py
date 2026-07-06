"""Native text extraction for HWP and HWPX attachments.

Korean university recruitment guidelines are frequently published only as HWP
(legacy binary) or HWPX (OWPML zip) files. Without extracting their text the
classifier only sees the surrounding board HTML, which lowers detection.

* HWPX is an OWPML package (a zip of XML) and is parsed with the standard
  library alone.
* HWP 5.x is an OLE compound file. The ``PrvText`` preview stream gives a
  reliable UTF-16 summary; the ``BodyText`` sections give the full content but
  are stored as (optionally deflate-compressed) record streams, so they are
  parsed on a best-effort basis.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
import zlib
from xml.etree import ElementTree

try:
    import olefile
except ImportError:  # pragma: no cover - optional dependency
    olefile = None

LOGGER = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 12000

# HWP5 paragraph-text control characters that occupy a single UTF-16 unit.
_CHAR_CONTROLS = {0, 10, 13, 24, 25, 26, 27, 28, 29, 30, 31}
# Inline/extended controls occupy 8 UTF-16 units (16 bytes) including the code.
_LONG_CONTROLS = {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23}

HWPTAG_PARA_TEXT = 0x43  # HWPTAG_BEGIN (0x10) + 51


def extract_hwpx_text(data: bytes) -> str:
    """Extract visible text from an HWPX (OWPML zip) document."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return ""

    with archive:
        section_names = sorted(
            name for name in archive.namelist()
            if name.startswith("Contents/section") and name.endswith(".xml")
        )
        lines: list[str] = []
        for name in section_names:
            try:
                xml_bytes = archive.read(name)
            except KeyError:  # pragma: no cover - defensive
                continue
            lines.extend(_hwpx_section_lines(xml_bytes))

    return "\n".join(line for line in lines if line)[:MAX_TEXT_LENGTH]


def _hwpx_section_lines(xml_bytes: bytes) -> list[str]:
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        return []

    lines: list[str] = []
    for element in root.iter():
        if _local_name(element.tag) != "p":
            continue
        runs = [
            node.text
            for node in element.iter()
            if _local_name(node.tag) == "t" and node.text
        ]
        if runs:
            lines.append(" ".join(run.strip() for run in runs).strip())
    return lines


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def extract_hwp_text(data: bytes) -> str:
    """Extract text from an HWP 5.x (OLE compound) document."""
    if olefile is None:
        return ""

    try:
        ole = olefile.OleFileIO(io.BytesIO(data))
    except Exception:
        return ""

    try:
        compressed = _hwp_is_compressed(ole)
        body_text = _hwp_body_text(ole, compressed)
        if body_text:
            return body_text[:MAX_TEXT_LENGTH]
        return _hwp_preview_text(ole)[:MAX_TEXT_LENGTH]
    finally:
        ole.close()


def _hwp_is_compressed(ole) -> bool:
    if not ole.exists("FileHeader"):
        return False
    header = ole.openstream("FileHeader").read()
    # Byte 36 holds document properties; bit 0 marks per-stream compression.
    return len(header) > 36 and bool(header[36] & 0x01)


def _hwp_preview_text(ole) -> str:
    if not ole.exists("PrvText"):
        return ""
    raw = ole.openstream("PrvText").read()
    return raw.decode("utf-16-le", errors="ignore").strip()


def _hwp_body_text(ole, compressed: bool) -> str:
    sections: list[tuple[int, list]] = []
    for entry in ole.listdir():
        if len(entry) == 2 and entry[0] == "BodyText" and entry[1].startswith("Section"):
            match = re.search(r"(\d+)", entry[1])
            sections.append((int(match.group(1)) if match else 0, entry))

    lines: list[str] = []
    for _, entry in sorted(sections, key=lambda item: item[0]):
        try:
            raw = ole.openstream(entry).read()
            if compressed:
                raw = zlib.decompress(raw, -15)
            lines.extend(_hwp_section_paragraphs(raw))
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.debug("HWP section parse skipped: %s", exc)
    return "\n".join(line for line in lines if line)


def _hwp_section_paragraphs(data: bytes) -> list[str]:
    lines: list[str] = []
    offset = 0
    length = len(data)
    while offset + 4 <= length:
        header = int.from_bytes(data[offset:offset + 4], "little")
        tag_id = header & 0x3FF
        size = (header >> 20) & 0xFFF
        offset += 4
        if size == 0xFFF:
            if offset + 4 > length:
                break
            size = int.from_bytes(data[offset:offset + 4], "little")
            offset += 4
        record = data[offset:offset + size]
        offset += size
        if tag_id == HWPTAG_PARA_TEXT:
            text = _decode_para_text(record)
            if text:
                lines.append(text)
    return lines


def _decode_para_text(record: bytes) -> str:
    chars: list[str] = []
    i = 0
    length = len(record)
    while i + 2 <= length:
        code = record[i] | (record[i + 1] << 8)
        if code in _LONG_CONTROLS:
            i += 16
            continue
        if code in _CHAR_CONTROLS:
            if code in (10, 13):
                chars.append("\n")
            i += 2
            continue
        chars.append(chr(code))
        i += 2
    return "".join(chars).strip()
