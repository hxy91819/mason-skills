---
name: article-polish
description: "Use when the user invokes $article-polish to polish, condense, expand, or rewrite an article."
disable-model-invocation: true
triggers:
  - user
metadata:
  openclaw:
    homepage: https://github.com/JimLiu/baoyu-skills/tree/main/skills/baoyu-translate
    requires:
      anyBins:
        - bun
        - npx
---

# Article Polish

流程类 Skill，默认仅在用户显式调用 `$article-polish` 时运行。

Improve the requested article while preserving the author's meaning and voice. Complete the selected mode through its final artifact; optional saved preferences are not a prerequisite.

## Resolve preferences

Use explicit request settings first, then the first existing `EXTEND.md` in this order:

1. `.mason-skills/article-polish/EXTEND.md` in the project.
2. `${XDG_CONFIG_HOME:-$HOME/.config}/mason-skills/article-polish/EXTEND.md`.
3. `$HOME/.mason-skills/article-polish/EXTEND.md`.

Read an existing file once per session unless it changes. With no file, use `normal`, `general`, `natural`, and `improve` for mode, audience, style, and goal, adjusted by the user's request. Proceed without a setup questionnaire or writing persistent preferences. Ask only if a missing choice materially changes the article's meaning or requested result.

When the user asks to save or edit defaults, read [preference setup](references/config/first-time-setup.md) and [schema](references/config/extend-schema.md). Preserve unrelated saved settings.

## Choose the requested mode

| Mode | Completion |
| --- | --- |
| `quick` / quick polish | Polish directly and save `polished.md` |
| `normal` (default) | Analyze → assemble prompt → polish; save `01-analysis.md`, `02-prompt.md`, and `polished.md` |
| `refined` / publication quality | Analyze → draft → review → revise → finalize, including all intermediate files in [refined workflow](references/refined-workflow.md), ending at `polished.md` |

If the user requests refinement of an existing normal result, preserve it as `03-draft.md` and continue review, revision, and finalization. A request for refined output already authorizes those stages; an initial draft is not its completion point. Normal mode ends with its polished result; offer another mode only when it would address a stated unmet need.

## Read only matching details

| When | Reference |
| --- | --- |
| Materializing inline/URL source, creating output directories, or handling existing output | [Workflow mechanics](references/workflow-mechanics.md) |
| Selecting a non-default style, audience, or goal | [Writing preferences](references/writing-preferences.md) |
| Normal/refined source reaches `chunk_threshold` (4000 words by default) | [Long content](references/long-content.md) |
| Refined mode, or a requested continuation after normal mode | [Refined workflow](references/refined-workflow.md) |
| Explicit `style: chinese`, `--style chinese`, or an anti-AI Chinese request | [Chinese style integration](references/chinese-style.md) |

Chinese text alone does not select `chinese` style. Keep the chosen style and author's voice unless the user requests that transformation.

## Output and invariants

Use a file source as-is; materialize inline or fetched text under `polish/{slug}.md`. Put results in `{source-dir}/{source-basename}-polished/`, preserving earlier results as specified in workflow mechanics.

- Preserve core arguments, facts, authorial stance, links, images, code blocks, and Markdown structure. Rewrite as much as the requested goal needs; do not invent evidence to support expansion.
- Adapt wording, explanation depth, flow, and tone to the selected audience and goal.
- For YAML frontmatter, rename source metadata with a camelCase `source` prefix (`url` → `sourceUrl`, `title` → `sourceTitle`), add polished metadata, skip a new `title` when the body has H1, and preserve other fields.
- Check the finished article against the source for meaning drift, missing content, broken formatting, and remaining issues relevant to the chosen mode. Fix them before delivery.
- Report a clickable path to `polished.md` and briefly state material changes or unresolved author decisions. Explain mode/style choices only when they affect the result.

## Observability boundary

Intermediate files beside the output record the article workflow; they are content artifacts, not an anonymized performance ledger. Use `rg --files <output-dir>` as a read-only inventory of the current run, then compare retained chunk files with the final merged article for coverage. There is no duration/outcome ledger, disposition writeback, retention rollup, or historical acceptance-rate command; do not claim historical model-quality statistics.
