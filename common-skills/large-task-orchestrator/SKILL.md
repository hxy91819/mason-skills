---
name: large-task-orchestrator
description: Orchestrate an existing large task plan with external worker and validator agents, one Story per session.
disable-model-invocation: true
---

# Large Task Orchestrator

Use the agent that invoked this Skill as the orchestrator. Run all Story implementation and validation through external agents controlled by ACPX or Herdr.

## Roles

- **Orchestrator:** the current agent. Own plan state, dependency waves, routing, dispatch, handoffs, integration, and user decisions. Stay on the control plane instead of implementing Stories or using Codex collaboration subagents.
- **Worker:** an external leaf agent. Give each Story a fresh worker session. A session may receive fixes and follow-ups for that Story, and never work on another Story.
- **Validator:** a separate external leaf agent and session for the same Story. Check completion, report evidence to the orchestrator, and never implement fixes.

Workers and validators do not start other agents, edit the large task plan, or push repository changes.

## Use the plan as state

Treat the existing large task plan as the sole source of truth. Preserve its schema and status vocabulary; do not create a parallel ledger or repository sidecar.

When the plan follows the sibling `large-task-planning` contract, read [`../large-task-planning/agent-schema.md`](../large-task-planning/agent-schema.md) and use its `scripts/epic_story.py` commands for every Agent JSON update and dashboard render. Never add unsupported fields or edit `agent/*.json` directly.

Map orchestration phases onto its existing execution-card states:

| Card status | Orchestration meaning |
| --- | --- |
| `todo` | Not claimed; readiness comes from dependencies and the generated project status. |
| `in_progress` | Worker execution, `worker_done`, validation, and `needs_fix` remain active phases. Record the current agent/model/session and phase in existing `owner`, `verification`, and `handoff` fields. |
| `blocked` | A decision, environment, authority, `INSERT_STORY`, or `REPLAN` prevents safe continuation. |
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

- Prefer ACPX for headless, persistent, structured orchestration. Read [references/acpx.md](references/acpx.md) before using it.
- Use Herdr when `HERDR_ENV=1` and visible terminal panes are useful or requested. Read [references/herdr.md](references/herdr.md) before using it.
- If neither surface is usable, report the missing capability instead of substituting built-in subagents.

## Build execution waves

Derive a dependency DAG from the plan. A Story is claimable only when its dependency cards are `done` and the generated project status marks it ready. Run claimable Stories in parallel only when their write scopes are disjoint or an existing worktree arrangement isolates them. Serialize shared-file, schema-before-consumer, migration, and integration work.

Use existing worktrees when the plan assigns them. Never create, switch, clean, stash, reset, or remove branches or worktrees without explicit user authorization. Choose concurrency from ready work, provider capacity, and collision risk.

## Route workers by capability

Use this worker order, subject to live availability and the Story's dominant risk:

- General Stories: `codexl` → `codex` → `codexp` → Kiro.
- Frontend-dominant Stories: Kimi → `codexl` → `codex` → `codexp` → Kiro.

Treat `codexl` and `codexp` as candidates only when the selected control surface resolves them to live ACP-compatible agents. Inspect the installed registry and advertised model IDs before dispatch. For mixed Stories, select for the highest-risk portion; split only when the plan preserves independent acceptance and ownership.

Before creating any worker or validator session, read [references/worker-profiles.md](references/worker-profiles.md), resolve the external role profile, classify the Story's difficulty, and select the configured effort for the chosen agent/model. Treat the adapter's advertised model and effort options as authoritative. Record the resolved role, agent, model, effort, and profile source in the execution-card handoff so a replacement session can reproduce or intentionally change the choice. Keep provider-specific effort values in configuration rather than this Skill.

## Dispatch a worker

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

After `worker_done`, create a separate validator session dedicated to that Story. Keep the card `in_progress`, record the validator role/session in its existing handoff data, and prefer Pi with its advertised DeepSeek V4 Flash model. If that route is unavailable or quota-exhausted, use Kiro or another independent economical agent with enough domain ability for the acceptance criteria.

Explicitly invoke the sibling `$story-direction-review` Skill in the validator prompt and follow its fixed output contract. Give it the Epic, Story, execution-card handoff, worker evidence, current diff, and remaining Story map. It checks goal direction, acceptance coverage, major omissions, and whether the next Story remains valid. Do not substitute a broad review, `autoreview`, architecture audit, style sweep, or refactor pass unless the plan explicitly requires one.

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
5. Record the pushed commit SHA, remote, branch, and push result in the plan's delivery state.

Claim successful completion only when every Story card is `done`, combined integration checks pass, the intended repository changes are pushed, and the plan records worker and validator sessions, evidence, quota handoffs, delivery state, and remaining risks. Otherwise report the mission as blocked or partially delivered with its exact reason.
