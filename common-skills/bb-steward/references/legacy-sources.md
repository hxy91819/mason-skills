# Legacy sources: Git-ref workbooks and historical running logs

Only two kinds of old projects read this: those whose workbook still lives in the project repository with a remote
branch as the source of truth, and those whose requirement ledger continues an existing Markdown historical running
log. Local offline workbooks (`.local/steward/`) are not affected.

## Git-ref mode

When the workbook's source of truth is a remote branch and the main worktree is not on that branch, pass `--ref` at
registration:

```bash
python3 scripts/steward_watch.py register --workbook <workbook path> --ref origin/<branch> [--name <short name>]
```

- The plugin and watchdog keep the original thread and host ownership, and Git's remote/branch is also part of
  same-goal matching: a new thread taking over a Git goal must pass the same `--ref` explicitly; when the same thread
  re-registers without it, the original ref is kept and the binding is not released.
- Every time the Git entry is actively opened or refreshed, the remote is checked first and a SHA pinned; the
  workbook, ledgers and relative links are read at that same SHA, usable even with no file on disk. An unreachable
  remote, deleted ref or timeout is reported explicitly as unverifiable, never falling back to an old local ref.
  Only "refresh remote document" re-checks the remote.
- The body is shown read-only in the plugin; no persistent workbook copy is generated. Large documents and
  directories are paginated; when not fully read, this is marked clearly with a continue button, and continuation
  pages stay pinned to the same SHA. Directory links in the history index (e.g. `2026-10/`) are listed by the plugin,
  then navigate to the original shard.
- When reading via the plugin CLI/RPC, `document` returns the first page by default plus `next: {path, sha, offset}`
  or `null`. Continuation parameters, offset units and output limits are in the plugin's own steward skill; when you
  need to diagnose or export the body, load it by name, continue with the `next` actually returned, and never treat a
  partial body as complete.
- Deterministic checks: `python3 scripts/steward_workbook.py --mode check --repo <absolute repo path> --ref origin/<branch> --file <repo-relative path>`;
  `ledger-check` supports the same. When an operation has already pinned a SHA, use `--revision <40-char SHA>` instead
  of `--ref`; the output snapshot names that version and does not claim to be latest. Git sources do not support
  `should-commit`; commit decisions apply to the locally edited workbook.
- When `init` finds the target empty and the project has `docs/steward/`, it copies the old files and keeps the
  original copies; follow its prompts to delete the old copies via MR and update the routing line in the project
  `AGENTS.md`.

## Historical running log

When an existing Markdown historical running log is kept with the user's confirmation, the workbook header is marked
exactly `[要求帐（历史流水账）](relative-index.md)` (the label is a literal the script matches), keeping the old ledger
and index links, not rewriting them into the five-column table or inventing status statistics. The platform can view
the index and its relative ledger links, and marks standard statistics as not applicable.

- `ledger-check --ledger-kind history` returns not-applicable with no standard statistics; standard ledgers still use
  the default validation.
- The watchdog does not check historical running logs for stale recording, and takeover gives no `ledger_gap`;
  takeover proceeds as "without `ledger_gap`".
- A header without a ledger entry is a gap to fill; passing the structure check does not mean the entry is present.
