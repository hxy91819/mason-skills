# History 与复盘

复杂长时运行需要最小可观测性，但不需要第二套状态账本。使用
[`scripts/orchestration_history.py`](../scripts/orchestration_history.py) 维护 Git-ignored 的
`<repo>/.local/large-task-orchestrator/run-history.json`。History 是旁路复盘缓存；写入失败只警告，
不改变计划状态或交付事实。

```bash
python3 <skill-dir>/scripts/orchestration_history.py --repository <repo> start \
  --run-id <stable-run-id> --plan-ref <topic>
python3 <skill-dir>/scripts/orchestration_history.py --repository <repo> attempt start \
  --run-id <run-id> --attempt-id <story-role-attempt> --story <STORY-ID> \
  --role worker --agent <host-agent> --route host-native \
  --model <actual-model-or-default> --effort <actual-effort-or-default> \
  --plan-ref <topic>/agent/stories/<Story.json>
python3 <skill-dir>/scripts/orchestration_history.py --repository <repo> attempt finish \
  --run-id <run-id> --attempt-id <story-role-attempt> --outcome worker-done
python3 <skill-dir>/scripts/orchestration_history.py --repository <repo> show
python3 <skill-dir>/scripts/orchestration_history.py --repository <repo> finish \
  --run-id <run-id> --outcome delivered \
  --plan <topic>/agent/plan.json --stories-dir <topic>/agent/stories
```

## 记什么

Worker 与 Validator 每次 turn 各记录一个 attempt（`--role worker` / `--role validator`）；真实
plan change、blocked episode 和 Git checkpoint 记录 event。只保存 engine/model/耗时/outcome/reason/
stable id 等最小事实，不保存 prompt、回复、diff、测试日志或密钥。

## 何时读取

- **启动或恢复**：`start` 创建或幂等恢复 active run。
- **每次 Worker / Validator turn**：`attempt start` 与 `attempt finish`。
- **计划变化、阻塞、checkpoint**：`event`。
- **聚合复盘**：`show` 输出带分母的统计与确定性复盘 hook。
- **收口**：`finish --outcome delivered`；放弃则 `--outcome abandoned` 并给非 `none` reason。

记录失败只告警并继续权威流程。交付是否成立由 Plan、测试和 Git 证明，不被 history 写入结果推翻。
