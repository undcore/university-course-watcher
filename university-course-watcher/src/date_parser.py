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
RANGE_CONTEXT_WORDS = ["접수", "신청", "등록", "원서", "모집기간", "수강"]


def parse_notice_dates(title: str, body: str, notice_date: str, today: date) -> dict[str, str | bool]:
    return parse_notice_dates_from_sources(
        title,
        [("본문", body)],
        notice_date,
        today,
    )


def parse_notice_dates_from_sources(
    title: str,
    sources: list[tuple[str, str]],
    notice_date: str,
    today: date,
) -> dict[str, str | bool]:
    source_results: list[tuple[str, Optional[date], Optional[date]]] = []

    for source_name, source_text in sources:
        start, end = _find_range(f"{title}\n{source_text}")

        if start or end:
            source_results.append((source_name, start, end))

    notice = _normalize_date(notice_date)

    if not source_results:
        return {
            "notice_date": notice or "",
            "application_start_date": "",
            "application_end_date": "",
            "deadline_status": deadline_status(None, None, today),
            "date_source": "",
            "date_conflict": False,
        }

    selected_source, selected_start, selected_end = source_results[0]
    selected_period = (selected_start, selected_end)
    date_conflict = any(
        (start, end) != selected_period
        for _, start, end in source_results[1:]
    )
    matching_sources = [
        source_name
        for source_name, start, end in source_results
        if (start, end) == selected_period
    ]

    return {
        "notice_date": notice or "",
        "application_start_date": selected_start.isoformat() if selected_start else "",
        "application_end_date": selected_end.isoformat() if selected_end else "",
        "deadline_status": deadline_status(selected_start, selected_end, today),
        "date_source": ", ".join(matching_sources) or selected_source,
        "date_conflict": date_conflict,
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
    lstSegments = re.split(r"[\n\r]|(?<=[.!?])\s+", text)

    for sSegment in lstSegments:
        sNormalizedSegment = " ".join(sSegment.split())

        if not any(sWord in sNormalizedSegment for sWord in RANGE_CONTEXT_WORDS):
            continue

        for match in RANGE_RE.finditer(sNormalizedSegment):
            sStartYear, sStartMonth, sStartDay, sEndYear, sEndMonth, sEndDay = match.groups()
            dateStart = _to_date((sStartYear, sStartMonth, sStartDay))
            dateEnd = _to_date((sEndYear or sStartYear, sEndMonth, sEndDay))

            if dateStart is None or dateEnd is None:
                continue
            if dateEnd < dateStart:
                continue

            return dateStart, dateEnd

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
