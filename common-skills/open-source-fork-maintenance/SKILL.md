---
name: open-source-fork-maintenance
description: Maintain a non-maintainer public fork through its local aggregate workspace.
disable-model-invocation: true
triggers:
  - user
---

# Open-source fork maintenance

This is a process skill. Invoke it explicitly as `$open-source-fork-maintenance` when maintaining a public upstream fork whose operator cannot merge changes upstream. It establishes and operates a local `local/aggregate` integration branch without treating it as an upstream contribution branch.

## Boundary

Use this skill only after confirming that the repository is a public fork or upstream clone and that the operator is not an upstream maintainer. Upstream maintainers should use the project's normal contribution and release workflow instead.

The project owns its branch registry, its feedback records, its verification commands, and any local service deployment. The skill owns the repeatable maintenance model:

- the main checkout stays on `local/aggregate` for integration and experience;
- every product change lives on its own `feature/*` or `fix/*` branch and worktree;
- a source branch is verified after relevant project checks pass in its worktree and `$autoreview` closeout there reports no accepted/actionable findings;
- the aggregate receives verified source commits with `git cherry-pick -x`;
- a committed project manifest records each source commit, aggregate commit, and upstream feedback issue.

The personal fork is the handoff channel: after verified packaging, push each completed source branch and `local/aggregate` to that fork with ordinary fast-forward pushes. Those published aggregate commits are reusable source snapshots for another environment, never upstream contribution branches.

Read [references/setup.md](references/setup.md) before initializing a repository. Initialization creates branches, project files, and a project-local skill link, so perform it only after the user explicitly authorizes setup.

For an already initialized fork, read [references/maintenance.md](references/maintenance.md). Run the linked `scripts/local-aggregate-status.mjs` from the project root after fetching the configured upstream. It reports source-branch changes, unregistered local feature/fix branches, upstream changes, stable releases when configured, and the state of every registered upstream feedback issue.

Do not rebase, rebuild the aggregate, update a local service, push rewritten history, or discard a worktree merely because the report found work. Present the resulting maintenance choices to the user first. All local `feature/*` and `fix/*` worktrees are default candidates for aggregation once they are committed, verified, and registered; do not ask whether to include them.

## Completion

An aggregation is complete only when the project manifest and its `AGENTS.md` overview agree on every included branch, each aggregate commit retains its `-x` source reference, relevant verification has passed from the aggregate checkout, any requested local deployment has passed its project-specific health check, and the completed source and aggregate refs match their personal-fork refs.
