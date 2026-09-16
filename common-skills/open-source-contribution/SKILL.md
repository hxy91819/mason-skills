---
name: open-source-contribution
description: Protect public contribution and publication privacy and Git identity when contributing to a public repository, preparing a public release, or checking files and history before public publication. Not for ordinary autoreview or PR validation without a public contribution or publication context.
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

## Task References

Read only the branches needed for the authorized public contribution or
publication task. Ordinary code review, autoreview, or a PR in an unspecified
repository does not itself start this workflow. Reading a reference does not
expand permission to change repository settings, rewrite history, publish, or
merge.

- Before public commits, push, or PR, read [identity and privacy](references/identity-and-privacy.md)
  for file/metadata checks and the existing [identity checker](scripts/check_identity.py).
  The same reference covers GitHub-generated identity before and after an
  authorized server-side merge; preparing a PR does not authorize merging it.
- Only for explicitly approved history cleanup, read [history cleanup](references/history-cleanup.md).
  Preserve its force-with-lease, verification, and residual-exposure safeguards.
- For public-release preparation or requested repository security baseline work,
  read [repository hygiene and security baseline](references/security-baseline.md).
  A focused contribution does not authorize adding a new repository-wide baseline.
- When the public patch changes installers or services, read [installer and service safety](references/installer-safety.md).
- When the public patch changes an interactive-agent HTTP proxy, read [proxy and streaming safety](references/proxy-safety.md).

## Secure Release Routing

For an authorized task designing, migrating, or validating a registry or GitHub
release pipeline, consult the sibling [secure-release](../secure-release/SKILL.md)
for protocol, runtime kit, ecosystem adapter, and rerun semantics. It lives in
this repository's `common-skills/secure-release`, not necessarily in the global
skill installation. Resolve the actual directory containing this skill's
`SKILL.md` (follow symlinks), then check the sibling files, for example:

```bash
test -r "{baseDirectory}/../secure-release/SKILL.md"
test -r "{baseDirectory}/../secure-release/references/protocol.md"
test -r "{baseDirectory}/../secure-release/references/adapters.md"
```

Read its linked resources only for the selected branch and verify the selected
kit/adapter is present before using it. If this skill was copied without the
sibling or required assets are missing, report the exact missing dependency and
pause the dependent release work; obtain a complete trusted repository checkout
or a user-provided verified location before continuing. Do not silently install
it, pretend it is globally available, or replace its release gates with a
privacy scan.

`secure-release` remains an explicit-only workflow. Consulting its protocol as
reference for an already authorized task does not invoke the independent
workflow or authorize publication, credentials, remote configuration, or a
migration cutover. When that workflow is explicitly started, apply both sets of
completion gates. Keep public privacy/identity checks here and detailed release
protocol there.

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
