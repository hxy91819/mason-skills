---
name: large-task-orchestrator
description: Persistently orchestrate an existing large task plan with external worker and validator agents, one Story per session.
disable-model-invocation: true
---

# Large Task Orchestrator

Use the agent that invoked this Skill as the orchestrator. Run all Story implementation and validation through external agents controlled by ACPX or Herdr.

## Roles

- **Orchestrator:** the current agent. Own plan state, dependency waves, routing, dispatch, handoffs, integration, and user decisions. Stay on the control plane instead of implementing Stories or using Codex collaboration subagents.
- **Worker:** an external leaf agent. Give each Story a fresh worker session. A session may receive fixes and follow-ups for that Story, and never work on another Story.
- **Validator:** a separate external leaf agent and session for the same Story. Check completion, report evidence to the orchestrator, and never implement fixes.

Workers and validators do not start other agents, edit the large task plan, or push repository changes.

## Drive the mission autonomously

Operate as a persistent goal runner: the default response to uncertainty is to inspect, decide, record, and continue. Resolve worker and validator questions yourself when the choice stays inside the accepted plan, task scope, and existing authority. Choose the lowest-risk reversible option supported by repository evidence, then validate the outcome; do not ask the user to select among equivalent implementation, tooling, routing, or recovery options.

Within the accepted Goal, the orchestrator owns the solution path. It may reorder, split, merge, insert, or rewrite not-yet-started Stories, change routes and implementation tactics, and add work required by new evidence. Record each non-obvious plan choice as an Agent decision with its evidence, trade-off, and impact; increment `intent_version` when a Story's scope or acceptance changes, and keep the original Goal, golden acceptance, and user boundaries unchanged. A validator judges the unchanged acceptance contract, not whether the initial plan was followed.

Treat runtime enablement as an orchestration decision. On startup/resume, reconcile every recorded capability lease before dispatch: restore or quarantine any project/personal elevation whose owner is absent, expired, or not verified closed. When an accepted Story requires ports, containers, network access, filesystem writes, or similar worker capabilities, adjust the selected worker's session to the minimum sufficient capability and continue. Prefer task/session scope. A project-level change is allowed only inside an isolated project scope, with an owner, expiry/checkpoint, serialized access for the elevation window, and restoration plus inheritance verification at Story close, handoff, abort, or restart. If a configured personal profile is the only viable authorized surface, apply the same lease requirements. If any restoration or verification fails, keep the affected chain blocked and do not dispatch unrelated work through the elevated scope. Add a notebook entry only when the change affects future routing or recovery.

Record other non-obvious execution decisions in the authoritative plan field that owns the outcome, normally the execution-card handoff or verification evidence. Use the notebook only for its qualifying recovery events. A decision record is evidence for resumption, not a request for retrospective approval.

Escalate only when no safe in-scope action can make meaningful progress because at least one of these conditions holds:

- Required credentials or authority are unavailable to the orchestrator and cannot be obtained from the configured environment.
- The next action is destructive, difficult to reverse, materially externally visible or costly, or expands the user's requested scope.
- The choice changes product intent, acceptance criteria, or an authorized architecture boundary and the plan or repository provides no defensible default.
- Concurrent edits conflict in the same semantic area and their intended outcome cannot be reconciled from available evidence.
- Every viable control surface, route, and proportionate recovery for the affected work has been exhausted, or the validation contract requires a user-authorized replan.

Before marking work `blocked`, inspect the exact failure, try the safe applicable recovery paths, and continue every independent ready Story. Block only the affected dependency chain; stop the mission only when no other meaningful plan work can proceed. When escalation is unavoidable, ask one minimum decision question and report the evidence, attempted recoveries, affected Stories, and the action that will resume execution. Do not treat ambiguity, a worker's first failure, a preference between reasonable options, or a sandbox mismatch by itself as a user blocker.

## Use the plan as state

Treat the existing large task plan as the sole source of truth. Preserve its schema and status vocabulary; do not create a parallel ledger or repository sidecar.

When the plan follows the sibling `large-task-planning` contract, read [`../large-task-planning/agent-schema.md`](../large-task-planning/agent-schema.md) and use its `scripts/epic_story.py` commands for every Agent JSON update and dashboard render. Never add unsupported fields or edit `agent/*.json` directly.

Map orchestration phases onto its existing execution-card states:

