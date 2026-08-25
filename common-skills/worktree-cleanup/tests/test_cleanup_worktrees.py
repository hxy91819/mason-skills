from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "cleanup_worktrees.py"
REAL_GIT = "/usr/bin/git"


class CleanupWorktreesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.repo = self.root / "repository"
        self.worktree = self.repo / ".worktrees" / "pr-123"
        self.state_home = self.root / "state"
        self.fake_bin = self.root / "bin"
        self.fake_bin.mkdir()

        self.run_git("init", "-b", "main", str(self.repo), cwd=self.root)
        self.run_git("config", "user.name", "Test User")
        self.run_git("config", "user.email", "test@example.invalid")
        (self.repo / ".gitignore").write_text(".local/\n", encoding="utf-8")
        (self.repo / "tracked.txt").write_text("baseline\n", encoding="utf-8")
        self.run_git("add", ".")
        self.run_git("commit", "-m", "baseline")
        self.worktree.parent.mkdir()
        self.run_git("worktree", "add", "-b", "pr-123", str(self.worktree))

    def run_git(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [REAL_GIT, *args],
            cwd=cwd or self.repo,
            check=True,
            capture_output=True,
            text=True,
        )

    def install_fake_gh(self, state: str = "CLOSED") -> None:
        merged_at = '"2026-01-02T03:04:05Z"' if state == "MERGED" else "None"
        closed_at = '"2026-01-02T03:04:05Z"' if state == "CLOSED" else "None"
        script = f"""#!/usr/bin/env python3
import json
import sys

if sys.argv[1:3] == ["pr", "view"]:
    print(json.dumps({{
        "number": 123,
        "state": "{state}",
        "title": "Test pull request",
        "url": "https://github.example/pulls/123",
        "headRefName": "pr-123",
        "mergedAt": {merged_at},
        "closedAt": {closed_at},
    }}))
elif sys.argv[1:3] == ["pr", "list"]:
    print("[]")
else:
    sys.exit(2)
"""
        gh = self.fake_bin / "gh"
        gh.write_text(script, encoding="utf-8")
        gh.chmod(0o755)

    def helper_environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment["PATH"] = f"{self.fake_bin}:/usr/bin:/bin"
        environment["XDG_STATE_HOME"] = str(self.state_home)
        return environment

    def run_helper(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), *args],
            cwd=self.root,
            env=self.helper_environment(),
            capture_output=True,
            text=True,
        )

    def test_dry_run_keeps_dirty_closed_pr_worktree(self) -> None:
        self.install_fake_gh()
        (self.worktree / "uncommitted.txt").write_text("keep me\n", encoding="utf-8")

        result = self.run_helper("--dry-run", "--json")

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["eligible"], 0)
        self.assertEqual(report["entries"][0]["action"], "skip")
        self.assertIn("uncommitted changes", report["entries"][0]["skip_reason"])
        self.assertTrue((self.worktree / "uncommitted.txt").exists())
        self.assertFalse(self.state_home.exists())

    def test_apply_backs_up_local_data_and_removes_clean_closed_pr_worktree(self) -> None:
        self.install_fake_gh()
        local_file = self.worktree / ".local" / "notes.txt"
        local_file.parent.mkdir()
        local_file.write_text("restore me\n", encoding="utf-8")

        result = self.run_helper("--apply", "--json")

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["removed"], 1)
        self.assertFalse(self.worktree.exists())
        backup_root = Path(report["backup_root"])
        backup_file = backup_root / "pr-123" / ".local" / "notes.txt"
        self.assertEqual(backup_file.read_text(encoding="utf-8"), "restore me\n")
        manifest = json.loads((backup_root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["items"][0]["action"], "removed")
        branches = self.run_git("branch", "--format=%(refname:short)").stdout.splitlines()
        self.assertIn("pr-123", branches)

    def test_failed_removal_is_recorded_in_manifest(self) -> None:
        self.install_fake_gh()
        git_wrapper = self.fake_bin / "git"
        git_wrapper.write_text(
            """#!/usr/bin/env python3
import os
import sys

if sys.argv[1:3] == ["worktree", "remove"]:
    print("simulated worktree guard", file=sys.stderr)
    sys.exit(77)
os.execv("/usr/bin/git", ["git", *sys.argv[1:]])
""",
            encoding="utf-8",
        )
        git_wrapper.chmod(0o755)

        result = self.run_helper("--apply", "--json")

        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertEqual(report["failed"], 1)
        self.assertTrue(self.worktree.exists())
        backup_root = Path(report["backup_root"])
        manifest = json.loads((backup_root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["items"][0]["action"], "failed")
        self.assertIn("simulated worktree guard", manifest["items"][0]["error"])

    def test_apply_rejects_backup_root_inside_cleanup_target(self) -> None:
        self.install_fake_gh()
        unsafe_backup_root = self.worktree / ".local" / "backups"

        result = self.run_helper(
            "--apply", "--backup-root", str(unsafe_backup_root), "--json"
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("is inside cleanup target", result.stderr)
        self.assertTrue(self.worktree.exists())
        self.assertFalse(unsafe_backup_root.exists())


if __name__ == "__main__":
    unittest.main()
