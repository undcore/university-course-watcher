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
        if not self.token or not self.chat_id:
            LOGGER.info("Telegram settings missing; notification skipped.")
            return []
        sent: list[dict] = []
        for item in targets:
            try:
                self._send(self._message(item))
                sent.append(item)
            except Exception as exc:
                LOGGER.warning("Telegram send failed: %s", exc)
        return sent

    def _send(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        response = requests.post(url, json={"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True}, timeout=15)
        response.raise_for_status()

    def _message(self, item: dict) -> str:
        courses = ", ".join((item.get("possible_departments") or []) + (item.get("possible_computer_courses") or [])) or "확인 필요"
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
