from __future__ import annotations

import unittest

from src.classifier import HARD_EXCLUSION_TERMS, classify
from src.utils import CONFIG_DIR, load_json


class CourseClassifierTest(unittest.TestCase):
    def setUp(self) -> None:
        self.keywords = load_json(CONFIG_DIR / "keywords.json", {})
        self.open_dates = {"deadline_status": "모집중"}

    def test_qualification_notices_are_hard_excluded_despite_positive_signals(self) -> None:
        title = "2026학년도 2학기 시간제등록생 모집요강"
        positive_body = "고등학교 졸업 일반인 누구나 신청 가능 AI Python 소프트웨어 원서접수"

        for exclusion_term in HARD_EXCLUSION_TERMS:
            with self.subTest(exclusion_term=exclusion_term):
                result = classify(title, f"{positive_body} {exclusion_term} 안내", self.open_dates, self.keywords)

                self.assertEqual("D", result.grade)

    def test_b_grade_requires_external_applicant_signal(self) -> None:
        result = classify("시간제등록", "", self.open_dates, self.keywords)

        self.assertEqual("C", result.grade)
        self.assertEqual(0, result.external_score)

    def test_b_grade_remains_available_with_external_applicant_signal(self) -> None:
        result = classify("시간제등록", "성인학습자 대상", self.open_dates, self.keywords)

        self.assertEqual("B", result.grade)
        self.assertGreaterEqual(result.external_score, 20)


if __name__ == "__main__":
    unittest.main()
