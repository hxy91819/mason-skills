# Driver 内部循环

这是 `scripts/large_task_driver.py` 的维护参考，不是手动编排步骤。调用者只启动或恢复 driver；脚本负责
线程生命周期和计划状态转换。

## 输入与持久状态

- `agent/plan.json`、`agent/stories/*.json` 与 Git 是权威事实。
- `Story.owner` 保存 Worker 的 BB `thr_*` ID，planning 只要求 active Story 的 owner 为非空字符串。
- `<repo>/.local/large-task-orchestrator/driver-state.json` 缓存阶段、线程、次数和起始脏路径；
  `driver-log.jsonl` 仅追加事件。两者被 `.gitignore` 排除，丢失时可从计划和 BB 重新定位。

## 每张 Story 的状态机

1. `status --json` 给出 ready frontier；driver 领取一张 todo Story，记录基线并经 `bb-dispatch` 派 Worker。
2. `bb thread wait <id> --timeout <poll>` 后读取 `show`、interactions 和 `output`。当前 BB 在 timeout 时返回
   退出码 2；只要线程仍是 `pending|starting|active|stopping`，这表示 busy，不是命令错误。driver 补足
   poll 间隔，避免主循环忙等。
3. Worker `worker_done` 时，driver 只将业务改动与 `write_scope` 比对；计划投影和 `.local/` 不算越界。
   没有业务改动须经 `--allow-empty-story` 明示，或交 Judge。
4. simple Story 默认直接采纳 Worker 证据；其余 Story（或 `--validator always`）派只读 Validator。
   Validator 失败把精确缺口发回同一 Worker；三次不能解析的 Validator 输出交 Judge，防止无限重派。
5. 完成时写入 Acceptance、受限长度的 Handoff、刷新投影，并用 `git commit --only -- <targets>` 创建
   checkpoint。目标是业务路径加当前 Story/SPEC/STATUS，排除开始前的脏路径和 `.local/`，因此不会提交
   其他 Agent 的既有暂存改动。

`error` 首次执行 `bb thread retry`；第二次 Worker error 交 Judge，第二次 Validator error 改派新的
Validator。pending interaction 的完整内容交 Judge；Judge 处理已授权交互并回复 `patch` 加
`interaction handled` 后，driver 继续等待原线程。

## Judge 与回执

异常才经 `bb-dispatch --difficulty complex --kind general` 派 Judge。它的动作含义：

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
