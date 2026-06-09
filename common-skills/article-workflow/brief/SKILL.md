---
name: article-workflow-brief
description: Article phased optimization workflow Phase 0: Generate an editorial Brief from oral drafts, outlines, and reference materials. Use when the user asks to create/update an article brief, editorial Brief, article brief, or mentions `.article-workflow/brief.md`, oral draft, outline, or article workflow Phase 0. Reads `.article-workflow/sources/outline.md` and `.article-workflow/sources/oral-draft/`, asks author decisions through dialog, and writes the final `.article-workflow/brief.md`.
priority: P2
---

# Article Workflow Brief

This is the first step in the `article-workflow-*` skill series, corresponding to Phase 0 of the article optimization workflow.

Goal: Organize an editorial Brief from oral drafts and outlines, helping the author confirm the article's thesis, target audience, main narrative thread, personal judgments, and evidence standards. The AI is an editorial assistant — it does not decide the author's final viewpoints for them. Decisions that require the author's input must be collected through dialog, not written into the final brief as unresolved items.

## Trigger Scenarios

Use this skill when the user requests:

- Generate, organize, or update `.article-workflow/brief.md`
- Read `.article-workflow/sources/outline.md` and `.article-workflow/sources/oral-draft/`
- Generate an editorial brief based on oral drafts
- Execute Phase 0 of the article optimization workflow
- Collect user decisions through dialog and write them into the brief

## Input and Output

Default inputs:

- `.article-workflow/sources/outline.md`
- `.article-workflow/sources/oral-draft/`
- Optional: `.article-workflow/sources/references/`
- Optional: `.article-workflow/sources/proofs/`

Default output:

- `.article-workflow/brief.md`

If the user provides an article directory, look for `.article-workflow/` inside it first. If the user only provides an oral draft directory, ask where the brief should be saved.

## Core Principles

- Edit, don't ghostwrite.
- Do not rewrite the article body.
- Do not decide the author's final viewpoints for them.
- First identify questions that require the author's decision, collect the author's choices through dialog, then write the confirmed results into the brief.
- When encountering ambiguities that affect the thesis, audience, structural trade-offs, author judgments, or evidence standards, proactively use dialog to ask the user for confirmation — do not silently guess.
- The author makes judgments; the AI diagnoses, organizes, and executes.
- After each round's deliverable is complete, a sub-agent must be launched for alignment review; the sub-agent only offers review feedback, and the main agent decides whether to adopt it.
- Preserve the author's personal judgments, first-person experiences, viewpoint formation process, and distinctive voice.
- Technical details, evidence, and materials serve the article's main narrative only — do not turn the brief into a material dump.

## Workflow

### Step 1: Read Source Materials

Read the following:

1. `outline.md`
2. All Markdown files under `oral-draft/`
3. If `references/README.md` exists, read it to understand the reference material structure
4. If a brief already exists, read the current brief and update it later rather than blindly overwriting

After reading, assess:

- What problem the article appears to be discussing
- Which paragraphs seem like the main narrative and which are just materials
- Which judgments clearly come from the author personally
- Which pieces of evidence need source attribution preserved

### Step 2: Form Internal Diagnosis

Form an internal diagnosis based on the source materials, preparing questions for the author. Do not write "questions requiring further author decisions" into `.article-workflow/brief.md`.

The internal diagnosis should cover:

- Possible core thesis
- Possible target audience
- Main narrative paragraphs vs. material paragraphs
- Author personal judgments that should be preserved
- Trade-offs that must be decided by the author
- Any ambiguities that would affect the final brief's direction

At this stage, do not change titles, rewrite openings, or rework paragraphs. Also, do not write out a brief file with pending questions, to prevent subsequent agents from treating unconfirmed issues as confirmed directions.

### Step 3: Collect Author Decisions Through Dialog

Once the internal diagnosis is complete, use structured dialog to collect author decisions. Prefer `AskQuestion`; if that tool is unavailable, ask questions in plain text instead.

If ambiguities are found, do not wait for the user to point them out — compress these questions into a small number of clear options, and ask the user to confirm before writing the final brief.

Suggested questions to collect in one pass:

1. **Article Direction**
   - Project Alpha / In-depth case analysis
   - Use a case to discuss broader trends or methodologies
   - Personal observation / Experience retrospective
   - Other

2. **Opening Hook**
   - Event / Bill / Conflict
   - Core question
   - Personal experience
   - Technical mechanism

3. **Target Audience**
   - General tech readers
   - Open-source maintainers / Tech leads
   - Heavy agent users
   - Trend observers / Non-technical readers

