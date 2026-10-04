---
name: distill
description: Review the current conversation or a bounded set of recent sessions as a harness and project-knowledge retrospective, with an explicit audit of repository Skills and AGENTS.md instructions, then prune or strengthen the surfaces that shape future human and agent work. Use only when a user or scheduler explicitly invokes $distill after substantial agent work, debugging, retries, user corrections, or skill execution, or for a periodic or milestone review.
disable-model-invocation: true
triggers:
  - user
---

# Distill Session Evidence into the Harness and Project Knowledge

Turn session evidence into the smallest verified changes that make future work more
reliable. The **harness** is everything that shapes an agent's run: intent and specs, the
applicable `AGENTS.md` chain, repository Skills and their invocation metadata, tools and
scripts, environment and permissions, and verification. **Project knowledge** is the
durable documentation and decision rationale that give humans and agents an accurate
global view of the project.

Run the four phases in order. Phase 3 is the single approval gate: the user's confirmation
of the candidate set authorizes its smallest in-scope edits. Ask again only for a
materially different target, an external repository, or a destructive change. Finish
without edits when no candidate survives.

## Evidence scope

- **Session mode** (default): the current conversation and its tool evidence.
- **Review mode** (explicit or scheduler-invoked): a bounded set of recent sessions, to find
  recurring patterns and judge whether earlier changes worked. See _Review mode_ below.

## Phase 1: Replay

Reconstruct the trajectory and record:

- The intended outcome and acceptance criteria.
- Actions, tool feedback, failures, retries, and repeated work.
- Every explicit user correction, clarification, or rejected assumption, as a **belief
  delta**: what the agent believed, what the user established, and the intended scope.
- Every non-obvious gotcha whose root cause and recovery were verified, kept apart from the
  ordinary error that exposed it.
- Shortcuts worth making repeatable, and interaction friction (avoidable questions,
  excessive output).
- Every repository instruction or Skill that shaped the work: missed or surprising
  invocation, unclear steps, ignored guidance, and places the user had to compensate.
- Every durable decision the user made or clarified, with its rationale and constraints.
- Every material decision the agent introduced, what consequences were disclosed, and
  whether the user confirmed it.

Compare the actual path with the shortest reliable one. Classify each signal as a
**harness gap**, **project-knowledge gap**, **execution defect**, **environment or tool
defect**, **request ambiguity**, or **one-off**. An agent mistake becomes a harness
candidate only when the harness could reliably prevent, expose, or shorten it.

Done when every material detour, correction, shortcut, and decision in scope has traceable
evidence.

## Phase 2: Audit and route

