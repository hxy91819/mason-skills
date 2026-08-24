---
name: distill
description: Review the current conversation as a harness and project-knowledge retrospective, then prune or strengthen the specs, documentation, decisions, context, instructions, tools, checks, workflows, and environment that shape future human and agent work. Use after substantial agent work, debugging, retries, user corrections, or skill execution when session evidence may reveal reusable improvements or durable product and technical decisions.
---

# Distill the Session into the Harness and Project Knowledge

Turn session evidence into the smallest verified harness and project-knowledge changes
that make future work more reliable. The harness includes intent and specs, context and
instructions, skills, tools and scripts, environment and permissions, and verification
and evals. Project knowledge includes the durable documentation and decision rationale
that give humans and agents an accurate global view of the project.

Follow all four phases. Phase 3 is the single approval gate: confirmation of the proposed
candidate set authorizes its smallest in-scope edits. Ask again only for a materially
different target, an external repository, or a destructive change. Finish without edits
when no candidate survives the evidence and value gates.

## Phase 1: Replay

Reconstruct the complete session trajectory:

- Intended outcome and acceptance criteria
- Actions, tool feedback, failures, retries, corrections, and repeated work
- Successful shortcuts worth making repeatable
- User interaction friction, including avoidable questions or excessive output
- Every executed skill, from instruction loading through validation and handoff
- Every durable product or technical decision made or clarified by the user, including
  its rationale, constraints, rejected alternatives when they prevent future confusion,
  and affected project concepts
- Every material decision introduced by the agent, the user-visible consequences that
  were disclosed before approval, and the exact evidence that the user confirmed it

Compare the actual path with the shortest reliable path. Classify each material signal as
a **harness gap**, **project-knowledge gap**, **execution defect**, **environment or tool
defect**, **request ambiguity**, or **one-off event**. An agent mistake becomes a harness
candidate only when the harness could reliably prevent, expose, or shorten it. A session
detail becomes a project-knowledge candidate only when it improves durable global
understanding or preserves decision rationale. Carry unverified improvements as
hypotheses.

Complete this phase when every material detour, correction, shortcut, and durable decision
has traceable conversation or tool evidence.

## Phase 2: Audit and Route

Audit two required lanes before proposing additions: the applicable harness and the
project documentation touched by the session's concepts or decisions. A lane may produce
no candidate only after its relevant sources of truth have been inspected. Apply this
table to every existing rule, mechanism, or document in scope:

| State | Action |
|---|---|
| Stale | Delete it or update the source of truth. |
| Duplicate | Merge the meaning into one authoritative location. |
| Conflicting | Resolve to one authoritative meaning and location; ask if intent remains ambiguous. |
| Superseded | Remove prose replaced by equivalent verified enforcement, retaining only useful rationale or routing. |
| Misplaced | Move it to the narrowest effective scope; broader sources may point but must not restate. |
| Live | Keep it unchanged. |

Resolve conflicts from, in order: the user's current explicit intent and declared
authority and scope; approved specs and contracts; then implementation, tests, and
configuration as evidence of current behavior rather than automatic proof of intended
behavior. Never silently choose between unresolved semantic rules.

### Decision approval and visibility

Treat a decision as material when it changes what the user receives or must operate,
including product or release composition, independent usability, installation and offline
behavior, compatibility or migration, supported environments, security boundaries,
external dependencies, or operational ownership and cost.

For every material decision, record its provenance as explicitly user-confirmed, inherited
from an approved source, or agent-proposed. An agent-proposed decision remains a hypothesis
until the user sees the choice, user-visible consequences, rationale or tradeoff, and any
rejected alternative needed to understand it, then confirms it. Approval of a broad plan
counts only when that plan disclosed those consequences in plain language; package names,
implementation terminology, code, tests, or completed work do not prove informed approval.

Audit discoverability separately from authority. A material decision must be visible at
the appropriate abstraction level in a document its human stakeholders are expected to
read. Agent-only execution material may carry exact implementation details, but it cannot
be the sole place where the decision or its consequences appear. A human-facing summary
and a linked detailed contract are complementary, not duplicate sources of truth.

When one human-facing document carries multiple material decisions, present them as a
numbered decision list. For every item, state the decider, the agent recommendation and
whether the user accepted or rejected it, and the result and user-visible impact. Mark an
unconfirmed recommendation as pending user confirmation; never rewrite it as a user
decision because implementation already exists.

