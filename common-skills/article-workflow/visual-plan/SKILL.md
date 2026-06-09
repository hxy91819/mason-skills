---
name: article-workflow-visual-plan
description: Phase 4.6 of the article staged optimization workflow: Illustration & Visual Aid Planning. Use when the user asks to execute Phase 4.6, illustration planning, visual plan, illustration plan, or generate `.article-workflow/04.6-visual-plan/` from `brief.md`, main draft, evidence pool, and source images.
priority: P2
---

# Article Workflow Visual Plan

This is Phase 4.6 of the `article-workflow-*` skill series, corresponding to "Illustration & Visual Aid Planning" in the article optimization workflow.

Goal: After the main draft structure stabilizes, determine where the article needs illustrations, what types of images to use, whether existing materials can support them, and whether AI-generated images are needed to aid understanding. **This phase only creates plans; it does not generate images by default and does not modify the main text.**

## Trigger Scenarios

Use this skill when the user asks to:

- Execute article optimization workflow Phase 4.6
- Supplement illustration planning / visual plan / visual plan
- Inventory screenshots, evidence images, and reference images in the article materials
- Determine which positions are suitable for evidence screenshots, explanatory diagrams, mood images, or cover images
- Generate `.article-workflow/04.6-visual-plan/`
- Prepare briefs for subsequent AI image generation, but not directly generate images

## Input and Output

Default inputs:

- `.article-workflow/brief.md`
- `.article-workflow/04.5-main-draft/main-draft.md`
- `.article-workflow/05-polish-rounds/polished-draft.md` (if Phase 5 is already completed and the visual plan needs updating, prefer this)
- `.article-workflow/02-evidence-pool/evidence-pool.md`
- `.article-workflow/02-evidence-pool/fact-check.md` (if available)
- `.article-workflow/02-evidence-pool/open-questions.md` (if author image source replies exist)
- `.article-workflow/sources/proofs/`
- `.article-workflow/sources/references/`
- Other files from prior phases that mention image sources, screenshots, or evidence paths

Default outputs:

- `.article-workflow/04.6-visual-plan/asset-manifest.md`
- `.article-workflow/04.6-visual-plan/visual-plan.md`
- `.article-workflow/04.6-visual-plan/ai-image-briefs.md`

Optional follow-up outputs (only written when the user explicitly requests preparing formal prompts):

- `.article-workflow/04.6-visual-plan/prompts/*.md`
- `.article-workflow/04.6-visual-plan/prompt-summary.md` (after referencing the `article-illustrator` prompt specification, summarize prompt settings, files, captions, and insertion suggestions back into this phase)

If the user provides an article directory, first look for `.article-workflow/` under that directory.

## Core Principles

- **Only plan and write prompts; do not generate images.** This phase does not call image generation backends or ask the agent to produce images; even if the user requests "preparing formal prompts," only write prompt files and summary documents. Actual image generation should be handled as a separate follow-up task.
- **Evidence screenshots and AI images must be kept separate.** Evidence screenshots support facts; AI images can only be explanatory illustrations or mood images, and must never be disguised as evidence screenshots.
- **Do not rely solely on file globs to determine whether materials exist.** You must search through prior `sources`, `evidence-pool`, `fact-check`, `open-questions`, `revised-sources` and other text for image source annotations. In real sessions it has occurred that image file bodies were not found by glob, but prior materials had already annotated image source paths and author replies.
- **Inventory first, then plan.** First output `asset-manifest.md`, distinguishing existing image source annotations, found file bodies, files pending sync, evidence screenshots, explanatory diagrams, mood/cover images, AI generation candidates, and reference images; then write `visual-plan.md`.
- **Fewer images are better than more.** A technical opinion article typically only needs 1–3 key images: an opening factual anchor, a core mechanism explanation, and necessary on-site material or a cover. Do not turn the article into slides.
- **Every recommended image must state the reader question it addresses.** For each recommended image, clearly specify: after which paragraph to place it, what understanding problem it solves, image type, priority, whether it is required, suggested caption, and usage boundaries.
- **Do not hardcode the current article's specific visual conclusions as general rules.** For example, "bill screenshot" or "clownfish image" belong only to this article; general skills should only specify how to find and evaluate such image sources.
- **The AI image generation portion is guided by this skill to read the `article-illustrator` prompt specification; it must not copy its full content.** When preparing formal prompt files or handling reference images, read the Type x Style x Palette, prompt file, and reference rules from `../article-illustrator/SKILL.md`; do not call its image generation backend in this phase. `article-workflow-visual-plan` is responsible for collecting prompt results, organizing them, and summarizing them into `.article-workflow/04.6-visual-plan/`.
- **When encountering ambiguities that would affect progress or output quality, proactively use the structured questioning tool available at runtime to ask the user for confirmation; if prior materials and the user's current request are already clear, do not force questions for formality's sake.**
- **After writing outputs, must launch a sub-agent for review; the sub-agent only provides review opinions, and the main agent decides whether to adopt them.**

