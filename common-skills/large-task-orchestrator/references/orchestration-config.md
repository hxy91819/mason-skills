# Orchestration configuration

Use this reference before a first worker/validator dispatch, on orchestrator resume, or when switching routes.

## Resolve configuration

Run the deterministic resolver from this Skill; agents do not read or merge orchestration JSON directly:

```bash
python3 <skill-directory>/scripts/resolve_orchestration_config.py \
  --repository <absolute-repository-root>
```

The resolver is the runtime source of truth. It always checks these exact locations in order and accepts no path override:

1. `${XDG_CONFIG_HOME:-$HOME/.config}/mason-skills/large-task-orchestrator/orchestrator.json` — required user configuration.
2. `<repository>/.local/large-task-orchestrator/orchestrator.json` — optional project override; keep it local and untracked through `.git/info/exclude` when needed.

Proceed only when exit code is zero, `ok=true`, and `sources.user` plus `sources.project` each report their fixed path and status. A missing project file is a successful `absent` source. Any other read, JSON, schema, route, candidate, profile, or merged-required-route error fails closed and names its source path. Without a successful two-source report, create, ensure, and prompt no external session. Invoke the resolver again on every orchestrator resume and route switch; never reuse a prior merged result across either boundary.

The successful `config` is the only routing/profile input. A project `routing.<role>.<name>` replaces that entire user candidate array. Profiles merge by `name`: project definitions replace same-named user definitions and have selection priority over user profiles. Do not reproduce this merge in prompts or host-specific configuration readers.

## Version 1 schema

Each present file is one object with exactly `version`, `routing`, and `profiles`. `version` is integer `1`. `routing` may contain partial overrides, but the merged result must contain non-empty `routing.worker.default` and `routing.validator.default` arrays. Supported route keys are:

- `routing.worker.default`
- optional `routing.worker.frontend`
- `routing.validator.default`

Every route is a non-empty candidate array. Each candidate has exactly these supported fields:

- `agent`: required ACPX agent name or Herdr kind.
- `acpx_command`: optional complete ACP-compatible command passed as one `--agent` value instead of the registered name.
- `native_args`: optional string array appended when Herdr starts the configured `agent` kind.
- `model_contains`: optional case-insensitive substring for a candidate that intentionally requires a model family. It is a strict compatibility constraint for worker capabilities that genuinely depend on that model; on validator candidates it is treated as a non-blocking legacy preference.
- `model_preference`: optional model-family or model ID recommendation. Request it during session setup before the first prompt; if the adapter cannot honor it, record the actual model and continue. It never invalidates a validator review.
- `reason`: optional operator-facing rationale for a non-obvious routing constraint; it does not affect matching.

`profiles` is an array whose `name` values are unique within a source. A profile has required `name` and `match`, plus optional `effort_by_difficulty`. `match` requires `agent` and may include `role` (`worker` or `validator`) and `model_contains`. The effort map may contain `routine`, `standard`, `complex`, and `critical`; omitted keys leave the adapter default unchanged. Profiles without an effort map are valid. Unknown fields, roles, routes, and difficulty keys are errors.

Permission is a role contract, not a routing preference. The orchestrator must not let user/project JSON weaken the validator boundary: every ACPX validator uses [the fixed read/search/execute policy](validator-permission-policy.json), while a Herdr validator expresses the same boundary through its native sandbox. A worker's write authority remains dependent on independently enforced sandbox evidence. Do not add `--approve-reads` or `--approve-all` to a validator route; select the provider first, then apply the role policy at session creation/ensure and prompt.

## Use the resolved route

Walk the selected candidate array in order. A candidate becomes eligible after its adapter, authentication, and required capability pass a bounded ACP initialize/session handshake. Apply `model_preference` (and any validator `model_contains` kept for compatibility) before the first prompt when supported; record the actual model and continue when a validator uses a different one. The inherited process environment is part of that candidate even though it is not duplicated in the schema: start the exact `acpx_command` through ACPX `sessions new` under the same `HOME` and provider profile that dispatch will use. Do not append `--help` or `--version` to a long-running stdio adapter; many adapters wait for ACP stdin instead of terminating. An isolated or substituted HOME does not establish authentication or model availability for the resolved route.

For a Kiro `acpx_command` that pins `--model` or `--effort`, verify those flags through the resulting ACP session and its advertised configuration, not just process startup; any model choice is made before the first prompt. A separately documented, terminating native help/version command may be run as optional bounded diagnostics, but it is not the route gate. Enforce `model_contains` only for a non-validator capability that declares it. A validator proceeds when the handshake succeeds and the review contract produces a valid conclusion, even if the advertised model differs from either model field. On quota exhaustion or unavailability, preserve the attempt evidence, rerun the resolver for the route switch, and advance to the next candidate. Exhausting the array blocks the Story.

Choose the matching profile with the most match fields; when specificity ties, use the resolver's array order. Classify difficulty from ambiguity, cross-module breadth, correctness risk, and cost of failure: `routine` is bounded mechanical work, `standard` is ordinary implementation, `complex` requires substantial reasoning or integration, and `critical` risks data, security, compatibility, or the remaining plan.

Apply a configured effort through the adapter config option advertised by the handshake (`reasoning_effort` for Codex ACP, `thought_level` for Pi ACP) or through a candidate's validated native startup flag. A profile may intentionally keep the adapter default; then omit the setting and record `effort=default` with any observed default. Otherwise keep the adapter default and record `effort=default` when no option/value is available; do not try alternate option names or synthesized model IDs. Re-resolve routing and effort when switching agent or model; never inherit either from the prior attempt.
