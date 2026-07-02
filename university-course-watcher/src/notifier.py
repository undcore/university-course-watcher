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


class GraduateAdmissionNotifier:
    def __init__(self):
        load_dotenv()
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.summary_sent = False

    def send_candidates(self, items: list[dict], dry_run: bool = False, send_empty_summary: bool = True) -> list[dict]:
        targets = [
            item for item in items
            if item.get("is_new") and item.get("grade") in {"A", "B"}
        ]

        if dry_run:
            return targets
        if not self.token or not self.chat_id:
            LOGGER.info("Telegram settings missing; graduate admission notification skipped.")
            return []

        sent: list[dict] = []
        if not targets:
            if not send_empty_summary:
                LOGGER.info("Graduate admission empty summary unchanged; notification skipped.")
                return sent
            try:
                self._send(self._summary_message(items))
                self.summary_sent = True
            except Exception as exc:
                LOGGER.warning("Telegram summary send failed: %s", exc)
            return sent

        for item in targets:
            try:
                self._send(self._message(item))
                sent.append(item)
            except Exception as exc:
                LOGGER.warning("Telegram send failed: %s", exc)

        return sent

    def _send(self, text: str) -> None:
        if not self.token or not self.chat_id:
            raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required.")

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        response = requests.post(url, json={"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True}, timeout=15)
        response.raise_for_status()

    def _message(self, item: dict) -> str:
        matched = ", ".join(item.get("matched_keywords") or []) or "확인 필요"

        return (
            "[2026 후기 일반대학원 모집요강 알림]\n\n"
            f"등급: {item.get('grade')}\n"
            f"대학: {item.get('university_name')}\n"
            f"지역: {item.get('region')} {item.get('city')}\n"
            f"게시판: {item.get('board_type')}\n"
            f"제목: {item.get('title')}\n"
            f"게시일: {item.get('notice_date') or '확인 필요'}\n"
            f"확인 키워드: {matched}\n"
            f"판단 근거: {item.get('reason')}\n"
            f"링크: {item.get('url')}\n\n"
            "자동 확인 결과입니다. 최종 지원 가능 여부와 전형 세부사항은 해당 대학원 공식 모집요강에서 다시 확인해야 합니다."
        )

    def _summary_message(self, items: list[dict]) -> str:
        active_count = int(os.getenv("GRADUATE_ADMISSION_ACTIVE_BOARD_COUNT", "0") or "0")
        disabled_count = int(os.getenv("GRADUATE_ADMISSION_DISABLED_BOARD_COUNT", "0") or "0")
        checked_at = items[0].get("checked_at") if items else ""

        return (
            "[2026 후기 일반대학원 모집요강 확인 완료]\n\n"
            "신규 알림 대상: 없음\n"
            f"확인 시각: {checked_at or '확인 필요'}\n"
            f"활성 감시 대상: {active_count}개\n"
            f"보류/비활성 대상: {disabled_count}개\n"
            f"기존/참고 후보 감지: {len(items)}건\n\n"
            "새로 알릴 2026학년도 후기 일반대학원 모집요강 공고는 발견되지 않았습니다. "
            "보류/비활성 대상은 공식 URL 확인 또는 접근 방식 보정 후 재활성화가 필요합니다."
        )

    def send_test_success(self) -> None:
        item = {
            "grade": "A",
            "university_name": "테스트대학교",
            "region": "서울",
            "city": "서울",
            "board_type": "후기 일반전형 모집요강",
            "title": "[테스트] 2026학년도 후기 일반대학원 신입생 모집요강 공지",
            "notice_date": "2026-06-11",
            "matched_keywords": ["2026", "후기", "일반대학원", "모집요강", "입학전형"],
            "reason": "텔레그램 수신 형식 확인을 위한 테스트 메시지입니다. 실제 공고 알림은 이 형식으로 전송됩니다.",
            "url": "https://example.com/test-graduate-admission",
        }
        self._send(self._message(item))

    def send_test_empty(self) -> None:
        os.environ.setdefault("GRADUATE_ADMISSION_ACTIVE_BOARD_COUNT", "20")
        os.environ.setdefault("GRADUATE_ADMISSION_DISABLED_BOARD_COUNT", "4")
        self._send(self._summary_message([]))
