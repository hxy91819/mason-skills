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
和[联合设计](../../docs/large-task-system-design.md)。计划 JSON 与 Git 是权威状态；每个 `(仓库, 计划)` 的
`.local/large-task-orchestrator/<topic-slug>/` 保存可回看的运行事实。

## 生命周期用法

1. 先确定用户指定的计划；未指定时只能使用当前仓库唯一的计划。阅读仓库规则、`SPEC.md`、`STATUS.md`，检查
   分支、`git status --short` 和 `git worktree list`，保留并发改动。然后只对这个 `(仓库, 计划)` 查询状态：

```bash
python3 <orchestrator-skill>/scripts/large_task_driver.py status \
  --plan <topic>/agent/plan.json --stories-dir <topic>/agent/stories
```

2. 若 `status` 显示 driver 仍在运行，把 completed/total、每张 in-progress Story 的阶段、线程 ID 和难度翻译给
   用户；不要自己运行主循环，也不要读线程全文。若 `last_stop` 非空或有 blocked Story，说明事实，并只向用户索取
   继续所需的最小决定。需要停止时使用 `stop [--wait]`；它只在当前 `run_once` 结束后退出，不会中断 BB 线程。

3. 若没有运行中的 driver，用 `start` 启动指定计划。`start` 自己会先执行计划校验和 `bb-dispatch --dry-run`，
   然后在新 session 中派生后台 `run`；本轮到此结束，向用户报告 pid、日志路径和后续状态命令。不要在本轮改用
   前台 `run` 等待结果。

```bash
python3 <orchestrator-skill>/scripts/large_task_driver.py start \
  --plan <topic>/agent/plan.json \
  --stories-dir <topic>/agent/stories \
  --repository <repo-root> \
  --environment <bb-environment-id>
```

同一计划已有存活 pid 时 `start` 以退出码 4 拒绝重复启动；陈旧 pid 自动覆盖。不同仓库或同一仓库不同计划使用
独立的状态目录与锁，可以同时运行。计划中的 `owner` 保留 Worker 线程 ID；遗失计划本地状态时，driver 会从计划
和 BB 线程恢复。仅在排障或定时任务需要前台单次推进时才用 `run` 或 `start --foreground` 加 `--once`。

## 正常循环与异常

正常路径不调用强模型：driver 选择 ready frontier、领取 Story、派 Worker、核对改动；按配置决定是否派
Validator；通过后更新 Handoff、刷新投影并创建只含本 Story 路径的 checkpoint。

发生 Worker `blocked`/`failed`、线程 error、待处理 interaction、越界写入、空改动、报告无法解析或
Validator 多轮失败时，driver 才派 `complex` Judge。Judge 只能选择 `retry`、`escalate`、`patch`、
`block`、`replan` 或 `stop`。`block` 后继续其他 ready Story；`replan` 后重新校验计划；`stop` 或没有
ready Story 时退出并把最小原因写到 stderr。

不要手动篡改 driver 状态文件、Story 的 `owner` 或 Handoff 来跳过这些状态转换。要处理停下原因，先读 driver
`status --json`、计划状态和该计划的 jsonl；只有在既定 Goal 和授权内作出必要处理后，才在下一次本 Skill 调用时
按上述流程重新 `start`。需要凭据、权限、外部/破坏性动作、显著成本或稳定边界变更时才请用户决定。

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

契约字段以中文为准，因为 Worker 通常运行在要求中文回复的系统提示下；driver 同时接受旧的英文字段名
和常见同义写法（如「已变更」「剩余工作」「交接说明」），值也接受「完成 / 通过 / 成立」等同义词。
Worker 回复不可解析时 driver 先让同一线程按契约重发一次，再派 Judge。

Worker 的「变更」「验证」最多各 8 行，「交接」最多 400 字符；最终只回复：

```text
结果：worker_done | blocked | failed
变更：<可观察结果和文件>
验证：<命令及结果>
剩余：<未完成工作，或 无>
交接：<下一位 Worker 所需事实>
```

Validator 只读核验 Acceptance，不做代码审查。driver 在任务里列出自己维护的计划状态与投影路径，
Validator 不得因这些路径判越界：

```text
结论：PASS | FAIL
验收：
- AC-01: holds | missing — <命令或观察证据>
缺口：<遗漏、越界或黄金案例冲突；或 无>
新事实：<推翻后续假设的发现；或 无>
```

Judge 只回复一个动作：

```text
动作：retry | escalate | patch | block | replan | stop
说明：<给 driver 或用户的事实>
```

## 常用参数与退出码

- `--default-difficulty simple|medium|complex`：Story 没有既有档位时的首轮档位。
- `--validator standard-up|always`：默认跳过 simple Story 的 Validator；`always` 强制每张都验。
- `--max-patch-rounds`、`--max-attempts`、`--max-judge-rounds`：恢复上限，耗尽后停给用户。
- `--poll-seconds`：每次 `bb thread wait` 的节奏；`--wait-timeout` 是该轮等待上限。
- `--allow-empty-story`：仅纯验证 Story 可无业务改动完成。
- `--once`、`--max-stories N`：适合定时或受限批次；`--push` 在全部完成后推送并核对 upstream HEAD。
- `status [--json]`：只读显示进程、计划进度、in-progress/blocked Story、最近日志和上次停止原因；不读取线程全文。
- `stop [--wait]`：向该计划的 pid 发送 SIGTERM；`--wait` 最长等待 `--wait-timeout` 秒。

退出码 `0` 表示完成或本轮受控结束；`2` 表示 driver/环境契约错误；`3` 表示需用户处理，原因在 stderr；`4` 表示
同一计划已有存活 driver。

维护 driver 的内部状态、BB 回执兼容性和等待语义时，读
[driver 循环](references/bb-dispatch-loop.md)。
