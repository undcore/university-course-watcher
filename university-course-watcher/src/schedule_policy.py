from __future__ import annotations

import argparse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")


def should_run(event_name: str, now_utc: datetime | None = None) -> bool:
    if event_name == "workflow_dispatch":
        return True

    if event_name != "schedule":
        return False

    current_utc = now_utc or datetime.now(timezone.utc)
    if current_utc.tzinfo is None or current_utc.utcoffset() is None:
        raise ValueError("now_utc must be timezone-aware")

    current_kst = current_utc.astimezone(KST)
    return current_kst.weekday() < 5


def main() -> None:
    parser = argparse.ArgumentParser(description="Check whether the watcher may run now.")
    parser.add_argument("--event", required=True, help="GitHub Actions event name")
    args = parser.parse_args()

    print("true" if should_run(args.event) else "false")


if __name__ == "__main__":
    main()
