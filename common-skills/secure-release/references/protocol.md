# Cross-language release protocol

## Required state transitions

| Stage | Required evidence | Failure behavior |
|---|---|---|
| Dispatch | Explicit stable tag input; workflow runs from the primary workflow ref | Reject implicit, prerelease, malformed, or wrong-ref dispatches |
| Source | Tag resolves to one commit; declared version matches; commit is reachable from the protected primary branch | Reject missing, moved, mismatched, or unreachable identities |
| Preflight | Frozen dependency install, project checks, privacy gate, changelog section, adapter package inspection | Stop before obtaining publish credentials |
| Handoff | One CI artifact bundle contains release files, release notes, and a canonical manifest with SHA-256 and sizes | Reject extra, missing, duplicate, symlink, or changed files |
| Publish | Exact downloaded bytes are reverified; registry version is absent; OIDC job has only required permissions and its own Environment | Treat ambiguous registry responses as errors; never rebuild |
| Registry smoke | Exact version metadata resolves and a clean consumer can install or pull it | Retry only documented eventual consistency; never change identity |
| GitHub Release | Exact tag, notes, asset names, bytes, and hashes are downloaded and compared after creation | Creation failure may be reconciled only with an identical existing release |

## Workflow invariants

- Start with `permissions: {}` and grant per job. Preflight normally needs
  `contents: read`; registry publication adds `id-token: write`; GitHub Release
  creation uses a separate `contents: write` job.
- Use tag-scoped concurrency with `cancel-in-progress: false`. Concurrent runs
  for different tags may proceed; the same tag must serialize.
- Set explicit timeouts. Disable checkout credential persistence.
- Pin third-party and GitHub Actions to reviewed full commit SHAs. Record the
  upstream tag as a comment for maintainability.
- Keep the Trusted Publisher repository, exact workflow filename, and GitHub
  Environment in the target repository. Changing any of the three is an
  identity migration requiring registry-side reconfiguration and a dry run.
- Use a cumulative committed changelog. Generate or extract notes before the
  tag is published, then verify the tagged changelog section without modifying
  the release checkout.

## Rerun semantics

Before publication, reruns may replace ephemeral CI artifacts. After registry
publication, the version is immutable: verify that the existing registry
object matches the intended package and continue only to missing readback
steps. Never interpret every nonzero lookup as "absent". GitHub Release
reconciliation must require the exact tag, final/non-draft state, notes, asset
set, and hashes before declaring success.

Do not automatically delete a registry version or GitHub Release during error
handling. Those are separate, explicitly authorized recovery operations.
