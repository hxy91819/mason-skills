---
name: worktree-cleanup
description: Audit Git worktrees, back up per-worktree .local data, and retire worktrees whose GitHub pull requests are merged or closed.
---

# Worktree Cleanup

Run this workflow only when the user explicitly invokes `$worktree-cleanup`. It performs repository-wide discovery and can remove worktrees, so begin with a report and keep every uncertain target.

## Requirements

Require Git, Python 3.10+, GitHub CLI, and an authenticated `gh` session with read access to the repository's pull requests. Run from a repository checkout or pass `--repo <path>`.

## Audit

1. Check the current branch, `git status --short`, and `git worktree list`. Preserve concurrent and unrelated work.
2. Run the helper in dry-run mode:

   ```bash
   python3 <skill-dir>/scripts/cleanup_worktrees.py --repo <repo-path> --dry-run
   ```

3. Review every candidate and skip reason. A candidate is eligible only when its pull request is merged or closed, its status is known and clean, it is not the checkout selected by `--repo`, and it lives under the primary checkout's `.worktrees/` directory.
4. Tell the user which exact worktrees are eligible, where backups will go, and which targets remain unresolved or dirty.

Completion criterion: every listed worktree has a resolved action or a conservative skip reason, and no state has changed.

## Apply

After the dry run, apply the same default scope:

```bash
python3 <skill-dir>/scripts/cleanup_worktrees.py --repo <repo-path> --apply
```

For each eligible target, the helper copies `.local` when present, writes `metadata.json`, removes the clean worktree without `--force`, and updates the batch `manifest.json`. The default backup root is the user's state directory:

```text
${XDG_STATE_HOME:-~/.local/state}/worktree-cleanup/<repo-name>-<id>/<timestamp>/
```

Use `--backup-root <path>` when the user requests another durable location. A failed removal remains recorded in the manifest and causes a nonzero exit.

## Guardrails

- Include worktrees outside the primary checkout's `.worktrees/` directory only after the user explicitly authorizes `--include-external` and the exact targets are reviewed.
- Use `--force-remove-dirty` only after the user explicitly authorizes destruction of the named uncommitted changes. The helper still backs up only `.local`; it is not a general worktree backup.
- Keep targets whose pull request lookup is missing, ambiguous, or failed.
- Keep worktrees for open pull requests.
- Never remove the checkout selected by `--repo`.
- Keep the backup root outside every cleanup target; the helper rejects unsafe paths before writing.
- Treat branch deletion as a separate operation outside this skill.

## Output

Use `--json` for machine-readable reporting. On completion, report removed paths, retained paths and reasons, backup location, failures, and the final worktree count.
