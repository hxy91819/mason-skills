# 大型任务规划与编排：核心设计

[`large-task-planning`](../common-skills/large-task-planning/SKILL.md) 把大型目标编译成可恢复的计划；
[`large-task-orchestrator`](../common-skills/large-task-orchestrator/SKILL.md) 使用宿主提供的 subagent 持续执行，
直到完成交付或遇到真实阻塞。两者共享本页的不变量，字段和命令留在各自 Skill。

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

每张 Story 应由一个 fresh Worker context 完成。`brief` 从 JSON 提取行为结果、公共测试 seam、相关黄金
案例、稳定边界和直接前置 Handoff；Worker 无需重放历史对话或加载整个计划。

subagent session 不是持久状态，可以在失败、配额耗尽或上下文丢失后替换。恢复顺序固定为 Agent JSON
→ Git/diff → history。替换 Worker 读取同一执行包和当前工作区继续，不重新发明需求。

## Orchestrator 是唯一控制面

当前 Agent 使用所在 coding agent 的原生 subagent 接口：

- Worker 实现一张 Story；
- 独立 Reviewer 分开检查 Spec 与 Standards；
- Orchestrator 裁决证据、更新 JSON、创建 Git checkpoint 并完成最终交付。

默认只有一个 Worker 写共享工作区。只读调查和 Reviewer 可以并行；多个写入 Worker 只有在已经存在
隔离边界并明确分配 write scope 时才并行。Worker 与 Reviewer 都是叶子，不继续派生 subagent，也不
拥有计划状态或 Git 交付状态。这套协议不绑定某个 coding agent 或 provider。

## 端到端闭环

1. Planning 固定目标、黄金案例和边界，生成 Agent JSON 与两份人读视图，并校验依赖图。
2. Orchestrator 从 frontier 原子领取一张 Story，再用 `brief` 派发 fresh Worker。
3. Worker 在公共 seam 上以 red → green 纵向小循环实现并报告证据。
4. 独立 Reviewer 对同一 diff 分别检查 Spec 和 Standards；修复留在同一 Story。
5. Orchestrator 核对工作区事实，更新验收与 Handoff，刷新人读视图并提交 checkpoint。
6. 新证据触发最小计划调整，然后继续下一项可执行结果，不在 Story 之间等待人工确认。
7. `final_story` 在同一 acceptance commit 上重跑全部黄金案例和整合检查。
8. 完成门禁、测试、授权提交与真实远端 HEAD 同时成立后，目标才算完成。

`worker_done` 和 Reviewer 往返都属于 `in_progress`，不增加更多状态。

## 权限、阻塞与恢复

用户拥有稳定目标和边界；orchestrator 在其中拥有可逆技术选择、计划调整和恢复动作。只阻塞耗尽安全
恢复路径的依赖链，并继续其他 ready 工作。一次 subagent、session 或 provider 故障是 attempt 结果，
不是 Story 失败；保留已有 diff 与证据后派发 replacement Worker。

需要新凭据或权限、破坏性或明显外部动作、显著成本、稳定契约变化，或无法协调的同区域并发修改时，
才请求用户作一个最小决定。不得以降低黄金判据作为恢复手段。

## 最小可观测性

权威状态已经在 Agent JSON 与 Git 中，运行历史只用于复盘调度质量。checkout-local 的
`.local/large-task-orchestrator/run-history.json` 保存稳定 attempt ID、角色、agent/model、耗时、outcome、
固定 reason、计划变化和 checkpoint；不保存 prompt、回复、diff、日志或密钥。

历史脚本提供滚动保留、固定维度 rollup、幂等写入和带分母的 review hooks。History 写入失败只告警，
不改变 Story 状态，也不推翻由计划、测试和 Git 证明的交付。

## 维护边界

计划格式、依赖、readiness、黄金验收和人读投影由 Planning 维护；subagent 生命周期、独立 review、恢复、
checkpoint 和最终交付由 Orchestrator 维护。共享理由只在本文保留一次。
