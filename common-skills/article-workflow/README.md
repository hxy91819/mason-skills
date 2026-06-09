# Article Workflow

A phased article optimization workflow. Each skill handles one phase — from brief generation through final publication. Skills are designed to be used in sequence, but each can also be invoked independently.

## Workflow overview

All phases work on the same `.article-workflow/` directory inside your article project, sharing inputs and outputs across phases.

```
Phase 0    brief                    Generate an editorial brief from oral drafts, outlines, and reference materials
Phase 0.5  clean-sources           Clean oral draft transcription errors
Phase 1    section-review           Section-by-section narrative review
Phase 2    evidence-pool            Fact-checking and material pool
Phase 3    *(author self-read)*     Author directly edits `.article-workflow/00-cleaned-sources/`
Phase 3.5  ai-edit-pass             AI-assisted editing based on confirmed decisions
Phase 4    global-review            Whole-article coherence review
Phase 4.5  main-draft               Integrate sections into a continuous main draft
Phase 4.6  visual-plan              Illustration and visual aid planning
Phase 5.0  style-bible              Extract a style bible from the main draft
Phase 5    polish                   Multi-round polishing (redundancy → rhythm → terminology)
Phase 6    final-review             Final review, reader testing, and image placement
Phase 8    publish                  Sync final draft to publishing channels
```

> Phase 3 has no separate skill — the author reads and edits directly. Phase 7 is intentionally skipped (reserved for future use).

## Core principles

- **AI diagnoses, the author decides.** Every phase separates "what AI can do" (analysis, organization, drafting) from "what only the author can decide" (key judgments, style calls, fact ownership).
- **Sub-agent review after each phase.** Every phase produces outputs, then spawns a read-only sub-agent to verify alignment with that phase's goals. The main agent decides which review suggestions to adopt.
- **No silent overrides.** If something is unclear and would affect the output direction, the skill asks the author first — it does not guess and proceed.
- **Working files in `.article-workflow/`.** All phases read from and write to the same project-level directory, so outputs from one phase become inputs for the next.

## Directory structure

```
.article-workflow/
├── brief.md                          ← Phase 0
├── sources/
│   ├── outline.md
│   ├── oral-draft/
│   ├── references/
│   └── proofs/
├── 00-cleaned-sources/               ← Phase 0.5
├── 01-section-reviews/               ← Phase 1
├── 02-evidence-pool/                 ← Phase 2
├── 03.5-ai-edit-pass/               ← Phase 3.5
├── 04-global-review/                 ← Phase 4
├── 04.5-main-draft/                  ← Phase 4.5
├── 04.6-visual-plan/                 ← Phase 4.6
├── style-bible.md                    ← Phase 5.0
├── 05-polish-rounds/                ← Phase 5
├── 06-final-review/                  ← Phase 6
└── 08-publish/                       ← Phase 8
```

## How to use

### Invoke a single phase

Tell the agent which phase you want to run. Each skill's `description` field lists its trigger phrases:

```
/run Phase 1 section review
```

### Run the full workflow

Start from Phase 0 and proceed in order. After each phase, review the outputs before moving to the next one.

### Skip phases

Not every phase is required. For example:
- If you already have a clean draft, skip Phase 0 and 0.5.
- If you don't need AI editing assistance, skip Phase 3.5.
- If you don't need illustrations, skip Phase 4.6.

### Create a new phase skill

Use `skill-maker` to turn a manually executed phase into a reusable workflow skill.

## Skills

| Phase | Skill | Directory | Purpose |
|-------|-------|-----------|---------|
| 0 | `article-workflow-brief` | `brief/` | Generate an editorial brief |
| 0.5 | `article-workflow-clean-sources` | `clean-sources/` | Clean oral draft transcription errors |
| 1 | `article-workflow-section-review` | `section-review/` | Section-by-section narrative review |
| 2 | `article-workflow-evidence-pool` | `evidence-pool/` | Fact-checking and material pool |
| 3.5 | `article-workflow-ai-edit-pass` | `ai-edit-pass/` | AI-assisted editing based on confirmed decisions |
| 4 | `article-workflow-global-review` | `global-review/` | Whole-article coherence review |
| 4.5 | `article-workflow-main-draft` | `main-draft/` | Integrate sections into a continuous draft |
| 4.6 | `article-workflow-visual-plan` | `visual-plan/` | Illustration and visual aid planning |
| 5.0 | `article-workflow-style-bible` | `style-bible/` | Extract a style bible from the main draft |
| 5 | `article-workflow-polish` | `polish/` | Multi-round polishing |
| 6 | `article-workflow-final-review` | `final-review/` | Final review and reader testing |
| 8 | `article-workflow-publish` | `publish/` | Sync final draft to publishing channels |
| — | `article-workflow-skill-maker` | `skill-maker/` | Meta skill: create new workflow phases |

## Installation

Copy the entire `article-workflow/` directory into your skills location:

- **Personal** — `~/.cursor/skills/article-workflow/`
- **Project** — `.cursor/skills/article-workflow/`

Each subdirectory contains its own `SKILL.md` and is discovered automatically.

## License

MIT License. See the [repository license](../../LICENSE) for details.