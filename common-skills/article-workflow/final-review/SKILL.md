---
name: article-workflow-final-review
description: Phase 6 of the article staged optimization workflow: Final refinement and reader testing. Use when the user asks to execute Phase 6, final review, final refinement, pre-publish check, insert illustrations, or generate `.article-workflow/06-final-review/final.md` and `.article-workflow/06-final-review/06-final-review.md` from `polished-draft.md`, `style-bible.md`, and optional visual plan assets.
priority: P2
---

# Article Workflow Final Review

This is Phase 6 of the `article-workflow-*` skill series, corresponding to "Final Refinement and Reader Testing" in the article optimization workflow overview.

Goal: Final refinement before publication — including title, opening, ending, credibility, reader experience, and illustration placement. AI performs final editorial review and inserts confirmed illustrations; the author makes the final publish decision. Do not rewrite the entire narrative arc.

## Trigger Scenarios

Use this skill when the user asks to:

- Execute Phase 6 of the article optimization workflow
- Perform final review / pre-publish check / final review
- Generate `.article-workflow/06-final-review/06-final-review.md`
- Generate `.article-workflow/06-final-review/final.md`
- Insert confirmed screenshots, diagrams, or AI images into the final draft per the visual plan

## Input and Output

Default inputs:

- `.article-workflow/brief.md`
- `.article-workflow/style-bible.md`
- `.article-workflow/05-polish-rounds/polished-draft.md`
- `.article-workflow/04.6-visual-plan/visual-plan.md` (if present)
- `.article-workflow/04.6-visual-plan/asset-manifest.md` (if present)
- `.article-workflow/04.6-visual-plan/ai-image-briefs.md` (if present and confirmed by author)
- `.article-workflow/sources/proofs/` (if present)

Default outputs go into the Phase 6 directory:

- `.article-workflow/06-final-review/06-final-review.md`
- `.article-workflow/06-final-review/final.md`: Publishable version generated after the author confirms final edits, including confirmed illustration placements

If the user provides an article directory, first look for `.article-workflow/` under that directory.

## Core Principles

- **Final refinement, not rewriting the narrative arc.** Only address the most worthwhile pre-publish issues, confirmed illustration placements, title/opening/ending/credibility checks — do not reorganize the entire structure.
- **Review first, then finalize.** By default, write `06-final-review.md` first; only write/update `final.md` when the author confirms final edits, or the user explicitly requests generating the final draft in the current round.
- **Only insert illustrations the author has confirmed or the visual plan explicitly adopts.** If the image file already exists, insert it directly; if the file hasn't been generated yet but `visual-plan.md`, `asset-manifest.md`, `imgs/outline.md`, or prompt files have explicitly defined the position and target filename, you can insert the planned path, but must list it as a pre-publish file confirmation item in the review report.
- **Apply discretion to explanatory infographics.** Don't insert every explanatory infographic just because a prompt/outline exists. Prioritize evidence screenshots and one core mechanism diagram that truly lowers the comprehension barrier; images that repeat the body text, weaken narrative pacing, or turn the article into slides should not be inserted — explain the reason.
- **Evidence images and AI images must be clearly distinguished.** Evidence screenshots retain their source attribution; AI images must be labeled as explanatory illustrations or atmosphere images, never disguised as evidence.
- **Images cannot replace body-text argumentation.** Screenshots and diagrams can only aid understanding or support facts; the body text must first make clear why the reader should look at the image.
- **Better to omit than to clutter.** If an image would interrupt reading, repeat the body text, have unclear evidential value, or lack a clear caption/alt text, don't insert it — and explain why in `06-final-review/06-final-review.md`.
- **Final quality comes from the author reading through.** AI can do final editorial review, but cannot replace the author reading the piece end to end. After generating `final.md`, you must remind the author to read the entire piece; places that read awkwardly, don't sound like the author, or feel skippable should be addressed by extracting specific paragraphs and having a focused conversation with AI for localized edits — not by reopening a large-scope process.
- When encountering ambiguities that would affect the publish decision (title direction, whether to make a screenshot public, whether AI images are allowed, whether final is publishable), proactively ask the author; if prior materials are already clear, don't force questions.
- After writing outputs, you must launch a sub-agent review; the sub-agent only provides review comments, and the main agent decides whether to adopt them.

## Workflow

### Step 1: Read the Final Draft and Visual Plan

Read:

