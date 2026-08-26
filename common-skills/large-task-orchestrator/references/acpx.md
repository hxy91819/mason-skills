# ACPX orchestration

Use this branch when ACPX is the selected control surface.

## Discover and prepare

Confirm `acpx` is installed, then inspect `acpx config show` and the relevant command help. ACPX provides built-in agent names and user configuration may add custom ones. Treat the resolved registry and adapter-advertised models as authoritative. The `cursor` route launches `cursor-agent acp`; the `kiro` route launches `kiro-cli-chat acp`.

Preflight every candidate before assigning it work. Confirm its local CLI or npx adapter can start an ACP server without sending a model prompt. Check native ACP help where available, such as `cursor-agent acp --help`, `kimi acp --help`, `kiro-cli-chat acp --help`, and `opencode acp --help`. For Kiro, also confirm `kiro-cli-chat whoami` succeeds without exposing account details. ACPX's Pi and Codex routes use the `pi-acp` and `@agentclientprotocol/codex-acp` npx packages; make them locally available before relying on offline execution. Exclude a candidate whose adapter, authentication, or required model configuration is unavailable.

Kiro supports ACPX named sessions and advertises its available models during the ACP handshake. Read the recorded session's model list and choose by Story risk, validator cost, and quota; do not cache a model list in the plan or assume Kiro's current default remains stable.

An orchestration candidate is not an ACPX agent merely because a same-named shell wrapper launches a coding CLI. Use a custom candidate only when `acpx config show` resolves it to an ACP-compatible stdio adapter and its preflight succeeds. An ordinary interactive CLI wrapper does not qualify.

When a candidate defines `acpx_command`, validate that exact command through its native help and use it as one quoted `--agent` value. Keep the candidate's logical `agent` for profile matching. Create its named session with `--agent <command> sessions new --name <role-session>`; prompt an existing session with `--agent <command> prompt -s <role-session>`. The explicit `prompt` verb is required because raw-agent parsing does not accept `-s` in the positional-agent form.

Scope every invocation to the Story's repository with `--cwd <absolute-repo-path>`. Use unique names such as `<run>-<story>-worker-1` and `<run>-<story>-validator-1`. A replacement worker increments its attempt number.

For first dispatch, choose a name not used by an earlier Story run and create a fresh session:

```bash
acpx --cwd <repo> <agent> sessions new --name <role-session>
```

On orchestrator resume, inspect and reuse the recorded session instead of calling `new` again. `sessions new` can replace an existing open scope, so uniqueness and plan reconciliation are required before creation.

Session lifecycle verbs do not share the prompt option shape: close a named session with `sessions close <role-session>`, not `sessions close -s <role-session>`. Check the installed command help before applying prompt-style flags to another verb.

Resolve the role profile before session creation. Select the advertised model and apply the profile's effort through the adapter's advertised model variant, config option, or matching validated startup option from `acpx_command`. For a registered agent, create the session, inspect its advertised config option ID, then run `acpx --cwd <repo> <agent> set <effort-option-id> <effort> -s <role-session>` and verify the accepted value before the first task prompt. Model ID and effort are separate settings unless the adapter explicitly advertises a combined variant; never synthesize an ID. Read the current adapter configuration before dispatch because provider-qualified IDs, option IDs, and supported effort values may differ.

## Dispatch a wave

Submit one complete worker or validator prompt to each named session:

```bash
acpx --cwd <repo> --format json --json-strict <agent> -s <role-session> --file <prompt-path>
```

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
