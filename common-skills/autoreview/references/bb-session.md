# BB session engine

Use this mode from an active BB thread when the review should run as a fresh BB
session instead of a direct reviewer CLI process:

```bash
"$AUTOREVIEW" --engine bb --bb-trusted-input --mode local
```

The helper reads the invoking thread's latest recorded execution and carries its
provider, model, reasoning level, and service tier into the review thread. An
explicit `--model bb=<model>` or `--thinking bb=<level>` overrides the matching
inherited value. `AUTOREVIEW_BB_MODEL` and `AUTOREVIEW_BB_THINKING` provide the
same overrides through the existing per-engine environment convention.

BB mode requires `BB_THREAD_ID` and a reachable BB CLI. Use `--bb-bin` or
`AUTOREVIEW_BB_BIN` to select the CLI; otherwise the helper uses `BB_CLI`, then
`bb` from the trusted executable path. `--bb-timeout` or
`AUTOREVIEW_BB_TIMEOUT_SECONDS` controls the wait, with a 30-minute default.
BB validates inherited or overridden reasoning values against the selected
provider rather than autoreview maintaining a stale local allowlist.
`--no-tools` is unavailable because the reviewer must read the prompt file from
its temporary workspace and BB does not expose a prompt-file-only tool flag.

## Non-isolation and lifecycle

The review thread is a hidden root thread, not a child. This prevents its
completion notification from steering the invoking turn while the helper is
waiting. It runs on the current BB host in a temporary Git workspace outside
the reviewed repository, with `auto` permission mode so the hidden worker does
not wait for an interaction that no user can see. The validated,
redacted review prompt is attached from that workspace, and the worker is
instructed to use read-only tools only to open that file.

This is context separation, not a host-read security boundary. BB does not
currently expose a per-thread no-tools or read-root control, so session tools
may read beyond the temporary workspace. Use BB mode only for trusted changes
on a host where that exposure is acceptable; use Codex, Claude, or Pi engine
isolation for untrusted diffs. Keep the helper's
`reviewer isolation: none (BB session tools are not confined to the review bundle)`
line in the final report.

`--bb-trusted-input` is mandatory and has no persistent environment shortcut.
It asserts that every changed line plus all explicit prompt and dataset content
comes from trusted parties. Without it, the helper fails before bundle creation
or thread spawn. Selecting BB for an external or otherwise untrusted PR is not
a valid use of the flag.

The helper waits for the review turn's terminal `turn/completed` event, reads
`bb thread output`, then passes that text through the same schema validation,
priority filtering, finding IDs, exit status, and history path as other
engines. It deliberately does not use thread `idle` as the completion signal:
provider continuation or automatic compaction can make that status transient.
It prints `bb review thread: <id>` for traceability. The resolved model and
reasoning level are recorded in review history.

After success or failure, the helper archives and stops the hidden thread.
Cleanup failures are warnings and do not replace a valid review result. Spawn,
wait, or output failures fail the review closed. The temporary workspace is
removed when the engine returns.

BB is opt-in and is not included in `--reviewers all`. It may be selected
explicitly in a panel, but a single BB reviewer is the normal session-mode use.

## Proof

Run the deterministic local self-test, then a real BB fixture from an active BB
thread:

```bash
"$AUTOREVIEW" --self-test
"$AUTOREVIEW_HARNESS" --fixture benign --engine bb
```

The real fixture should print the inherited session configuration and thread
ID, finish with `autoreview clean`, and leave the hidden review thread archived
and stopped.