4. **Technical Detail Ratio**
   - Lightweight explanations, understandable to general readers
   - Moderate expansion, preserving key mechanisms
   - Deep technical analysis

5. **Narrative Stance**
   - Observer analysis
   - Firsthand narrative
   - Commentary / Opinion piece
   - Tutorial / Methodology

6. **Risks and Limitations**
   - Explicitly acknowledge
   - Briefly mention
   - Do not expand for now

7. **Ending Focus**
   - Imperfect but workable
   - May become the norm in the future
   - Takeaways for ordinary teams
   - Return to personal cognitive shifts

8. **Evidence Presentation**
   - Links / Footnotes
   - Screenshots / Illustrations
   - Short in-text excerpts
   - Summary only

Options can be adjusted based on article content, but keep questions focused. Do not ask too many open-ended questions at once.

### Step 4: Write the Final Brief Based on Decisions

After receiving author decisions, write or update `.article-workflow/brief.md`. The final brief is a reference for subsequent writing — it is not a questionnaire.

Recommended final structure:

```markdown
# Editorial Brief

## One-sentence Positioning

## Confirmed Direction

## Core Thesis

## Target Audience

## Suggested Narrative Path

## Section Trade-offs

## Author Judgments to Preserve

## Evidence Standards

## Reminders for Subsequent Writing
```

The final brief should:

- Lead with confirmed directions, so subsequent agents can read them quickly.
- List the narrative path and section trade-offs in the middle, guiding subsequent cleanup, review, and integration.
- Preserve evidence standards and author judgments at the end, preventing drift in later stages.
- Not include a "questions requiring further author decisions" section.
- If critical unresolved items remain, proactively continue asking through dialog; unless the user explicitly requests it, do not write unresolved questions into the brief.

### Step 5: Launch Sub-agent for Review

After the final brief is written, the main agent must launch a read-only sub-agent to review whether this round's deliverable aligns with the objectives.

Sub-agent review focus areas:

- Whether the brief follows "edit, don't ghostwrite"
- Whether it does not decide unconfirmed viewpoints on behalf of the author
- Whether it does not write pending questions into the final brief
- Whether it clearly preserves directions confirmed by the author through dialog
- Whether it is easy for subsequent stages to reference directly
- Whether any main narrative thread, material, author judgment, or evidence standard has been missed

After the main agent receives the review:

- Judge for itself which feedback is valid
- Only adopt suggestions consistent with this stage's objectives
- Do not expand the task scope or rewrite the article body based on review feedback
- If adopting, update `.article-workflow/brief.md`
- If not adopting, briefly explain the reason in the final reply

### Step 6: Verification

After completion, check:

- Whether `.article-workflow/brief.md` exists
- Whether the article body has still not been rewritten
- Whether only confirmed directions, trade-offs, and evidence standards have been written
- Whether user decisions collected through dialog are preserved
- Whether all ambiguities affecting the brief's direction have been proactively asked about
- Whether no "questions requiring further author decisions" section remains
- Whether sub-agent review has been completed and its feedback judged for adoption by the main agent
- Whether lints have been checked on recently edited files

## Output Style

- Use English unless the user specifies otherwise.
- The brief should be clear, restrained, and easy for subsequent reference.
- Minimize vague editorial jargon; write actionable judgments instead.
- Do not write a lengthy commentary — the brief is a working document, not the article itself.

## Naming Convention for Subsequent Skills

This group of article optimization skills uses the unified `article-workflow-` prefix.

Recommended subsequent naming:

- `article-workflow-brief`: Phase 0, Editorial Brief
- `article-workflow-clean-sources`: Phase 0.5, Oral draft cleanup
- `article-workflow-section-review`: Phase 1, Section-by-section narrative review
- `article-workflow-evidence-pool`: Phase 2, Fact-checking and material pool
- Phase 3 Author read-through and direct editing: no separate skill needed; the author edits `.article-workflow/00-cleaned-sources/` directly
- `article-workflow-ai-edit-pass`: Phase 3.5, Apply confirmed edits on the author's behalf
- `article-workflow-global-review`: Phase 4, Full-text coherence review
- `article-workflow-main-draft`: Phase 4.5, Consolidate main draft
- `article-workflow-visual-plan`: Phase 4.6, Illustration and visual aid planning
- `article-workflow-style-bible`: Phase 5.0, Style guide
- `article-workflow-polish`: Phase 5, Round-by-round polishing
- `article-workflow-final-review`: Phase 6, Final refinement and reader testing