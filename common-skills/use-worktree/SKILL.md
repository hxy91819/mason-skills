---
name: use-worktree
description: Create one isolated Git worktree for the current task and clean it up after delivery.
disable-model-invocation: true
---

# Use Worktree

Use this skill only when the user explicitly invokes it. The invocation authorizes creating, managing, and cleaning up one worktree and branch owned by the current task.

## Location Convention

- Path: `<repo-root>/.worktrees/<task-name>`
- Exclude: Ensure `/.worktrees/` is recorded in `.git/info/exclude` once so task worktrees remain ignored.

## Workflow

1. **Start**: Check current workspace status. Create the task branch and worktree under `.worktrees/<task-name>` from the target remote default branch (e.g. `origin/main`).
2. **Work**: Perform all edits, tests, commits, and pushes inside the task worktree. Never use `git stash`.
3. **Clean Up**: Once the work is merged into the target branch or a PR/MR is submitted with its commits pushed to remote, clean up:
   - Remove the task worktree and delete its local branch. If blocked by the git wrapper, use `--user-approved='clean delivered worktree'` under this invocation's existing authorization without asking the user again.
   - Never use `--force`. If the worktree is dirty or commits are not durably pushed, keep it intact and report the path.
