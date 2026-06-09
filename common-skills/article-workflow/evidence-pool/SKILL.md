---
name: article-workflow-evidence-pool
description: Phase 2 of the article stage-by-stage optimization workflow: Fact-checking & Evidence Pool. Use when the user asks to execute Phase 2, fact-checking, evidence pool, fact-check, or generate `.article-workflow/02-evidence-pool/` from `.article-workflow/brief.md`, `00-cleaned-sources/`, `01-section-reviews/` and `sources/references/`.
priority: P2
---

# Article Workflow Evidence Pool

This is Phase 2 of the `article-workflow-*` skill series, corresponding to "Fact-checking & Evidence Pool" in the article optimization workflow.

Goal: Organize the article's facts, cases, data, screenshots, source code, and quotes into a verifiable evidence pool first — **do not rush to stuff them back into the body text**. AI performs fact-checking, cross-referencing, and material classification, providing evidence strength and usage recommendations; the author completes necessary responses in Phase 2 deliverables and directly edits the working draft in Phase 3. AI must not edit the body text, write paragraphs on behalf of the author, or decide what to keep or delete on the author's behalf.

## Trigger Scenarios

Use this skill when the user requests:

- Execute article optimization workflow Phase 2
- Fact-check article materials, look for evidence, verify data
- Generate `.article-workflow/02-evidence-pool/`
- Organize evidence, quotes, screenshots, and source-code facts that can enter the body text
- Collect questions that require the author to supplement sources or confirm

## Input and Output

Default inputs:

- `.article-workflow/brief.md`
- `.article-workflow/00-cleaned-sources/*.md`
- `.article-workflow/01-section-reviews/` (especially `📝 Author response:` in `index.md`)
- `.article-workflow/sources/references/` (if present)
- `.article-workflow/sources/proofs/` (first-hand evidence such as screenshots, if present)

Default outputs:

- `.article-workflow/02-evidence-pool/fact-check.md`: Fact-claim verification checklist
- `.article-workflow/02-evidence-pool/evidence-pool.md`: Evidence and material pool that can enter the body text
- `.article-workflow/02-evidence-pool/open-questions.md`: Questions requiring the author's supplementation or confirmation

If the user provides an article directory, first look for `.article-workflow/` within that directory. If `brief.md` or `00-cleaned-sources/` is missing, ask whether to proceed; without a brief, it is impossible to judge "which materials serve the main thread vs. which are merely interesting but distracting," so only basic fact-checking can be performed.

## Core Principles

- Verify and organize, do not edit the body text. Only provide material recommendations and a verification checklist; do not write paragraphs on the author's behalf.
- Do not decide what to keep or delete on the author's behalf. Phase 2 only labels evidence strength and usage recommendations; final trade-off is the author's work in Phase 3.
- **Proactively verify accessible first-hand evidence**: Screenshots in `sources/proofs/` must actually be opened and examined (read images, read source code, read the original review text) — do not rely solely on the body text's paraphrasing. The most valuable findings in this phase often come from personally checking original materials.
- **Cross-reference numerical consistency across the entire repository**: The same fact (amounts, quantities, versions, layer counts, etc.) is frequently inconsistent across the brief, cleaned drafts, references, and early drafts. Identify contradictions one by one and indicate which has evidentiary support.
- Do not fabricate verification results. External links that have not been personally verified should be labeled "pending verification," never written as "verified."
- Keep the three material categories clear: Verified (with screenshot/link/source code/PR/commit/comment), Pending verification (needs supplementary source or reconfirmation), Personal judgment (keep as judgment, do not present as fact).
- Preserve the "imperfections" that the brief's risk-attitude requirements mandate acknowledging; do not downplay shortcomings during verification.
- Respect existing `📝 Author response:` in `01-section-reviews/index.md`; do not re-ask confirmed directions as open questions.
- Distinguish two types of uncertainty: Points that would block this phase's output direction (missing brief, contradictory source materials with no way to determine which to follow, user's stated approach conflicting with Phase 2) must be confirmed with the author proactively — they cannot just be written into `open-questions.md` for the author to discover later; only author-side trade-off decisions belong in `open-questions.md` for Phase 3.
- Do not modify any source materials by default (including incorrect numbers in references); if source material errors are found, note them in the deliverables and ask before changing.
- After each round of deliverables is complete, a sub-agent must be launched for an alignment review; the sub-agent only provides review opinions, and the main agent decides whether to adopt them.
- If a sub-agent is unavailable, the main agent must perform self-review against the same review focus and state this limitation in the final response.

## Workflow

