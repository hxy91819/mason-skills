---
name: article-workflow-ai-edit-pass
description: Article phased optimization workflow Phase 3.5: AI executes edits based on confirmed feedback. Use when the user asks to execute Phase 3.5, AI edit pass, edit based on confirmed feedback, or generate `.article-workflow/03.5-ai-edit-pass/` from `brief.md`, `00-cleaned-sources/`, `01-section-reviews/`, `02-evidence-pool/`.
priority: P2
---

# Article Workflow AI Edit Pass

This is Phase 3.5 of the `article-workflow-*` skill series, corresponding to "AI executes edits based on confirmed feedback" in the article optimization workflow.

Goal: After the author has responded to Phase 1 / Phase 2 diagnostics, or has made direct edits in the working draft, let the AI **only execute modifications explicitly confirmed by the author**, producing revised sections for the author to review and approve. AI executes; the author reviews and makes final calls. AI must not write unconfirmed new viewpoints, expand the scope of modifications, or convert an oral draft into a polished media piece.

## Trigger Scenarios

Use this skill when the user requests:

- Execute article optimization workflow Phase 3.5
- Have AI execute edits based on confirmed feedback
- Execute modifications based on author replies in `01-section-reviews/` and `02-evidence-pool/`
- Generate `.article-workflow/03.5-ai-edit-pass/`

## Input and Output

Default inputs:

- `.article-workflow/brief.md`
- `.article-workflow/00-cleaned-sources/*.md` (author's working draft; may already contain author's Phase 3 direct edits/annotations)
- `.article-workflow/01-section-reviews/` (especially `📝 Author Reply:` in `index.md` and per-section `*.review.md`)
- `.article-workflow/02-evidence-pool/` (especially factual positions confirmed by the author in `open-questions.md`)
- `.article-workflow/03-author-pass-notes.md` (if present)

Default outputs (all under `03.5-ai-edit-pass/`, **never modify** `00-cleaned-sources/`):

- `edit-plan.md`: Pre-execution modification plan listing each planned edit and its authorization source
- `revised-sources/<original-filename>.md`: Revised version per original section
- `change-log.md`: Itemized description of what was changed, mapped to which author confirmation
- `author-review-checklist.md`: Checklist for the author to review, **only listing decisions that require the author's final call**

If the user provides an article directory, first look for `.article-workflow/` under that directory.

## Core Principles

