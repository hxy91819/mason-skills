# Maintain the aggregate

## Audit and decide

Fetch the registry's upstream ref, then run the linked status helper:

```bash
git fetch --prune --tags <upstream-remote>
node <linked-skill>/scripts/local-aggregate-status.mjs --repo .
```

Read the registered specification, actual upstream feedback, related context, and their relevant replies and pull requests before recommending action. Only `upstreamFeedback` means this change has been reported upstream. A closed issue or merged pull request is an adoption candidate: compare observable behavior, data and synchronization semantics, boundary cases, and verification coverage. Record an intentional upstream policy difference as `upstream-divergence`; keep outdated feedback as `needs-update`. Retire only behavior supplied by the selected stable tag, preserving the historical record and any unadopted remainder.

Report five independent facts: first-tier patch-version deltas, domain integration deltas, newly discovered feature/fix branches, upstream release movement, and feedback/adoption signals. Name the recommended integration ref. Continue the path already authorized by the user; if only an assessment was requested, present these maintenance choices before modifying refs:

- no change on the recommended integration ref: incremental integration of verified source deltas;
- a newer matching stable tag than the recorded baseline: keep dormant first-tier refs fixed, rebuild affected domains from their selected mappings/adaptations, and replay direct patches on that tag; refresh an active source only when its work needs it; verify, then freeze a train;
- unreleased trunk after the latest matching tag: report it as debt; keep the recommended target on the tag unless the user explicitly chooses the upstream tip;
- no release tags available, and the upstream ref has moved: use its exact selected SHA as the domain/direct rebuild baseline;
- user explicitly declines rebase: incremental integration against the current aggregate baseline, retaining and reporting upstream debt;
- upstream implementation fully covers a local branch: validate it on the selected release before retiring the selection; retain provenance and the retirement reason.

Keep v3 direct-only repositories on their existing maintenance path while preparing [migration.md](migration.md); the composer requires v4 selections.

## Update first-tier patches

Continue active feature work in its own worktree from a suitable current baseline or effective domain implementation, then refresh only that feature's explicit patch selection. Starting from a domain does not make all domain ancestry part of the feature. An advanced source whose recorded version is still an ancestor is an incremental candidate. A rewritten source is a replacement: recalculate its selected commits and mappings instead of treating its ancestry as an incremental range. Previously frozen trains continue to reference their old selections.

## Rebase domain worktrees

Prepare each domain on the next train's locked integration ref. For a domain whose ancestry consists of the recorded old baseline and owned patch sequence, rebase in its own worktree:

```bash
git -C <domain-worktree> status --short
git -C <domain-worktree> rebase --no-autostash --onto <new-baseline-sha> <old-baseline-sha>
```

Otherwise rebuild from explicit selections in a clean domain worktree rather than replaying unrelated ancestry. These are alternative upgrade paths: do not rebase the domain and then apply the same source commits again. Record source-to-domain mappings for rewritten, split, or combined commits. Every adaptation names its reason and affected feature IDs. Product behavior changes return to a first-tier source; version compatibility remains in the domain. Resolve conflicts and verify there. First-tier refs move only when their feature itself changes.

Before freezing the train, assign every selected feature according to the project's domain policy. A feature mapped to a domain enters through that domain's adapted commits; replay first-tier commits directly only for explicitly selected direct features. If upstream moves a feature's UI or data contract, repair its owning domain mapping there before composing the aggregate.

For reconstruction, the composer can construct the registered domain ref transactionally:

```bash
node <loaded-skill>/scripts/local-aggregate-compose.mjs --repo . \
  --kind domain --target <domain-id> --output-ref refs/heads/<registered-domain-branch>
```

It refuses a checked-out output ref. Preserve active or dirty worktrees; use a new registered domain branch for the new train, or retire an inactive clean domain worktree before composition and add it back at the returned tip. It atomically compares the observed tip and only updates after every selected commit applies. Record returned mappings after review, including `integrated.sourceLogicalPatches` and explicit `adaptations`. A source-mapping match alone does not establish compatibility on a new baseline; run the relevant checks there.

## Incremental integration

On the existing baseline, select only verified source deltas. For v4, freeze a new train/candidate even if all features are direct; leave the old train immutable. The legacy v3 incremental path requires a clean root `local/aggregate` and a recorded source version that remains an ancestor of the source branch. Finish relevant source checks and `$autoreview` closeout before applying selected commits in dependency order with `-x`; branch ancestry is not the patch selection.

