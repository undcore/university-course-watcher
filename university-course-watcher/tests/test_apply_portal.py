from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.apply_portal import _fetch_uway, _grade, fetch_portal_items


UWAY_HTML = """
<div class='list col2'><h4>대학원 전기</h4><ul>
<li><a href='https://ipsi1.uwayapply.com/2027/gradu1/gen/?CHA=1'><i class='rec' title='접수예정'>예</i>가톨릭대학교 일반대학원(성심)<span><i title='유웨이 단독'>U</i></span></a></li>
<li><a href='https://ipsi2.uwayapply.com/2027/gradu1/cukgrd/?CHA=4'><i class='rec' title='접수중'>접</i>가톨릭대학교 일반대학원(성의)</a></li>
<li><a href='https://ipsi1.uwayapply.com/2027/gradu1/counselg/?CHA=5'><i class='rec' title='접수중'>접</i>가톨릭대학교 교육대학원</a></li>
</ul></div>
<div class='list col2'><h4>대학원 후기</h4><ul>
<li><a href='https://ipsi1.uwayapply.com/2026/gradu/gen/?CHA=1'><i class='rec clos' title='접수마감'>마</i>가톨릭대학교 일반대학원(성심)</a></li>
</ul></div>
"""


class FakeResponse:
    def __init__(self, text: str):
        self.content = text.encode("utf-8")

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, text: str):
        self.text = text

    def get(self, *args: object, **kwargs: object) -> FakeResponse:
        return FakeResponse(self.text)


class ApplyPortalClassificationTest(unittest.TestCase):
    def test_general_graduate_recruitment_is_accepted(self) -> None:
        self.assertEqual("A", _grade("테스트대학교 일반대학원 일반전형"))

    def test_separate_programs_are_excluded(self) -> None:
        names = [
            "테스트대학교 일반대학원 학석사연계과정",
            "테스트대학교 일반대학원 계약학과",
            "테스트대학교 일반대학원 외국인전형",
        ]

        for name in names:
            with self.subTest(name=name):
                self.assertEqual("D", _grade(name))


class UwayApplyFetchTest(unittest.TestCase):
    def test_catholic_general_graduate_entries_are_collected_and_closed_ones_skipped(self) -> None:
        with patch("src.apply_portal.SafeHttpSession", return_value=FakeSession(UWAY_HTML)):
            items = _fetch_uway("")

        self.assertEqual(
            ["가톨릭대학교 일반대학원(성심)", "가톨릭대학교 일반대학원(성의)"],
            [item["title"] for item in items],
        )
        self.assertEqual({"가톨릭대학교"}, {item["university_name"] for item in items})
        self.assertEqual(["접수예정", "접수중"], [item["apply_status"] for item in items])
        self.assertEqual("유웨이어플라이 대학원 전기", items[0]["board_type"])

    def test_missing_graduate_sections_is_a_failure_not_an_empty_result(self) -> None:
        with patch("src.apply_portal.SafeHttpSession", return_value=FakeSession("<html>점검중</html>")):
            with self.assertRaises(RuntimeError):
                _fetch_uway("")

    def test_uway_failure_is_reported_but_jinhak_failure_is_only_logged(self) -> None:
        failures: list[str] = []

        def _fetch_uway(target_term: str) -> list[dict]:
            raise RuntimeError("timeout")

        def _fetch_jinhak(target_term: str) -> list[dict]:
            raise RuntimeError("403")

        with patch("src.apply_portal._fetch_uway", new=_fetch_uway), \
                patch("src.apply_portal._fetch_jinhak", new=_fetch_jinhak), \
                self.assertLogs("src.apply_portal", level="WARNING"):
            items = fetch_portal_items(failures=failures)

        self.assertEqual([], items)
        self.assertEqual(["유웨이어플라이: timeout"], failures)


if __name__ == "__main__":
    unittest.main()
