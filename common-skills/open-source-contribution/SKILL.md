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
  secrets, private service names, or corporate/internal email addresses.
- Use a user-approved personal open-source email or GitHub noreply address for
  public commit authors and committers. Treat employer/corporate addresses as
  prohibited even when they are already configured globally or locally.
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

## GitHub Merge Email Gate

Treat GitHub-generated merge and squash commits as a separate identity path:
local `git config user.email` does not control their author email.

Before the first server-side merge for an account:

1. Identify the approved personal address. For Mason's public repositories,
   use `masonxhuang@proton.me`; employer addresses are prohibited.
2. Verify that GitHub **Settings → Emails → Primary email address** uses the
   approved address. The public `email` returned by `gh api user` is not proof
   of the account's primary email.
3. If available, cross-check with `gh api user/emails` and require the approved
   address to have `primary: true` and `verified: true`. This endpoint needs the
   `user` OAuth scope; do not broaden authentication scopes automatically.
4. When the primary-email state cannot be verified, pause the server-side
   merge and ask the user to confirm the GitHub setting. Do not infer it from
   repository-local Git configuration.

After every server-side merge, resolve the merge SHA and inspect the raw commit
metadata through the GitHub commits API. Confirm that the author is the
approved address or an approved GitHub noreply address before declaring the
merge complete. GitHub's `noreply@github.com` committer on web-generated commits
is expected. A prohibited author email is a privacy incident; report it and
obtain explicit approval before rewriting published history.

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
git config --get user.email
git log --format='%h %an <%ae> | %cn <%ce>' --all
git remote -v
gh repo view --json visibility,description,url,repositoryTopics 2>/dev/null || true
```

Before creating public commits, replace an employer/corporate Git email with a
repository-local, user-approved personal open-source address:

```bash
git config --local user.email 'approved-open-source-address@example.com'
```

If unpushed commits already contain a prohibited address, obtain explicit user
approval before rewriting their author and committer metadata. Verify the
rewritten publish range before pushing; do not treat a scanner-only pass as
sufficient metadata validation.

Classify findings:

- **Must fix**: real tokens, private keys, company/internal emails, local
  transcripts, private logs, hidden binary artifacts, sensitive hostnames.
- **Usually fix**: absolute local paths, usernames, old private project names,
  machine-specific service names, corporate copyright holder strings.
- **Acceptable when intentional**: user-approved personal open-source or GitHub
  noreply email, public GitHub username in clone URLs, documented public
  repository URL, public maintainer identity.

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
- Tests, lint, gitleaks, and autoreview command/result.
- Git history rewrite details if performed.
- Remote URL, branch, and final commit SHA if pushed.
- Any residual risk, especially GitHub cache/history caveats after force-push.
