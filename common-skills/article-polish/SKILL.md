---
name: article-polish
description: Polishes and improves article writing with three modes - quick (direct polish), normal (analyze then polish), and refined (analyze, polish, review, finalize). Supports custom style preferences, target audience tuning, and writing goals via EXTEND.md. Use when the user asks to polish, rewrite, improve, condense, expand, or refine articles and writing.
version: 1.2.0
metadata:
  openclaw:
    homepage: https://github.com/JimLiu/baoyu-skills/tree/main/skills/baoyu-translate
    requires:
      anyBins:
        - bun
        - npx
---

# Article Polish

Three-mode writing improvement skill: **quick** for direct polishing, **normal** for analysis-informed improvement, **refined** for full publication-quality workflow with review and finalization.

## User Input Tools

When this skill prompts the user, follow this tool-selection rule (priority order):

1. **Prefer built-in user-input tools** exposed by the current agent runtime — e.g., `AskUserQuestion`, `request_user_input`, `clarify`, `ask_user`, or any equivalent.
2. **Fallback**: if no such tool exists, emit a numbered plain-text message and ask the user to reply with the chosen number/answer for each question.
3. **Batching**: if the tool supports multiple questions per call, combine all applicable questions into a single call; if only single-question, ask them one at a time in priority order.

Concrete `AskUserQuestion` references below are examples — substitute the local equivalent in other runtimes.

## Script Directory

Scripts in `scripts/` subdirectory. `{baseDir}` = this SKILL.md's directory path. Resolve `${BUN_X}` runtime: if `bun` installed → `bun`; if `npx` available → `npx -y bun`; else suggest installing bun. Replace `{baseDir}` and `${BUN_X}` with actual values.

| Script | Purpose |
|--------|---------|
| `scripts/main.ts` | CLI entry point. Default action splits markdown into chunks; also supports explicit `chunk` subcommand |
| `scripts/chunk.ts` | Markdown chunking implementation used by `main.ts` and kept compatible for direct invocation |

## Preferences (EXTEND.md)

Check EXTEND.md in priority order — the first one found wins:

| Priority | Path | Scope |
|----------|------|-------|
| 1 | `.mason-skills/article-polish/EXTEND.md` | Project |
| 2 | `${XDG_CONFIG_HOME:-$HOME/.config}/mason-skills/article-polish/EXTEND.md` | XDG |
| 3 | `$HOME/.mason-skills/article-polish/EXTEND.md` | User home |

| Result | Action |
|--------|--------|
| Found | Read, parse, apply. On first use in session, briefly remind: "Using preferences from [path]. You can edit EXTEND.md to customize style, audience, etc." |
| Not found | **MUST** run first-time setup (see below) — do NOT silently use defaults |

**EXTEND.md supports**: default mode, target audience, style preference, polish goal, chunk settings, custom rules.

Schema: [references/config/extend-schema.md](references/config/extend-schema.md).

### First-Time Setup (BLOCKING)

**CRITICAL**: When EXTEND.md is not found, you **MUST** run the first-time setup before ANY polishing. This is a **BLOCKING** operation.

Full reference: [references/config/first-time-setup.md](references/config/first-time-setup.md)

Use `AskUserQuestion` with all questions (mode, audience, style, goal, save location) in ONE call. After user answers, create EXTEND.md at the chosen location, confirm "Preferences saved to [path]", then continue.

## Defaults

All configurable values in one place. EXTEND.md overrides these; CLI flags override EXTEND.md.

| Setting | Default | EXTEND.md key | CLI flag | Description |
|---------|---------|---------------|----------|-------------|
| Mode | `normal` | `default_mode` | `--mode` | Polish mode |
| Audience | `general` | `audience` | `--audience` | Target reader profile |
| Style | `natural` | `style` | `--style` | Writing style preference |
| Goal | `improve` | `goal` | `--goal` | Primary polish goal |
| Chunk threshold | `4000` | `chunk_threshold` | — | Word count to trigger chunked polish |
| Chunk max words | `5000` | `chunk_max_words` | — | Max words per chunk |

## Modes

| Mode | Flag | Steps | When to Use |
|------|------|-------|-------------|
| Quick | `--mode quick` | Polish | Short texts, quick fixes, informal content |
| Normal | `--mode normal` (default) | Analyze → Polish | Articles, blog posts, general improvement |
| Refined | `--mode refined` | Analyze → Polish → Review → Finalize | Publication-quality, important documents |

