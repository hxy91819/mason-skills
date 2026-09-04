---
name: large-task-planning
description: 把超出单次上下文的大型工程目标编译为人读 SPEC/STATUS 与 Agent JSON 执行计划。
disable-model-invocation: true
---

# Large Task Planning

这是流程类 Skill，仅在用户显式调用 `$large-task-planning` 时运行。

为两种受众生成一个计划系统：人通过 `SPEC.md` 理解目标和取舍，通过 `STATUS.md` 判断是否顺利、是否
需要介入；Agent 通过结构化 JSON 领取、执行和恢复。JSON 是唯一事实源，两份 Markdown 都由脚本按
人的阅读问题重新组织，不逐字段转抄 Agent 细节。

创建或检查计划前读[格式契约](references/plan-format.md)。发现 v1 的 `epics/ + stories/ +
agent/*.json + 项目进展.md` 时，再读[迁移说明](references/migrate-v1.md)。维护与 orchestrator 共享的
职责、完成语义或回溯 Matt 上游借鉴时，读[联合核心设计](../../docs/large-task-system-design.md)。

## 产物与受众

```text
<topic>/
├── SPEC.md                 # 人：为什么做、完成后怎样、承诺、边界、取舍与验收
├── STATUS.md               # 人：已得到什么、正在验证什么、下一步与介入点
└── agent/
    ├── plan.json           # Agent：稳定 Goal、规格、黄金案例与 final Story
    └── stories/*.json      # Agent：执行单元、状态、依赖、上下文与 handoff
```

人读文档不按 Epic/Story 模板展开，也不展示内部 ID、依赖图、代码锚点、write scope、owner、attempt
或原始命令日志。Agent JSON 不承担项目介绍文的可读性。相同事实只在 JSON 维护一次；`render` 根据
人的阅读任务重新组织信息。

`SPEC.md` 面向首次加入项目或需要做取舍的人，按“为什么要做 → 完成后是什么样 → 对使用者的承诺 →
必须守住的边界 → 已定取舍 → 怎样确认完成 → 交付路线”阅读。`STATUS.md` 面向正在跟进项目的人，先给
当前判断，再给正在推进、接下来、之后路线、需要关注和已经得到的结果。若一项 Agent 字段不能帮助人
理解终态、判断进展或采取行动，就不应出现在 Markdown 中。

## 先清除决策迷雾

只有任务明显超过一个 fresh context，或需要跨会话、跨 Agent 恢复时才使用本 Skill。单会话可安全
闭环的任务直接执行。

先区分：

- **决策迷雾**：产品结果、正确答案或边界尚不能清楚描述。先调查、原型或询问。
- **执行路径**：结果和判据已明确，只需选择可逆实现。由 Agent 决定并继续。

只有会改变用户所得、公开契约、兼容/迁移、安全、发布物、运维责任或显著成本的选择属于用户决策。
已有对话和仓库事实足够时直接综合；不能安全推断时，只问能解除阻塞的最小问题。不要把仍在迷雾中的
工作预切成虚构 Story。

## 编译规格

1. 读取适用的 `AGENTS.md`、需求、规格、ADR、领域词汇和代码入口；检查 branch、
   `git status --short`、`git worktree list` 与基线。区分事实、假设、边界和范围外事项。
2. 在 `plan.json.spec` 中写 Problem Statement、用户视角的 Solution、完整但不重复的 User Stories、
   Boundaries、重大 Decisions、公共 Testing seams 和 Out of Scope。这一结构借鉴 To Spec，但不绑定其
   tracker 或安装包。
3. 写黄金案例。每个 `GC-NN` 都有可复现 fixture、连续 actions、独立 oracle 和要保留的 evidence。
   没有已知正确结果的演示不是黄金案例。
4. 选择最高且稳定的公开测试 seam。优先沿用仓库已有 seam；测试可观察行为，不绑定实现细节。

## 编译执行路径

把工作拆成 tracer-bullet Story：每张 Story 交付一条窄而完整、可独立验证的纵向结果，并能由一个
fresh Worker context 完成。依赖字段 `blocked_by` 只表达真正阻止开工的边。

Story Context 只保存执行所需的公共 test seams、代码入口、权威资料、write scope 和停止条件。
Outcome 与 Acceptance 说结果，不列层级实现任务。宽范围机械迁移使用 expand → 分批 migrate →
contract → final acceptance，而不是硬切伪纵向片段。

指定一个 `final_story`：它直接或间接阻塞于全部其他 Story，并在同一 acceptance commit 上复验全部
黄金案例。初次编号用 `STORY-NN`；中途插入用 `STORY-NN.M`，保留已有 ID。

用 `write` 原子写入 JSON，再渲染和校验：

```bash
python3 <skill-dir>/scripts/epic_story.py write \
  --file <topic>/agent/plan.json --from <draft-plan.json>
python3 <skill-dir>/scripts/epic_story.py write \
  --file <topic>/agent/stories/STORY-01-<slug>.json --from <draft-story.json>
python3 <skill-dir>/scripts/epic_story.py render \
  --plan <topic>/agent/plan.json --stories-dir <topic>/agent/stories
python3 <skill-dir>/scripts/epic_story.py check \
  --plan <topic>/agent/plan.json --stories-dir <topic>/agent/stories
```

不要手改 `agent/*.json`、`SPEC.md` 或 `STATUS.md`。长字段更新时读出 JSON，在临时文件中修改完整对象，
再通过 `write` 落盘；随后 `render` 与 `check`。

完成标准：SPEC 能让不参与实现的人说清问题、最终体验、关键取舍和验收方式；STATUS 能在一分钟内回答
“已经得到什么、现在在做什么、下一步是什么、我是否需要介入”；每个 Agent Story 有独立结果、行为
验收、真实 blocker 和足够的 fresh-context 输入；校验通过且至少一个 Story 可领取或有具体 blocker。

## 计划演化

Goal、黄金 oracle 和用户边界稳定；Story、依赖、顺序、代码路径与实现方案是当前假设。Orchestrator
可重排、插入、合并或改写未开始的 Story。改变 Story Outcome/Acceptance 时递增 `intent_version`；
只更新状态或 handoff 时不递增。改变稳定契约时暂停受影响工作，取得用户决定后递增 `goal_version`。

只有 orchestrator 修改计划状态和 handoff。领取时使用预期状态保护：

```bash
python3 <skill-dir>/scripts/epic_story.py transition \
  --story <topic>/agent/stories/STORY-01-*.json \
  --expect todo --status in_progress --owner <worker-id>
```

为 fresh Worker 提取最小执行包：

```bash
python3 <skill-dir>/scripts/epic_story.py brief \
  --plan <topic>/agent/plan.json --stories-dir <topic>/agent/stories \
  --story STORY-01
```

标记 `done` 前，在 JSON 中把已证明的 Acceptance 设为 `passed=true`，并写清 handoff 的结果、验证、
剩余工作、风险和下一步。最终使用 `completion-check`；它证明计划内部与人读投影收口，不替代仓库
测试、Git 检查或远端交付。
