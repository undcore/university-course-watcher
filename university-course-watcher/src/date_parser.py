from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from dateutil.parser import parse


DATE_RE = re.compile(r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})")
RANGE_RE = re.compile(
    r"(20\d{2})?\s*[.\-/년]?\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})"
    r"(?:\D{0,20}(?:~|부터|까지|-)\D{0,20})"
    r"(20\d{2})?\s*[.\-/년]?\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})"
)


def parse_notice_dates(title: str, body: str, notice_date: str, today: date) -> dict[str, str]:
    text = f"{title}\n{body}"
    start, end = _find_range(text, today.year)
    notice = _normalize_date(notice_date) or _find_first_date(text)
    return {
        "notice_date": notice or "",
        "application_start_date": start.isoformat() if start else "",
        "application_end_date": end.isoformat() if end else "",
        "deadline_status": deadline_status(start, end, today),
    }


def deadline_status(start: Optional[date], end: Optional[date], today: date) -> str:
    if not start and not end:
        return "날짜확인필요"
    if start and today < start:
        return "접수예정"
    if end and today > end:
        return "마감됨"
    if end:
        days = (end - today).days
        if days <= 3:
            return "긴급"
        if days <= 7:
            return "마감임박"
    return "모집중"


def _find_range(text: str, default_year: int) -> tuple[Optional[date], Optional[date]]:
    for match in RANGE_RE.finditer(text):
        y1, m1, d1, y2, m2, d2 = match.groups()
        year1 = int(y1 or default_year)
        year2 = int(y2 or y1 or default_year)
        try:
            return date(year1, int(m1), int(d1)), date(year2, int(m2), int(d2))
        except ValueError:
            continue
    dates = [_to_date(m.groups()) for m in DATE_RE.finditer(text)]
    dates = [d for d in dates if d]
    if len(dates) >= 2:
        return dates[0], dates[1]
    if len(dates) == 1:
        return None, dates[0]
    return None, None


def _find_first_date(text: str) -> str:
    match = DATE_RE.search(text)
    if not match:
        return ""
    d = _to_date(match.groups())
    return d.isoformat() if d else ""


def _normalize_date(value: str) -> str:
    if not value:
        return ""
    try:
        return parse(value).date().isoformat()
    except Exception:
        return ""


def _to_date(parts: tuple[str, str, str]) -> Optional[date]:
    try:
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None
