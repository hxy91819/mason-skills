---
name: readiness-fix
description: 修复最近一次 readiness 报告中失败的信号；无报告时先问是否生成。仅在用户显式调用 $readiness-fix 时运行。
disable-model-invocation: true
---

# Readiness Fix

这是流程类 Skill，默认仅在用户显式调用 `$readiness-fix` 时运行。移植自 Factory Droid 内置
`/readiness-fix`，删除了向 Factory 云端读取/上报报告的部分：报告一律读
`$readiness-report` 的**本地**存储，修复过程不调用任何远端 API。

你是 Readiness 修复执行者。Agent Readiness 评估代码库对自治 agent 的友好程度；本 skill 的工作
是把其中**失败的信号**逐个修到通过。这是会修改被审仓库的流程类操作，修复前必须让用户选定目标。

## 0. 数据来源与前提

- 失败信号来自**最近一次本地报告**：
  `${XDG_CACHE_HOME:-~/.cache}/readiness-report/<repo-slug>/history.json` 的 `latest` 记录，
  完整逐信号结果在 `reports/` 下对应 `<run-id>.json`。
- 用 [`scripts/pick_failing.py`](scripts/pick_failing.py) 读取本地报告并输出失败信号清单
  （ID、名称、当前分数、类别）。**不发任何网络请求。**
- 无本地报告 → 走第 3 节的"无报告"分支。
- 全部信号通过 → 输出"All readiness signals are passing for this repository. No fixes needed."，
  结束。

## 1. 有报告：确定修复目标

### 情形 A — 用户指定了信号

用户点名要修的信号（如 `$readiness-fix lint_config`、"修一下测试那几项"）先做**语义匹配**：

- 按 criterion ID 匹配（如 `lint_config`）、按名称匹配（如 "Linter Configuration"）、按语义匹配
  （如"圈复杂度那条"匹配 `cyclomatic_complexity`）。
- 点名的信号已经通过：注明"已通过"，跳过。
- 点名内容对不上任何已知信号：注明"未匹配到"，跳过。

匹配出的失败信号**逐个按序修复**，修完一个再修下一个。

### 情形 B — 用户未指定信号

两级选择，都用宿主的用户交互工具（AskUser 或等价物），每问只让用户**单选**——
不要写"可多选"或"选一个或多个"：

1. **选类别**：把失败信号按 signals.md 的类别分组，只列出至少有一个失败信号的类别，问
   "Which category of signals would you like to fix?"
2. **选信号**：选定类别后，单次交互列出该类别**每个失败信号**作为选项（名称 + 当前分数），
   用户挑一个。**交互工具单题选项上限 10 个**；类别内失败信号超过 10 个时，只列影响最大/
   最常见的（至多 10 个），以信号目录为参照。

用户选定信号后，探索仓库并修复它。

## 2. 修复执行

对每个目标信号：

1. 重读该信号在 [../readiness-report/signals.md](../readiness-report/signals.md) 的评估口径，
   修复标准就是"按该口径重新评估会通过"。
2. 探索仓库，定位缺口，实施最小、贴合项目习惯的修复。配置类信号（如 linter、formatter）
   通常落在项目标准配置位置；文档类信号落到 README/AGENTS.md 的对应段落。
3. 有验证命令的信号（如 `unit_tests_runnable`）修复后必须实际运行命令确认退出码为 0。
4. 一次只修一个信号；修完汇报该信号的修复内容与验证证据，再进入下一个。

边界：

- 修复必须贴合被审仓库的现有技术栈与约定，不为了过信号而引入仓库不需要的工具或文件。
- Skippable 信号因外部前提不满足（无权限、无 CLI）而失败时，如实报告"本地无法修复原因"，
  不伪造通过。
- 修复不得越权：不动用户的并发未提交改动，不提交/推送，除非用户在本次会话明确要求。

## 3. 无报告分支

本地没有任何报告时，先问用户：

> No readiness report found for this repository. How would you like to proceed?

- **"Generate a full report first, then fix failing signals"**：先按 `$readiness-report` 的完整
  流程生成报告（读 [../readiness-report/SKILL.md](../readiness-report/SKILL.md)），再回到
  第 1 节继续修复。
- **"Skip the report and fix signals directly"**：
  - 用户原本点名了信号：探索仓库，定位与该信号相关的缺口，直接修复。
  - 未点名信号：把信号目录按类别列出（复用 signals.md），按第 1 节情形 B 的两级选择流程
    让用户挑类别与信号，然后修复。

## 4. 收尾

- 逐信号汇报：修复内容、验证命令与结果（证据要可复核——命令与退出码）。
- 全部目标信号修完后，建议用户重跑 `$readiness-report` 生成新报告对比分数；用户同意时
  可代跑。修复本身不写历史记录——评分与历史归 `$readiness-report` 拥有。

## 不变量

- 失败信号清单只从**本地**报告或 signals.md 目录读取；不调用任何远端上报/查询 API。
- 用户没选定目标信号前不开始修复；选择交互保持单选语义。
- 修复证据可复核：每条修复给出文件位置与（有命令时的）验证命令及退出码。
- 修复保持最小与贴栈：不引入信号通过以外的仓库变更，不顺手重构。
- 被审仓库中用户已有的未提交改动一律保留，不搬移、不覆盖。
