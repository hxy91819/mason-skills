# Token login 示例

固定提示词，用来重复触发 `large-task-planning`，并对照每次生成结果。

当前仓库里的最新快照在 [`docs/largeplan-example/`](../../../../docs/largeplan-example/)。那是 2026-08-18 用 OpenCode + `zai-coding-plan/glm-5.2` 跑出来的第一份结果。

## 触发

在仓库根目录：

```bash
python3 common-skills/large-task-planning/examples/token-login/run_example.py --dry-run
python3 common-skills/large-task-planning/examples/token-login/run_example.py
```

默认使用 `opencode` 和 `zai-coding-plan/glm-5.2`，先清空再生成 `docs/largeplan-example/`。需要在现有快照上续写时加 `--keep-existing`。

## 每次结果

每次运行写入 `runs/<UTC时间>/`：

| 文件 | 内容 |
| --- | --- |
| `prompt.sent.txt` | 实际发给 Agent 的提示词 |
| `meta.json` | Agent、模型、退出码、check 结论 |
| `check.log` | `epic_story.py check` 输出 |
| `status.json` | `epic_story.py status --json` |
| `portal/` | 当次生成的门户副本 |
| `before/` | `--fresh` 时保存的上一份门户 |
| `acpx.ndjson` | acpx 事件流（默认不入库） |

看差异时对比两次 `runs/*/portal/`，或对比 `docs/largeplan-example/` 与某次 `portal/`。
