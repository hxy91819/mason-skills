---
name: large-task-orchestrator
description: 启动确定性 driver 执行大型任务计划，并在它停下时处理用户决策。
disable-model-invocation: true
---

# 大型任务 driver

这是流程类 Skill，仅在用户显式调用 `$large-task-orchestrator` 时运行。它只接管已经通过
`large-task-planning` v2 校验的计划：脚本是控制面，Worker、Validator 和异常时的 Judge 都是经
`bb-dispatch` 创建的 BB 线程。Worker 和 Validator 按轮次独立；每张 Story 的 Judge 使用一个独立会话，
后续裁决在同一会话续聊。

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

正常路径由 driver 选择 ready frontier、领取 Story、派 Worker、核对 Git 改动事实，再派 Validator 判断
Acceptance、Story 边界和 Worker 路径归属；通过后更新 Handoff、刷新投影并只 checkpoint Validator
确认归属的 Worker 路径。

发生 Worker `blocked`/`failed`、线程 error、待处理 interaction、空改动、报告无法解析或
Validator 多轮失败时，driver 才启用 `complex` Judge；同一 Story 后续异常复用该会话，线程失效时才替换。
Judge 只能选择 `retry`、`escalate`、`patch`、
`block`、`replan` 或 `stop`。`block` 后继续其他 ready Story；`replan` 后重新校验计划；`stop` 或没有
ready Story 时退出并把最小原因写到 stderr。

不要手动篡改 driver 状态文件、Story 的 `owner` 或 Handoff 来跳过这些状态转换。要处理停下原因，先读 driver
`status --json`、计划状态和该计划的 jsonl；只有在既定 Goal 和授权内作出必要处理后，才在下一次本 Skill 调用时
按上述流程重新 `start`。需要凭据、权限、外部/破坏性动作、显著成本或稳定边界变更时才请用户决定。

旧运行若已丢失 dirty baseline，且 Judge 或用户已经确认该 Worker 实际修改的精确路径，使用
`repair-baseline --story <id> --worker-path <path>...` 恢复；命令只接受仍为 dirty、且不属于 Driver 计划
状态的路径，并要求 driver 已停止、Story 已恢复为 `in_progress`。它把其余 dirty 路径保留为共享基线。
不要直接编辑 `.local` 状态文件。

## 能力档

Story 的首轮 `difficulty` 与 `kind` 由 [`large-task-planning`](../large-task-planning/SKILL.md) 定义；driver
只消费它们并在 Judge 升档后覆盖实际难度。Validator 固定 `simple --kind test`，Judge 固定
`complex --kind judge`，通过 `bb-model-routing` 的 `defaults.judge` 与 complex Worker 分别配置。

## 报告契约

各角色的自然语言终答都不是控制协议。任务内的一次性命令调用 `scripts/large_task_report.py`，向 driver
指定路径提交 JSON；脚本严格校验字段、枚举、长度和执行身份，以 `0600` 原子写入。Worker、Validator
报告缺失或无效时只让同一线程重交一次；Worker 仍失败才派 Judge，Validator 仍失败则受控停止。Judge
同样只允许补交一次，仍失败就受控停止。

Worker 提交的 payload 只有以下字段，不接受额外字段：

```json
{
  "result": "worker_done | blocked | failed",
  "changes": [{"path": "仓库相对路径", "summary": "可观察变更"}],
  "verification": [{"command": "实际命令", "outcome": "passed | failed | not_run", "summary": "结果"}],
  "remaining": [],
  "handoff": "下一位 Worker 所需事实"
}
```

`changes`、`verification` 和 `remaining` 各最多 8 项，`handoff` 最多 400 字符。`worker_done` 至少有一项
verification；`blocked` 与 `failed` 至少有一项 remaining。

Validator 只读核验 Acceptance，并依据 Outcome、Acceptance、边界和实际 Git 改动判断是否夹带无关或其他
Story 的工作；计划中的 `write_scope` 只是预估线索，不是文件白名单。共享工作区的新 dirty 文件只是候选增量，
Validator 应以 Worker 的 BB `turn/diff` 确认归属，不得凭 mtime 或活跃时间窗口推断；无法归属的并行改动记为
新事实，不判当前 Story 失败。报告绑定当前 Worker attempt、Story intent version 和 validation round；
Acceptance ID 必须与计划顺序、集合完全一致：

```json
{
  "verdict": "PASS | FAIL",
  "acceptance": [{"id": "AC-01", "outcome": "holds | missing", "evidence": "实际证据"}],
  "worker_paths": ["Validator 从 Worker turn diff 确认归属的精确 dirty 文件路径"],
  "gaps": [],
  "new_facts": []
}
```

Judge 报告再绑定 judge round，动作仍限制在固定集合：

```json
{
  "action": "retry | escalate | patch | block | replan | stop",
  "note": "给 driver 或用户的事实与理由"
}
```

三类线程最终终答只需通知结构化报告已提交；driver 不从终答文本提取任何状态或决定。

## 常用参数与退出码

- `--default-difficulty simple|medium|complex`：Story 缺少 `difficulty` 时的首轮档位；Story 的值优先，Judge 升档结果再优先。
- `--kind general|debug`：Story 缺少 `kind` 时的 Worker 派发类型；Story 的值优先。
- `--validator always|standard-up`：默认每张 Story 都验；显式 `standard-up` 才跳过 simple Story。
- `--max-patch-rounds`、`--max-attempts`、`--max-judge-rounds`：恢复与裁决轮次上限，耗尽后停给用户。
- `--stall-minutes`（默认 90）：单个 busy 线程超过此时长会被停止；Worker 走一次 retry 后再交 Judge，Validator 改派。
- `--no-progress-hours`（默认 3）：本次 `run` 启动后若没有新的 `story.done` 超过此时长，driver 以退出码 3 停下。
- `--max-judges-total`（默认 12）、`--max-workers-total`（默认 0，即 Story 总数的 3 倍）：计划级累计新建线程上限，跨 replan 与 reopen 保留；Judge 续聊不增加前者。
- `--max-blocked-per-story`（默认 2）：同一 Story 累计进入 blocked 的上限；耗尽表示需要用户修改计划。
- `--poll-seconds`：每次 `bb thread wait` 的节奏；`--wait-timeout` 是该轮等待上限。
- `--allow-empty-story`：仅纯验证 Story 可无业务改动完成。
- `--once`、`--max-stories N`：适合定时或受限批次；`--push` 在全部完成后推送并核对 upstream HEAD。
- `status [--json]`：只读显示进程、计划进度、in-progress/blocked Story、全局兜底计数与阈值、最近日志和上次停止原因；不读取线程全文。
- `stop [--wait]`：向该计划的 pid 发送 SIGTERM；`--wait` 最长等待 `--wait-timeout` 秒。

退出码 `0` 表示完成或本轮受控结束；`2` 表示 driver/环境契约错误；`3` 表示需用户处理，原因在 stderr；`4` 表示
同一计划已有存活 driver。

维护 driver 的内部状态、BB 回执兼容性和等待语义时，读
[driver 循环](references/bb-dispatch-loop.md)。