## Workflow

### Step 1: Read the Article and Phase Constraints

Read first:

1. Phase 4.6 description in the article optimization workflow overview
2. `brief.md`: confirm the article's main thread, audience, and evidence presentation discipline
3. `polished-draft.md` (preferred) or `main-draft.md`: determine illustration positions based on final reading order
4. `evidence-pool.md` / `fact-check.md` / `open-questions.md`: find evidence image sources, author replies, and factual positions
5. `sources/proofs/` and `sources/references/`: find actual images, screenshots, image source paths, and reference image descriptions

When searching, do two types of lookups simultaneously:

- File-level: image formats, proofs directory, references directory
- Text-level: `screenshot`, `image source`, `proofs/`, `.jpg`, `.jpeg`, `.png`, `image`, `asset`, specific material names, etc.

### Step 2: Determine Whether to Ask the Author First

Some author decisions in this phase will affect the final plan. If prior materials or the user's current request are already clear, do not ask again; otherwise, use the structured questioning tool available at runtime to collect key options in one pass.

Situations requiring proactive confirmation:

- It is unclear whether illustrations are needed or if the article should remain text-only.
- It is unclear whether existing evidence screenshots can be used publicly, and this would affect `visual-plan.md` recommendations.
- The factual nature of evidence screenshots and on-site materials is unclear, e.g., whether they are GitHub page screenshots, tweet screenshots, or community chat screenshots.
- It is unclear whether AI images are allowed, and the user has requested generating AI image briefs, formal prompts, or needs to define boundaries for subsequent image generation.
- The article's publishing platform has special requirements, e.g., a cover image is mandatory, or WeChat Official Account long images, Xiaohongshu cards, or social media landscape images are needed.
- Multiple style directions would significantly change subsequent prompts or image output, e.g., blueprint technical style, hand-drawn knowledge cards, editorial covers.

Situations not requiring proactive confirmation:

- The user only asked to "supplement the visual plan" and did not request immediate image generation.
- Prior materials have already annotated image source paths; just note in the output "confirm files are synced/publicly usable before publication."
- It is only a judgment that certain positions do not need illustrations.

### Step 3: Write `asset-manifest.md`

`asset-manifest.md` answers: what existing materials are there, what is their nature, what is their current status, and can they go into the main text.

Recommended structure:

```markdown
# Asset Manifest

## Current Conclusions

## Materials with Existing Image Source Annotations
### 1. <Material Name>
- Main text position
- Image source path
- Where the image source annotation comes from
- Current status: File found / Has image source annotation but needs sync / Pending
- Image type: Evidence screenshot / On-site material / Explanatory diagram / Mood image / Cover image / AI generation candidate / Reference image
- Priority
- Usage
- Usage boundaries
- Suggested caption

## Visual Materials Convertible from Text

## Content Not Recommended as Images
```

Material statuses must be precisely distinguished:

- **File found**: The image file exists locally.
- **Has image source annotation**: Prior materials have paths, author replies, or evidence pool records, but the current tool has not found the file body.
- **Pending**: Only exists as a description in the main text or verbal mention, with no path, author reply, or evidence pool support.
- **Not recommended for use**: Would interfere with reading, duplicate the main text, has insufficient factual attribution, or carries excessive risk.

Image types must also be precisely distinguished:

