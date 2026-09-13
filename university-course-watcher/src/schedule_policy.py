from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")


def scheduled_slot_utc(schedule: str, now_utc: datetime) -> datetime:
    """GitHub 예약 실행은 몇 시간 늦게 시작되므로 cron이 가리킨 원래 실행 시각을 복원한다."""
    minute_text, hour_text = schedule.split()[:2]
    slot = now_utc.replace(hour=int(hour_text), minute=int(minute_text), second=0, microsecond=0)
    if slot > now_utc:
        slot -= timedelta(days=1)
    return slot


def should_run(event_name: str, now_utc: datetime | None = None, schedule: str = "") -> bool:
    if event_name == "workflow_dispatch":
        return True

    if event_name != "schedule":
        return False

    current_utc = now_utc or datetime.now(timezone.utc)
    if current_utc.tzinfo is None or current_utc.utcoffset() is None:
        raise ValueError("now_utc must be timezone-aware")

    reference_utc = current_utc
    if schedule:
        try:
            reference_utc = scheduled_slot_utc(schedule, current_utc)
        except ValueError:
            reference_utc = current_utc

    # 금요일 19:00 KST 예약이 토요일 새벽에 시작돼도 금요일 실행으로 판단한다.
    return reference_utc.astimezone(KST).weekday() < 5


def main() -> None:
    parser = argparse.ArgumentParser(description="Check whether the watcher may run now.")
    parser.add_argument("--event", required=True, help="GitHub Actions event name")
    parser.add_argument("--schedule", default="", help="Cron expression that triggered the run")
    args = parser.parse_args()

    print("true" if should_run(args.event, schedule=args.schedule) else "false")


if __name__ == "__main__":
    main()
