from __future__ import annotations

import logging
import os

import requests

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv() -> None:
        return None

LOGGER = logging.getLogger(__name__)
DISCLAIMER = "※ 결과는 자동 검색 후보이며, 최종 지원 가능 여부는 대학 공식 모집요강 원문과 입학처 문의로 확인해야 합니다."


class TelegramNotifier:
    def __init__(self):
        load_dotenv()
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    def send_candidates(self, items: list[dict], dry_run: bool = False) -> list[dict]:
        targets = [
            item for item in items
            if item.get("is_new") and item.get("grade") in {"A", "B"} and item.get("deadline_status") != "마감됨"
        ]

        if dry_run:
            return targets

        if not self._is_configured():
            LOGGER.info("Telegram settings missing; candidate notification skipped.")
            return []

        sent: list[dict] = []
        for item in targets:
            try:
                self._send(self._candidate_message(item))
                sent.append(item)
            except Exception as exc:
                LOGGER.warning("Telegram candidate send failed: %s", exc)

        return sent

    def send_daily_report(self, summary: dict, dry_run: bool = False) -> bool:
        if dry_run:
            return True

        if not self._is_configured():
            LOGGER.info("Telegram settings missing; daily report skipped.")
            return False

        try:
            self._send(self._daily_report_message(summary))
            return True
        except Exception as exc:
            LOGGER.warning("Telegram daily report send failed: %s", exc)
            return False

    def _is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def _send(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True}
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()

    def _candidate_message(self, item: dict) -> str:
        courses = ", ".join((item.get("possible_departments") or []) + (item.get("possible_computer_courses") or []))
        courses = courses or "확인 필요"
        period = f"{item.get('application_start_date') or '?'} ~ {item.get('application_end_date') or '?'}"

        return (
            "[시간제등록/외부 수강 공고 후보 발견]\n\n"
            f"등급: {item.get('grade')}\n"
            f"상태: {item.get('deadline_status')}\n"
            f"대학: {item.get('university_name')}\n"
            f"지역: {item.get('region')} {item.get('city')}\n"
            f"제목: {item.get('title')}\n"
            f"모집기간: {period}\n"
            f"외부 신청 가능성: {item.get('external_applicant_status')}\n"
            f"컴퓨터 관련 과목: {item.get('computer_course_status')}\n"
            f"가능 학과/과목 후보: {courses}\n"
            f"링크: {item.get('url')}\n"
            f"판정 이유: {item.get('reason')}\n\n"
            f"{DISCLAIMER}"
        )

    def _daily_report_message(self, summary: dict) -> str:
        grade_counts = summary.get("grade_counts", {})
        status_counts = summary.get("status_counts", {})
        sent_count = summary.get("sent_count", 0)

        grade_line = ", ".join(f"{grade}:{grade_counts.get(grade, 0)}" for grade in ["A", "B", "C", "D"])
        status_line = self._format_counts(status_counts) or "없음"

        if summary.get("candidate_count", 0):
            result_line = f"알림 후보 {summary.get('candidate_count')}건 중 {sent_count}건을 텔레그램으로 발송했습니다."
        else:
            result_line = "신규 알림 후보는 발견되지 않았습니다."

        return (
            "[시간제등록/외부 수강 공고 일일 점검 보고]\n\n"
            f"점검 시각: {summary.get('checked_at')}\n"
            f"점검 대학: {summary.get('university_count')}개\n"
            f"점검 게시판: {summary.get('board_count')}개\n"
            f"게시판 처리: 성공 {summary.get('board_success_count')}개, 실패 {summary.get('board_failure_count')}개, 스킵 {summary.get('board_skip_count')}개\n"
            f"수집 공지: {summary.get('crawled_count')}건\n"
            f"중복 제거 후: {summary.get('deduped_count')}건\n"
            f"공개 보고 대상(A~C): {summary.get('public_count')}건\n"
            f"신규 A/B 후보: {summary.get('candidate_count')}건\n"
            f"등급 분포: {grade_line}\n"
            f"마감 상태 분포: {status_line}\n\n"
            f"처리 결과: {result_line}\n\n"
            f"보고서 파일: GitHub Actions artifact의 report.html을 확인하세요.\n"
            f"{DISCLAIMER}"
        )

    def _format_counts(self, counts: dict) -> str:
        parts: list[str] = []

        for key in sorted(counts):
            parts.append(f"{key}:{counts[key]}")

        return ", ".join(parts)
