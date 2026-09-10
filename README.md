# mason-skills

A collection of [Cursor Agent Skills](https://docs.cursor.com/context/skills) shared for the tech community.

Skills are reusable instruction sets that teach AI agents how to perform specialized workflows — code review, documentation, automation, and more.

## What's inside

可移植的 BB 配额与 ACP 入口插件见 [tools/bb-account-limits](tools/bb-account-limits/README.md)，包含目标环境配置、安装与回退说明。

Skills live under `common-skills/`. Each skill is a directory with a required `SKILL.md` file.

```
common-skills/
├── anti-ai-slop/
│   └── SKILL.md
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
├── open-source-fork-maintenance/
│   ├── SKILL.md
│   ├── agents/
│   ├── assets/
│   ├── references/
│   └── scripts/
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

Repository tooling includes the [shared-worktree Git stash guard](tools/git-shared-worktree-guard/README.md),
which prevents state-changing stash operations and autostash.

`config/` holds the facts for reproducing a user-scope setup on a new machine:
[`skill-symlinks.yaml`](config/skill-symlinks.yaml) is the recommended global-skills manifest
(applied by `$skill-manifest-sync`), and [`user-agents.md`](config/user-agents.md) is the shared
user-scope `AGENTS.md`, linked to `~/.agents/AGENTS.md` by `$harness-config-sync`.
On Windows the manifest script falls back to NTFS junctions when symbolic-link privilege is
missing, and file-level prompt links are created with `mklink` (admin or Developer Mode).

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

> **Note**: Only 21 core engineering and governance skills are recommended for global user scope. See [docs/recommended-global-skills.md](docs/recommended-global-skills.md) and [`config/skill-symlinks.yaml`](config/skill-symlinks.yaml) for the full list, rationale, and one-command sync instructions.

```bash
# Sync recommended user-scope skills automatically:
python3 common-skills/skill-manifest-sync/scripts/sync_skill_symlinks.py --mode apply --yes
```

## Available skills

### Project-scoped groups

| Group | Skill | Tags | Use |
|-------|-------|------|-----|
| Open-source | `open-source-fork-maintenance` | `fork-maintenance`, `non-maintainer`, `local-aggregate`, `project-symlink` | Link into the skills directory of a public fork that is locally maintained by a non-maintainer. |

| Skill | Description |
|-------|-------------|
| [anti-ai-slop](common-skills/anti-ai-slop/) | Reviews the current diff or latest commit for AI slop in code and docs, then deletes it. |
| [ask-oracle](common-skills/ask-oracle/) | Produces a concise brief containing the original request and all decision-relevant context, reserving technical judgment for an expert oracle. |
| [article-polish](common-skills/article-polish/) | Article polishing with quick / normal / refined modes. Derivative work based on [baoyu-translate](https://github.com/JimLiu/baoyu-skills/tree/main/skills/baoyu-translate). |
| [article-workflow](common-skills/article-workflow/) | A phased article optimization workflow with 13 skills — from brief generation through final publication. See [workflow README](common-skills/article-workflow/README.md) for phase order and usage. |
| [distill](common-skills/distill/) | Reviews one session or a bounded periodic cross-session window for evidence-backed harness and project-knowledge improvements, explicitly auditing repository Skills and AGENTS.md instructions for design and usability problems. |
| [large-task-planning](common-skills/large-task-planning/) | Compiles a large engineering goal into reader-friendly SPEC/STATUS views and a JSON execution plan. Explicit invocation only. |
| [large-task-orchestrator](common-skills/large-task-orchestrator/) | 用带 pid 锁的后台确定性 driver 经 BB（`bb-model-routing`）派发 Worker / Validator，并仅在异常时派 Judge 执行计划；按计划隔离状态，支持并行。仅显式调用。 |
| [mermaid-lint](common-skills/mermaid-lint/) | Validates and fixes mermaid diagrams in markdown. Renders every block against the real mermaid renderer and reports all failures in one pass. Original skill design. |
| [readiness-report](common-skills/readiness-report/) | Read-only Agent-Readiness audit of the current Git repository with a 1–5 level score and a local JSON report. Adapted from Factory Droid's built-in `/readiness-report` with remote reporting removed. Explicit invocation only. |
| [readiness-fix](common-skills/readiness-fix/) | Fixes failing signals from the latest local readiness report; asks whether to generate a report first when none exists. Adapted from Factory Droid's built-in `/readiness-fix` with remote report access removed. Explicit invocation only. |
| [open-source-contribution](common-skills/open-source-contribution/) | Open-source contribution hygiene: identity verification, privacy scanning, Git history cleanup, installer hardening, autoreview, and safe push/PR validation. |
| [open-source-fork-maintenance](common-skills/open-source-fork-maintenance/) | Maintains a non-maintainer public fork through a project-local `local/aggregate` integration branch. Explicit invocation only. |
| [secure-release](common-skills/secure-release/) | Integrates fail-closed release pipelines using a versioned CI kit; npm is the first implemented adapter. |
| [submitting-github-issues-with-images](common-skills/submitting-github-issues-with-images/) | Uploads local screenshots, videos, or diagnostic attachments as GitHub Release Assets, embeds them in issues, PR bodies, or comments, and verifies the published result by reading it back online. Explicit invocation only, with a stated exception for authorized caller workflows. |
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

执行端 `large-task-orchestrator` 是确定性 driver：它先查询计划状态，未运行时以后台 `start` 启动，并按
`(仓库, 计划)` 隔离 pid、状态和日志；它经 `bb-model-routing` 派 fresh Worker 和廉价 Validator，在 Worker
异常、验证失败、越界或报告不可解析时才派一次性的 strong Judge。计划文件、Git checkpoint、driver jsonl 和
BB 线程记录让会话可替换、长时执行可恢复。两项 Skill 共享
[核心设计](docs/large-task-system-design.md)，v2 令牌登录示例在
[`docs/largeplan-example/`](docs/largeplan-example/)。

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
validation by an independent validator thread, not two-axis code review. See the
[pinned upstream provenance](docs/large-task-system-design.md#上游借鉴与版本回溯) for the exact
source commit and design mapping.

### [story-direction-review](common-skills/story-direction-review/)

Original skill design for independent, big-picture review of completed engineering Stories.

### [tech-doc-html](common-skills/tech-doc-html/)

Original Cursor skill design. Visual style inspired by [html-effectiveness](https://github.com/ThariqS/html-effectiveness) (Apache-2.0, Copyright Anthropic PBC). Style patterns used in `references/design_system.md` and `references/component_patterns.md`. [Full Apache-2.0 text](licenses/APACHE-2.0.txt).

### [worktree-cleanup](common-skills/worktree-cleanup/)

Original skill design for explicitly invoked, GitHub-aware worktree retirement. It proves each clean HEAD is remotely durable, inventories ignored data, backs up `.local`, applies one reviewed audit report without admitting new candidates, and isolates stale or failed candidates instead of aborting the batch.
