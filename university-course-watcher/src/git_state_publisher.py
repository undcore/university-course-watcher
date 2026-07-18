from __future__ import annotations

import os
import subprocess
from pathlib import Path


class RemoteStatePublishError(RuntimeError):
    """Raised when a state change cannot be proven durable on the remote branch."""


class GitStatePublisher:
    def __init__(self, repository_root: Path, branch: str, max_attempts: int = 3):
        self.repository_root = repository_root.resolve()
        self.branch = branch
        self.max_attempts = max_attempts

    @classmethod
    def from_actions_environment(cls, repository_root: Path) -> GitStatePublisher | None:
        enabled = os.getenv("DELIVERY_STATE_PUSH_ENABLED", "").lower() == "true"
        branch = os.getenv("GITHUB_REF_NAME", "")
        if not enabled:
            return None
        if not branch:
            raise RemoteStatePublishError("GITHUB_REF_NAME is required for durable delivery state.")
        return cls(repository_root, branch)

    def publish(self, state_path: Path) -> None:
        relative_path = state_path.resolve().relative_to(self.repository_root)
        path_text = relative_path.as_posix()

        self._run(["git", "config", "user.name", "github-actions[bot]"])
        self._run([
            "git",
            "config",
            "user.email",
            "41898282+github-actions[bot]@users.noreply.github.com",
        ])
        self._run(["git", "add", "--", path_text])

        staged_change = self._run(
            ["git", "diff", "--cached", "--quiet", "--", path_text],
            check=False,
        )
        if staged_change.returncode == 0:
            return

        self._run([
            "git",
            "commit",
            "--only",
            "-m",
            "Persist Telegram delivery state [skip ci]",
            "--",
            path_text,
        ])
        state_commit = self._output(["git", "rev-parse", "HEAD"])

        for attempt_index in range(0, self.max_attempts):
            push_result = self._run(
                ["git", "push", "origin", f"HEAD:{self.branch}"],
                check=False,
            )
            if push_result.returncode == 0 and self._remote_contains(state_commit):
                return
            if self._remote_contains(state_commit):
                return
            if attempt_index + 1 < self.max_attempts:
                self._run(["git", "fetch", "origin", self.branch])
                self._run([
                    "git",
                    "rebase",
                    "--autostash",
                    "-X",
                    "theirs",
                    f"origin/{self.branch}",
                ])
                state_commit = self._output(["git", "rev-parse", "HEAD"])

        raise RemoteStatePublishError(
            f"Delivery state was not confirmed on origin/{self.branch}; Telegram send is blocked."
        )

    def _remote_contains(self, commit: str) -> bool:
        fetch_result = self._run(["git", "fetch", "origin", self.branch], check=False)
        if fetch_result.returncode != 0:
            return False
        contains_result = self._run(
            ["git", "merge-base", "--is-ancestor", commit, f"origin/{self.branch}"],
            check=False,
        )
        return contains_result.returncode == 0

    def _output(self, command: list[str]) -> str:
        result = self._run(command)
        return result.stdout.strip()

    def _run(self, command: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=self.repository_root,
            check=check,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
