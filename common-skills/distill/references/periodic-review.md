# Periodic Review Mode

Load this protocol only after `distill` selects **Review mode**. It extends the four main
phases; it does not create a parallel learning system or a second approval path.

## 1. Establish the review boundary

Review mode must be explicitly requested or invoked by an external scheduler. The skill
does not schedule itself, remember the last run, or imply that a cadence has been created.
A useful external cadence is weekly while a project is active and at milestone or release
boundaries; skip routine windows with no material work.

Choose the boundary in this order:

1. A user- or caller-supplied date, commit, milestone, branch, or session range.
2. Otherwise, the most recent seven days, capped at ten sessions with material work.

A material session contains at least one substantial repository change, durable decision,
explicit correction, verified non-obvious gotcha, repeated debugging path, or meaningful
workflow or interaction friction. Exclude trivial lookups and unrelated conversations.
Limit collection to the current repository or worktree unless the user explicitly expands
the scope.

State the exact boundary, evidence sources, number of distinct tasks or sessions, and any
coverage gaps. If conversation traces are unavailable, do not reconstruct user corrections
from commits, diffs, or tests. Repository evidence may corroborate behavior and outcomes;
it cannot prove what the user intended or approved.

## 2. Collect evidence safely

Prefer evidence in this order when available:

1. Conversation and approval traces for corrections, clarifications, preferences, and
   decisions.
2. Tool traces and command outcomes for the actual execution path.
3. Commits, diffs, tests, CI, issues, and pull requests for corroborating implementation
   and post-change behavior.
4. Existing specs, instructions, skills, and documentation for current authority and
   discoverability.

Process a large window in batches rather than dropping sessions silently. Keep batch
results as temporary audit data and merge them before Phase 2. Do not persist raw
transcripts, secrets, incidental errors, or user wording. If a scratch file is necessary,
place it outside the repository and delete it before handoff.

## 3. Build a temporary signal table

Track only the fields needed to compare evidence:

- Semantic pattern key, based on the belief, constraint, root cause, or workflow gap
- Signal type: explicit correction, clarification or preference, rejected assumption,
  verified gotcha, reusable shortcut, repeated friction, durable decision, or prior-change
  outcome
- Belief or behavior before, and the corrected or verified conclusion after
- Intended scope and authority
- Evidence references and distinct task or session identities
- First seen, last seen, and distinct-task recurrence count
- Current authoritative source, if any
- Whether evidence occurred before or after a relevant accepted change
- Current disposition: unaddressed, already addressed, regressed, superseded, unverified,
  or one-off

The table is an analysis aid, not a repository artifact. Do not create `.learnings`, a
review ledger, or a permanent event database.

## 4. Normalize recurrence without manufacturing it

Merge signals by meaning, not by shared wording or error strings. Multiple retries,
commands, or resumed conversations serving the same task count as one occurrence. Count a
pattern again only when a distinct task or decision opportunity independently exposes it.

Apply these evidence rules:

- An explicit user correction is high-authority evidence within its stated scope. One
  occurrence may be enough when the constraint is durable and the future cost is real.
- A clarification or behavioral reversal without an explicit correction is lower-authority
  evidence until the intended rule and scope are confirmed.
- An agent-inferred gotcha requires a verified root cause and successful recovery. The
  ordinary error that exposed it is not itself a learning.
- Recurrence raises expected value, not truth. A frequent unsupported explanation remains
  unsupported.
- A mechanically verified, high-impact one-off may justify action without recurrence.
- Recurrence after an accepted change is stronger than pre-change recurrence because it
  tests whether the change was correct, discoverable, and strong enough.

## 5. Evaluate earlier Distill changes

When the window contains evidence after an earlier accepted change, identify the change's
approval or enactment boundary and separate pre-change from post-change observations.
Classify the result:

- **Effective**: a comparable opportunity occurred and the old failure was prevented,
  exposed earlier, or made materially cheaper.
- **Inconclusive**: no comparable opportunity occurred, or evidence coverage is too partial
  to judge.
- **Regressed**: the pattern recurred after the change.
- **Superseded**: later approved intent or implementation made the earlier change obsolete.

Absence of recurrence is not proof when there was no comparable opportunity. For a
regression, diagnose the failure before proposing more guidance: the source may be wrong,
unreachable, too broad, too weakly enforced, contradicted elsewhere, or based on a false
hypothesis. Do not create another candidate when the existing authoritative change is
working.

## 6. Synthesize through the normal four phases

Run the normal Phase 2 authority, scope, value, routing, and duplication gates on every
surviving pattern. A recurring error is not a candidate; a verified reusable conclusion
may be. Cadence is an opportunity to prune stale guidance and evaluate previous changes,
not a quota for new rules.

Before the Phase 3 decision brief, provide one plain evidence-provenance sentence with the
review boundary, coverage, and material gaps. In each technical note, identify whether the
support is an authoritative correction, cross-task recurrence, or post-change regression.
Keep immediate checks separate from predictions that require future sessions.

If no candidate survives, finish without edits. Report the boundary and summarize which
material signals were already addressed, one-off, unverified, superseded, or outside the
approved scope. Do not write a recurring report or checkpoint into the repository.

During Phase 4, run current verification for every new change and report earlier accepted
changes as effective, inconclusive, regressed, or superseded. Never claim that a future
review is scheduled; the caller or external scheduler owns cadence.
