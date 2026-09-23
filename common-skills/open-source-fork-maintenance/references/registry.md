# Registry and evidence contract

The registry describes current ownership. A committed train freezes one selection. A receipt records what actually ran against its final source. Do not substitute one for another.

Use the existing v4 format for both direct-only and domain-based forks; this standard does not introduce another registry version. `aggregate.upstreamRef` is the tracking ref for discovery, while `lastIntegratedUpstreamCommit` is the actual integrated baseline. Keep the project's personal-fork remote, skill installation/revision, and verification entrypoints in its linked maintenance guidance; do not invent parser fields for facts the helper does not consume.

The version 4 registry extends version 3 without changing its feedback fields. Set `aggregate.upstreamRepository` to the upstream GitHub `owner/repo`, separately from its Git tracking ref. `aggregate.lastIntegratedUpstreamCommit` changes only after a complete aggregate rebuild based on a new upstream commit. Every feature gets a stable `id`. Every feature selected for a v4 train, including direct patches, declares the exact owned patch selection:

```json
{
  "id": "example",
  "branch": "feature/example",
  "lastPackaged": {
    "sourceCommit": "<source SHA>",
    "aggregateCommit": "<aggregate cherry-pick SHA>"
  },
  "specIssue": null,
  "upstreamFeedback": [
    {
      "repository": "upstream-owner/upstream-repo",
      "number": 123,
      "feedbackUrl": "https://github.com/upstream-owner/upstream-repo/issues/123#issuecomment-1"
    }
  ],
  "relatedIssues": [],
  "disposition": "reported",
  "reason": "The upstream report describes the current implementation.",
  "source": {
    "baseCommit": "<source baseline SHA>",
    "versionCommit": "<selected source version SHA>",
    "commits": [
      { "commit": "<owned commit SHA>", "logicalPatch": "example-core" }
    ]
  },
  "dependsOn": [],
  "integration": { "domain": "provider" }
}
```

The `commits` array, not branch ancestry, defines feature ownership. `logicalPatch` remains stable across a rewrite or replacement so shared dependencies deduplicate by identity. A replacement of the same logical patch keeps that identity and changes its SHA; a distinct additional patch gets a new identity. A new source commit advances `versionCommit` and the selection; a rewritten source requires recalculating the complete selection. Direct features use `integration: { "domain": null }`, not an invented domain. All executable selections use full commit SHAs.

Domains lock a baseline, members, integrated tip, source mappings, and explicit compatibility adaptations. `sourceLogicalPatches` distinguishes mappings of first-tier patches from adaptations so a later rebuild can replace stale source mappings without dropping domain-owned compatibility. Each mapped patch names all affected feature IDs; an adaptation may name several. A domain adaptation that changes product behavior requires a corresponding first-tier feature.

```json
{
  "id": "provider",
  "branch": "integration/provider-v1.2.3",
  "baseline": { "ref": "v1.2.3", "commit": "<full SHA>" },
  "members": ["example"],
  "adaptations": [],
  "integrated": {
    "commit": "<domain tip SHA>",
    "sourceLogicalPatches": ["example-core"],
    "patches": [
      {
        "commit": "<domain commit SHA>",
        "sourceCommit": "<first-tier commit SHA>",
        "logicalPatch": "example-core",
        "features": ["example"]
      }
    ]
  }
}
```

`trains` points to committed train manifests. A train locks one baseline, exact dependency-closed `features`, a `dependencies` map, per-feature `featureSources` and `featurePatches` maps, domain selections, direct feature IDs, and an ordered `patches` array containing one canonical mapped commit, source commit, logical patch ID, and merged feature owners per logical patch. Composition verifies dependency closure, first-tier provenance, and each feature's complete logical-patch selection from the train itself, never from a later feature record, and rejects duplicate logical IDs. Legacy version 4 entries remain visible to status reporting but cannot enter a new train until their explicit source selection has been frozen. Keep package credentials separate because they bind the resulting source SHA and artifact digests after the source commit exists.

