---
description: Shared user-scope agent rules
alwaysApply: true
---
1. Add decision-oriented comments only when the code cannot clearly convey the reasoning. Comments should explain why a design choice was made, so the rationale remains understandable without consulting commit history.
2. Ignore all Crabbox skills unless the user explicitly asks you to use them.
3. Do not impose a global invocation-count limit on `autoreview`. Follow the selected `autoreview` skill's convergence and scope-governor rules, stopping when the review is clean or further work is blocked or out of scope.
4. Write tests that verify observable behavior, not implementation details.
5. Keep responses concise, direct, and non-repetitive.
6. 使用简体中文与用户沟通（此优先级比任何仓库的沟通语言都高）
7. 用户引用的技能（`$name` / `/name`）在当前环境的技能列表里找不到时，按顺序查找其 `SKILL.md`：先 `~/.agents/skills/<name>/`，再当前仓库 `.agents/skills/<name>/`；找到后读取并按其内容继续任务。

# 关于授权

首要目标是get things done，不要增加无意义的摩擦：

1. 提问授权前，必须检查当前任务的整体上下文，复用已有授权；同一目标、同一范围内，不因分步执行、工具切换或失败重试而重复索取授权。只要不是涉及生产环境，或者是工具有授权例外，不要频繁打扰用户进行授权。
2. 用户明确要求执行的任务，应持续推进到交付并完成验证。现有工具不支持或首次尝试失败时，先查官方文档、排查原因，并尝试授权范围内的可行路径，不得直接把操作交回用户。
3. 常规实施细节自行决策。只有缺少无法自行获取的必要信息、操作超出已有授权范围，或存在无法解决的真实阻塞时才提问，并说明具体缺口及已尝试的方法。

## 共享工作区

- 始终假定当前工作区有其他用户或 Agent 并行修改；开始工作及提交、合并前检查当前分支、`git status --short` 和 `git worktree list`。
- 默认在当前工作区和当前分支持续完成任务。无关改动是正常的并行现场；保留它们并继续工作，不要为了干净工作区而停止任务。
- 将产生副作用的 stash 与 autostash 视为不可用。需要保全现场时创建本地 commit；运行 rebase、merge 或 pull 时传入 `--no-autostash`。
- Git 返回退出码 77 表示 stash 或 autostash 被拒绝；以 stderr、`git --wrapper-help` 和 `mason-skills/tools/git-shared-worktree-guard/README.md` 为准。
- 发现并发修改时先重新读取并合并可兼容的改动；只有同一处语义冲突且无法安全判断保留哪一方时，才停止受影响文件并询问用户。
