# article-polish

A general-purpose article polishing skill for Cursor and other AI agents.

## What it does

Improves writing with three modes:

| Mode | Workflow | Best for |
|------|----------|----------|
| **Quick** | Polish | Short texts, quick fixes |
| **Normal** | Analyze → Polish | Articles, blog posts |
| **Refined** | Analyze → Polish → Review → Finalize | Publication-quality output |

It also supports style presets, audience tuning, polish goals, long-document chunking, and persistent preferences via `EXTEND.md`.

## Upstream

This is a **derivative work** based on [baoyu-translate](https://github.com/JimLiu/baoyu-skills/tree/main/skills/baoyu-translate) from [baoyu-skills](https://github.com/JimLiu/baoyu-skills) (MIT License).

The original skill handles translation; this version repurposes the same workflow architecture (quick / normal / refined modes, chunking, `EXTEND.md` preferences) for **writing improvement**.

This is an independent project — not affiliated with or endorsed by baoyu-skills.

## License

This skill is part of [mason-skills](../../README.md) and is released under the [MIT License](../../LICENSE).

Upstream attribution and license text: [NOTICE](../../NOTICE).
