---
name: skill-authoring-gate
description: 创建、迁移、重命名或修改任何 skill 前的强制门禁。任务涉及 SKILL.md、agents/openai.yaml，或会改变 skill 行为的 references/scripts 时使用：先加载写作指南，判定触发类型，再修改内容与配置。
---

# Skill 编写门禁

## 开始编辑前

1. 加载 `~/.agents/skills/writing-for-agents/SKILL.md`；涉及 frontmatter、触发方式或 router 时，继续加载同目录的 `SKILL-MECHANICS.md`。
2. 加载 `~/.agents/skills/.system/skill-creator/SKILL.md`；它是系统 skill，不是目标仓库的 skill。不要把"系统可能自动选中 Skill Creator"当作门禁，规则本身必须保证被执行。
3. 先读取目标 `SKILL.md` 和 `agents/openai.yaml`（如果存在），按实际工作流判断默认触发类型，再修改内容与配置。

## 分类与配置一致

- **流程类 Skill**（规划、审查、复盘、治理、发布、迁移、编排，或带审批、用户决策、明显副作用的多步流程）：默认仅显式触发，同时设置 `policy.allow_implicit_invocation: false` 和 frontmatter `disable-model-invocation: true`，两层都必须存在。用户通过宿主原生语法显式调用：Codex、Pi、OpenCode 用 `$skill-name`，Kimi 用 `/skill:skill-name`。
- **被动型 Skill**（低风险的格式化、生成、查询或验证能力）：默认允许隐式触发，设置 `policy.allow_implicit_invocation: true`，且不得遗留 `disable-model-invocation: true`。
- **无法明确分类或混合型 Skill**：采用流程类的保守默认值；用户要改成允许隐式触发时，必须明确提出并说明风险与影响。

## 交付前

- 运行 Skill validator、YAML 解析和 `git diff --check`；如果 validator 尚不识别兼容性的 `disable-model-invocation` 字段，记录该工具限制并补做 frontmatter 结构检查，不得为了让 validator 通过而删除流程类 Skill 的禁用标记。
- 向用户报告：分类、默认策略、判断依据、配置位置，以及显式触发 Skill 的 `$skill-name` 用法；用户明确意图与默认分类冲突时，以用户意图为准并说明。