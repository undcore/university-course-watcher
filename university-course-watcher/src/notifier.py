from __future__ import annotations

import logging
import os

import requests

from .recency import is_recent_notice

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
        self.delivery_failures: list[str] = []

    def send_candidates(self, items: list[dict], dry_run: bool = False) -> list[dict]:
        targets = [
            item for item in items
            if self._is_notifiable_change(item)
            and item.get("grade") in {"A", "B"}
            and item.get("deadline_status") != "마감됨"
            and is_recent_notice(item)
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
                self.delivery_failures.append(str(exc))

        return sent

    def _is_notifiable_change(self, item: dict) -> bool:
        change_type = item.get("change_type", "")
        if change_type:
            return change_type in {"new", "content_changed", "grade_changed", "deadline_changed"}
        return bool(item.get("is_new"))

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
            self.delivery_failures.append(str(exc))
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
            f"변경 유형: {item.get('change_type') or ('new' if item.get('is_new') else 'unchanged')}\n"
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
        # 신규 후보가 없는 날은 같은 목록을 반복하지 않고 짧은 확인 메시지만 보낸다
        if not summary.get("candidate_count", 0) and not summary.get("preview_items"):
            return self._no_news_message(summary)

        grade_counts = summary.get("grade_counts", {})
        status_counts = summary.get("status_counts", {})
        sent_count = summary.get("sent_count", 0)
        preview_items = summary.get("preview_items", [])
        failed_boards = summary.get("failed_boards", [])
        failed_details = summary.get("failed_details", [])
        actions_run_url = summary.get("actions_run_url", "")
        artifact_name = summary.get("artifact_name", "university-course-watcher-results")
        report_html_url = summary.get("report_html_url", "")

        grade_line = ", ".join(f"{grade}:{grade_counts.get(grade, 0)}" for grade in ["A", "B", "C", "D"])
        status_line = self._format_counts(status_counts) or "없음"
        preview_line = self._format_preview_items(preview_items)
        failure_line = self._format_failed_boards(failed_boards + failed_details)
        report_line = self._format_report_location(actions_run_url, artifact_name, report_html_url)

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
            f"상세 글 처리: 전체 {summary.get('detail_count')}개, 실패 {summary.get('detail_failure_count')}개\n"
            f"수집 공지: {summary.get('crawled_count')}건\n"
            f"중복 제거 후: {summary.get('deduped_count')}건\n"
            f"공개 보고 대상(A~C): {summary.get('public_count')}건\n"
            f"신규 A/B 후보: {summary.get('candidate_count')}건\n"
            f"등급 분포: {grade_line}\n"
            f"마감 상태 분포: {status_line}\n\n"
            f"상위 확인 후보:\n{preview_line}\n\n"
            f"실패/점검 필요 게시판:\n{failure_line}\n\n"
            f"처리 결과: {result_line}\n\n"
            f"보고서 확인: {report_line}\n"
            f"{DISCLAIMER}"
        )

    def _no_news_message(self, summary: dict) -> str:
        failed_boards = summary.get("failed_boards", []) + summary.get("failed_details", [])
        failure_line = ""

        if failed_boards:
            failure_line = f"\n점검 필요 게시판 {len(failed_boards)}개는 report.html에서 확인하세요."

        return (
            "[시간제등록 일일 점검 - 신규 없음]\n\n"
            f"점검 시각: {summary.get('checked_at')}\n"
            f"게시판 {summary.get('board_success_count')}개 점검, 공지 {summary.get('crawled_count')}건 수집.\n"
            "새로 발견된 시간제등록/외부 수강 공고는 없습니다."
            f"{failure_line}"
        )

    def _format_counts(self, counts: dict) -> str:
        parts: list[str] = []

        for key in sorted(counts):
            parts.append(f"{key}:{counts[key]}")

        return ", ".join(parts)

    def _format_preview_items(self, items: list[dict]) -> str:
        if not items:
            return "- A~C 후보 없음"

        lines: list[str] = []

        for index, item in enumerate(items[:5]):
            sNew = "신규" if item.get("is_new") else "기존"
            lines.append(
                f"{index + 1}. [{item.get('grade')}/{sNew}] {item.get('university_name')} - {item.get('title')}\n"
                f"   {item.get('url')}"
            )

        return "\n".join(lines)

    def _format_failed_boards(self, boards: list[dict]) -> str:
        if not boards:
            return "- 없음"

        lines: list[str] = []

        for index, board in enumerate(boards[:5]):
            sError = str(board.get("error", "")).splitlines()[0]
            if len(sError) > 120:
                sError = sError[:117] + "..."
            lines.append(
                f"{index + 1}. {board.get('university_name')} / {board.get('board_type')}: {sError}"
            )

        if len(boards) > 5:
            lines.append(f"- 그 외 {len(boards) - 5}개는 report.html 또는 Actions 로그 확인")

        return "\n".join(lines)

    def _format_report_location(self, actions_run_url: str, artifact_name: str, report_html_url: str = "") -> str:
        if report_html_url:
            return report_html_url

        if not actions_run_url:
            return f"GitHub 저장소 > Actions > 최신 실행 > Artifacts > {artifact_name} > report.html"

        return f"{actions_run_url} 에서 Artifacts > {artifact_name} 다운로드 후 report.html 열기"