1. `brief.md`: Confirm the article's thesis, target readers, risk posture, and ending resolution.
2. `style-bible.md`: Confirm the author's style and do-not-change boundaries.
3. `05-polish-rounds/polished-draft.md`: As the final draft baseline.
4. If `04.6-visual-plan/` exists, read `visual-plan.md`, `asset-manifest.md`, `ai-image-briefs.md`.
5. If evidence screenshots are involved, check whether the corresponding files exist in `sources/proofs/`.

### Step 2: Determine Whether to Ask the Author First

Usually you can proceed directly. Only ask first in these cases:

- `visual-plan.md` recommends images, but whether the author will use them is unclear, and illustrations would affect the final.
- Whether a screenshot can be made public is unclear.
- Whether AI images are allowed is unclear.
- Multiple mutually exclusive options exist for the title direction or final resolution.
- The user's request conflicts with Phase 6 goals, e.g., asking to rewrite the entire narrative arc.

When there are no such ambiguities, proceed directly and explain key assumptions in `06-final-review.md`.

### Step 3: Perform Final Refinement and Reader Testing

Check from the target reader's perspective:

- Does the title accurately express the article's thesis, rather than just chasing clicks?
- Does the opening draw the reader in, and does it remain the author's own way of entering?
- Is the main thread clear, with no obvious tangents or repetition?
- Do factual evidence sufficiently support key judgments?
- Do personal judgments carry weight, without being presented as unverified facts?
- Does the ending land naturally on the author's own observations, rather than generic uplift?
- Do illustrations genuinely aid understanding, rather than interrupting reading or diluting the main thread?

List only the 5 most worthwhile pre-publish issues, ranked by priority.

### Step 4: Insert Confirmed Illustrations and Evaluate Explanatory Images

Only process images that are confirmed for use, have existing files, or have clearly defined planned paths:

- Insert images near the corresponding paragraphs in `final.md`.
- Adopted images should be copied to `.article-workflow/06-final-review/imgs/`, and `06-final-review/final.md` should only reference relative paths under that directory (e.g., `imgs/example.png`), not depend on prior-stage directories as publish-draft image sources.
- Add caption, alt text, and source attribution for each image.
- Captions address the article reader, not internal workflow jargon. Avoid stiff prefixes like `<sub>`, `Caption:`, `Evidence screenshot:`; default to a natural italic sentence.
- Captions serve only lightweight explanation: what is this, and where it comes from if necessary. Complex caveats, attribution explanations, or importance rationale should go in the body text or footnotes, not crammed into captions.
- Evidence screenshots use one sentence to note the source or attribution, e.g., a tweet, receipt screenshot, GitHub page, or review output; don't write the evidence explanation like an audit report.
- AI images note "explanatory illustration" or "atmosphere image," not as factual evidence; if the context already makes this clear, describe it naturally in the caption rather than mechanically slapping on a label.
- If image files haven't been generated yet but paths are already clearly defined by the visual plan, you can insert the `imgs/...` planned path first and list it in the review report's pre-publish checklist as "generate/copy to Phase 6 image directory before publishing."
- Filter explanatory infographics by reading value: prioritize inserting the one that best explains the core mechanism; images where the body text already has code blocks, quotes, or natural narrative to accomplish the same goal should not be inserted by default.
- If an image's evidential value is unclear, would interrupt reading, or would repeat the body text, don't insert it — record the reason in `06-final-review/06-final-review.md`.

Suggested Markdown image format:

```markdown
![alt text](relative/path/to/image)

*A natural image caption. Note source or attribution when necessary; complex explanations go in body text or footnotes.*
```

### Step 5: Write `06-final-review/06-final-review.md`, Generate `06-final-review/final.md` Upon Confirmation

Recommended structure for `06-final-review/06-final-review.md`:

```markdown
# Phase 6 Final Refinement and Reader Testing

## Current Conclusion

## Top 5 Pre-Publish Issues

## Illustration Placement Check

## Explanatory Infographic Selection Decisions

## Omitted Images and Reasons

## Final Pre-Publish Checklist

## Author Final Read-Through Reminder
```

`06-final-review/final.md` (after author confirmation, or when the user explicitly requests direct generation):

- Based on `polished-draft.md` as the baseline.
- Apply author-confirmed final minor edits.
- Insert confirmed illustrations.
- Remove workflow markers, author decision slots, and internal TODOs (unless the author explicitly asks to keep them).

If the current round doesn't yet have author confirmation, don't force-generate a final publishable draft; only list the final edits and illustration placements that need confirmation in `06-final-review/06-final-review.md`.

In the "Author Final Read-Through Reminder" section of `06-final-review/06-final-review.md`, explicitly write:

