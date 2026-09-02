# codexp orchestrator ACPX 冒烟案例

你现在是 `large-task-orchestrator` 的 orchestrator。请把下面内容当作一个已经通过规划校验的最小计划，不要读取或修改仓库中的其他计划。

- Epic：ACPX dispatch smoke test
- Story：SMOKE-01
- 目标：验证能否快速启动一个外部 worker
- 依赖：无
- 验收：创建一个命名 worker session，并发送一条 no-op prompt；worker 只需回复 `READY`
- 仓库：`/data/code/mason-skills`
- 写入范围：无。orchestrator、worker、validator 都禁止修改文件、提交、推送、创建 worktree。

请使用 `$large-task-orchestrator` 的 ACPX 流程，但采用最短路径：

1. 只检查当前仓库的 branch/status/worktree 和 ACPX 是否可用。
2. 选择 `codex` 作为 worker；只做一次 `sessions ensure` 握手。
3. 不设置 Codex/CodeXL effort；不尝试任何 effort 参数或模型变体。
4. 创建唯一 named session `codexp-smoke-codex-SMOKE-01-worker-1`。
5. 立即发送 no-op worker prompt：`Reply with exactly READY. Do not read or modify files.`
6. 记录从开始到 prompt 返回的工具调用数量、耗时和任何失败。

不要创建 notebook、不要 patch 计划卡、不要读取 validator skill；这是一次只测 dispatch 的冒烟测试。最终用简体中文报告实际执行路径和指标。
