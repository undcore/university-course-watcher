from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"


def setup_logging(debug: bool = False) -> None:
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
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logging.getLogger(__name__).warning("손상된 JSON 파일 무시: %s", path)
        return default


def save_json(path: Path, data: Any, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    # ponytail: 잘못 디코딩된 첨부파일 텍스트의 서로게이트 문자가 UTF-8 인코딩을 깨뜨림
    with tmp.open("w", encoding="utf-8", errors="replace") as f:
        if compact:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def now_kst() -> datetime:
    tz = ZoneInfo(os.getenv("TIMEZONE", "Asia/Seoul"))
    return datetime.now(tz)


def normalize_space(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.replace("\xa0", " ").split())


def truncate(text: str, limit: int = 500) -> str:
    text = normalize_space(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out
