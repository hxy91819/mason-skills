# Periodic Review Mode

Load this protocol only after `distill` selects **Review mode**. It extends the four main
phases; it does not create a parallel learning system or a second approval path.

## 1. Establish the review boundary

Review mode must be explicitly requested or invoked by an external scheduler. The skill
does not schedule itself or imply that a cadence has been created. A useful external
cadence is weekly while a project is active and at milestone or release boundaries; skip
routine windows with no material work.

Choose the boundary in this order:

1. A user- or caller-supplied date, commit, milestone, branch, or session range.
2. Otherwise, a valid checkpoint from the user-local state described below. Start strictly
   after its `reviewed_through` cursor and use the current invocation time as the fixed
   upper bound.
3. If no usable checkpoint exists, use the most recent seven days, initially capped at ten
   sessions with material work.

The checkpoint is a retrieval optimization, not an evidence exclusion rule. The manager
may widen the lower bound or reopen already covered sessions when a regression, an
unresolved signal, a coverage gap, a user request, or an informed judgment makes that
useful. State the widened boundary and reason in the evidence-provenance sentence, and do
not count a reopened session as a new recurrence merely because it was revisited.

Store the checkpoint outside the repository, by default at
`~/.local/state/distill/periodic-review/<repository-key>.json` (respect
`XDG_STATE_HOME` when it is set). Derive `<repository-key>` from the canonical remote
identity and canonical worktree path when both are available, otherwise use the canonical
worktree path, so separate repositories and worktrees do not share a cursor. Strip URL
credentials before using a remote identity; if it cannot be safely normalized, use the
path. Keep only the minimum state needed for retrieval:

```json
{
  "schema_version": 1,
  "repository": "<canonical remote + worktree identity>",
  "last_review_date": "YYYY-MM-DD",
  "reviewed_through": "YYYY-MM-DDTHH:MM:SSZ"
}
```

`last_review_date` is the user's local calendar date for display; `reviewed_through` is
the exact RFC 3339 cursor used for exclusion and may carry the local offset.

Create the parent directory as needed. Write the replacement in the same state directory
and rename it atomically so an interrupted write cannot corrupt the previous cursor.

Read malformed, future-dated, or inaccessible state as unavailable and report that
coverage limitation. After all evidence batches and Phase 4 verification finish
successfully, including a review that produces no candidate, atomically update
`last_review_date` and `reviewed_through` to the completed fixed upper bound. Do not
advance the cursor for an interrupted review, a review still waiting for Phase 3 approval,
or an unverified partial result. Failure to write this optional local state must not block
the review; report it and continue without pretending the cursor advanced.

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

Freeze the upper boundary before collection. Process a large window in deterministic
batches rather than dropping sessions silently; continue until every material session in
the stated boundary has been considered, even when that requires more than the initial
ten-session batch. Track batch cursors and coverage only in temporary audit data, merge
semantically equivalent signals before Phase 2, and expose any missing batch or source in
the provenance sentence. Do not persist raw transcripts, secrets, incidental errors, or
user wording. If a scratch file is necessary, place it outside the repository and delete
it before handoff.

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
approved scope. Update only the user-local checkpoint after the complete review as defined
above; never write a recurring report, review ledger, or checkpoint into the repository.

During Phase 4, run current verification for every new change and report earlier accepted
changes as effective, inconclusive, regressed, or superseded. Never claim that a future
review is scheduled; the caller or external scheduler owns cadence. A later review may
still reopen earlier sessions when its evidence judgment warrants it.
