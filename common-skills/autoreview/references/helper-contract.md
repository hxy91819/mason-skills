# Helper runtime contract

## Helper

After setting `AUTOREVIEW` and `AUTOREVIEW_HARNESS` above:

```bash
"$AUTOREVIEW" --help
```

The smoke harness has thin shell wrappers over a shared Python implementation:

```bash
"$AUTOREVIEW_HARNESS" --fixture benign --engine codex
```

On native Windows, invoke the extensionless Python helper through Python:

```powershell
python $AUTOREVIEW --help
```

and the smoke harness:

```powershell
& $AUTOREVIEW_HARNESS -Fixture benign -Engine codex
```

The helper:

- chooses dirty local changes first
- accepts `--mode uncommitted` as an alias for `--mode local`
- otherwise uses current PR base if `gh pr view` works
- otherwise uses `origin/main` for non-main branches
- does not fetch automatically during branch review; the selected base ref must already resolve locally
- recognizes `--engine droid`, `copilot`, `cursor`, and `opencode` only to fail closed with isolation errors; runnable engines are `codex`, `claude`, `pi`, and `bb`, plus the non-independent `subagent` engine; default is `AUTOREVIEW_ENGINE` or `codex`
- resolves bare `git`, `gh`, reviewer, and PowerShell shell commands from absolute `PATH` entries only, never from the reviewed checkout; explicit `--*-bin` paths are interpreted from the reviewed repository root when relative and accepted only when both the supplied path and resolved target stay outside the reviewed repository
- use `--mode commit --commit <ref>` for already-committed work, especially clean `main` after landing
- scans safe Git patches in full, recognizes synthetic fixture values tied to their credential field, reviews them in one pass up to the aggregate prompt limit, and automatically uses complete bounded passes above it
- should be left in `--mode auto` or forced to `--mode branch` for PR/branch work; do not force `--mode local` after committing
- writes only to stdout unless `--output`, `--json-output`, or live streamed engine stderr is set
- supports `--dry-run`, `--parallel-tests`, `--parallel-tests-shell`, `--prompt`, repo-relative `--prompt-file`, repo-relative `--dataset`, `--no-tools`, `--no-web-search`, repeatable Codex-only safe model/response tuning with `--codex-config key=value`, Codex-only `--codex-speed fast|flex|default`, BB session selection with `--bb-bin`/`--bb-timeout` plus the required per-run `--bb-trusted-input` gate, and commit refs
- supports `--stream-engine-output` or `AUTOREVIEW_STREAM_ENGINE_OUTPUT=1` for live engine text while preserving structured validation; Codex and Claude hide tool/file event details, emit compact activity summaries, and report usage at turn completion
- supports opt-in review panels with `--panel` / `--reviewers`, plus per-engine `--model`, `--thinking`, and Claude/pi `--fallback-model`
- uses built-in defaults `codex=gpt-5.6-sol` with `high` reasoning and an access-only `gpt-5.6-terra` retry; Claude inherits the current Claude Code model and effort unless `--model`/`--thinking` or env overrides are set; honors `AUTOREVIEW_MODEL`, `AUTOREVIEW_THINKING`, `AUTOREVIEW_MAX_PRIORITY`, `AUTOREVIEW_FALLBACK_MODEL`, and per-engine `AUTOREVIEW_<ENGINE>_MODEL` / `AUTOREVIEW_<ENGINE>_THINKING` environment overrides when CLI flags are omitted
- after a Codex usage-limit failure, records a fixed cooldown (default 1 hour) outside the reviewed repository and skips Codex on later runs, switching a Codex-only review to Claude; `--ignore-codex-cooldown` or `AUTOREVIEW_IGNORE_CODEX_COOLDOWN=1` forces Codex
- forwards a custom Codex `model_provider` from `CODEX_HOME/config.toml` (allowlisted keys plus `env_key`/`auth.command` credentials) so `--ignore-user-config` does not silently route the review to api.openai.com
- gives Codex the bundle in an empty workspace with web search available; Claude receives the bundle plus WebSearch by default and optional domain-constrained WebFetch, and Pi receives the bundle with no tools
- runs Claude with `--safe-mode` (`v2.1.169+`), `--setting-sources user`, MCP and auto-memory disabled, no filesystem/shell tools, an empty external workspace, and `--fallback-model` when set; omits `--model`/`--effort` by default so user Claude Code model selection still applies
- refuses Droid, Copilot, Cursor, and OpenCode reviews until their CLIs expose the required project, filesystem, and network isolation
- runs Pi `v0.79.0+` from neutral temporary directories with `--no-approve`, `--no-session`, disabled Pi context/resource loading, and `--no-tools` because its built-in read tools are not repository-confined; when a `--fallback-model`/`AUTOREVIEW_PI_FALLBACK_MODEL` is set and the primary run fails with a provider-availability error, retries once with the fallback model
- runs BB reviews as non-host-read-isolated hidden root threads in a temporary external Git workspace, inherits the invoking thread's provider/model/reasoning/service tier unless model or thinking is explicitly overridden, delegates reasoning validation to BB, reads the final output through `bb thread output`, and archives/stops the worker on every terminal path
- prints `review still running: <engine> elapsed=<seconds>s pid=<pid>` to stderr at long-running intervals while waiting for the selected review engine, unless streamed output or compact Codex activity has been visible recently
- prints `autoreview clean: no accepted/actionable findings reported` when the selected review command exits 0
- records one review-history entry per (run, reviewer) in a git-ignored local cache under `AUTOREVIEW_STATE_DIR` (default `~/.cache/autoreview/run-history.json`): engine, model, thinking, fallback usage, duration, outcome, and each finding's stable id, priority, category, and location — never prompts, bodies, diffs, or logs; `--history-summary` aggregates acceptance rates and retrospective hooks, and `--record-dispositions --run-id <id> --disposition <finding-id>=accepted|rejected[:reason]` records the main agent's per-finding decisions
- supports `--engine subagent` for a zero-config, non-independent review: phase 1 writes `prompt-<n>.md`, `schema.json`, and `state.json` into an owner-only handoff directory under `AUTOREVIEW_STATE_DIR`, prints the resume command, and exits 3 (`EXIT_AWAITING_EXTERNAL_RESULT`) without recording history
- finishes a handoff with `--resume-run <run-id>` plus one `--result <file>` per prompt (each a regular file outside the repository, at most 1 MB); it validates, priority-filters, merges chunks, records history as `engine=subagent`, prints `reviewer independence: none (subagent shares the author model/context)`, deletes the handoff on success, and keeps it for retry on failure
- falls back to the `subagent` engine only when the engine was not requested and its CLI is missing, printing `engine_fallback: ...`; `--no-engine-fallback` / `AUTOREVIEW_NO_ENGINE_FALLBACK=1` disables it
- exits nonzero when accepted/actionable findings are present
