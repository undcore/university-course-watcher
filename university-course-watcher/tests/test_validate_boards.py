from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from validate_graduate_admission_boards import evaluate_result, _markdown_summary


class EvaluateResultTest(unittest.TestCase):
    def test_healthy_board_is_ok(self) -> None:
        ok, reason = evaluate_result("200", 3, "https://grad.example.ac.kr/notice")
        self.assertTrue(ok)
        self.assertEqual("정상", reason)

    def test_disabled_board_is_excluded_not_failed(self) -> None:
        ok, _ = evaluate_result("SKIP", 0, "https://grad.example.ac.kr/notice")
        self.assertTrue(ok)

    def test_request_error_fails(self) -> None:
        ok, reason = evaluate_result("ERR", 0, "ConnectionError: boom")
        self.assertFalse(ok)
        self.assertIn("요청 실패", reason)

    def test_non_200_status_fails(self) -> None:
        ok, reason = evaluate_result("404", 0, "https://grad.example.ac.kr/notice")
        self.assertFalse(ok)
        self.assertIn("404", reason)

    def test_login_redirect_fails(self) -> None:
        ok, reason = evaluate_result("200", 5, "https://sso.example.ac.kr/login")
        self.assertFalse(ok)
        self.assertIn("SSO", reason)

    def test_zero_keyword_hits_fails(self) -> None:
        ok, reason = evaluate_result("200", 0, "https://grad.example.ac.kr/notice")
        self.assertFalse(ok)
        self.assertIn("키워드", reason)


class MarkdownSummaryTest(unittest.TestCase):
    def test_summary_counts_failures(self) -> None:
        results = [
            {"university_name": "A대", "status": "200", "keyword_hits": 3,
             "enabled": True, "ok": True, "reason": "정상"},
            {"university_name": "B대", "status": "404", "keyword_hits": 0,
             "enabled": True, "ok": False, "reason": "HTTP 상태 404"},
            {"university_name": "C대", "status": "SKIP", "keyword_hits": 0,
             "enabled": False, "ok": True, "reason": "비활성화된 게시판(검증 제외)"},
        ]

        markdown = _markdown_summary(results)

        self.assertIn("검증 대상: 2개", markdown)
        self.assertIn("정상: 1개 / 문제: 1개", markdown)
        self.assertIn("| B대 |", markdown)


if __name__ == "__main__":
    unittest.main()
