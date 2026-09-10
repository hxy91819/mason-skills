# Driver 内部循环

这是 `scripts/large_task_driver.py` 的维护参考，不是手动编排步骤。调用者先查单个计划的 `status`，未运行时用
`start` 后台启动；脚本负责进程、线程生命周期和计划状态转换。

## 输入与持久状态

- `agent/plan.json`、`agent/stories/*.json` 与 Git 是权威事实。
- `Story.owner` 保存 Worker 的 BB `thr_*` ID，planning 只要求 active Story 的 owner 为非空字符串。
- 每个 `(repo, plan)` 使用 `<repo>/.local/large-task-orchestrator/<topic-slug>/`；slug 包含计划 topic 的可读
  形式和短哈希，避免同名路径碰撞。目录里的 `state.json` 缓存阶段、线程、次数、起始脏路径，以及顶层
  `counters`（累计 Worker/Judge、每 Story blocked 次数和最近 `story.done`）；这些累计值不随 replan 或 reopen
  清空。`log.jsonl` 仅追加事件，`driver.pid` 保存 pid/启动时间，`driver.out` 接收后台 stdout/stderr，
  `last-stop.txt` 保存最近一次退出码 3 的原因。它们都被 `.gitignore` 排除，丢失状态后可从计划和 BB 重新定位。
- `start` 先通过计划 `check` 和 `bb-dispatch --dry-run`，再以 `start_new_session=True` 派生后台 `run`。pid 文件
  用原子创建预占：存活 pid 返回退出码 4，陈旧 pid 覆盖。`run` 与 `start --foreground` 也受同一锁保护。
- `status [--json]` 只读取计划、本地状态和最近日志，不读线程全文。`stop` 对 pid 发 SIGTERM；信号处理器只设置
  停止标志，driver 在当前 `run_once` 后以退出码 3 退出并清除 pid，不会中断已派出的 BB 线程。

## 每张 Story 的状态机

1. `status --json` 给出 ready frontier；driver 领取一张 todo Story，记录基线并经 `bb-dispatch` 派 Worker。
2. `bb thread wait <id> --timeout <poll>` 后读取 `show`、interactions 和 `output`。当前 BB 在 timeout 时返回
   退出码 2；只要线程仍是 `pending|starting|active|stopping`，这表示 busy，不是命令错误。driver 补足
   poll 间隔，避免主循环忙等。busy 自最近一次 driver 对该线程的事件超过 `--stall-minutes` 时，driver 先
   `bb thread stop` 并记录 `thread.stalled`，再让 Worker retry 一次后交 Judge，或直接改派 Validator。
3. Worker `worker_done` 时，driver 从 Git 区分业务改动、计划投影、`.local/` 与起始 dirty baseline；没有业务
   改动须经 `--allow-empty-story` 明示，或交 Judge。程序不把计划的 `write_scope` 解释成文件白名单。
4. 默认每张 Story 都派只读 Validator；只有显式 `--validator standard-up` 才跳过 simple Story。Validator
   逐条核验 Acceptance，并结合 Outcome、边界和实际改动判断是否夹带无关或其他 Story 的工作；`write_scope`
   只是规划预估。Validator 失败把精确缺口发回同一 Worker；报告两次无效时受控停止。
5. 完成时写入 Acceptance、受限长度的 Handoff、刷新投影，并用 `git commit --only -- <targets>` 创建
   checkpoint。目标是业务路径加当前 Story/SPEC/STATUS，排除开始前的脏路径和 `.local/`，因此不会提交
   其他 Agent 的既有暂存改动。

`error` 首次执行 `bb thread retry`；第二次 Worker error 交 Judge，第二次 Validator error 改派新的
Validator。pending interaction 的完整内容交 Judge；Judge 处理已授权交互并回复 `patch` 加
`interaction handled` 后，driver 继续等待原线程。

每次运行还检查全局计时与累计上限：没有新的 `story.done` 超过 `--no-progress-hours` 即以退出码 3 停下；
Worker 与 Judge 的累计派发量分别受 `--max-workers-total`（0 表示 Story 总数的 3 倍）和
`--max-judges-total` 约束；同一 Story 的 blocked 累计达到 `--max-blocked-per-story` 后停止并要求用户修改计划。

同一仓库的不同计划可以同时运行。其他已由 driver 管理的计划的 `SPEC.md`、`STATUS.md`、`agent/plan.json` 和
`agent/stories/` 投影不计入当前 Story 的业务改动或 checkpoint，避免并发状态转换被误算成 Worker 改动。

## Judge 与回执

异常才经 `bb-dispatch --difficulty complex --kind judge` 派 Judge，路由来自 `defaults.judge`；未配置该键
时沿用 `defaults.complex`。它的动作含义：

- `retry`：同档 fresh Worker；`escalate`：高一档 Worker；`patch`：向现有 Worker 发送小修复提示。
- `block`：写 blocker 后继续其他 ready Story；`replan`：Judge 已改计划，driver 重新 `check`；`stop`：退出码 3。

`bb-dispatch` 的创建回执在已知 BB 版本中出现过两种形状：`result.thread.id` 与 `result.id`。driver 两者
都接受；没有任一 ID 时退出码 2，避免在创建结果不明时重复派发。

## 维护检查

修改此循环后，更新 fake BB 用例并运行：

```bash
cd common-skills/large-task-orchestrator
python3 -m unittest discover -s tests -p 'test_*.py'
```

真实环境检查先跑 `bb-dispatch --dry-run`，再在临时 Git 仓库里运行一张示例 Story。核对 child 的
`parentThreadId`、`status`、`output`、driver jsonl 与 checkpoint；接口差异应以兼容代码和回归测试收口。
