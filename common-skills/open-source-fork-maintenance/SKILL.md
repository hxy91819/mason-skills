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
- every product change lives on its own first-tier `feature/*` or `fix/*` source and keeps an explicit ordered patch selection;
- related first-tier sources may be combined in a second-tier domain branch that owns stable-release adaptation, while dormant source refs remain unchanged;
- low-coupling patches may continue directly to the aggregate;
- a source branch is verified after relevant project checks pass in its worktree and `$autoreview` closeout there reports no accepted/actionable findings;
- a frozen train locks the stable tag and SHA, selected source patches, domain mappings, shared dependencies, direct patches, and verification inputs;
- the aggregate receives the locked train without importing old aggregate ancestry;
- a committed project manifest records source ownership and mapping alongside local specifications, actual upstream feedback, related context, and the reason for retaining each change.

The personal fork is the handoff channel: after verified packaging, push completed source and domain branches, immutable train refs, and `local/aggregate` to that fork. Rebased moving branches may use `--force-with-lease`; invoking this skill provides standing authorization for that personal-fork history rewrite, so do not request separate approval. Immutable refs are create-only. Those published aggregate commits are reusable source snapshots for another environment, never upstream contribution branches.

Registered issues on the personal fork are local specification records, not the feedback loop itself. The open-source feedback loop happens on the upstream repository: a registered change that is meaningful to upstream users should eventually be filed as an upstream issue there. Deployment-only repairs and changes the owner classifies as personal preference stay fork-local. Filing an issue on the upstream repository always requires the user's explicit confirmation first — present the proposed issue content and wait for the decision; record a fork-only disposition in the project's feedback record.

Use the version 4 registry described in [references/setup.md](references/setup.md) for two-tier maintenance. Version 3 remains supported for direct-only repositories. A branch may have no issue yet: record `needs-feedback` or `internal` with its reason instead of filling an upstream slot with a fork specification or a loosely related issue. Existing version 2 registries remain readable, but their issue references are unclassified until audited.

Read [references/setup.md](references/setup.md) before initializing a repository. Initialization creates branches, project files, and a project-local skill link, so perform it only after the user explicitly authorizes setup.

For an already initialized fork, read [references/maintenance.md](references/maintenance.md). Run the linked `scripts/local-aggregate-status.mjs` from the project root after fetching the configured upstream. It reports source-branch changes, unregistered local feature/fix branches, upstream changes, stable releases when configured, the recommended integration ref, and the state of every registered upstream feedback issue.

When the registry has a `stableTagPattern`, the default domain and train baseline is the latest matching tag reachable from the upstream ref. Commits on that upstream ref after the tag are unreleased trunk: report them, and wait for an explicit choice before tracking them. The upstream ref itself is the integration target only when the upstream publishes no release tags; setup configures the pattern otherwise.

Do not rebase, rebuild the aggregate, update a local service, or discard a worktree merely because the report found work. Present the resulting maintenance choices to the user first. Once the user chooses a domain upgrade or rebuild, publish completed source, domain, train, and aggregate refs to the configured personal fork without another approval prompt. The final replacement of a running local BB service remains a separate explicit authorization boundary owned by the project's deployment workflow. Registered first-tier work remains a default candidate, but a frozen train is the authority for one release and may intentionally retain, defer, or retire individual patches.

## Completion

An aggregation is complete only when the registry, frozen train, and generated overview agree; every selected patch and adaptation has an explicit mapping; relevant domain and candidate verification has passed; a real package credential names the final source SHA, train digest, toolchain, protocol, platform, database compatibility, and artifact digest; immutable source refs and completed moving refs match the personal fork; and deployment state remains unchanged unless the project deployment workflow separately completed it.
