# 大型任务规划与编排：核心设计

[`large-task-planning`](../common-skills/large-task-planning/SKILL.md) 把大型目标编译成可恢复的计划；
[`large-task-orchestrator`](../common-skills/large-task-orchestrator/SKILL.md) 通过 BB 线程持续执行，
直到完成交付或遇到真实阻塞。两者共享本页的不变量，字段和命令留在各自 Skill。

系统的两个目标：让模型长时间自主工作；用成本分层省钱。Orchestrator 是上下文大、判断力强的会话，
只做调度与裁决；实现由便宜但可靠的 Worker 完成，完成校验由更便宜的 Validator 完成。所有设计取舍
都以这两个目标为判据。

## 两种读者，一份事实

```text
<topic>/
├── SPEC.md                  人：理解目标、体验、取舍和完成证明
├── STATUS.md                人：判断进展、下一步和是否需要介入
└── agent/
    ├── plan.json            Agent：稳定规格、黄金案例和最终收口点
    └── stories/*.json       Agent：执行状态、依赖、上下文和 handoff
```

JSON 是唯一事实源，由 planning 脚本校验和原子更新。Markdown 也是生成物，但不是 JSON 的逐字段副本：
生成器按人的阅读任务重新组织事实，隐藏内部 ID、依赖图、代码锚点、owner、session 和命令日志。

`SPEC.md` 帮助首次加入或需要决策的人回答：为什么做、完成后是什么样、对使用者承诺什么、必须守住
哪些边界、做过哪些关键取舍、怎样证明真的完成，以及大致沿什么结果路线前进。

`STATUS.md` 帮助正在跟进的人在一分钟内回答：已经得到什么、现在验证什么、下一项结果是什么、后面还
有什么，以及是否存在需要人工处理的阻塞或残余风险。它不是工单看板，也不机械展开 Agent Story。

## 目标稳定，路径可替换

Problem、最终体验、黄金 oracle 和已确认的产品、兼容、安全、发布、运维边界是稳定契约。Story、依赖、
顺序、代码路径和实现方案只是当前证据下的执行路线。

规划先清除会改变终态的决策迷雾，再把清楚的工作拆成纵向 tracer bullet。每张 Agent Story 交付一个
可观察结果，而不是一个技术层或一串待办。新证据出现后，orchestrator 可以调整尚未开始的路线；只有
稳定契约本身变化才回到用户决策。因此计划是围绕目标持续更新的假设，不是一次性预测未来的清单。

## Fresh context 是执行边界

每张 Story 应由一个 fresh Worker context 完成，而且应由 economy 或 standard 档的 Worker 完成。规划时
预计需要 strong 才能做完的 Story 是拆分信号，不是升档信号；strong 只保留给整合和已证明的能力失败。
`brief` 从 JSON 提取行为结果、公共测试 seam、相关黄金案例、稳定边界和直接前置 Handoff；Worker 无需
重放历史对话或加载整个计划。Handoff 是给下一个便宜 Worker 的输入，必须短：planning 的 `check` 对
过长的 Handoff 告警。

线程 session 不是持久状态，可以在失败、配额耗尽或上下文丢失后替换。恢复顺序固定为 Agent JSON
→ Git/diff → BB 线程记录。替换 Worker 读取同一执行包和当前工作区继续，不重新发明需求。

Orchestrator 的上下文同样是执行边界。它不读完整 diff、测试日志或线程全文，只消费结构化报告与
`git diff --stat` 级别的摘要；需要细节时派便宜的只读线程去看。每个状态转换点都把阶段、线程 ID 和
下一步写回 Handoff，使上下文压缩在任何时刻发生都不丢事实。

## Orchestrator 是唯一控制面

当前 Agent 通过 `$bb-model-routing` 的 `bb-dispatch` 创建 BB 线程。Worker 按 Story 难度映射为
`simple / medium / complex`；Validator 固定 `simple` 加 `--kind test`。provider、模型和 reasoning 由
用户的路由配置决定，叶子不自选型号，orchestrator 也不在任务文本里写路由要求。

- Worker 实现一张 Story；
- 独立 Validator 只逐条确认 Acceptance 是否成立并报告新事实，不做代码审查，也不做计划级判断；
- Orchestrator 裁决证据、决定是否插入 Story 或重规划、更新 JSON、创建 Git checkpoint 并完成最终交付。

Validator 不是每张 Story 都需要：economy 且验收可由脚本直接判定的 Story，orchestrator 用验收命令结果
判定即可；黄金案例在 `final_story` 仍会全量复验。这是主要的成本杠杆之一。

默认只有一个 Worker 写共享工作区。只读调查和 Validator 可以并行；多个写入 Worker 只有在已经存在
隔离环境并明确分配 write scope 时才并行。Worker 与 Validator 都是叶子，不继续派生线程，也不拥有
计划状态或 Git 交付状态。Validator 的只读靠任务声明与 diff 核对保证，不依赖 BB 权限模式。

## 端到端闭环

