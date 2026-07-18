from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.git_state_publisher import GitStatePublisher, RemoteStatePublishError


class GitStatePublisherTest(unittest.TestCase):
    def test_actions_factory_requires_branch_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            environment = {"DELIVERY_STATE_PUSH_ENABLED": "true", "GITHUB_REF_NAME": ""}
            with patch.dict(os.environ, environment, clear=False):
                with self.assertRaisesRegex(RemoteStatePublishError, "GITHUB_REF_NAME"):
                    GitStatePublisher.from_actions_environment(Path(temp_dir))

    def test_publish_is_confirmed_in_remote_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            remote_path = temp_root / "remote.git"
            seed_path = temp_root / "seed"
            clone_path = temp_root / "clone"

            self._git(temp_root, "init", "--bare", str(remote_path))
            self._git(temp_root, "init", "-b", "main", str(seed_path))
            state_path = seed_path / "data" / "outbox.json"
            state_path.parent.mkdir(parents=True)
            state_path.write_text("{}\n", encoding="utf-8")
            self._git(seed_path, "config", "user.name", "test")
            self._git(seed_path, "config", "user.email", "test@example.com")
            self._git(seed_path, "add", "data/outbox.json")
            self._git(seed_path, "commit", "-m", "initial")
            self._git(seed_path, "remote", "add", "origin", str(remote_path))
            self._git(seed_path, "push", "-u", "origin", "main")
            self._git(temp_root, "clone", "-b", "main", str(remote_path), str(clone_path))

            cloned_state_path = clone_path / "data" / "outbox.json"
            cloned_state_path.write_text('{"delivery":"sending"}\n', encoding="utf-8")
            publisher = GitStatePublisher(clone_path, "main")

            publisher.publish(cloned_state_path)

            local_head = self._git(clone_path, "rev-parse", "HEAD").stdout.strip()
            remote_head = self._git(
                clone_path,
                "ls-remote",
                "origin",
                "refs/heads/main",
            ).stdout.split()[0]
            self.assertEqual(local_head, remote_head)

    def _git(self, working_directory: Path, *arguments: str):
        import subprocess

        return subprocess.run(
            ["git", *arguments],
            cwd=working_directory,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )


if __name__ == "__main__":
    unittest.main()
