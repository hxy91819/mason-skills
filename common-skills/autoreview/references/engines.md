# Reviewer selection and configuration

## Review Panels

Run multiple reviewers against one frozen bundle:

```bash
"$AUTOREVIEW" --reviewers codex,claude,pi
```

`--panel` is shorthand for Codex plus Claude unless `--engine` changes the first reviewer:

```bash
"$AUTOREVIEW" --panel
```

Set reviewer models and thinking/effort explicitly:

```bash
"$AUTOREVIEW" --reviewers codex,claude --model codex=gpt-5.6-sol --thinking codex=high --model claude=claude-fable-5 --thinking claude=max
```

Inline syntax is also supported for simple model IDs:

```bash
"$AUTOREVIEW" --reviewers codex:gpt-5.6-sol:high,claude:claude-fable-5:max
```

For models with slashes or extra colons, prefer keyed form:

```bash
"$AUTOREVIEW" --engine pi --model anthropic/claude-sonnet-4 --thinking high
"$AUTOREVIEW" --reviewers codex,pi --model codex=gpt-5.6-sol --model pi=anthropic/claude-sonnet-4
```

`--reviewers all` covers Codex, Claude, and Pi. BB remains opt-in because it creates a durable BB thread. Droid, Copilot, Cursor, and OpenCode selections fail closed because their current CLI contracts cannot confine project instructions, filesystem reads, or network fetches to the review boundary. `subagent` is refused in `--panel` and `--reviewers` because it is not an independent opinion; run it alone.

## BB Session Engine

Use `--engine bb` from an active BB thread to review through a fresh hidden BB
session while preserving the invoking thread's provider, model, reasoning, and
service tier:

```bash
"$AUTOREVIEW" --engine bb --bb-trusted-input --mode local
```

Before running this mode, read [references/bb-session.md](bb-session.md)
for its configuration inheritance, non-isolation warning, lifecycle, and real
BB fixture proof. Keep the printed
`reviewer isolation: none (BB session tools are not confined to the review bundle)`
line in the final report. `--bb-trusted-input` is a per-run assertion that the
change bundle, prompt, and datasets all come from trusted parties; omit it and
the helper fails before spawning a thread.

## Subagent Engine (zero-config fallback)

Use when no reviewer CLI is installed. The host agent (Claude Code, Codex, ...) supplies the reviewer through its own subagent while the helper still builds and redacts the bundle, validates structured output, filters priorities, assigns finding ids, and records history. This is **not** an independent second opinion: the reviewer shares the author model and context, so prefer codex/claude/pi whenever one is available.

Phase 1 writes the handoff and exits **3** (`EXIT_AWAITING_EXTERNAL_RESULT`, distinct from 0 clean and 1 findings):

```bash
"$AUTOREVIEW" --engine subagent --model subagent=claude-fable-5-1
```

It prints `subagent handoff: <dir>`, `subagent prompts: <n>`, one `subagent prompt <n>: <path>` line per prompt, and the exact `subagent resume:` command. The handoff directory lives under `AUTOREVIEW_STATE_DIR` (default `~/.cache/autoreview/handoff/<run-id>`), never inside the reviewed repository, and holds `prompt-<n>.md`, `schema.json`, and `state.json` with owner-only permissions.

Then, for each prompt file: spawn one general-purpose subagent of the host (no repository access, no commands, no tools needed) and give it only that prompt file's contents; the bundle is self-contained. Require its final answer to be a single JSON object matching `schema.json` and nothing else, and save each answer to its own file outside the reviewed repository.

Phase 2 validates the answers, prints the report, and exits with the usual codes:

```bash
"$AUTOREVIEW" --engine subagent --resume-run <run-id> --result /tmp/result-1.json
```

Pass one `--result` per prompt, in order. A failed validation keeps the handoff directory so a corrected result can be resumed again; a successful resume deletes it. `--model subagent=<label>` is only a history label. Parallel tests run during phase 1 and their status is applied to the phase 2 exit code.

Automatic fallback: with no `--engine` and no `AUTOREVIEW_ENGINE`, a missing Codex CLI (or a missing Claude CLI after a Codex cooldown) prints `engine_fallback: codex CLI not found; using subagent (non-independent)` and continues as a subagent handoff. An explicitly requested engine is never replaced. `--no-engine-fallback` / `AUTOREVIEW_NO_ENGINE_FALLBACK=1` turns it off.

## Models and thinking

The helper accepts `--model` globally or per engine (`engine=model`) and `--thinking` globally or per engine (`engine=level`). Repeat either flag for multiple reviewers.

Recommended model defaults:

