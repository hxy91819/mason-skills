---
name: open-source-fork-maintenance
description: Initialize, migrate, and maintain public forks with feature sources, optional domains, and frozen integration trains.
disable-model-invocation: true
triggers:
  - user
---

# Open-source fork maintenance

Invoke explicitly as `$open-source-fork-maintenance` for a public upstream fork whose operator cannot merge changes upstream. Use the same maintenance model across projects: independent feature/fix sources, optional domain integration, and a frozen train for each aggregate release. Small forks can remain direct-only; creating a domain is a response to recurring shared compatibility work, not an initialization requirement.

## Boundary

Use this skill only after confirming that the repository is a public fork or upstream clone and that the operator is not an upstream maintainer. Upstream maintainers should use the project's normal contribution and release workflow instead.

The project owns its registry, upstream release channel, feedback records, verification/build commands, and deployment policy. The skill owns the repeatable maintenance model:

- after setup or migration cutover, the main checkout stays on `local/aggregate` for integration and experience;
- every product change lives on its own first-tier `feature/*` or `fix/*` source and keeps an explicit ordered patch selection;
- related first-tier sources may be combined in a second-tier domain branch that owns stable-release adaptation, while dormant source refs remain unchanged;
- low-coupling patches may continue directly to the aggregate;
- a source branch is verified after relevant project checks pass in its worktree and `$autoreview` closeout there reports no accepted/actionable findings;
- a frozen train locks the stable tag and SHA, selected source patches, domain mappings, shared dependencies, direct patches, and verification inputs;
- the aggregate receives the locked train without importing old aggregate ancestry, including explicitly selected fork-maintenance files needed to reconstruct the complete tree;
- a committed project manifest records source ownership and mapping alongside local specifications, actual upstream feedback, related context, and the reason for retaining each change.

The personal fork is the handoff channel. Publish verified source/domain work as it completes; publish a train's candidate and completed `local/aggregate` according to the selected delivery stage. Rebuilt moving refs may use explicit-lease `--force-with-lease`; this maintenance flow provides standing authorization for that personal-fork rewrite. Immutable refs are create-only. Published aggregate commits are reusable source snapshots for another environment, never upstream contribution branches.

Registered issues on the personal fork are local specification records, not the feedback loop itself. The open-source feedback loop happens on the upstream repository: a registered change that is meaningful to upstream users should eventually be filed as an upstream issue there. Deployment-only repairs and changes the owner classifies as personal preference stay fork-local. Filing an issue on the upstream repository always requires the user's explicit confirmation first — present the proposed issue content and wait for the decision; record a fork-only disposition in the project's feedback record.

## Choose the workflow

| Project state | Read next | Result |
| --- | --- | --- |
| New fork, no local product history to preserve | [New-project setup](references/setup.md) | Baseline, project rules, v4 registry; start direct-only. |
| Existing fork, ad hoc aggregate, or v2/v3 registry | [Gradual migration](references/migration.md) | Preserve the current release, inventory patches, pilot a useful domain, and prove complete reconstruction. |
| Initialized fork, feature work or upstream update | [Maintenance](references/maintenance.md) | Update owned patches/domains, freeze and verify the selected train. |
| Editing a registry or train in any workflow | [Record contract](references/registry.md) | Exact source ownership, dependency closure, mappings, and historical evidence. |

Initialization changes branches, project files, and a project-local skill link. A request to initialize or migrate authorizes the described local work; a request only to assess a project does not. Continue an already selected setup, migration, upgrade, or packaging workflow without repeatedly asking for the same decision. A status report alone does not authorize a rebuild, deletion, or deployment.

Use v4 for new projects, including direct-only ones. Existing v3 direct maintenance can continue during migration; v2 remains readable with unclassified issue references. A missing upstream report is `needs-feedback`; local maintenance can be `internal`, with its reason. Neither needs a placeholder issue.

The default upgrade target is the latest tag matching the project's release channel and reachable from its upstream tracking ref. Report subsequent trunk commits as unreleased debt; use trunk only when explicitly selected or the upstream publishes no release tags. Structural migration starts on the existing baseline, then upgrades separately. A frozen train decides which registered patches are retained, deferred, or retired for that release.

## Domain ownership

Group features that repeatedly share compatibility changes, contracts, or ordered data migrations. Directory names alone do not establish a domain. Give each feature and adaptation one owner; model shared prerequisites as explicit dependencies and keep the dependency graph acyclic. If two domains repeatedly require the same integration fixes, move the shared contract into an owned dependency or reconsider the boundary.

First-tier sources preserve contribution-sized intent. Domains absorb upstream-version adaptation. Active feature development may still need a refreshed source baseline; dormant sources do not rebase on every upstream release. Contribution extraction selects one feature, its dependencies, and relevant adaptations. It can require a final target-upstream adjustment and review; two tiers reduce repeated integration work, not eliminate it.

## Project-specific verification

Use the project's commands and supported environments. Node is needed by the bundled status/compose helpers, not prescribed as the project's build runtime; GitHub feedback lookup uses `gh`. Other forge integrations need an equivalent project-owned feedback lookup. Resource isolation, ABI/protocol checks, and service replacement belong to projects that use them.

Give compatibility code an explicit owner and version/support range where it is needed. For persistent databases, test actual historical schema and migration-ledger fixtures with representative non-sensitive data, including upgrades from shipped fork releases; check semantic outcomes, preserved data, and repeat runs. A fresh database alone cannot demonstrate upgrade safety. For wire protocols, test the supported old/new peer combinations; a shared compile does not prove interoperability. Record applicable compatibility limits in release evidence. Projects without these contracts need no empty compatibility subsystem.

The read-only status helper reports registered source/domain drift, local unregistered branches, release movement, and upstream feedback. Git manifests and compose results preserve selection/provenance; post-build receipts preserve verification and artifacts. This skill has no independent run-history database and the status helper does not inspect deployment health or prove historical builds passed.

## Completion

Report completion at the requested stage: setup, migrated source, verified candidate, packaged artifacts, published refs, or deployed service. Do not promote one stage into another.

A source reconstruction has complete ownership/mappings, committed registry/train inputs, matching full-tree evidence for the intended snapshot, relevant verification, and durable personal-fork refs when publication is in scope. Packaging additionally requires a successful real build and a receipt binding final source SHA, train digest, toolchain/configuration, artifact digests, and applicable compatibility evidence. A source-only project records its actual distribution/verification result. Deployment follows the project's existing authorization and service workflow; this skill neither invents a deployment requirement nor overrides one.
