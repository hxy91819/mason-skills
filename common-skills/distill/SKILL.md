---
name: distill
description: Extract verified lessons from the current conversation and integrate them into a project's documentation. Use for debugging discoveries, new patterns, workflow improvements, convention updates, and architecture decisions that should be preserved for future work.
---

# Distill Conversation Lessons

Turn durable lessons from the current conversation into concise, structured project documentation.

Follow all four phases. Get the user's approval before moving from one phase to the next.

---

## Phase 1: Extract lessons

Review the entire conversation and identify lessons worth preserving.

Preserve:

- Debugging discoveries, including symptoms, root causes, and verified fixes
- Environment or toolchain behavior that is likely to recur
- Workflow improvements proven during the conversation
- Missing or incomplete conventions
- Architecture decisions and their rationale

Do not preserve:

- One-off business logic that matters only to the current request
- Speculative advice that was not verified
- Code snippets that apply only to one narrow case

Present a lesson list. For each item, include:

1. A one-sentence summary
2. The proposed destination document, or "new document"
3. The proposed change type: add section, append item, update content, or create document

Wait for the user to confirm or revise the list before continuing.

---

## Phase 2: Audit the documentation system

1. Read `AGENTS.md` and identify the project's documentation index.
2. Read the documents relevant to each approved lesson.
3. Search for existing coverage to avoid duplication.
4. Choose the smallest appropriate change:
   - **Append** to an existing section whenever possible.
   - **Update** inaccurate or outdated guidance.
   - **Merge** overlapping documentation.
   - **Create** a document only when no existing document fits.

Preserve verified facts only. Prefer concise additions to new documents.

Present a change plan containing:

- Target file
- Change type
- Summary of the intended content

Wait for approval before editing files.

---

## Phase 3: Apply documentation changes

Apply only the approved plan.

When editing:

1. Place additions in the most relevant existing section.
2. Update a document's change-history table when it has one:
   ```markdown
   | YYYY-MM-DD | Change summary | Reason |
   ```
3. Use `git mv` for renames and `git rm` for deletions.
4. Give new documents a clear title, any required enforcement statement, and a change-history table when the project uses one.
5. Keep prose concise and provide complete, copyable commands.
6. Record symptoms, causes, and solutions for debugging lessons.
7. Prefer structured lists and tables over long paragraphs.

---

## Phase 4: Check consistency

Verify:

1. References to renamed or deleted files are updated.
2. Internal links resolve.
3. New material does not duplicate existing guidance.
4. Filenames and titles still match their content.
5. `AGENTS.md` or any equivalent documentation index reflects additions, removals, and merges.

Report the number of lessons preserved, the files changed, and any points the user should review.

## Guardrails

- Never skip the approval gates after Phases 1 and 2.
- Never preserve speculation as fact.
- Prefer three precise lines to thirty vague lines.
- Keep the project documentation index synchronized.
- Preserve file history for renames.
