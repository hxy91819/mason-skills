---
name: article-workflow-polish
description: Article multi-phase optimization workflow Phase 5: round-by-round polish. Under the constraint of preserving personal style, iteratively polish the main draft expression across rounds (5.1 trim redundancy → 5.2 adjust rhythm → 5.3 unify terminology). Use when the user asks to execute Phase 5, round-by-round polish, polish, language polish, or generate `.article-workflow/05-polish-rounds/` from `.article-workflow/04.5-main-draft/main-draft.md` and `.article-workflow/style-bible.md`.
priority: P2
---

# Article Workflow Polish

This is Phase 5 of the `article-workflow-*` skill series, corresponding to the "round-by-round polish" step of the article optimization workflow.

Goal: Under the constraint of preserving the author's personal style, iteratively polish the main draft expression across three rounds — remove truly redundant words (not tone carriers), smooth out truly awkward sentences (not flatten deliberate rhythm), and unify residual terminology and formatting inconsistencies. The AI executes; the author makes the final judgment. Each round produces independent output, and the next round only proceeds after the author confirms.

## Trigger Scenarios

Use this skill when the user requests:

- Executing article optimization workflow Phase 5
- Round-by-round polish / language polish / polish
- Generating `.article-workflow/05-polish-rounds/` output
- Doing a final expression polish pass after the main draft is complete
- Starting from the main draft + style bible and iteratively tightening the text

## Input and Output

Default inputs:

- `.article-workflow/04.5-main-draft/main-draft.md` (the integrated main draft from Phase 4.5, serving as the polish baseline)
- `.article-workflow/style-bible.md` (the style bible from Phase 5.0; must be read before each polish round)
- `.article-workflow/04.6-visual-plan/visual-plan.md` (if present; only used to avoid polish disrupting planned text-image rhythm; does not change the polish scope)

Optional inputs:

- `.article-workflow/00-cleaned-sources/terminology-notes.md` (confirmed proper noun table and uncertain items from Phase 0.5)

Default outputs (all placed in a single directory):

- `.article-workflow/05-polish-rounds/05.1-trim.md`: Round 1 — trim redundant words
- `.article-workflow/05-polish-rounds/05.2-rhythm.md`: Round 2 — adjust rhythm
- `.article-workflow/05-polish-rounds/05.3-terms.md`: Round 3 — unify terminology
- `.article-workflow/05-polish-rounds/polished-draft.md`: Final polished draft output from the three rounds

If the user provides an article directory, first look for `.article-workflow/` within that directory.

## Core Principles

- **Each round does only one thing.** 5.1 only trims redundant words; 5.2 only adjusts sentence rhythm; 5.3 only unifies terminology. Do not mix tasks across rounds — cross-round changes interact, and mixing makes rollback difficult.
- **All tone carriers are in the no-edit zone.** For example: transitions, expressions of doubt, hesitation, emphasis, colloquial judgments, and connective words that lower the comprehension barrier; these may not be redundant words but rather part of the author's tone. When unsure whether something is redundant or a tone carrier, default to not changing it.
- **Short-sentence judgments, rhetorical-question progression, change-of-mind rhythm, and personal closing paragraphs are entirely off-limits.** These are signature strokes that Phase 5 must not touch. Changing them would make the article feel like it was written by someone else.
- **Overall polish direction: make the article cleaner, not more standardized.** Clean = remove true redundancy, smooth true awkwardness; standardized = impose uniform sentence patterns, erase personality, converge toward "standard" prose. The latter is a directional error.
- **Every round must read style-bible.md.** Re-read it before each round — not just once at the beginning.
- **Each round's output must be confirmed before proceeding.** After one round is complete, wait for the author to confirm (or point out mistaken deletions/edits) before advancing to the next round. Do not run all three rounds and submit together — if a tone carrier was mistakenly removed, the subsequent rounds will build on a corrupted baseline.
- **When uncertain about a change, default to reverting.** If you're unsure whether a change oversteps, default to not changing or reverting. The author would rather see a clean version that reads like their own writing than a perfect version that reads like someone else's.
- **For an article that has gone through the full Phase 1–4 process, Phase 5 changes are typically minimal.** If one round changes dozens of places, it has likely overstepped. A mature main draft that has gone through four rounds of editing typically has no more than 10 mechanical redundancies per round that genuinely need removal.
- **After each round's output is written, a sub-agent review must be launched;** the sub-agent only provides review observations, and the main agent decides whether to adopt them.

