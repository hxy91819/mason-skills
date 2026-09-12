# Decide and apply candidate changes

## Phase 3: Decide and Apply

Rank candidates internally by safety and correctness impact, likely recurrence, evidence
strength, feedback speed, maintenance cost, and context load. Treat the surviving
candidates as a decision tree. The **frontier** is the set of candidates whose
prerequisites and dependent choices are already settled. Present the frontier in numbered
rounds, grouped by independent categories such as **Harness** and **Project knowledge**;
split a category further when that keeps its choices understandable. Show at most eight
non-overlapping candidates or questions in one message, but impose no total candidate or
round limit. Do not suppress one category to fit another, silently drop lower-priority
items, or merge unrelated candidates just to fit the per-message window. After each reply,
recompute the frontier and continue with as many category rounds as needed until every
surviving candidate has been shown and every real choice is settled. Do not present the
internal audit record.

In review mode, precede the first brief with one plain sentence stating the exact review
window, the number of distinct sessions or tasks covered, the evidence sources used, and
material coverage gaps. This is evidence provenance, not the internal audit. In each
technical note, distinguish checks that can run now from future efficacy predictions and
identify whether support is an authoritative correction, a recurring pattern, or a
post-change regression. Paraphrase corrections; do not expose raw private transcript text.

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

Recommend the complete surviving set by default; the user can confirm it or exclude
candidate numbers as the rounds proceed. Treat Phase 3 as one approval stage that may span
any number of category and question rounds. For every real choice, map the design tree,
explore facts yourself, and ask the currently unblocked frontier. Include a recommended
answer for every question. When more than eight frontier decisions remain, ask the eight
highest-impact independent decisions, then recompute the frontier after the reply. Never
cap the total number of rounds or candidates, and never leave a branch silently assumed.
Ask no question whose viable answer is already determined by evidence, prior decisions,
constraints, or delegated defaults.

For user choices, use grilling's numbered `Q1` / `Q2` format and mark the recommended
answer with `➡️`; keep candidate proposals in this skill's existing decision-brief format.

Apply only when real choices are settled and the resulting candidate set is authorized.
Existing explicit approval of the same candidates and targets satisfies this gate; do not
request a second final confirmation. A general request to run a retrospective or a
scheduler trigger alone does not approve newly discovered edits. A candidate is
not ready without a `方案：` / `Solution:` paragraph and a verification that can run
now. Keep future-session predictions distinct from checks that can run now, even when
both appear in the same technical note.

After confirmation, read the target repository instructions and sources of truth, then
make the smallest approved changes. Prefer modifying or deleting existing surfaces over
creating new artifacts. Preserve supported behavior, safety controls, validation depth,
and approval gates. Create no persistent retrospective report, learning log, or periodic-
review checkpoint in the repository; project-documentation edits must update durable
sources of truth, and an approved eval may add only the artifact needed to run the
experiment. When no candidate survives in review mode, report the boundary and the
disposition of material signals without writing a repository artifact.