If implementation, documentation, or a gate relies on an unconfirmed or human-invisible
material decision, propose surfacing the decision for approval and revoking the affected
readiness or completion claim before treating current behavior as intended.

### Project-knowledge lane

Keep project documentation as a compact map for humans and agents: product concepts,
system boundaries, architecture, major workflows, and the decisions needed to reason
about them. Route details that code, tests, types, schemas, or configuration already make
cheap to discover back to those sources. When a durable decision's rationale is local to
code and the code cannot express why the choice exists, preserve it in a
decision-oriented comment; otherwise update the narrowest authoritative document.

Preserve every durable product or technical decision established by the user in one
authoritative location. Record the choice and why it was made, plus constraints or
consequences needed to apply it correctly. Do not create a duplicate decision log when an
existing product, architecture, specification, or code surface is already the better
home.

Simplify documentation in this order:

1. Delete or reconcile conflicting, superseded, and duplicate material.
2. Correct claims that disagree with current approved intent or verified behavior.
3. Consolidate scattered explanations into the narrowest authoritative source and leave
   pointers only where discovery requires them.
4. Add only missing global context or decision rationale that survives the evidence and
   value gates.

Prefer a net reduction when deletion or consolidation communicates the same truth. Keep
implementation walkthroughs, line-by-line behavior, inventories, and other cheap lookups
in code and the environment. Persistent documentation must describe the project, not the
retrospective session that caused it to change.

### Harness lane

Prefer pruning and consolidation before addition. Route the surviving signal to the
closest reliable layer:

| Signal | Harness layer |
|---|---|
| Unclear intent, behavior, or acceptance | Spec, contract, or task interface |
| Missing discovery or judgment-dependent guidance | Context pointer, focused documentation, or skill |
| Repeated operation | Tool, script, or common command entry point |
| Mechanically decidable invariant | Type/schema constraint, behavioral test, lint, or architecture check |
| Check must apply to every change | Run the same local verifier from pre-commit and existing CI |
| Environment, access, or consequence risk | Reproducible environment, permission boundary, or approval control |
| Promising but unverified change | Falsifiable eval with a predicted outcome |

CI is an execution venue, not the sole implementation of a rule. Keep one source for each
meaning. Let the environment state facts that are cheap to inspect; prose should carry
intent, rationale, non-obvious constraints, or routing. Remove a safety, permission,
approval, or validation rule only after equivalent protection is demonstrated.

Complete this phase when every surviving signal in both lanes has one proposed action and
target layer, with existing overlap and conflicts accounted for. Group signals solved by
the same authoritative change; they are one candidate, not several.

## Phase 3: Decide and Apply

Rank candidates internally by safety and correctness impact, likely recurrence, evidence
strength, feedback speed, maintenance cost, and context load. Present up to eight
non-overlapping candidates per round as a decision brief, grouped under **Harness** and
**Project knowledge** when both have candidates. Do not suppress one lane to make room
for the other, and do not present the internal audit record:

```markdown
You need to decide: <one-sentence decision and consequence>. Recommendation: <answer>.

1. **<overview title>**
   问题： <the current problem, same plain style as the solution paragraph>

   方案： <the solution, same plain style as the problem paragraph>

   > Technical detail: <mechanism, files, verification; same language as the user.>

Reply <shortest unambiguous confirmation or exclusion instruction>.
```

The main text must stand on its own for a reader who has not read the repository or the
audit. Write every user-visible sentence in the user's language, including the technical
blockquote. Do not switch to English because this skill or its examples are in English.
Keep code, paths, identifiers, and command names in their original form. The label
`Technical detail` may stay.

Give each candidate an overview title, two short prefixed paragraphs, and one technical
blockquote. The title names the topic; it does not have to name the mechanism. Prefix the
first paragraph with `问题：` and the second with `方案：` when the user wrote Chinese;
use `Problem:` and `Solution:` when the user wrote English. Keep both paragraphs in the
same plain register, with no file paths, commands, identifiers, or implementation facts.
The problem paragraph explains only the current problem. The solution paragraph explains
only the solution: what will be different, what still has to pass, what reruns on
failure, and where that failure is visible. An item is not ready if those two roles are
mixed into one paragraph, if a prefix is missing, or if the solution paragraph restates
the problem. Keep one claim per sentence; split or shorten chained clauses. Do not lead
with labels such as `Change`, `Verify now`, and `Eval`.

