---
name: skill-authoring-gate
description: 创建、迁移、重命名或修改 Skill 的 SKILL.md、agents/openai.yaml 或影响行为的 references/scripts 时使用。
---

# Skill 编写门禁

按实际使用上下文决定手动还是自动。用户的维护偏好是：**新技能默认手动，只有确实需要 Agent 自行发现的入口才自动**。这覆盖 skill-creator 的通用自动默认值；不因宿主省略配置时默认为 true，就省略本仓的策略选择。

## 编辑前

1. 读取 `~/.agents/skills/writing-for-agents/SKILL.md`；涉及调用策略或 router 时再读同目录 `SKILL-MECHANICS.md`。
2. 读取系统 `~/.agents/skills/.system/skill-creator/SKILL.md`，按用户偏好和本门禁选择调用方式，其余结构指导仍适用。
3. 读取目标 Skill、已有 metadata 及调用清单，检查真实使用请求、调用方和自动发现的必要性。窄修改只检查相关路径。
4. description 用简短能力说明加精确触发条件；排除容易混淆的相邻任务。参数、长能力清单和执行步骤放正文，未改变匹配范围时保留原描述。

## 按调用需求分类

| 上下文 | 策略与理由 |
|---|---|
| 人主动启动的独立流程，如规划、全库治理、发布、迁移编排 | 默认手动；由人决定何时进入这一套工作 |
| 当前任务中 Agent 必须自行选用的能力，如查 DB、TAPD 记录、日志或远端代码 | 可自动；以具体对象、平台和证据需求限定匹配 |
| 已启动流程必须自动衔接的下游 | 可自动；说明调用方、到达条件和完成边界，只覆盖该下游，不据此自动启动整套新流程 |
| 查询能力与独立编排混合 | 先区分入口；有实际查询自动需求时只自动匹配该分支，编排由人启动。无法清楚分流时保留手动，必要时按调用方式拆分 |
| 没有真实自动调用场景，或用途尚不清楚 | 保留手动，不因为模型能推断用途就开放发现 |

判断的关键是“谁需要在什么上下文找到它”，不是步骤多少、Skill 名称或是否含写入。DB/TAPD 查询即使包含鉴权、分页和重试，也仍是可供任务选用的能力。一个没有副作用的长篇规划流程，也可能只需要人手动启动。

选择自动时，在交付说明中记录至少一个真实正例、容易误选的相邻反例和自动选择的必要性；下游另说明实际调用方。任务未要求重新评估的既有策略保持不变，不顺手批量翻转。

本门禁保留自动发现：创建或修改 Skill 时需要自行加载这份编写约束；普通业务任务不触发，也不因已加载门禁就启动全库审计。

## 配置与正文一致

| 策略 | `agents/openai.yaml` | `SKILL.md` frontmatter |
|---|---|---|
| 手动（新技能默认） | `policy.allow_implicit_invocation: false` | `disable-model-invocation: true`；支持 Devin 时同步 `triggers: [user]` |
| 有明确需要的自动入口 | `policy.allow_implicit_invocation: true` | 移除禁用字段和仅限 user 的 triggers |

保留无关 UI/依赖字段，同步仓库调用清单。手动入口写明调用方式；自动入口仍可手动调用。手动流程启动后可使用所需能力，续办同一流程不要求用户每步重新输入命令；显式引用其他流程资料也不授权扩大任务。

## 跨 Skill 运行时依赖

Skill 执行另一个 Skill 的脚本时，不使用 `../<skill>/...` 等源码树相对路径；各 Skill 通常独立软链到 user scope，相对位置不是运行时契约。按 user-scope 根目录解析：

```bash
DEPENDENCY="${AGENTS_HOME:-$HOME/.agents}/skills/<skill-name>/scripts/<entrypoint>"
```

执行前检查入口存在且可执行；缺失时报告依赖 Skill 未安装，不猜测当前项目里的源码位置。依赖本仓 `common-skills/` 且需要在其他项目运行时，将目标 Skill 登记到 `config/skill-symlinks.yaml`，并用同步脚本校验安装状态。

本 Skill 自己的 `scripts/`、`references/` 和 `assets/` 仍使用 Skill 内相对路径；仓库内仅供编写维护的文档链接也可保持相对路径。本规则只约束跨 Skill 的运行时调用。

## 实际操作授权

发现策略只控制如何进入技能，不能代替目标、访问权限或写入授权。

- 已有授权覆盖精确动作和目标时继续，缺失信息只阻塞依赖它的操作。
- 独立发布、通知、治理、任务登记等目标不从普通查询中推导出来。
- 外部操作仍核验目标、环境、审批、guard 和审计；需要人决定时先准备可审阅材料。
- 保留真正的业务完成条件；手动启动不等于每一步都要重新确认，自动发现也不等于可以直接执行写入。

## 验收与依据

- 走查正例、相邻反例、续办和下游衔接，检查正文/引用是否残留与最终策略冲突的要求。
- 检查跨 Skill 脚本调用是否从 user scope 解析，且依赖已进入软链清单；不接受依赖源码目录相邻的运行时路径。
- 运行适用 validator、YAML 解析和 `git diff --check`，核对策略清单、frontmatter 与宿主 metadata。结构检查不能证明模型的触发准确率，不写只匹配固定文案的测试。
- 报告最终策略、理由、配置位置、执行边界及未验证部分。

[OpenAI 文章](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra)提供精确描述、按需加载和任务边界原则；[Codex 文档](https://developers.openai.com/codex/skills)说明自动发现默认值及关闭机制。本文的“默认手动、按必要性开放”是用户选择的维护策略，不冒充文章规定。
