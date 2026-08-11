---
name: distill
description: Review the current conversation as a harness-engineering retrospective, then prune or strengthen the specs, context, instructions, tools, checks, workflows, and environment that shape future agent runs. Use after substantial agent work, debugging, retries, user corrections, or skill execution when session evidence may reveal reusable improvements.
---

# Distill the Session into the Harness

Turn session evidence into the smallest verified harness change that makes future runs
more reliable. The harness includes intent and specs, context and knowledge, instructions
and skills, tools and scripts, environment and permissions, and verification and evals.

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

Compare the actual path with the shortest reliable path. Classify each material signal as
a **harness gap**, **execution defect**, **environment or tool defect**, **request
ambiguity**, or **one-off event**. An agent mistake becomes a harness candidate only when
the harness could reliably prevent, expose, or shorten it. Carry unverified improvements
as hypotheses.

Complete this phase when every material detour, correction, and shortcut has traceable
conversation or tool evidence.

## Phase 2: Audit and Route

Inspect the applicable harness before proposing additions. Audit each existing rule or
mechanism in scope:

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

Complete this phase when every surviving signal has one proposed action and target layer,
with existing overlap and conflicts accounted for. Group signals solved by the same
harness change; they are one candidate, not several.

## Phase 3: Decide and Apply

Rank candidates by safety and correctness impact, likely recurrence, evidence strength,
feedback speed, maintenance cost, and context load. Present at most five non-overlapping
candidates:

```text
N. <session signal> -> <harness gap>
   Change: <add | update | merge | delete | move | experiment> <target>
   Verify now: <check that can run in the current task>
   Eval: <future-session prediction, only when needed>
```

Recommend the complete set by default; the user can confirm it or exclude candidate
numbers. For any other real choices, use a decision tree: explore facts yourself, ask the
whole currently unblocked frontier in one short numbered round, include a recommended
answer, then recompute after the reply. Ask no question whose viable answer is already
determined by evidence, prior decisions, constraints, or delegated defaults. A candidate
is not ready without a concrete action target and a verification that can run now. Put
behavior that only a future agent run can prove under `Eval`, never `Verify now`. Write
`Verify now` as an inspection or command plus its expected result, not as a question.

After confirmation, read the target repository instructions and sources of truth, then
make the smallest approved changes. Prefer modifying or deleting existing surfaces over
creating new artifacts. Preserve supported behavior, safety controls, validation depth,
and approval gates. Create no persistent retrospective report; an approved eval may add
only the artifact needed to run the experiment.

## Phase 4: Prove

Run the fastest relevant check after each change and the broader affected validation at
the end. For every candidate, verify the predicted recurrence is prevented, exposed, or
shortened. Revise or revert a change whose prediction fails.

Check that conflicts and duplicates are gone, links and pointers resolve, deterministic
facts are not needlessly cached in prose, improved skills validate, and unrelated user
work remains untouched.

Report the candidates applied, actions taken, validation results, and any reviewed skills
or signals that correctly produced no change. Keep the handoff concise.