**Default mode**: Normal (can be overridden in EXTEND.md `default_mode` setting).

**Style presets** — control the voice and tone of the polished output:

| Value | Description | Effect |
|-------|-------------|--------|
| `natural` | Smooth, natural flow (default) | Fixes awkward phrasing while preserving author's voice |
| `concise` | Brief and to the point | Removes redundancy, tightens sentences |
| `vivid` | Lively and engaging | Adds sensory details, strong verbs, vivid imagery |
| `formal` | Professional and structured | Elevates register, removes colloquialisms |
| `conversational` | Casual and approachable | Friendly tone, as if speaking to reader |
| `academic` | Scholarly and rigorous | Formal register, precise terminology |
| `storytelling` | Narrative-driven | Smooth transitions, engaging pacing |
| `elegant` | Refined and polished | Careful word choices, rhythmic prose |
| `chinese` | Anti-AI Chinese prose (opt-in) | Strips AI fingerprints from Chinese writing; auto-picks a 直接型/分析型 benchmark by genre. Only when explicitly selected |

Custom style descriptions are also accepted, e.g., `--style "poetic and contemplative"`.

**Chinese module (`style: chinese`)**: A dedicated rule set for Chinese prose that removes the four-layer AI fingerprints (思维模式 / 句式 / 词汇 / 结构). See [Chinese Anti-AI Module](#chinese-anti-ai-module) below.

**Auto-detection**:
- "quick polish", "quick", "fast polish" → quick mode
- "refined", "refine", "publication quality", "full polish" → refined mode
- Otherwise → default mode (normal)
- **Chinese content**: the default style (`natural`, etc.) preserves the author's voice and is **not** overridden for Chinese. The `chinese` style is **opt-in** — only apply it when the user explicitly selects it (`--style chinese`, EXTEND.md, or a request like "去 AI 味" / "anti-AI"). If the source is predominantly Chinese and no Chinese-specific intent is expressed, you may surface a one-line suggestion ("This is Chinese prose — reply `chinese` to apply the anti-AI Chinese style") but do not switch automatically.

**Upgrade prompt**: After normal mode completes, display:
> Polish complete. To further review and refine, reply "refine" or "continue refining".

If user responds, continue with review → finalize steps (same as refined mode Steps 4-6 in refined-workflow.md) on the existing output.

**Polish goals** — what aspect to focus on during polishing:

| Value | Description | Effect |
|-------|-------------|--------|
| `improve` | General improvement (default) | Fix awkward phrasing, improve clarity, enhance flow |
| `simplify` | Make it easier to read | Reduce complexity, shorter sentences, clearer structure |
| `strengthen` | Make it more impactful | Stronger verbs, clearer arguments, better pacing |
| `condense` | Reduce word count | Remove fluff, tighten expression, keep only essentials |
| `expand` | Add depth and detail | Elaborate on key points, add examples, enrich content |
| `rewrite` | Significant reworking | Restructure sentences and paragraphs for better effect |

Custom goal descriptions are also accepted, e.g., `--goal "more persuasive and energetic"`.

**Audience presets**:

| Value | Description | Effect |
|-------|-------------|--------|
| `general` | General readers (default) | Plain language, explain specialized terms |
| `technical` | Developers / engineers | Keep technical terms, explain only domain-specific jargon |
| `academic` | Researchers / scholars | Formal register, assume domain knowledge |
| `business` | Business professionals | Results-focused, action-oriented language |
| `beginner` | Novice readers | Simple vocabulary, clear explanations, patient tone |
| `expert` | Domain experts | Dense information, minimal explanation, precise terms |

Custom audience descriptions are also accepted, e.g., `--audience "startup founders interested in AI"`.

## Workflow

### Step 1: Load Preferences

1.1 Check EXTEND.md (see Preferences section above)

1.2 Apply settings: mode, audience, style, goal

### Step 2: Materialize Source & Create Output Directory

Materialize source (file as-is, inline text/URL → save to `polish/{slug}.md`), then create output directory: `{source-dir}/{source-basename}-polished/`.

Full details: [references/workflow-mechanics.md](references/workflow-mechanics.md)

**Output directory contents** (all intermediate and final files go here):

| File | Mode | Description |
|------|------|-------------|
| `polished.md` | All | Final polished version (always this name) |
| `01-analysis.md` | Normal, Refined | Content analysis (structure, tone, issues) |
| `02-prompt.md` | Normal, Refined | Assembled polish prompt |
| `03-draft.md` | Refined | Initial polished draft before review |
| `04-critique.md` | Refined | Critical review findings (diagnosis only) |
| `05-revision.md` | Refined | Revised version based on critique |
| `chunks/` | Chunked | Source chunks + polished chunks |

### Step 3: Assess Content Length

Quick mode does not chunk — polish directly regardless of length. Before polishing, estimate word count. If content exceeds chunk threshold (default 4000 words), proactively warn: "This article is ~{N} words. Quick mode polishes in one pass without chunking — for long content, `--mode normal` produces better results with consistent quality." Then proceed if user doesn't switch.

For normal and refined modes:

| Content | Action |
|---------|--------|
| < chunk threshold | Polish as single unit |
| >= chunk threshold | Chunk polish (see Step 3.1) |

**3.1 Long Content Preparation** (normal/refined modes, >= chunk threshold only)

Before polishing chunks:

1. **Analyze structure**: Scan entire document for structure, recurring themes, writing patterns
2. **Build session context**: Establish consistent style, tone, and audience-targeting guidelines
3. **Split into chunks**: Use `${BUN_X} {baseDir}/scripts/main.ts <file> [--max-words <chunk_max_words>] [--output-dir <output-dir>]`
   - Parses markdown blocks (headings, paragraphs, lists, code blocks, tables, etc.)
   - Splits at markdown block boundaries to preserve structure
   - If a single block exceeds the threshold, falls back to line splitting, then word splitting
4. **Assemble polish prompt**:
   - Main agent reads `01-analysis.md` (if exists) and assembles shared context using Part 1 of [references/subagent-prompt-template.md](references/subagent-prompt-template.md) — inlining: target style, goal, audience, content background, and polish challenges
   - Save as `02-prompt.md` in the output directory (shared context only, no task instructions)
5. **Draft polish via subagents** (if Agent tool available):
   - Spawn one subagent **per chunk**, all in parallel (Part 2 of the template)
   - Each subagent reads `02-prompt.md` for shared context, receives chunk position info (chunk N of M + brief context of where it sits in the argument), polishes its chunk, saves to `chunks/chunk-NN-draft.md`
   - Consistency is guaranteed by the shared `02-prompt.md` (style, goal, audience, voice, and polish challenges from analysis)
   - If no chunks (content under threshold): spawn one subagent for the entire source file
   - If Agent tool is unavailable, polish chunks sequentially inline using `02-prompt.md`
6. **Merge**: Once all subagents complete, combine polished chunks in order. If `chunks/frontmatter.md` exists, prepend it. Save as `03-draft.md` (refined) or `polished.md` (normal)
7. All intermediate files (source chunks + polished chunks) are preserved in `chunks/`

**After chunked draft is merged**, return control to main agent for critical review, revision, and finalize (Step 4).

### Step 4: Polish & Refine

**Polishing principles** (apply to all modes):

- **Preserve meaning**: Never change the author's intended meaning or core arguments
- **Maintain voice**: Keep the author's unique voice and perspective; don't make it generic
- **Rewrite, not edit**: Rewrite content into natural, engaging prose as if a skilled writer composed it from scratch. Quality test: "Does this read like it was originally written this well?"
- **Fix awkwardness**: Smooth out clunky phrasing, unclear sentences, jarring transitions
- **Improve flow**: Ensure logical progression from sentence to sentence, paragraph to paragraph
- **Enhance clarity**: Make complex ideas easier to understand without dumbing down
- **Correct errors**: Fix grammar, spelling, punctuation issues
- **Respect style**: Follow the chosen style preset while preserving authorial voice
- **Audience awareness**: Adjust vocabulary and explanation depth for target audience
- **Preserve format**: Keep all markdown formatting (headings, bold, italic, images, links, code blocks)
- **Frontmatter**: If source has YAML frontmatter, rename source-metadata fields with `source` prefix (camelCase: `url`→`sourceUrl`, `title`→`sourceTitle`, etc.), add polished values as new top-level fields (skip `title` if body has H1), keep other fields as-is
- **Chinese content**: only when `style: chinese` is explicitly selected, additionally apply the [Chinese Anti-AI Module](#chinese-anti-ai-module) — load its rules into the analyze, polish, and review steps. Under any other style, preserve the author's voice as usual (no benchmark convergence)

#### Quick Mode

Polish directly → save to `polished.md`. Apply all polishing principles above.

#### Normal Mode

1. **Analyze** → `01-analysis.md` (structure, tone, strengths, issues, opportunities)
2. **Assemble prompt** → `02-prompt.md` (polish instructions with context)
3. **Polish** (following `02-prompt.md`) → `polished.md`

After completion, prompt user: "Polish complete. To further review and refine, reply **refine** or **continue refining**."

If user continues, proceed with critical review → revision → finalize (same as refined mode Steps 4-6 below), saving `03-draft.md` (rename current `polished.md`), `04-critique.md`, `05-revision.md`, and updated `polished.md`.

#### Refined Mode

Full workflow for publication quality. See [references/refined-workflow.md](references/refined-workflow.md) for detailed guidelines per step.

The subagent (if used in Step 3.1) only handles the initial draft. All subsequent steps (critical review, revision, finalize) are handled by the main agent, which may delegate to subagents at its discretion.

Steps and saved files (all in output directory):
1. **Analyze** → `01-analysis.md` (structure, tone, strengths, issues, opportunities)
2. **Assemble prompt** → `02-prompt.md` (polish instructions with inlined context)
3. **Draft** → `03-draft.md` (initial polished version with writer's notes; from subagent if chunked)
4. **Critical review** → `04-critique.md` (diagnosis only: clarity, flow, style consistency, remaining issues)
5. **Revision** → `05-revision.md` (apply all critique findings to produce revised version)
6. **Finalize** → `polished.md` (final publication-quality version)

Each step reads the previous step's file and builds on it.

### Step 5: Output

Final polished version is always at `polished.md` in the output directory.

Display summary:
```
**Polish complete** ({mode} mode)

Source: {source-path}
Output dir: {output-dir}/
Final: {output-dir}/polished.md
Style: {style}
Goal: {goal}
Audience: {audience}
```

## Chinese Anti-AI Module

This module is **opt-in**: it activates only when `style: chinese` is explicitly selected (via `--style chinese`, EXTEND.md, or an explicit anti-AI request). It is never auto-applied just because the content is Chinese — under any other style the author's voice is preserved as usual. When active, load the rule source [references/zh/anti-ai.md](references/zh/anti-ai.md). It is the single source of truth for Chinese polishing and contains two functional halves that map onto the existing workflow steps:

| Rule half | Source sections | Applied in step |
|-----------|-----------------|-----------------|
| **Diagnostic** (detect AI fingerprints) | §1–4 fingerprints + §7 判定标准 | `01-analysis.md` (analyze) and `04-critique.md` (critical review) |
| **Generative** (how to rewrite) | Benchmarks + §5–12 principles | Polish / `05-revision.md` |

How it integrates with each mode:

- **Analyze step**: scan the source for the four fingerprint layers (思维模式 / 句式 / 词汇 / 结构), record hit locations and types, and estimate fingerprint density per §7 (每 500 字 3 处 → 全文需要改写). Record findings in `01-analysis.md`.
- **Benchmark selection** (`§0 风格自动判定`): pick **直接型** (narrative / opinion / experiential) or **分析型** (analytical / data-driven / argumentative) by genre — the agent decides automatically, no user input. Note the chosen benchmark in `01-analysis.md` / `02-prompt.md` so chunk subagents stay consistent.
- **Polish / Revision step**: rewrite toward the chosen benchmark and apply §5–12 (具体胜过抽象, 断言需要支撑, 信任读者, 比喻结构对应, 中英文加空格, 零 emoji, etc.).
- **Critical review step** (refined / continued-refine): re-scan density per §7 to verify fingerprints are gone before finalizing.

When chunking long Chinese content, inline the chosen benchmark and the relevant rules into `02-prompt.md` so every chunk subagent converges on the same style.

## Extension Support

Custom configurations via EXTEND.md. See **Preferences** section for paths and supported options.