- **Evidence screenshot**: Bills, tweets, GitHub pages, review outputs, etc., used to support facts.
- **On-site material**: Author observations or community discussion scenes, primarily providing context and impact, not independently proving system mechanisms.
- **Explanatory diagram**: Flows, layers, lanes, decision boundaries, etc., used to aid understanding.
- **Mood image / Cover image**: Used to attract readership or establish thematic atmosphere, not bearing factual proof responsibility.
- **AI generation candidate**: Can later be generated by AI as explanatory illustrations or mood images; must be clearly marked as non-evidence.
- **Reference image**: Only provides style, composition, or color palette references; cannot be used directly as main text evidence.

### Step 4: Write `visual-plan.md`

`visual-plan.md` proposes illustration recommendations in final draft reading order.

Must include:

- Overall recommendation: how many images are suggested, the maximum, and a rationale if no images are recommended.
- Recommended illustration order: one subsection per image.
- Optional illustrations: state trigger conditions; do not include by default.
- Positions where illustrations are not recommended: explain why.
- Author confirmation checklist or pre-publication processing checklist.

Each image must specify:

- Placement: after which paragraph or in which subsection
- Image type: Evidence screenshot / Explanatory diagram / Mood image / Cover image
- Priority: P0 / P1 / P2 / P3
- Whether required
- Reader question addressed
- Current material status
- Source annotation (if any)
- Pre-publication processing
- Suggested caption
- Usage notes

Priority guidelines:

- **P0**: Article factual hook or key evidence; absence would weaken credibility.
- **P1**: Significantly helps understanding of core mechanisms or key turning points.
- **P2**: Helps dissemination or summarization, but does not affect understanding.
- **P3**: Only use when the platform requires it, e.g., cover mood image.

### Step 5: Write `ai-image-briefs.md`

`ai-image-briefs.md` only serves subsequent AI image generation; it does not directly generate images.

Must first state usage boundaries:

- AI images must be labeled as explanatory illustrations or mood images.
- Do not generate forged bills, tweets, GitHub pages, terminal output, or product UI.
- Do not include fake interfaces of real brands.
- Cannot bear factual proof responsibility.

AI image generation prompt methodology:

- If only writing briefs: this skill can directly organize them using the Type x Style x Palette structure.
- If preparing formal prompt files or handling reference images: must read and follow the prompt-related rules in `../article-illustrator/SKILL.md`, treating it as the prompt construction sub-process for Phase 4.6.
- Do not copy the full rules from `article-illustrator`; only reference it as the authoritative process for prompt construction, to avoid diverging into two sets of rules.
- This phase does not select an image backend, does not call image generation tools, and does not generate images. The parts of `article-illustrator` about calling backends are skipped in this phase.
- Prompt output must not be left scattered; after writing prompts, must write back / summarize into this phase's outputs, at minimum updating `asset-manifest.md`, `visual-plan.md`, `ai-image-briefs.md`, and `prompt-summary.md`.

Recommended structure:

```markdown
# AI Image Briefs

## Usage Boundaries

## Generation Process Suggestions
- Density
- Primary preset
- Alternative preset
- Language
- Palette

## Brief 1: <Image Name>
- Usage
- Recommended placement
- Priority
- Type
- Style
- Palette
- Suggested prompt file
- Suggested output file
- Target reader question

  Prompt brief:
  > LAYOUT / ZONES / CONNECTIONS / LABELS / STYLE / ASPECT

  Suggested caption:

  Acceptance criteria:

## Images Not Recommended for Generation

## Prompt File Template
```

Recommend using the `article-illustrator` three-dimensional classification:

- **Type**: `infographic`, `scene`, `flowchart`, `comparison`, `framework`, `timeline`
- **Style**: e.g., `blueprint`, `vector-illustration`, `sketch-notes`, `ink-notes`, `editorial`
- **Palette**: e.g., technical/blueprint, macaron, mono-ink, warm; avoid neon, cyber, or humanoid robots unless the article itself requires them

If subsequently generating formal prompt files:

- One independent prompt file per image, recommended to be placed in `.article-workflow/04.6-visual-plan/prompts/`
- Do not write non-existent files in the `references` frontmatter
- Prompts must contain real terminology, numbers, or key sentences from the article, but must not forge evidence screenshots
- Before writing prompts, follow the `article-illustrator` confirmation strategy; after confirmation, only write prompts, do not proceed to generate images

### Step 5.5: Reference `article-illustrator` to Generate Prompts and Collect Results as Needed

