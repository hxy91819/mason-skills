---
name: article-workflow-global-review
description: Phase 4 of the staged article optimization workflow: global coherence review. Use when the user asks to execute Phase 4, global review, whole-article coherence review, or generate `.article-workflow/04-global-review/` from `brief.md`, `03.5-ai-edit-pass/revised-sources/` (or `00-cleaned-sources/`), `02-evidence-pool/`.
priority: P2
---

# Article Workflow Global Review

This is Phase 4 of the `article-workflow-*` skill series, corresponding to "global coherence review" in the article optimization workflow.

Goal: read the scattered chapters **as one continuous article**, find breaks, repetitions, and misplacements, and give a clear handling direction for each repetition. This is not about mechanically deleting all repetitions, but about judging which repetitions make the article spin in place and which are necessary progression or echo. AI does the diagnosis and organization; the author makes the judgment. **This phase does not directly edit the draft** — it only points out problem locations and adjustment directions; the actual changes are left to Phase 4.5.

## Trigger Scenarios

Use this skill when the user asks to:

- Execute article optimization workflow Phase 4
- Global coherence review / whole-article coherence review / global review
- Check all chapters as one continuous article for breaks, cross-chapter repetitions, content misplacements
- Generate `.article-workflow/04-global-review/`

## Input and Output

Default inputs:

- `.article-workflow/brief.md` (Phase 0 editing brief, the reference baseline for the main thread and must-keep judgments)
- Main text chapters, one of two:
  - `.article-workflow/03.5-ai-edit-pass/revised-sources/*.md` — **if Phase 3.5 has passed author review, read this first**
  - `.article-workflow/00-cleaned-sources/*.md` — if Phase 3.5 was not executed
- `.article-workflow/02-evidence-pool/` (`evidence-pool.md`, `open-questions.md`, etc., for cross-checking evidence calibrations and confirmed facts)
- `.article-workflow/03-author-pass-notes.md` (if it exists)
- May reference `.article-workflow/03.5-ai-edit-pass/change-log.md`, `author-review-checklist.md` to confirm Phase 3.5 is closed and calibrations are unified

Default output (**always create a folder, even if there is only one file**):

- `.article-workflow/04-global-review/global-review.md`: whole-article coherence review report with inline author decision points

If the user provides an article directory, first look for `.article-workflow/` under that directory.

## Core Principles

