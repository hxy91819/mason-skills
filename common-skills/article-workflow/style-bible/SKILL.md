---
name: article-workflow-style-bible
description: Article phased optimization workflow Phase 5.0: Distill a style bible from the main draft and the author's existing judgments, serving as the constraint baseline for subsequent polish rounds. Use when the user asks to create a style bible, generate a style bible, style fingerprint, Phase 5.0, or generate `.article-workflow/style-bible.md` from `.article-workflow/04.5-main-draft/main-draft.md` and `.article-workflow/brief.md`.
priority: P2
---

# Article Workflow Style Bible

This is Phase 5.0 of the `article-workflow-*` skill series.

Goal: Before entering multi-round polishing, distill a style bible from the main draft and Brief that describes the writing fingerprint the author wants to preserve. The AI does the distillation and organization; the author confirms and corrects. Every subsequent Phase 5 polish round must read it as a constraint baseline.

## Trigger Scenarios

Use this skill when the user requests:

- Execute the preliminary step of Phase 5 of the article optimization workflow
- Generate a style bible / style fingerprint
- Prepare a constraint document for multi-round polishing
- Extract writing style from the main draft and organize it into citable rules
- Generate `.article-workflow/style-bible.md`

## Input and Output

Default input:

- `.article-workflow/04.5-main-draft/main-draft.md` (the main draft after Phase 4.5 integration, for observing the author's actual writing fingerprint)
- `.article-workflow/brief.md` (Phase 0 editorial Brief, to cross-reference confirmed direction, attitude, and author judgments)
- Optional: `.article-workflow/sources/oral-draft/` (to sense the original spoken style)
- Optional: `.article-workflow/00-cleaned-sources/terminology-notes.md` (confirmed proper noun conventions)

Default output:

- `.article-workflow/style-bible.md`

If a previous project already has `.article-workflow/05-polish-rounds/style-bible.md`, read it for reference, but write the new artifact to the root-level `.article-workflow/style-bible.md` by default, to avoid confusion with Phase 5 round artifacts.

## Core Principles

- Extract patterns from real text; do not invent definitions. Every "author characteristic" must be traceable to a corresponding passage in the main draft.
- Do not treat "general standards of good writing" as style: distinguish between "good Chinese" and "this author's Chinese."
- Positive descriptions (what to preserve) and negative lists (what to forbid) are equally important. Negative lists often have stronger binding force on subsequent agents.
- Proper nouns, terminology, and formatting conventions must be precise enough for mechanical checking.
- No-change zones must cover: rhetorical-question progression, short-sentence judgments, colloquial connectors, turning-point rhythms, and personal reflections in closing paragraphs — these are the tone carriers most easily deleted by mistake during polishing.
- Clearly distinguish "trimmable" from "untouchable": list trimmable content types as well, to prevent subsequent polishing from going to either extreme (change nothing vs. change everything).
- When encountering ambiguities that would affect the overall polishing direction (e.g., whether a class of tone words belongs to the author's voice or is redundant, whether the author intentionally uses a certain type of expression), proactively use `AskQuestion` to ask the author to confirm; if the main draft's characteristics are clear and ambiguities are few, do not force questions just for form's sake.
- After the artifact is written, a sub-agent review must be launched; the sub-agent only provides review opinions, and the main agent decides whether to adopt them.

## Workflow

### Step 1: Read Source Materials

Read:

1. `04.5-main-draft/main-draft.md` — Scan paragraph by paragraph for the author's narrative stance, sentence rhythm, word choice, transition methods, and judgment habits
2. `brief.md` — Cross-reference the confirmed narrative attitude, audience, technical detail ratio, and author judgments to preserve
3. If `terminology-notes.md` exists, extract the confirmed proper noun table; if only the legacy file `_cleaning-notes-terminology.md` exists, read it for compatibility but do not write the old filename into the new artifact
4. If oral drafts exist, skim them to sense the original tone, but do not treat them as primary evidence

### Step 2: Form Internal Diagnosis

Extract the following dimensions from the main draft:

**Narrative Stance**:
- First-person appearance frequency and position (opening, mid-section, personal closing paragraphs?)
- Whether it shows a three-step rhythm of doubt → turning point → judgment
- Observer tone or participant tone

**Structural Habits**:
- Whether it uses "firstly/secondly/lastly" or numbered headings
- Section transition methods: rhetorical-question progression? contrastive progression? incremental progression?
- Whether subsection headings are phrasal or interrogative

**Language Texture**:
- Degree of colloquialism (density and function of words like "geshi", "to put it bluntly", "actually" etc.)
- Whether it uses short sentences at key positions as judgment anchors
- Whether technical terms are paired with plain-language explanations
- Chinese-English mixed-layout conventions

**Formatting**:
- Chinese-English spacing conventions
- Whether proper noun writing has a unified pattern (inherited from `terminology-notes.md`)
- Punctuation choices (full-width/half-width, dash style)
- Blockquote/code block usage conventions

**Negative List**:
- Tones the main draft has successfully avoided (media commentary tone, consulting report tone, AI summary tone, etc.)
- Differentiation features from "standard technical articles"

### Step 3: Determine Whether to Ask the Author First

In most cases at this stage, you can generate directly — the main draft itself is the best evidence. However, the following situations require confirmation first:

- The attribution judgment of certain expressions (e.g., "geshi", "to put it bluntly", "actually", "indeed") is ambiguous: are they author tone or redundant words? If not clarified first, subsequent polishing will delete or retain them by mistake
- Paragraphs with inconsistent style appear in the main draft (e.g., a section suddenly shifts to a report tone), which may be leftovers from the integration phase and need intent confirmation
- The user's "preserve personal style" in the Brief contradicts the actual characteristics of the main draft and needs clarification
- Unresolved uncertain items in the terminology table (e.g., "uncertain items" in `terminology-notes.md`)

If there are no such ambiguities, generate directly without forcing questions. If confirmation is needed, use `AskQuestion` for structured questions, collecting only a few key decisions at a time.

### Step 4: Write the Style Bible

Write to `.article-workflow/style-bible.md`.

Recommended section structure:

```markdown
# Style Bible

## 1. Narrative Stance
### 1.1 First-Person Experiential Sense
### 1.2 Three-Step Rhythm of Doubt, Turning Point, and Judgment

## 2. Structural Habits
### 2.1 Avoid Three-Point Summaries and Numbered Frameworks
### 2.2 Use Natural Connections for Section Transitions

## 3. Language Texture
### 3.1 Colloquial but Not Internet-Slangy
### 3.2 Short-Sentence Judgments
### 3.3 Parallel Presentation of Technical Terms and Chinese Explanations

## 4. No-Change Zones
### 4.1 Tone Structures That Must Not Be Rewritten
### 4.2 Content Types That May Be Trimmed but Not Expanded

## 5. Formatting Conventions
### 5.1 Chinese-English Spacing
### 5.2 Proper Noun Unification (Tabular Format)
### 5.3 Punctuation
### 5.4 Code/Blockquote Usage

## 6. Tones That Must Not Appear (Negative List)

## 7. General Polishing Principles
```

Each section must:
- Have specific example sentences from the main draft as evidence, not abstract descriptions
- Have clear binary rules of "allowed" and "not allowed"
- The negative list must use complete counterexample sentences for demonstration

The proper noun table must cover at minimum: project names, core bot names, tool names, personal names, term capitalization, and all other entities appearing in the main draft.

### Step 5: Launch Sub-Agent Review

After the artifact is written, the main agent must launch a read-only sub-agent review. The sub-agent only provides review opinions, focusing on:

- Whether each item in the style bible can find corresponding evidence in the main draft (not invented)
- Whether the no-change zones cover the tone features most easily deleted by mistake during polishing (rhetorical-question progression, short-sentence judgments, colloquial connectors, turning-point rhythms, personal closing paragraphs)
- Whether the negative list is specific (providing complete counterexample sentences) and whether there are omitted forbidden tones
- Whether the proper noun table is complete (covering all entities in the main draft)
- Whether formatting conventions are mechanically executable (not vague suggestions)
- Whether any clearly observable style features from the main draft are missing
- Whether preferences the author has not confirmed have been forced in

After the main agent receives the review:
- Judge for itself which opinions are valid
- Only adopt suggestions that improve the accuracy and operability of the style bible
- If adopted, update `style-bible.md`
- If not adopted, briefly explain the reasons in the final response

### Step 6: Verification

After completion, check:

- Whether the artifact exists at `.article-workflow/style-bible.md`
- Whether each style description can find corresponding evidence in the main draft
- Whether no-change zones fully cover rhetorical-question progression, short-sentence judgments, colloquial connectors, turning-point rhythms, and personal reflections in closing paragraphs
- Whether the negative list provides specific counterexamples
- Whether the proper noun table covers all entities in the main draft
- Whether formatting conventions are mechanically checkable
- Whether general writing advice has been written in as style
- Whether preferences the author has not confirmed have been forced in
- Whether sub-agent review has been completed and the main agent has judged adoption

## Output Style

- Use English unless the user specifies otherwise.
- The style bible itself should be concise, executable, and directly citable as constraint parameters by subsequent agents.
- Minimize "suggest" and "recommend"; favor "allow," "forbid," "change/don't change" — polishing agents need clear boundaries.
- Every counterexample must be a complete sentence that is immediately recognizable as something that should not appear.

## Relationship to the Workflow

This skill is Phase 5.0, executed after Phase 4.6 (Illustration and Visual Aid Planning, optional) and before Phase 5.1. Its artifact `.article-workflow/style-bible.md` is a required input for `article-workflow-polish` (Phase 5 multi-round polishing).

Relationship to the main draft: The style bible describes "the style of this article," not "a universal style for all articles." It must be regenerated or reconfirmed for the current article each time Phase 5 is executed — it cannot be simply reused from a previous article's style bible.

Recommended sequence:

- `article-workflow-brief`: Phase 0, Editorial Brief
- `article-workflow-clean-sources`: Phase 0.5, Oral Draft Cleaning
- `article-workflow-section-review`: Phase 1, Section-by-Section Narrative Review
- `article-workflow-evidence-pool`: Phase 2, Fact Verification and Material Pool
- Phase 3 Author Self-Read and Direct Editing: no separate skill; the author directly modifies `.article-workflow/00-cleaned-sources/`
- `article-workflow-ai-edit-pass`: Phase 3.5, Assisted Editing per Confirmed Opinions
- `article-workflow-global-review`: Phase 4, Holistic Coherence Review
- `article-workflow-main-draft`: Phase 4.5, Integrate Main Draft
- `article-workflow-visual-plan`: Phase 4.6, Illustration and Visual Aid Planning
- `article-workflow-style-bible`: Phase 5.0, Style Bible (this skill)
- `article-workflow-polish`: Phase 5, Multi-Round Polishing
- `article-workflow-final-review`: Phase 6, Final Refinement and Reader Testing