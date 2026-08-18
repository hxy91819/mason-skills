# Adapter contract and status

An adapter owns only four ecosystem operations: `build/package`, `inspect`,
`publish`, and `registry smoke`. The core owns source identity, changelog,
manifest/hash, artifact handoff, permissions, and GitHub Release readback.

| Ecosystem | Status in kit v1 | Evidence required before promotion |
|---|---|---|
| npm | **Implemented** | Unit-tested pack/manifest logic; exact tarball publish; recognized-404 absence check; clean install smoke; OIDC-compatible npm invocation |
| PyPI | Not implemented | Build wheel/sdist once, inspect metadata, Trusted Publisher upload, exact-version JSON/install smoke |
| Cargo | Not implemented | Deterministic crate package inspection, crates.io Trusted Publishing path, exact-version fetch/build smoke |
| Go/GitHub binaries | Not implemented | Reproducible target matrix, archive layout contract, checksums, platform smoke, exact GitHub asset readback |
| Container | Not implemented | OCI build output identity, digest-first signing/attestation policy, registry OIDC, pull-by-digest smoke |

Do not emulate an unsupported adapter with ad hoc shell embedded in a release
job and then label it supported. First add a versioned adapter command, offline
fixtures, negative tests, a thin workflow example, and registry readback proof.

## npm v1 assumptions

- One public package with a committed `package-lock.json` and stable `vX.Y.Z`
  tags whose suffix equals `package.json` version.
- `npm pack --json` emits exactly one tarball. The adapter rejects symlinks and
  unexpected multiple outputs before creating the manifest.
- `npm view` absence succeeds only for a recognizable `E404`; authentication,
  DNS, timeout, throttling, and malformed output fail closed.
- A post-publish rerun downloads the exact existing package tarball and requires
  byte-for-byte SHA-256 equality before continuing; it never republishes.
- Publish receives the exact tarball path and requests provenance. The publish
  job supplies OIDC through GitHub Actions and a pinned npm CLI version.
- Smoke first resolves exact metadata, then installs `name@version` in a clean
  temporary consumer and checks the installed package version.

Scoped private packages, workspaces, prereleases, dist-tag promotion, custom
registries with different error contracts, and lifecycle-script smoke require
explicit extensions and tests; kit v1 does not claim them.
