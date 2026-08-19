---
name: open-source-contribution
description: Standardizes open-source contribution and release hygiene for coding agents. Use when preparing a project for public release, contributing to a public repository, cleaning private/local information before publishing, rewriting Git history for privacy, hardening install scripts/services, running autoreview, or validating a repository before push/PR.
---

# Open Source Contribution

Use this skill when helping a user publish, clean up, or contribute to an
open-source repository. The default posture is conservative: protect privacy,
preserve user work, keep the patch small, and prove the repository is safe to
push.

## Core Rules

- Never expose tokens, private keys, prompt logs, local transcripts, shell
  secrets, private service names, corporate/internal email addresses, or
  corporate identifiers (employee IDs, company usernames) as commit author
  names.
- Use a user-approved personal open-source email or GitHub noreply address for
  public commit authors and committers. Treat employer/corporate addresses as
  prohibited even when they are already configured globally or locally.
- Match the public author name to the GitHub account: use the GitHub login or
  an approved display name. Treat a corporate ID configured as `user.name` as
  prohibited even when it is already configured globally or locally.
- Treat Git commit metadata as public data. Secret scanners do not catch author
  and committer names/emails.
- Do not rewrite history unless the user explicitly allows it. If allowed, use
  force-with-lease and verify the remote head afterward.
- Do not push just to test. Push only when the user requested publish, ship, or
  PR update.
- When adding install/service scripts, assume they may run as root. Validate all
  user-controlled path/name inputs before interpolating them into filesystem
  paths or service manager commands.
- Run review after non-trivial changes. Treat review findings as advisory, then
  independently verify and fix only real, in-scope issues.

## Secure Release Routing

When the task includes designing, migrating, or validating a registry or
GitHub release pipeline, use the `secure-release` skill for the release
protocol, runtime kit, ecosystem adapter, and rerun semantics. Keep this skill
for public-repository privacy, identity, security baseline, review, and push/PR
hygiene. Apply both sets of completion gates without copying the detailed
release protocol into this file.

## GitHub Merge Identity Gate

Treat GitHub-generated merge and squash commits as a separate identity path:
local `git config user.name` and `user.email` do not control their author
identity.

