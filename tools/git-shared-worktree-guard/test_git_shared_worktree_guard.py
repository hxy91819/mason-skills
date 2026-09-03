import subprocess
import tempfile
import unittest
from pathlib import Path


GIT = "/usr/bin/git"
GUARD = Path(__file__).with_name("git")


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)


class SharedWorktreeGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repository"
        self.worktree = Path(self.temp.name) / "cleanup-target"
        self.root.mkdir()
        self.git("init")
        self.git("config", "user.name", "Guard Test")
        self.git("config", "user.email", "guard-test@example.invalid")
        (self.root / "README.md").write_text("base\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-m", "base")
        self.git("worktree", "add", "-b", "cleanup-target", str(self.worktree))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        result = run(GIT, *args, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def guard(self, *args: str) -> subprocess.CompletedProcess[str]:
        return run(str(GUARD), *args, cwd=self.root)

    def test_worktree_remove_without_authorization_is_blocked(self) -> None:
        result = self.guard("worktree", "remove", str(self.worktree))

        self.assertEqual(result.returncode, 77)
        self.assertTrue(self.worktree.exists())

    def test_user_authorization_removes_a_clean_registered_worktree(self) -> None:
        result = self.guard(
            "--user-approved=the user asked to clean this verified obsolete worktree",
            "worktree",
            "remove",
            str(self.worktree),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.worktree.exists())

    def test_user_authorization_requires_a_reason(self) -> None:
        result = self.guard("--user-approved", "worktree", "remove", str(self.worktree))

        self.assertEqual(result.returncode, 64)
        self.assertTrue(self.worktree.exists())

    def test_task_authorized_flag_is_no_longer_accepted(self) -> None:
        result = self.guard(
            "--task-authorized=the user asked to clean this verified obsolete worktree",
            "worktree",
            "remove",
            str(self.worktree),
        )

        self.assertEqual(result.returncode, 77)
        self.assertTrue(self.worktree.exists())

    def test_rebase_is_not_blocked(self) -> None:
        (self.root / "new.txt").write_text("content\n", encoding="utf-8")
        self.git("add", "new.txt")
        self.git("commit", "-m", "commit for rebase")
        result = self.guard("rebase", "HEAD~1")
        self.assertNotEqual(result.returncode, 77)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rebase_with_autostash_and_dirty_worktree_is_blocked(self) -> None:
        (self.root / "README.md").write_text("dirty change\n", encoding="utf-8")
        result = self.guard("rebase", "--autostash", "HEAD")
        self.assertEqual(result.returncode, 77)

    def test_rebase_with_autostash_and_clean_worktree_is_not_blocked(self) -> None:
        result = self.guard("rebase", "--autostash", "HEAD")
        self.assertNotEqual(result.returncode, 77)

    def test_rebase_with_config_autostash_and_dirty_worktree_is_blocked(self) -> None:
        self.git("config", "rebase.autoStash", "true")
        (self.root / "README.md").write_text("dirty change\n", encoding="utf-8")
        result = self.guard("rebase", "HEAD")
        self.assertEqual(result.returncode, 77)

    def test_rebase_with_config_autostash_and_no_autostash_flag_is_not_blocked(
        self,
    ) -> None:
        self.git("config", "rebase.autoStash", "true")
        (self.root / "README.md").write_text("dirty change\n", encoding="utf-8")
        result = self.guard("rebase", "--no-autostash", "HEAD")
        self.assertNotEqual(result.returncode, 77)


if __name__ == "__main__":
    unittest.main()
