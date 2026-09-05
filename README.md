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
│   ├── agents/
│   ├── references/
│   └── scripts/
├── large-task-orchestrator/
│   ├── SKILL.md
│   ├── agents/
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
├── tech-doc-html/
│   ├── SKILL.md
│   ├── references/       # Design system, component templates, security rules
│   ├── scripts/          # Validation helpers
│   └── assets/           # Example output
└── worktree-cleanup/
    ├── SKILL.md
    ├── agents/
    ├── scripts/
    └── tests/
```

See [common-skills/README.md](common-skills/README.md) for authoring guidelines.

Repository tooling includes the [shared-worktree Git guard](tools/git-shared-worktree-guard/README.md),
which preserves concurrent Agent work without blocking safe local history operations.

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

Agents that discover user-scoped skills from `~/.agents/skills` can link individual skills.

> **Note**: Only 16 core engineering and governance skills are recommended for global user scope. See [docs/recommended-global-skills.md](docs/recommended-global-skills.md) and [`config/skill-symlinks.yaml`](config/skill-symlinks.yaml) for the full list, rationale, and one-command sync instructions.

```bash
# Sync recommended user-scope skills automatically:
python3 common-skills/skill-manifest-sync/scripts/sync_skill_symlinks.py --mode apply --yes
```

## Available skills

| Skill | Description |
|-------|-------------|
| [ask-oracle](common-skills/ask-oracle/) | Produces a concise brief containing the original request and all decision-relevant context, reserving technical judgment for an expert oracle. |
| [article-polish](common-skills/article-polish/) | Article polishing with quick / normal / refined modes. Derivative work based on [baoyu-translate](https://github.com/JimLiu/baoyu-skills/tree/main/skills/baoyu-translate). |
| [article-workflow](common-skills/article-workflow/) | A phased article optimization workflow with 13 skills — from brief generation through final publication. See [workflow README](common-skills/article-workflow/README.md) for phase order and usage. |
| [distill](common-skills/distill/) | Reviews one session or a bounded periodic cross-session window for evidence-backed harness and project-knowledge improvements, explicitly auditing repository Skills and AGENTS.md instructions for design and usability problems. |
| [large-task-planning](common-skills/large-task-planning/) | Compiles a large engineering goal into reader-friendly SPEC/STATUS views and a JSON execution plan. Explicit invocation only. |
| [large-task-orchestrator](common-skills/large-task-orchestrator/) | Uses host-native workers and an economy validator (`$story-direction-review`) to execute a plan until delivery or a genuine blocker. Explicit invocation only. |
| [mermaid-lint](common-skills/mermaid-lint/) | Validates and fixes mermaid diagrams in markdown. Renders every block against the real mermaid renderer and reports all failures in one pass. Original skill design. |
| [readiness-report](common-skills/readiness-report/) | Read-only Agent-Readiness audit of the current Git repository with a 1–5 level score and a local JSON report. Adapted from Factory Droid's built-in `/readiness-report` with remote reporting removed. Explicit invocation only. |
| [readiness-fix](common-skills/readiness-fix/) | Fixes failing signals from the latest local readiness report; asks whether to generate a report first when none exists. Adapted from Factory Droid's built-in `/readiness-fix` with remote report access removed. Explicit invocation only. |
| [open-source-contribution](common-skills/open-source-contribution/) | Open-source contribution hygiene: identity verification, privacy scanning, Git history cleanup, installer hardening, autoreview, and safe push/PR validation. |
| [secure-release](common-skills/secure-release/) | Integrates fail-closed release pipelines using a versioned CI kit; npm is the first implemented adapter. |
| [story-direction-review](common-skills/story-direction-review/) | Reviews a completed Story for direction drift, invalidated assumptions, coverage gaps, and necessary plan changes. Explicit invocation only. |
| [tech-doc-html](common-skills/tech-doc-html/) | Interactive single-file HTML from technical design docs. Original skill design; visual style inspired by [html-effectiveness](https://github.com/ThariqS/html-effectiveness). |
| [worktree-cleanup](common-skills/worktree-cleanup/) | Audits clean worktrees, proves their HEAD is durable on GitHub, and removes one reviewed report in a resilient batch. Explicit invocation only. |

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

Replays either the current session or a bounded periodic or milestone review window as a
harness and project-knowledge retrospective. It treats explicit user corrections as
high-authority belief changes, separates their intended scope from recurrence and impact,
and ignores ordinary errors unless investigation produced a verified reusable conclusion.
In review mode it merges semantically equivalent signals across distinct tasks, checks
whether earlier improvements worked or regressed, and discloses evidence coverage without
claiming access to unavailable conversation history.

Before adding guidance, it explicitly audits the applicable `AGENTS.md` chain and the
repository's Skill catalog as harness surfaces. It checks ownership and coverage,
invocation policy, reachability, usability, coherence, and observed effectiveness, while
also pruning stale, duplicate, conflicting, or misplaced rules and project documentation.
Cross-session signal tables stay temporary: the skill creates no learning ledger or
recurring report, and routes only the confirmed durable result to its authoritative
source. It presents up to eight changes or questions per message as a category-based
frontier, with no total cap on candidates or rounds, then applies the confirmed set behind
one approval gate. Periodic reviews use a user-local, repository-specific checkpoint to
avoid re-reading covered sessions by default; the manager may reopen earlier evidence when
it is useful.

### large-task-planning

Compiles engineering work that exceeds one context into two audience-specific layers.
`SPEC.md` and `STATUS.md` help people understand the intended outcome and judge progress;
`agent/plan.json` and `agent/stories/*.json` are the validated source of truth for intent,
state, dependencies, context, and handoff. The Markdown views are generated around human
questions instead of mirroring internal Story fields.

Its execution counterpart, `large-task-orchestrator`, drives fresh host-native worker
subagents and an economy validator that runs `$story-direction-review` to confirm the
story is actually complete, with one writer by default. Plan files and
Git checkpoints make subagent sessions disposable and long-running work recoverable. The
two Skills share a [core system design](docs/large-task-system-design.md), and the v2
token-login example is [`docs/largeplan-example/`](docs/largeplan-example/).

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
history rewrites before pushing. Ships `scripts/check_identity.py` (Python
stdlib only; needs `git`, `gh` optional) that verifies repository-local Git
identity and every commit author/committer against the approved GitHub account.

### secure-release

Routes release migrations from repository discovery into a cross-language
protocol and a CI-independent, versioned vendored kit. The shared core verifies
stable source identity, committed changelog notes, an exact artifact set, and
SHA-256 handoff. Kit v1 implements npm packaging, OIDC publication commands,
and clean-install registry smoke; PyPI, Cargo, Go/GitHub binaries, and
containers remain explicit adapter design targets rather than claimed support.

### readiness-report

A read-only Agent-Readiness audit ported from Factory Droid's built-in `/readiness-report`
slash command, with the remote (Factory cloud) reporting removed. It statically inspects
the repository against a catalog of 85 signals across 12 categories (style & validation,
build system, testing, documentation, dev environment, observability, security, delivery,
code health, task discovery, product & experimentation), scores the repo on a 1–5 level,
and stores the report locally under the XDG cache — never on any remote endpoint.

### readiness-fix

The remediation counterpart ported from Factory Droid's built-in `/readiness-fix`, with
remote report access removed. It reads the latest **local** readiness report (from
`readiness-report`), lists the failing signals, and fixes them one at a time: named
signals are matched by criterion ID, name, or meaning and fixed in sequence; otherwise
the user picks a category, then a single signal. With no local report it asks whether to
generate one first or fix directly. Ships `scripts/pick_failing.py` to extract the
failing signals from the local report (no network access anywhere).

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

Original long-running task system. The v2 design selectively adapts the decision-fog,
tracer-bullet, and observable-test-seam ideas from
[Matt Pocock's skills](https://github.com/mattpocock/skills) (MIT, Copyright Matt Pocock)
without vendoring or requiring that package at runtime. Story closeout is completion
validation via `$story-direction-review`, not two-axis code review. See the
[pinned upstream provenance](docs/large-task-system-design.md#上游借鉴与版本回溯) for the exact
source commit and design mapping.

### [story-direction-review](common-skills/story-direction-review/)

Original skill design for independent, big-picture review of completed engineering Stories.

### [tech-doc-html](common-skills/tech-doc-html/)

Original Cursor skill design. Visual style inspired by [html-effectiveness](https://github.com/ThariqS/html-effectiveness) (Apache-2.0, Copyright Anthropic PBC). Style patterns used in `references/design_system.md` and `references/component_patterns.md`. [Full Apache-2.0 text](licenses/APACHE-2.0.txt).

### [worktree-cleanup](common-skills/worktree-cleanup/)

Original skill design for explicitly invoked, GitHub-aware worktree retirement. It proves each clean HEAD is remotely durable, inventories ignored data, backs up `.local`, applies one reviewed audit report without admitting new candidates, and isolates stale or failed candidates instead of aborting the batch.
