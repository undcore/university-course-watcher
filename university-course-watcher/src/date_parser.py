from __future__ import annotations

import re
from datetime import date
from typing import Optional

from dateutil.parser import parse


DATE_RE = re.compile(r"(20\d{2})\D{0,5}(\d{1,2})\D{0,5}(\d{1,2})")
RANGE_RE = re.compile(
    r"(20\d{2})\D{0,5}(\d{1,2})\D{0,5}(\d{1,2})"
    r"\D{0,30}(?:~|부터|까지|-|to|until)\D{0,30}"
    r"(20\d{2})?\D{0,5}(\d{1,2})\D{0,5}(\d{1,2})",
    re.IGNORECASE,
)


def parse_notice_dates(title: str, body: str, notice_date: str, today: date) -> dict[str, str]:
    text = f"{title}\n{body}"
    start, end = _find_range(text)
    notice = _normalize_date(notice_date)

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
        days_left = (end - today).days

        if days_left <= 3:
            return "긴급"

        if days_left <= 7:
            return "마감임박"

    return "모집중"


def _find_range(text: str) -> tuple[Optional[date], Optional[date]]:
    dates: list[date] = []

    for match in RANGE_RE.finditer(text):
        start_year, start_month, start_day, end_year, end_month, end_day = match.groups()
        start_date = _to_date((start_year, start_month, start_day))
        end_date = _to_date((end_year or start_year, end_month, end_day))

        if start_date and end_date:
            return start_date, end_date

    for match in DATE_RE.finditer(text):
        found_date = _to_date(match.groups())

        if not found_date:
            continue

        dates.append(found_date)

        if len(dates) >= 2:
            break

    if len(dates) >= 2:
        return dates[0], dates[1]

    if len(dates) == 1:
        return None, dates[0]

    return None, None


def _find_first_date(text: str) -> str:
    match = DATE_RE.search(text)

    if not match:
        return ""

    found_date = _to_date(match.groups())

    if not found_date:
        return ""

    return found_date.isoformat()


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
