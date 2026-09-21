# Initialize a new fork

Use this path when there is no existing fork product history to preserve. Otherwise start with [migration.md](migration.md). Reuse setup authorization already provided by the user's request, as described in [SKILL.md](../SKILL.md).

## Establish the project facts

Inspect the checkout before writing:

```bash
git remote -v
git branch --show-current
git status --short
git worktree list
gh repo view --json nameWithOwner,visibility,viewerPermission,isFork,parent
```

Identify the upstream repository and tracking ref, the personal-fork publication remote, and the operator's role. Remote names are not roles: `origin` may be upstream or the fork. Confirm the public/non-maintainer scope in SKILL.md. Preserve unrelated work; do not use stash or autostash.

Choose the baseline before creating integration branches. Fetch the upstream and inspect its tag namespace and release channel:

```bash
git fetch --prune --tags <upstream-remote>
git tag --merged <upstream-ref> --sort=-version:refname
```

Configure `aggregate.stableTagPattern` to match the mature channel used by the project, excluding unrelated packages and less mature prereleases. For ordinary stable tags an example is `^v\d+\.\d+\.\d+$` (escape backslashes in JSON). If the upstream ships only prereleases, select its most mature channel, such as rc over alpha. Use `null` only when there are no release tags. Resolve the selected tag to its full commit SHA. `upstreamRef` remains the tracking branch used to discover releases; `lastIntegratedUpstreamCommit` records the baseline actually integrated.

Record the project's dependency install, relevant tests, build/distribution commands, supported platforms, and existing deployment policy in its own guidance. Reuse its native tools; do not copy another project's Node version, resource runner, service manager, migration runner, or deployment approval policy.

## Create the minimum layout

1. Create `local/aggregate` from the chosen baseline, or inspect and reuse an existing identical branch. Never reset a pre-existing aggregate as initialization. Move the root checkout only when its work is preserved and that move is covered by setup authorization. Use a clean worktree while preparing changes.
2. Link the loaded skill into the project's discovery directory. `.agents/skills` is the default; use a documented project-specific directory when applicable:

   ```bash
   python3 <loaded-skill>/scripts/link_project_skill.py \
     --repo "$PWD" --skills-dir .agents/skills --apply
   ```

   The helper creates an absent link or accepts an identical one; it does not replace a different file/link. Record the shared skill revision used by a release and how another machine installs it. A local relative symlink alone is not a portable copy of the tool.
3. Copy [the registry template](../assets/local-aggregate-features.json). Use v4 from the start, with empty `features`, `domains`, and `trains`. Fill the actual upstream repository, tracking ref, release pattern, and baseline SHA. An empty new fork needs neither placeholder features nor an empty train; the composer expects a nonempty patch selection.
4. Install [the marked AGENTS block](../assets/AGENTS.local-aggregate.md), substituting actual registry and skill locations. Update an existing marked block in place. Link to the registry instead of copying a table of moving SHAs. If the project already has another configuration convention, keep it and pass `--manifest <registry-path>` to the helpers.
5. Commit the project's maintenance files as an owned maintenance selection before constructing its first train. The composer automatically carries only the committed registry and selected train; AGENTS, runbooks, helper wrappers, and other required tracked assets need explicit selected patches too.

## First feature, then first domain

Start each feature/fix in its own source worktree. Record its stable feature ID, exact owned commits, dependencies, feedback role, and `integration: { "domain": null }` using [registry.md](registry.md). Run relevant checks and source review. A direct-only fork already follows the standard.

Add a domain when several features repeatedly require coordinated upstream adaptation. Choose members by their shared contracts and upgrade conflicts, not by the number of branches. Register its baseline, members, source mappings, and adaptations; start its worktree from the chosen release. There is no requirement to invent database, UI, or provider domains for every project.

Freeze the first nonempty train and follow [maintenance.md](maintenance.md) for composition, verification, packaging, and publication. Keep deployment separate according to the project's existing workflow.

## Verify setup

```bash
node <loaded-skill>/scripts/local-aggregate-status.mjs --repo .
```

Confirm the reported aggregate, upstream, registry, release target, and source inventory. Investigate discovered local feature/fix branches before calling the project empty. Setup is complete when these facts and project instructions are committed and consistent; it does not claim a build, publication, or deployment that has not occurred.
