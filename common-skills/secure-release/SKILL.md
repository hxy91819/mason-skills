---
name: secure-release
description: Design, integrate, migrate, and verify fail-closed software release pipelines with immutable source identity, one hashed artifact set, least privilege, OIDC publication, registry smoke tests, and GitHub Release readback. Use when creating or reviewing release automation for npm or when evaluating adapters for PyPI, Cargo, Go/GitHub binaries, or containers; only the bundled npm adapter is currently implemented.
disable-model-invocation: true
---

# Secure Release

这是流程类 Skill，默认仅在用户显式调用 `$secure-release` 时运行。

Keep the agent-facing integration workflow separate from the runtime release
components. A target repository's CI must work after this skill is removed.

## Workflow

1. Inspect repository instructions, Git state, manifests, release workflows,
   changelog policy, registry configuration, and existing published releases.
2. Read [protocol.md](references/protocol.md) and classify each invariant as
   present, missing, conflicting, or not applicable.
3. Read [adapters.md](references/adapters.md). Select only an adapter whose
   status is **implemented**. Treat all other ecosystems as design targets,
   never as supported release paths.
4. Prefer the versioned vendored kit in `assets/secure-release-kit/v1/` for the
   shared deterministic checks. Copy it into the target repository, normally
   under `.github/secure-release/v1/`, and retain its tests.
5. Create or migrate a thin workflow in the target repository. Keep its exact
   path, GitHub Environment, permissions, trigger, project checks, and adapter
   commands visible there. Pin external actions to reviewed commit SHAs.
6. Configure the registry Trusted Publisher out of band using the target
   repository, exact workflow filename, and Environment shown in the thin
   workflow. Never put that identity in a reusable workflow hidden elsewhere.
7. Exercise `--help`, unit tests, an offline fixture release, and fail-closed
   negative cases before enabling publication. Verify the packed contents.
8. Run repository checks, privacy and Git-metadata review, then independently
   review the final workflow and kit diff.

## Migration Rules

- Preserve an existing release trigger until the replacement has an explicit
  cutover decision. Do not leave two workflows able to publish one version.
- Build once in preflight, upload one named artifact bundle, and publish only
  downloaded bytes that pass the manifest SHA-256 check. Never rebuild in the
  privileged publish job.
- Resolve the tag, version, commit, manifest, registry identity, and GitHub
  Release identity independently. Any mismatch or ambiguous network error is a
  hard failure.
- Treat registry publication as irreversible. A rerun may verify an already
  published exact version, but must not silently overwrite or repoint it.
- Keep project-specific build, test, package-content, and smoke assertions in
  the thin workflow or adapter configuration, not in the common protocol.
- Do not require a Codex installation, this skill directory, or network access
  to this repository during CI execution.

## Component Choice

Use a public Action only after its interface and maintenance justify adding a
remote trust boundary. Use an independent CLI when multiple kits need a shared
release cadence and signed distribution. For the current small, auditable
surface, use the versioned vendored kit: it is SHA-pinnable through the target
repository commit, reviewable with the workflow, and runnable without agent
infrastructure. See [component-boundaries.md](references/component-boundaries.md).

## Completion Evidence

Report the workflow path and Environment identity, kit version, implemented
adapter, source/tag/version proof, manifest verification, packed-content test,
registry and GitHub readback plan or result, privacy result, and every remaining
manual registry setting. Clearly list unsupported ecosystems.
