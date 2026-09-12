---
name: distill
description: "Use when a user or scheduler invokes $distill for a session retrospective or a bounded cross-session harness review."
disable-model-invocation: true
triggers:
  - user
---

# Distill Session Evidence into the Harness and Project Knowledge

Turn session evidence into the smallest verified harness and project-knowledge changes
that make future work more reliable. The harness includes intent and specs, the applicable
`AGENTS.md` instruction chain, repository Skills and their invocation metadata, tools and
scripts, environment and permissions, and verification and evals. Project knowledge
includes the durable documentation and decision rationale that give humans and agents an
accurate global view of the project.

Follow all four phases. Phase 3 is the single approval gate: confirmation of the proposed
candidate set authorizes its smallest in-scope edits. Ask again only for a materially
different target, an external repository, or a destructive change. Finish without edits
when no candidate survives the evidence and value gates.

## Operating Modes

Use one workflow with two evidence scopes:

- **Session mode** is the default. Review the current conversation and its tool evidence.
- **Review mode** is explicit or scheduler-invoked. Review a bounded set of recent
  sessions for recurring patterns, regressions, and the effectiveness of earlier changes.

In review mode, read `references/periodic-review.md` before Phase 1 and follow its evidence
boundary, batching, privacy, recurrence, and previous-change evaluation rules. A periodic
trigger starts an audit; it never authorizes edits or weakens the Phase 3 approval gate.
The caller or scheduler owns cadence. Distill may use and update a user-local review
checkpoint for the default evidence boundary, but the checkpoint is a soft retrieval
cursor and never prevents the manager from reopening an earlier window when the evidence
calls for it.

### BB stage review

When the caller explicitly asks to review a bounded BB stage, use **Review mode** with the
`repo-harness` profile. Read [BB 阶段复盘](references/bb-stage-review.md) before collecting
threads. It defines the BB-only adapter: how to freeze the boundary, cover interrupted
threads with their continuations, request each session's `$distill`, and dispatch one
read-only aggregator. The adapter never bypasses this Skill's evidence rules or Phase 3
approval gate.

Use `scripts/bb-stage-retro.py discover` to produce a candidate thread list and
`scripts/bb-stage-retro.py plan` before its explicit `apply` command. The script only
coordinates BB records and prompts. It neither decides what is durable nor writes a
repository artifact. Its exact interface and failure handling live in the BB reference.

## Phase 1: Replay

Reconstruct the complete session trajectory:

- Intended outcome and acceptance criteria
- Actions, tool feedback, failures, retries, and repeated work
- Every explicit user correction, clarification, preference, or rejection of an agent
  assumption. Capture the **belief delta**: what the agent believed, what the user
  established instead, the intended scope, and the evidence for that scope.
- Every non-obvious gotcha whose root cause and recovery were verified. Keep the reusable
  conclusion separate from the ordinary error, failed command, or retry that exposed it.
- Successful shortcuts worth making repeatable
- User interaction friction, including avoidable questions or excessive output
- Every repository instruction or Skill that shaped the work, from `AGENTS.md` discovery
  and Skill selection through instruction loading, execution, validation, and handoff.
  Record missed or surprising invocation, unclear steps, ignored guidance, workarounds,
  and places where the user had to compensate for the harness.
- Every durable product or technical decision made or clarified by the user, including
  its rationale, constraints, rejected alternatives when they prevent future confusion,
  and affected project concepts
- Every material decision introduced by the agent, the user-visible consequences that
  were disclosed before approval, and the exact evidence that the user confirmed it

In review mode, merge semantically equivalent signals across the bounded evidence window
as specified in the periodic-review reference. Do not turn shared error text or repeated
retries within one task into false recurrence.

Compare the actual path with the shortest reliable path. Classify each material signal as
a **harness gap**, **project-knowledge gap**, **execution defect**, **environment or tool
defect**, **request ambiguity**, or **one-off event**. An agent mistake becomes a harness
candidate only when the harness could reliably prevent, expose, or shorten it. A session
detail becomes a project-knowledge candidate only when it improves durable global
understanding or preserves decision rationale. Carry unverified improvements as
hypotheses.

Complete this phase when every material detour, correction, shortcut, durable decision,
and cross-session pattern within the stated evidence boundary has traceable conversation
or tool evidence.

## Phase 2: Audit and Route

Read [audit and routing rules](references/audit-and-route.md) for the evidence, authority, scope, recurrence, and project-knowledge/harness lanes. Inspect relevant existing sources before proposing additions. Prefer removing stale, conflicting, duplicate, or superseded guidance and route surviving signals to one authoritative home.

Complete when every surviving signal has a supported action and target, with overlap and conflicts accounted for. No surviving candidate means no edits.

## Phase 3: Decide and Apply

When candidates survive, read [decision brief and approval](references/decision-brief.md). Present their user-visible problem, proposed result, and current verification in the user's language, with technical details disclosed separately.

Resolve real choices and obtain authorization for the candidate set. Reuse existing explicit approval for the same candidates and targets; an ordinary retrospective request or scheduler trigger alone does not approve newly discovered changes. Apply the smallest approved changes and continue through proof without another routine confirmation. A new target, external repository, or destructive action needs its own applicable authorization.

## Phase 4: Prove

Validate each coherent set of changes with the fastest relevant checks. Run broader
checks only for affected behavior or unresolved evidence; repeat checks only when a later
change or failure invalidates the result. For every candidate, verify the predicted recurrence is prevented, exposed, or
shortened. In review mode, use post-change evidence to classify earlier accepted changes
as effective, inconclusive, regressed, or superseded. Do not claim success when the window
is too short or partial to contain a comparable opportunity. Revise or revert a change
whose prediction fails.

Check that conflicts and duplicates are gone, links and pointers resolve, deterministic
facts and implementation details are not needlessly cached in prose, every captured
decision has one authoritative home and explicit approval provenance, and a stakeholder
reading only the human-facing sources can explain each material choice and its consequence.
Check that improved skills validate and unrelated user work remains untouched.

Report the user-visible outcome first. Put files, commands, validation results, and any
reviewed skills or signals that correctly produced no change afterward as supporting
detail. In review mode, include the evidence boundary and the effectiveness classification
for previously accepted changes. Keep the handoff concise and use the same plain-language-
first structure as the decision brief.
