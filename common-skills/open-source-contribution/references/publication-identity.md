# Public identity and privacy checks

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

Before public push or PR, scan the actual publish range and its Git metadata.
For initial publication or an explicit history audit, include the whole repository
and reachable history. Keep existing baseline findings distinct from new exposure;
an unchanged baseline finding is not evidence that the current patch introduced it.

File content checks:

```bash
git grep -l -I -E '(PRIVATE_TOKEN|AUTH_TOKEN|API_KEY|SECRET|PASSWORD|Bearer |ghp_|github_pat_|sk-[A-Za-z0-9_-]+|BEGIN .*PRIVATE KEY)' HEAD -- . || true
git grep -l -I -E '(/root/|/home/[^ /]+|/Users/[^ /]+|/data/code|@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}|internal|private)' HEAD -- . || true
gitleaks detect --no-git --redact --no-banner --source .
```

The grep commands list candidate paths only; avoid printing matching secret values.
For a committed contribution, use the scanner's Git-range option with the actual
base/head instead of scanning unrelated working files. Report scanner coverage and
verified fixture findings separately; do not suppress unknown matches to obtain a pass.

Metadata checks:

```bash
python3 {baseDirectory}/scripts/check_identity.py
git remote -v
gh repo view --json visibility,description,url,repositoryTopics 2>/dev/null || true
```

The script checks repository-local `user.name`/`user.email` and every
author/committer in history against the approved identity, and cross-checks the
GitHub login via `gh` when available. A corporate ID used as an author name (a
company username that differs from the GitHub login) is a must-fix finding even
when the email is already personal. Override the defaults with `--name`,
`--email`, `--github-login`, `--allowed-name`, `--prohibited-email`, and
`--prohibited-name` for accounts other than Mason's.

Before creating public commits, check the repository-local Git identity and
commit history:

1. Check the repository-local identity with the identity check script
   (`python3 {baseDirectory}/scripts/check_identity.py`). When it reports a
   missing or non-approved local `user.name`/`user.email`, configure them
   directly without asking and report the change in the final report:

   ```bash
   git config --local user.name 'approved-github-login'
   git config --local user.email 'approved-open-source-address@example.com'
   git config --local user.useConfigOnly true
   ```

2. Scan commit history for prohibited names and addresses. When any commit
   uses a company email or corporate ID, ask the user whether to rewrite
   history. Rewrite only after explicit user confirmation; never rewrite on the
   agent's own initiative. When the user confirms, follow [Git History Cleanup](history-cleanup.md)
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