class GraduateAdmissionNotifier:
    def __init__(self):
        load_dotenv()
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.delivery_failures: list[str] = []
        self.summary_sent = False

    def send_candidates(
        self,
        items: list[dict],
        dry_run: bool = False,
        send_empty_summary: bool = True,
    ) -> list[dict]:
        targets = [
            item for item in items
            if item.get("is_new") and item.get("grade") in {"A", "B"} and is_recent_notice(item)
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
                self.delivery_failures.append(str(exc))
            return sent

        # 원서접수 포털(유웨이/진학사) 항목은 수십 건씩 쏟아지므로 요약 한 통으로 묶는다
        portal_targets = [item for item in targets if self._is_portal_item(item)]
        board_targets = [item for item in targets if not self._is_portal_item(item)]

        for item in board_targets:
            try:
                self._send(self._message(item))
                sent.append(item)
            except Exception as exc:
                LOGGER.warning("Telegram send failed: %s", exc)
                self.delivery_failures.append(str(exc))

        for batch_items, message in self._portal_digest_batches(portal_targets):
            try:
                self._send(message)
                sent.extend(batch_items)
            except Exception as exc:
                LOGGER.warning("Telegram portal digest send failed: %s", exc)
                self.delivery_failures.append(str(exc))

        return sent

    def _is_portal_item(self, item: dict) -> bool:
        return "어플라이" in str(item.get("board_type", ""))

    def _portal_digest_messages(self, items: list[dict], max_lines: int = 25) -> list[str]:
        return [message for _, message in self._portal_digest_batches(items, max_lines)]

    def _portal_digest_batches(
        self,
        items: list[dict],
        max_lines: int = 25,
    ) -> list[tuple[list[dict], str]]:
        lstLines = [
            f"- {item.get('title')}\n  {item.get('url')}"
            for item in items
        ]
        batches: list[tuple[list[dict], str]] = []

        for iStart in range(0, len(lstLines), max_lines):
            chunk = lstLines[iStart:iStart + max_lines]
            batch_items = items[iStart:iStart + max_lines]
            message = (
                f"[원서접수 포털 - 접수중인 일반대학원 {len(items)}건]\n\n"
                + "\n".join(chunk)
                + "\n\n유웨이어플라이/진학사어플라이 접수 목록에서 확인된 신규 항목입니다."
            )
            batches.append((batch_items, message))

        return batches

    def _send(self, text: str) -> None:
        if not self.token or not self.chat_id:
            raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required.")

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        response = requests.post(url, json={"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True}, timeout=15)
        response.raise_for_status()

    def _message(self, item: dict) -> str:
        matched = ", ".join(item.get("matched_keywords") or []) or "확인 필요"

        return (
            "[일반대학원 모집 알림]\n\n"
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
            "[일반대학원 모집 확인 완료]\n\n"
            "신규 알림 대상: 없음\n"
            f"확인 시각: {checked_at or '확인 필요'}\n"
            f"활성 감시 대상: {active_count}개\n"
            f"보류/비활성 대상: {disabled_count}개\n"
            f"기존/참고 후보 감지: {len(items)}건\n\n"
            "새로 알릴 일반대학원 모집 공고는 발견되지 않았습니다. "
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
