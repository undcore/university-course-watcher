from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"


class DurableStateError(RuntimeError):
    """Raised when persisted notification state cannot be trusted."""


def setup_logging(debug: bool = False) -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logging.getLogger(__name__).warning("Invalid JSON file ignored: %s", path)
        return default


def load_durable_json(path: Path, default: Any, expected_type: type | tuple[type, ...]) -> Any:
    """Load notification state without treating corruption as empty state."""
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise DurableStateError(f"Durable state is unreadable: {path}") from exc

    if not isinstance(data, expected_type):
        raise DurableStateError(f"Durable state has an invalid structure: {path}")

    return data


def save_json(path: Path, data: Any, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")

    with temporary_path.open("w", encoding="utf-8", errors="replace") as file:
        if compact:
            json.dump(data, file, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(data, file, ensure_ascii=False, indent=2)

    temporary_path.replace(path)


def now_kst() -> datetime:
    timezone = ZoneInfo(os.getenv("TIMEZONE", "Asia/Seoul"))
    return datetime.now(timezone)


def normalize_space(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.replace("\xa0", " ").split())


def truncate(text: str, limit: int = 500) -> str:
    normalized_text = normalize_space(text)
    if len(normalized_text) <= limit:
        return normalized_text
    return normalized_text[: limit - 1] + "…"


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)

    return result
