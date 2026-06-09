---
name: article-workflow-section-review
description: Phase 1 of the article staged optimization workflow: section-by-section narrative review. Use when the user asks to execute Phase 1, section-by-section narrative review, section review, or generate `.article-workflow/01-section-reviews/` from `.article-workflow/brief.md` and `.article-workflow/00-cleaned-sources/`.
priority: P2
---

# Article Workflow Section Review

This is Phase 1 of the `article-workflow-*` skill series, corresponding to "Section-by-Section Narrative Review" in the article optimization workflow.

Goal: Review article materials section by section for narrative structure issues, providing actionable diagnostics for subsequent editing. The AI produces editorial diagnostics and default resolution suggestions — it does not revise body text, polish, or make key trade-off decisions on behalf of the author. The author makes judgment calls; trade-offs that would affect the direction of subsequent edits must have clearly marked author response slots, and can be collected in advance via dialog when necessary.

## Trigger Scenarios

Use this skill when the user asks to:

- Execute article optimization workflow Phase 1
- Perform section-by-section narrative review on `.article-workflow/00-cleaned-sources/`
- Generate `.article-workflow/01-section-reviews/`
- Check sections for logical jumps, information density, reader interest, or material selection
- Organize review results into actionable editing references for subsequent agents or the author

## Inputs and Outputs

Default inputs:

- `.article-workflow/brief.md`
- `.article-workflow/00-cleaned-sources/*.md`

Default outputs:

- `.article-workflow/01-section-reviews/<original-filename>.review.md`: per-section review
- `.article-workflow/01-section-reviews/index.md`: full-text issue index and global decision entry point

If the user provides an article directory, first look for `.article-workflow/` under that directory. If `brief.md` is missing, ask whether to proceed; without a brief, only basic narrative diagnostics can be performed — do not infer the article's main thread, target readers, or material selection criteria on your own.

## Core Principles

- Review, do not revise.
- Diagnose narrative structure; do not polish language.
- Every identified issue must have a default resolution path; do not only point out problems.
- Items requiring the author's decision must be explicitly marked and include a `📝 Author Response:` slot.
- When the author has not responded, subsequent phases may follow the "default resolution path"; author responses override default paths.
- For blocking decisions marked as "Requires Author Confirmation: Yes" that would affect section splitting, material retention/removal, factual boundaries, or the author's viewpoint, Phase 1 may provide a default path, but subsequent editing phases must not execute such blocking decisions without author confirmation.
- Review files must serve subsequent editing; do not write generic editorial opinions.
- Do not impose standardized writing frameworks to reshape the author's article; only point out how existing materials can better serve the brief.
- Preserve the author's personal experience, article tone, and necessary judgments; deletion or compression suggestions must not override author intent by default.
- After each round of output is complete, a sub-agent must be launched for goal-alignment review; the sub-agent only raises review opinions, and the main agent decides whether to adopt them.
- If a sub-agent is unavailable, a self-check covering the same review focus areas must be performed, and the final response must note the limitation of not completing a sub-agent review.

## Workflow

### Step 1: Read Source Materials

Read the following:

1. `.article-workflow/brief.md`
2. All body-text Markdown files under `.article-workflow/00-cleaned-sources/`
3. If `.article-workflow/01-section-reviews/` already exists, read existing reviews and update them rather than blindly overwriting

After reading, first determine:

- The article positioning, thesis, target readers, narrative path, and material selection confirmed in the brief
- Which cleaned sources are body-text materials and which are notes or intermediate files
- The narrative task each section undertakes
- Which issues can be resolved by default and which require author confirmation

Skip the following intermediate files in `00-cleaned-sources/` by default:

- `terminology-notes.md`
- `_cleaning-notes-*`
- Notes, indexes, or temporary files that are clearly not body-text sections

### Step 2: Produce Section-by-Section Diagnostics

Read body-text materials section by section, checking only for narrative-level issues:

