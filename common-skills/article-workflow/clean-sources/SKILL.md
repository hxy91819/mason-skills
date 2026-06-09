---
name: article-workflow-clean-sources
description: Phase 0.5 of the article optimization workflow: clean oral draft transcription errors. Use when the user asks to clean oral drafts, organize oral drafts, execute Phase 0.5, or generate `.article-workflow/00-cleaned-sources/` from `.article-workflow/sources/oral-draft/` using `.article-workflow/brief.md`.
priority: P2
---

# Article Workflow Clean Sources

This is Phase 0.5 of the `article-workflow-*` skill series, corresponding to "oral draft cleaning" in the article optimization workflow overview.

Goal: first correct obvious errors introduced by oral transcription, preventing downstream structural reviews from being disrupted by transcription mistakes. AI only performs cleaning — no polishing, rewriting, structural changes, or opinion processing. The author makes the final call on terminology, style, and uncertain items.

## Trigger Scenarios

Use this skill when the user requests:

- Referencing Phase 0.5 to clean oral drafts
- Organizing, cleaning, or correcting `.article-workflow/sources/oral-draft/`
- Generating `.article-workflow/00-cleaned-sources/`
- Standardizing proper nouns, capitalization, and obvious transcription errors in oral drafts
- Recording terminology questions or uncertain items from oral draft cleaning

## Input and Output

Default input:

- `.article-workflow/sources/oral-draft/`
- `.article-workflow/brief.md`

Default output:

- `.article-workflow/00-cleaned-sources/*.md`: cleaned oral draft text, saved under the original filenames
- `.article-workflow/00-cleaned-sources/terminology-notes.md`: proper noun corrections, uncertain items, and cleaning boundary records

If the user provides an article directory, first look for `.article-workflow/` within that directory. If `brief.md` is missing, ask whether to proceed; without a brief, only basic transcription cleaning can be done — do not infer the article's terminology system on your own.

## Core Principles

- Clean, not polish.
- Preserve the author's speaking style, sentence patterns, tone, and order of ideas.
- Only correct obvious typos, speech recognition errors, proper noun capitalization and spelling, clearly redundant filler words, and basic spacing between Chinese and English text.
- Do not restructure sentences, replace the author's word choices, optimize expressions, delete ideas, or add content.
- Terminology notes are intermediate artifacts, always using `terminology-notes.md`, to avoid being mistaken for article body text in later phases.
- When uncertain about proper nouns, facts, colloquial style boundaries, or cleaning strategies that affect whole-document consistency, do not guess — proactively ask the author to confirm via dialog before writing into the cleaned draft.
- Terminology notes record confirmed treatments and a small number of low-risk doubtful points; they do not replace proactive confirmation.
- Blockquotes, code blocks, and original excerpts are kept as-is by default, unless the user explicitly requests synchronized corrections.
- By default, standardize `issue/issues` in body text to `Issue/Issues`, but do not change blockquotes, code blocks, or original excerpts by default.
- After each round of output, a sub-agent must be launched for goal-alignment review; the sub-agent only provides review opinions, and the main agent decides whether to adopt them.

## Workflow

### Step 1: Read Source Materials

Read the following:

1. `.article-workflow/brief.md`
2. All Markdown files under `.article-workflow/sources/oral-draft/`
3. If `.article-workflow/00-cleaned-sources/terminology-notes.md` already exists, read and update it rather than blindly overwriting; if only the legacy file `_cleaning-notes-terminology.md` exists, first read its content and migrate it to `terminology-notes.md`
4. If `.article-workflow/00-cleaned-sources/` already exists, first confirm whether to update or regenerate

After reading, assess:

- Proper nouns, capitalization, article terminology, and no-change boundaries already confirmed in the brief
- Obvious speech recognition errors and homophone misrecognitions in the oral drafts
- Which words are the author's personal expressions and should not be treated as errors
- Which suspected errors need author confirmation
- Which ambiguities must be asked of the author first and not just noted

### Step 2: Form a Cleaning Strategy

Before writing files, form an internal cleaning strategy.

The cleaning strategy should cover:

- Standardized spelling for project names, product names, person names, model names, and tool names
- Capitalization of common English abbreviations, e.g., `PR`, `Issue`, `GitHub`, `AI`
- Whether to preserve English blockquote text as-is
- Deletion boundaries for verbal filler words
- Uncertain items requiring proactive author consultation
- Low-risk doubtful points that can be recorded in terminology notes without affecting current cleaning

If any judgment in the cleaning strategy could affect overall document style, factual accuracy, the author's original intent, colloquial style boundaries, or terminology consistency, ask the author to confirm via dialog first. For uncertain proper nouns, default to proactive inquiry; only points that do not affect body text processing should be recorded as low-risk notes.

### Step 3: Collect Author Decisions via Dialog

When key uncertain items exist, collect author decisions through structured questions. Prefer using a dialog tool; if unavailable, use regular text questions.

Do not wait for the author to discover issues after the fact. Before writing into the cleaned draft, proactively compile all ambiguities that affect cleaning results and compress them into a few multiple-choice questions.

Suggested question types:

1. **Terminology capitalization**
   - Use common English project conventions, e.g., `Issue`, `GitHub`
   - Preserve original oral draft capitalization
   - Only standardize terms explicitly mentioned in the brief
   - Other / needs supplement

