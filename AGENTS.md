# Repository Agent Rules

## Skill invocation policy

每当新增或迁移一个 skill 到本仓库，交付前必须先判断它的默认触发类型，并把判断结果告知用户。

### 分类与默认值

先阅读该 skill 的 `SKILL.md`，以及已有的 `agents/openai.yaml`（如果存在），再按主要使用方式分类：

- **流程类 skill**：负责规划、审查、复盘、治理、发布、迁移、编排，或包含审批门禁、用户决策或明显副作用的多步流程。默认仅显式触发，设置 `policy.allow_implicit_invocation: false`；用户需要通过 `$skill-name` 调用。它不会被隐式注入 Codex context。
- **被动型 skill**：提供可在请求自然匹配时由 agent 主动采用的通用能力，通常是低风险的格式化、生成、查询或验证。默认允许隐式触发，设置 `policy.allow_implicit_invocation: true`。
- **无法明确分类或两者混合**：采用流程类的保守默认值 `false`，并向用户说明不确定性和可选覆盖方式，不得静默选择。

分类依据是 skill 的实际工作流和风险，不是目录名称。可参考仓库现有设置：`distill`、`autoreview`、`large-task-planning`、`use-worktree`、`story-direction-review` 和 `ask-oracle` 为显式触发；`open-source-contribution` 为允许隐式触发。

仓库存在两种触发标记：Codex 优先读取 `agents/openai.yaml` 的 `policy.allow_implicit_invocation`；部分兼容旧技能还在 `SKILL.md` frontmatter 使用 `disable-model-invocation: true`。流程类 skill 必须以 `allow_implicit_invocation: false` 为 Codex 默认值，并保留或同步已有的 `disable-model-invocation: true`；被动型 skill 不得遗留与允许隐式触发相冲突的禁用标记。

### 配置与告知机制

1. 在 `agents/openai.yaml` 中写入或更新 `policy.allow_implicit_invocation`，保留无关的 `interface` 与 `dependencies` 字段；缺少该文件时创建最小完整配置。
2. 让 `SKILL.md` 的描述和正文与该策略一致：显式触发的 skill 要说明需要用户调用，允许隐式触发的 skill 不得声称只能手动调用。
3. 向用户报告：skill 名称、分类、默认策略、判断依据、配置文件，以及显式触发时的 `$skill-name` 用法；若采用保守默认，还要说明如何请求改为允许隐式触发。
4. 用 skill validator、YAML 解析和 `git diff --check` 验证；若配置或分类与用户明确要求冲突，以用户要求为准并在报告中说明。

## Owner 交付权限

当当前用户明确是该仓库的 owner，或已由当前认证身份和远端仓库归属确认是 owner 时，完成用户要求的改动并通过必要校验后，可以直接提交并推送到当前目标分支，不再额外询问确认。推送前仍必须检查分支、工作区和 worktree，只暂存本次任务范围内的文件，并保留并发产生的无关改动。

这项权限只覆盖用户明确要求的仓库改动交付，不扩大修改范围，也不授权删除数据、改写历史或推送无关内容。无法确认 owner 身份时，提交可以继续，但推送前必须向用户确认。
