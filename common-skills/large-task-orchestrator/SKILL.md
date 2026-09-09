---
name: large-task-orchestrator
description: 用 BB 线程持续执行已有大型任务计划，直到完整交付或出现真实 blocker。
disable-model-invocation: true
---

# Large Task Orchestrator

这是流程类 Skill，仅在用户显式调用 `$large-task-orchestrator` 时运行。

当前 Agent 是 orchestrator：一个上下文大、判断力强的会话，只做调度与裁决。实际实现由便宜但可靠的
Worker 完成，完成校验由更便宜的 Validator 完成；两者都是通过 `$bb-model-routing` 派发的 BB 线程，
路由表由 `bb-dispatch` 用户配置持有。计划 JSON、Git 和线程记录承载长期状态，任何线程都可以丢弃和
替换。

只接管已存在并通过 sibling `large-task-planning` v2 校验的计划。先读
[`../large-task-planning/references/plan-format.md`](../large-task-planning/references/plan-format.md)
与[`../bb-model-routing/SKILL.md`](../bb-model-routing/SKILL.md)。角色边界、并行规则和 blocker 规则
以[联合核心设计](../../docs/large-task-system-design.md)为准，本文只写执行流程。

## 上下文纪律

Orchestrator 的上下文是最贵的资源，也是长时运行最大的风险源。规则：

- 不读完整 diff、测试日志或线程全文。只看 `git status --short`、`git diff --stat`、Worker 与 Validator
  的结构化报告，以及 `epic_story.py status --json`。
- 需要看细节时派 economy 只读线程去看，让它回摘要。
- 每个状态转换点（领取后、Worker 回报后、Validator 回报后、checkpoint 后）都把当前阶段、线程 ID 和
  精确下一步写回 Story Handoff。不要等 compaction 来临才写：你无法预知它何时发生。
- 恢复顺序固定为 Agent JSON → Git → `bb thread show <id>`。不要求重新读取子线程对话。

## 启动或恢复

1. 读取适用的 `AGENTS.md`、`SPEC.md`、`STATUS.md` 与 `agent/plan.json`；检查当前 branch、
   `git status --short`、`git worktree list` 与已有提交。保留无关并发改动。
2. 运行：

```bash
python3 <planning-skill>/scripts/epic_story.py check \
  --plan <topic>/agent/plan.json --stories-dir <topic>/agent/stories
python3 <planning-skill>/scripts/epic_story.py status \
  --plan <topic>/agent/plan.json --stories-dir <topic>/agent/stories --json
```

3. 对每个 `in_progress` Story，读 Handoff 里记录的线程 ID，用 `bb thread show <id> --json` 看线程
   状态与最终输出，再对照 `git diff --stat`。线程仍在跑就 `wait`；线程已结束或丢失就把 Handoff 里的
   事实交给 fresh replacement Worker。不要因为对话压缩而重新领取。
4. 确认 `bb status --json` 指向目标项目和环境，`bb-dispatch --dry-run` 通过。配置缺失先按
   `$bb-model-routing` 补齐，再开始循环。

## 选择能力档

派发 Worker 前先定本轮能力档，直接映射为 `bb-dispatch --difficulty`。用户指定模型或 reasoning 时
转成配置别名或 `--agent`/`--reasoning` 传入，不写进任务文本。难度从当前 Story 与已有失败证据现场
判定，不写入计划 JSON。

| 能力档 | `--difficulty` | 适用 |
| --- | --- | --- |
| economy | `simple` | 验收可脚本化、write_scope 窄、已有测试或黄金案例可当 oracle、无设计分叉 |
| standard | `medium` | 常规实现；seam 清楚，但需要跨文件判断 |
| strong | `complex` | 跨模块设计、模糊契约、安全或数据迁移、同一 Story 已因能力失败、`final_story` 整合 |

默认取最低够用档。Validator 固定 `--difficulty simple --kind test`，不随 Worker 升档。排障型
Story 加 `--kind debug`。

同一 Story 上较低档 Worker 失败，且原因是实现能力（不是环境、权限、配额）时升一档再派。strong 仍
失败则拆分、换路线或按 blocker 规则问用户。长时间 strong 循环或并行多个 strong Worker 属于显著
成本，先问用户。Validator 失败换同档 replacement，不升档。路由不可用或配额耗尽时按
`$bb-model-routing` 报告，不自行换模型。

## 自主循环

持续执行下面的循环，不在 Story 之间停下来询问是否继续。派发、等待、取报告和 follow-up 的具体命令
见[BB 派发循环](references/bb-dispatch-loop.md)。

1. **选择 frontier。** 从 `status --json` 的 `ready` 中选择最能降低 Goal 风险的 Story；通常取第一项。
2. **原子领取。** `transition --expect todo --status in_progress --owner <worker-thread-或-run-id>`。
   预期状态失败就重新读取计划并协调并发事实。
