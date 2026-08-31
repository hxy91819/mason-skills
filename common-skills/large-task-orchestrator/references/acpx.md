# ACPX orchestration

Use this branch when ACPX is the selected control surface.

## Discover and prepare

Use the route selected by the deterministic orchestration resolver; then use `acpx config show` only to inspect the selected registered alias and its structured `argv`. Start the first candidate with one bounded `sessions new` ACP initialize/session handshake. ACPX has no `preflight` verb: fresh session creation is the single capability check. On resume, inspect the recorded session and use `sessions ensure` only for that exact session. Inspect later candidates only after this one is unavailable, incompatible, or quota-exhausted; do not probe the whole fallback chain up front.

Kiro supports ACPX named sessions and advertises its available models during the ACP handshake. Treat the inherited `HOME` and provider profile as part of the candidate identity: changing `HOME`, partially symlinking a profile, or replacing its config can change Kiro authentication, backend selection, and the advertised model catalog. Preflight and dispatch under the same environment that the configured route will actually inherit. An isolated-home result proves only that isolated profile; it cannot disqualify the real route unless that is the route's intended environment.

Read the exact handshake's model list and choose by Story risk, validator cost, and quota; do not cache a model list in the plan or assume Kiro's current default remains stable. A model rejected because it was not advertised is a route/profile mismatch, not provider or quota exhaustion. Re-resolve against that handshake instead of probing model names learned from another HOME or session.

An orchestration candidate is not an ACPX agent merely because a same-named shell wrapper launches a coding CLI. Use a custom candidate only when `acpx config show` resolves it to an ACP-compatible stdio adapter and its ACP initialize/session handshake succeeds. An ordinary interactive CLI wrapper does not qualify.

When a candidate defines `acpx_command`, pass that exact command as one quoted `--agent` value to `sessions new`; the resulting ACP initialize/session handshake is the preflight. Keep the candidate's logical `agent` for profile matching. Do not append `--help` or `--version` to a long-running stdio adapter: adapters commonly treat those tokens as application arguments and wait for ACP stdin. A separately documented, terminating native help/version command is optional diagnostic evidence only and must have its own short timeout. Create its named session with `--agent <command> sessions new --name <role-session>`; prompt an existing session with `--agent <command> prompt -s <role-session>`. The explicit `prompt` verb is required because raw-agent parsing does not accept `-s` in the positional-agent form.

Scope every invocation to the Story's repository with `--cwd <absolute-repo-path>`. Use unique names such as `<run>-<story>-worker-1` and `<run>-<story>-validator-1`. A replacement worker increments its attempt number.

For first dispatch, choose a name not used by an earlier Story run and create a fresh session, then establish its provider identity baseline before prompting:

```bash
acpx --cwd <repo> --timeout <preflight-timeout-seconds> <role-permission-flags> --non-interactive-permissions fail <agent> sessions new --name <role-session>
acpx --cwd <repo> --timeout <preflight-timeout-seconds> <agent> sessions show <role-session>
```

On orchestrator resume, run `sessions show <role-session>` and compare the recorded provider session identifier, agent, cwd, effective permission flags, and sandbox/capability fingerprint before reusing it with `sessions ensure`. Immediately run `sessions show` again after `ensure` and compare all fields before sending any prompt. If the session is missing, closed, mismatched, or changed during ensure, quarantine/reconcile the workspace and create a new attempt with the prior handoff; do not silently replay the Story under the same attempt. After every strict-JSON prompt, compare the returned provider `agentSessionId` (or equivalent identifier) with the pre-dispatch record; a changed or missing identifier is a continuity failure. Quarantine and reconcile all workspace side effects from that prompt before any validator or retry, then create a new attempt. `sessions new` can replace an existing open scope, so uniqueness and plan reconciliation are required before creation.

Session lifecycle verbs do not share the prompt option shape: close a named session with `sessions close <role-session>`, not `sessions close -s <role-session>`. Check the installed command help before applying prompt-style flags to another verb.

Resolve the role profile before session creation. Select an advertised model. Apply effort only when the handshake or a validated startup argument explicitly supports it; otherwise keep the adapter default, record `effort=default`, and continue. Never guess option names or synthesize model IDs after a rejected setting.