### Step 1: Read Materials

Read the following:

1. `.article-workflow/brief.md`, focusing on "evidence standards," "core claims," "section trade-off," and "author judgments to preserve"
2. All body-text chapter files under `.article-workflow/00-cleaned-sources/` (skip intermediate artifacts like `terminology-notes.md`, `_cleaning-notes-*`)
3. `.article-workflow/01-section-reviews/`, especially global decisions and `📝 Author response:` in `index.md`
4. `.article-workflow/sources/references/` (detail-notes, early-materials, early-drafts, etc.)
5. First-hand evidence such as screenshots under `.article-workflow/sources/proofs/` — **actually open and verify, not just check filenames**
6. If `.article-workflow/02-evidence-pool/` already exists, read existing deliverables and update rather than blindly overwriting

After reading, first determine:

- Which are hard facts that must have sources, and which are personal judgments that can be softened
- Which evidence is already complete, and which lacks links/screenshots/source-code locations
- Which numbers are written inconsistently across different materials

### Step 2: Verification and Cross-referencing

Organize factual claims one by one, and perform two fact-checking tasks:

- **First-hand verification**: Open `sources/proofs/` screenshots, reference source-code notes, and original review text to confirm whether the body text's paraphrasing is consistent with the original materials.
- **Cross-referencing**: Place the same fact's various descriptions from the brief, cleaned drafts, references, and early-drafts side by side, marking contradictions and which has evidentiary support.

Common items to focus verification on:

- Specific numbers: amounts, quantities, percentages, durations, version numbers, layer counts, headcounts, etc.
- Different metrics for the same indicator (e.g., "cumulative closures" and "current outstanding" are not the same thing — do not conflate them)
- Named external facts (naming a specific project/person + making accusatory claims; high risk without links)
- Whether quotes and paraphrases (famous quotes, tweets, podcasts) have traceable sources
- Whether screenshots actually exist in `sources/proofs/`, and whether screenshots claimed in the body text are missing

Do not edit the body text at this stage, and do not write paragraphs on the author's behalf.

### Step 3: Determine Whether to Ask the Author First

Phase 2 is a diagnostic phase by default. Author decisions are collected via `open-questions.md` and left for Phase 3 — **typically no need to open a dialog**.

Only proactively confirm with the author when there are blocking ambiguities that would affect the entire Phase 2 deliverable's direction. Prefer structured questions or dialog mechanisms; use plain text questions only if such tools are unavailable. Common situations requiring upfront confirmation:

- Missing `brief.md` or `00-cleaned-sources/`, making it impossible to determine the main thread and evidence standards
- Multiple contradictory versions exist in references/proofs with no way to determine which to follow
- The user's requested approach conflicts with workflow Phase 2, e.g., requesting toincidentally edit the body text or write paragraphs

If there are no such ambiguities, do not force questions for formality's sake; proceed directly, write items needing the author's decision into `open-questions.md`, and state key assumptions in the final response.

Note the distinction: ambiguities that block this phase's output direction must be asked first — they cannot just be written into `open-questions.md` for the author to discover later; `open-questions.md` is only for trade-off decisions that don't block output and are left for the author to decide in Phase 3.

### Step 4: Write Three Deliverables

#### fact-check.md (Fact-claim Verification Checklist)

Organize by verification status. Each entry provides the claim, source, current evidence, status, and recommended action.

Suggested status legend:

- ✅ Verified: Has traceable evidence such as screenshots/tweets/source code/original review text
- ⚠️ Pending verification: Direction is credible, but lacks links/sources, or numbers are inconsistent across multiple places
- 💭 Personal judgment/experience: Preserve as the author's judgment, do not present as a hard fact requiring statistical evidence

Suggested sections: Hard data (readers will catch errors), Mechanism-type claims, External facts/citations, Content that should remain as personal judgment. At the end, include a "will become hard errors" action summary listing the few items that must be resolved before entering the main draft.

#### evidence-pool.md (Evidence Material Pool for Body Text)

Archive evidence by article main-thread sections, labeling each entry with evidence strength, source, and recommended usage.

Suggested evidence strength legend: 🟢 Strong (can be cited directly) / 🟡 Medium (usable but needs supplementary source or restrained use) / 🔴 Weak (background only or soften expression).

Usage discipline follows the brief: body text states a fact in one sentence, key evidence uses links/footnotes, screenshots serve as illustrations not replacing arguments, technical details are only elaborated to the extent they support claims. At the end, an optional "citable quotes reference" table can be attached, consolidating original text and sources.

