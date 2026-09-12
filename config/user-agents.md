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
8. 设计应该以长远维护、消除歧义为目标，应考虑此会话结束后，新的会话也能有轻松接手工作。主动优化用户的仓库上下文，包含但不限于 AGENTS.md，skills，docs。
9. 中文沟通中引用英文技术术语（如 seam、deep module、adapter）时，保留英文原词，首次出现用括号给出自然的中文解释（如 seam（可替换的边界点）），后续直接用英文原词；不要生造生僻中文译名（如“接缝”）。

## 共享工作区

- 始终假定当前工作区有其他用户或 Agent 并行修改；开始工作及提交、合并前检查当前分支、`git status --short` 和 `git worktree list`。
- 默认在当前工作区和当前分支持续完成任务。无关改动是正常的并行现场；保留它们并继续工作，不要为了干净工作区而停止任务。
- 将产生副作用的 stash 与 autostash 视为不可用。需要保全现场时创建本地 commit；运行 rebase、merge 或 pull 时传入 `--no-autostash`。
- Git 返回退出码 77 表示 stash 或 autostash 被拒绝；以 stderr、`git --wrapper-help` 和 `mason-skills/tools/git-shared-worktree-guard/README.md` 为准。
- 发现并发修改时先重新读取并合并可兼容的改动；只有同一处语义冲突且无法安全判断保留哪一方时，才停止受影响文件并询问用户。

## BB 本机资源安全

- 在 BB 仓库执行全量测试、资源密集构建或源码 App 启动时，必须通过 `bb-resource-run -- <command>` 运行；本地聚合打包使用 `bb-resource-run --profile package -- <command>`。命令不可用、scope 已占用或进程因 OOM 退出时，停止该项重型操作并报告，不得绕过隔离器重试。
