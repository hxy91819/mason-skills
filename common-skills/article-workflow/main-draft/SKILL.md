---
name: article-workflow-main-draft
description: Phase 4.5 of the article phased optimization workflow: Integrate main draft. Use when the user asks to execute Phase 4.5, integrate main draft, combine into a continuous article, main draft, or generate `.article-workflow/04.5-main-draft/` from `brief.md`, `03.5-ai-edit-pass/revised-sources/` (or `00-cleaned-sources/`), `02-evidence-pool/`, `04-global-review/global-review.md`.
priority: P2
---

# Article Workflow Main Draft

This is Phase 4.5 of the `article-workflow-*` skill series, corresponding to "Integrate Main Draft" in the article optimization workflow overview.

Goal: Before entering language polishing, **integrate scattered sections into a continuous main draft**. This phase only executes the delete/keep/move/supplement decisions the author finalized in Phase 4, handling section transitions, necessary reordering, and a small number of transitional sentences—**no language polishing, no rewriting of expressions, no making new judgments on behalf of the author**. The AI does integration and execution; the author does final confirmation.

## Trigger Scenarios

Use this skill when the user requests:

- Execute article optimization workflow Phase 4.5
- Integrate main draft / combine all sections into a continuous article / main draft
- Combine the working draft into a readable continuous draft per Phase 4 serial review conclusions
- Generate `.article-workflow/04.5-main-draft/`

## Input and Output

Default inputs:

- `.article-workflow/brief.md` (Phase 0 editorial brief, main thread, narrative attitude, must-keep judgment baseline)
- `.article-workflow/04-global-review/global-review.md` (Phase 4 review report, **author has filled in each `📝 Author Decision:`** — this is the most important input for this phase)
- Body chapter sections, one of two:
  - `.article-workflow/03.5-ai-edit-pass/revised-sources/*.md` — **if Phase 3.5 has passed author review, read this first**
  - `.article-workflow/00-cleaned-sources/*.md` — if Phase 3.5 was not executed
- `.article-workflow/02-evidence-pool/` (verify the stated framing of facts and confirmed facts, to avoid introducing new number/link errors during integration)
- `.article-workflow/03-author-pass-notes.md` (if available)
- Optionally reference `.article-workflow/03.5-ai-edit-pass/change-log.md` to confirm that unified fact-framing remains consistent after integration