Apply the **wait-what check** before sending: hide every blockquote and read only the
opening, titles, and two prefixed paragraphs. A reader must be able to choose without
repository context, including restating the problem from `问题：` / `Problem:` and the
solution from `方案：` / `Solution:`. The opening must state the user-visible problems,
not name their technical causes. Move file paths, commands, identifiers, and other
implementation facts into the blockquote.

```markdown
<!-- Too technical for the decision layer -->
1. **Support npm 12 pack JSON and registry retries**

<!-- Problem and solution mixed; body leaks implementation; prefixes missing -->
2. **Don't run the slow checks in one queue**
   They currently run one after another, so split the CI workflow into parallel jobs.

<!-- Decision layer plus disclosed technical detail -->
1. **Avoid treating a successful release as failed**
   Problem: Publishing tools can report the same success differently, or take time to
   show up, so a real publish can look like a failure.

   Solution: Treat those expected differences as success, and wait a bounded time for
   the registry, without hiding a real failure.

   > Technical detail: Accept the npm 11 array and npm 12 single-object output, then use
   > bounded registry retries; verify with focused tests, typecheck, lint, and real output.

2. **Don't run the slow checks in one queue**
   Problem: They currently run one after another. When a later check flakes, the whole
   pipeline including work that already passed has to start over.

   Solution: Run the checks that can proceed independently in parallel. Landing still
   requires all of them; a failure reruns only that check, and that check's record is
   where the failure shows.

   > Technical detail: Split the serial CI `check` and release `preflight` into parallel
   > jobs; landing still requires every job to succeed.

<!-- Language switch: the user wrote Chinese, the note is English -->
> Technical detail: Split the serial CI `check` job into parallel jobs.

<!-- Same language as the user, including 问题： / 方案： -->
问题： 它们现在排成一条队。后面一项一抖，已经通过的部分也要整场重来。

方案： 能独立做的检查改成并行。合入仍要全部通过；一条失败只重跑那一条，失败记录在那一条上。

> Technical detail: 把 CI 的 `check` 和发布预检拆成并行 job；一条失败只重跑那一条，失败记录在那条 job 的日志里。
```

Keep technical precision through progressive disclosure instead of deleting it. Put
concrete versions, protocols, files, commands, code or configuration literals, function
names, implementation mechanisms, verification, and eval predictions only in the
blockquote below the relevant item. The main text may retain a technical domain term only
when the user needs it to tell candidates apart; explain it on first use when the project
has no clearer established name. Do not repeat technical details in both layers. Keep each
technical note focused on facts that help the user assess scope, confidence, or risk; it
is not a dump of the analysis trace. The note uses the user's language; only identifiers
stay in their original form.

Recommend the complete set by default; the user can confirm it or exclude candidate
numbers. Treat Phase 3 as one approval stage that may span multiple question rounds. For
any other real choices, map a decision tree, explore facts yourself, and ask the currently
unblocked frontier in numbered rounds of at most eight questions. Include a recommended
answer for every question. When more than eight frontier decisions remain, ask the eight
highest-impact independent decisions, then recompute the frontier after the reply. Do not
cap the total number of rounds or leave a branch silently assumed. Ask no question whose
viable answer is already determined by evidence, prior decisions, constraints, or
delegated defaults.

Do not edit until the frontier is empty and the user confirms the resulting candidate
set. That final confirmation is the single approval gate for all rounds. A candidate is
not ready without a `方案：` / `Solution:` paragraph and a verification that can run
now. Keep future-session predictions distinct from checks that can run now, even when
both appear in the same technical note.

After confirmation, read the target repository instructions and sources of truth, then
make the smallest approved changes. Prefer modifying or deleting existing surfaces over
creating new artifacts. Preserve supported behavior, safety controls, validation depth,
and approval gates. Create no persistent retrospective report; project-documentation
edits must update durable sources of truth, and an approved eval may add only the artifact
needed to run the experiment.

## Phase 4: Prove

Run the fastest relevant check after each change and the broader affected validation at
the end. For every candidate, verify the predicted recurrence is prevented, exposed, or
shortened. Revise or revert a change whose prediction fails.

Check that conflicts and duplicates are gone, links and pointers resolve, deterministic
facts and implementation details are not needlessly cached in prose, every captured
decision has one authoritative home and explicit approval provenance, and a stakeholder
reading only the human-facing sources can explain each material choice and its consequence.
Check that improved skills validate and unrelated user work remains untouched.

Report the user-visible outcome first. Put files, commands, validation results, and any
reviewed skills or signals that correctly produced no change afterward as supporting
detail. Keep the handoff concise and use the same plain-language-first structure as the
decision brief.