- The author should ideally read through `final.md` from start to finish.
- Highlight paragraphs that read awkwardly, don't sound like the author, or that even the author would skip.
- These issues are best resolved through localized conversation: extract specific paragraphs, have AI propose 1–2 small fixes, then let the author make the call.
- Don't restart a full-text rewrite or large-scope polishing over a few localized issues.

### Step 6: Launch Sub-Agent Review

After writing outputs, the main agent must launch a read-only sub-agent review. The sub-agent focuses on checking:

- Whether `06-final-review/final.md` did not rewrite the entire narrative arc.
- Whether the title, opening, and ending align with brief and style-bible.
- Whether illustrations only use confirmed images, with reasonable placement.
- Whether captions, alt text, and source attributions are accurate.
- Whether evidence screenshots, explanatory diagrams, and AI images are clearly distinguished.
- Whether `06-final-review/06-final-review.md` only lists the most important pre-publish issues, without reopening large-scope revision.

After the main agent receives the review: judge which suggestions are valid; only adopt suggestions consistent with Phase 6 goals; if adopted, update `06-final-review/final.md` or `06-final-review/06-final-review.md`; if not adopted, briefly explain the reason.

### Step 7: Verification

After completion, check:

- Whether `.article-workflow/06-final-review/06-final-review.md` exists.
- Whether `.article-workflow/06-final-review/final.md` exists.
- Whether Phase 6 outputs are all under `.article-workflow/06-final-review/`.
- Whether `06-final-review.md` reminds the author to personally read through the entire piece, and suggests handling awkward spots as localized edits.
- Whether adopted images are copied to `.article-workflow/06-final-review/imgs/`, and `final.md` only references images under that directory.
- If `final.md` has been generated, whether it's based on `polished-draft.md` and didn't reorganize the entire text.
- If `final.md` has been generated, whether confirmed illustrations are inserted at correct positions.
- If `final.md` has been generated, whether each image has alt, caption, and source or attribution notes.
- If `final.md` has been generated, whether AI images are labeled as explanatory illustrations or atmosphere images.
- If image paths come from the plan but the actual files haven't been generated yet, whether they're listed as generate/copy confirmation items in the pre-publish checklist.
- Whether omitted images have reasons explained in `06-final-review/06-final-review.md`.
- Whether sub-agent review has been completed and the main agent has judged adoption.

## Author Decision Dialog

This phase typically doesn't need opening questions. Only use structured questions to collect decisions on ambiguities that would affect the publish decision:

- Whether to use a particular evidence screenshot.
- Whether to allow AI images in the final.
- Which title direction to choose.
- Whether to accept leaving a pre-publish issue unaddressed for now.
- Whether `final.md` can serve as the publishable version.

Don't re-ask about caption details, low-risk phrasing, or images already confirmed in the visual plan.

## Output Style

- Use English unless the user specifies otherwise.
- Final reply should only summarize: location of `06-final-review/final.md`, location of `06-final-review/06-final-review.md`, which images were inserted, which were omitted and why, and what still needs the author's decision.
- The final reply must end with a reminder to the author: before publishing, read through the entire piece yourself; wherever it reads awkwardly, doesn't sound like you, or feels skippable, extract those specific paragraphs and work with AI on localized edits.
- Do not output the full text, do not produce a verbose publish checklist.

## Relationship to the Workflow

This skill comes after `article-workflow-polish` and is the final step before article publication. It reads `polished-draft.md` and optional `04.6-visual-plan/`, and generates the final publishable `final.md`.

Recommended sequence:

- `article-workflow-brief`: Phase 0, edit Brief
- `article-workflow-clean-sources`: Phase 0.5, dictated draft cleanup
- `article-workflow-section-review`: Phase 1, section-by-section narrative review
- `article-workflow-evidence-pool`: Phase 2, fact verification and material pool
- Phase 3 author read-through and direct edits: no separate skill, author directly modifies `.article-workflow/00-cleaned-sources/`
- `article-workflow-ai-edit-pass`: Phase 3.5, apply confirmed suggestions as edits
- `article-workflow-global-review`: Phase 4, holistic coherence review
- `article-workflow-main-draft`: Phase 4.5, assemble main draft
- `article-workflow-visual-plan`: Phase 4.6, illustration and visual aid planning
- `article-workflow-style-bible`: Phase 5.0, style bible
- `article-workflow-polish`: Phase 5, round-by-round polishing
- `article-workflow-final-review`: Phase 6, final refinement and reader testing (this skill)