Default output (**always create a folder, even if there's only one file**):

- `.article-workflow/04.5-main-draft/main-draft.md`: A continuous main draft with newly added/rewritten transitional sentences marked
- `.article-workflow/04.5-main-draft/integration-notes.md` (recommended): Decision-by-decision implementation log + list of new transitional sentences + author review decision slots

If the user provides an article directory, look for `.article-workflow/` under that directory first.

## Core Principles

- **Only execute decisions the author has confirmed**. Every deletion/merge/move/rewrite in the integration must be traceable to an `📝 Author Decision:` filled in by the author in `global-review.md`, or to the author's Phase 3 revision results. Do not introduce new deletions or changes based on this phase's own judgment.
- **No language polishing**. Cutting adverbs, adjusting sentence structures, and unifying terminology are Phase 5 tasks; this phase only resolves the structural integration of "scattered sections → continuous article."
- **Transitional sentences should be few, author-like, and marked**. Allow a small number of transitional sentences to connect sections naturally, but they must preserve the author's original voice; every new or rewritten transition must be explicitly marked in the text (e.g., `【New Transition】`, `【Rewritten·BN】`), so the author can find and confirm them at a glance.
- **Do not write new expressions beyond transitions**. All other sentences in the body should come entirely from `revised-sources/` (or `00-cleaned-sources/`), only performing deletion, merging, moving, and rewriting in confirmed directions — no inventing new paragraphs, new judgments, or new examples.
- **Do not reshape the article into a standard argumentative essay**. Preserve the original observer's voice, first-person perspective, and judgment style; do not sacrifice the author's voice for "structural neatness."
- **Execute deduplication, but follow Phase 4 action verbs**. The most common mistake in this phase is stringing identical expressions across multiple sections together verbatim; follow the author's confirmed "keep as echo / merge / delete / move later / rewrite as progression" one by one. Necessary echoes must be preserved — don't mistakenly delete them.
- **"Executed" does not mean "achieved"**. For decisions like "merge / weaken to echo / rewrite as progression / move later," after implementation, go back and confirm whether the *goal* was truly achieved: are there residual repetitions in adjacent sections, are dual landing points actually separated, are cross-section numbers reported redundantly, and are necessary echoes progressive rather than restatements? Only confirming "the action happened" easily leaves behind repetitions the author can spot at a glance (in practice, this often requires an author review round to catch).
- **Preserve confirmed fact-framing**. Do not introduce new numbers, links, name mentions, or citations during integration; fact-framing unified in Phase 3.5 / open-questions must remain consistent after merging.
- **Do not make decisions the author hasn't filled in**. Items left blank or marked "leave for polishing phase" in `global-review.md` (such as pure wording collisions) should not be forced in this phase; record them in `integration-notes.md` for Phase 5.
- **When encountering ambiguities that would block integration or affect the output direction, proactively use `AskQuestion` to confirm — do not guess**, and do not silently write them into `integration-notes.md` as pending items for the author to correct after the fact. Ambiguities that emerge mid-integration that are blocking should also be paused and asked about. (This does not conflict with the previous point: the previous point refers to items the author has "explicitly decided not to handle in this phase," which can be deferred; this point refers to items that "have no conclusion yet but would affect integration," which must be asked about first.)
- After writing the output, a sub-agent review must be launched; the sub-agent only provides review opinions, and the main agent decides whether to adopt them. If a sub-agent is unavailable, self-review using the same focus areas and note the limitation in the final response.

## Workflow

### Step 1: Read inputs, confirm decisions are complete

- First determine which body text set to read: check whether Phase 3.5 has passed author review (look at `03.5-ai-edit-pass/author-review-checklist.md` / `change-log.md`). If passed, read `revised-sources/`; otherwise, read `00-cleaned-sources/`.
- Read `global-review.md`, transcribe each B / R / F / A **author decision** into a "confirmed action checklist" (which to delete, which to keep, where to move, what to rewrite, which are must-keep echoes).
- Read `brief.md` (main thread, narrative attitude, must-keep judgments, "imperfections" that must be acknowledged) and `02-evidence-pool/` (confirmed fact-framing).
- Check for `03-author-pass-notes.md`.

### Step 2: Determine whether to ask the author first

This phase is primarily about **executing confirmed decisions**; in most cases, no opening questions are needed. Only ask (using `AskQuestion` structured format) when ambiguities arise that would block integration or affect output direction:

- **Key structural decisions still left blank or self-contradictory** in `global-review.md` (especially opening contraction, ending division of labor) that make integration impossible based on them.
- Phase 4 left a "major chapter reorder" but didn't give a specific order; the author needs to determine the order.
- **Section subtitle style undetermined**: If the full text is on the longer side and subtitles would help readers, but the author hasn't specified which type, ask once (see "Author Decision Dialog").
- User request conflicts with Phase 4.5 (e.g., requesting substantial expression rewriting or main thread changes rather than integration).

If no such ambiguities exist, proceed directly with integration — do not force questions for formality's sake.

### Step 3: Integrate into a continuous main draft

Following the current (or author-confirmed adjusted) chapter order, combine sections into a continuous article:

- Implement the "confirmed action checklist" chapter by chapter: delete what should be deleted, merge what should be merged, move what should be moved, rewrite in the confirmed direction.
- Add a **small number** of transitional sentences at section seams, preserving the author's voice, and mark each one.
- Execute cross-section repetitions per Phase 4 action verbs: merge/delete bad repetitions; rewrite as progression; preserve necessary echoes.
- Throughout, compare against `revised-sources/` as the "before" baseline, ensuring no new expressions were written beyond marked transitions.
- Preserve confirmed fact-framing; do not introduce new numbers/links/name mentions.

### Step 4: (If needed) Handle section subtitles

If the article is long and the author confirms subtitles should be added:

- Default to **plain phrase subtitles** (strong essay feel, not academic); alternatively, use "numbered phrases" or no subtitles per author preference. Bare numbers are generally not recommended.
- The opening usually serves as a lead-in without a subtitle; add subtitles from the second section onward.
- **Resolve hierarchy conflicts**: If a section (e.g., "Features" or "How It Works") already has `##` subheadings inside, after adding a chapter-level `##`, demote those internal subheadings to `###` to form a clean two-level structure.
- Record the subtitle addition in `integration-notes.md`, noting that wording can be fine-tuned in Phase 5.

### Step 5: Write outputs

Create the `04.5-main-draft/` folder (even if there's only one file):

- `main-draft.md`: The continuous main draft. At the top, include a one-line note explaining this is the Phase 4.5 integrated draft, mark the legend (`【New Transition】`/`【Rewritten·BN】`), note title is TBD, etc.
- `integration-notes.md` (recommended):
  - **New/rewritten transitional sentence list**: Extract each transitional sentence, noting which Phase 4 item (B1/B2…) it corresponds to, so the author can confirm whether it sounds like something they would write.
  - **Decision-by-decision implementation table**: A table cross-referencing each B/R/F from `global-review.md` + author opinion + integration action taken.
  - **Unhandled / deferred items**: Decisions the author left blank, wording deferred to Phase 5, title TBD, fact-framing review items.
  - **Author review decision slots**: Inline `📝 Author Decision:` items for Phase 4.5 confirmations — whether new transitional sentences sound like the author's voice, whether section order adjustments match the original narrative intent, whether merged/deleted/moved content aligns with the author's Phase 1–3 conclusions, whether the integrated draft has become a "standard article" that lost the original voice, and whether this version is ready for Phase 5 polishing.

### Step 6: Launch sub-agent for goal alignment + decision implementation review

After writing outputs, the main agent must launch a read-only sub-agent review. The sub-agent only provides review opinions, focusing on:

- **Decision implementation**: Verify each B/R/F the author confirmed in `global-review.md` has actually been implemented in `main-draft.md` (using `revised-sources/` as the "before" baseline, confirming deletions/merges/moves/rewrites actually occurred), checking for omissions or discrepancies with `integration-notes.md` declarations.
- **Residual deduplication check (most commonly missed)**: For "merge / weaken / rewrite as progression / move later" decisions, don't just verify "the action happened" and pass it — confirm the *goal* was achieved: no residual repetitions in adjacent sections, whether landing points are truly separated, whether cross-section numbers are reported redundantly, whether echoes have become restatements. The sub-agent should report "fully separated / residual remains" rather than a binary "applied ✅".
- **Whether necessary echoes were mistakenly deleted** (🟢 keep category).
- **Whether transitions overstep their bounds**: Whether marked transitional sentences are purely connective without smuggling in new judgments/expressions; whether the rest of the body text can be traced back to the working draft.
- **Voice and boundaries**: Whether the article was reshaped into a "standard argumentative essay" that lost the author's voice; whether Phase 5 polishing was done prematurely.
- **Fact-framing consistency**: Whether confirmed numbers/links/citations remain consistent after merging.

After receiving the review, the main agent: judges which findings are valid; adopts only recommendations aligned with Phase 4.5 objectives; revises the main draft accordingly; briefly explains reasons for not adopting suggestions. If a sub-agent is unavailable, self-review using the above focus areas and note the limitation.

### Step 7: Handle author review, iterate as needed

The author will fill in confirmations after `📝 Author Decision:` in `integration-notes.md`, or annotate directly on `main-draft.md`:

- **Classify author feedback first**: Structural residuals (adjacent repetitions, undivided landing points, cross-section numbers still redundantly reported, content attribution errors) still need to be fixed in this phase — fix directly in the main draft. Pure language/style issues (awkward phrasing, list formats too AI-summary-like, word choice, subtitle naming, whether quotes should use the Chinese or English original text) should be recorded by default and carried to Phase 5 — do not force them in this phase unless the author explicitly requests it now. Sentence-level feedback the author gives after reading through often falls into the latter category — don't get pulled into doing polishing early.
- **Remove temporary markers**: After the author confirms the voice of transitional sentences, remove `【New Transition】`/`【Rewritten】` markers and the top legend from the main draft so it enters Phase 5 cleanly.
- If the author approves and the voice is preserved, prepare the draft for Phase 5.
- If a section doesn't sound like the author or reveals content issues requiring direct rewriting, go back to Phase 3 for the author to revise, or return to Phase 4 for re-division.
- Do not proceed to Phase 5 until the author confirms this main draft version is ready for polishing.

### Step 8: Verification

After completion, check:

- Outputs are in `04.5-main-draft/main-draft.md`, and a folder was created (not a bare file).
- The main draft is a continuous, readable article with natural section transitions.
- Every new/rewritten transition is marked (after the author confirms the voice, these markers should be removed); beyond transitions, no new expressions were written (everything is traceable to the working draft).
- Every author-confirmed deletion/merge/move/rewrite has been implemented; necessary echoes are preserved.
- No language polishing was done, the article was not reshaped into a standard argumentative essay, and no author judgments were replaced.
- Confirmed fact-framing is consistent after merging.
- If subtitles were added, the hierarchy is correct (chapter-level `##`, internal subheadings `###`), with no conflicts with existing subheadings.
- Author review decision slots are inline and complete.
- Sub-agent review (including decision implementation check) has been completed, and the main agent has made adoption decisions.
- If the environment provides Markdown lint or editor diagnostics, check recently edited files; if no relevant diagnostics exist, do not force-run code lints.

## Author Decision Dialog

This phase is primarily about **executing confirmed decisions**; in most cases, no opening questions are needed. Only use `AskQuestion` to confirm when ambiguities arise that would block integration or affect output direction (see Step 2).

The most common genuine decision point is **section subtitles**. If the full text is on the longer side, subtitles would help, and the author hasn't specified a style, ask once:

- Subtitle format: plain phrase subtitles (recommended, essay feel) / numbered phrases (strong sequential feel) / simple numbers 1/2/3 / no subtitles, keep continuous.
- Specific wording: use the agent's proposed set / direction is right but the author adjusts themselves.

Dialog rules (only when needed):

- Only ask the few items that truly block progress or significantly affect the output.
- Provide clear options for each question, allowing "Other / need to add" as an escape option.
- Do not re-ask information already clear in the brief, global-review author decisions, or Phase 3.5 outputs.
- Deletion/change directions the author finalized in Phase 4 should be executed directly in this phase; do not go back and ask again.

## Output Style

- Use English unless the user specifies otherwise.
- `main-draft.md` should read like a **real article**, not working notes; markings should be limited to new/rewritten transitions for easy author identification and removal.
- `integration-notes.md` is a working file: decisions should be traceable item by item, new transitions should be verifiable, and pending items should be clear.
- The final response should only summarize: output location, which structural integrations were applied, how many new/rewritten transitions need author confirmation, the sub-agent's conclusions (including decision implementation check), and next steps (proceed to Phase 5 after author confirmation, or return to Phase 3).

## Relationship to the Workflow

This skill comes after Phase 4 (global serial review) and before Phase 4.6 (visual and illustration planning). It reads the decisions the author filled in `04-global-review/global-review.md`, integrates them into `04.5-main-draft/main-draft.md`; after the author confirms this main draft, it serves as input for Phase 4.6 visual planning and Phase 5 polishing; if content issues requiring direct rewriting are revealed, it can go back to Phase 3 or Phase 4.

Recommended sequence:

- `article-workflow-brief`: Phase 0, Editorial Brief
- `article-workflow-clean-sources`: Phase 0.5, Dictation Draft Cleanup
- `article-workflow-section-review`: Phase 1, Section-by-Section Narrative Review
- `article-workflow-evidence-pool`: Phase 2, Fact Verification and Material Pool
- Phase 3 Author Read-Through and Direct Revision: no separate skill; the author directly modifies `.article-workflow/00-cleaned-sources/`
- `article-workflow-ai-edit-pass`: Phase 3.5, Assisted Editing per Confirmed Opinions
- `article-workflow-global-review`: Phase 4, Global Serial Review
- `article-workflow-main-draft`: Phase 4.5, Integrate Main Draft
- `article-workflow-visual-plan`: Phase 4.6, Visual and Illustration Planning
- `article-workflow-style-bible`: Phase 5.0, Style Guide
- `article-workflow-polish`: Phase 5, Multi-Round Polishing
- `article-workflow-final-review`: Phase 6, Final Refinement and Reader Testing