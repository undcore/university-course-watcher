from __future__ import annotations

import sys

import requests
from urllib3.exceptions import InsecureRequestWarning


requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)


def main() -> int:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 university-course-watcher/1.0"})

    for sUrl in sys.argv[1:]:
        try:
            response = session.get(sUrl, timeout=10, allow_redirects=True, verify=False)
            sText = response.text[:20000]
            intHits = 0

            for sKeyword in ["대학원", "입학", "모집", "전형", "공지", "2026"]:
                if sKeyword in sText:
                    intHits += 1

            print(f"{response.status_code}\t{intHits}\t{response.url}")
        except Exception as exc:
            print(f"ERR\t0\t{sUrl}\t{type(exc).__name__}: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
