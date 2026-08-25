from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
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
        self.state_home = self.root / "state"
        self.fake_bin = self.root / "bin"
        self.fake_bin.mkdir()
        self.remote_heads: dict[str, str] = {}
        self.fake_pr_state = "CLOSED"
        self.fake_no_pr = False
        self.fake_durable = True

        self.run_git("init", "-b", "main", str(self.repo), cwd=self.root)
        self.run_git("config", "user.name", "Test User")
        self.run_git("config", "user.email", "test@example.invalid")
        (self.repo / ".gitignore").write_text(".local/\n.env\n", encoding="utf-8")
        (self.repo / "tracked.txt").write_text("baseline\n", encoding="utf-8")
        self.run_git("add", ".")
        self.run_git("commit", "-m", "baseline")
        self.default_head = self.run_git("rev-parse", "HEAD").stdout.strip()
        self.worktree = self.add_worktree("task-123")
        self.install_fake_gh()

    def run_git(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [REAL_GIT, *args],
            cwd=cwd or self.repo,
            check=True,
            capture_output=True,
            text=True,
        )

    def add_worktree(self, branch: str) -> Path:
        path = self.repo / ".worktrees" / branch
        path.parent.mkdir(exist_ok=True)
        self.run_git("worktree", "add", "-b", branch, str(path))
        self.remote_heads[branch] = self.run_git(
            "-C", str(path), "rev-parse", "HEAD"
        ).stdout.strip()
        return path

    def install_fake_gh(self) -> None:
        script = """#!/usr/bin/env python3
import json
import os
import re
import sys

args = sys.argv[1:]
heads = json.loads(os.environ["FAKE_HEADS_JSON"])
state = os.environ["FAKE_PR_STATE"]
no_pr = os.environ["FAKE_NO_PR"] == "1"

def pr_row(branch):
    number_match = re.search(r"(\\d+)$", branch)
    number = int(number_match.group(1)) if number_match else 1
    timestamp = "2026-01-02T03:04:05Z"
    return {
        "number": number,
        "state": state,
        "title": f"Test pull request for {branch}",
        "url": f"https://github.example/pulls/{number}",
        "headRefName": branch,
        "headRefOid": heads[branch],
        "mergedAt": timestamp if state == "MERGED" else None,
        "closedAt": timestamp if state == "CLOSED" else None,
    }

if args[:2] == ["repo", "view"]:
    print(json.dumps({
        "nameWithOwner": "example/repository",
        "defaultBranchRef": {"name": "main"},
    }))
elif args[:2] == ["pr", "view"]:
    number = args[2]
    branch = next((name for name in heads if name.endswith(number)), None)
    if no_pr or branch is None:
        print("pull request not found", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(pr_row(branch)))
elif args[:2] == ["pr", "list"]:
    branch = args[args.index("--head") + 1]
    print(json.dumps([] if no_pr else [pr_row(branch)]))
elif args and args[0] == "api":
    endpoint = args[1]
    if "/commits/" in endpoint:
        if endpoint.endswith("/branches-where-head"):
            commit = endpoint.split("/commits/", 1)[1].split("/", 1)[0]
            print(json.dumps([
                {"name": branch}
                for branch, head in heads.items()
                if head == commit
            ]))
        else:
            print(json.dumps({"sha": os.environ["FAKE_DEFAULT_HEAD"]}))
    elif "/compare/" in endpoint:
        comparison = endpoint.rsplit("/", 1)[-1]
        base = comparison.split("...", 1)[0]
        merge_base = base if os.environ["FAKE_DURABLE"] == "1" else "0" * 40
        print(json.dumps({"merge_base_commit": {"sha": merge_base}}))
    else:
        sys.exit(2)
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
        environment["FAKE_HEADS_JSON"] = json.dumps(self.remote_heads)
        environment["FAKE_PR_STATE"] = self.fake_pr_state
        environment["FAKE_NO_PR"] = "1" if self.fake_no_pr else "0"
        environment["FAKE_DURABLE"] = "1" if self.fake_durable else "0"
        environment["FAKE_DEFAULT_HEAD"] = self.default_head
        return environment

    def run_helper(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), *args],
            cwd=self.root,
            env=self.helper_environment(),
            capture_output=True,
            text=True,
        )

    def audit(self) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        result = self.run_helper("--dry-run", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        return result, json.loads(result.stdout)

    def approval_for(self, report: dict[str, object], path: Path) -> str:
        entry = next(
            item for item in report["entries"] if item["path"] == str(path)
        )
        token = entry["approval_token"]
        self.assertIsInstance(token, str)
        return token

    def test_apply_requires_an_exact_dry_run_approval_token(self) -> None:
        result = self.run_helper("--apply", "--json")

        self.assertEqual(result.returncode, 2)
        self.assertIn("--apply requires", result.stderr)
        self.assertTrue(self.worktree.exists())

    def test_dirty_closed_pr_worktree_is_kept(self) -> None:
        (self.worktree / "uncommitted.txt").write_text("keep me\n", encoding="utf-8")

        _, report = self.audit()

        entry = report["entries"][0]
        self.assertEqual(report["worktree_count_before"], 2)
        self.assertEqual(report["worktree_count_after"], 2)
        self.assertEqual(report["eligible"], 0)
        self.assertEqual(entry["action"], "skip")
        self.assertIn("untracked changes", entry["skip_reason"])
        self.assertTrue((self.worktree / "uncommitted.txt").exists())

    def test_apply_reports_ignored_data_and_removes_only_the_approved_target(self) -> None:
        local_file = self.worktree / ".local" / "notes.txt"
        local_file.parent.mkdir()
        local_file.write_text("restore me\n", encoding="utf-8")
        (self.worktree / ".env").write_text("discard after approval\n", encoding="utf-8")
        _, report = self.audit()
        entry = report["entries"][0]

        self.assertEqual(entry["ignored"]["discarded_sample"], [".env"])
        token = self.approval_for(report, self.worktree)
        result = self.run_helper("--apply", "--approve", token, "--json")

        self.assertEqual(result.returncode, 0, result.stderr)
        applied = json.loads(result.stdout)
        self.assertEqual(applied["removed"], 1)
        self.assertEqual(applied["worktree_count_before"], 2)
        self.assertEqual(applied["worktree_count_after"], 1)
        self.assertFalse(self.worktree.exists())
        backup_root = Path(applied["backup_root"])
        self.assertEqual(
            (backup_root / "task-123" / ".local" / "notes.txt").read_text(
                encoding="utf-8"
            ),
            "restore me\n",
        )
        self.assertFalse((backup_root / "task-123" / ".env").exists())
        branches = self.run_git("branch", "--format=%(refname:short)").stdout.splitlines()
        self.assertIn("task-123", branches)

    def test_locked_worktree_is_kept(self) -> None:
        self.run_git("worktree", "lock", "--reason", "active agent", str(self.worktree))

        _, report = self.audit()

        entry = report["entries"][0]
        self.assertEqual(entry["action"], "skip")
        self.assertEqual(entry["locked_reason"], "active agent")
        self.assertIn("locked", entry["skip_reason"])

    def test_pr_head_that_does_not_contain_local_head_is_kept(self) -> None:
        self.remote_heads["task-123"] = "f" * 40
        self.fake_durable = False

        _, report = self.audit()

        entry = report["entries"][0]
        self.assertEqual(entry["action"], "skip")
        self.assertIn("not contained", entry["skip_reason"])

    def test_branch_without_pr_number_is_looked_up_by_head_branch(self) -> None:
        worktree = self.add_worktree("descriptive-branch")

        _, report = self.audit()

        entry = next(item for item in report["entries"] if item["path"] == str(worktree))
        self.assertEqual(entry["pr"]["head_ref_name"], "descriptive-branch")
        self.assertIsInstance(entry["approval_token"], str)

    def test_old_prless_worktree_landed_on_default_branch_is_eligible(self) -> None:
        self.fake_no_pr = True
        self.remote_heads["task-123"] = "f" * 40
        old = time.time() - 25 * 3600
        os.utime(self.worktree / ".git", (old, old))

        _, report = self.audit()

        entry = report["entries"][0]
        self.assertEqual(entry["expiration_reason"], "landed-on-default")
        self.assertEqual(entry["remote_proof"]["kind"], "default-branch")
        self.assertIsInstance(entry["approval_token"], str)

    def test_old_prless_worktree_pushed_to_remote_branch_is_eligible(self) -> None:
        (self.worktree / "tracked.txt").write_text("pushed branch\n", encoding="utf-8")
        self.run_git("-C", str(self.worktree), "add", "tracked.txt")
        self.run_git("-C", str(self.worktree), "commit", "-m", "pushed branch")
        self.remote_heads["task-123"] = self.run_git(
            "-C", str(self.worktree), "rev-parse", "HEAD"
        ).stdout.strip()
        self.fake_no_pr = True
        self.fake_durable = False
        old = time.time() - 25 * 3600
        os.utime(self.worktree / ".git", (old, old))

        _, report = self.audit()

        entry = report["entries"][0]
        self.assertEqual(entry["remote_proof"]["kind"], "remote-branch-head")
        self.assertEqual(entry["remote_proof"]["branches"], ["task-123"])
        self.assertIsInstance(entry["approval_token"], str)

    def test_recent_prless_worktree_is_kept(self) -> None:
        self.fake_no_pr = True

        _, report = self.audit()

        entry = report["entries"][0]
        self.assertEqual(entry["action"], "skip")
        self.assertIn("younger than 24 hours", entry["skip_reason"])

    def test_state_drift_invalidates_the_approval_token(self) -> None:
        _, report = self.audit()
        token = self.approval_for(report, self.worktree)
        (self.worktree / "new-untracked.txt").write_text("changed\n", encoding="utf-8")

        result = self.run_helper("--apply", "--approve", token, "--json")

        self.assertEqual(result.returncode, 1)
        error = json.loads(result.stdout)
        self.assertIn("stale approval", error["error"])
        self.assertTrue(self.worktree.exists())

    def test_git_guard_task_authorization_is_used_when_available(self) -> None:
        _, report = self.audit()
        token = self.approval_for(report, self.worktree)
        git_wrapper = self.fake_bin / "git"
        git_wrapper.write_text(
            """#!/usr/bin/env python3