- **Read the full text as one continuous article.** Read through in current chapter order, focusing on "after the reader is led into a train of thought/mood in the previous section, does the next section break or repeat?", rather than reviewing each chapter in isolation.
- **Do not directly edit the draft.** Only point out problem locations and adjustment directions; any "how it should be changed" is a suggestion for the author and Phase 4.5, not a direct edit to the text.
- **Must produce a cross-chapter repetition list.** This is the hard deliverable of this phase; list item by item "where the same point/example/judgment/background/sentence pattern reappears across chapters."
- **Give each repetition a clear handling verb:** keep as echo / merge / delete / move later / rewrite as progression. Don't just say "this is repeated" without giving a direction.
- **Distinguish bad repetitions from necessary echoes.** Bad repetitions make the article spin in place (must be handled); necessary echoes are progressions or callbacks of the theme line, keywords (must be **kept**, not deleted as repetition). Must-keep echoes typically come from the core expressions and key sentences specified in the brief.
- **Use severity levels:** 🔴 makes the article spin in place, recommended to handle; 🟡 recommended to handle; 🟢 can be kept as echo.
- **Decision points are inline, no centralized area.** Under each question requiring author sign-off (break B, cross-chapter repetition R, functional repetition F, attribution A), leave a `📝 Author decision:`, placed right next to that question. "Expression repetitions" and "necessary echoes" do not get separate numbered sections, but exist as entries in the R list (one R entry may be an expression repetition or necessary echo). Where an attribution A overlaps with an R entry, note "already merged into RN" and don't require a separate decision. **Do not** aggregate all questions into a "centralized decision area" — that makes the author feel they're being asked the same thing twice. (This is an **intentional exception** to the series default of "not writing pending decisions into deliverables": Phase 4's deliverable is itself the author decision carrier, which the author fills in asynchronously for Phase 4.5 to read.)
- **Don't force the author to sign off on items that don't need changes.** 🟢 necessary echo decision points are marked "(keep by default, write only if you disagree)" to reduce author burden.
- **Verify the main thread hasn't drifted.** Check item by item against the brief's "suggested narrative path", confirming that chapter order, narrative tone, and must-keep judgments still hold; problems should focus on "which section covers the same thing, and to what depth", not the main thread itself.
- **Incidentally re-check confirmed calibrations.** Numbers, links, named references, and citation sources unified in Phase 3.5 / open-questions should be cross-checked for cross-chapter consistency from a coherence perspective; if found, flag them to remind Phase 4.5 to re-check, but don't fix them in this phase.
- **After writing the deliverable, must launch a sub-agent for goal alignment review; the sub-agent only provides review opinions, and the main agent decides whether to adopt them. If a sub-agent is unavailable, self-check against the same focus areas and note the limitation in the final response.**

## Workflow

### Step 1: Confirm input sources and read through the full text

- First determine which text set to read: check `03.5-ai-edit-pass/author-review-checklist.md` / `change-log.md` to confirm whether Phase 3.5 has passed author review. If passed, read `revised-sources/*.md`; otherwise, read `00-cleaned-sources/*.md`.
- Read `brief.md` and note: one-sentence positioning, central claim, suggested narrative paths 1–N, must-keep author judgments, "imperfections" that must be acknowledged.
- Read `02-evidence-pool/` (including calibrations confirmed by the author in `open-questions.md`).
- Check if `03-author-pass-notes.md` exists.
- **Read through the full text continuously once** in current chapter order, linking each chapter's narrative task, emotional arc, key examples, and judgments in your mind.

### Step 2: Determine whether to ask the author first

Phase 4 author judgments are **collected inline in the deliverable by default**, so there is generally no need to open a dialog. Only ask proactively (prefer structured questions / dialog) for **ambiguities that would block the deliverable**:

- Main text is missing or incomplete, cannot be read as a complete article.
- Cannot determine whether to read `revised-sources/` or `00-cleaned-sources/` (Phase 3.5 status unclear).
- User's request conflicts with Phase 4 (e.g., asking to directly edit the draft or rearrange the full text, rather than producing a review).

If there are no blocking points, just proceed and leave all author judgments inline as `📝 Author decision:` in the deliverable — don't force questions for the sake of formality.

### Step 3: Perform coherence diagnosis across six dimensions

Organize the full-text reading into six categories of issues, each tagged with location and severity:

- **Breaks (B)**: The previous section led the reader into a certain mood/line of thought, and the next section suddenly jumps to a completely different context, or a hook thrown earlier is never picked up.
- **Cross-chapter repetitions — content (R)**: The same point, example, judgment, or background information appears repeatedly across different chapters.
- **Expression repetitions**: Different chapters use similar sentence patterns or similar abstract judgments, making the reader feel the article is spinning in place.
- **Functional repetitions (F)**: Two chapters serve the same narrative function (e.g., both are "wrapping up with a call to the future" or "telling the same twist"), and need to be merged, compressed, or have their roles redistributed.
- **Necessary echoes**: Some keywords/judgments **should** be repeated, but must form a progression or callback — call these out and explicitly mark "keep" to prevent later phases from mistakenly deleting them.
- **Attributions (A)**: Whether a piece of content would fit better in another section.

### Step 4: Write `04-global-review/global-review.md`

Create the `04-global-review/` folder (even if there's only this one file) and write the review report. Suggested structure:

- **Top note**: reading order, how the author should use this (each question has a `📝 Author decision:`, which are the most critical ones).
- **One-sentence conclusion**: what is the single most important global issue across the full text.
- **Main thread vs. Brief alignment check**: use a table to check each brief narrative path item by item, marking "aligned / ⚠️ has issues".
- **Break list (B1…)**: for each, give location, impact, adjustment direction, with `📝 Author decision:`.
- **Cross-chapter repetition list (R1…)** [key deliverable of this phase]: for each, give "appearance locations (quote original text / mark chapters) → assessment → handling suggestion (keep as echo / merge / delete / move later / rewrite as progression)", tag 🔴🟡🟢, with `📝 Author decision:`. 🟢 necessary echoes marked "(keep by default, write only if you disagree)".
- **Functional repetitions (F1…)**: where two sections serve the same function, give role redistribution suggestions, with `📝 Author decision:`.
- **Necessary echoes summary**: list the recommended-to-keep echoes in one place as a reminder not to mistakenly delete them. This is a **read-only recap with no decision points** (these echoes' decision points are already on their corresponding R entries, marked "keep by default, write only if you disagree") — it is not a "centralized decision area."
- **Attribution suggestions (A1…)**: content misplacements or items better placed elsewhere; where overlapping with R, note "already merged into RN" to avoid asking for duplicate decisions.
- **Handoff summary**: for Phase 4.5, priority processing order, must-keep echoes, calibrations needing re-check; at the end, leave a `📝 Author decision:` for "next step (return to Phase 3 or proceed to Phase 4.5)".

Writing requirements: do not edit the main text; every repetition must have a handling verb; decision points are placed next to each question, no separate centralized area.

### Step 5: Launch sub-agent for goal alignment review

After writing the deliverable, the main agent must launch a read-only sub-agent review. The sub-agent only provides review opinions, focusing on:

- Whether the full text was truly read as a continuous article, and whether break/repetition judgments hold (any obvious cross-chapter repetitions missed, or necessary echoes mistakenly flagged as bad repetitions).
- Whether the cross-chapter repetition list is complete, and whether each entry has a clear handling verb.
- Whether severity levels are reasonable (whether 🔴 items truly make the article spin in place).
- Whether the brief's main thread and must-keep judgments were checked against, without suggesting deletion of core expressions the brief requires keeping.
- Whether decision points are inline under each question, with no separate centralized decision area.
- Whether the "don't edit the draft" boundary was maintained, only giving directions.

Main agent after receiving review: judge for itself which suggestions are valid; only adopt suggestions consistent with Phase 4 goals; revise the report accordingly; briefly explain reasons for not adopting others. If sub-agent is unavailable, self-check against the above focus areas and note the limitation.

### Step 6: Process author review, iterate as needed

The author will fill in their choices directly after each `📝 Author decision:` in `global-review.md`, and may also annotate specific items. After reading the author's decisions:

- If the author only confirms/tweaks, compile a "confirmed handling list" as input for Phase 4.5's main draft integration.
- If the author's decisions surface new structural issues, update the corresponding report entries and re-run Step 5 if necessary.
- Do not proceed to Phase 4.5 until the author has filled in key decisions (especially structural decisions like opening contraction, ending role distribution).

### Step 7: Verification

After completion, check:

- Deliverable is in `04-global-review/global-review.md`, and a folder was created (not a bare file).
- Whether the full text was read as a continuous article, covering all six dimensions.
- Whether the cross-chapter repetition list is complete, with each entry having a handling verb and severity level.
- Whether necessary echoes are called out separately with a note to keep them.
- Whether each question requiring author sign-off has an inline `📝 Author decision:`, with no separate centralized decision area.
- Whether no main text chapters or other inputs were modified.
- Whether the main thread was checked against the brief; whether cross-chapter consistency of confirmed calibrations was re-checked.
- Whether sub-agent review was completed, and the main agent judged adoption.
- If the environment provides Markdown lint or editor diagnostics, check recently edited files; if no relevant diagnostics are available, don't force-run code lints.

## Author Decision Dialog

Phase 4 author judgments are **collected inline in the deliverable via `📝 Author decision:` by default, without opening with questions.** Only proactively use structured questions / dialog for the ambiguities listed in Step 2 that would block the deliverable (incomplete main text, unclear input source, user request conflicting with this phase).

Dialog rules (only when needed):

- Ask only the few items that truly block progress at one time.
- Give clear options for each question, allowing "other / need to supplement" as an escape hatch.
- Don't re-ask information already clarified in the brief, open-questions, or Phase 3.5 deliverables.
- Don't turn routine trade-offs that can be inline in the deliverable into opening questions.

## Output Style

- Use English unless the user specifies otherwise.
- The report is a working document: scannable, organized by dimension, each item short and specific.
- When quoting the main text, clearly mark the chapter and excerpt the original sentence for easy author reference.
- Use consistent handling verbs for suggestions (keep as echo / merge / delete / move later / rewrite as progression).
- Decision points are placed next to each question, marking the most critical ones.
- Final response only summarizes: output location, the single most important global issue, which items are structural decisions requiring author sign-off, sub-agent review conclusions, and next steps (wait for author to fill in decisions then return to Phase 3 or proceed to Phase 4.5).

## Relationship to the Workflow

This skill sits after Phase 3.5 (AI-assisted draft editing) and before Phase 4.5 (main draft integration). Its deliverable `04-global-review/global-review.md`, after the author fills in decisions, serves as input for Phase 4.5's main draft integration; if it reveals issues requiring direct draft editing, it can go back to Phase 3.

Recommended sequence:

- `article-workflow-brief`: Phase 0, editing brief
- `article-workflow-clean-sources`: Phase 0.5, dictated draft cleaning
- `article-workflow-section-review`: Phase 1, section-by-section narrative review
- `article-workflow-evidence-pool`: Phase 2, fact-checking and material pool
- Phase 3 author self-read and direct editing: no separate skill, author directly modifies `.article-workflow/00-cleaned-sources/`
- `article-workflow-ai-edit-pass`: Phase 3.5, AI-assisted editing per confirmed comments
- `article-workflow-global-review`: Phase 4, global coherence review

Planned subsequent phases:

- `article-workflow-main-draft`: Phase 4.5, main draft integration
- `article-workflow-visual-plan`: Phase 4.6, illustration and visual aid planning
- `article-workflow-style-bible`: Phase 5.0, style guide
- `article-workflow-polish`: Phase 5, multi-round polishing
- `article-workflow-final-review`: Phase 6, final refinement and reader testing