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

## 共享工作区

- 始终假定当前工作区有其他用户或 Agent 并行修改；开始工作及提交、合并前检查当前分支、`git status --short` 和 `git worktree list`。
- 默认在当前工作区和当前分支持续完成任务。无关改动是正常的并行现场；保留它们并继续工作，不要为了干净工作区而停止任务。
- Agent 不得自行创建、切换或清理分支与 worktree，也不得使用 stash、clean、破坏性 reset/restore 等操作搬移、隐藏、删除或覆盖现有工作。只有用户在当前任务中明确要求时才可执行。
- Git 命令被本机 git wrapper 拦截（退出码 77）时，按 wrapper 的规则处理：以其 stderr 指引、`git --wrapper-help` 和维护源 `mason-skills/tools/git-shared-worktree-guard/README.md` 为准。合规通道只有两条：任务已明确授权该目标时用 `git --user-approved='<理由>'` 单次执行，或先向用户说明命令、影响与理由并获授权；stash/autostash 类硬拦截没有授权通道。跑仓内测试时被误拦（如临时测试仓的 `branch -M`）同样按此处理，不得重排 PATH、改用 /usr/bin/git 或别名绕过。
- 发现并发修改时先重新读取并合并可兼容的改动；只有同一处语义冲突且无法安全判断保留哪一方时，才停止受影响文件并询问用户。可以建议 worktree，但未经授权不得创建。