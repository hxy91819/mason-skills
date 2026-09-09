---
name: large-task-orchestrator
description: 启动确定性 driver 执行大型任务计划，并在它停下时处理用户决策。
disable-model-invocation: true
---

# 大型任务 driver

这是流程类 Skill，仅在用户显式调用 `$large-task-orchestrator` 时运行。它只接管已经通过
`large-task-planning` v2 校验的计划：脚本是控制面，Worker、Validator 和异常时的 Judge 都是经
`bb-dispatch` 创建的短生命周期 BB 线程。

开始前阅读相邻的 `large-task-planning` 计划格式、[`bb-model-routing`](../bb-model-routing/SKILL.md)
和[联合设计](../../docs/large-task-system-design.md)。计划 JSON 与 Git 是权威状态；BB 线程记录和
`.local/large-task-orchestrator/driver-log.jsonl` 是可回看的运行事实。

## 启动与恢复

1. 阅读仓库规则、`SPEC.md`、`STATUS.md`，检查分支、`git status --short` 和 `git worktree list`；保留
   并发改动。
2. 校验计划与路由：

```bash
python3 <planning-skill>/scripts/epic_story.py check \
  --plan <topic>/agent/plan.json --stories-dir <topic>/agent/stories
<routing-skill>/scripts/bb-dispatch --difficulty medium \
  --task '校验 driver 路由；不创建线程。' --dry-run
```

3. 在目标 BB 项目与环境中启动；`bb-dispatch` 会将新线程关联到当前父线程。

```bash
python3 <orchestrator-skill>/scripts/large_task_driver.py \
  --plan <topic>/agent/plan.json \
  --stories-dir <topic>/agent/stories \
  --repository <repo-root> \
  --environment <bb-environment-id>
```

重复运行同一命令即可恢复。计划中的 `owner` 保留 Worker 线程 ID；遗失 `.local/` 状态时，driver 会从
计划和 BB 线程恢复。定时任务使用 `--once`，每次只推进一个可观察步骤。

## 正常循环与异常

正常路径不调用强模型：driver 选择 ready frontier、领取 Story、派 Worker、核对改动；按配置决定是否派
Validator；通过后更新 Handoff、刷新投影并创建只含本 Story 路径的 checkpoint。

发生 Worker `blocked`/`failed`、线程 error、待处理 interaction、越界写入、空改动、报告无法解析或
Validator 多轮失败时，driver 才派 `complex` Judge。Judge 只能选择 `retry`、`escalate`、`patch`、
`block`、`replan` 或 `stop`。`block` 后继续其他 ready Story；`replan` 后重新校验计划；`stop` 或没有
ready Story 时退出并把最小原因写到 stderr。

不要手动篡改 driver 状态文件、Story 的 `owner` 或 Handoff 来跳过这些状态转换。要处理停下原因，先读
stderr、计划 `status --json`、driver jsonl 与相关 `bb thread show/output`，在既定 Goal 和授权内处理后
重启 driver；需要凭据、权限、外部/破坏性动作、显著成本或稳定边界变更时才请用户决定。

## 能力档

| 能力档 | `--difficulty` | 使用条件 |
| --- | --- | --- |
| economy | `simple` | write scope 窄，验收可直接脚本化，没有设计分叉 |
| standard | `medium` | 常规跨文件实现，公开 seam 和验收明确 |
| strong | `complex` | 已证明的能力不足、跨模块不确定性或复杂整合 |

默认从最低足够档开始。Validator 固定 `simple --kind test`；排障 Worker 使用 `--kind debug`。`strong`
持续失败是重拆 Story 或请求决定的信号，不是无限升档的理由。实际 provider、模型、reasoning 和权限由
用户的 `bb-model-routing` 配置决定，不能写进任务文本。

## 报告契约

Worker 的 `Changed`、`Verified` 最多各 8 行，`Handoff` 最多 400 字符；最终只回复：

```text
Result: worker_done | blocked | failed
Changed: <可观察结果和文件>
Verified: <命令及结果>
Remaining: <未完成工作或 none>
Handoff: <下一位 Worker 所需事实>
```

Validator 只读核验 Acceptance，不做代码审查：

```text
Verdict: PASS | FAIL
Acceptance:
- AC-01: holds | missing — <命令或观察证据>
Gaps: <遗漏、越界或黄金案例冲突；none>
New facts: <推翻后续假设的发现；none>
```

Judge 只回复一个动作：

```text
Action: retry | escalate | patch | block | replan | stop
Note: <给 driver 或用户的事实>
```

## 常用参数与退出码

- `--default-difficulty simple|medium|complex`：Story 没有既有档位时的首轮档位。
- `--validator standard-up|always`：默认跳过 simple Story 的 Validator；`always` 强制每张都验。
- `--max-patch-rounds`、`--max-attempts`、`--max-judge-rounds`：恢复上限，耗尽后停给用户。
- `--poll-seconds`：每次 `bb thread wait` 的节奏；`--wait-timeout` 是该轮等待上限。
- `--allow-empty-story`：仅纯验证 Story 可无业务改动完成。
- `--once`、`--max-stories N`：适合定时或受限批次；`--push` 在全部完成后推送并核对 upstream HEAD。

退出码 `0` 表示完成或本轮受控结束；`2` 表示 driver/环境契约错误；`3` 表示需用户处理，原因在 stderr。

维护 driver 的内部状态、BB 回执兼容性和等待语义时，读
[driver 循环](references/bb-dispatch-loop.md)。