import os
import sys

if sys.argv[1:] == ["--wrapper-help"]:
    print("--task-authorized=<reason>")
    sys.exit(0)
if len(sys.argv) > 1 and sys.argv[1].startswith("--task-authorized="):
    os.execv("/usr/bin/git", ["git", *sys.argv[2:]])
os.execv("/usr/bin/git", ["git", *sys.argv[1:]])
""",
            encoding="utf-8",
        )
        git_wrapper.chmod(0o755)

        result = self.run_helper("--apply", "--approve", token, "--json")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["removed"], 1)
        self.assertFalse(self.worktree.exists())

    def test_failed_first_removal_marks_remaining_targets_not_attempted(self) -> None:
        second = self.add_worktree("task-456")
        _, report = self.audit()
        approvals = [
            self.approval_for(report, self.worktree),
            self.approval_for(report, second),
        ]
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

        result = self.run_helper(
            "--apply",
            "--approve",
            approvals[0],
            "--approve",
            approvals[1],
            "--json",
        )

        self.assertEqual(result.returncode, 1)
        applied = json.loads(result.stdout)
        actions = {entry["path"]: entry["action"] for entry in applied["entries"]}
        self.assertEqual(actions[str(self.worktree)], "authorization-required")
        self.assertEqual(actions[str(second)], "not-attempted")
        self.assertTrue(self.worktree.exists())
        self.assertTrue(second.exists())


if __name__ == "__main__":
    unittest.main()