If integration conflicts, abort the failed composition and repair the owning source, shared dependency, or domain adapter. Do not leave an unowned product fix on the aggregate.

## Extract a contribution

Extract the target feature with its explicit dependencies and associated domain adaptations:

```bash
node <loaded-skill>/scripts/local-aggregate-compose.mjs --repo . \
  --kind contribution --target <feature-id> --output-ref refs/heads/contribution/<unique-name>
```

Inspect its changed paths and verify product behavior against the target specification. Split an adaptation that unnecessarily bundles unrelated changes before claiming a focused contribution. The helper selects the domain/current aggregate baseline; adapt the extracted result to the intended upstream contribution target when needed. This creates a local exercise or contribution branch; upstream issue, comment, and PR publication retain their existing explicit authorization boundaries.

## Freeze and verify a train

Commit a train manifest using [registry.md](registry.md): locked baseline, dependency-closed selections, domain/direct mappings, canonical patch order, verification inputs, and required maintenance patches. Compose a new immutable candidate:

```bash
node <loaded-skill>/scripts/local-aggregate-compose.mjs --repo . \
  --kind train --target <train-id> --output-ref refs/tags/fork-candidate/<unique-name>
```

The composer refuses dirty/untracked registry and train inputs, reads both from `HEAD`, carries those exact files into the candidate, and returns the manifest commit plus train SHA-256. It validates frozen source/logical-patch selections and dependency closure, without consulting later feature records. It does not generate a train, copy every maintenance file from HEAD, execute validation commands, or prove compatibility. Review full-tree reconstruction and run the project checks. A shared dependency has one canonical mapped commit with merged owners; output refs are create-only. New inputs or corrections produce a new candidate name. A candidate build may verify compatibility, but it is not the final package.

## Promote the aggregate

After candidate verification and before packaging, recheck root branch/status/worktrees, preserve a recoverable old aggregate ref, and replace root `local/aggregate` with the exact candidate commit. Preserve concurrent edits and user files; never silently use a destructive reset. Confirm the root SHA equals the candidate SHA. Service replacement follows the project's existing deployment policy and authorization.

Finalize selection-bearing metadata before freezing. The new registry records its actual integrated baseline; the old active aggregate remains the record of its old baseline until replacement. On an unchanged baseline, retain that SHA. Keep historical `lastPackaged` evidence intact in the frozen source; record the new build's results in its post-build receipt. Do not modify the tested source merely to insert its own final SHA or a new artifact digest. Link the overview to these records. Any later source correction requires a new candidate and the affected verification.

## Publish and package

Publish completed source/domain work once verified; a later aggregate package need not hold those source refs hostage. Publish the manifest, retained contribution exercises, immutable input refs, candidate, and promoted aggregate to the personal fork. Compare the remote aggregate SHA with the candidate before packaging. Use an ordinary push for absent refs or fast-forwards. For a deliberately rewritten moving ref, inspect its remote SHA and use `--force-with-lease=<ref>:<observed-sha>` without another approval prompt. Immutable refs are create-only. Never force-push upstream. Verify remote SHAs, peeling annotated tags to compare their commit targets.

Run the project's package/distribution workflow against the promoted aggregate SHA, using its resource isolation when required. Either machine may build a clean detached immutable release ref created after promotion, provided its commit equals that aggregate SHA. After success, write a receipt outside the source commit recording aggregate SHA/tree, train digest, immutable input refs, skill/toolchain revisions, build commands/configuration, applicable platform information, artifact locations/digests, verification results, publication state, and deployment state. Add runtime ABI, schema/ledger compatibility, or wire protocol versions only when relevant. Keep credentials and private machine configuration out of public evidence. A dry run or unit test does not set packaged status; a source-only project reports its actual source verification/distribution stage.

Publish immutable refs that keep every selected original source and canonical mapped commit reachable, together with the registry/train input commit and candidate. A SHA in JSON or a cherry-pick trailer does not preserve its Git object. Another environment must be able to fetch those refs, install the recorded tool revision and project dependencies, and reconstruct the same tracked tree; commit IDs can differ when composition timestamps differ. Artifact reproducibility depends on the project's build controls. The aggregate is never an upstream PR branch.
