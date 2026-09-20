# Maintain the aggregate

## Audit and decide

Fetch the registry's upstream ref, then run the linked status helper:

```bash
git fetch --prune --tags <upstream-remote>
node <linked-skill>/scripts/local-aggregate-status.mjs --repo .
```

Read the registered specification, actual upstream feedback, related context, and their relevant replies and pull requests before recommending action. Only `upstreamFeedback` means this change has been reported upstream. A closed issue or merged pull request is an adoption candidate: compare observable behavior, data and synchronization semantics, boundary cases, and verification coverage. Record an intentional upstream policy difference as `upstream-divergence`; keep outdated feedback as `needs-update`. Check whether an adopted fix is present in the selected stable tag as well as on trunk before recommending retirement.

Present five independent facts to the user: first-tier patch-version deltas, domain integration deltas, newly discovered feature/fix branches, upstream release movement, and feedback/adoption signals. Name the recommended integration ref from the status report. Recommend one of these paths and wait for the user's decision:

- no change on the recommended integration ref: incremental packaging of verified source deltas;
- a newer matching stable tag than the recorded baseline: for version 4 domain-managed features, keep dormant first-tier refs fixed, rebuild affected domain worktrees on that tag from selected mappings and owned adaptations, verify them, then freeze a train; for version 3 and version 4 direct-only features, retain the existing source-rebase and direct aggregate-rebuild path;
- unreleased trunk after the latest matching tag: report it as debt; keep the recommended target on the tag unless the user explicitly chooses the upstream tip;
- no stable tag configured, and the upstream ref has moved: rebase affected source worktrees onto that ref, verify them, then rebuild the aggregate;
- user explicitly declines rebase: incremental packaging against the current aggregate baseline, retaining and reporting upstream debt;
- upstream implementation fully covers a local branch: validate the upstream behavior before retiring that branch from both the aggregate and registry.

## Update first-tier patches

Continue active feature work from the current effective domain implementation, then refresh only that feature's explicit patch selection. An advanced source whose recorded version is still an ancestor is an incremental candidate. A rewritten source is a replacement: recalculate its selected commits and mappings instead of treating its ancestry as an incremental range.

## Rebase domain worktrees

Rebase only in the corresponding domain worktree, onto the train's locked integration ref:

```bash
git -C <domain-worktree> status --short
git -C <domain-worktree> rebase --no-autostash <integration-ref>
```

Apply only each member's registered commits in dependency order. Record source-to-domain mappings for rewritten, split, or combined commits. Every adaptation names its reason and affected feature IDs. Product behavior changes return to a first-tier source; version compatibility remains in the domain. Resolve conflicts and verify in the domain worktree. First-tier refs move only when their feature itself changes.

Use `scripts/local-aggregate-compose.mjs --kind domain` to construct the registered domain ref transactionally. Remove its persistent worktree before composition and add it back at the returned tip; the composer refuses to move a checked-out ref. It uses an atomic compare-and-update from the observed tip, so a concurrent update fails instead of being overwritten, and updates the ref only after every selected commit applies. Record the returned mappings in the registry after review. The status report marks a domain stale when its source mappings no longer match the current dependency-closed first-tier selections.

## Incremental packaging

Direct-only incremental packaging requires a clean root checkout on `local/aggregate` and a recorded source version that remains an ancestor of the source branch. Package only explicitly selected verified deltas. If `$autoreview` closeout has not completed in the source worktree, finish it there before cherry-picking. Cherry-pick commits in dependency order with `-x`; branch ancestry is not the patch selection.

If a cherry-pick conflicts, abort it and repair the source worktree. Do not make a product-only fix on the aggregate branch.

## Extract a contribution

Use `scripts/local-aggregate-compose.mjs --kind contribution` with the target feature ID. The result contains its explicit dependencies and domain adaptations associated with that feature, not the complete domain. Verify its product behavior and inspect its changed paths against the target specification. This creates a local exercise or contribution branch; upstream issue, comment, and PR publication retain their existing explicit authorization boundaries.

## Freeze and package a train

Commit a train manifest that locks the stable tag and SHA, exact dependency-closed feature IDs, frozen dependency and per-feature logical-patch maps, domain IDs and optional member subsets, direct feature IDs, one canonical entry per logical patch, verification record, and expected maintenance inputs. Use `scripts/local-aggregate-compose.mjs --kind train` to construct an immutable candidate ref. The composer refuses dirty or untracked registry and train inputs, reads both from `HEAD`, commits those exact files into the candidate, and returns the manifest commit plus train SHA-256. It validates complete feature selections rather than consulting a later registry revision. A shared dependency appears once with its frozen canonical mapped commit and merged feature ownership; duplicate logical IDs are rejected rather than silently choosing between domain rewrites. Output refs are created with an atomic absent-ref check and are never replaced.

Run the project's real resource-isolated package workflow from that exact candidate. After it succeeds, write a package credential outside the source commit that records candidate SHA, train-manifest digest, immutable ref, Node and package-manager versions, OS/architecture/ABI, build command and configuration, host protocol version, known database compatibility, artifact paths and digests, verification result, publication state, and deployment state. A dry run or test does not set packaged status.

## Publish completed snapshots

After domain, candidate, package, and registry verification succeed, push completed source branches, domain branches, contribution exercises requested for preservation, immutable train refs, and the candidate or aggregate ref to the configured personal-fork remote. Use an ordinary push when the remote ref is absent or an ancestor of the local ref. For a deliberately rebased or rebuilt moving ref, inspect the remote SHA immediately before publication and use `--force-with-lease=<ref>:<observed-sha>`; the skill invocation is standing authorization for this personal-fork maintenance push, so do not request separate approval. Immutable refs are create-only. Never force-push the upstream remote. Verify every remote SHA after pushing.

The published aggregate is a reproducible source snapshot for another environment. It does not replace that environment's dependency installation or build, and it must never be used as an upstream pull-request branch.

## Complete rebuild

Use the frozen train to construct a temporary integration worktree from its locked baseline. Verify the result, record its source and package credentials, then create a recoverable local backup ref and replace the root `local/aggregate` without another approval prompt when that replacement is in scope. The only remaining confirmation is the project deployment workflow's final replacement of a running local service. Never silently use a destructive reset.

After a successful rebuild, update every package record, the human overview in `AGENTS.md`, and `aggregate.lastIntegratedUpstreamCommit`. Do not update the upstream baseline after incremental packaging performed without a rebase.