Treat an explicitly approved personal identity recorded in this skill or by the
user as durable account-level confirmation. Reuse it across repositories and
future PRs without asking again unless the user revokes it, evidence conflicts
with it, or post-merge metadata violates it. For Mason's public repositories,
the approved identity is GitHub account `hxy91819` with email
`masonxhuang@proton.me`; employer addresses and corporate IDs used as author
names (such as `masonxhuang`, Mason's company ID) are prohibited.

Before a server-side merge:

1. Use the durable approved identity (GitHub login and email) when one is
   recorded. For an account with no durable confirmation, ask once for the
   GitHub account login and **Settings → Emails → Primary email address**, and
   record the approved personal identity.
2. If available, cross-check with `gh api user/emails` and require the approved
   address to have `primary: true` and `verified: true`. This endpoint needs the
   `user` OAuth scope; do not broaden authentication scopes automatically.
3. Treat a missing `user` scope or unavailable email API as unavailable
   corroboration, not as a blocker, when durable confirmation already exists.
4. Pause only when no durable confirmation exists or available evidence
   conflicts with the approved address. The public `email` returned by
   `gh api user` and repository-local Git configuration are not substitutes for
   first-time confirmation.

After every server-side merge, resolve the merge SHA and inspect the raw commit
metadata through the GitHub commits API. Confirm that the author name is the
approved GitHub login (or an approved display name) and the author email is the
approved address or an approved GitHub noreply address before declaring the
merge complete. GitHub's `noreply@github.com` committer on web-generated commits
is expected. A prohibited author name or email is a privacy incident; report it
and obtain explicit approval before rewriting published history.

## Privacy Review

Before public push or PR, scan both tracked files and Git metadata.

File content checks:

```bash
git grep -n -I -E '(PRIVATE_TOKEN|AUTH_TOKEN|API_KEY|SECRET|PASSWORD|Bearer |ghp_|github_pat_|sk-[A-Za-z0-9_-]+|BEGIN .*PRIVATE KEY)' HEAD -- . || true
git grep -n -I -E '(/root/|/home/[^ /]+|/Users/[^ /]+|/data/code|@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}|internal|private)' HEAD -- . || true
gitleaks detect --no-git --redact --no-banner --source .
```

Metadata checks:

```bash
git config --get user.name
git config --get user.email
git log --format='%h %an <%ae> | %cn <%ce>' --all
gh api user --jq '.login' 2>/dev/null || true
git remote -v
gh repo view --json visibility,description,url,repositoryTopics 2>/dev/null || true
```

Compare every author/committer name and email in the log against the approved
GitHub identity. A corporate ID used as an author name (a company username that
differs from the GitHub login) is a must-fix finding even when the email is
already personal.

Before creating public commits, check the repository-local Git identity and
commit history:

1. Check the repository-local identity:

   ```bash
   git config --local --get user.name
   git config --local --get user.email
   ```

   When either is missing or not the approved personal identity, configure it
   directly without asking and report the change in the final report:

   ```bash
   git config --local user.name 'approved-github-login'
   git config --local user.email 'approved-open-source-address@example.com'
   git config --local user.useConfigOnly true
   ```

2. Scan commit history for prohibited names and addresses. When any commit
   uses a company email or corporate ID, ask the user whether to rewrite
   history. Rewrite only after explicit user confirmation; never rewrite on the
   agent's own initiative. When the user confirms, follow Git History Cleanup
   and verify the rewritten publish range before pushing; do not treat a
   scanner-only pass as sufficient metadata validation.

Classify findings:

- **Must fix**: real tokens, private keys, company/internal emails, corporate
  IDs or company usernames used as commit author names, local transcripts,
  private logs, hidden binary artifacts, sensitive hostnames.
- **Usually fix**: absolute local paths, usernames, old private project names,
  machine-specific service names, corporate copyright holder strings.
- **Acceptable when intentional**: user-approved personal open-source or GitHub
  noreply email, user-approved GitHub login as author name, public GitHub
  username in clone URLs, documented public repository URL, public maintainer
  identity.

## Git History Cleanup

Use only with explicit user approval.

For a new repository, prefer squashing to a clean single root commit:

```bash
git switch --orphan sanitized-main
git rm -r --cached . >/dev/null 2>&1 || true
git add -A
GIT_AUTHOR_NAME='public-name' \
GIT_AUTHOR_EMAIL='public-name@users.noreply.github.com' \
GIT_COMMITTER_NAME='public-name' \
GIT_COMMITTER_EMAIL='public-name@users.noreply.github.com' \
  git commit -m 'Initial open source release'
git branch -D main
git branch -m main
git push --force-with-lease origin main
```

Before force-push:

- Confirm `git status --short --ignored` does not show important untracked
  source files.
- Confirm ignored build outputs, such as `bin/` or `dist/`, are not tracked.
- Run `git ls-files` and inspect the file list.

After force-push:

```bash
git ls-remote --heads origin main
git log --format='%h %an <%ae> | %cn <%ce>' --all
git reflog expire --expire=now --all
git gc --prune=now
```

Then verify old sensitive commits are no longer present locally when their SHAs
are known:

```bash
git cat-file -e OLD_SHA^{commit} 2>/dev/null && echo "old commit still exists"
```

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

## Installer And Service Safety

When reviewing install scripts or services, check these bug classes:

- A root service must not execute a binary from a user-writable checkout.
- `ProtectHome=true` breaks services whose `ExecStart` points into `~/...`.
- If side-by-side services are supported, each service needs its own installed
  binary path. Do not make all units point at one shared global binary unless
  that is the documented contract.
- Validate service names, labels, paths, and unit filenames before using them
  in `rm`, `install`, `systemctl`, `launchctl`, or template substitution.
- Reject or safely escape whitespace, `%`, path separators, `..`, and shell
  metacharacters in values that enter service files.
- Uninstall paths need the same validation as install paths.

Prefer service-specific, root-owned install paths for system services, for
example:

```text
/usr/local/lib/<project>/<service-id>/<binary>
```

## Proxy And Streaming Safety

For HTTP proxy projects used by interactive agents:

- Do not log prompts, response bodies, authorization headers, or tokens.
- Copy hop-by-hop headers carefully.
- Preserve streaming semantics. If using `net/http` directly, flush writable
  chunks when `http.Flusher` is available.
- Add focused tests for request mutation and streaming/flush behavior.
- Keep default bind address on `127.0.0.1` unless remote access is explicit and
  secured.

## Review Workflow

Before review, freeze scope: user request, changed files, intended behavior,
security boundary, and tests.

Run focused proof first:

```bash
go test ./...
gitleaks detect --no-git --redact --no-banner --source .
pre-commit run --all-files
```

Then run the project's autoreview helper if available. If a finding is
accepted:

1. Verify it against real code.
2. Fix the smallest in-scope bug class.
3. Add or update a focused test when practical.
4. Rerun focused proof and autoreview.
5. Stop when autoreview reports no accepted/actionable findings.

Do not keep widening scope to satisfy speculative findings. Escalate when the
fix requires a new public contract, release policy, or architecture decision.

## Final Report

Include:

- Files changed and why.
- Privacy checks run and their result.
- Repository-local Git identity changes made (user.name/user.email configured
  to the approved personal identity).
- Tests, lint, gitleaks, and autoreview command/result.
- Git history rewrite details if performed.
- Remote URL, branch, and final commit SHA if pushed.
- Any residual risk, especially GitHub cache/history caveats after force-push.
