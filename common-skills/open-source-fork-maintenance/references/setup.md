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
5. Find every local `feature/*` and `fix/*` branch and worktree. Register each one after it has an upstream issue or feedback comment and a committed, verified implementation. They are default aggregation candidates, not opt-in candidates.

The registry schema is version 2. `aggregate.lastIntegratedUpstreamCommit` changes only after a complete aggregate rebuild based on a new upstream commit. Each feature has this shape:

```json
{
  "branch": "feature/example",
  "lastPackaged": {
    "sourceCommit": "<source SHA>",
    "aggregateCommit": "<aggregate cherry-pick SHA>"
  },
  "upstreamIssues": [
    {
      "repository": "upstream-owner/upstream-repo",
      "number": 123,
      "feedbackUrl": "https://github.com/upstream-owner/upstream-repo/issues/123#issuecomment-1"
    }
  ]
}
```

Use `null` for `lastPackaged` only while a registered branch has not yet been aggregated. `stableTagPattern` may be `null`; set it to a regular-expression string only when the upstream's stable-release tag namespace is known.

## Verify setup

From the project root, fetch the selected upstream and run:

```bash
node <linked-skill>/scripts/local-aggregate-status.mjs --repo .
```

The output must identify the expected aggregate branch, the selected upstream, the registry path, all registered features, and any unregistered local feature/fix branch. Report any repository-specific service or deployment rule separately; this skill does not infer or install one.