`specIssue` is the local specification issue, or `null` when there is none. `upstreamFeedback` contains only actual reports or feedback comments in `aggregate.upstreamRepository`; a matching upstream issue that has not received this change's feedback belongs in `relatedIssues`. All three use the same issue reference shape, including `feedbackUrl` for the exact issue or comment URL. `relatedIssues` also holds historical context and parent feature specifications for maintenance repairs.

Choose a disposition from the evidence, and put the explanation in `reason`:

| Disposition | Meaning |
| --- | --- |
| `reported` | Actual upstream feedback describes the current change. |
| `needs-update` | Recorded upstream feedback describes an older implementation. |
| `needs-feedback` | No actual upstream feedback is recorded yet. |
| `fork-only` | The owner intentionally retains the change locally. |
| `internal` | Fork maintenance or deployment repair, without an upstream product claim. |
| `upstream-divergence` | Upstream handled the original report; the fork retains different behavior. |

When migrating version 2, classify every old `upstreamIssues` entry by its actual role rather than copying the array to `upstreamFeedback`. Preserve all package SHAs and the recorded baseline; see [migration.md](migration.md) for staged migration beyond reference classification. The helper reads version 2 with an unclassified-reference warning so other forks can migrate independently.

## Freeze one selection

Register each train as `{ "id": "v1.2.3-r1", "manifest": "config/local-aggregate-trains/v1.2.3-r1.json" }`. The path is repository-relative. Commit the registry and train together before composition. These fields make up its executable selection:

| Field | Meaning |
| --- | --- |
| `baseline: { ref, commit }` | Release tag/ref and full SHA; they must resolve to the same commit. |
| `features` | Exact selected feature IDs, including the dependency closure and selected maintenance features. |
| `dependencies` | Map of each selected ID to its frozen dependency IDs, including empty arrays. |
| `featureSources` | Map of each ID to its original `{ logicalPatch, commit }` source selections. |
| `featurePatches` | Map of each ID to every logical patch applied for it, including relevant adaptations. |
| `domains` / `domainFeatures` | Selected domain IDs and member subsets. Use empty selections for a direct-only train. |
| `directFeatures` | Selected IDs integrated without a domain. |
| `patches` | Ordered canonical `{ logicalPatch, commit, sourceCommit, features }` mappings. Shared patches have one entry and all affected owners. |

`commit` in a mapping is the chosen replayable commit; `sourceCommit` identifies its original source. For a direct unchanged patch they are equal. Domain adaptations also have explicit commits, logical identities, affected features, and reasons in the domain record. Keep the domain/member/direct descriptions consistent with the canonical sequence; the helper's source/dependency checks are not a full semantic audit of those descriptions.

Record project-specific verification commands/inputs and required maintenance assets alongside the frozen selection. The composer does not run them. All required tracked content beyond the registry and selected train must come from the baseline or selected patches. Keep distinct identity for a new patch, stable identity for a replacement of the same patch, and one canonical mapping when several domains carry that shared patch.

## Preserve history and build evidence

`lastPackaged` is the legacy `{ sourceCommit, aggregateCommit }` mapping; use `null` until the branch has been aggregated. Preserve known historical mappings when adopting v4. This field alone is not evidence of a successful artifact build, and an old mapping does not define the new train's selection. Current v4 ownership is in `source` and domain mappings; a frozen train records its own selection even if the current registry later changes.

Post-build receipts bind the promoted aggregate to its build/verification inputs and output digests, as described in [maintenance.md](maintenance.md). Record them after the final source commit exists, outside that source tree: for example in a release attachment or durable evidence store referenced by the release. Public evidence omits private machine configuration and credentials. New runs produce new evidence; old failures and successes retain their original input SHAs. A later registry revision can summarize completed evidence without rewriting the candidate it describes.

Publish immutable refs for the manifest input commit, selected source/mapped objects, and candidate. The receiving environment needs these objects and the recorded helper revision, not merely the latest moving branches. Compare reconstructed trees; do not promise identical commit or artifact hashes unless their creation/build is actually deterministic.
