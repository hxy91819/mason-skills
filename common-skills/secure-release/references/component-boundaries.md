# Component boundaries

## Skill

Identify release surfaces, select an implemented adapter, copy/version the kit,
migrate the target workflow, configure verification, and report registry-side
identity steps. The skill never participates in a CI run.

## Thin target workflow

Own the exact trigger, primary branch, workflow filename, Environment, job
permissions, pinned Action SHAs, project checks, package-content assertions,
and adapter arguments. This file is the auditable OIDC identity boundary.

## Vendored kit

Provide deterministic, versioned source/changelog/manifest checks and adapter
commands. It has no GitHub token or registry credentials of its own. The target
repository reviews upgrades as ordinary source diffs and pins the kit through
its own commit.

## Why not a reusable public Action yet

A public Action would centralize upgrades but introduces another repository,
tag-mutability risk, action runtime, and permission boundary. The current core
is one standard-library Python program, so vendoring is smaller and easier to
audit. Reconsider an Action after at least two implemented adapters need the
same orchestration and consumers demonstrate upgrade friction.

## Why not an independent CLI yet

A separately distributed CLI needs signed binaries/packages, bootstrap and
update policy, compatibility guarantees, and its own secure release chain.
Promote the kit to a CLI only when its API stabilizes across several real
repositories. Preserve the manifest schema and command behavior as the future
migration seam.
