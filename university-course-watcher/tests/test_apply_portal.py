from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.apply_portal import _grade


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


if __name__ == "__main__":
    unittest.main()
