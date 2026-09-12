---
name: autoreview
description: "Use when the user invokes $autoreview to review local changes, a commit, or a branch/PR."
disable-model-invocation: true
triggers:
  - user
---

# Auto Review

这是流程类 Skill，默认仅在用户显式调用 `$autoreview` 时运行。审查用户指定的本地改动、commit 或 branch/PR。

Run the bundled structured review helper. This is code review, not Guardian `auto_review` approval routing. Use the configured engine and model; the built-in default is Codex, with optional engines described only when needed below.

Source review judges the change bundle. Validate changed user-visible behavior against its behavior contract as part of the implementation task; a clean source review alone does not prove the running result.

A prose-only internal note or Skill documentation edit does not require an external review unless requested. Inspect its diff and run relevant documentation checks. This exception does not cover executable examples, configuration, scripts, generated files, or behavior changes.

## Run and select references

Resolve `AUTOREVIEW` to this skill's `scripts/autoreview`; resolve `AUTOREVIEW_HARNESS` to `scripts/test-review-harness` only when testing the helper. On native Windows, invoke the extensionless helper through Python. Use `--help` for CLI parameters.

| When | Read |
| --- | --- |
| Setting installation paths, credential preflight, oversized bundles, or parallel tests | [Execution details](references/execution.md) |
| Choosing/configuring reviewers, panel or BB mode, resolving access failures/cooldowns, or exit 3 subagent handoff | [Engine rules](references/engines.md) |
| Changing or diagnosing helper implementation/isolation | [Runtime contract](references/helper-contract.md), [engine isolation](references/engines.md#review-engine-isolation) |
| Reviewing release/beta/hotfix/signing/publishing work | [Release boundary](references/release-review.md) before classifying findings |
| Changing audit suppression or tracing a regression's author/PR | [Specialized checks](references/specialized-checks.md) |

Run the helper directly; summarize its completed output without asking a second reviewer to repeat the same review.

## Pick Target

Dirty local work:

```bash
"$AUTOREVIEW" --mode local
```

Use this only when the patch is actually unstaged/staged/untracked in the
current checkout. `--mode uncommitted` is accepted as an alias for `--mode local`.
For committed, pushed, or PR work, point the helper at the commit
or branch diff instead; do not force dirty modes just
because the helper docs mention dirty work first. A clean local review
only proves there is no local patch.

Branch/PR work:

```bash
"$AUTOREVIEW" --mode branch --base origin/main
```

Optional review context is first-class. Prompt files and datasets must be repo-relative so review bundles cannot pull arbitrary host files:

```bash
"$AUTOREVIEW" --mode branch --base origin/main --prompt-file review-notes.md --dataset evidence.json
```

If an open PR exists, use its actual base:

```bash
base=$(gh pr view --json baseRefName --jq .baseRefName)
"$AUTOREVIEW" --mode branch --base "origin/$base"
```

Committed single change:

```bash
"$AUTOREVIEW" --mode commit --commit HEAD
```

Use commit review for already-landed or already-pushed work on `main`. Reviewing
clean `main` against `origin/main` is usually an empty diff after push. For a
small stack, review each commit explicitly or review the branch before merging
with `--base`.

## Contract

- Honor `--max-priority` and `AUTOREVIEW_MAX_PRIORITY`. Do not pass
  `--max-priority` unless the user asked for a specific threshold. Built-in
  default is P1 when neither is set. P0 means issues worth blocking the
  current change because they materially break the normal flow, outcome, or
  safety boundary; P1 means real defects in the changed code that should be
  fixed before shipping even if the main flow still works. Reviewers rate the
  same defect P0 or P1 inconsistently, so a P0-only threshold silently drops
  real bugs. Wider thresholds include those findings plus the extra
  priorities. Treat helper output at the configured threshold as the review
  result; do not drop in-threshold findings just because they are not P0.
- Treat review output as advisory. Never blindly apply it.
- The `subagent` engine is a non-independent review: the reviewer is the host agent, sharing the author model and context. Prefer codex/claude/pi whenever one is available, and keep the `reviewer independence: none (subagent shares the author model/context)` line in the final report.
- Close the feedback loop: after verifying findings, record each accepted/rejected decision with `--record-dispositions` (see Review History And Retrospective) so reviewer quality is measurable over time.
- Verify every finding by reading the real code path and adjacent files.
- Read dependency docs/source/types when the finding depends on external behavior.
- Reject unrealistic edge cases, speculative risks, unrelated rewrites, and fixes that over-complicate the codebase.
- Prefer root-cause fixes at the right ownership boundary. A coherent refactor is appropriate when it removes the bug class, duplicate policy, stale paths, or ownership confusion; do not default to a symptom patch.
- When an accepted finding exposes a bug class or repeated pattern, inspect its owner and relevant sibling implementations before fixing.
- Fix the same bug class across its owner-boundary neighborhood when practical; stop at unrelated invariants, different owners, and unapproved contract changes.
- Keep going until structured review returns no accepted/actionable findings only while the work remains inside the authorized architectural and task scope.
- If a review-triggered fix changes code, rerun focused tests and rerun the structured review helper.
- Preserve the requested engine/model. Use only the helper's documented access fallback, usage-limit cooldown, or missing-default-CLI fallback; read [engine rules](references/engines.md) when selecting overrides or resolving a failure.
- Be patient with large bundles. Structured review can take up to 30 minutes while the model call is active, especially with Codex tools or web search.
- Treat heartbeat lines like `review still running: ... elapsed=... pid=...` as healthy progress, not a hang. Let the helper continue while heartbeats are advancing. Pass `--stream-engine-output` when live engine text is useful; Codex and Claude filter tool/file chatter, other runnable engines pass raw output through.
- Do not kill a review just because it has been quiet for 2-5 minutes, or because it is still running under the 30-minute window. Inspect the process only after missing multiple expected heartbeats, after 30 minutes, or after an obviously failed subprocess; prefer letting the same helper command finish.
- If the repository changes while a bundle is being built or reviewed, keep the captured bundle's report, warn that it describes that snapshot, and preserve the concurrent changes. Do not discard an otherwise valid code review solely because another actor edited the worktree; rerun later when a report for the newer snapshot is needed.
- Tools are useful in review mode. Codex receives the validated bundle in an empty workspace so ignored files and linked-worktree metadata remain unreadable; web search stays available for dependency contracts and upstream docs. BB receives the bundle as an attachment in a temporary workspace outside the reviewed repository, but BB does not expose a per-thread host-read boundary; reserve it for trusted changes.
- Security perspective is always included, but it should not cripple legitimate functionality. Report security findings only when the change creates a concrete, actionable risk or removes an important safety check.
- Reviewer subprocesses preserve engine authentication and non-credentialed proxy variables needed by headless or restricted-network environments while stripping process-injection, Git override, and credentialed proxy values.
- The helper redacts locally recognized secrets and omits sensitive paths; prompt/dataset inputs are checked before invocation. Credential scanning is a separate, explicit preflight; see [execution details](references/execution.md#optional-credential-preflight) when required before commit, push, or external review.
- Do not invoke built-in `codex review`, nested reviewers, or reviewer panels from inside the review. The helper builds one validated bundle, calls the selected engine once for normal inputs or once per complete bounded chunk for oversized inputs, validates the structured results, and stops.
- Stop as soon as the helper exits 0 with no accepted/actionable findings. Do not run an extra review just to get a nicer "clean" line, a second opinion, or clearer closeout wording.
- Treat the helper's successful exit plus absence of actionable findings as the clean review result, even if the underlying Codex CLI output is terse.
- Multi-reviewer panels are opt-in only. Use them when explicitly requested or when risk justifies the extra spend; the main agent still verifies every accepted finding before fixing.
- If rejecting a finding as intentional/not worth fixing, add a brief inline code comment only when it explains a real invariant or ownership decision that future reviewers should know.
- Do not push just to review. Push only when the user requested push/ship/PR update.

## Scope Governor

Autoreview is a closeout gate, not permission to change the task's product contract. Define scope by the authorized invariant and its architectural owner, not by the first patch.

Before the first review, record a scope baseline: original request or issue, violated invariant, target branch, intended behavior, owner boundary, relevant sibling surfaces, and public/security/product contracts. Record changed files and non-test LOC as measurements, not hard caps. For inherited or already-bloated branches, distinguish the intended architectural fix from unrelated branch drift.

Before patching a finding, classify it:

- **In-scope blocker**: the finding affects the same violated invariant or owner-boundary neighborhood, including relevant sibling implementations and connected obsolete paths, and can be fixed without changing the task's contract.
- **Follow-up**: the finding is real but belongs to an unrelated bug class, different owner, independent cleanup, or broader hardening track.
- **Stop-and-escalate**: the finding requires a new protocol/config/storage/public API contract, a different owner boundary, a release-process change, or a design choice outside the original request.

Stop patching and report the scope break instead of continuing when:

- a task turns into an unauthorized product, protocol, migration, storage, security, or release-process change;
- added files or production LOC no longer serve the authorized invariant, owner boundary, or meaningful simplification; file counts, initial diff size, and arbitrary LOC multipliers are never automatic stop conditions;
- two review-triggered patch cycles have not converged; pause and reclassify every remaining finding before another edit;
- the best fix is "define the canonical contract first" rather than another local inference layer;
- fixing the accepted finding would make the PR no longer describe the same behavior, issue, or owner boundary.

After the two-cycle pause, continue only when every remaining accepted finding is still an in-scope blocker. Otherwise preserve the useful analysis, identify a coherent root-cause-safe landed subset if one exists, and open or request a follow-up for unrelated work. Do not land a symptom patch or keep committing speculative fixes just to satisfy the reviewer.

Do not stack or push review-triggered fix commits while scope classification or focused proof is unresolved. Keep exploratory edits local until the cycle is proven in scope; if scope breaks, remove them from the landing lane instead of preserving them as branch history.

Critical exceptions must be explicit: active data loss, crash, broken install/upgrade, release blocker, or concrete security exposure. If the exception is not one of those, it is not critical enough to blow up scope.

## Review History And Retrospective

The helper records a minimal, git-ignored local history (mirroring the large-task-orchestrator pattern): one entry per (run, reviewer) with engine, model, thinking, fallback usage, duration, outcome, and per-finding ids. Prompts, finding bodies, diffs, and logs are never recorded; recording failures never change the review result.

After verifying findings, record the main agent's decisions so future retrospectives can measure reviewer quality:

```bash
python3 "$AUTOREVIEW" --record-dispositions \
  --run-id 20260902T121310Z-376faf \
  --disposition "aae57af1d9=accepted:real traversal bug" \
  --disposition "b7c3d2e1f0=rejected:speculative, path already guarded"
```

- The run id is printed as `history run: <id>` at review start; finding ids appear as `[P1:<id>]` in the report.
- Record every accepted finding and every rejected finding with a brief reason; re-recording a finding id overwrites its earlier decision.
- When choosing or re-confirming a reviewer (engine, model, thinking), read `--history-summary` first: acceptance rate, fallback frequency, and average duration per `engine|model|thinking` are the selection signals; hooks flag low-acceptance reviewers and frequently-falling-back primaries.
- History lives in `AUTOREVIEW_STATE_DIR` (default `~/.cache/autoreview`), stays outside the reviewed repository, is never committed, and keeps only the last 200 runs plus fixed-dimension rollups.

## Final Report

Include:

- review command used and the history run id
- tests/proof run
- findings accepted/rejected, briefly why
- the clean review result from the final helper/review run, or why a remaining finding was consciously rejected
- for `subagent` runs, the `reviewer independence: none (subagent shares the author model/context)` line, so the reader knows the review was not independent
- for BB runs, the printed `bb review thread` id and `reviewer isolation: none` line

Do not run another review solely to improve the final report wording. If the final helper run exited 0 and produced no accepted/actionable findings, report that exact run as clean.