- **Logical jumps**: Discontinuity between preceding and following sections, missing transitions, unclear narrative order
- **Information density overload**: Readers may not keep up, stacked technical details, material overload
- **Main thread drift**: Section undertakes too many tasks, tangential materials steal focus from the main thread
- **Reader interest risk**: Long quotations, long case studies, internal details that may be skipped
- **Material selection**: What should be kept, compressed, moved later, or deleted
- **Assertion strength**: Overly definitive conclusions, overly strong predictions, insufficient risk acknowledgment
- **Evidence calibration**: Need for citations, short excerpts, screenshots, footnotes, or downgrading to summaries

Do not rewrite body text at this stage, and do not write new paragraphs on behalf of the author.

### Step 3: Determine Whether to Ask the Author First

If ambiguities that would affect the direction of the entire Phase 1 output arise before starting the review, the author must be consulted first. Prioritize structured questioning or dialog mechanisms available in the current environment; if such tools are unavailable, use plain-text questions.

Common situations requiring advance questions:

- Missing `brief.md`, making it impossible to determine the main thread and target readers
- Multiple versions exist in `00-cleaned-sources/`, and it is unclear which set to review
- The user's requested review scope conflicts with workflow Phase 1, such as requesting inline edits or polishing
- The author explicitly states that certain materials must not be altered, but the brief does not record this

If no such ambiguities exist, do not force questions for form's sake; proceed directly and explain the basis in the final response.

### Step 4: Write Section-by-Section Reviews

For each body-text source file, write:

```text
.article-workflow/01-section-reviews/<original-filename>.review.md
```

Each review file uses the following structure:

```markdown
# `<original-filename>` Narrative Review

## Issues for Subsequent Editing

### Issue 1: <short title>

- Type: <emoji + text>
- Issue: <specific narrative problem identified>
- Default resolution path: <how subsequent phases should handle this if the author does not respond>
- Requires author confirmation: Yes/No.
  - 📝 Author Response:
```

Suggested issue types:

- `🔗 Transition`: Missing connections between paragraphs, sections, or viewpoints
- `🎯 Main Thread`: Material drifts away from the section's task or steals focus
- `📚 Information Density`: Stacked information, long quotations, excessive technical details
- `⚖️ Assertion Strength`: Overly definitive conclusions, overly strong predictions, unbalanced risk attitudes
- `✂️ Material Selection`: Keep, compress, delete, move later, split into separate section
- `🧩 Evidence`: Insufficient evidence, overly long evidence, inappropriate evidence presentation
- `🔁 Repetition`: Same judgment expressed repeatedly across different sections
- `✍️ Expression`: Not about polishing, but about expression calibration affecting narrative judgment
- `🧭 Structure`: Section structure, paragraph order, narrative framework issues

Writing requirements:

- Every issue must have a "Default resolution path."
- Only mark "Requires author confirmation: Yes" for items that would affect author intent, material selection, section splitting, factual boundaries, article tone, or subsequent phase inputs.
- Items requiring author confirmation must retain `📝 Author Response:`, making it easy for the author to fill in directly.
- Do not request author confirmation for directions already made clear in the brief.
- When the author has already filled in responses in existing reviews, the updated file must preserve those responses.

### Step 5: Write the Index

Write or update:

```text
.article-workflow/01-section-reviews/index.md
```

The index is a global decision entry point, not just an issue summary. Recommended structure:

```markdown
# Phase 1 Section-by-Section Narrative Review Index

## How the Author Should Respond

The author fills in responses directly after each "Suggested Author Confirmation" or "Requires Author Priority Confirmation" item at the `📝 Author Response:` location.

Subsequent editing phases execute according to the following priorities:

- Prioritize global decisions in this file.
- Then refer to the "Issues for Subsequent Editing" in each section's `.review.md`.
- When the author has not responded, the agent follows the "Default resolution path."
- When the author has responded, the author's response overrides the default resolution path.
- If a global response conflicts with a section-level response, the more specific and more recent response takes precedence.

## Most Important Issues for the Full Text

### 1. <global issue>

- Type: <emoji + text>
- Issue: <full-text-level narrative problem>
- Default resolution path: <how subsequent phases should handle this if the author does not respond>
- Requires author confirmation: Yes/No.
- 📝 Author Response:

## Key Handling Suggestions by Section

## Trade-offs Requiring Author Priority Confirmation
```

