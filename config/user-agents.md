---
description: Shared user-scope agent rules
alwaysApply: true
---

# 编码
1. Write tests that verify observable behavior, not implementation details.

# 沟通
2. Keep responses concise, direct, and non-repetitive.

# 上下文工程: Skills，AGENTS.md 和 docs

1. 禁止在未经用户授权的情况下，添加 guardrails，用户日常 skills 使用默认以低摩擦方式设计。
2. 用户引用的技能（`$name` / `/name`）在当前环境的技能列表里找不到时，按顺序查找其 `SKILL.md`：先 `~/.agents/skills/<name>/`，再当前仓库 `.agents/skills/<name>/`；找到后读取并按其内容继续任务。
3. 设计应该以长远维护、消除歧义为目标，应考虑此会话结束后，新的会话也能有轻松接手工作。主动优化用户的仓库上下文，包含但不限于 AGENTS.md，skills，docs。

## 共享工作区

- 始终假定当前工作区有其他用户或 Agent 并行修改；开始工作及提交、合并前检查当前分支、`git status --short` 和 `git worktree list`。
- 将产生副作用的 stash 与 autostash 视为不可用。需要保全现场时创建本地 commit；运行 rebase、merge 或 pull 时传入 `--no-autostash`。
- 默认工作区保持为主干分支，仅在用户明确要求的情况下才可以切换主工作区分支。改动如果与当前工作区存在冲突，使用worktree进行修改，并明确告知用户。