2. **Blockquote handling**
   - Preserve blockquote text exactly as-is
   - Only correct obvious formatting errors in blockquotes
   - Standardize terminology in blockquotes along with body text
   - Other / needs supplement

3. **Colloquial imperfection retention**
   - Remove clearly redundant filler words
   - Preserve all colloquial traces as much as possible
   - Lightly correct colloquial errors that affect comprehension
   - Other / needs supplement

4. **Uncertain proper noun handling**
   - Ask the author about key uncertain items before modifying body text
   - Only record notes for low-risk doubtful points that don't affect current body text processing
   - Pause cleaning of related files until the author confirms
   - Other / needs supplement

Do not ask too many open-ended questions at once. Terms already specified in the brief do not need to be re-asked.

### Step 4: Write Cleaned Drafts and Terminology Notes

Write or update:

```text
.article-workflow/00-cleaned-sources/<original-filename>.md
.article-workflow/00-cleaned-sources/terminology-notes.md
```

Cleaned draft requirements:

- Filenames match the original oral drafts
- Paragraph order matches the original
- Headings and separators are preserved as much as possible
- Only make changes within the cleaning scope
- Original text in blockquotes, code blocks, and data tables is not changed by default

Recommended structure for terminology notes:

```markdown
# Oral Draft Cleaning Terminology Record

## Corrections unified per brief and context

## Low-risk residual doubtful points, not affecting current cleaning

## Cleaning boundary notes
```

Terminology notes should record "why this change was made" but should not become article content analysis. Key uncertain items must not just be left in notes for the author to discover — ask proactively; notes only retain low-risk residual doubtful points that do not affect current cleaning results. The notes file is always `terminology-notes.md`; downstream phases reading body text must skip it.

### Step 5: Check for Residual Errors

After writing, do a round of residual checks:

- Search whether known incorrect spellings still appear in the cleaned draft body text
- Search whether terminology capitalization is consistent
- Confirm that residual text in blockquotes is intentionally preserved
- Confirm that body text files in `00-cleaned-sources/` are saved under original filenames
- Confirm that notes files in `00-cleaned-sources/` use the `_cleaning-notes-` prefix

If obvious errors are still found in the body text, correct them directly. Errors appearing only in the "corrections record" section of `terminology-notes.md` do not count as residual errors.

### Step 6: Launch Sub-Agent Review

After writing the cleaned drafts and terminology notes, the main agent must launch a read-only sub-agent to review whether the current round's output aligns with the goals.

Sub-agent review focus:

- Whether the cleaned draft only performs transcription cleaning, with no polishing, sentence restructuring, rewriting, or idea deletion/modification
- Whether proper nouns and capitalization are consistent with the brief and terminology notes
- Whether any obvious speech recognition errors were missed
- Whether the author's personal expressions or colloquial style were mistakenly changed
- Whether blockquotes, code blocks, or original excerpts were unnecessarily modified
- Whether terminology notes use `terminology-notes.md`, avoiding confusion with cleaned body text
- Whether `00-cleaned-sources/` contains only cleaned body text files besides `terminology-notes.md`

After the main agent receives the review:

- Independently judge which opinions are valid
- Only adopt suggestions consistent with Phase 0.5 goals
- Do not proceed into polishing, structural review, or fact-checking based on review opinions
- If adopting, update the cleaned draft or terminology notes
- If not adopting, briefly explain why in the final response

### Step 7: Verification

After completion, check:

- Whether `.article-workflow/00-cleaned-sources/` exists
- Whether each original oral draft has a correspondingly named cleaned draft
- Whether `.article-workflow/00-cleaned-sources/terminology-notes.md` exists
- Whether `00-cleaned-sources/` contains only correspondingly named body text files and the `terminology-notes.md` intermediate artifact
- Whether no sentence restructuring, polishing, rewriting, or idea addition has occurred
- Whether uncertain proper nouns and facts have been recorded
- Whether ambiguities affecting cleaning results have been proactively asked of the author
- Whether a sub-agent review has been completed and judged for adoption by the main agent
- Whether lints have been checked on recently edited files

## Output Style

- Use English unless the user specifies otherwise.
- Cleaned drafts should still read like the author's own oral expressions.
- Terminology notes should be concise, focusing on change rationales and items pending confirmation.
- The final response should only summarize the cleaning scope, output locations, terminology requiring author confirmation, and review resolution results.

## Relationship to the Workflow

This skill is positioned after `article-workflow-brief` and before per-section narrative review.

Recommended order:

- `article-workflow-brief`: Phase 0, edit Brief
- `article-workflow-clean-sources`: Phase 0.5, oral draft cleaning

Subsequent planned phases:

- `article-workflow-section-review`: Phase 1, per-section narrative review
- `article-workflow-evidence-pool`: Phase 2, fact-checking and material pool
- Phase 3 author self-read and direct editing: no separate skill; the author directly modifies `.article-workflow/00-cleaned-sources/`
- `article-workflow-ai-edit-pass`: Phase 3.5, apply confirmed suggestions as edits
- `article-workflow-global-review`: Phase 4, full-document coherence review
- `article-workflow-main-draft`: Phase 4.5, integrate main draft
- `article-workflow-visual-plan`: Phase 4.6, illustration and visual aid planning
- `article-workflow-style-bible`: Phase 5.0, style guide
- `article-workflow-polish`: Phase 5, multi-round polishing
- `article-workflow-final-review`: Phase 6, final refinement and reader testing