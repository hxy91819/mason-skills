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

The personal fork is the handoff channel: after verified packaging, push each completed source branch and `local/aggregate` to that fork. Rebased maintenance branches may use `--force-with-lease`; invoking this skill provides standing authorization for that personal-fork history rewrite, so do not request separate approval. Those published aggregate commits are reusable source snapshots for another environment, never upstream contribution branches.

Registered issues on the personal fork are local specification records, not the feedback loop itself. The open-source feedback loop happens on the upstream repository: a registered change that is meaningful to upstream users should eventually be filed as an upstream issue there. Deployment-only repairs and changes the owner classifies as personal preference stay fork-local. Filing an issue on the upstream repository always requires the user's explicit confirmation first — present the proposed issue content and wait for the decision; record a fork-only disposition in the project's feedback record.

Read [references/setup.md](references/setup.md) before initializing a repository. Initialization creates branches, project files, and a project-local skill link, so perform it only after the user explicitly authorizes setup.

For an already initialized fork, read [references/maintenance.md](references/maintenance.md). Run the linked `scripts/local-aggregate-status.mjs` from the project root after fetching the configured upstream. It reports source-branch changes, unregistered local feature/fix branches, upstream changes, stable releases when configured, the recommended integration ref, and the state of every registered upstream feedback issue.

When the registry has a `stableTagPattern`, the default rebase and rebuild target is the latest matching tag reachable from the upstream ref. Commits on that upstream ref after the tag are unreleased trunk: report them, and wait for an explicit choice before tracking them. When no pattern is configured, the upstream ref itself is the integration target.

Do not rebase, rebuild the aggregate, update a local service, or discard a worktree merely because the report found work. Present the resulting maintenance choices to the user first. Once the user chooses a rebase or rebuild, replace the aggregate root and publish rewritten refs to the configured personal fork without another approval prompt. The final replacement of a running local BB service remains a separate explicit authorization boundary owned by the project's deployment workflow. All local `feature/*` and `fix/*` worktrees are default candidates for aggregation once they are committed, verified, and registered; do not ask whether to include them.

## Completion

An aggregation is complete only when the project manifest and its `AGENTS.md` overview agree on every included branch, each aggregate commit retains its `-x` source reference, relevant verification has passed from the aggregate checkout, any requested local deployment has passed its project-specific health check, and the completed source and aggregate refs match their personal-fork refs.
