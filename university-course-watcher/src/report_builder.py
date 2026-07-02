from __future__ import annotations

import html
from pathlib import Path

from .notifier import DISCLAIMER
from .utils import DATA_DIR, now_kst


STATUS_ORDER = {"모집중": 0, "접수예정": 1, "마감임박": 2, "긴급": 3, "날짜확인필요": 4, "마감됨": 5}
GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}


def build_report(items: list[dict], path: Path = DATA_DIR / "report.html") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    visible = sorted(
        [i for i in items if i.get("grade") != "D"],
        key=lambda i: (GRADE_ORDER.get(i.get("grade"), 9), STATUS_ORDER.get(i.get("deadline_status"), 9), i.get("university_name", "")),
    )
    rows = "\n".join(_row(item) for item in visible) or "<tr><td colspan='16'>검색 결과가 없습니다.</td></tr>"
    content = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>대학 시간제등록/외부 수강 후보 리포트</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #1f2937; }}
    h1 {{ font-size: 24px; margin-bottom: 6px; }}
    .meta {{ color: #6b7280; margin-bottom: 18px; }}
    .notice {{ padding: 12px; background: #fff7ed; border: 1px solid #fed7aa; border-radius: 6px; margin-bottom: 18px; }}
    .summary {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 18px; }}
    .summary span {{ padding: 6px 10px; background: #f3f4f6; border-radius: 6px; font-size: 13px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px; vertical-align: top; }}
    th {{ background: #f3f4f6; position: sticky; top: 0; }}
    .grade-A {{ background: #ecfdf5; }}
    .grade-B {{ background: #eff6ff; }}
    .grade-C {{ background: #f9fafb; }}
    a {{ color: #1d4ed8; }}
  </style>
</head>
<body>
  <h1>대학 시간제등록/외부 수강 후보 리포트</h1>
  <div class="meta">확인 일시: {html.escape(now_kst().isoformat(timespec="seconds"))}</div>
  <div class="notice">{html.escape(DISCLAIMER)}</div>
  <div class="summary">
    <span>전체 후보 {len(visible)}건</span>
    <span>A등급 {sum(1 for item in visible if item.get("grade") == "A")}건</span>
    <span>B등급 {sum(1 for item in visible if item.get("grade") == "B")}건</span>
    <span>신규 {sum(1 for item in visible if item.get("is_new"))}건</span>
  </div>
  <table>
    <thead>
      <tr>
        <th>신규</th><th>등급</th><th>마감상태</th><th>대학명</th><th>지역</th><th>제목</th><th>모집기간</th>
        <th>외부 신청</th><th>컴퓨터 과목</th><th>점수</th><th>검증 근거</th><th>학과/과목 후보</th><th>판정 이유</th><th>링크</th><th>첨부</th><th>확인일시</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
"""
    path.write_text(content, encoding="utf-8")


def _row(item: dict) -> str:
    period = f"{item.get('application_start_date') or '?'} ~ {item.get('application_end_date') or '?'}"
    courses = "; ".join((item.get("possible_departments") or []) + (item.get("possible_computer_courses") or []))
    attachments = "<br>".join(f"<a href='{html.escape(u)}'>첨부</a>" for u in item.get("attachment_urls", []))
    score = (
        f"등록 {item.get('registration_score', 0)} / "
        f"외부 {item.get('external_score', 0)} / "
        f"컴퓨터 {item.get('computer_score', 0)} / "
        f"신선도 {item.get('freshness_score', 0)}"
    )
    evidence = item.get("course_evidence_text") or "본문/첨부 키워드 기준"
    if item.get("course_evidence_url"):
        evidence = f"<a href='{html.escape(item.get('course_evidence_url', ''))}'>교과 근거</a><br>{html.escape(evidence)}"
    else:
        evidence = html.escape(evidence)
    return (
        f"<tr class='grade-{html.escape(item.get('grade', ''))}'>"
        f"<td>{'신규' if item.get('is_new') else '기존'}</td>"
        f"<td>{html.escape(item.get('grade', ''))}</td>"
        f"<td>{html.escape(item.get('deadline_status', ''))}</td>"
        f"<td>{html.escape(item.get('university_name', ''))}</td>"
        f"<td>{html.escape(item.get('region', ''))} {html.escape(item.get('city', ''))}</td>"
        f"<td>{html.escape(item.get('title', ''))}</td>"
        f"<td>{html.escape(period)}</td>"
        f"<td>{html.escape(item.get('external_applicant_status', ''))}</td>"
        f"<td>{html.escape(item.get('computer_course_status', ''))}</td>"
        f"<td>{html.escape(score)}</td>"
        f"<td>{evidence}</td>"
        f"<td>{html.escape(courses)}</td>"
        f"<td>{html.escape(item.get('reason', ''))}</td>"
        f"<td><a href='{html.escape(item.get('url', ''))}'>원문</a></td>"
        f"<td>{attachments}</td>"
        f"<td>{html.escape(item.get('checked_at', ''))}</td>"
        "</tr>"
    )
