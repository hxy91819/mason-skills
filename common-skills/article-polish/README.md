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

For Chinese writing, the opt-in `chinese` style loads a dedicated anti-AI rule set that strips the four-layer fingerprints of AI-generated Chinese and rewrites toward a human, direct voice. By default the author's voice is preserved; the `chinese` style is applied only when explicitly selected. See [references/zh/anti-ai.md](references/zh/anti-ai.md).

## License

Part of [mason-skills](../../README.md) — [MIT License](../../LICENSE).

**Upstream:** Derivative work based on [baoyu-translate](https://github.com/JimLiu/baoyu-skills/tree/main/skills/baoyu-translate) from [baoyu-skills](https://github.com/JimLiu/baoyu-skills) (MIT, Copyright Jim Liu). Independent project, not affiliated with baoyu-skills.