3. **派发 fresh Worker。** 用 planning 的 `brief` 提取执行包，加上仓库规则、当前基线、并发 write
   scope 和下面的 Worker 报告契约，组成 `--task`。要求它先验证现状，在指定公开 seam 上按 red → green
   的纵向小循环实现并运行相关测试。不复制会话历史或全部计划。派发后立刻把线程 ID 写回 Handoff。
4. **等待并取报告。** `bb thread wait` 到 idle，`bb thread output` 取报告。线程卡在交互上时用
   `bb thread interactions` 处理：属于已授权范围的直接批准；越权或需要用户决定的按 blocker 规则。
5. **核对边界。** 只看 `git status --short` 和 `git diff --stat`：确认没有越界 write_scope、没有丢失
   并发改动、不是只改了报告。Worker 回复不是完成证明。
6. **完成校验。** 按 Story 分流：
   - economy 且 Acceptance 全部可由脚本或测试直接判定：orchestrator 派 economy 只读线程跑验收命令并
     回摘要，或自己跑输出短小的命令；不派 Validator。
   - 其他 Story：派未参与实现的 Validator（`--difficulty simple --kind test`），固定本轮基线与 diff，
     按下面的 Validator 契约逐条核对 Acceptance 并跑必要测试。
7. **裁决。** 全部 Acceptance 成立则完成 Story。有明确小遗漏则把精确遗漏用 `bb thread tell` 发回
   同一 Worker 线程修复，再复核。Validator 报告的新事实由 orchestrator 判断：新独立结果用插入 Story
   承接；Goal 或用户边界失效才请求用户。
8. **完成 Story。** 用 planning 的 `write` 更新 Story JSON：已证明的 Acceptance 设为 `passed=true`，
   Handoff 记录可观察结果、验证命令与结论、线程 ID、残余风险和下一 Story 输入。随后
   `transition --status done`、`check`，并创建包含 Story ID 的 Git checkpoint。
9. **继续。** 重新计算 frontier，直到 `final_story` 完成或没有可推进工作。

## 报告契约

写进 `--task` 末尾，要求线程最终回复只包含这段。事实仍以工作区、测试和计划为准。

Worker：

```text
Result: worker_done | blocked | failed
Changed: <可观察结果和文件>
Verified: <命令及结果>
Remaining: <未完成工作或 none>
Handoff: <替换 Worker 继续所需上下文>
```

Validator：

```text
Verdict: PASS | FAIL
Acceptance:
- AC-01: holds | missing — <命令或观察证据>
Gaps: <遗漏、越界或与黄金案例冲突的事实；none>
New facts: <推翻后续 Story 前提或计划假设的发现；none>
```

Validator 只确认 Story 是否真正完成，不做代码审查、风格或重构建议。它意外写了文件时不接受其
结论；先隔离该改动，再派新的 Validator。计划级判断（插入 Story、重规划）由 orchestrator 做，需要
大局视角时另派线程显式调用 `$story-direction-review`。

## 计划演化与 blocker

Orchestrator 在既定 Goal 和用户边界内拥有实现路径，可以重排、插入、合并或改写未开始的 Story。
修改 Story 结果或验收时递增 `intent_version`，保留完成证据和既有 ID；插入使用 `STORY-NN.M`。

预计需要 strong 才能完成的 Story 首先是拆分信号，不是升档信号。

询问用户的条件、恢复优先级和"不得降低黄金判据"见联合核心设计。提问时给出证据、已尝试恢复、
影响范围和一个最小决策，并先继续其他独立 ready Story。

## 收口与交付

完成 `final_story` 前，在同一 acceptance commit 上运行全部黄金案例和跨 Story 整合检查（派线程跑，
回摘要）。然后：

1. 运行 `completion-check`，确认全部 Story、验收勾选、依赖与黄金覆盖收口。
2. 检查 `git diff --stat`、branch、`git status --short`、`git worktree list` 与待推送提交，只提交
   授权范围。
3. 推送当前目标分支到明确 upstream；不 force-push、不绕过 hook、不猜测歧义 remote。
4. 查询真实 upstream，确认其 commit 等于本地交付 HEAD。

只有计划完成门禁、整合测试、授权提交和远端 HEAD 都成立时报告完成。

## 可观测性

没有独立的运行历史账本。每个 Worker / Validator 线程由 `bb-dispatch` 创建并关联到当前父线程，
BB 已持久化 provider、模型、状态、耗时和最终输出；Story Handoff 记录该 Story 用过的线程 ID 与
结论。复盘用：

```bash
bb thread list --parent-thread <orchestrator-thread-id> --json
bb thread show <thread-id> --json
```

缺口：没有跨运行的成功率聚合，升档决策只留在 Handoff 文本里。
