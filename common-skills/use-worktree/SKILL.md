---
name: use-worktree
description: Create one isolated Git worktree for the current task and clean it up after delivery.
disable-model-invocation: true
---

# Use Worktree

Use this skill only when the user explicitly invokes it. The invocation authorizes creating, managing, and cleaning up one worktree and branch owned by the current task.

## Start

1. Preflight the shared workspace. Check the current branch, status, and active worktrees:
   ```bash
   git status --short && git branch --show-current && git worktree list
   ```
   Preserve unrelated work and proceed when the current task has not yet altered the shared workspace.
2. Resolve the repository root and register the worktrees exclusion once:
   ```bash
   git rev-parse --show-toplevel
   grep -qxF '/.worktrees/' .git/info/exclude 2>/dev/null || echo '/.worktrees/' >> .git/info/exclude
   ```
3. Fetch the clean base commit (e.g. `origin/main`):
   ```bash
   git fetch origin main
   ```
4. Create the isolated task worktree under `.worktrees/<task-name>`. The git wrapper forwards `worktree add` transparently:
   ```bash
   git worktree add -b <task-branch> .worktrees/<task-name> origin/main
   ```
5. Verify the new worktree is registered and clean:
   ```bash
   git worktree list
   git -C .worktrees/<task-name> status --short
   ```

## Work And Deliver

1. Perform all edits, tests, commits, and pushes inside `.worktrees/<task-name>`:
   ```bash
   cd .worktrees/<task-name>
   ```
   (In environments supporting workspace directory switching like `bb`, call `update_environment_directory` with the absolute path.)
2. Do not touch files in the parent checkout. Never run `git stash` (strictly blocked by the git wrapper in all worktrees).

## Clean Up

1. After delivery, confirm the worktree is clean and its `HEAD` is durably stored on the remote:
   ```bash
   git -C .worktrees/<task-name> status --short
   git branch -r --contains HEAD
   ```
2. The git wrapper blocks `worktree remove` and `branch -d` by default (exit 77). Because invoking this skill already authorized managing this task's worktree, use `--user-approved` directly without asking the user again:
   ```bash
   git --user-approved='clean delivered task worktree' worktree remove .worktrees/<task-name>
   git --user-approved='clean delivered task branch' branch -d <task-branch>
   rmdir .worktrees 2>/dev/null || true
   ```
3. If the worktree is dirty, uncommitted, or not durably pushed, keep it intact and report the exact path and status instead of forcing cleanup.
