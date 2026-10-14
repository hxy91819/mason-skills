---
name: open-source-fork-maintenance
description: Set up or migrate a public fork to independent feature/fix branches on the upstream stable tag, aggregated by a rebuilt merge of those branches.
disable-model-invocation: true
triggers:
  - user
---

# Open-source fork maintenance

Invoke explicitly as `$open-source-fork-maintenance` for a public upstream fork whose owner cannot merge upstream. The model serves three goals and nothing else:

1. every change is an independent, focused `feature/*` or `fix/*` branch that can go upstream as-is;
2. the owner can aggregate those branches and distribute installable packages through the fork's CI;
3. new upstream stable releases can be absorbed.

State lives in Git: the branches themselves plus one `.fork/branches` list. `main` is the personal fork's default branch and latest aggregate, rebuilt from the stable tag by merging the listed branches; `git rerere` remembers conflict resolutions between runs. Domains, patch registries, frozen trains, SHA tables, candidate tags, and build receipts are out of scope: they cost more integration time than they save.

After setup, the project owns its copy of the rules, script, and release workflow when packaging applies. Day-to-day work (new branches, aggregation, packaging, conflicts, upgrades, upstream feedback) follows the project's `docs/fork-maintenance.md`; this skill is for setup, migration, and changing the shared template.

## Conventions

| Item | Value |
| --- | --- |
| Remotes | `origin` = upstream (read-only), `fork` = personal fork (all pushes) |
| Base | a tag from the upstream release channel, recorded on the `base` line of `.fork/branches` |
| Tooling branch | `fork-tooling`, based on the base tag; holds `.fork/branches`, `scripts/fork-aggregate`, `docs/fork-maintenance.md`, and the AGENTS section; merged like any other branch |
| Default branch | `main` on the personal fork; ordinary clones receive the latest aggregate |
| Aggregate | `scripts/fork-aggregate` builds a temporary local candidate in `.worktrees/aggregate-next` (`aggregate/next`); `--promote` puts the result on root `main` and publishes `fork/main` with a lease |
| Worktrees | `.worktrees/<name>`, excluded via `.git/info/exclude` or `.gitignore` |

Use `main` / `fork/main` for ordinary checkouts, clones, deployment, and sharing. `aggregate/next` is only a temporary verification candidate used by the script; it is not a user-facing or published branch.

Upstream issues, comments, and PRs always need the user's confirmation per item. Rewriting fork branches (rebase onto a new tag, rebuilt `main`) uses `--force-with-lease` against the observed remote SHA without asking again; never push to `origin`.

## Setup

1. Confirm the remotes and pick the base: the newest tag of the upstream release channel (use upstream `main` only when the user asks or no release tags exist). Inspect existing build/package commands, release workflows, and the installation targets stated in the task or repository.
2. Create `fork-tooling` from the base in its own worktree and add, adapting placeholders to the project:
   - `assets/fork-aggregate` → `scripts/fork-aggregate` (executable);
   - `assets/branches.example` → `.fork/branches`, listing `fork-tooling` first;
   - `assets/fork-maintenance.md` → `docs/fork-maintenance.md`, filling in the project's verification, packaging, release, and deployment commands;
   - `assets/AGENTS.fork-maintenance.md` → appended to the project's always-loaded agent instructions (`AGENTS.md` or `CLAUDE.md`).
3. When installable artifacts and packaging commands are known, include a tag-triggered release workflow in `fork-tooling`, adapting the [packaging and release contract](assets/fork-maintenance.md#3-打包与发布) to the project's actual platforms and runtime dependencies. Reuse upstream build tooling where useful, and publish to the personal fork. Deliver a runnable pipeline and installation instructions rather than recurring instructions to build on each machine. If the artifact or target remains unclear, continue independent setup work and clarify that missing choice.
4. Rebase each existing change onto the base as its own branch (see Migration for a fork with history), register it in the list, and push branches and `fork-tooling` to `fork`.
5. Prepare a clean root on `main`, preserving any previous `main` tip under an archive ref before replacing it. Run `scripts/fork-aggregate`, verify with the project's checks, then `--promote`. Set the personal fork's GitHub default branch to `main` and verify it. When packaging applies, release that verified aggregate through CI using the project's documented tag flow.

Done when every listed branch is on `fork`, the root checkout is `main` at the promoted commit, the remote `main` SHA matches, and the personal fork's default branch is `main`. When packaging applies, also require a successful fork Release and an installation smoke test using its downloaded artifact; report unavailable runners, credentials, or failed builds as unfinished release work.

## Moving an existing aggregate to main

Update the project's scripts, rules, packaging and deployment checks to use `fork/main`. Preserve the previous local and remote `main` tips under archive refs, then put the clean root on `main` at the verified aggregate. Publish it with a lease against the observed remote `main` SHA; set and verify the personal fork's default branch as `main`. Stop publishing `local/aggregate`; it may remain as a historical ref. Verify a fresh ordinary clone receives the aggregate. This migration does not require a new package release or service restart.

The base remains the recorded stable tag. GitHub can still show commits behind upstream development `main`; changing the fork's default branch does not change its release baseline.

## Migration from a registry/domain/train model

1. Tag the current aggregate as `archive/<old-model-name>` and each fork branch tip you will rewrite as `archive/pre-simplify/<branch>`; push the tags to `fork`.
2. Rebuild each feature branch on the new base from the most recent verified integration of that feature (the last train or domain commits already adapted to the base, if any; otherwise its source commits). Cherry-pick with `-x`, skip commits that become empty, and keep branches independent; stack a branch on another only when its patches do not apply without it, and note the stack in the list.
3. Compare each rebuilt branch's own commits with its old tip by subject; branches cut from the old aggregate carry unrelated commits, so only their top commits matter.
4. Drop features the user retires; they stay reachable through the archive tags.
5. Carry only maintenance assets the project still uses (deploy/runtime scripts, release workflows, ignore rules) into `fork-tooling`; delete registries, train manifests, domain branches, and candidate tags from the new tree. Apply Setup's packaging branch when migrating an installable project.
6. Aggregate, verify, compare the result with the old aggregate (differences should be exactly the retired features and maintenance files), push with leases, promote.
7. Remove clean obsolete worktrees without `--force`; leave dirty or in-use ones and report them.

## Changing the shared template

Edit the assets here, then run `node --test tests/test_fork_aggregate.mjs` from this skill's root. Projects keep their own copies; propagate a change to a project only when asked or when that project's copy hits the same bug.