Only enter this step when the user explicitly requests "prepare formal prompts / generate prompt files / use article-illustrator to organize image prompts." If the user requests "generate images," first remind them that this phase defaults to only producing prompts; whether to proceed with actual image generation should be confirmed as a separate follow-up task.

Prompt sub-process rules:

1. First read `../article-illustrator/SKILL.md`, treating it as the authoritative process for prompt construction and Type x Style x Palette.
2. Convert P1/P2 explanatory image candidates from `visual-plan.md` into Type x Style x Palette inputs for `article-illustrator`.
3. Respect the `article-illustrator` confirmation strategy: unless the user explicitly says "no confirmation needed / write prompts with defaults," first let the user confirm density, style, palette, and whether a cover prompt is needed.
4. Fix prompt file output location to `.article-workflow/04.6-visual-plan/prompts/`, avoiding scattering into the main text directory or external temporary directories.
5. Do not call any image backend, do not write `images/` outputs, do not generate evidence screenshot substitutes; bills, tweets, GitHub pages, and review outputs can only use real screenshots or links.

After the prompt sub-process completes, must collect results:

- Update `asset-manifest.md`:
  - List the image corresponding to the prompt as an "AI generation candidate"
  - Clearly state the prompt file path, usage, whether subsequent generation is recommended, and that it is not factual evidence
- Update `visual-plan.md`:
  - Change the corresponding image's current status from "recommended to create" to "prompt prepared / AI generation candidate"
  - Add prompt file path, suggested insertion position, caption, and follow-up image generation checks
- Update `ai-image-briefs.md`:
  - Retain original briefs
  - Link to actual prompt files
  - If Type / Style / Palette were changed during prompt writing, record the changes
- Create or update `prompt-summary.md`:
  - Prompt settings: density, type, style, palette
  - Prompt list: prompt file, usage, suggested insertion position, suggested caption for each image
  - Prompts not written / reason for skipping: e.g., evidence images cannot be AI-generated, cover not needed at this time
  - Follow-up image generation todos: e.g., confirm backend, generate images, compress images, copy to publish directory, check text readability in images

Recommended structure for `prompt-summary.md`:

```markdown
# Prompt Summary

## Prompt Settings

## Prepared Prompts
| Image | Type | Prompt File | Suggested Insertion Position | Suggested Caption | Evidence Attribute |

## Skipped or Not Prepared

## Write-back Status
- asset-manifest.md: Updated / Not updated (reason)
- visual-plan.md: Updated / Not updated (reason)
- ai-image-briefs.md: Updated / Not updated (reason)

## Follow-up Image Generation Todos
```

### Step 6: Launch Sub-Agent for Review

After writing outputs, the main agent must launch a read-only sub-agent for goal alignment review. If `article-illustrator` was referenced to generate prompts, the review must also check whether prompt results have been collected back into this phase's outputs.

The sub-agent only provides review opinions, focusing on:

- Whether it aligns with Phase 4.6: only planning, no default image generation, no main text modification.
- Whether `sources/proofs/`, `sources/references/`, and image source annotations in prior texts have been fully inventoried.
- Whether evidence screenshots, on-site materials, explanatory illustrations, mood images, and AI images are correctly distinguished.
- Whether any image sources already annotated in prior `evidence-pool`, `fact-check`, or `open-questions` have been missed.
- Whether each recommended image specifies placement, reader question, type, priority, whether required, caption, and usage boundaries.
- Whether `ai-image-briefs.md` clearly states that AI images cannot be disguised as evidence.
- Whether the AI image generation prompt portion correctly references the `article-illustrator` prompt rules rather than copying excessive external skill content or bypassing its confirmation / prompt file rules.
- If `article-illustrator` was referenced for prompt generation: whether outlines / prompts have been written back to `asset-manifest.md`, `visual-plan.md`, `ai-image-briefs.md`, and `prompt-summary.md`.
- Whether an image backend was called in Phase 4.6 or the agent was asked to directly generate images.
- Whether the user was forced to confirm low-risk details, or whether key confirmations affecting public use, image type, or AI image boundaries were missed.
- Whether article-specific image sources have been hard-coded as general rules.

After the main agent receives the review:

- Independently judge which opinions are valid.
- Only adopt suggestions that improve Phase 4.6 output quality and reusability.
- If adopted, update the outputs.
- If not adopted, briefly state the reason in the final reply.

