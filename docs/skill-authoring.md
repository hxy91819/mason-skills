# Skill 编写与触发策略

## Skill invocation policy

每当创建、迁移或修改一个 skill，交付前必须先判断它的默认触发类型，并把判断结果告知用户。

### 分类与默认值

先阅读该 skill 的 `SKILL.md`，以及已有的 `agents/openai.yaml`（如果存在），再按主要使用方式分类：

- **流程类 skill**：负责规划、审查、复盘、治理、发布、迁移、编排，或包含审批门禁、用户决策或明显副作用的多步流程。默认仅显式触发，设置 `policy.allow_implicit_invocation: false`；用户需要通过 `$skill-name` 调用。它不会被隐式注入 Codex context。
- **被动型 skill**：提供可在请求自然匹配时由 agent 主动采用的通用能力，通常是低风险的格式化、生成、查询或验证。默认允许隐式触发，设置 `policy.allow_implicit_invocation: true`。
- **无法明确分类或两者混合**：采用流程类的保守默认值 `false`，并向用户说明不确定性和可选覆盖方式，不得静默选择。

分类依据是 skill 的实际工作流和风险，不是目录名称。可参考仓库现有设置：`anti-ai-slop`、`distill`、`autoreview`、`large-task-planning`、`use-worktree`、`story-direction-review` 和 `ask-oracle` 为显式触发；`open-source-contribution` 为允许隐式触发。

仓库存在三种触发标记：Codex 优先读取 `agents/openai.yaml` 的 `policy.allow_implicit_invocation`；Claude、Kimi 等兼容宿主读取 frontmatter 的 `disable-model-invocation`；Devin 读取 `triggers`（缺省 `[user, model]` 允许自动触发）。采用默认显式策略的流程类 skill 同时设置 `allow_implicit_invocation: false`、`disable-model-invocation: true` 和 `triggers: [user]`；允许隐式触发的 skill 不得遗留冲突的禁用标记。

已有明确例外按用户意图保留：`open-source-contribution` 与 `html-preview` 虽含流程与副作用，仍允许隐式触发，具体写入操作受正文授权边界限制。`skill-authoring-gate` 作为编写时的被动规范允许隐式采用。优化描述或拆分参考文件本身不改变这些策略。

### 配置与告知机制

1. 在 `agents/openai.yaml` 中写入或更新 `policy.allow_implicit_invocation`，保留无关的 `interface` 与 `dependencies` 字段；缺少该文件时创建最小完整配置。
2. 让 `SKILL.md` 的描述和正文与该策略一致：显式触发的 skill 要说明需要用户调用，允许隐式触发的 skill 不得声称只能手动调用。`description` 只写何时触发，不介绍 skill 做什么；行为变化写进正文，默认不动 `description`。
3. 向用户报告：skill 名称、分类、默认策略、判断依据、配置文件，以及显式触发时的 `$skill-name` 用法；若采用保守默认，还要说明如何请求改为允许隐式触发。
4. 用 skill validator、YAML 解析和 `git diff --check` 验证；若配置或分类与用户明确要求冲突，以用户要求为准并在报告中说明。

## 编写与验证

设计依据：[OpenAI — Rethinking skills and prompts for GPT-6 Astra](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra)。落实为精确触发、渐进披露、明确决策边界与可检查的完成标准；适用于本仓库各宿主，不替换其模型配置。

- Skill 的主入口只保留各分支都需要的目标、约束、完成标准，以及带触发条件的参考链接。单流程短文档直接写清，不为拆分而拆分。
- 描述只表达触发条件；此次任务明确要求优化触发描述时可精简，保留能区分相邻技能的边界。实现、参数表和完整示例放正文或参考。
- 保留可验证的安全、兼容性和运行约束；步骤的细致程度由风险决定，不因更换模型就删除保护，也不假定所有使用者都运行同一模型。
- 已有授权覆盖的实现、检查和修复连续完成。只在缺少会改变结果的用户决策、越过授权范围或遇到不可恢复的外部阻塞时暂停受影响部分。
- 为任务写清最终产物、必要验证和停止条件；验证通过后交付，只有后续修改、失败或未解决的疑点才重跑受影响检查。
- Skill 文档与路由修改检查 frontmatter、YAML、参考路径和触发场景；脚本变化运行受影响的行为测试。普通文字改动不要求安装全部宿主、调用外部模型或重跑无关测试。
- 创建或大改外部引擎、重试/fallback、人工裁决或难以定位失败的流程时，读取 [可观测设计](skill-observability.md)。
