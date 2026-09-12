# Initial public release and security baseline

Use when initial publication or a repository-security task includes these controls. An ordinary contribution does not require rebuilding this baseline.

## Repository Hygiene

Minimum public repository baseline:

- `README.md` explains purpose, install, usage, verification, and maintenance.
- `LICENSE` uses the intended public copyright holder.
- `SECURITY.md` explains how to handle vulnerabilities and what not to commit.
- `.gitignore` excludes build output, logs, `.env*`, keys, certificates, and
  temp files.
- CI runs formatting, tests, build, and script syntax checks.
- Optional pre-commit runs secret scanning, file hygiene, formatting, vet/test,
  and lint.

## Baseline Repository Security

Make dependency maintenance and GitHub-native/CI security part of the default
public-release workflow. Reconcile existing configuration instead of replacing
customized Dependabot, CodeQL, scanner, or audit policy.

Complete safe local baseline work while unrelated identity, copyright, history,
or publication choices are pending. Those choices may block their own files or
remote publication, but not independent Dependabot and CI security changes.

### Discover And Plan

1. Inspect manifests, lockfiles, existing workflows, scanner configuration,
   repository visibility, default branch, and current GitHub security settings.
2. Map every present package ecosystem supported by Dependabot and always add
   `github-actions` when the repository uses GitHub. Use the repository's
   actual manifest directory for monorepos; do not infer one root entry when
   packages live in multiple directories.
3. Detect the package manager from its lockfile and existing CI setup. Select a
   lockfile-preserving install and matching audit command; never regenerate or
   relax a frozen lockfile merely to make an audit pass.
4. Record the intended file changes and remote setting changes separately.
   Confirm the target repository before any remote mutation. A request limited
   to local preparation authorizes file changes only; report remote settings as
   pending.

Complete discovery only when every manifest and lockfile is accounted for,
existing security automation has been reconciled, and each planned remote
change is classified as already enabled, missing, unsupported, or unauthorized.

### Configure Dependency Maintenance

Create or reconcile `.github/dependabot.yml` with:

- one entry for every supported ecosystem and manifest directory present;
- a `github-actions` entry;
- a bounded weekly schedule and `open-pull-requests-limit`;
- grouped routine minor/patch development updates where that ecosystem supports
  grouping; constrain dependency groups to the development dependency type
  rather than grouping all dependencies, and leave security updates visible
  and actionable.

Enable Dependabot vulnerability alerts and security updates when the
authenticated operator has repository-administration authority and remote
configuration is in scope. Inspect first, apply only missing settings, then
read them back. Report plan, repository, or permission limitations precisely.

### Configure GitHub And CI Security

- Prefer GitHub CodeQL default setup when GitHub supports the repository and
  detected languages. Select only languages actually present and use an
  appropriate maintained query suite. Add a least-privilege maintained CodeQL
  workflow only when default setup is unavailable or repository requirements
  make it unsuitable. Verify the selected languages and first analysis run.
- Enable secret scanning and push protection when supported and authorized.
  Inspect, apply only missing settings, and verify the resulting state. Treat
  private-repository plan limitations and permission failures as explicit
  incomplete coverage.
- Run one maintained secret scanner on every `push` and `pull_request`. Reuse
  existing scanner configuration and jobs; avoid duplicate scanners. Give the
  workflow only required permissions, disable checkout credential persistence
  where practical, prefer the event-scoped `${{ github.token }}` over a
  repository secret when the scanner needs a token, and ensure fork pull
  requests do not receive repository secrets or other privileged credentials.
- Run the ecosystem-appropriate dependency audit on every `push` and
  `pull_request`, after the repository's frozen/immutable install. Reuse an
  existing audit job when present. Examples include `npm audit` for
  `package-lock.json`, `pnpm audit` for `pnpm-lock.yaml`, the matching Yarn or
  Bun audit for their lockfiles, `pip-audit` for locked Python dependencies,
  `bundle audit`, `govulncheck`, `cargo audit`, `composer audit`, and the
  repository's established Maven, Gradle, or NuGet audit tooling. Pin or manage
  added audit tools through the project's existing dependency/tooling policy.
  Audit all resolved production and development dependencies unless the
  repository documents a narrower security policy.

Do not add Codex Security installation to this baseline. It is independent of
repository-native dependency, secret, and CodeQL controls.

### Verify Security Baseline

1. Validate every changed YAML file and run `git diff --check`.
2. Record the pre-test status and digest of every lockfile. Run the secret
   scanner and each dependency audit locally or in an equivalent isolated
   environment. Require lockfiles to remain byte-for-byte unchanged; if a tool
   rewrites one, remove only the mutation created by this verification and
   report the command as incompatible with frozen verification.
3. After an authorized push, verify the first CI and CodeQL runs and inspect
   their jobs, conclusions, and annotations or alerts.
4. Report three independent outcomes: configuration state, workflow/run state,
   and finding count with severities. A successful scanner run proves the
   scanner executed; it does not prove that the repository has zero findings.

The baseline is complete only when local configuration is validated, every
authorized remote setting is verified or explicitly reported as unavailable,
and the first available CI/CodeQL evidence and findings are reported without
equating execution success with a clean result.

For GitHub discoverability, set a search-friendly description containing the
main product names, integration surface, and key problem solved. Add topics for
tools, protocols, model names, and domain.
