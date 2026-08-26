# Worker profile configuration

Use this reference only when routing or replacing a worker or validator.

## Resolve configuration

Load the first existing user profile, then merge an optional project override on top by profile name:

1. `${XDG_CONFIG_HOME:-$HOME/.config}/mason-skills/large-task-orchestrator/worker-profiles.json`
2. `<repository>/.local/large-task-orchestrator/worker-profiles.json`

The project file wins. Keep both files outside the Skill so model and provider preferences can change without editing workflow instructions. Keep the project override local and untracked; when needed, exclude its exact path through `.git/info/exclude`. Treat malformed files, unknown schema versions, duplicate profile names, and invalid effort values as configuration errors; identify the path and fall back to live adapter defaults for affected workers rather than guessing a value.

## Schema and matching

The document has `version: 1` and a `profiles` array. Each profile contains:

- `name`: unique diagnostic name.
- `match.agent`: ACPX agent name or Herdr kind.
- `match.model_contains`: optional case-insensitive model-ID substring.
- `effort_by_difficulty`: a map whose optional keys are `routine`, `standard`, `complex`, and `critical` and whose values are adapter-supported effort strings.

Choose the matching profile with the most match fields; when specificity ties, the project profile wins and then earlier array order wins. A missing difficulty key means the adapter default applies.

Classify difficulty from the Story's ambiguity, cross-module breadth, correctness risk, and cost of failure. Use `routine` for bounded mechanical work, `standard` for ordinary implementation, `complex` for substantial reasoning or integration, and `critical` when failure can corrupt data, security, compatibility, or the remaining plan.

After session creation, compare the configured effort with the adapter's advertised options. Apply it only when supported. When the adapter exposes one effort, use that value. Otherwise leave its default unchanged and record the mismatch in the execution-card handoff and orchestrator notebook. Re-evaluate the profile when switching agent or model; never inherit effort blindly from the prior worker.
