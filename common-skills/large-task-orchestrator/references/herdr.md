# Herdr orchestration

Use this branch only inside a Herdr-managed pane.

## Verify and discover

First require:

```bash
test "${HERDR_ENV:-}" = 1
```

If it fails, return to ACPX selection or report that Herdr is unavailable. Do not control the focused Herdr session from outside Herdr.

Run `herdr --help`, `herdr agent`, and the relevant `herdr pane` commands before mutation. The installed CLI and listed agent kinds are authoritative. Inspect live state with explicit caller context and IDs; do not rely on UI focus.

## Create Story role sessions

For each ready Story worker, create an available sibling shell pane in the current tab and preserve the caller's working directory and focus. After the worker reports `worker_done`, create a different pane and agent for its validator:

```bash
herdr pane split --current --direction <right-or-down> --cwd "$PWD" --no-focus
```

Choose direction from the current layout and parse the new pane ID from `.result.pane.pane_id`. Avoid parallelism that makes panes unusably small. Do not create workspaces, tabs, or worktrees unless the user explicitly requests that topology.

Start one uniquely named supported agent in each role pane:

```bash
herdr agent start <run-story-role-attempt> --kind <kind> --pane <pane-id> -- <native-agent-options>
```

Use native options to select the configured model and effort only when the installed kind supports them. Keep them as separate settings unless that kind explicitly exposes a combined model variant, and validate both against the live agent capabilities before dispatch.

The agent name remains dedicated to one Story and one role. Worker and validator always use different panes and names. A replacement worker receives a new pane/name and attempt number for the same Story; never reuse a live agent name for different work.

## Dispatch and monitor a wave

Send the complete role prompt through `herdr agent prompt`. To fan out, submit prompts to all ready idle workers without waiting for each to finish, then monitor them by unique name with `herdr agent wait`, `herdr agent get`, and `herdr agent read`. Start each validator only after its worker settles at `worker_done`.

Use `--wait --timeout <ms>` when dispatching a single worker or when the host can wait on multiple workers concurrently. Without `--until`, settled states are `idle`, `done`, or `blocked`. `unknown` does not prove completion.

If a worker or validator becomes `blocked`, inspect its recent unwrapped output before deciding what it needs:

```bash
herdr agent get <story-agent-name>
herdr agent read <story-agent-name> --source recent-unwrapped --lines 120
```

Ask the user before answering approval or decision dialogs that exceed existing authority. Use logical keys such as `esc` or `ctrl+c` only when interruption is actually required.

If alternate-screen output truncates the final result, ask that same Story agent to write the complete report to a temporary Markdown file and respond with its path, then read the file directly.

## Preserve the session

Keep background focus unchanged. Do not close panes, tabs, workspaces, or sessions you did not create. Retain completed and quota-exhausted panes until their result and diff have been reconciled; cleanup requires explicit user direction when it would close or destroy session state.