| Engine              | Default model                                      | Source note                                           |
| ------------------- | -------------------------------------------------- | ----------------------------------------------------- |
| **codex** (default) | `gpt-5.6-sol` -> `gpt-5.6-terra` on access failure | OpenClaw org review default                           |
| **claude**          | current Claude Code config                         | omit `--model`/`--effort` unless overridden           |
| **bb**              | current BB thread execution                        | provider, model, reasoning, and service tier inherited |

CLI flags and environment variables override these defaults. Claude inherits the current Claude Code model and effort when those flags are omitted. Pi does not get a built-in model default because its provider catalog may vary by installation. Droid, Copilot, Cursor, and OpenCode are currently refused.

| Engine              | Model flag                 | Example model IDs                                                            | Thinking flag                 | Accepted levels                                            |
| ------------------- | -------------------------- | ---------------------------------------------------------------------------- | ----------------------------- | ---------------------------------------------------------- |
| **codex** (default) | `codex --model X exec ...` | `gpt-5.6-sol`, then `gpt-5.6-terra` on Sol access failure                    | `-c model_reasoning_effort=Y` | `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max` |
| **claude**          | `claude --model X`         | `claude-fable-5`, `claude-opus-4-8`, `claude-sonnet-4-6`, `claude-haiku-4-5` | `--effort Y`                  | `low`, `medium`, `high`, `xhigh`, `max`                    |
| **droid**           | currently refused          | Factory model IDs                                                            | `-r, --reasoning-effort Y`    | `off`, `none`, `low`, `medium`, `high`, `xhigh`, `max`     |
| **copilot**         | currently refused          | Copilot model aliases                                                        | not supported                 | n/a                                                        |
| **pi**              | `pi --model X`             | `zai/glm-5.3-flash`, `anthropic/claude-sonnet-4`, `openai/gpt-4o`              | `--thinking Y`                | `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`   |
| **cursor**          | currently refused          | Cursor model aliases                                                         | not supported                 | n/a                                                        |
| **opencode**        | currently refused          | OpenCode provider/model IDs                                                  | not supported                 | n/a                                                        |
| **subagent**        | `--model subagent=X`       | free-form history label, e.g. `claude-fable-5-1`                             | not supported                 | n/a                                                        |
| **bb**              | current thread or `bb=X`   | current BB model ID                                                          | `--reasoning-level Y`         | validated dynamically by BB                               |

