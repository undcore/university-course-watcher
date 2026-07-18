from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

from requests.exceptions import SSLError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.course_finder import CourseFinder


class TlsSecurityContractTest(unittest.TestCase):
    def test_course_finder_does_not_retry_without_certificate_validation(self) -> None:
        finder = CourseFinder({"course_names": [], "course_search": []})
        finder.session.get = Mock(side_effect=SSLError("certificate rejected"))

        with self.assertRaisesRegex(SSLError, "certificate rejected"):
            finder._get("https://university.example/course")

        finder.session.get.assert_called_once_with(
            "https://university.example/course",
            timeout=finder.timeout,
        )

    def test_python_sources_do_not_disable_tls_verification(self) -> None:
        forbidden_patterns = (
            re.compile(r"verify\s*=\s*False"),
            re.compile(r"disable_warnings\s*\("),
            re.compile(r"InsecureRequestWarning"),
        )
        violations: list[str] = []
        contract_path = Path(__file__).resolve()

        for source_path in sorted(PROJECT_ROOT.rglob("*.py")):
            if "__pycache__" in source_path.parts or source_path.resolve() == contract_path:
                continue

            source_text = source_path.read_text(encoding="utf-8")
            for pattern in forbidden_patterns:
                if pattern.search(source_text):
                    relative_path = source_path.relative_to(PROJECT_ROOT)
                    violations.append(f"{relative_path}: {pattern.pattern}")

        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