| Card status | Orchestration meaning |
| --- | --- |
| `todo` | Not claimed; readiness comes from dependencies and the generated project status. |
| `in_progress` | Worker execution, `worker_done`, validation, and `needs_fix` remain active phases. Record the current agent/model/session and phase in existing `owner`, `verification`, and `handoff` fields. |
| `blocked` | An exhausted environment or authority failure, irreconcilable decision, `INSERT_STORY`, or `REPLAN` prevents the affected dependency chain from continuing safely. |
| `done` | Worker evidence is complete and the independent validator returned `CONTINUE`. |

Quota exhaustion is an execution-attempt outcome, not a Story state; record the handoff and keep the card `in_progress` while switching workers.

Only the orchestrator changes plan state. Patch and render promptly after dispatch, worker result, validator result, and handoff. On resume, run the plan's status command and reconcile every `in_progress` or `blocked` card against its recorded role/session, actual ACPX or Herdr session, working tree, and evidence before dispatching anything. Never redispatch a non-`todo` Story merely because conversation context was lost.

## Keep one lightweight local notebook

Use `<repository>/.local/large-task-orchestrator/notebook.ndjson` as the default orchestrator notebook. Keep one file per repository and distinguish missions with `run_id`; never create one notebook per Story, worker, or validator. Keep it local and untracked. Before the first write, confirm the exact path is ignored; when necessary, add it to `.git/info/exclude` instead of changing the shared `.gitignore` merely for orchestration.

Create the file only at the first qualifying event. Append one compact JSON object for:

- An unexpected provider, quota, session, tool, or environment failure that changes routing or the next action.
- A worker handoff, concurrent-edit conflict, or validator result whose context is not fully represented by the execution card.
- Discovery, promotion, or resolution of a blocker.
- A checkpoint immediately before context compaction or orchestrator handoff when active work would otherwise be hard to reconstruct.

Do not record routine successful dispatches, ordinary progress messages, full transcripts, diffs, requirements, test logs, or facts already authoritative in the plan. Keep each entry under 1200 UTF-8 bytes with only `time`, `run_id`, `event`, `story`, `session`, up to three short `facts`, `decision`, `next`, and `plan_ref`; omit unused fields and all secrets. Use no more than one checkpoint per Story phase. When a run approaches 30 entries, append one consolidation entry and continue only for new blockers or materially changed recovery actions.

The notebook is recovery evidence, never a status source. If an event changes readiness, dependencies, acceptance, sequence, or user decisions, update the execution card, risk register, or authorized plan first and let the notebook point to that record. On resume, read the plan first, then only the latest relevant notebook entries, then reconcile actual agent sessions and Git state.

Before dispatch and again before integration, read applicable `AGENTS.md` files and inspect the current branch, `git status --short`, and `git worktree list`. Treat unrelated changes as concurrent work and preserve them.

## Select the control surface

- Prefer ACPX for headless, persistent, structured orchestration. When using it, follow the short path in [references/acpx.md](references/acpx.md): select one candidate, run one preflight, create/ensure one session, and dispatch. Read recovery guidance only when recovery is needed.
- Use Herdr when `HERDR_ENV=1` and visible terminal panes are useful or requested. Read [references/herdr.md](references/herdr.md) before using it.
- If neither surface is usable, report the missing capability instead of substituting built-in subagents.

## Build execution waves

Derive a dependency DAG from the plan. A Story is claimable only when its dependency cards are `done` and the generated project status marks it ready. Run claimable Stories in parallel only when their write scopes are disjoint or an existing worktree arrangement isolates them. Serialize shared-file, schema-before-consumer, migration, and integration work.

Use existing worktrees when the plan assigns them. Never create, switch, clean, stash, reset, or remove branches or worktrees without explicit user authorization. Choose concurrency from ready work, provider capacity, and collision risk.

## Route external roles

Before creating any worker or validator session, read [references/orchestration-config.md](references/orchestration-config.md) and resolve the external configuration. Use the `frontend` worker route for a frontend-dominant Story and the `default` worker route otherwise; use the validator's `default` route for the validation gate. For mixed Stories, classify by the highest-risk portion; split only when the plan preserves independent acceptance and ownership.

Walk the selected candidate array lazily. Preflight and use the first candidate; advance only when it is unavailable, incompatible, or quota-exhausted. If no candidate remains, block the Story with the exact routing reason instead of inventing a fallback.

