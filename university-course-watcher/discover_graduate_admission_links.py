from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from urllib3.exceptions import InsecureRequestWarning


CONFIG_PATH = Path("config") / "graduate_admission_boards.json"
MATCH_WORDS = ["입학", "모집", "전형", "공지", "notice", "admission", "board"]

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)


def main() -> int:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 university-course-watcher/1.0"})

    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        boards = json.load(file)

    for board in boards:
        sUniversityName = board.get("university_name", "")
        sUrl = board.get("url", "")
        print(f"\n[{sUniversityName}] {sUrl}")

        response = _fetch(session, sUrl)
        if response is None or response.status_code >= 400:
            parsed = urlparse(sUrl)
            sRootUrl = f"{parsed.scheme}://{parsed.netloc}/"
            print(f"  primary failed; trying root {sRootUrl}")
            response = _fetch(session, sRootUrl)

        if response is None:
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        lstLinks = []

        for tag in soup.find_all("a", href=True):
            sText = " ".join(tag.get_text(" ").split())
            sHref = tag.get("href", "")
            sFullUrl = urljoin(response.url, sHref)
            sHaystack = f"{sText} {sFullUrl}".lower()

            if not any(sWord.lower() in sHaystack for sWord in MATCH_WORDS):
                continue

            lstLinks.append((sText[:80], sFullUrl))

        for sText, sFullUrl in lstLinks[:20]:
            print(_safe_text(f"  - {sText}\t{sFullUrl}"))

    return 0


def _fetch(session: requests.Session, sUrl: str):
    try:
        return session.get(sUrl, timeout=10, allow_redirects=True, verify=False)
    except Exception as exc:
        print(f"  fetch failed: {type(exc).__name__}: {exc}")
        return None


def _safe_text(sText: str) -> str:
    return sText.encode("cp949", errors="replace").decode("cp949")


if __name__ == "__main__":
    raise SystemExit(main())