#### open-questions.md (Questions Requiring Author's Supplementation or Confirmation)

Collect questions requiring the author's decision or supplementary materials before entering Phase 3 / Phase 4.5, graded by severity:

- 🔴 Will become a hard error in the body text if unresolved (contradictory numbers, unsourced naming, missing key screenshots, etc.)
- 🟡 Affects credibility, recommended to resolve (missing links, missing sources, precision of headcounts, etc.)
- 🟢 Optional improvements (add PR numbers, add illustrations, etc.)

Each question retains a `📝 Author response:` slot. At the end, provide a handoff summary indicating which questions must be answered at minimum before proceeding to the next phase.

### Step 5: Launch Sub-agent for Review

After the three deliverables are written, the main agent must launch a read-only sub-agent to review whether this round's deliverables align with Phase 2 objectives.

Sub-agent review focus:

- Whether only verification and material organization was done, with no body-text edits or paragraphs written on the author's behalf
- Whether accessible first-hand evidence (screenshots, source code, original review text) was actually verified, not just based on paraphrasing
- Whether repository-wide numerical cross-referencing was performed and contradictions identified
- Whether verified/pending verification/personal judgment categories were distinguished, without writing unverified links as verified
- Whether the evidence pool is organized by main-thread sections with strength and usage recommendations labeled
- Whether `open-questions.md` is graded by severity and retains `📝 Author response:`
- Whether the brief's required "imperfections" are preserved
- Whether directions already confirmed by the author in `01-section-reviews/index.md` are not re-raised as open questions
- Whether source materials were not modified without authorization

After the main agent receives the review:

- Judge which opinions are valid on its own
- Only adopt suggestions consistent with Phase 2 objectives
- Do not enter body-text editing or paragraph writing based on review opinions
- If adopted, update the corresponding deliverable
- If not adopted, briefly explain the reason in the final response

If the current environment cannot launch a sub-agent, the main agent must perform self-review against the above focus areas and state this limitation in the final response.

### Step 6: Verification

After completion, check:

- Whether `.article-workflow/02-evidence-pool/` exists
- Whether `fact-check.md`, `evidence-pool.md`, and `open-questions.md` have all been generated
- Whether each factual claim has a source and verification status
- Whether `sources/proofs/` screenshots and other first-hand evidence were actually opened and verified
- Whether numerical cross-referencing was performed and contradictions identified
- Whether the evidence pool has evidence strength and usage recommendations labeled
- Whether `open-questions.md` is graded by severity and retains `📝 Author response:`
- Whether inputs such as `brief.md`, `00-cleaned-sources/*.md`, `01-section-reviews/`, `sources/` were not modified
- Whether sub-agent review was completed and adopted based on the main agent's judgment
- If the environment provides Markdown lint or editor diagnostics, whether recently edited files were checked; if no relevant diagnostics exist, do not force-run code lints

## Output Style

- Use English unless the user specifies otherwise.
- All three deliverables are working documents — they should be clear, concise, and actionable.
- Use emoji + English labels for status and strength, for quick scanning by the author.
- Each verification item includes a "recommended action," not just pointing out the problem.
- Original text quotes are consolidated for easy reuse in subsequent phases.
- The final response only summarizes the output location, the most important verification findings (especially numerical contradictions and unsourced naming), the 🔴 questions requiring the author's priority attention, and the sub-agent review disposition. If source material errors are found, ask whether to fix themincidentally, but do not change them without confirmation.

## Relationship to the Workflow

This skill is positioned after `article-workflow-section-review` and before Phase 3 (author self-read and direct editing).

Recommended sequence:

- `article-workflow-brief`: Phase 0, edit Brief
- `article-workflow-clean-sources`: Phase 0.5, oral draft cleaning
- `article-workflow-section-review`: Phase 1, section-by-section narrative review
- `article-workflow-evidence-pool`: Phase 2, fact-checking & evidence pool

Planned subsequent phases:

- Phase 3 author self-read and direct editing: no separate skill; author directly modifies `.article-workflow/00-cleaned-sources/`
- `article-workflow-ai-edit-pass`: Phase 3.5, apply confirmed suggestions as edits
- `article-workflow-global-review`: Phase 4, full-text coherence review
- `article-workflow-main-draft`: Phase 4.5, consolidate main draft
- `article-workflow-visual-plan`: Phase 4.6, illustration and visual aid planning
- `article-workflow-style-bible`: Phase 5.0, style guide
- `article-workflow-polish`: Phase 5, round-by-round polishing
- `article-workflow-final-review`: Phase 6, final refinement and reader testing