---
name: distill
description: Extract verified lessons from the current conversation and integrate them into project documentation or reusable skills. Use for debugging discoveries, workflow improvements, convention updates, architecture decisions, and end-to-end retrospectives of any skills executed during the session, especially to fix observed failures, retries, or avoidable detours without weakening capabilities or safeguards.
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

### Review every executed skill

If the conversation executed one or more skills, review each skill's complete execution path:

1. Identify the exact skill source and the user request that triggered it.
2. Reconstruct the actual path from instruction loading and planning through tool calls, retries, corrections, validation, and final output.
3. Compare the actual path with the shortest reliable path the skill should have enabled.
4. Record concrete evidence for errors, failed attempts, ambiguous instructions, missing prerequisites, unnecessary branching, or repeated work.
5. Classify each issue before proposing a skill change:
   - **Skill defect:** the instructions were missing, ambiguous, incorrect, poorly ordered, or encouraged a detour.
   - **Execution defect:** the agent failed to follow adequate instructions.
   - **Environment or tool defect:** the failure came from shell behavior, permissions, unavailable tooling, external state, or another local condition.
   - **Request ambiguity:** the workflow required a user decision the skill could not safely infer.
6. Propose a skill change only when it addresses a transferable workflow problem. Do not encode an agent mistake or one-off environment quirk as a general rule.

Prioritize improvements in this order:

1. Prevent observed errors and unsafe outcomes.
2. Remove verified dead ends, retries, and avoidable detours.
3. Make the reliable path explicit and easier to follow.
4. Reduce steps only when the shorter path preserves all capabilities, validation, safety checks, and required user approval gates.

Treat step reduction as optional. Require a clear before-and-after path and evidence that no behavior is lost. Prefer no simplification when equivalence is uncertain.

Do not preserve:

- One-off business logic that matters only to the current request
- Speculative advice that was not verified
- Code snippets that apply only to one narrow case
- Hypothetical skill optimizations unsupported by the execution trace
- Cosmetic step reduction that weakens checks, flexibility, or clarity

Present a lesson list. For each item, include:

1. A one-sentence summary
2. The proposed destination document, or "new document"
3. The proposed change type: add section, append item, update content, or create document
4. For skill improvements, the execution evidence, root cause classification, exact skill path, and protected capabilities or safeguards

Wait for the user to confirm or revise the list before continuing.

---

## Phase 2: Audit the documentation system

1. Read `AGENTS.md` and identify the project's documentation index.
2. Read the documents relevant to each approved lesson.
3. For an approved skill improvement, resolve the exact source behind any user-level symlink, read the complete `SKILL.md`, inspect only the referenced resources needed to understand the failure, and follow the skill repository's authoring rules.
4. Search for existing coverage to avoid duplication.
5. Choose the smallest appropriate change:
   - **Append** to an existing section whenever possible.
   - **Update** inaccurate or outdated guidance.
   - **Merge** overlapping documentation.
   - **Create** a document only when no existing document fits.
   - **Refine a skill** only enough to fix the evidenced problem or reinforce the reliable path.

Preserve verified facts only. Prefer concise additions to existing documents over new documents.

Present a change plan containing:

- Target file
- Change type
- Summary of the intended content
- For skill changes, the observed failure or detour, intended reliable path, preserved invariants, and validation method

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

When improving a skill:

1. Fix observed correctness and routing problems before considering simplification.
2. Strengthen the best reliable path with explicit ordering, prerequisites, decision rules, or failure handling.
3. Keep alternate paths only when they serve real environments or use cases.
4. Remove or combine steps only when the change preserves outputs, supported scenarios, validation depth, safety constraints, and approval gates.
5. Avoid broad rewrites when a targeted instruction change solves the problem.
6. Validate the skill with its repository's validator and any relevant bundled scripts or focused checks.

---

## Phase 4: Check consistency

Verify:

1. References to renamed or deleted files are updated.
2. Internal links resolve.
3. New material does not duplicate existing guidance.
4. Filenames and titles still match their content.
5. `AGENTS.md` or any equivalent documentation index reflects additions, removals, and merges.
6. Each improved skill addresses the evidenced failure or detour without encoding unrelated session details.
7. Any shortened workflow preserves the stated capabilities, safeguards, validation, and approval gates.

Report the number of lessons preserved, the files changed, the skills reviewed, the execution problems fixed, and any carefully justified step reductions. Explicitly report when a reviewed skill did not warrant modification.

## Guardrails

- Never skip the approval gates after Phases 1 and 2.
- Never preserve speculation as fact.
- Prefer three precise lines to thirty vague lines.
- Keep the project documentation index synchronized.
- Preserve file history for renames.
- Never treat every execution failure as a skill defect.
- Never remove capability, validation, safety checks, or approval gates merely to reduce step count.
- Never optimize for a single session at the expense of supported workflows.
- Prefer a small evidenced improvement to a comprehensive rewrite.
