from __future__ import annotations

import json
from pathlib import Path

import requests


CONFIG_PATH = Path("config") / "graduate_admission_boards.json"
KEYWORDS = ["대학원", "입학", "모집", "전형", "공지"]

def main() -> int:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 university-course-watcher/1.0"})

    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        boards = json.load(file)

    print("university_name\tstatus\tkeyword_hits\tfinal_url")

    for board in boards:
        sUniversityName = board.get("university_name", "")
        sUrl = board.get("url", "")

        if not board.get("enabled", True):
            print(f"{sUniversityName}\tSKIP\t0\t{sUrl}")
            continue

        try:
            response = session.get(sUrl, timeout=10, allow_redirects=True)
            sText = response.text[:20000]
            intKeywordHits = 0

            for sKeyword in KEYWORDS:
                if sKeyword in sText:
                    intKeywordHits += 1

            print(f"{sUniversityName}\t{response.status_code}\t{intKeywordHits}\t{response.url}")
        except Exception as exc:
            print(f"{sUniversityName}\tERR\t0\t{type(exc).__name__}: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
