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
        self.current_branch = self.git("branch", "--show-current").stdout.strip()
        self.git("worktree", "add", "-b", "cleanup-target", str(self.worktree))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        result = run(GIT, *args, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def guard(self, *args: str) -> subprocess.CompletedProcess[str]:
        return run(str(GUARD), *args, cwd=self.root)

    def assert_blocked(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 77, result.stderr)

    def assert_not_blocked(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertNotEqual(result.returncode, 77, result.stderr)

    def commit_file(self, name: str, content: str, message: str) -> None:
        (self.root / name).write_text(content, encoding="utf-8")
        self.git("add", name)
        self.git("commit", "-m", message)

    def test_worktree_remove_without_authorization_is_blocked(self) -> None:
        result = self.guard("worktree", "remove", str(self.worktree))

        self.assert_blocked(result)
        self.assertTrue(self.worktree.exists())

    def test_worktree_prune_dry_run_is_allowed(self) -> None:
        result = self.guard("worktree", "prune", "--dry-run")

        self.assertEqual(result.returncode, 0, result.stderr)

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

        self.assert_blocked(result)
        self.assertTrue(self.worktree.exists())

    def test_rebase_without_autostash_is_allowed_after_commit(self) -> None:
        self.commit_file("new.txt", "content\n", "commit for rebase")

        result = self.guard("rebase", "--no-autostash", "HEAD~1")

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rebase_with_autostash_is_blocked_even_when_clean(self) -> None:
        result = self.guard("rebase", "--autostash", "HEAD")

        self.assert_blocked(result)
        self.assertIn("HARD-BLOCKED", result.stderr)

    def test_rebase_with_configured_autostash_is_blocked_even_when_clean(self) -> None:
        self.git("config", "rebase.autoStash", "true")

        result = self.guard("rebase", "HEAD")

        self.assert_blocked(result)

    def test_explicit_no_autostash_overrides_config_and_uses_native_git_safety(
        self,
    ) -> None:
        self.git("config", "rebase.autoStash", "true")
        (self.root / "README.md").write_text("dirty change\n", encoding="utf-8")

        result = self.guard("rebase", "--no-autostash", "HEAD")

        self.assert_not_blocked(result)
        self.assertEqual((self.root / "README.md").read_text(encoding="utf-8"), "dirty change\n")

    def test_merge_with_configured_autostash_is_blocked(self) -> None:
        self.git("config", "merge.autoStash", "true")

        result = self.guard("merge", "HEAD")

        self.assert_blocked(result)

    def test_pull_uses_rebase_autostash_config_when_rebase_is_selected(self) -> None:
        self.git("config", "pull.rebase", "true")
        self.git("config", "rebase.autoStash", "true")

        result = self.guard("pull")

        self.assert_blocked(result)

    def test_pull_does_not_use_irrelevant_rebase_autostash_config(self) -> None:
        self.git("config", "pull.rebase", "false")
        self.git("config", "rebase.autoStash", "true")

        result = self.guard("pull")

        self.assert_not_blocked(result)

    def test_rebase_read_only_control_is_not_mistaken_for_autostash_start(self) -> None:
        self.git("config", "rebase.autoStash", "true")

        result = self.guard("rebase", "--show-current-patch")

        self.assert_not_blocked(result)

    def test_stash_list_and_show_are_read_only(self) -> None:
        (self.root / "README.md").write_text("fixture change\n", encoding="utf-8")
        self.git("stash", "push", "-m", "fixture")

        self.assertEqual(self.guard("stash", "list").returncode, 0)
        self.assertEqual(self.guard("stash", "show", "stash@{0}").returncode, 0)

    def test_mutating_stash_commands_are_hard_blocked(self) -> None:
        for args in (
            ("stash", "push"),
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

    def test_stash_cannot_be_unblocked_by_user_approval(self) -> None:
        (self.root / "README.md").write_text("must remain visible\n", encoding="utf-8")

        result = self.guard(
            "--user-approved=attempted override",
            "stash",
            "push",
            "-m",
            "must not run",
        )

        self.assert_blocked(result)
        self.assertIn("没有 break-glass", result.stderr)
        self.assertEqual(
            (self.root / "README.md").read_text(encoding="utf-8"),
            "must remain visible\n",
        )

    def test_git_alias_cannot_bypass_stash_prohibition(self) -> None:
        self.git("config", "alias.hide", "stash push -m hidden")
        (self.root / "README.md").write_text("must remain visible\n", encoding="utf-8")

        result = self.guard("hide")

        self.assert_blocked(result)
        self.assertIn("HARD-BLOCKED", result.stderr)
        self.assertEqual(
            (self.root / "README.md").read_text(encoding="utf-8"),
            "must remain visible\n",
        )

    def test_command_scoped_alias_cannot_bypass_stash_prohibition(self) -> None:
        (self.root / "README.md").write_text("must remain visible\n", encoding="utf-8")

        result = self.guard("-c", "alias.hide=stash push", "hide")

        self.assert_blocked(result)
        self.assertEqual(
            (self.root / "README.md").read_text(encoding="utf-8"),
            "must remain visible\n",
        )

    def test_safe_git_alias_is_not_blocked(self) -> None:
        self.git("config", "alias.overview", "log --format='%h %s' -1")

        result = self.guard("overview")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("base", result.stdout)

    def test_alias_cannot_shadow_builtin_rebase_policy(self) -> None:
        self.git("config", "alias.rebase", "status")
        self.git("config", "rebase.autoStash", "true")

        result = self.guard("rebase", "HEAD")

        self.assert_blocked(result)

    def test_ignored_alias_for_safe_builtin_does_not_create_false_positive(self) -> None:
        self.git("config", "alias.status", "stash push")

        result = self.guard("status", "--short")

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_shell_alias_requires_explicit_authorization(self) -> None:
        self.git("config", "alias.external", "!printf 'safe output\\n'")

        result = self.guard("external")

        self.assert_blocked(result)
        self.assertIn("无法静态判定", result.stderr)

    def test_authorized_shell_alias_is_forwarded(self) -> None:
        self.git("config", "alias.external", "!printf 'safe output\\n'")

        result = self.guard("--user-approved=the exact shell alias was reviewed", "external")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("safe output", result.stdout)

    def test_safe_reset_alias_is_classified_after_expansion(self) -> None:
        self.commit_file("new.txt", "content\n", "checkpoint")
        self.git("config", "alias.uncommit", "reset --soft HEAD~1")

        result = self.guard("uncommit")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "new.txt").read_text(encoding="utf-8"), "content\n")

    def test_clean_dry_run_is_allowed(self) -> None:
        (self.root / "untracked.txt").write_text("keep\n", encoding="utf-8")

        result = self.guard("clean", "-nd")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / "untracked.txt").exists())

    def test_clean_is_blocked_without_racy_effect_preflight(self) -> None:
        (self.root / "untracked.txt").write_text("keep\n", encoding="utf-8")

        result = self.guard("clean", "-fd")

        self.assert_blocked(result)
        self.assertTrue((self.root / "untracked.txt").exists())

    def test_clean_x_cannot_delete_ignored_agent_state(self) -> None:
        (self.root / ".gitignore").write_text("scratch/\n", encoding="utf-8")
        (self.root / "scratch").mkdir()
        (self.root / "scratch" / "notes.txt").write_text("keep\n", encoding="utf-8")

        result = self.guard("clean", "-fdx")

        self.assert_blocked(result)
        self.assertTrue((self.root / "scratch" / "notes.txt").exists())

    def test_clean_exclude_pattern_containing_n_is_not_mistaken_for_dry_run(self) -> None:
        (self.root / "untracked.txt").write_text("keep\n", encoding="utf-8")

        result = self.guard("clean", "-e-notes", "-fd")

        self.assert_blocked(result)
        self.assertTrue((self.root / "untracked.txt").exists())

    def test_reset_soft_is_allowed_and_preserves_file_and_index_state(self) -> None:
        self.commit_file("new.txt", "content\n", "checkpoint")

        result = self.guard("reset", "--soft", "HEAD~1")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "new.txt").read_text(encoding="utf-8"), "content\n")
        self.assertIn("new.txt", self.git("diff", "--cached", "--name-only").stdout)

    def test_mixed_reset_cannot_clear_another_agents_staging(self) -> None:
        (self.root / "README.md").write_text("staged work\n", encoding="utf-8")
        self.git("add", "README.md")

        result = self.guard("reset", "HEAD")

        self.assert_blocked(result)
        self.assertIn("README.md", self.git("diff", "--cached", "--name-only").stdout)

    def test_hard_reset_is_blocked_even_if_preflight_would_look_clean(self) -> None:
        result = self.guard("reset", "--hard", "HEAD")

        self.assert_blocked(result)

    def test_restore_staged_cannot_clear_another_agents_staging(self) -> None:
        (self.root / "README.md").write_text("staged work\n", encoding="utf-8")
        self.git("add", "README.md")

        result = self.guard("restore", "--staged", "README.md")

        self.assert_blocked(result)
        self.assertIn("README.md", self.git("diff", "--cached", "--name-only").stdout)

    def test_restore_without_a_path_is_left_to_native_git(self) -> None:
        result = self.guard("restore")

        self.assert_not_blocked(result)

    def test_restore_worktree_cannot_discard_another_agents_file_change(self) -> None:
        (self.root / "README.md").write_text("working change\n", encoding="utf-8")

        result = self.guard("restore", "README.md")

        self.assert_blocked(result)
        self.assertEqual(
            (self.root / "README.md").read_text(encoding="utf-8"),
            "working change\n",
        )

    def test_help_like_path_does_not_bypass_restore_guard(self) -> None:
        help_named_path = self.root / "-h"
        help_named_path.write_text("base\n", encoding="utf-8")
        self.git("add", "--", "-h")
        self.git("commit", "-m", "add help-like path")
        help_named_path.write_text("working change\n", encoding="utf-8")

        result = self.guard("restore", "--", "-h")

        self.assert_blocked(result)
        self.assertEqual(help_named_path.read_text(encoding="utf-8"), "working change\n")

    def test_help_like_pathspec_file_argument_does_not_bypass_restore_guard(self) -> None:
        (self.root / "--help").write_text("README.md\n", encoding="utf-8")
        (self.root / "README.md").write_text("working change\n", encoding="utf-8")

        result = self.guard("restore", "--pathspec-from-file", "--help")

        self.assert_blocked(result)
        self.assertEqual(
            (self.root / "README.md").read_text(encoding="utf-8"),
            "working change\n",
        )

    def test_checkout_of_current_branch_is_allowed(self) -> None:
        result = self.guard("checkout", self.current_branch)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_checkout_of_a_path_is_blocked_even_if_currently_clean(self) -> None:
        result = self.guard("checkout", "--", "README.md")

        self.assert_blocked(result)

    def test_checkout_pathspec_file_cannot_bypass_guard(self) -> None:
        pathspec = self.root / "paths.txt"
        pathspec.write_text("README.md\n", encoding="utf-8")

        result = self.guard("checkout", f"--pathspec-from-file={pathspec}")

        self.assert_blocked(result)

    def test_combined_force_checkout_flags_cannot_bypass_guard(self) -> None:
        (self.root / "README.md").write_text("working change\n", encoding="utf-8")

        result = self.guard("checkout", "-qf", self.current_branch)

        self.assert_blocked(result)
        self.assertEqual(
            (self.root / "README.md").read_text(encoding="utf-8"),
            "working change\n",
        )

    def test_creating_a_branch_without_switching_is_allowed(self) -> None:
        result = self.guard("branch", "safe-pointer")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.git("show-ref", "--verify", "refs/heads/safe-pointer")

    def test_deleting_a_branch_is_blocked(self) -> None:
        self.git("branch", "keep-this-branch")

        result = self.guard("branch", "-D", "keep-this-branch")

        self.assert_blocked(result)
        self.git("show-ref", "--verify", "refs/heads/keep-this-branch")

    def test_combined_branch_delete_flags_cannot_bypass_guard(self) -> None:
        self.git("branch", "keep-this-remote-branch")

        result = self.guard("branch", "-dr", "keep-this-remote-branch")

        self.assert_blocked(result)
        self.git("show-ref", "--verify", "refs/heads/keep-this-remote-branch")

    def test_git_apply_is_allowed_as_a_context_checked_edit(self) -> None:
        patch = self.root / "change.patch"
        patch.write_text(
            "--- a/README.md\n"
            "+++ b/README.md\n"
            "@@ -1 +1 @@\n"
            "-base\n"
            "+patched\n",
            encoding="utf-8",
        )

        result = self.guard("apply", str(patch))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "README.md").read_text(encoding="utf-8"), "patched\n")

    def test_git_apply_cannot_write_outside_worktree(self) -> None:
        patch = self.root / "outside.patch"
        patch.write_text(
            "--- /dev/null\n"
            "+++ b/../outside.txt\n"
            "@@ -0,0 +1 @@\n"
            "+outside\n",
            encoding="utf-8",
        )

        result = self.guard("apply", "--unsafe-paths", str(patch))

        self.assert_blocked(result)
        self.assertFalse((self.root.parent / "outside.txt").exists())

    def test_git_apply_check_with_unsafe_paths_is_read_only(self) -> None:
        patch = self.root / "outside.patch"
        patch.write_text(
            "--- /dev/null\n"
            "+++ b/../outside.txt\n"
            "@@ -0,0 +1 @@\n"
            "+outside\n",
            encoding="utf-8",
        )

        result = self.guard("apply", "--check", "--unsafe-paths", str(patch))

        self.assert_not_blocked(result)
        self.assertFalse((self.root.parent / "outside.txt").exists())

    def test_force_push_and_remote_deletion_are_blocked(self) -> None:
        for args in (
            ("push", "--force", "origin", self.current_branch),
            ("push", "--force-with-lease", "origin", self.current_branch),
            ("push", "origin", f"+{self.current_branch}"),
            ("push", "origin", f":{self.current_branch}"),
            ("push", "--delete", "origin", self.current_branch),
            ("push", "--mirror", "origin"),
            ("push", "--prune", "origin"),
        ):
            with self.subTest(args=args):
                self.assert_blocked(self.guard(*args))

    def test_force_push_dry_run_is_not_blocked(self) -> None:
        result = self.guard("push", "--dry-run", "--force", "origin", self.current_branch)

        self.assert_not_blocked(result)

    def test_later_no_force_option_avoids_false_positive(self) -> None:
        result = self.guard(
            "push",
            "--force",
            "--no-force",
            "origin",
            self.current_branch,
        )

        self.assert_not_blocked(result)

    def test_configured_force_push_refspec_is_blocked(self) -> None:
        self.git("remote", "add", "origin", str(self.root))
        self.git(
            "config",
            "remote.origin.push",
            f"+refs/heads/{self.current_branch}:refs/heads/{self.current_branch}",
        )

        result = self.guard("push", "origin")

        self.assert_blocked(result)

    def test_configured_mirror_push_is_blocked(self) -> None:
        self.git("remote", "add", "origin", str(self.root))
        self.git("config", "remote.origin.mirror", "true")

        result = self.guard("push", "origin")

        self.assert_blocked(result)

    def test_sequencer_actions_that_discard_work_are_blocked(self) -> None:
        for command, action in (
            ("rebase", "--abort"),
            ("rebase", "--skip"),
            ("rebase", "--quit"),
            ("merge", "--abort"),
            ("merge", "--quit"),
            ("cherry-pick", "--abort"),
            ("cherry-pick", "--skip"),
            ("cherry-pick", "--quit"),
            ("am", "--abort"),
            ("am", "--skip"),
            ("am", "--quit"),
        ):
            with self.subTest(command=command, action=action):
                self.assert_blocked(self.guard(command, action))

    def test_rebase_continue_is_not_blocked(self) -> None:
        result = self.guard("rebase", "--continue")

        self.assert_not_blocked(result)

    def test_revert_is_not_blocked(self) -> None:
        self.commit_file("reverted.txt", "content\n", "commit to revert")

        result = self.guard("revert", "--no-edit", "HEAD")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / "reverted.txt").exists())

    def test_revert_abort_is_not_blocked(self) -> None:
        self.commit_file("reverted.txt", "line\n", "add line")
        (self.root / "reverted.txt").write_text("changed\n", encoding="utf-8")
        self.git("add", "reverted.txt")
        self.git("commit", "-m", "change line")

        start = self.guard("revert", "--no-edit", "HEAD~1")
        self.assert_not_blocked(start)
        self.assertNotEqual(start.returncode, 0, start.stderr)

        abort = self.guard("revert", "--abort")

        self.assertEqual(abort.returncode, 0, abort.stderr)
        self.assertEqual((self.root / "reverted.txt").read_text(encoding="utf-8"), "changed\n")

    def test_revert_sequencer_actions_reach_git_without_state(self) -> None:
        for action in ("--abort", "--skip", "--quit"):
            with self.subTest(action=action):
                result = self.guard("revert", action)

                self.assert_not_blocked(result)

    def test_forced_rm_cannot_discard_a_dirty_file(self) -> None:
        (self.root / "README.md").write_text("dirty work\n", encoding="utf-8")

        result = self.guard("rm", "-f", "README.md")

        self.assert_blocked(result)
        self.assertTrue((self.root / "README.md").exists())

    def test_forced_rm_dry_run_is_allowed(self) -> None:
        result = self.guard("rm", "--dry-run", "--force", "README.md")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / "README.md").exists())

    def test_plain_rm_uses_git_native_dirty_file_protection(self) -> None:
        result = self.guard("rm", "README.md")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / "README.md").exists())

    def test_forced_mv_cannot_overwrite_another_agents_destination(self) -> None:
        self.commit_file("source.txt", "source\n", "add source")
        (self.root / "target.txt").write_text("destination work\n", encoding="utf-8")

        result = self.guard("mv", "-f", "source.txt", "target.txt")

        self.assert_blocked(result)
        self.assertEqual((self.root / "source.txt").read_text(encoding="utf-8"), "source\n")
        self.assertEqual(
            (self.root / "target.txt").read_text(encoding="utf-8"),
            "destination work\n",
        )

    def test_forced_mv_dry_run_is_allowed(self) -> None:
        self.commit_file("source.txt", "source\n", "add source")
        (self.root / "target.txt").write_text("destination work\n", encoding="utf-8")

        result = self.guard("mv", "--dry-run", "--force", "source.txt", "target.txt")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / "source.txt").exists())
        self.assertEqual(
            (self.root / "target.txt").read_text(encoding="utf-8"),
            "destination work\n",
        )

    def test_prune_dry_run_is_allowed_but_real_prune_is_blocked(self) -> None:
        self.assertEqual(self.guard("prune", "--dry-run").returncode, 0)
        self.assert_blocked(self.guard("prune"))

    def test_explicit_gc_prune_is_blocked_but_gc_auto_is_allowed(self) -> None:
        self.assert_blocked(self.guard("gc", "--prune=now"))
        self.assertEqual(self.guard("gc", "--auto").returncode, 0)

    def test_gc_prune_never_is_allowed(self) -> None:
        result = self.guard("gc", "--prune=never")

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reflog_expire_dry_run_is_allowed(self) -> None:
        result = self.guard("reflog", "expire", "--dry-run", "--all")

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_read_only_bisect_and_sparse_checkout_commands_are_not_blocked(self) -> None:
        self.assert_not_blocked(self.guard("bisect", "log"))
        self.assert_not_blocked(self.guard("sparse-checkout", "list"))


if __name__ == "__main__":
    unittest.main()
