import os
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
        self.root.mkdir()
        self.git("init")
        self.git("config", "user.name", "Guard Test")
        self.git("config", "user.email", "guard-test@example.invalid")
        (self.root / "README.md").write_text("base\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-m", "base")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        result = run(GIT, *args, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def guard(
        self, *args: str, env_overrides: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(GUARD), *args],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, **(env_overrides or {})},
        )

    def assert_blocked(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 77, result.stderr)
        self.assertIn("HARD-BLOCKED", result.stderr)

    def assert_forwarded(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertNotEqual(result.returncode, 77, result.stderr)

    def test_wrapper_help_describes_only_stash_policy(self) -> None:
        result = self.guard("--wrapper-help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("stash operations and autostash", result.stdout)
        self.assertNotIn("--user-approved", result.stdout)

    def test_stash_list_and_show_are_forwarded(self) -> None:
        (self.root / "README.md").write_text("fixture change\n", encoding="utf-8")
        self.git("stash", "push", "-m", "fixture")

        self.assertEqual(self.guard("stash", "list").returncode, 0)
        self.assertEqual(self.guard("stash", "show", "stash@{0}").returncode, 0)

    def test_stash_help_is_forwarded(self) -> None:
        result = self.guard("stash", "push", "--help")

        self.assert_forwarded(result)

    def test_state_changing_stash_commands_are_hard_blocked(self) -> None:
        for args in (
            ("stash",),
            ("stash", "push"),
            ("stash", "save"),
            ("stash", "create"),
            ("stash", "store", "deadbeef"),
            ("stash", "pop"),
            ("stash", "apply"),
            ("stash", "drop"),
            ("stash", "clear"),
            ("stash", "branch", "temporary"),
        ):
            with self.subTest(args=args):
                self.assert_blocked(self.guard(*args))

    def test_explicit_autostash_is_hard_blocked(self) -> None:
        for args in (
            ("rebase", "--autostash", "HEAD"),
            ("merge", "--autostash", "HEAD"),
            ("pull", "--autostash"),
        ):
            with self.subTest(args=args):
                self.assert_blocked(self.guard(*args))

    def test_configured_autostash_is_hard_blocked(self) -> None:
        self.git("config", "rebase.autoStash", "true")
        self.assert_blocked(self.guard("rebase", "HEAD"))

        self.git("config", "--unset", "rebase.autoStash")
        self.git("config", "merge.autoStash", "true")
        self.assert_blocked(self.guard("merge", "HEAD"))

    def test_pull_uses_the_selected_strategy_autostash_setting(self) -> None:
        self.git("config", "pull.rebase", "true")
        self.git("config", "rebase.autoStash", "true")
        self.assert_blocked(self.guard("pull"))

        self.git("config", "pull.rebase", "false")
        self.git("config", "--unset", "rebase.autoStash")
        self.git("config", "merge.autoStash", "true")
        self.assert_blocked(self.guard("pull"))

    def test_no_autostash_overrides_configuration(self) -> None:
        self.git("config", "rebase.autoStash", "true")
        (self.root / "README.md").write_text("dirty change\n", encoding="utf-8")

        result = self.guard("rebase", "--no-autostash", "HEAD")

        self.assert_forwarded(result)
        self.assertEqual(
            (self.root / "README.md").read_text(encoding="utf-8"),
            "dirty change\n",
        )

    def test_rebase_query_is_not_treated_as_an_autostash_start(self) -> None:
        self.git("config", "rebase.autoStash", "true")

        self.assert_forwarded(self.guard("rebase", "--show-current-patch"))

    def test_static_alias_cannot_hide_stash(self) -> None:
        self.git("config", "alias.hide", "stash push -m hidden")
        (self.root / "README.md").write_text("must remain visible\n", encoding="utf-8")

        result = self.guard("hide")

        self.assert_blocked(result)
        self.assertEqual(
            (self.root / "README.md").read_text(encoding="utf-8"),
            "must remain visible\n",
        )

    def test_command_scoped_alias_cannot_hide_stash(self) -> None:
        (self.root / "README.md").write_text("must remain visible\n", encoding="utf-8")

        result = self.guard("-c", "alias.hide=stash push", "hide")

        self.assert_blocked(result)
        self.assertEqual(
            (self.root / "README.md").read_text(encoding="utf-8"),
            "must remain visible\n",
        )

    def test_builtin_command_takes_precedence_over_alias(self) -> None:
        self.git("config", "alias.rebase", "status")
        self.git("config", "rebase.autoStash", "true")

        self.assert_blocked(self.guard("rebase", "HEAD"))

    def test_shell_alias_is_forwarded(self) -> None:
        self.git("config", "alias.external", "!printf 'safe output\\n'")

        result = self.guard("external")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("safe output", result.stdout)

    def test_reset_and_worktree_removal_are_forwarded(self) -> None:
        (self.root / "README.md").write_text("changed\n", encoding="utf-8")
        reset = self.guard("reset", "--hard", "HEAD")

        self.assertEqual(reset.returncode, 0, reset.stderr)
        self.assertEqual(
            (self.root / "README.md").read_text(encoding="utf-8"), "base\n"
        )

        worktree = Path(self.temp.name) / "delivered-worktree"
        self.git("worktree", "add", "-b", "delivered-worktree", str(worktree))
        removal = self.guard("worktree", "remove", str(worktree))

        self.assertEqual(removal.returncode, 0, removal.stderr)
        self.assertFalse(worktree.exists())


if __name__ == "__main__":
    unittest.main()