### Step 7: Verification

After completion, check:

- Whether `.article-workflow/04.6-visual-plan/` was created.
- Whether it contains `asset-manifest.md`, `visual-plan.md`, `ai-image-briefs.md`.
- Whether `asset-manifest.md` distinguishes "File found / Has image source annotation / Pending / Not recommended for use."
- Whether `visual-plan.md` proposes illustration positions in article order, and specifies the reader question and priority for each image.
- Whether `ai-image-briefs.md` only writes briefs and does not generate images by default.
- Whether AI images are clearly labeled as explanatory illustrations or mood images, not substitutes for evidence screenshots.
- Whether reading the `article-illustrator` prompt rules is required when formal prompts are needed.
- If `article-illustrator` was referenced, whether `prompt-summary.md` was generated or updated, and whether the final state of prompts was written back to the three core outputs of this phase.
- Whether no images were generated and no image generation backend was called.
- Whether a sub-agent review was completed, and the main agent judged adoption.
- If the environment provides Markdown lint or editor diagnostics, check recently edited files; if no relevant diagnostics exist, do not force-run code tests.

## Author Decision Dialog

This phase does not necessarily require opening questions. If materials and the user's request are already clear, proceed directly and state key assumptions in the final reply.

If there are ambiguities that would affect output direction, boundaries, facts, style, or inputs to subsequent phases, use the structured questioning tool available at runtime to collect key decisions in one pass. Suggested questions:

- **Illustration density**: Keep text-only / Restrained illustration (1–3 images, recommended) / Illustrate every section / Cover image only.
- **Evidence image public-use boundaries**: Can publish original images / Need to redact sensitive information / Keep only links or footnotes / Do not use for now.
- **AI image boundaries**: No AI images allowed / Only explanatory diagrams allowed / Cover mood images allowed / Need to review prompts first before deciding.
- **Visual style**: Technical blueprint / Hand-drawn knowledge cards / Editorial cover / Follow existing reference images / Other.
- **Publishing platform**: Standard Markdown / WeChat Official Account / Social media cards / Xiaohongshu / Other.

Do not ask about:

- Whether image sources already clearly identified in prior materials exist.
- Low-risk caption wording details that do not affect planning.
- Pixel dimensions that can only be decided during actual layout.

## Output Style

- Use English unless the user specifies otherwise.
- Outputs are planning documents, not promotional copy.
- Judgments should be restrained: few images, many images, or no images are all acceptable, but the rationale along the reading path must be stated.
- Maintain boundary awareness with AI images; do not use descriptions like "stunning" or "maximum futuristic feel" that would undermine the article's seriousness, unless the article itself calls for it.
- The final reply should only summarize: output locations, recommended number of images, key evidence image status, whether AI briefs have been prepared, and sub-agent review conclusions.

## Relationship to the Workflow

This skill is positioned after Phase 4.5 (main draft integration) and before Phase 5.0 style bible and Phase 5 polish rounds: as long as `main-draft.md` is stable, the visual plan can be done first. If Phase 5 is already completed, `polished-draft.md` can also be used to re-run or update the plan based on the final reading order. It does not modify the main text; it only prepares plans for pre-publication image-text layout, evidence presentation, and AI explanatory images.

Recommended sequence:

- `article-workflow-brief`: Phase 0, edit Brief
- `article-workflow-clean-sources`: Phase 0.5, dictated draft cleanup
- `article-workflow-section-review`: Phase 1, section-by-section narrative review
- `article-workflow-evidence-pool`: Phase 2, fact-checking and material pool
- Phase 3 author self-read and direct edits: no separate skill; the author directly modifies `.article-workflow/00-cleaned-sources/`
- `article-workflow-ai-edit-pass`: Phase 3.5, execute confirmed edits
- `article-workflow-global-review`: Phase 4, holistic coherence review
- `article-workflow-main-draft`: Phase 4.5, main draft integration
- `article-workflow-visual-plan`: Phase 4.6, illustration & visual aid planning (this skill)
- `article-workflow-style-bible`: Phase 5.0, style bible
- `article-workflow-polish`: Phase 5, round-by-round polish
- `article-workflow-final-review`: Phase 6, final refinement and reader testing