The index should only contain full-text-level issues and section-level summaries, not a repetition of every issue from every section.

Full-text-level issues in the index must also follow the per-issue contract: each must have "Type," "Issue," "Default resolution path," and "Requires author confirmation." Do not use loose suggestions in the index that raise issues without default paths.

### Step 6: Launch Sub-Agent for Review

After section-by-section reviews and the index are written, the main agent must launch a read-only sub-agent to review whether this round's output aligns with Phase 1 goals.

Sub-agent review focus areas:

- Whether only narrative review was done, with no body-text revision, polishing, or ghostwriting
- Whether the brief and cleaned sources were fully read
- Whether each section has a corresponding `.review.md`
- Whether each issue has "Type," "Issue," "Default resolution path," and "Requires author confirmation"
- Whether only items truly requiring author judgment are marked as confirmation items
- Whether confirmation items provide `📝 Author Response:`
- Whether existing author responses are preserved
- Whether `index.md` can serve as a global entry point for subsequent editing
- Whether there are problems of over-standardization, excessive deletion, or making viewpoint decisions on behalf of the author

After the main agent receives the review:

- It decides for itself which opinions are valid
- It only adopts suggestions consistent with Phase 1 goals
- It does not enter body-text editing or polishing based on review opinions
- If adopted, it updates review files or the index
- If not adopted, it briefly explains why in the final response

If the current environment cannot launch a sub-agent, the main agent must perform a self-check covering the review focus areas listed above and note this limitation in the final response.

### Step 7: Verification

After completion, check:

- Whether `.article-workflow/01-section-reviews/` exists
- Whether each cleaned source body-text section has a corresponding `.review.md`
- Whether `index.md` exists
- Whether each `.review.md` uses the per-issue structure
- Whether each issue includes `Type`, `Issue`, `Default resolution path`, and `Requires author confirmation`
- Whether items requiring author confirmation include `📝 Author Response:`
- Whether blocking confirmation items that would affect subsequent editing phases are clearly marked
- Whether existing author responses have not been lost
- Whether `00-cleaned-sources/*.md`, `brief.md`, or subsequent phase outputs have not been modified
- Whether sub-agent review has been completed and the main agent has decided on adoption
- If the environment provides Markdown lint or editor diagnostics, whether recently edited files were checked; if no relevant diagnostics are available, do not force code linter runs

## Output Style

- Use English unless the user specifies otherwise.
- Reviews are working documents; they should be clear, concise, and actionable.
- Minimize abstract editorial jargon; focus on "what to do by default."
- Keep issue titles short for easy scanning.
- Use emoji + English for type labels so the author can quickly identify them.
- Do not use tables; list format is more compatible with Markdown editors.
- The final response should only summarize output locations, major global issues, items requiring author priority confirmation, and sub-agent review handling results.

## Relationship to the Workflow

This skill is positioned after `article-workflow-clean-sources` and before fact verification and the material pool.

Recommended sequence:

- `article-workflow-brief`: Phase 0, Edit Brief
- `article-workflow-clean-sources`: Phase 0.5, Dictation Transcript Cleaning
- `article-workflow-section-review`: Phase 1, Section-by-Section Narrative Review

Subsequent planned phases:

- `article-workflow-evidence-pool`: Phase 2, Fact Verification and Material Pool
- Phase 3 Author Self-Read and Direct Editing: No separate skill; the author directly modifies `.article-workflow/00-cleaned-sources/`
- `article-workflow-ai-edit-pass`: Phase 3.5, Execute confirmed suggestions as edits
- `article-workflow-global-review`: Phase 4, Full-Text Coherence Review
- `article-workflow-main-draft`: Phase 4.5, Consolidate Main Draft
- `article-workflow-visual-plan`: Phase 4.6, Illustration and Visual Aid Planning
- `article-workflow-style-bible`: Phase 5.0, Style Guide
- `article-workflow-polish`: Phase 5, Round-by-Round Polishing
- `article-workflow-final-review`: Phase 6, Final Refinement and Reader Testing