Current `codex-acp` exposes model and effort as separate config options. For a registered Codex candidate such as `codex`, `codexp`, or `codexl`, apply the resolved profile after `sessions new` and the baseline `sessions show`, before the first prompt:

```bash
acpx --cwd <repo> <agent> set reasoning_effort <resolved-effort> -s <role-session>
```

Continue with that effort only after the command reports `config set: reasoning_effort=<resolved-effort>`. If the option or value is rejected, record `effort=default` and dispatch without trying aliases such as `thought_level` or a synthesized `<model>[<effort>]` ID. Reapply the newly resolved effort when a replacement attempt changes candidate, model, or difficulty.

## Dispatch a wave

Submit one complete worker or validator prompt immediately after the single bounded ACP handshake, with the resolved provider sandbox and non-interactive permission behavior:

For a validator, use the dedicated contract block below; do not fill `<resolved-permission-flags>` with a convenience mode.

```bash
acpx --cwd <repo> <resolved-permission-flags> --non-interactive-permissions fail --format json --json-strict <agent> prompt -s <role-session> --file <prompt-path> > <repo>/.local/large-task-orchestrator/<role-session>.ndjson
```

Resolve the role-specific permission flags before dispatch and record them with the provider sandbox evidence and effective permission behavior in the execution-card handoff. ACPX's permission policy is tool-oriented and cannot by itself constrain file paths, shell arguments, or network destinations to a Story. A worker or validator may use automatic approval only when that provider sandbox independently enforces the role's repository, command, and network scope; validators receive read/search/execute authority without code-editing. Otherwise fail closed or route to an adapter with verifiable isolation. Do not use `--approve-all` merely to bypass an unproven boundary.

### Validator permission contract

“Read-only” is an authority boundary, not a promise that the validator will make no terminal calls. `openspec validate`, `git status`, `git diff --check`, and targeted tests are ACPX `execute` requests. Use the checked-in [validator-permission-policy.json](validator-permission-policy.json) exactly:

```json
{
  "autoApprove": ["read", "search", "execute"],
  "autoDeny": ["edit", "delete", "move", "fetch", "switch_mode"],
  "defaultAction": "deny"
}
```

Pass the policy by its absolute Skill path (the policy is loaded by the orchestrator, not by the leaf validator), and use the same flags for session creation/ensure and every prompt:

```bash
acpx --cwd <repo> \
  --permission-policy <absolute-skill-dir>/references/validator-permission-policy.json \
  --non-interactive-permissions fail <agent> sessions new --name <role-session>
acpx --cwd <repo> \
  --permission-policy <absolute-skill-dir>/references/validator-permission-policy.json \
  --non-interactive-permissions fail <agent> sessions ensure --name <role-session>
acpx --cwd <repo> \
  --permission-policy <absolute-skill-dir>/references/validator-permission-policy.json \
  --non-interactive-permissions fail --format json --json-strict \
  <agent> prompt -s <role-session> --file <prompt-path>
```

Do not replace this with `--approve-reads`: that mode covers only `read`/`search`, so the first `execute` request falls through to an interactive prompt and returns `PERMISSION_PROMPT_UNAVAILABLE` (ACPX exit 5) in a headless run. `defaultAction: deny` keeps unknown tools closed while the explicit deny list protects the validator's no-edit contract. Approving `execute` is safe only when the provider sandbox independently enforces the read-only repository/command boundary; ACPX kind matching cannot enforce paths or shell arguments. Record the policy path, SHA-256, effective flags, and sandbox fingerprint with the session baseline.

The JSON stream may still contain `session/request_permission` events for requests that ACPX auto-resolved; their presence alone is not a policy failure. Judge the outcomes together with `turn.stop_reason`, the ACPX exit code, and any cancellation or unanswered request.

If the policy file is missing, unreadable, or does not have exactly the contract above, fail closed before creating or prompting a validator session; do not silently fall back to `--approve-reads`, `--approve-all`, or an interactive permission prompt.

