# Dispatch task template

Fill the body of `bb-dispatch --task` from this. The template has one purpose: the child agent receives a contract, not a verbal briefing. Fill every section; write "None" when there is nothing.

```markdown
<One-sentence goal: what to do, to what extent, and what not to do>

## Read first
<Files and rules that must be read before starting, in reading order; include the project AGENTS.md, relevant skills, source evidence>

## Before starting
- git fetch first and confirm HEAD contains origin/main; if behind, first preserve others' uncommitted files (patch or local commit, no stash), then fast-forward with --ff-only; stop on failure.
- List uncommitted files in the workspace that do not belong to this task; never touch them or commit them along the way.

## Authorized scope and root-cause location
- Files or modules you may change: <list>
- If the root cause lies outside this scope (e.g. the permission check is in the store, not the page), <allowed to change / report first, then change>.
- Out of scope: <explicitly excluded items, e.g. no data model changes, no new pages, no new release>

## To do
<Itemized, down to the component or file; each item checkable>

## Decisions I introduced
- Where the task does not say but the implementation must pick one of two, pick the one that does not expand scope;
- List each such decision in a separate "Decisions I introduced" section of the final reply: decision, reason, impact, so the parent thread can confirm them one by one; never leave them only in code comments or scattered through the body.

## Delivery and verification
- Verification: <how to actually operate or run it locally; pages and identities needing screenshots; check commands>
- Before pushing: run the project's required fast local checks first (the entry point specified in the project AGENTS.md), push only after they pass; CI is only a backstop.
- Independent review split: <the parent thread dispatches independent review after acceptance, or the child thread dispatches it via autoreview before committing (pick one, do not stack both; at most 2 rounds inside the child thread)>
- Release / commit: <whether to release, commit message prefix, whether to push, add only files you changed>
- Where temporary scripts and artifacts go, and whether to delete them before delivery.

## Reply format
1. Version or commit
2. For each "To do" item, the change and verification result
3. Decisions I introduced (listed separately)
4. Conflicts with existing documents (list only; do not change the documents yourself)
5. Unfinished items
```

Usage rules:

- Task text holds only goal, scope, inputs, and acceptance; do not write provider, model, or reasoning level into it.
- "Read first" must include the authoritative sources for terms (glossary, option files, status lists); the implementation only references them and does not coin new names; if terms are not finalized, finalize them before dispatching.
- When the goal or boundary comes from the user's request, attach the user's original words; when restating rules or constraints, state the reason and scope, so the child thread can judge cases the rules do not cover.
- When multiple child threads change the same repository, state in "Before starting" which files the parent thread changes, and that child threads pull latest before changing files.
- Grading follows SKILL.md "Judgment and invocation"; the task brief still states goal, boundaries, authoritative entry points, and acceptance gaps; whether the parent thread investigates first is decided by cost.
- Item 3 of the reply format is the input for the parent thread's decision summary; send it back for completion if missing.
