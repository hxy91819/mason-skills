---
name: readiness-fix
description: 修复最近一次 readiness 报告中失败的信号；无报告时先问是否生成。仅在用户显式调用 $readiness-fix 时运行。
disable-model-invocation: true
---

# Readiness Fix

这是流程类 Skill，默认仅在用户显式调用 `$readiness-fix` 时运行。移植自 Factory Droid 内置
`/readiness-fix`；与原版的唯一差异是删除了云端报告读取：失败信号一律读
`$readiness-report` 的**本地**存储，不调用任何远端 API。

正文为原版提示词原文（三个分支模板已实例化），评估与修复语义以本文为准。

**Local report source:** the latest run in
`${XDG_CACHE_HOME:-~/.cache}/readiness-report/<repo-slug>/history.json` plus its
`reports/<run-id>.json`. Use [`scripts/pick_failing.py`](scripts/pick_failing.py) to list
the failing signals (id, name, current score, category) — it reads local files only.
Wherever the branches below say "the failing signals listed above", that list is the
output of `pick_failing.py` (the original inlined a Report Summary and Failing Signals
block from the cloud report; see 本地运行差异 at the end).

---

The following block is the original i2I text the binary appends to every branch:

## Fix Instructions

For each signal you are fixing:

1. Explore the repository to understand the current state related to the signal
2. Make **substantive improvements** to the codebase that genuinely address the signal
3. Verify your fix addresses the issue (e.g., run linter if fixing lint_config, run tests if adding tests)
4. Keep changes focused on the signal - don't refactor unrelated code

## Completion

- Provide a succinct summary of what you changed and why it genuinely improves the codebase

## CRITICAL: Quality Standards

Your fix must **genuinely improve the codebase**. Do NOT use workarounds or shortcuts:

- **NO** empty placeholder files (e.g., empty test files, stub configs)
- **NO** minimal implementations that technically pass but provide no real value
- **NO** disabling checks or adding skip markers to pass validation
- **NO** trivial changes that game the metric without improving quality

Examples of BAD fixes:

- Adding an empty `test.js` file to satisfy "has tests" criterion
- Creating a `.eslintrc` that disables all rules
- Adding `// @ts-nocheck` to satisfy TypeScript requirements

Examples of GOOD fixes:

- Writing actual unit tests with meaningful assertions for existing code
- Configuring ESLint with appropriate rules for the project's language/framework
- Adding proper TypeScript types to improve type safety

---

## Branch 1 — Previous report exists, user named signals

You are fixing failing Agent Readiness signals. Agent Readiness evaluates how well a repository supports autonomous AI agents working on the codebase.

**Repository:** `<the git repository this skill runs in>`

## User Requested Signals

The user asked to fix: "`<signals named by the user, e.g. 'lint_config' or 'the cyclomatic complexity criteria'>`"

## Your Task

1. Semantically match the user's requested signals ("<as named>") to the failing signals listed above.
   - Match by criterion ID (e.g., "lint_config"), criterion name (e.g., "Linter Configuration"), or semantic meaning (e.g., "the cyclomatic complexity criteria" matches `cyclomatic_complexity`).
   - If a requested signal already passes, note that it passes and skip it.
   - If a requested signal doesn't match any known criterion, note that and skip it.
2. For each matched failing signal, fix it in sequence.

The repair standard for each signal is its evaluation contract in
[../readiness-report/signals.md](../readiness-report/signals.md): the fix is done when
re-evaluating that criterion by its own rules would pass. Fix one signal at a time; after
each fix, report what changed and the verification evidence (command and exit code when
the criterion has one). The Fix Instructions and Quality Standards blocks above are
part of this contract.

## Branch 2 — Previous report exists, no signals named

You are fixing failing Agent Readiness signals. Agent Readiness evaluates how well a repository supports autonomous AI agents working on the codebase.

**Repository:** `<the git repository this skill runs in>`

## Your Task

**Step 1:** Group the failing signals above by their category. Ask the user which category they want to fix using the AskUser tool. Only show categories that have at least one failing signal.

**Step 2:** Based on the chosen category, present each failing signal in that category as an option in a single AskUser call. Each option is exactly one signal (with its name and current score). The user picks one signal to fix. Do NOT say "select all that apply" or "select one or more".

After the user selects a signal, fix it.

The same repair standard as Branch 1 applies: re-evaluation by the criterion's own contract in signals.md must pass.

## Branch 3 — No previous report found

You are fixing failing Agent Readiness signals. Agent Readiness evaluates how well a repository supports autonomous AI agents working on the codebase.

**Repository:** `<the git repository this skill runs in>`

## Context

No previous readiness report was found for this repository.

## Your Task

**Step 1:** Ask the user using the AskUser tool:

> "No readiness report found for this repository. How would you like to proceed?"

Options:

- "Generate a full report first, then fix failing signals"
- "Skip the report and fix signals directly"

**If the user chooses to generate a report first:**

Follow the readiness report generation instructions in [../readiness-report/SKILL.md](../readiness-report/SKILL.md) to evaluate the repository and store the report locally. Then:

- If the user originally requested specific signals: semantically match the user's requested signals to the failing signals and fix each matched failing signal.
- Otherwise: present the failing signals to the user via the AskUser tool for selection, and fix the selected ones.

**If the user chooses to skip the report:**

- If the user originally requested specific signals: explore the repository, identify gaps related to "`<as named>`", and fix them directly.
- Otherwise:
  - **Step 2:** Ask the user which category to fix using the AskUser tool:
    "Which category of signals would you like to fix?"
    Options: the category names from [../readiness-report/signals.md](../readiness-report/signals.md).
  - **Step 3:** Present the signals from the chosen category in a single AskUser call with one question. Each option is exactly one signal. The user picks one signal to fix. Do NOT say "select all that apply" or "select one or more" -- the user picks a single signal. IMPORTANT: The AskUser tool has a hard limit of 10 options per question. If the category has more than 10 signals, only include the most impactful/common ones (up to 10). Use the catalog below as reference: the signals grouped by category in signals.md.
  - After the user selects a signal, explore the repository and fix it.

## All passing

If every signal in the latest report passes, output exactly:

> All readiness signals are passing for this repository. No fixes needed.

## Repair rules

- Fixes fit the audited repository's existing stack and conventions; do not introduce tools or files the repository does not need just to pass a signal.
- A signal that fails only because an external precondition is unmet (no admin access, no CLI) is reported as unfixable locally with the reason — never faked as passing.
- Do not touch the user's concurrent uncommitted changes; do not commit or push unless the user explicitly asks in this session.
- After all targeted signals are fixed, suggest re-running `$readiness-report` to compare scores; scoring and history belong to `$readiness-report`, this skill writes neither.

## 本地运行差异（与原版的不同，均已如实记录）

- 原版从 Factory 云端拉取最近报告；本 skill 只读本地 `readiness-report` 缓存
  （`pick_failing.py` 或直接读 `history.json` / `reports/*.json`）。
- 原版每个分支内嵌 Report Summary（Repository/Level/Score）与逐条 Failing Signals
  清单（来自云端报告）；本地版以 `pick_failing.py` 输出替代，正文 "the failing
  signals listed above" 指该输出。
- 原版"无报告"分支内嵌的完整 report 生成指令（云端版），本地替换为引用
  `../readiness-report/SKILL.md` 的本地存储流程。
- 原版 Fix Instructions / Completion / Quality Standards 块原样保留（见上方），
  未做删改。