- **Only execute confirmed modifications.** Authorization sources are limited to four categories: ① Author explicitly agreed in section reviews and `index.md` `📝 Author Reply`; ② Items marked "needs author confirmation: no" in reviews, executable via default resolution path; ③ Factual position corrections the author replied to in `open-questions.md`; ④ Author's direct edits/annotations in `00-cleaned-sources/` or `03-author-pass-notes.md`.
- **Author's veto or rewrite has the highest priority.** If the author explicitly opposes, rewrites wording, or requests a different approach, follow the author's decision — do not fall back to the default path.
- **Do not write unconfirmed new viewpoints**, and do not proactively expand the modification scope. Any added transitional or supplementary sentences must be marked in `change-log.md`.
- **"Compress / reduce / streamline" ≠ "delete".** This is the most common overreach error in this phase: when a review only says "compress a paragraph," never delete the entire paragraph; when it says "reduce analogies," keep representative examples rather than zeroing them out. Any deletions beyond what the review explicitly authorized must be prominently flagged at the top of `change-log.md` for the author to decide on.
- **Preserve the author's style**: first-person perspective, judgment style, sentence rhythm, personal experiences, and judgments that must be expressed. Do not write self-referential meta-narrative like "this article shifts from… to…" and do not convert to media commentary tone or bullet-point-summary tone.
- **Ask when confirmation is missing; do not guess.** If a key modification affecting the output has no authorization (no mention in reviews / open-questions / author's direct edits), or if the authorization is vague (e.g., "compress" without specifying how much, cross-section move without specifying target section), proactively ask the author for confirmation — do not decide unilaterally or bury it in the output hoping the author notices.
- **Delegate machine-verifiable checks to sub-agents; reserve human decisions for the author.** Factual position consistency, whether only confirmed items were executed, and whether there are unauthorized deletions — these are audited by sub-agents; identity/privacy, facts only the author knows, placement preferences, and tone policing — these go into `author-review-checklist.md`.
- **Change-log must be low-noise and scannable.** Do not stack itemized logs or large tables; put "judgment calls beyond authorization" at the top, then concise per-section highlights below. The author should be able to quickly understand what changed and which items need special attention.
- After each round of output, a sub-agent audit review must be initiated; the sub-agent only provides review opinions, and the main agent decides whether to adopt them. When sub-agents are unavailable, self-check against the same priorities and note the limitation in the final reply.

## Workflow

### Step 1: Collect All Confirmed Feedback

Read all inputs and compile author-confirmed decisions into an "authorization list":

- `index.md`: `📝 Author Reply` for global decisions, and priority rules from "author reply method."
- Per-section `*.review.md`: each `📝 Author Reply`; and items marked "needs author confirmation: no" that can be executed via the default path.
- `open-questions.md`: Factual position corrections the author has replied to (figures, named links, citation sources, etc.).
- `00-cleaned-sources/` and `03-author-pass-notes.md`: Author's direct edits, strikethroughs (`~~…~~`), `# Author Annotation` / `# Author Approval` blocks. These are the highest-priority signals of author intent and must not be reverted.

When compiling, specially flag three categories:

- Modifications the author **explicitly agreed** to;
- Modifications the author **vetoed or rewrote** (follow the author's opinion, not the default path);
- Items using "compress / reduce / streamline / move later" **rather than "delete"** (must not overreach and delete entirely during execution).

### Step 2: Write `edit-plan.md`

Produce the modification plan before starting edits. `edit-plan.md` should let the author see at a glance "what will be changed and based on which confirmation." It is recommended to include:

- Execution boundary declaration (only execute confirmed items, do not write new viewpoints, preserve style).
- Author veto/rewrite comparison table (default path → author's opinion → this execution).
- Factual position correction list (from `open-questions.md`).
- Global structural modifications (from `index.md`).
- Per-section execution highlights, each with its authorization source.
- Explicitly list **items not being executed** (unconfirmed new viewpoints, major section reordering left for Phase 4/4.5, 🟢 optional items left for polishing).

### Step 3: Determine Whether to Ask the Author First

The premise of Phase 3.5 is that "confirmations already exist." Before starting, assess whether there are **ambiguities that would block the entire round of output**:

- Reviews and open-questions have almost no author replies — this means Phase 1/2 is not closed-loop; return to the previous phase rather than guessing for the author.
- The user's intent conflicts with Phase 3.5 (e.g., requesting a major viewpoint overhaul or full-text restructuring on the side).
- Ambiguities listed in the "Author Decision Dialog" below that require the author's final call and would determine the editing direction.

If there are blocking points, ask first (prefer structured questions / dialogs); see "Author Decision Dialog" for what to ask and how. If there are no blocking points, proceed directly and put the few decisions needing author approval into `author-review-checklist.md` — do not force a question for formality's sake.

### Step 4: Write `revised-sources/*.md`

Produce revised versions per section, implementing the authorization list item by item:

- Strictly follow confirmed items; for author veto/rewrite items, follow the author's opinion.
- "Compress" means compress while preserving the core; "reduce analogies" means keep representative examples; do not delete entire paragraphs.
- Content moved across sections (personal perspectives, specific examples, certain material) should be placed per the confirmed direction — deleted from the source section, received in the target section — and recorded in change-log as "moved, not deleted."
- Added transitional or supplementary sentences should be restrained, and all must be recorded in change-log.
- Preserve first-person perspective and author's judgment style throughout; do not introduce standardized frameworks.
- **Only write to `revised-sources/`; never modify `00-cleaned-sources/`.**

### Step 5: Write `change-log.md` and `author-review-checklist.md`

`change-log.md` (low-noise, scannable):

- Top "⚠️ Requires Special Attention" section: list all **deletions beyond what the review explicitly authorized** (e.g., review said compress but content was entirely deleted), and other judgment calls, marking each as handled / pending author decision.
- Per-section change summary: 3–5 short bullets per section, with authorization source (`Issue N` / `✅` / `QN` / `Author Annotation`).
- Cross-section moves: listed separately, noting content only changed position, not disappeared.
- Factual position unification, added sentences/paragraphs, unexecuted items: each compressed into a compact list.
- Do not use layered itemized logs or large tables.

`author-review-checklist.md` (only human decisions):

- Top: a one-line "auto-verified" summary (factual positions, fidelity, unauthorized deletions checked by sub-agent).
- Only list decisions requiring the author's final call, clearly typed: identity/privacy, facts only the author knows, cross-section placement preferences, tone policing, trade-off of points the author struck through but that were originally must-keep, etc.
- Each item provides one or two options, allowing "leave as is" as a quick pass.

### Step 6: Initiate Sub-Agent Audit Review

After writing output, the main agent must initiate a read-only sub-agent audit. This phase should cover at least three types of verification (can be parallelized or merged):

- **Fidelity / scope audit**: Verify each substantive change in `revised-sources/` against the authorization list — whether it can be traced to an authorization source, whether it is within `edit-plan.md`'s plan; whether any author-vetoed/rewritten items were executed; whether any unconfirmed new viewpoints were written in.
- **Factual position consistency audit**: Whether various figures (amounts, quantities, version numbers, etc.) are consistent across the full text and conform to `open-questions.md` confirmations; whether links, citation sources, and required "imperfect" points are in place.
- **Deletion authorization audit**: Compare `00-cleaned-sources/` with `revised-sources/` section by section, find deleted/heavily compressed content, and categorize as "authorized deletion," "review only said compress but was entirely deleted (overreach)," "deletion with no authorization," "only moved across sections." Focus on reporting overreach and unauthorized deletions.

After the main agent receives the review: judge which findings are valid; only adopt suggestions consistent with Phase 3.5 goals; revise `revised-sources/` accordingly and write judgment calls into the top of `change-log.md`; briefly explain reasons for not adopting. When sub-agents are unavailable, self-check against the above priorities and note the limitation.

### Step 7: Handle Author Review-Back and Iterate as Needed

The author may provide feedback in two ways, both of which must be handled:

- Directly leaving `# Author Annotation` / `# Author Approval` blocks or strikethrough content in `revised-sources/*.md` — treat as authorized edits, implement item by item, clear annotation blocks, and record in change-log.
- Replying to decisions in `author-review-checklist.md` — implement and update checklist status.

After each iteration, affected changes re-run the relevant Step 6 audits (especially the "compress ≠ delete" check when deletions are involved). Do not proceed to Phase 4 until the author explicitly approves `revised-sources/`.

### Step 8: Verification

After completion, check:

- Whether `03.5-ai-edit-pass/` contains `edit-plan.md`, `revised-sources/`, `change-log.md`, `author-review-checklist.md` in full.
- Whether `revised-sources/` covers all main-text sections and only modifies confirmed items.
- Whether no unconfirmed new viewpoints were written; whether all added sentences/paragraphs are marked in change-log.
- Whether no "compress/reduce" from reviews was executed as "delete entire paragraph"; whether overreach deletions are flagged and handled at the top of change-log.
- Whether author-vetoed/rewritten items were executed per the author's opinion.
- Whether factual positions are consistent with `open-questions.md` confirmations.
- Whether `author-review-checklist.md` only contains human decisions, with machine-verifiable items collected into a single "auto-verified" statement.
- Whether `00-cleaned-sources/`, `brief.md`, `01-section-reviews/`, `02-evidence-pool/` and other inputs were not modified.
- Whether sub-agent audit has been completed and the main agent has judged adoption.
- If the environment provides Markdown lint or editor diagnostics, check recently edited files; if no relevant diagnostics exist, do not forcibly run code lints.

## Author Decision Dialog

Most decisions in Phase 3.5 are already closed out in Phase 1/2, **so no opening dialog is needed by default.** Only proactively collect author decisions when the following situations arise:

- Key modifications lack authorization or authorization is vague ("compress" without specifying degree, cross-section move without specified destination).
- Wording involving identity / privacy (e.g., whether to disclose the author's relationship with a project party).
- Facts only the author knows (citation attribution, case origin, personal names).
- The author struck through a point originally listed as "must-keep" in `open-questions.md`, requiring confirmation whether to delete entirely or keep it in a different position.

Dialog rules:

- Only ask the few items that truly need the author's final call at one time (typically 3–8 items).
- Provide clear options for each question, allowing "leave as is / other" as an escape hatch.
- Do not re-ask information already given in reviews, open-questions, or author's direct edits.
- Do not turn low-risk details that don't block progress into questions; put these in the checklist or note assumptions in the final reply.

## Output Style

- Use English unless the user specifies otherwise.
- All four outputs are working documents — clear, concise, and actionable.
- `change-log.md` must put "judgment calls beyond authorization" at the top, then per-section highlights; low-noise and scannable.
- `author-review-checklist.md` only contains human decisions; machine-verifiable items are collected into a single "auto-verified" statement.
- The final reply only summarizes: output location, which confirmed items were executed, whether there were overreach deletions and how they were handled, which items still need the author's final call, and sub-agent audit conclusions.

## Relationship to the Workflow

This skill sits after Phase 3 (author self-review and direct editing) and before Phase 4 (full-text coherence review). Its output `revised-sources/`, after passing author review, is prioritized as input for Phase 4 / 4.5; if not approved, return to Phase 3 for direct editing.

Recommended sequence:

- `article-workflow-brief`: Phase 0, edit Brief
- `article-workflow-clean-sources`: Phase 0.5, oral draft cleanup
- `article-workflow-section-review`: Phase 1, per-section narrative review
- `article-workflow-evidence-pool`: Phase 2, fact verification and material pool
- Phase 3 author self-review and direct editing: no separate skill; author directly modifies `.article-workflow/00-cleaned-sources/`
- `article-workflow-ai-edit-pass`: Phase 3.5, execute edits based on confirmed feedback

Subsequent planned phases:

- `article-workflow-global-review`: Phase 4, full-text coherence review
- `article-workflow-main-draft`: Phase 4.5, consolidated main draft
- `article-workflow-visual-plan`: Phase 4.6, illustration and visual aid planning
- `article-workflow-style-bible`: Phase 5.0, style guide
- `article-workflow-polish`: Phase 5, round-by-round polishing
- `article-workflow-final-review`: Phase 6, final refinement and reader testing