Claude also supports `--fallback-model a,b` for availability-based fallback chains ([model-config](https://code.claude.com/docs/en/model-config)). Current Claude docs note that auth, billing, rate-limit, request-size, and transport errors do not trigger fallback, and the changelog documents interactive-session support in `v2.1.166`.

Pi supports an access-only fallback: when the primary run exits nonzero with a provider-availability failure (transport errors, auth, rate limit, model not found, 4xx/5xx status lines), the helper retries once with `--fallback-model` (or `AUTOREVIEW_PI_FALLBACK_MODEL`). Review-content failures never trigger fallback; if the fallback run also fails, both errors are reported.

# Pi with provider fallback, e.g. z.ai primary and Ollama Cloud backup
"$AUTOREVIEW" --engine pi --model zai/glm-5.3-flash --fallback-model pi=ollama-cloud/glm-5.3-flash:cloud

[OpenAI's model guidance](https://developers.openai.com/api/docs/guides/latest-model) identifies Sol as the GPT-5.6 frontier-capability route and documents `max` support. Autoreview keeps `high` as its default; use `max` only for the hardest quality-first reviews after comparing its latency and cost with `xhigh` on representative changes.

Examples matching current `main` behavior:

```bash
# Codex with explicit model and reasoning
"$AUTOREVIEW" --engine codex --model gpt-5.6-sol --thinking high

# Codex fast mode (priority service tier); needs a model whose catalog lists the tier, silently standard otherwise
"$AUTOREVIEW" --engine codex --codex-speed fast

# Safe Codex model/response tuning overrides (--codex-speed wins over a service_tier here)
"$AUTOREVIEW" --engine codex --codex-config 'service_tier="fast"'

# Claude inherits the current Claude Code model and effort
"$AUTOREVIEW" --engine claude

# Claude Code aliases or full model names, with optional availability fallback
"$AUTOREVIEW" --engine claude --model claude-fable-5 --thinking max
"$AUTOREVIEW" --engine claude --model claude-fable-5 --fallback-model claude-opus-4-8,claude-sonnet-4-6

# Pi with explicit model and thinking level
"$AUTOREVIEW" --engine pi --model anthropic/claude-sonnet-4 --thinking high --pi-bin pi

```

`--cursor-agent-bin` and `CURSOR_AGENT_BIN` remain compatibility aliases for
`--cursor-bin` and `CURSOR_BIN`.

### Environment defaults

CLI flags take precedence over environment variables.

Store persistent personal defaults in your shell startup file or launcher
environment. For repository-local defaults, use an existing local environment
loader such as an untracked `.envrc`; the helper does not write a config file.

A complete personal default-harness switch is plain env, no code changes. For
example, to make Pi on `zai/glm-5.3-flash` with `max` thinking the default
harness, falling back to the Ollama Cloud copy of the same model when z.ai is
unavailable:

```bash
export AUTOREVIEW_ENGINE=pi
export AUTOREVIEW_PI_MODEL=zai/glm-5.3-flash
export AUTOREVIEW_PI_THINKING=max
export AUTOREVIEW_PI_FALLBACK_MODEL=ollama-cloud/glm-5.3-flash:cloud
```

CLI flags still win over these variables, so a one-off
`--engine codex --model gpt-5.6-sol --thinking high` overrides the personal
default without editing it.

| Variable                           | Purpose                                                                                                                          |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `AUTOREVIEW_ENGINE`                | Default engine when `--engine` is omitted; built-in default is `codex`                                                            |
| `AUTOREVIEW_MODEL`                 | Override the built-in default `--model` for all engines                                                                          |
| `AUTOREVIEW_THINKING`              | Default `--thinking` for all engines                                                                                             |
| `AUTOREVIEW_MAX_PRIORITY`          | Default `--max-priority` (`P0`–`P3`). Built-in default is `P1` when unset                                                        |
| `AUTOREVIEW_FALLBACK_MODEL`        | Default `--fallback-model` chain for Claude/pi reviewers                                                                         |
| `AUTOREVIEW_<ENGINE>_MODEL`        | Per-engine model override, for example `AUTOREVIEW_CODEX_MODEL=gpt-5.6-sol`                                                      |
| `AUTOREVIEW_<ENGINE>_THINKING`     | Per-engine thinking override                                                                                                     |
| `AUTOREVIEW_CODEX_CONFIG`          | Safe Codex model/response tuning overrides, semicolon-separated, e.g. `service_tier="fast"`; capability-bearing keys fail closed |
| `AUTOREVIEW_CODEX_SPEED`           | Codex service tier override: `fast` (priority), `flex`, or `default`; silently standard when the model does not list the tier    |
| `AUTOREVIEW_CODEX_COOLDOWN_HOURS`  | Hours to skip Codex after a usage-limit failure. Built-in default is `1`                                                             |
| `AUTOREVIEW_IGNORE_CODEX_COOLDOWN` | Set to `1` to invoke Codex even during a recorded usage-limit cooldown                                                               |
| `AUTOREVIEW_STATE_DIR`             | Directory for helper state such as the Codex cooldown file and subagent handoffs; must stay outside the reviewed repository          |
| `AUTOREVIEW_NO_ENGINE_FALLBACK`    | Set to `1` to disable the automatic switch to the `subagent` engine when a non-requested reviewer CLI is missing                     |
| `AUTOREVIEW_CLAUDE_FALLBACK_MODEL` | Claude-only fallback chain                                                                                                       |
| `AUTOREVIEW_PI_FALLBACK_MODEL`     | Pi-only access-failure fallback model                                                                                            |
| `AUTOREVIEW_BB_BIN`                | BB CLI for the `bb` engine; falls back to `BB_CLI`, then `bb`                                                                    |
| `AUTOREVIEW_BB_TIMEOUT_SECONDS`    | Seconds to wait for the BB review thread; built-in default is `1800`                                                             |
| `AUTOREVIEW_PROVIDER_ENV_ALLOW`    | Comma-separated custom Pi/OpenCode credential variable names; names must end in a recognized credential suffix                   |

Codex maps thinking to `model_reasoning_effort`. Claude maps thinking to `--effort`. Pi maps thinking to `--thinking`; when a fresh native session already reports `max`, omit the flag to keep that default. ACPX `pi-acp` may expose a smaller `thought_level` set, so do not infer its default from native Pi. Claude and pi accept `--fallback-model`; global CLI/env fallback requires at least one Claude or pi reviewer, and engine-specific fallback overrides require that reviewer to be selected. Fallback overrides for other engines, including `AUTOREVIEW_CODEX_FALLBACK_MODEL`, fail closed instead of being silently ignored.

## Review engine isolation

When autoreview runs inside the repository under review, external reviewer CLIs must not load project-local trust or configuration that the branch controls.

| Engine       | Isolation flags                                                                                                                                                                                  | Reference                                                                   |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------- |
| **codex**    | Auth-only config overrides, isolated workspace, `exec --ignore-user-config --ignore-rules --skip-git-repo-check`, plus read-only sandbox                                                         | Codex CLI `exec --help`                                                     |
| **claude**   | `--safe-mode --setting-sources user --strict-mcp-config --disallowedTools mcp__*`; auto-memory and filesystem/shell tools disabled; empty external workspace; WebSearch by default (`v2.1.169+`) | Claude Code [CLI reference](https://code.claude.com/docs/en/cli-reference)  |
| **droid**    | Fails closed: current CLI cannot disable both project instructions and all tools                                                                                                                 | Droid CLI `exec --help` and `--list-tools`                                  |
| **copilot**  | Fails closed: repository read tools also expose ignored files outside the reviewed bundle                                                                                                        | GitHub Copilot CLI command reference                                        |
| **pi**       | `--no-approve --no-session --no-context-files --no-extensions --no-skills --no-prompt-templates --no-themes --no-tools`                                                                          | Pi CLI `--help`; requires Pi `v0.79.0+`                                     |
| **opencode** | Fails closed: project/global config isolation and private-network fetch denial are not both proven                                                                                               | OpenCode CLI contract                                                       |
| **cursor**   | Fails closed: documented read permissions can target absolute host paths and no proven repository-only filesystem sandbox is exposed                                                             | Cursor CLI [permissions](https://cursor.com/docs/cli/reference/permissions) |
| **bb**       | Not host-read isolated: temporary Git workspace reduces accidental project context, but BB session tools are not bundle-confined; use only for trusted changes                                      | `bb thread spawn`, `wait`, and `output`                                     |
| **subagent** | Not isolated: runs inside the host agent; treat as author-side self-review                                                                                                                      | this skill, Subagent Engine section                                         |

Codex `--ignore-user-config` skips config loading for the exec run. Autoreview reconstructs only the documented `cli_auth_credentials_store`, `forced_login_method`, and `forced_chatgpt_workspace_id` settings from `CODEX_HOME/config.toml`, keeping authentication usable without forwarding unrelated user configuration. When that config selects a custom `model_provider` (for example a local CLI proxy), autoreview also rebuilds that provider from a fixed allowlist: `base_url` (credential-free http/https only), `wire_api`, `name`, `requires_openai_auth`, `supports_websockets`, and retry/timeout counters. Credentials come from the provider's `env_key` variable or its `auth.command`, which must be an absolute executable outside the reviewed repository; the command runs once with the real `HOME` and its output is passed to the isolated run through `AUTOREVIEW_CODEX_PROVIDER_API_KEY`. Headers, query params, and any other provider keys are never forwarded, and provider names must be bare TOML keys because Codex `-c` cannot parse quoted key segments. A custom provider always runs with the isolated runtime `CODEX_HOME`, so the user's global `AGENTS.md` and other home-level instructions stay out of the review prompt. Codex runs in an empty temporary workspace: the validated bundle is its sole repository input, ignored files and linked-worktree metadata remain unreadable, and the zero project-doc budget keeps workspace instructions out of the prompt. `--ignore-rules` skips user/project execpolicy rules. Claude `--safe-mode` disables project hooks, skills, plugins, MCP servers, and CLAUDE.md; autoreview supplies WebSearch by default, permits only explicitly domain-constrained WebFetch rules, and exposes no filesystem or shell tools. Pi runs from a neutral temporary directory with project resources disabled and `--no-tools`. Droid, Copilot, Cursor, and OpenCode fail closed because their current CLI contracts cannot isolate untrusted review input from host, project, or private-network trust surfaces.

Codex uses a named permission profile that grants read access only to an empty temporary workspace. This is narrower than repository-root access, which would expose ignored credentials, and narrower than the legacy `read-only` sandbox, which permits reads across the host filesystem. BB has no equivalent public per-thread control: its external temporary Git workspace reduces accidental project context but is not a security boundary for reads. The helper archives/stops the hidden BB review thread after output is collected.

## Fallback boundaries

- Never switch or override the requested review engine/model except for the documented Codex Sol-to-Terra account-access fallback, the documented pi access-only fallback-model retry, and a recorded Codex usage-limit cooldown. Capacity and unrelated failures keep the same engine/model. A Codex usage-limit failure records a fixed cooldown (default 1 hour, `AUTOREVIEW_CODEX_COOLDOWN_HOURS`) and later runs skip Codex in favor of Claude instead of waiting on reset. Do not retry Codex during that window. `--ignore-codex-cooldown` forces Codex. When the engine was never requested (no `--engine`, no `AUTOREVIEW_ENGINE`) and the default or cooldown-substituted CLI is not installed, the helper switches to the `subagent` engine and says so; an explicitly requested engine is still never replaced. `--no-engine-fallback` or `AUTOREVIEW_NO_ENGINE_FALLBACK=1` disables that switch.
