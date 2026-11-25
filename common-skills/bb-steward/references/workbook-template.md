# Workbook template

Default path `<main checkout root>/.local/steward/<topic>.md`; if the project AGENTS.md specifies otherwise, the
project wins. If the directory is missing, run `steward_workbook.py --mode init` first; the workbook and requirement
ledger are committed only to the local git in that directory, never pushed, no MR. The three sections are fixed;
a section with no content says `无` (none). Admission criteria: SKILL.md "Workbook (工作簿)"; route states: "Closing
reconciliation (收尾对账)". When the project already has a roadmap or decision registry, the route and key-decision
sections hold only links and the current position; the example lines in the template are for projects without them.

Section headings, the `←` state keywords, the to-do table header, the to-do status values (`待办`/`已完成`), the
"why only the user" categories and `不挡` are literals parsed by `scripts/`; keep them verbatim. Free-text content in
`<…>` placeholders may be written in any language.

```markdown
# <goal in one sentence>

更新：<YYYY-MM-DD>；逐项状态、结果与材料见[要求帐](<topic>-要求帳.md)。

## 路线

- [x] <Stage 1: one sentence on the output>
- [ ] <Stage 2> ← 进行中 thr_xxx
- [ ] <Stage 3> ← 等用户
- [ ] <Stage 4> ← 定时 <MM-DD HH:MM> <what to do at that time>
- [ ] <Stage 5> ← 排在 <Stage 2> 后：<which output of Stage 2 it needs>

## 关键决策

- <YYYY-MM-DD> <decision in one sentence>. Reason: <one sentence>. Impact: <which stages or modules>.

## 用户待办

| 编号 | 状态 | 事项 | 背景 | 建议 | 为什么只能用户做 | 挡住 | 提出 | 完成 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | 待办 | <what to do> | <what it is, why the user must do it now, what happens if not; no internal codenames> | <recommended answer> | 真机线下：<device or session only the user has> | <Stage 3> | <YYYY-MM-DD> | — |
| D2 | 待办 | <what to do> | ... | ... | 凭据账号：<token or permission only the user holds> | 不挡 | <YYYY-MM-DD> | — |
| D3 | 已完成 | <what to do> | ... | — | ... | ... | <YYYY-MM-DD> | — |
```

To-do table columns: number | status | item | background | recommendation | why only the user can do it | blocks |
raised | completed.

After every edit run `steward_workbook.py --mode verify --file <workbook path>`; the script writes completion times
in Singapore time, sorts and validates; commit once it passes. Keep the route time comments the script generates.
Missing historical completion times show as `待核实` (to be verified); never guess dates.

When one project has several stewards, to-do numbers carry this steward's short prefix (e.g. `HST-D1`); conventions
shared by all stewards go in `共用约定.md` in the same directory, and key decisions hold one line
`- 共用约定见[共用约定](共用约定.md)。`

Add one line to the project `AGENTS.md` so any session can pick up:

```markdown
The steward workbook is at `.local/steward/<topic>.md` under the main checkout root (a local directory, ignored by git, not in the repo); if missing, create it with bb-steward init; if present, read it first and report only open user to-dos.
```

## Requirement ledger template

Default path `.local/steward/<topic>-要求帳.md`. Admission, when to write and status semantics: SKILL.md
"Requirement ledger (要求帐)". One table per period; update rows in place and keep historical rows; the ledger is
independent of the workbook's three sections and one-screen gate. Replace the placeholder rows before validating.

The period heading format `## <YYYY-MM-DD> 起（<topic>）`, the five column headers and the seven status values are
literals parsed by `scripts/`; keep them verbatim.

```markdown
# <goal>: user requirement ledger

## <YYYY-MM-DD> 起（<topic>）

| 日期 | 要求 | 狀態 | 結果 | 材料 |
| --- | --- | --- | --- | --- |
| <MM-DD> | <one independent request from the user> | 進行中 | <current progress or dependency> | — |
| 10-27 | Optimize CI performance | 完成 | CI 21→8 min (-62%), docs-only check 52 s | [PR #117](https://github.com/example/project/pull/117) |
```