Prompt text may instead arrive on stdin. Use the host's parallel command surface to start independent Story invocations concurrently. ACPX queueing is per session; `--no-wait` queues follow-ups to an already busy session and is not a substitute for separate parallel Story sessions.

Apply the least-permissive ACP permission policy that permits the role's authorized operations. Workers may receive bounded write authority; validators receive read/search/execute authority without code-editing authority through the fixed policy above. Do not use `--approve-all` unless the user's authority and repository policy justify it.

Use persistent named sessions for worker fixes and validator rechecks of the same Story. Keep worker and validator sessions separate. Use `exec` only for stateless read-only work where continuity is irrelevant. Do not use `compare` for implementation because it runs agents serially against the same prompt and does not provide Story sessions.

## Observe and recover

Use `status`, `sessions show`, and `sessions history` for the exact agent, repository, and session name. Preserve the ACPX process exit code and pass it as `--acpx-exit` when reading the redirected NDJSON stream with [`../scripts/read_acpx_result.py`](../scripts/read_acpx_result.py), rather than parsing events inline. One run yields the turn's stop reason, runtime error with its acpx code, permission outcomes, tool-call failures, provider session continuity, a machine-readable failure classification, and the role contract block. Any non-zero ACPX exit makes the stream untrusted, even when a conclusion is present; the reader reports `acpx-exit-nonzero`. For a validator, route `failure.classification=permission_policy_mismatch` through the permission-policy recovery below; it is never a conclusion or quota result. Also inspect the repository because output alone cannot prove changes landed.

Keep a non-zero ACPX status available to the reader instead of letting shell `set -e` discard the stream evidence:

```bash
acpx_exit=0
acpx --cwd <repo> <role-permission-flags> \
  --non-interactive-permissions fail --format json --json-strict \
  <agent> prompt -s <role-session> --file <prompt-path> > <stream-path> || acpx_exit=$?
python3 <skill-dir>/scripts/read_acpx_result.py \
  --stream <stream-path> --expect validator \
  --session <baseline-provider-session-id> --acpx-exit "$acpx_exit"
```

When `session/new` succeeds but the first prompt returns an immediate dispatch failure before any tool call or workspace effect, keep the Story unchanged and classify the failure before falling back. Run one minimal no-tool prompt with the exact configured command and actual dispatch environment, then compare its current and advertised models with the failed handshake. Success there identifies a harness/profile mismatch; the same failure there makes the candidate unavailable. This diagnostic is recovery-only—do not add a synthetic prompt to every healthy preflight or contaminate a fresh Story session.

If a validator prompt returns `PERMISSION_PROMPT_UNAVAILABLE`, `permission prompt unavailable`, or ACPX exit 5, classify it as a permission-policy mismatch. Inspect the event stream for the denied `execute` request, verify that the named session is idle and the workspace has no side effect, then use `sessions ensure` (not `sessions new`) and retry the unchanged prompt once with [the fixed validator policy](validator-permission-policy.json) applied at ensure and prompt. Preserve the provider session ID when the session is clean; otherwise quarantine/reconcile and create a new attempt. Never turn this failure into `CONTINUE`, `PATCH_PROMPT`, or `quota_exhausted`, and never broaden to `--approve-all` as recovery. If the corrected-policy retry fails again, re-resolve the validator route and open a fresh validator attempt, not a worker session, while keeping the Story `in_progress`.

A client timeout or incomplete final result does not prove the named session is idle, even when the wrapper exits successfully. Inspect that exact session; if its prompt is still running, cancel it and confirm it is idle before sending a retry. Otherwise the retry only queues behind the stalled prompt.

If a prompt must be stopped, use the matching agent and session:

```bash
acpx --cwd <repo> <agent> cancel -s <role-session>
```

For a worker quota exhaustion, retain the original session for audit, create a new named session under the fallback agent, and send a handoff prompt for the same Story. For a validator quota exhaustion, create a fresh validator attempt instead; do not turn it into a worker attempt. Do not queue more prompts to the exhausted provider during that wave.

For a fixed reusable graph, an ACPX flow may encode routing and checkpoints. Do not generate a flow file merely to run a one-off plan; named sessions plus the stateful large task plan remain the simpler control plane.
