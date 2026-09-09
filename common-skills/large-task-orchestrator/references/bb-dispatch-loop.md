# BB 派发循环

所有线程通过 sibling `bb-model-routing` 的 `scripts/bb-dispatch` 创建，路由、模型、reasoning 与权限
由用户配置决定。本文只列 orchestrator 在一次 Story 循环里用到的命令。`<routing-skill>` 指
`bb-model-routing` 目录；`bb-dispatch` 已在 PATH 时直接调用。

## 派发

```bash
<routing-skill>/scripts/bb-dispatch --difficulty medium \
  --title 'STORY-03 worker' \
  --task "$(cat /tmp/story-03-task.md)"
```

`--task` 内容 = `epic_story.py brief` 输出 + 仓库规则与基线 + 并发 write scope + 报告契约。把任务
写到临时文件再传入，避免 shell 转义问题。返回 JSON 里 `result.thread.id` 是线程 ID，立即写回 Story
Handoff。

Validator：

```bash
<routing-skill>/scripts/bb-dispatch --difficulty simple --kind test \
  --title 'STORY-03 validator' \
  --task "$(cat /tmp/story-03-validate.md)"
```

Validator 任务要固定基线 commit、Story ID、逐条 Acceptance、相关黄金案例和要跑的命令；声明只读。

只读探查（看 diff 细节、跑整合测试回摘要）同样用 `--difficulty simple`，任务里要求只回摘要。

## 等待与取报告

```bash
bb thread wait <thread-id> --timeout 1800 --json
bb thread output <thread-id>
```

`wait` 超时不代表失败：先 `bb thread show <thread-id> --json` 看状态。`status` 为等待交互时：

```bash
bb thread interactions list <thread-id> --json
bb thread interactions approve <interaction-id> <thread-id>   # 已授权范围内
bb thread interactions answer <interaction-id> <thread-id> ... # 能从计划回答的问题
```

超出授权或需要用户决定的交互按 blocker 规则处理，不替用户决定。

线程失败（provider、配额、session）用 `bb thread retry <thread-id>` 一次；仍失败则换同档
replacement，并在 Handoff 记下原线程 ID。

## 同一 Story 的 follow-up

Validator 指出的精确遗漏发回同一 Worker 线程：

```bash
bb thread tell <worker-thread-id> "$(cat /tmp/story-03-patch.md)"
bb thread wait <worker-thread-id> --json
bb thread output <worker-thread-id>
```

Worker 线程已丢失或上下文过长时改派 fresh Worker，把 Handoff 事实和遗漏一起交给它。

## 并发规则

默认同时只有一个会写工作区的线程在跑。Validator 与只读探查可与彼此并行，但不与写工作区的 Worker
并行读同一区域的未提交 diff，除非任务里固定了基线 commit。多个写入 Worker 只在已有隔离 worktree
并用 `--environment` 指定时才允许。
