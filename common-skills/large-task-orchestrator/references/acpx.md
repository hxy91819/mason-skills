# ACPX orchestration

Use this branch when ACPX is the selected control surface.

## Discover and prepare

Resolve the selected route from `acpx config show`, then use `sessions new` for the first candidate. ACPX has no `preflight` verb: fresh session creation is the single handshake and capability check. On resume, inspect the recorded session and use `sessions ensure` only for that exact session. Inspect later candidates only after this one is unavailable, incompatible, or quota-exhausted; do not probe the whole fallback chain up front.

Kiro supports ACPX named sessions and advertises its available models during the ACP handshake. Read the recorded session's model list and choose by Story risk, validator cost, and quota; do not cache a model list in the plan or assume Kiro's current default remains stable.

An orchestration candidate is not an ACPX agent merely because a same-named shell wrapper launches a coding CLI. Use a custom candidate only when `acpx config show` resolves it to an ACP-compatible stdio adapter and its preflight succeeds. An ordinary interactive CLI wrapper does not qualify.

When a candidate defines `acpx_command`, validate that exact command through its native help and use it as one quoted `--agent` value. Keep the candidate's logical `agent` for profile matching. Create its named session with `--agent <command> sessions new --name <role-session>`; prompt an existing session with `--agent <command> prompt -s <role-session>`. The explicit `prompt` verb is required because raw-agent parsing does not accept `-s` in the positional-agent form.

Scope every invocation to the Story's repository with `--cwd <absolute-repo-path>`. Use unique names such as `<run>-<story>-worker-1` and `<run>-<story>-validator-1`. A replacement worker increments its attempt number.

For first dispatch, choose a name not used by an earlier Story run and create a fresh session, then establish its provider identity baseline before prompting:

```bash
acpx --cwd <repo> <agent> sessions new --name <role-session>
acpx --cwd <repo> <agent> sessions show <role-session>
```

On orchestrator resume, run `sessions show <role-session>` and compare the recorded provider session identifier, agent, cwd, effective permission flags, and sandbox/capability fingerprint before reusing it with `sessions ensure`. Immediately run `sessions show` again after `ensure` and compare all fields before sending any prompt. If the session is missing, closed, mismatched, or changed during ensure, quarantine/reconcile the workspace and create a new attempt with the prior handoff; do not silently replay the Story under the same attempt. After every strict-JSON prompt, compare the returned provider `agentSessionId` (or equivalent identifier) with the pre-dispatch record; a changed or missing identifier is a continuity failure. Quarantine and reconcile all workspace side effects from that prompt before any validator or retry, then create a new attempt. `sessions new` can replace an existing open scope, so uniqueness and plan reconciliation are required before creation.

Session lifecycle verbs do not share the prompt option shape: close a named session with `sessions close <role-session>`, not `sessions close -s <role-session>`. Check the installed command help before applying prompt-style flags to another verb.

Resolve the role profile before session creation. Select an advertised model. Apply effort only when the handshake or a validated startup argument explicitly supports it; otherwise keep the adapter default, record `effort=default`, and continue. Never guess option names or synthesize model IDs after a rejected setting.

## Dispatch a wave

Submit one complete worker or validator prompt immediately after the single preflight, with the resolved provider sandbox and non-interactive permission behavior:

```bash
acpx --cwd <repo> <resolved-permission-flags> --non-interactive-permissions fail --format json --json-strict <agent> -s <role-session> --file <prompt-path>
```

Resolve `<resolved-permission-flags>` before dispatch and record it with the provider sandbox evidence and effective permission behavior in the execution-card handoff. ACPX's permission policy is tool-oriented and cannot by itself constrain file paths, shell arguments, or network destinations to a Story. A worker or validator may use automatic approval only when that provider sandbox independently enforces the role's repository, command, and network scope; validators still receive read and targeted-test authority without code-editing. Otherwise fail closed or route to an adapter with verifiable isolation. Do not use `--approve-all` merely to bypass an unproven boundary.

Prompt text may instead arrive on stdin. Use the host's parallel command surface to start independent Story invocations concurrently. ACPX queueing is per session; `--no-wait` queues follow-ups to an already busy session and is not a substitute for separate parallel Story sessions.

Apply the least-permissive ACP permission policy that permits the role's authorized operations. Workers may receive bounded write authority; validators receive read and targeted-test authority without code-editing authority. Do not use `--approve-all` unless the user's authority and repository policy justify it.

Use persistent named sessions for worker fixes and validator rechecks of the same Story. Keep worker and validator sessions separate. Use `exec` only for stateless read-only work where continuity is irrelevant. Do not use `compare` for implementation because it runs agents serially against the same prompt and does not provide Story sessions.

## Observe and recover

Use `status`, `sessions show`, and `sessions history` for the exact agent, repository, and session name. Parse JSON events and the final result block; also inspect the repository because output alone cannot prove changes landed.

A client timeout or incomplete final result does not prove the named session is idle, even when the wrapper exits successfully. Inspect that exact session; if its prompt is still running, cancel it and confirm it is idle before sending a retry. Otherwise the retry only queues behind the stalled prompt.

If a prompt must be stopped, use the matching agent and session:

```bash
acpx --cwd <repo> <agent> cancel -s <role-session>
```

On quota exhaustion, retain the original session for audit, create a new named session under the fallback agent, and send a handoff prompt for the same Story. Do not queue more prompts to the exhausted provider during that wave.

For a fixed reusable graph, an ACPX flow may encode routing and checkpoints. Do not generate a flow file merely to run a one-off plan; named sessions plus the stateful large task plan remain the simpler control plane.
