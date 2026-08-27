# Orchestration configuration

Use this reference when routing or replacing a worker or validator.

## Resolve configuration

Load the user configuration, then merge an optional project override:

1. `${XDG_CONFIG_HOME:-$HOME/.config}/mason-skills/large-task-orchestrator/orchestrator.json`
2. `<repository>/.local/large-task-orchestrator/orchestrator.json`

The project file wins. Keep its exact path local and untracked through `.git/info/exclude` when needed. Validate each file before merging. A malformed file, unknown schema version, duplicate profile name, missing required route, or invalid candidate blocks dispatch for the affected role; report the path and field instead of using an implicit route.

The document has `version: 1`, a `routing` object, and a `profiles` array. A project route replaces the complete user route at the same `routing.<role>.<name>` key; profiles merge by `name`.

## Routing

`routing.worker.default` and `routing.validator.default` are required non-empty candidate arrays. `routing.worker.frontend` is optional and replaces the worker default for frontend-dominant Stories when present.

Each candidate contains:

- `agent`: required ACPX agent name or Herdr kind.
- `acpx_command`: optional complete ACP-compatible command passed as one `--agent` value instead of the registered name.
- `native_args`: optional argument array appended when Herdr starts the configured `agent` kind.
- `model_contains`: optional case-insensitive substring that the advertised model ID must contain.
- `reason`: optional operator-facing rationale for a non-obvious routing constraint; it does not affect matching.

Walk the selected array in order. A candidate becomes eligible only after its adapter, authentication, configured model, and required capability pass preflight. On quota exhaustion or unavailability, preserve the attempt evidence and advance to the next candidate. Exhausting the array blocks the Story.

## Effort profiles

Each profile contains a unique `name`, `match.agent`, optional `match.role`, optional `match.model_contains`, and optional `effort_by_difficulty`. `match.role` is `worker` or `validator`. The effort map may use `routine`, `standard`, `complex`, and `critical`; a missing key leaves the adapter default unchanged. Profiles without an effort map are valid.

Choose the matching profile with the most match fields; when specificity ties, the project profile wins and then earlier array order wins. Classify difficulty from ambiguity, cross-module breadth, correctness risk, and cost of failure: `routine` is bounded mechanical work, `standard` is ordinary implementation, `complex` requires substantial reasoning or integration, and `critical` risks data, security, compatibility, or the remaining plan.

Apply a configured effort only when the adapter advertises it or the candidate pins the same value in validated native startup arguments. Otherwise keep the adapter default and record `effort=default`; do not try alternate option names or synthesized model IDs. Re-resolve routing and effort when switching agent or model; never inherit either from the prior attempt.
