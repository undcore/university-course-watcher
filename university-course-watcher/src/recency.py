from __future__ import annotations

import os
from datetime import date

from .utils import now_kst


DEFAULT_MAX_AGE_DAYS = 7


def notice_max_age_days() -> int:
    sConfiguredDays = os.getenv("NOTICE_MAX_AGE_DAYS", str(DEFAULT_MAX_AGE_DAYS))

    try:
        iConfiguredDays = int(sConfiguredDays)
    except ValueError:
        return DEFAULT_MAX_AGE_DAYS

    return max(0, iConfiguredDays)


def notice_age_days(item: dict, dateToday: date | None = None) -> int | None:
    sNoticeDate = str(item.get("notice_date", ""))

    if not sNoticeDate:
        return None

    try:
        dateNotice = date.fromisoformat(sNoticeDate)
    except ValueError:
        return None

    if dateToday is None:
        dateToday = now_kst().date()

    return (dateToday - dateNotice).days


def is_recent_notice(item: dict, dateToday: date | None = None) -> bool:
    iAgeDays = notice_age_days(item, dateToday)

    if iAgeDays is None:
        return False

    return 0 <= iAgeDays <= notice_max_age_days()


def is_stale_notice(item: dict, dateToday: date | None = None) -> bool:
    iAgeDays = notice_age_days(item, dateToday)

    if iAgeDays is None:
        return False

    return iAgeDays > notice_max_age_days()
