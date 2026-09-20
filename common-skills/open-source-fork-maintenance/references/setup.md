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
3. Create `config/local-aggregate-features.json` from [../assets/local-aggregate-features.json](../assets/local-aggregate-features.json). Replace both upstream placeholders with the selected ref and its resolved commit. If the project has an existing machine-readable configuration convention, locate the registry there and update the project-specific `AGENTS.md` block to name that path.
4. Add the marked content from [../assets/AGENTS.local-aggregate.md](../assets/AGENTS.local-aggregate.md) to the root `AGENTS.md`. Update an existing `open-source-fork-maintenance` marked block in place; never duplicate it. Add a short table that mirrors the registry when the first feature is packaged.
5. Find every local `feature/*` and `fix/*` branch and worktree. Register committed implementations with their actual feedback status; verification still determines when they can be aggregated. They are default aggregation candidates, not opt-in candidates. A missing upstream report is recorded as `needs-feedback`, and local maintenance as `internal`; neither needs a placeholder issue. Filing an issue on the upstream repository follows the authorization boundary in SKILL.md.

The registry schema is version 3. Set `aggregate.upstreamRepository` to the upstream GitHub `owner/repo`, separately from its Git tracking ref. `aggregate.lastIntegratedUpstreamCommit` changes only after a complete aggregate rebuild based on a new upstream commit. Each feature has this shape:

```json
{
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
  "reason": "The upstream report describes the current implementation."
}
```

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
