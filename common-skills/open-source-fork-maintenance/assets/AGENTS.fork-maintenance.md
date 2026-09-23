<!-- fork-maintenance:start -->
## Fork 维护

本仓库是个人 fork（远端 `fork`，上游 `origin` = <owner>/<repo>）。目标只有三个：每个改动是独立、可直接提给上游的分支；方便本机聚合打包；能纳入上游稳定版。完整流程见 [docs/fork-maintenance.md](docs/fork-maintenance.md)，不要引入领域分支、补丁登记表或冻结清单。

- 根目录永远检出 `local/aggregate`：它是 `scripts/fork-aggregate` 每次从稳定 tag 重新生成的产物。不在这里写产品代码，不从它拉分支，不从它提上游 PR。
- 新功能/修复：从 `.fork/branches` 的 `base` tag 拉 `feature/<name>` 或 `fix/<name>`，放在 `.worktrees/<name>`；只有依赖另一 fork 分支时才叠在它上面。完成后推送到 `fork`，并在 `fork-tooling` 分支的 `.fork/branches` 登记一行。
- 聚合打包：`scripts/fork-aggregate [--promote]`。分支与上游冲突 → 回该分支 rebase 修复；分支之间冲突 → 在聚合 worktree 里只合并两边，rerere 记住。产品修复不写进聚合的 merge 提交。
- 上游反馈：分支就是 PR 材料；向上游提 issue/评论/PR 前必须经用户逐项确认，状态记在 `.fork/branches`。
<!-- fork-maintenance:end -->
