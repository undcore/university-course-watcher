from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import requests
from urllib3.exceptions import InsecureRequestWarning


CONFIG_PATH = Path("config") / "graduate_admission_boards.json"
DEFAULT_REPORT_PATH = Path("data") / "board_validation.json"
KEYWORDS = ["대학원", "입학", "모집", "전형", "공지"]
SUSPICIOUS_FINAL_URL_MARKERS = ["error", "login", "signin", "sso", "auth"]

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)


def evaluate_result(status: str, keyword_hits: int, final_url: str) -> tuple[bool, str]:
    """Classify a fetched board into (ok, reason) without any network access."""
    if status == "SKIP":
        return True, "비활성화된 게시판(검증 제외)"
    if status == "ERR":
        return False, "요청 실패"
    if status != "200":
        return False, f"HTTP 상태 {status}"

    lowered_final = final_url.lower()
    if any(marker in lowered_final for marker in SUSPICIOUS_FINAL_URL_MARKERS):
        return False, "error/login/SSO 페이지로 리다이렉트 의심"
    if keyword_hits == 0:
        return False, "대학원 관련 키워드 미검출"

    return True, "정상"


def _fetch(session: requests.Session, url: str) -> tuple[str, int, str]:
    response = session.get(url, timeout=10, allow_redirects=True, verify=False)
    text = response.text[:20000]
    keyword_hits = sum(1 for keyword in KEYWORDS if keyword in text)
    return str(response.status_code), keyword_hits, response.url


def validate_boards(boards: list[dict]) -> list[dict]:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 university-course-watcher/1.0"})

    results: list[dict] = []
    for board in boards:
        university_name = board.get("university_name", "")
        board_type = board.get("board_type", "")
        url = board.get("url", "")

        if not board.get("enabled", True):
            status, keyword_hits, final_url = "SKIP", 0, url
        else:
            try:
                status, keyword_hits, final_url = _fetch(session, url)
            except Exception as exc:
                status, keyword_hits, final_url = "ERR", 0, f"{type(exc).__name__}: {exc}"

        ok, reason = evaluate_result(status, keyword_hits, final_url)
        results.append({
            "university_name": university_name,
            "board_type": board_type,
            "url": url,
            "enabled": board.get("enabled", True),
            "status": status,
            "keyword_hits": keyword_hits,
            "final_url": final_url,
            "ok": ok,
            "reason": reason,
        })

    return results


def _print_tsv(results: list[dict]) -> None:
    print("university_name\tstatus\tkeyword_hits\tfinal_url")
    for result in results:
        print(f"{result['university_name']}\t{result['status']}\t{result['keyword_hits']}\t{result['final_url']}")


def _markdown_summary(results: list[dict]) -> str:
    checked = [r for r in results if r["enabled"]]
    failures = [r for r in checked if not r["ok"]]
    lines = [
        "## 대학원 입학 게시판 URL 검증",
        "",
        f"- 검증 대상: {len(checked)}개 (비활성 {len(results) - len(checked)}개 제외)",
        f"- 정상: {len(checked) - len(failures)}개 / 문제: {len(failures)}개",
        "",
        "| 대학 | 상태 | 키워드 | 판정 | 사유 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in results:
        mark = "✅" if result["ok"] else "⚠️"
        lines.append(
            f"| {result['university_name']} | {result['status']} | {result['keyword_hits']} "
            f"| {mark} | {result['reason']} |"
        )
    return "\n".join(lines) + "\n"


def _write_step_summary(markdown: str) -> None:
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(markdown)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="대학원 입학 게시판 URL 상태를 검증합니다.")
    parser.add_argument("--json", action="store_true", help="결과를 JSON으로 출력합니다.")
    parser.add_argument("--report", nargs="?", const=str(DEFAULT_REPORT_PATH),
                        help="JSON 검증 리포트를 파일로 저장합니다.")
    parser.add_argument("--summary", action="store_true",
                        help="마크다운 요약을 출력하고 GITHUB_STEP_SUMMARY에도 기록합니다.")
    parser.add_argument("--fail-on-error", action="store_true",
                        help="검증에 실패한 게시판이 있으면 종료 코드 1을 반환합니다.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        boards = json.load(file)

    results = validate_boards(boards)

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    elif args.summary:
        markdown = _markdown_summary(results)
        print(markdown)
        _write_step_summary(markdown)
    else:
        _print_tsv(results)

    failures = [r for r in results if r["enabled"] and not r["ok"]]
    if failures and args.fail_on_error:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
