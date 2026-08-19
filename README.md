# mason-skills

A collection of [Cursor Agent Skills](https://docs.cursor.com/context/skills) shared for the tech community.

Skills are reusable instruction sets that teach AI agents how to perform specialized workflows — code review, documentation, automation, and more.

## What's inside

Skills live under `common-skills/`. Each skill is a directory with a required `SKILL.md` file.

```
common-skills/
├── ask-oracle/
│   └── SKILL.md
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
├── distill/
│   └── SKILL.md
├── large-task-planning/
│   ├── SKILL.md
│   ├── agent-schema.md
│   ├── agents/
│   ├── examples/
│   └── scripts/
├── mermaid-lint/
│   ├── SKILL.md
│   ├── validate-mermaid.py    # Extracts mermaid blocks, drives the worker
│   └── mermaid-worker.mjs     # Renders every block in one browser session
├── open-source-contribution/
│   └── SKILL.md
├── story-direction-review/
│   ├── SKILL.md
│   └── agents/
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

Agents that discover user-scoped skills from `~/.agents/skills` can link individual skills:

```bash
ln -s /path/to/mason-skills/common-skills/large-task-planning ~/.agents/skills/large-task-planning
ln -s /path/to/mason-skills/common-skills/story-direction-review ~/.agents/skills/story-direction-review
```

## Available skills

| Skill | Description |
|-------|-------------|
| [ask-oracle](common-skills/ask-oracle/) | Produces a concise brief containing the original request and all decision-relevant context, reserving technical judgment for an expert oracle. |
| [article-polish](common-skills/article-polish/) | Article polishing with quick / normal / refined modes. Derivative work based on [baoyu-translate](https://github.com/JimLiu/baoyu-skills/tree/main/skills/baoyu-translate). |
| [article-workflow](common-skills/article-workflow/) | A phased article optimization workflow with 13 skills — from brief generation through final publication. See [workflow README](common-skills/article-workflow/README.md) for phase order and usage. |
| [distill](common-skills/distill/) | Reviews agent sessions for evidence-backed harness and project-knowledge improvements, pruning stale, conflicting, or incorrect guidance before strengthening durable decisions, docs, specs, tools, checks, skills, or CI. |
| [large-task-planning](common-skills/large-task-planning/) | Builds an executable Epic/Story portal: human Markdown intent, script-owned Agent JSON, and a generated status dashboard. Explicit invocation only. |
| [mermaid-lint](common-skills/mermaid-lint/) | Validates and fixes mermaid diagrams in markdown. Renders every block against the real mermaid renderer and reports all failures in one pass. Original skill design. |
| [open-source-contribution](common-skills/open-source-contribution/) | Open-source contribution hygiene: identity verification, privacy scanning, Git history cleanup, installer hardening, autoreview, and safe push/PR validation. |
| [secure-release](common-skills/secure-release/) | Integrates fail-closed release pipelines using a versioned CI kit; npm is the first implemented adapter. |
| [story-direction-review](common-skills/story-direction-review/) | Reviews a completed Story for direction drift, invalidated assumptions, coverage gaps, and necessary plan changes. Explicit invocation only. |
| [tech-doc-html](common-skills/tech-doc-html/) | Interactive single-file HTML from technical design docs. Original skill design; visual style inspired by [html-effectiveness](https://github.com/ThariqS/html-effectiveness). |

### ask-oracle

A manually invoked skill that frames the user's request and all known decision-changing
context, then asks an expert oracle to supply the technical judgment.

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

### distill

Replays the current session as a harness and project-knowledge retrospective, including
failures, successful shortcuts, interaction friction, and durable product or technical
decisions. It distinguishes user-confirmed decisions from agent proposals and checks that
material choices were explained in human-facing sources before implementation. Before
adding guidance, it audits existing rules and project documentation for
staleness, duplication, conflicts, incorrect claims, deterministic replacements, and
misplaced detail. It prioritizes deletion, correction, and consolidation before adding
missing global context or decision rationale. It proposes up to eight changes or
questions per round across both lanes, continuing through a decision tree when needed,
then applies the confirmed set behind one approval gate.

### large-task-planning

Creates a compact project portal for engineering work that continues across sessions or
agents. Humans read Markdown epics and stories; agents keep structured JSON state that
scripts alone may write. The skill validates dependencies and coverage ownership,
requires user-visible confirmation for decisions that change product or release shape,
supports inserted IDs such as `STORY-03.1`, and generates the status dashboard from JSON.
It is manually invoked so ordinary tasks stay lightweight.

The token-login prompt and runner live in
[`common-skills/large-task-planning/examples/token-login/`](common-skills/large-task-planning/examples/token-login/).
The latest generated portal is [`docs/largeplan-example/`](docs/largeplan-example/).

### mermaid-lint

Finds every mermaid diagram in one or more markdown files, validates it, and fixes the
broken ones. Unlike the other skills here it ships executable helpers, so it needs
Node.js and [`@mermaid-js/mermaid-cli`](https://github.com/mermaid-js/mermaid-cli)
available on `PATH`; the skill will not install them for you.

Two design decisions are worth calling out, because the obvious alternatives are worse:

- **It renders each diagram instead of only parsing it.** `mermaid.parse()` covers the
  parse phase only, so errors raised while rendering slip through — an invalid gantt date
  such as `notadate` parses fine but fails to render. Rendering answers the question a
  document author actually has: will this diagram show up?
- **It renders the whole batch in a single browser session.** Spawning one Chromium per
  diagram costs roughly 1.7s each; sharing a session brings the marginal cost down to
  about 12ms, so 60 diagrams take ~2s instead of ~100s. Running `mmdc` over the markdown
  file directly would also share a session, but it aborts on the first bad diagram, which
  defeats the point of a linter.

Block extraction follows CommonMark fence rules. A deliberately broken example nested
inside a longer fence is not reported as a real error, and directive-style blocks,
fences carrying an info string, and tilde fences are all recognized.

### open-source-contribution

Standardizes open-source contribution cleanup and release checks for coding
agents: scan file content and Git metadata, verify commit author name and email
against the approved GitHub account, remove local paths and private identities,
harden installers, preserve streaming behavior in local proxies, run
gitleaks/pre-commit/tests, use autoreview as a closeout gate, and verify
history rewrites before pushing.

### secure-release

Routes release migrations from repository discovery into a cross-language
protocol and a CI-independent, versioned vendored kit. The shared core verifies
stable source identity, committed changelog notes, an exact artifact set, and
SHA-256 handoff. Kit v1 implements npm packaging, OIDC publication commands,
and clean-install registry smoke; PyPI, Cargo, Go/GitHub binaries, and
containers remain explicit adapter design targets rather than claimed support.

### story-direction-review

Performs a read-only, big-picture review after a Story is complete. It distinguishes
direction drift and invalidated planning assumptions from ordinary code-review findings,
then returns one decision: continue, patch the handoff, insert a Story, or replan. It is
manually invoked and changes no files unless the user separately requests it.

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

### [mermaid-lint](common-skills/mermaid-lint/)

Original skill design. Drives [mermaid](https://github.com/mermaid-js/mermaid) through
[`@mermaid-js/mermaid-cli`](https://github.com/mermaid-js/mermaid-cli) (MIT) at runtime;
neither project's code is vendored here.

### [large-task-planning](common-skills/large-task-planning/)

Original skill design for outcome-sized engineering plans and deterministic Epic/Story status portals.

### [story-direction-review](common-skills/story-direction-review/)

Original skill design for independent, big-picture review of completed engineering Stories.

### [tech-doc-html](common-skills/tech-doc-html/)

Original Cursor skill design. Visual style inspired by [html-effectiveness](https://github.com/ThariqS/html-effectiveness) (Apache-2.0, Copyright Anthropic PBC). Style patterns used in `references/design_system.md` and `references/component_patterns.md`. [Full Apache-2.0 text](licenses/APACHE-2.0.txt).