Audit two lanes before proposing additions: the harness (always including the `AGENTS.md`
chain and the repository's Skills) and the project documentation touched by the session.
A lane may produce no candidate only after its sources of truth were inspected. Give every
existing rule or document in scope one state:

| State | Action |
|---|---|
| Stale | Delete it or update the source of truth. |
| Duplicate | Merge into one authoritative location. |
| Conflicting | Resolve to one meaning and location; ask if intent is ambiguous. |
| Superseded | Remove prose replaced by equivalent enforcement; keep useful rationale. |
| Misplaced | Move to the narrowest effective scope; broader sources point, not restate. |
| Live | Keep. |

Resolve conflicts by: the user's current explicit intent, then approved specs and
contracts, then implementation, tests, and config as evidence of current (not intended)
behavior. Never silently pick between unresolved rules.

### Evidence weight

Judge **authority** (is it intended truth?), **scope** (task, repository, team, user
preference, or general practice), **recurrence** (repeated cost across distinct tasks), and
**impact** separately.

- One explicit user correction can justify a candidate when its scope is clear and durable.
  A behavioral reversal without an explicit statement is a hypothesis.
- Keep task-local instructions out of repository rules, and personal preferences out of
  project truth; route preferences to user-scoped context when available.
- Agent-inferred gotchas need independent verification. Recurrence raises value, never
  truth. Retries inside one task count once.
- A verified, high-impact one-off may justify a candidate. Recurrence after an earlier
  change is the strongest signal that the change is wrong, unreachable, or too weak.

### Material decisions

A decision is **material** when it changes what the user receives or must operate:
release composition, installation or offline behavior, compatibility, supported
environments, security boundaries, external dependencies, or operating cost. Record each
one as user-confirmed, inherited from an approved source, or agent-proposed. An
agent-proposed decision stays a hypothesis until the user has seen the choice and its
consequences in plain language and confirmed it; finished code is not approval. Each
material decision must be visible in a document its human stakeholders read, not only in
agent-facing material. If work relies on an unconfirmed decision, propose surfacing it and
withdraw the affected completion claim.

### Project-knowledge lane

Keep project docs a compact map: concepts, boundaries, architecture, major workflows, and
the decisions needed to reason about them. Leave cheap lookups to code, tests, schemas, and
config. Preserve each durable user decision, with its rationale, in one authoritative
place. For a surviving candidate read [核心知识落点](references/knowledge-sinks.md) and
route it to the narrowest live source. Simplify in this order: remove conflicting,
superseded, and duplicate material; correct wrong claims; consolidate; add only what is
still missing. Prefer a net reduction. Docs describe the project, never the retrospective.

### Harness lane

Prune and consolidate before adding. Route each surviving signal to the closest reliable
layer:

| Signal | Layer |
|---|---|
| Unclear intent or acceptance | Spec, contract, or task interface |
| Missing discovery or judgment guidance | Context pointer, focused doc, or Skill |
| Repeated operation | Script or common command entry point |
| Mechanically decidable invariant | Type/schema, behavioral test, lint, or architecture check, run from pre-commit and CI |
| Environment, access, or consequence risk | Reproducible environment, permission boundary, or approval control |
| Promising but unverified change | Falsifiable eval with a predicted outcome |

Classify an agent mistake before routing it. A **mechanical** violation (a fixed syntactic
pattern, a banned API, an import shape, a file-location rule) gets a deterministic check
in the repository's own linter, pre-commit hook, or CI, whichever is cheapest; build the
check rather than writing the rule. Prose rules are for **judgement calls** no check can
replace, and they belong in the coding standards the review stage reads, because the
reviewer works from a diff while the implementer already carries the heaviest context.
Read the repository's existing check commands and CI first: a check that exists but is
unwired or broken is the finding. A repository with no guardrail at all (no pre-commit
hook and no CI job running its lint, typecheck, or tests) is itself a candidate.

Inventory the repository's Skills (names, descriptions, invocation policy) and deep-read
every Skill that was invoked, edited, expected to trigger, or overlaps a signal. Check them
as a system:

- **Coverage**: one clear owner per recurring job; no gaps or overlapping triggers.
- **Invocation**: names, descriptions, explicit-only markers, and `agents/openai.yaml`
  agree with intended use.
- **Reachability**: the right instructions load before the decision they govern.
- **Usability**: branches, gates, completion criteria, and failure handling run without
  avoidable questions or workarounds.
- **Coherence**: instructions, scripts, validators, and host behavior reinforce one
  workflow.
- **Effectiveness**: where comparable evidence exists, did the Skill change the path as
  intended?

Report mechanically demonstrable defects (conflicting policy, a broken pointer, two Skills
claiming one trigger) even without a session failure. Remove a safety, permission, or
validation rule only after equivalent protection is shown.

Done when every surviving signal has one action and target layer. Signals solved by the
same change are one candidate.

## Phase 3: Decide

Rank candidates by safety and correctness impact, recurrence, evidence strength, and
maintenance cost. Present them in numbered rounds grouped by category (**Harness**,
**Project knowledge**), at most eight per message, with no cap on rounds. Recompute the
frontier after each reply until every candidate is shown and every choice settled.
Recommend the full surviving set by default. Ask choices in grilling's `Q1` / `Q2` format
with the recommended answer marked `➡️`; skip questions the evidence already answers.

Write every user-visible sentence in the user's language; keep code, paths, and
identifiers verbatim. Each candidate gets a title, a problem paragraph, a solution
paragraph, and one technical blockquote:

```markdown
你需要决定：<一句话的决定及其后果>。建议：<答案>。

1. **避免把成功的发布误判为失败**
   问题： 发布工具对同一种成功的报告方式不一致，或者要过一会儿才可见，所以真实的发布可能看起来像失败。

   方案： 把这些预期内的差异当作成功，并对注册表等待有限时间，同时不掩盖真正的失败。

   > Technical detail: 同时接受 npm 11 的数组和 npm 12 的单对象输出，再加有限次的注册表重试；用聚焦测试、typecheck、lint 和真实输出验证。

回复 <最短的确认或排除指令>。
```

Use `问题：` / `方案：` for Chinese and `Problem:` / `Solution:` for English. Both paragraphs
use plain words with no paths, commands, or identifiers; the problem paragraph states only
the problem, the solution paragraph only what will be different and how failure shows.
Everything technical (files, commands, mechanisms, verification, eval predictions) goes in
the blockquote, once. Check before sending: with the blockquotes hidden, a reader without
repository context can still choose.

In review mode, open with one sentence giving the review window, the number of sessions
covered, the evidence sources, and coverage gaps. Paraphrase corrections; never quote
private transcript text.

Edit nothing until the frontier is empty and the user confirms the set. A candidate is not
ready without a solution paragraph and a check that can run now.

## Phase 4: Apply and prove

Read the target repository's instructions and sources of truth, then make the smallest
approved changes, preferring to modify or delete existing surfaces over creating new
ones. Create no retrospective report, learning log, or review ledger in the repository.

Run the fastest relevant check after each change and the broader validation at the end.
Confirm that conflicts and duplicates are gone, pointers resolve, each decision has one
home with its approval provenance, changed Skills validate, and unrelated work is
untouched. Revise or revert a change whose prediction fails.

Report the user-visible outcome first, then files, commands, and results. In review mode,
classify each earlier accepted change as **effective**, **inconclusive**, **regressed**, or
**superseded**; absence of recurrence proves nothing without a comparable opportunity.

## Review mode

Use the boundary the user or scheduler gives (dates, commits, milestone, sessions);
otherwise the last seven days of sessions with material work in this repository. Freeze
the upper bound before collecting. A session is material when it holds a substantial
change, a durable decision, an explicit correction, a verified gotcha, a repeated
debugging path, or real friction.

Prefer evidence in this order: conversation and approval traces, tool traces, then commits,
diffs, tests, and CI as corroboration. Without conversation traces, never reconstruct user
intent or approval from repository evidence. Work through a large window in batches until
every material session is considered, and name any gap. Merge signals by meaning; a pattern
counts again only when a distinct task exposes it. Keep the signal table temporary.

### BB sessions

When the user asks to review a stage of BB threads:

1. List candidate threads with `bb thread list` for the window, then choose the material
   ones yourself; the list is not the evidence boundary.
2. When a thread was abandoned and another finished the same work, review only the last
   thread in that chain and count the pair once.
3. Send `$distill` (session mode) with `bb thread tell --mode auto` only to threads that are idle with
   no pending interaction; never steer a running thread.
4. Wait for every thread with `bb thread wait <id>`. If any fails, stop and report instead of aggregating.
5. Aggregate their outputs (`bb thread output <id> --json`) yourself, or dispatch one
   aggregator through `$bb-model-routing`, and continue at Phase 2 in review mode. The
   aggregator stops at the first Phase 3 brief and edits nothing.

BB thread records are the run history; keep no separate ledger. Look back with
`bb thread show <id> --json` and `bb thread log <id> --all`. `bb thread list` may page, so
state how threads were selected and any coverage gap.