## Workflow

### Step 0: Confirm Round Scope

Before executing this skill, confirm which rounds the user wants to run. Use `AskQuestion` once (if the user hasn't specified):

- **All three rounds** (5.1→5.2→5.3, recommended): suitable for articles that have gone through the full Phase 0–4.5
- **5.1 only** (trim redundancy only): suitable for articles that have already had rhythm adjustment and terminology unification
- **5.1 + 5.2** (trim redundancy + adjust rhythm): suitable for articles where terminology is already unified
- **Skip 5.1, only 5.2 + 5.3**: suitable for articles that have already been trimmed

If the user's request already specifies particular rounds (e.g., "execute Phase 5.1 and 5.2"), proceed directly without asking.

Also confirm whether the Phase 5.0 style-bible exists. If it doesn't, `article-workflow-style-bible` must be executed first before entering polish.

### Step 1: Read Inputs

When entering each new round, read:

1. `style-bible.md` — as the constraint baseline for this round
2. This round's input file:
   - 5.1: `04.5-main-draft/main-draft.md`
   - 5.2: `05-polish-rounds/05.1-trim.md`
   - 5.3: `05-polish-rounds/05.2-rhythm.md`
3. If running 5.3, also read `terminology-notes.md` (if present; for legacy projects, fall back to reading `_cleaning-notes-terminology.md` if that's all that exists)

### Step 2: Execute the Current Round

#### 5.1 Trim Redundant Words

Goal: Remove truly redundant words while preserving all tone carriers.

**Allowed to trim**:
- Redundant semantics
- Unnecessary prepositions
- Degree words that carry no tone
- Unnecessary self-reference ("the merging process itself" → "the merging process")
- Obvious verbal filler (note: articles transcribed from AI dictation have usually already been cleaned)

**Forbidden to trim (tone carriers)**:
- Words that express transition, doubt, reservation, or judgment intensity
- Colloquial connective words that lower the comprehension barrier
- Expressions the author uses repeatedly and that are listed in the style-bible no-edit zone
- All short-sentence judgments ("not perfect, but workable"; "build first, optimize later"; etc.)
- Sentences in personal closing paragraphs that carry the author's observations and aftertaste

**Execution method**:
- Output `05.1-trim.md`, with this round's principles noted in the file header comment
- For each proposed change, first ask yourself: does this word carry the author's tone? If yes, do not change it
- After editing, diff against the source file and check whether any tone carriers were mistakenly deleted. If any no-edit words were removed in the diff, revert them
- If unsure whether a word should be deleted, default to not deleting

#### 5.2 Adjust Sentence Rhythm

Goal: Fix truly awkward sentence structures or missing punctuation, without flattening the author's deliberate rhythm.

**Allowed to adjust**:
- Parallel structures that are grammatically broken
- Missing commas in long sentences that cause reading difficulty
- New issues introduced by 5.1 (e.g., removing a word broke a paired structure like "first...then...")

**Forbidden to adjust (author's deliberate rhythm)**:
- Rhetorical-question progression ("How does this work?" "What did these tokens actually buy?") — must not be converted to declarative sentences
- Short-sentence judgments — must not be expanded into full sentences
- Change-of-mind rhythm — must not be flattened
- Natural connective transitions between sections — must not be replaced with stacked subheadings
- Personal closing paragraphs — do not touch unless there are obvious typos

**Execution method**:
- Output `05.2-rhythm.md`, with this round's principles noted in the file header comment
- Only fix truly awkward passages — do not fix things that "could be smoother"; smoothness is not the goal; faithfulness to the author's rhythm is
- If you find issues introduced by 5.1 (as in the example above), fix them and note the fix
- If the entire text reads smoothly with nothing to fix, output a nearly identical file and explain

#### 5.3 Unify Terminology and Formatting

Goal: Fix residual inconsistencies across the full text so they align with the style-bible proper noun table.

**Checklist**:
- Terminology capitalization and Chinese/English writing conventions (per the proper noun table)
- Consistency of project names, person names, tool names, and model names throughout
- Chinese-English spacing (where Chinese text abuts English)
- Lane name capitalization
- Person name writing conventions
- Quotation mark style (full-width / half-width)
- Number formatting

**Execution method**:
- Output `05.3-terms.md`, with this round's principles noted in the file header comment
- Use grep/regex to scan the source file for all inconsistencies
- Prioritize the style-bible proper noun table and `terminology-notes.md` as authority
- If you find terminology inconsistencies not covered by the style-bible, note them but do not change them; wait for the author to confirm, update the style-bible, then come back and fix
- For an article that has gone through Phase 0–4.5, this round typically has very few changes (1–3 places)

### Step 3: Wait for Author Confirmation After Each Round

After each round:

1. Show what changed using a diff (line-by-line comparison with the source file)
2. List each change and the reason for it
3. If any change was mistaken (especially in 5.1 where a tone carrier was mistakenly deleted), mark it as "reverted" and explain
4. Wait for the author to say "continue" or provide correction feedback before advancing to the next round
5. If the author identifies mistaken deletions or edits, revert first, then continue to the next round

This round-by-round confirmation is critical — practical experience shows that in 5.1, the AI is most prone to the error of "treating tone carriers as redundant words and removing them." The author must have the opportunity to review the diff.

### Step 4: Generate polished-draft.md

After all specified rounds are complete and the author has confirmed:

- Copy the final round's output file as `polished-draft.md`
- Update the file header comment to "Polished Draft"
- Verify the diff volume between polished-draft.md and the original main-draft.md with a single command — for an article that has gone through Phase 1–4, the total changes across three rounds are typically 10–20 places. If there are 50+ changes, the process has likely overstepped
- **If only partial rounds were run** (e.g., 5.1 only): `polished-draft.md` = `05.1-trim.md` (renamed), with the header noting which rounds were actually executed

### Step 5: Launch Sub-agent for Review

After each round's output is written (including the final polished-draft.md), the main agent must launch a read-only sub-agent for alignment review.

Sub-agent review focus (by round):

**General**:
- Was style-bible.md read and its constraints followed?
- Were no-edit zones touched? (rhetorical-question progression, short-sentence judgments, colloquial connective words, change-of-mind rhythm, personal closing paragraphs)
- Do the changes maintain the direction of "making the article cleaner, not more standardized"?
- Were no negative-list tones introduced?

**5.1 specific**:
- Were any tone carriers mistakenly removed as redundant words?
- Are all deletions truly redundant, with no no-edit words removed?

**5.2 specific**:
- Were any of the author's deliberate rhythms mistakenly flattened?
- Were any "standardized" sentence patterns introduced?
- Were new issues introduced by 5.1 identified and noted?

**5.3 specific**:
- Do terminology corrections align with the style-bible proper noun table?
- Are there remaining inconsistencies that were not corrected?
- Has Chinese-English spacing been checked?

**polished-draft comprehensive**:
- Is the total change count across all three rounds reasonable (typically <20)?
- Compared to the original main-draft, is the language cleaner but still recognizably the same author's article?

After the main agent receives the review:

- Independently judge which observations are valid
- Only adopt suggestions consistent with this round's goal
- If adopting, update this round's output
- If not adopting, briefly explain why in the final reply

### Step 6: Verification

After completion, check:

- Outputs are in the `05-polish-rounds/` directory, including the specified round outputs and `polished-draft.md`
- Each round's output file has this round's principles noted in the header comment
- polished-draft.md exists and the diff against the original main-draft shows a reasonable number of changes
- All style-bible.md no-edit zones have been respected
- No tone carriers were mistakenly deleted
- Rhetorical-question progression, short-sentence judgments, change-of-mind rhythm, and personal closing paragraphs are all fully preserved
- No negative-list tones were introduced
- Each round has completed sub-agent review, with the main agent making adoption decisions
- Each round only advanced after author confirmation

## Recommended Models

Switching models across Phase 5 rounds can improve cost-effectiveness:

| Round | Recommended Model | Reason |
|-------|-------------------|--------|
| 5.1 | Cost-effective model (e.g., DeepSeek, GPT-4o-mini) | Removing adverbs is a mechanical task; a cost-effective model suffices |
| 5.2 | Language-sensitive model (e.g., Claude Opus, GPT-4o) | Restructuring sentences requires language sensitivity |
| 5.3 | Chinese-friendly model (e.g., DeepSeek) | Terminology unification is pattern recognition; choose a Chinese-friendly model |

If only one model can be used, prefer the 5.2 recommended model — language sensitivity is the most critical capability for the entire Phase 5.

## Author Decision Dialog

This skill requires only one opening confirmation (Step 0), followed by round-by-round waiting for the author's review and confirmation. There are no decisions that need to be collected via dialog within each round — the style bible has already defined all constraints, and the polish execution is mechanical.

Only when the style-bible does not exist do you need to first execute `article-workflow-style-bible` and complete its dialog confirmation.

**Do not proactively ask**:
- "Should this tone word be changed?" — Check the style-bible no-edit zone
- "Should this expression be kept?" — Check the style-bible
- "Should content be added/removed?" — Phase 5 does not make structural changes

## Output Style

- Use English unless the user specifies otherwise.
- Each round's output uses diff + table to explain changes and their reasons
- Do not output a "before polish / after polish" full-text comparison — diff is sufficient
- The final reply only summarizes: how many changes this round, any reverted mistaken deletions, sub-agent review conclusions, and waiting for author confirmation before proceeding to the next round
- Do not explain line by line why something was not changed — the burden of proof is on the agent to demonstrate a word is redundant, not to demonstrate it should be kept

## Relationship to the Workflow

This skill is the Phase 5 execution body, running after Phase 4.6 (illustration and visual aid planning, optional) and `article-workflow-style-bible` (Phase 5.0). Its output `polished-draft.md` is the input for Phase 6 (final review and reader testing).

This skill must read `style-bible.md` as the constraint baseline. If the style-bible does not exist, `article-workflow-style-bible` must be executed first before entering polish.

Recommended sequence:

- `article-workflow-brief`: Phase 0, editorial brief
- `article-workflow-clean-sources`: Phase 0.5, dictation transcript cleaning
- `article-workflow-section-review`: Phase 1, section-by-section narrative review
- `article-workflow-evidence-pool`: Phase 2, fact-checking and material pool
- Phase 3 author self-read and direct editing: no separate skill; the author directly edits `.article-workflow/00-cleaned-sources/`
- `article-workflow-ai-edit-pass`: Phase 3.5, AI-assisted editing based on confirmed feedback
- `article-workflow-global-review`: Phase 4, holistic coherence review
- `article-workflow-main-draft`: Phase 4.5, integrated main draft
- `article-workflow-visual-plan`: Phase 4.6, illustration and visual aid planning
- `article-workflow-style-bible`: Phase 5.0, style bible
- `article-workflow-polish`: Phase 5, round-by-round polish (this skill)
- `article-workflow-final-review`: Phase 6, final review and reader testing