1. Planning 固定目标、黄金案例和边界，生成 Agent JSON 与两份人读视图，并校验依赖图。
2. Orchestrator 从 frontier 原子领取一张 Story，再用 `brief` 派发 fresh Worker。
3. Worker 在公共 seam 上以 red → green 纵向小循环实现并报告证据。
4. 独立 Validator 逐条确认 Acceptance 是否真正成立，或由验收脚本直接判定；修复留在同一 Worker 线程。
5. Orchestrator 核对工作区事实，更新验收与 Handoff，刷新人读视图并提交 checkpoint。
6. 新证据触发最小计划调整，然后继续下一项可执行结果，不在 Story 之间等待人工确认。
7. `final_story` 在同一 acceptance commit 上重跑全部黄金案例和整合检查。
8. 完成门禁、测试、授权提交与真实远端 HEAD 同时成立后，目标才算完成。

`worker_done` 和 Validator 往返都属于 `in_progress`，不增加更多状态。

## 权限、阻塞与恢复

用户拥有稳定目标和边界；orchestrator 在其中拥有可逆技术选择、计划调整和恢复动作。只阻塞耗尽安全
恢复路径的依赖链，并继续其他 ready 工作。一次线程、session 或 provider 故障是 attempt 结果，
不是 Story 失败；保留已有 diff 与证据后派发 replacement Worker。

需要新凭据或权限、破坏性或明显外部动作、显著成本、稳定契约变化，或无法协调的同区域并发修改时，
才请求用户作一个最小决定。不得以降低黄金判据作为恢复手段。

普通实现不确定、首次测试失败、线程消失、路由或配额故障、等价技术方案选择都由 orchestrator 解决。
最终验收失败时保留失败证据：实现缺陷插入修复 Story；fixture 或环境错误修复验收环境；Goal 或边界
错误才请求用户。

## 最小可观测性

权威状态在 Agent JSON 与 Git 中。线程级事实（provider、模型、状态、耗时、最终输出）由 BB 持久化，
每个线程通过 `bb-dispatch` 关联到 orchestrator 父线程，可用 `bb thread list --parent-thread` 与
`bb thread show` 回看。Story Handoff 记录该 Story 用过的线程 ID 与结论。不再维护独立的运行历史
账本：它与 BB 线程记录重复，而且维护成本高于复盘价值。已知缺口是没有跨运行的成功率聚合。

## 上游借鉴与版本回溯

这套系统是本仓库独立维护的长时工作协议，不在运行时组装或依赖 Matt Pocock Skills。v2 只选择性吸收
其中经过验证的工程设计，再补上长期状态、自主恢复、计划演化、checkpoint 和真实交付闭环。

- **Matt 上游仓库：** [`mattpocock/skills`](https://github.com/mattpocock/skills)
- **借鉴基线：** [`6654f6b60cd9d5be8b54c6fafe44346dabeb3b76`](https://github.com/mattpocock/skills/commit/6654f6b60cd9d5be8b54c6fafe44346dabeb3b76)
  （2026-08-24 的上游 `main` 快照）
- **本仓库落点：** [`16c409efff03904fbc891c6a69f5ce7e71775e3f`](https://github.com/hxy91819/mason-skills/commit/16c409efff03904fbc891c6a69f5ce7e71775e3f)
  首次完成本轮 v2 简化改造

| 上游 Skill（固定版本） | 本系统吸收的设计 |
| --- | --- |
| [Wayfinder](https://github.com/mattpocock/skills/blob/6654f6b60cd9d5be8b54c6fafe44346dabeb3b76/skills/engineering/wayfinder/SKILL.md) | 区分决策迷雾与执行路径；目标稳定，路线随新证据演化 |
| [To Spec](https://github.com/mattpocock/skills/blob/6654f6b60cd9d5be8b54c6fafe44346dabeb3b76/skills/engineering/to-spec/SKILL.md) | 从使用者视角组织 Problem、Solution、User Stories、Decisions、Testing 与 Out of Scope |
| [To Tickets](https://github.com/mattpocock/skills/blob/6654f6b60cd9d5be8b54c6fafe44346dabeb3b76/skills/engineering/to-tickets/SKILL.md) | tracer-bullet 纵向结果、真实 blocker、fresh context，以及宽迁移的 expand-contract 例外 |
| [TDD](https://github.com/mattpocock/skills/blob/6654f6b60cd9d5be8b54c6fafe44346dabeb3b76/skills/engineering/tdd/SKILL.md) | 在公共 seam 验证可观察行为，并按 red → green 小循环推进 |
| [Code Review](https://github.com/mattpocock/skills/blob/6654f6b60cd9d5be8b54c6fafe44346dabeb3b76/skills/engineering/code-review/SKILL.md) | 独立 closeout 视角；本系统改为独立 Validator 逐条确认 Acceptance，不跑双轴代码审查 |

所有固定源文件都以同一个上游快照为准。这里不把“最后触碰文件的提交”当成设计版本，因为它可能只是
格式化或元数据修复。下次借鉴前，先比较上述基线与新的上游 `main` 在这五个文件上的语义差异；只吸收
仍符合本系统目标的部分，再更新基线与本仓库落点，不做整包同步。

## 维护边界

计划格式、依赖、readiness、黄金验收、Handoff 长度告警和人读投影由 Planning 维护；线程生命周期、
能力档、完成校验、恢复、checkpoint 和最终交付由 Orchestrator 维护；路由配置与派发校验由
`bb-model-routing` 维护。角色边界、并行规则和 blocker 规则只在本文写一次，两个 Skill 引用而不复述。
