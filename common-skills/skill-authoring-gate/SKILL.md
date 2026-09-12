---
name: skill-authoring-gate
description: "创建、迁移、重命名或修改 skill 时使用，包括 SKILL.md、触发配置及影响行为的参考文件或脚本。"
---

# Skill 编写门禁

## 开始编辑前

1. 读取 `writing-for-agents`；涉及 frontmatter、触发方式或 router 时，再读其 `SKILL-MECHANICS.md`。使用宿主已提供的位置；未列出时查找 `~/.agents/skills/writing-for-agents/SKILL.md`。
2. 读取宿主的系统 `skill-creator`（通常为 `~/.agents/skills/.system/skill-creator/SKILL.md`）。同一会话已读且未变化的指南直接复用，无需每修改一个文件就重读；缺少必要指南时报告具体路径，不把它当成用户审批门禁。
3. 先读取目标 `SKILL.md` 和 `agents/openai.yaml`（如果存在），按实际工作流判断默认触发类型，再修改内容与配置。
4. `SKILL.md` frontmatter 的 `description` 是触发规则，不是功能介绍。只写用户请求或任务形状何时匹配；能力、角色、实现和本轮改动写进正文。改行为时默认保持 `description` 不变，除非触发条件本身变了。

## 分类与配置一致

遵循目标仓库的触发规则和用户已明确的例外；修改现有 skill 时先保留其策略，只有实际工作流变化或配置冲突才重新选择。下面是缺少更具体约定时的分类默认值。

- **流程类 Skill**（规划、审查、复盘、治理、发布、迁移、编排，或带审批、用户决策、明显副作用的多步流程）：默认仅显式触发，同时设置 `policy.allow_implicit_invocation: false`、frontmatter `disable-model-invocation: true` 和 `triggers: [user]`（Devin 的等效标记），三层都必须存在。用户通过宿主原生语法显式调用：Codex、Pi、OpenCode 用 `$skill-name`，Kimi 用 `/skill:skill-name`，Devin 用 `/skill-name`。
- **被动型 Skill**（低风险的格式化、生成、查询或验证能力）：默认允许隐式触发，设置 `policy.allow_implicit_invocation: true`，且不得遗留 `disable-model-invocation: true`。
- **无法明确分类或混合型 Skill**：采用流程类的保守默认值；用户要改成允许隐式触发时，必须明确提出并说明风险与影响。

## 交付前

- 入口保留共同目标、约束与完成标准；多分支细节用带读取条件的参考链接。短单流程不必拆分。只保留会改变判断的说明，固定顺序用于真实的安全、兼容性或易错操作。
- 复用会话已有授权；已授权的编辑、验证、修复连续完成，只有缺少必要用户决策或超出范围时暂停受影响步骤。缺少可选配置时使用已声明默认值。
- 运行 Skill validator、YAML 解析和 `git diff --check`；如果 validator 尚不识别兼容性的 `disable-model-invocation` 或 `triggers` 字段，记录该工具限制并补做 frontmatter 结构检查，不得为了让 validator 通过而删除流程类 Skill 的禁用标记。
- 文档与路由修改核对参考可达性及代表性触发场景；脚本变化验证受影响行为。检查通过即交付，仅在后续修改或失败使证据失效时重跑。
- 核对 `description` 仍是触发匹配，没有被改成能力说明书。
- 向用户报告：分类、默认策略、判断依据、配置位置，以及显式触发 Skill 的 `$skill-name` 用法；用户明确意图与默认分类冲突时，以用户意图为准并说明。
