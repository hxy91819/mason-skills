# Refined Workflow Details

This file provides detailed guidelines for each workflow step. Steps are shared across modes:

- **Quick**: Polish only (no steps from this file)
- **Normal**: Step 1 (Analysis) → Polish
- **Refined**: Step 1 (Analysis) → Step 2 (Draft) → Step 3 (Review) → Step 4 (Revision) → Step 5 (Finalize)
- **Normal → Upgrade**: After normal mode, user can continue with Step 3 → Step 4 → Step 5

All intermediate results are saved as files in the output directory.

## Step 1: Content Analysis

Before polishing, analyze the source material. Save analysis to `01-analysis.md` in the output directory.

### 1.1 Document Profile

- What is this content about? What is the core argument?
- Author background, stance, and writing context
- Document type, length, and structure

### 1.2 Current Tone & Style

- What is the author's voice? (formal/casual/authoritative/conversational)
- What register and mood does the writing convey?
- Identify unique writing patterns, recurring expressions, personality markers

### 1.3 Strengths & Issues

- **Strengths**: What works well — clear explanations, vivid metaphors, logical structure — that should be preserved?
- **Issues**: Specific problems — awkward phrasing, unclear sentences, weak transitions, verbose passages, inconsistent tone — with locations and impact

### 1.4 Polish Challenges

Identify what may cause difficulty in polishing:

- **Voice-sensitive passages**: Sections where the author's personality is strong — preserve carefully
- **Structural challenges**: Long complex sentences, dense technical passages, sections needing restructuring
- **Clarity gaps**: Passages where meaning is unclear or arguments are underdeveloped
- **Flow breaks**: Jarring transitions, logical gaps, pacing problems

**Save `01-analysis.md`** with:
```
## Document Profile
[Type, length, structure, core argument, author context]

## Current Tone & Style
[Voice, register, mood, unique patterns]

## Strengths
- [strength with example, location]

## Issues
- [category]: [description] @ [location]
  - Example: "[problematic text]"
  - Impact: [why it matters]

## Polish Challenges
- [passage] → [challenge type] → [suggested approach]
- ...
```

## Step 2: Assemble Polish Prompt

Main agent reads `01-analysis.md` and assembles a complete polish prompt using [references/subagent-prompt-template.md](subagent-prompt-template.md). Inline the following from analysis:

- **Target style**: Resolved style preset + source voice assessment from §1.2
- **Target goal**: Resolved goal preset
- **Content background**: Summary from §1.1
- **Issues to fix**: All issues from §1.3
- **Polish challenges**: All challenges from §1.4

Save to `02-prompt.md`. This prompt is used by the subagent (chunked) or by the main agent itself (non-chunked).

## Step 3: Initial Draft

Save to `03-draft.md` in the output directory.

For chunked content, the subagent produces this draft (merged from chunk polishes). For non-chunked content, the main agent produces it directly.

Polish the full content following `02-prompt.md`. Apply all **Polishing principles** from SKILL.md.

## Step 4: Critical Review

The main agent critically reviews the draft against the source. Save review findings to `04-critique.md`. This step produces **diagnosis only** — no rewriting yet.

### 4.1 Meaning Integrity

- Compare each paragraph against the original
- Verify no meanings were altered, added, or removed
- Check that facts, data, proper nouns remain accurate

### 4.2 Voice & Voice Drift

- Does the polished version preserve the author's unique voice?
- Flag passages where the rewriting made the voice generic or unrecognizable
- Check emotional tone and personality markers are preserved

### 4.3 Clarity & Flow

- Are complex ideas now easier to understand?
- Flag remaining unclear passages or over-simplifications
- Check transitions between paragraphs — are they smooth and logical?
- Note where pacing could still be improved

### 4.4 Style & Goal Execution

- Was the chosen style consistently applied throughout?
- Was the polish goal achieved?
- Flag style mismatches: formal tone in a natural-style pass, verbose passages in a concise pass, etc.
- Were custom rules (from EXTEND.md) followed?

**Save `04-critique.md`** with:
```
## Meaning Integrity
- [issue]: [location] — [description]

## Voice & Voice Drift
- [issue]: [example] → [suggested fix]

## Clarity & Flow
- [issue]: [location] — [description]

## Style & Goal Execution
- [issue]: [location] — [description]

## Summary
[Overall assessment: X critical issues, Y improvements]
```

## Step 5: Revision

Apply all findings from `04-critique.md` to produce a revised version. Save to `05-revision.md`.

Read `03-draft.md` and `04-critique.md`, fix all issues, restore author voice where drifted, smooth remaining rough transitions.

## Step 6: Finalize

Save final version to `polished.md`.

Final pass on `05-revision.md` for publication quality:

- Read the entire polished piece as a standalone work — does it flow naturally?
- Smooth remaining rough edges
- Ensure consistent voice and style throughout
- Final grammar, spelling, and punctuation check
- Verify markdown formatting is preserved correctly

## Subagent Responsibility

Each subagent (one per chunk) is responsible **only** for producing the initial polished version of its chunk (Step 3). The main agent assembles the shared prompt (Step 2), spawns all subagents in parallel, then takes over for critical review (Step 4), revision (Step 5), and finalize (Step 6).

## Chunked Refined Polish

When content exceeds the chunk threshold and uses refined mode:

1. Main agent runs analysis (Step 1) on the **entire** document first → `01-analysis.md`
2. Main agent assembles polish prompt → `02-prompt.md`
3. Split into chunks → `chunks/`
4. Spawn one subagent per chunk in parallel (each reads `02-prompt.md` for shared context) → merge all results into `03-draft.md`
5. Main agent critically reviews the merged draft → `04-critique.md`
6. Main agent revises based on critique → `05-revision.md`
7. Main agent finalizes → `polished.md`
8. Final cross-chunk consistency check: voice, style, flow, transitions at chunk boundaries
