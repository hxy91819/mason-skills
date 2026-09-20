# Initialize a non-maintainer fork

## Preflight

Inspect the repository before proposing writes:

```bash
git remote -v
git status --short
git branch --show-current
git worktree list
gh repo view --json nameWithOwner,visibility,viewerPermission,isFork,parent 2>/dev/null || true
```

Identify the upstream tracking ref without assuming a remote name. Confirm that the user lacks upstream merge authority. If the repository is not a public fork or the operator is an upstream maintainer, stop and use that project's ordinary workflow.

Explain the proposed layout and obtain explicit authorization before creating `local/aggregate`, changing the root checkout, creating a project skill link, or editing `AGENTS.md`.

## Establish the project facts

After authorization, preserve unrelated worktree changes and perform these steps.

1. Create or reuse `local/aggregate` from the selected upstream ref. If the root checkout already contains work, use another clean worktree for the branch operation and only move the root checkout after its state is safe. Do not use `stash` or autostash.
2. Link this skill into the project's canonical skill directory. `.agents/skills` is the default; a project with a documented custom skill directory may use that directory instead.

   ```bash
   python3 <linked-skill>/scripts/link_project_skill.py \
     --repo "$PWD" --skills-dir .agents/skills --apply
   ```

   For example, a project that discovers skills from `.bb/skills` passes `--skills-dir .bb/skills`. The helper only creates an absent link or accepts an identical one. It never replaces a file, directory, or different link.
3. Create `config/local-aggregate-features.json` from [../assets/local-aggregate-features.json](../assets/local-aggregate-features.json). Replace both upstream placeholders with the selected ref and its resolved commit. Use version 4 when the project needs domain integration; version 3 remains valid for direct-only maintenance. If the project has an existing machine-readable configuration convention, locate the registry there and update the project-specific `AGENTS.md` block to name that path.
4. Add the marked content from [../assets/AGENTS.local-aggregate.md](../assets/AGENTS.local-aggregate.md) to the root `AGENTS.md`. Update an existing `open-source-fork-maintenance` marked block in place; never duplicate it. Add a short table that mirrors the registry when the first feature is packaged.
5. Find every local `feature/*` and `fix/*` branch and worktree. Register committed implementations with their actual feedback status; verification still determines when they can be aggregated. They are default aggregation candidates, not opt-in candidates. A missing upstream report is recorded as `needs-feedback`, and local maintenance as `internal`; neither needs a placeholder issue. Filing an issue on the upstream repository follows the authorization boundary in SKILL.md.

The version 4 registry extends version 3 without changing its feedback fields. Set `aggregate.upstreamRepository` to the upstream GitHub `owner/repo`, separately from its Git tracking ref. `aggregate.lastIntegratedUpstreamCommit` changes only after a complete aggregate rebuild based on a new upstream commit. Every feature gets a stable `id`. Domain-managed features also declare the exact owned patch selection:

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
      { "commit": "<owned commit SHA>", "logicalPatch": "example-core-v1" }
    ]
  },
  "dependsOn": [],
  "integration": { "domain": "provider" }
}
```

The `commits` array, not branch ancestry, defines feature ownership. `logicalPatch` remains stable across a rewrite or replacement so shared dependencies deduplicate by identity. A new source commit advances `versionCommit` and the selection; a rewritten source requires recalculating the complete selection.

Domains lock a baseline, members, integrated tip, source mappings, and explicit compatibility adaptations. `sourceLogicalPatches` distinguishes mappings of first-tier patches from adaptations so a later rebuild can replace stale source mappings without dropping domain-owned compatibility. Each mapped patch names all affected feature IDs; an adaptation may name several. A domain adaptation that changes product behavior requires a corresponding first-tier feature.

```json
{
  "id": "provider",
  "branch": "integration/provider-desktop-v1.2.3",
  "baseline": { "ref": "desktop-v1.2.3", "commit": "<full SHA>" },
  "members": ["example"],
  "adaptations": [],
  "integrated": {
    "commit": "<domain tip SHA>",
    "sourceLogicalPatches": ["example-core-v1"],
    "patches": [
      {
        "commit": "<domain commit SHA>",
        "sourceCommit": "<first-tier commit SHA>",
        "logicalPatch": "example-core-v1",
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

When migrating version 2, classify every old `upstreamIssues` entry by its actual role rather than copying the array to `upstreamFeedback`. Preserve all package SHAs and the recorded baseline. The helper reads version 2 with an unclassified-reference warning so other forks can migrate independently.

Use `null` for `lastPackaged` only while a registered branch has not yet been aggregated. Configure `stableTagPattern` whenever the upstream publishes release tags — fork packaging anchors the most mature tag channel the upstream ships, never trunk tip. Inspect the namespace first:

```bash
git tag --merged <upstream-ref> --sort=-version:refname | head
```

Set a regular expression that selects that channel and excludes less mature ones — for an upstream whose tags are all prereleases, a pattern matching only the rc line (for example `^dsh-v\d+\.\d+\.\d+(-rc\.\d+)?$`) anchors release candidates over alphas. Use `null` only when the upstream publishes no release tags at all. The latest matching tag reachable from `upstreamRef` then becomes the default rebase and rebuild target, and a rebuild records that tag's commit as `lastIntegratedUpstreamCommit`.

## Verify setup

From the project root, fetch the selected upstream and run:

```bash
node <linked-skill>/scripts/local-aggregate-status.mjs --repo .
```

The output must identify the expected aggregate branch, the selected upstream, the registry path, all registered features, and any unregistered local feature/fix branch. Report any repository-specific service or deployment rule separately; this skill does not infer or install one.