Classify the Story's difficulty and select the matching configured effort profile when one exists. Treat the adapter's advertised model and effort options as authoritative. If effort is unsupported, use the adapter default without probing alternatives. Record the resolved role, route, candidate, model, effort, and configuration sources in the execution-card handoff.

## Dispatch a worker

### ACPX golden path

For a normal first dispatch, use this exact sequence after reading the current Story and route:

```bash
acpx --cwd <repo> <agent> sessions new --name <role-session>
acpx --cwd <repo> <agent> sessions show <role-session>
acpx --cwd <repo> <resolved-permission-flags> --non-interactive-permissions fail --format json --json-strict <agent> -s <role-session> --file <prompt-path>
```

`acpx` has no `preflight` subcommand. `sessions new` is the fresh-session handshake and bootstrap for first dispatch; on resume, inspect the recorded session and use `sessions ensure` only for that exact session. ACPX permission policies match tools, not reliable file paths, command arguments, or network destinations; they are not a Story boundary. Use automatic approval only when the selected provider sandbox independently enforces the Story's repository, command, and network scope, and record that evidence. Otherwise choose a route with enforceable isolation or let the worker fail closed under `--non-interactive-permissions fail`; never present a broad tool approval as least-permissive Story isolation. If the handshake advertises no effort option, use the adapter default and dispatch.
`acpx` has no `preflight` subcommand. `sessions new` is the fresh-session handshake and bootstrap for first dispatch; run `sessions show` immediately after it and record the provider session identifier, agent, cwd, effective permission flags, and sandbox/capability fingerprint as the baseline before sending any prompt. On resume, run `sessions show <role-session>` first and compare all of those fields. Use `sessions ensure` only when the exact session and capability fingerprint are present and resumable; immediately run `sessions show` again and compare before prompting. If the session is missing, closed, mismatched, or changed during ensure, quarantine/reconcile the workspace and create a new attempt with the prior handoff instead of silently replaying under the same attempt. After every strict-JSON prompt, read the provider `agentSessionId` (or equivalent advertised identifier) and compare it with the baseline; a changed or missing identifier is a continuity failure. Quarantine and reconcile all workspace side effects from that prompt before any validator or retry, then create a new attempt; do not accept its work. Resolve `<resolved-permission-flags>` before dispatch: automatic approval (including `--approve-all`) is valid only when the selected provider sandbox independently enforces the Story's repository, command, and network scope, and that evidence is recorded. ACPX permission policies match tools, not reliable file paths, command arguments, or network destinations; they are not a Story boundary. Otherwise choose a route with enforceable isolation or let the worker fail closed under `--non-interactive-permissions fail`; never present a broad tool approval as least-permissive Story isolation. If the handshake advertises no effort option, use the adapter default and dispatch.

Create a fresh worker session whose unique name contains the mission/run, Story ID, `worker`, and attempt number. Never reuse a worker session from a completed Story.

Send a self-contained prompt containing:

- Story ID, objective, verified dependencies, and acceptance criteria.
- Repository path, current branch, owned write scope, and do-not-touch boundaries.
- Relevant plan context and concurrent changes that must be preserved.
- Required observable tests or validation commands.
- Authority boundaries for commits, branches, worktrees, external effects, and destructive actions.
- Instructions to read applicable `AGENTS.md`, work directly as a leaf executor, leave plan state to the orchestrator, and report blockers without starting other agents.

Require the worker's final response to end with this strict JSON block:

```json
{
  "story_id": "STORY-ID",
  "status": "worker_done",
  "summary": "observable outcome",
  "files_changed": [],
  "verification": [{"command": "command", "result": "pass", "evidence": "concise evidence"}],
  "remaining_work": [],
  "blocker": null,
  "handoff": "context needed by a replacement or validator"
}
```

`status` is `worker_done`, `blocked`, `failed`, or `quota_exhausted`. If the block is absent or invalid, ask the same worker session to emit a corrected block. A worker report leaves the execution card `in_progress`; only the validator gate can move it to `done`.

## Run the lightweight validation gate

After `worker_done`, create a separate validator session dedicated to that Story using the resolved validator route. Keep the card `in_progress` and record the validator role/session in its existing handoff data.

Explicitly invoke the sibling `$story-direction-review` Skill in the validator prompt and follow its fixed output contract. Resolve its `SKILL.md` from this Skill's sibling directory and include that absolute path in the prompt because an external agent's Skill registry may differ from the orchestrator's. Give it the Epic, Story, execution-card handoff, worker evidence, current diff, and remaining Story map. It checks goal direction, acceptance coverage, major omissions, and whether the next Story remains valid. Do not substitute a broad review, `autoreview`, architecture audit, style sweep, or refactor pass unless the plan explicitly requires one.

