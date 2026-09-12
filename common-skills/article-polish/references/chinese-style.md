# Chinese style integration

## Chinese Anti-AI Module

This module is **opt-in**: it activates only when `style: chinese` is explicitly selected (via `--style chinese`, EXTEND.md, or an explicit anti-AI request). It is never auto-applied just because the content is Chinese — under any other style the author's voice is preserved as usual. When active, load the rule source [references/zh/anti-ai.md](zh/anti-ai.md). It is the single source of truth for Chinese polishing and contains two functional halves that map onto the existing workflow steps:

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
