---
name: worktree-cleanup
description: Explicitly audit and retire clean Git worktrees whose HEAD is durably stored on GitHub, using review-bound approval tokens and .local backups.
disable-model-invocation: true
---

# Worktree Cleanup

Run this workflow only when the user explicitly invokes `$worktree-cleanup`. It performs repository-wide discovery and can remove worktrees. Always audit first, present the exact candidates, and apply only the approval tokens the user selects.

## Requirements

Require Git, Python 3.10+, GitHub CLI, and an authenticated `gh` session with read access to the repository's pull requests. Run from a repository checkout or pass `--repo <path>`.

## Audit

1. Check the current branch, `git status --short`, and `git worktree list`. Preserve concurrent and unrelated work.
2. Create a new temporary report path outside the repository and run the helper in dry-run mode:

   ```bash
   python3 <skill-dir>/scripts/cleanup_worktrees.py \
     --repo <repo-path> \
     --dry-run \
     --json \
     --write-approval-report <temporary-report.json>
   ```

3. Review every candidate and skip reason. A candidate is eligible only when all of these hold:
   - Git status is known and clean, including untracked files.
   - The worktree is neither locked nor marked prunable.
   - It is not the primary checkout or the checkout selected by `--repo`.
   - Its exact HEAD is contained in the remote head of a merged or closed GitHub pull request; or no pull request exists, the worktree is at least 24 hours old by default, and its HEAD is either the tip of a GitHub remote branch or contained in the remote default branch.
4. Review `ignored.discarded_sample` and `ignored.discarded_count` for every candidate. These count ignored path roots, not files or bytes; one listed directory may contain substantial data. `.local` is backed up; all other ignored files are deliberately discarded if that candidate is approved.
5. Tell the user the exact paths, whether each path is managed or external, remote durability proof, ignored data impact, backup base directory, and all retained paths with their reasons. Ask once whether to remove all listed candidates or a named subset; do not make the user copy or re-approve token strings. Worktrees outside `.worktrees/` follow the same eligibility rules.

Completion criterion: every listed worktree has a resolved action or a conservative skip reason, and no state has changed.

## Apply

After the user approves every candidate in the saved dry-run report, apply it directly:

```bash
python3 <skill-dir>/scripts/cleanup_worktrees.py \
  --repo <repo-path> \
  --apply \
  --approve-report <temporary-report.json>
```

For a subset, pass the selected candidates' `--approve <token>` values internally; users should approve paths, not transcribe tokens. The helper rediscovers all worktrees. Approval remains valid when a remote default branch or other durability witness advances, provided the exact worktree path, branch, HEAD, and local data state are unchanged and a valid remote durability proof still exists. Newly eligible worktrees are never added to an old report.

Changed or no-longer-eligible approvals are rejected individually while other approved candidates continue. Backup, authorization, or removal failure also affects only that candidate. Report every rejected or failed candidate; rerun dry-run only if the user wants to retry those candidates or include newly eligible ones.

For each approved target, the helper copies `.local` when present, writes `metadata.json`, removes the clean worktree without `--force`, and updates the batch `manifest.json`. Other ignored files are not backed up. Dry-run reports the backup base directory; apply creates the timestamped batch beneath it. The default layout is:

```text
${XDG_STATE_HOME:-~/.local/state}/worktree-cleanup/<repo-name>-<id>/<timestamp>/
```

Use `--backup-root <path>` when the user requests another durable location. A failed removal remains recorded in the manifest and causes a nonzero exit.

## Guardrails

- Never remove a dirty worktree. This skill has no force-removal mode.
- Keep targets whose pull request or remote durability lookup is ambiguous or failed.
- Keep worktrees for open pull requests.
- Keep locked and prunable worktrees for explicit operator handling.
- Never remove the primary checkout or the checkout selected by `--repo`.
- Keep the backup root outside every cleanup target; the helper rejects unsafe paths before writing.
- Continue independent candidates after a stale approval, backup failure, state-validation failure, authorization denial, or removal failure.
- Treat branch deletion as a separate operation outside this skill.
- Remote proof is point-in-time evidence, not a promise that a remote ref will exist forever. The helper never deletes the local branch, so removing a worktree does not delete its commit reference.

## Output

Use `--json` for machine-readable reporting. On completion, report removed paths, retained paths and reasons, backup location, failures, and the final worktree count.