Grant read and targeted-test authority but no code-editing authority. Route its single conclusion back to the orchestrator:

- `CONTINUE`: reconcile the evidence, patch the card to `done`, render the dashboard, and release newly claimable Stories without repeating a broad review.
- `PATCH_PROMPT`: keep the card `in_progress`, send the supplied prompt to the same worker session, then reuse the same validator session for another direction check.
- `INSERT_STORY`: patch affected work to `blocked` and apply the review Skill's insertion and authorization rules before dispatching further dependent work.
- `REPLAN`: patch affected work to `blocked`, surface the minimum user decision, and resume only after the plan is authorized and rendered.

## Supervise and recover

Inspect tool state, transcripts, and the working tree before retrying a stalled or failed worker. Treat provider quota, rate-limit, usage-cap, or model-unavailable errors as `quota_exhausted`, distinct from code or test failures:

1. Stop assigning new work to that provider for the current wave.
2. Preserve partial edits and verification evidence.
3. Record the failed attempt and handoff in the plan.
4. Create a fresh worker session for the same Story under the next capable agent, with a new attempt number.
5. Send the original contract, prior result, current diff, completed checks, and precise remaining work.

Do not repurpose failed or exhausted sessions for another Story.

## Integrate waves

After each wave, reconcile the working tree, run proportionate integration checks, checkpoint any validated work that could not be committed safely per Story, and release newly unblocked Stories. If concurrent agents touched the same semantic area despite ownership boundaries, pause that area and resolve only when intent is unambiguous; otherwise ask the user.

## Checkpoint commits and final push

Use Git commits as recoverable execution checkpoints. A phase is complete only when a Story's validator returns `CONTINUE`, the orchestrator reconciles its evidence, updates the card to `done`, renders the dashboard, and runs the Story's required checks. Then the orchestrator commits that Story's authorized changes with its Story ID in the message.

Workers and validators never commit. Do not commit `worker_done`, `PATCH_PROMPT`, quota handoffs, routine notebook checkpoints, failing checks, or an `in_progress` card. Stage only the completed Story's owned files and plan artifacts; preserve unrelated concurrent changes. When parallel Stories or concurrent edits cannot be separated safely at file or hunk level, wait until all affected Stories validate, run the wave checks, and make one wave checkpoint commit listing their Story IDs. Put later cross-Story integration fixes in a separate integration commit after their checks pass. Never rewrite an earlier checkpoint merely to make the history tidier.

Checkpoint commits stay local during execution. After every Story card is `done` and combined integration checks pass, the orchestrator owns the single final push. Do not push a partial mission while a Story is blocked unless the plan explicitly defines that partial delivery or the user accepts it.

1. Recheck the current branch, `git status --short`, `git worktree list`, the complete diff, and commits ahead of the upstream. Confirm the delivery contains only task-authorized changes; preserve unrelated concurrent work and never stage it merely to obtain a clean tree.
2. If validated task changes remain uncommitted, commit only those changes using the Story, wave, or integration checkpoint rule above. Do not amend or rewrite existing commits unless explicitly authorized.
3. Push the current branch directly to its configured upstream without asking for another confirmation. If no upstream exists and exactly one suitable remote is unambiguous, set the upstream while pushing the current branch.
4. Never force-push, push tags, push another branch, bypass hooks, or choose among ambiguous remotes. Treat authentication, protected-branch, non-fast-forward, ambiguous-remote, and inseparable-unrelated-commit failures as blockers instead of expanding scope.
5. Record the pushed commit SHA, remote, branch, and push result in the execution card's existing `handoff` or `verification` string. Do not put command-result objects in `verifies`; under the sibling planning schema, `verifies` is only a string array of affected test IDs.

Once the card, checks, commit, and push already satisfy the completion contract, do not create a follow-up commit solely to enrich optional orchestration metadata. Preserve the successful terminal state and report any non-authoritative recovery detail from the local notebook instead.

Claim successful completion only when every Story card is `done`, combined integration checks pass, the intended repository changes are pushed, and the plan records worker and validator sessions, evidence, quota handoffs, delivery state, and remaining risks. Otherwise report the mission as blocked or partially delivered with its exact reason.
