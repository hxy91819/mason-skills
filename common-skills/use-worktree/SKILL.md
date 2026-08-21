---
name: use-worktree
description: Create one isolated Git worktree for the current task and clean it up after delivery.
disable-model-invocation: true
---

# Use Worktree

Use this skill only when the user explicitly invokes it. The invocation authorizes creating and managing one worktree and branch owned by the current task.

## Start

1. Check the current branch, `git status --short`, and `git worktree list`. Preserve unrelated work and continue when the current task has not yet modified the shared workspace.
2. Resolve the repository root and create the task worktree at `<repo-root>/.worktrees/<task-name>`. Use a short, recognizable task name and a branch name consistent with the repository.
3. Add `/.worktrees/` to the repository's `.git/info/exclude` if it is not already present. Preserve the file's existing contents and add the entry only once.
4. Select a clean base commit. By default, fetch and use the target remote's default branch, such as `upstream/main` or `origin/main`; when no remote exists, use the local default branch. Use another branch only when the user explicitly requests it or the repository or task requires it.
5. Create the task branch and worktree from that exact base. Before editing, confirm the path and branch with `git worktree list` and require `git status --short` in the new worktree to be empty.

## Work And Deliver

Perform all task edits, tests, commits, pushes, and requested PR/MR operations inside the task worktree. Do not alter another worktree or include unrelated changes.

## Clean Up

After delivery, check the task worktree status. When a PR/MR was requested, also confirm that it exists and its remote branch contains the worktree's `HEAD`.

Remove only the task-owned worktree without `--force`. Delete its local branch only after its commit is verified on the remote, then remove the `.worktrees` directory only if it is empty. Leave `.git/info/exclude` configured for future use.

If the worktree is dirty, its commit is not durably stored, or ownership is unclear, keep it and report the exact path and reason instead of forcing cleanup.
