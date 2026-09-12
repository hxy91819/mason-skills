---
name: open-source-contribution
description: "Use before a public contribution push or PR, or when preparing public release hygiene, privacy cleanup, or repository security controls."
---

# Open Source Contribution

流程类 skill；保留仓库明确允许的隐式触发策略，也可通过 `$open-source-contribution` 显式调用。按当前任务选择下列分支。

Protect public commit identity, privacy, and the changed code's safety boundary. Ordinary contribution work covers its publish range and relevant checks. Initial release preparation or an explicit security-hardening request can additionally cover repository-wide controls.

## Publication checks

Before creating public commits, pushing, opening/updating a PR, or performing a server-side merge, read [public identity and privacy](references/publication-identity.md). It holds durable identity confirmation, file/metadata checks, and the separate GitHub merge-identity path. Reuse confirmed identity unless evidence conflicts.

- Preserve concurrent work and stage only the authorized scope. Existing user/repository authorization to commit, push, or update a PR remains valid; approval to edit locally alone does not authorize publication.
- Keep tokens, private keys, transcripts, private logs, internal identifiers, and unapproved corporate identity out of public content and commit metadata.
- If evidence reveals exposure in history, report it; rewriting history requires explicit authorization for that operation. Read [history cleanup](references/history-cleanup.md) only after that authorization.
- A blocker on identity or external publication does not block independent local edits and validation.

## Conditional work

| Task | Guidance |
| --- | --- |
| Initial public release, or requested dependency/CI/GitHub security controls | [Security baseline](references/security-baseline.md); preserve existing configuration and change remote settings only within the authorized repository and scope |
| Installer or service code changed | [Installer safety](references/installer-and-proxy.md#installer-and-service-safety) |
| HTTP proxy or streaming code changed | [Proxy safety](references/installer-and-proxy.md#proxy-and-streaming-safety) |
| Release-pipeline design or migration | Use the separately authorized `secure-release` workflow for protocol and adapters; this skill supplies publication hygiene |

Read only the matching branch. An ordinary push or review does not itself authorize adding release automation, Dependabot, CodeQL, repository topics, or remote security settings.

## Review and completion

Freeze the requested behavior, affected owner boundary, changed files, and relevant checks. Use the repository's actual validation commands for the changed surface. A documentation change needs documentation checks; a behavior change needs observable proof.

Inspect the final diff. Follow the repository's required review workflow, respecting explicit-only skills; if `autoreview` is requested or already authorized, use its convergence and scope-governor rules. Verify findings against real code before accepting them, fix in-scope causes, and rerun only checks/review invalidated by the fix. Follow-ups outside the task remain separate.

Complete when the requested change and relevant proof pass, publication privacy/identity checks pass when applicable, and authorized delivery is verified. Stop testing once that evidence is current. A new public contract, architecture decision, or release policy outside the request pauses only that affected action.

Report changed behavior, validation/privacy results, and any blocker. If pushed, include the branch and commit; if identity changed, say which configuration changed. Report history cleanup and residual exposure only when that branch was actually used.
