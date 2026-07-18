from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.delivery_outbox import DeliveryOutbox


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect or resolve ambiguous Telegram deliveries.")
    parser.add_argument("--watch", choices=["course", "graduate"], required=True)
    parser.add_argument("--delivery-id")
    parser.add_argument("--outcome", choices=["delivered", "retry"])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outbox_path = PROJECT_ROOT / "data" / f"{args.watch}_delivery_outbox.json"
    outbox = DeliveryOutbox(outbox_path)

    if bool(args.delivery_id) != bool(args.outcome):
        raise SystemExit("--delivery-id and --outcome must be provided together.")
    if args.delivery_id:
        outbox.resolve(args.delivery_id, args.outcome)

    print(json.dumps(outbox.unresolved(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
