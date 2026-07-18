from __future__ import annotations

import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "daily-check.yml"
PROJECT_ROOT = REPOSITORY_ROOT / "university-course-watcher"
LOCK_PATH = PROJECT_ROOT / "requirements.lock"

EXPECTED_ACTIONS = {
    "actions/cache": ("caa296126883cff596d87d8935842f9db880ef25", "v5.1.0"),
    "actions/checkout": ("df4cb1c069e1874edd31b4311f1884172cec0e10", "v6.0.3"),
    "actions/download-artifact": ("3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c", "v8.0.1"),
    "actions/setup-python": ("ece7cb06caefa5fff74198d8649806c4678c61a1", "v6.3.0"),
    "actions/upload-artifact": ("043fb46d1a93c77aae656e7c1c64a875d1fc6a0a", "v7.0.1"),
}


class SupplyChainContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.lock_text = LOCK_PATH.read_text(encoding="utf-8")

    def test_every_external_action_is_pinned_to_an_expected_commit(self) -> None:
        action_uses = re.findall(
            r"(?m)^\s*-?\s*uses:\s+([^@\s]+)@([^\s#]+)\s+#\s+(v[^\s]+)\s*$",
            self.workflow_text,
        )

        self.assertGreater(len(action_uses), 0)
        for action_name, commit_sha, version in action_uses:
            self.assertIn(action_name, EXPECTED_ACTIONS)
            self.assertEqual(EXPECTED_ACTIONS[action_name], (commit_sha, version))
            self.assertRegex(commit_sha, r"^[0-9a-f]{40}$")

        raw_uses_count = len(re.findall(r"(?m)^\s*-?\s*uses:", self.workflow_text))
        self.assertEqual(raw_uses_count, len(action_uses))

    def test_ci_installs_only_the_hash_locked_dependency_graph(self) -> None:
        install_command = (
            "python -m pip install --require-hashes "
            "-r university-course-watcher/requirements.lock"
        )

        self.assertEqual(2, self.workflow_text.count(install_command))
        self.assertNotIn("pip install -r university-course-watcher/requirements.txt", self.workflow_text)
        self.assertEqual(
            2,
            self.workflow_text.count(
                "cache-dependency-path: university-course-watcher/requirements.lock"
            ),
        )

    def test_lock_contains_only_exact_versions_and_sha256_hashes(self) -> None:
        package_blocks = re.findall(
            r"(?ms)^([a-z0-9][a-z0-9._-]*)==([^\s\\]+)\s*\\.*?"
            r"(?=^[a-z0-9][a-z0-9._-]*==[^\s\\]+\s*\\|\Z)",
            self.lock_text,
        )

        self.assertGreater(len(package_blocks), 0)
        self.assertNotRegex(self.lock_text, r"(?m)^\s*(?:-e\s+|https?://|git\+)")
        for package_name, version in package_blocks:
            package_prefix = f"{package_name}=={version}"
            package_start = self.lock_text.index(package_prefix)
            next_package = re.search(
                r"(?m)^[a-z0-9][a-z0-9._-]*==[^\s\\]+\s*\\",
                self.lock_text[package_start + len(package_prefix) :],
            )
            package_end = (
                package_start + len(package_prefix) + next_package.start()
                if next_package is not None
                else len(self.lock_text)
            )
            self.assertIn("--hash=sha256:", self.lock_text[package_start:package_end], package_name)


if __name__ == "__main__":
    unittest.main()
