# mason-skills

A collection of [Cursor Agent Skills](https://docs.cursor.com/context/skills) shared for the tech community.

Skills are reusable instruction sets that teach AI agents how to perform specialized workflows — code review, documentation, automation, and more.

## What's inside

Skills live under `common-skills/`. Each skill is a directory with a required `SKILL.md` file.

```
common-skills/
├── article-polish/
│   └── SKILL.md
├── article-workflow/
│   ├── README.md
│   ├── brief/
│   │   └── SKILL.md
│   ├── clean-sources/
│   │   └── SKILL.md
│   ├── section-review/
│   │   └── SKILL.md
│   ├── evidence-pool/
│   │   └── SKILL.md
│   ├── ai-edit-pass/
│   │   └── SKILL.md
│   ├── global-review/
│   │   └── SKILL.md
│   ├── main-draft/
│   │   └── SKILL.md
│   ├── visual-plan/
│   │   └── SKILL.md
│   ├── style-bible/
│   │   └── SKILL.md
│   ├── polish/
│   │   └── SKILL.md
│   ├── final-review/
│   │   └── SKILL.md
│   ├── publish/
│   │   └── SKILL.md
│   └── skill-maker/
│       └── SKILL.md
└── tech-doc-html/
    ├── SKILL.md
    ├── references/       # Design system, component templates, security rules
    ├── scripts/          # Validation helpers
    └── assets/           # Example output
```

See [common-skills/README.md](common-skills/README.md) for authoring guidelines.

## Usage

### Cursor IDE

1. Clone this repository or copy the skill directory you need.
2. Place skills in one of these locations:
   - **Personal** — `~/.cursor/skills/<skill-name>/` (available across all projects)
   - **Project** — `.cursor/skills/<skill-name>/` (shared with the repository)
3. Cursor discovers skills automatically from the `SKILL.md` frontmatter.

For the `article-workflow` group, copy the entire directory:
```
~/.cursor/skills/article-workflow/
```

### Other agents

Skills are plain markdown. You can adapt the instructions for other AI coding tools that support custom system prompts or skill files.

## Available skills

| Skill | Description |
|-------|-------------|
| [article-polish](common-skills/article-polish/) | Article polishing with quick / normal / refined modes. Derivative work based on [baoyu-translate](https://github.com/JimLiu/baoyu-skills/tree/main/skills/baoyu-translate). |
| [article-workflow](common-skills/article-workflow/) | A phased article optimization workflow with 13 skills — from brief generation through final publication. See [workflow README](common-skills/article-workflow/README.md) for phase order and usage. |
| [tech-doc-html](common-skills/tech-doc-html/) | Interactive single-file HTML from technical design docs. Original skill design; visual style inspired by [html-effectiveness](https://github.com/ThariqS/html-effectiveness). |

### article-polish

Polishes and improves writing with three modes (quick / normal / refined). Supports style presets, audience tuning, long-document chunking, and persistent preferences via `EXTEND.md`.

### article-workflow

A phased article optimization workflow. Each skill handles one phase — from brief generation through final publication. Skills are designed to be used in sequence, but each can also be invoked independently. See the [workflow README](common-skills/article-workflow/README.md) for details.

**Recommended order:**

| Phase | Skill | Purpose |
|-------|-------|---------|
| 0 | `article-workflow-brief` | Generate an editorial brief |
| 0.5 | `article-workflow-clean-sources` | Clean oral draft transcription errors |
| 1 | `article-workflow-section-review` | Section-by-section narrative review |
| 2 | `article-workflow-evidence-pool` | Fact-checking and material pool |
| 3 | *(Author self-read and direct editing)* | Author directly edits `.article-workflow/00-cleaned-sources/` |
| 3.5 | `article-workflow-ai-edit-pass` | AI-assisted editing based on confirmed decisions |
| 4 | `article-workflow-global-review` | Whole-article coherence review |
| 4.5 | `article-workflow-main-draft` | Integrate sections into a continuous draft |
| 4.6 | `article-workflow-visual-plan` | Illustration and visual aid planning |
| 5.0 | `article-workflow-style-bible` | Extract a style bible |
| 5 | `article-workflow-polish` | Multi-round polishing |
| 6 | `article-workflow-final-review` | Final review and reader testing |
| 8 | `article-workflow-publish` | Sync to publishing channels |

The `article-workflow-skill-maker` is a meta skill for turning a manually executed phase into a reusable workflow skill.

### tech-doc-html

An **original Cursor skill** that converts technical specs into interactive HTML visualizations. The agent picks components per section (Mermaid diagrams, SVG sliders, comparison tables, risk matrices), runs Mermaid security checks and Playwright QA, and applies a visual style inspired by [html-effectiveness](https://github.com/ThariqS/html-effectiveness).

**Triggers:** generate technical design HTML, architecture diagram pages, interactive RFC visualizations.

**Includes:** design system reference, component pattern library, example output, security validation scripts.

## Contributing

This is a personal skills collection. Feel free to fork, adapt, and use the skills under the [MIT License](LICENSE).

If you find a bug or have a suggestion, open an issue or pull request.

## License

This repository is released under the [MIT License](LICENSE).

## Attributions

### [article-polish](common-skills/article-polish/)

Derivative work based on [baoyu-translate](https://github.com/JimLiu/baoyu-skills/tree/main/skills/baoyu-translate) from [baoyu-skills](https://github.com/JimLiu/baoyu-skills) (MIT, Copyright Jim Liu). Repurposes the workflow for writing improvement. Independent project.

### [article-workflow](common-skills/article-workflow/)

Original skill designs for a phased article optimization workflow. Each skill covers one phase — from brief generation through publication. The visual planning phase references a generic `article-illustrator` skill for prompt construction rules.

### [tech-doc-html](common-skills/tech-doc-html/)

Original Cursor skill design. Visual style inspired by [html-effectiveness](https://github.com/ThariqS/html-effectiveness) (Apache-2.0, Copyright Anthropic PBC). Style patterns used in `references/design_system.md` and `references/component_patterns.md`. [Full Apache-2.0 text](licenses/APACHE-2.0.txt).