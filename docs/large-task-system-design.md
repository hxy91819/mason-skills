# 大型任务规划与编排：核心设计

[`large-task-planning`](../common-skills/large-task-planning/SKILL.md) 与
[`large-task-orchestrator`](../common-skills/large-task-orchestrator/SKILL.md)
是同一个大型任务系统的两个阶段。前者把目标变成可执行、可恢复的计划；后者把这份计划作为控制面，持续驱动外部 Agent 交付。

本文只维护两者共享的设计理由和不变量。具体文档格式、脚本命令、路由与 session 操作仍由各自 Skill 和
[`agent-schema.md`](../common-skills/large-task-planning/agent-schema.md) 负责。

## 一个系统，两种职责

| 角色 | 负责 | 不负责 |
| --- | --- | --- |
| Planning | 锁定 Goal、黄金验收和用户边界；设计 Epic/Story、依赖、门禁和状态契约 | 长期调度外部 Agent，或把初版路径冻结成不可修改的承诺 |
| Orchestrator | 领取既有计划，调度 worker/validator，维护状态、证据、提交和最终交付 | 重新发明 Goal，或绕过计划建立第二套状态账本 |
| Worker / Validator | 在一个 Story 边界内分别实现和独立验证 | 修改计划状态、跨 Story 调度、提交或推送 |

Planning 可以独立用于计划交接。Orchestrator 也只从一份已经存在且可领取的计划开始；它不会替代规划阶段。

## 三个核心原则

### 目标稳定，路径可变

Goal、黄金验收和已确认的产品、发布、运维边界是稳定契约。Epic、Story、顺序、路由和实现方案只是当前证据下的路径。新事实出现时，系统优先调整尚未开始的路径；只有稳定契约本身需要变化时才回到用户决策。

因此，计划不是预测未来的静态清单，而是围绕稳定目标持续更新的可执行假设。

### 计划是状态协议，不是长提示词

人读 Markdown 保存意图和重大取舍；脚本维护的 Agent JSON 保存动态状态、依赖、清单和交接；证据目录与 Git 保存可复核结果。每个事实只有一个权威位置，仪表盘只是生成的投影。

会话可以丢失，计划不能依赖会话记忆。新的执行者应能从一个 Story、其执行卡和直接权威输入恢复工作，而不需要重放历史对话。

### 编排器留在控制面

Orchestrator 负责边界、状态和整合，把实现交给 fresh worker session，把方向验证交给独立 validator session。外部 Agent 是叶子执行者，不能再派生 Agent，也不能写计划或交付 Git 状态。

这种分离让实现上下文保持聚焦，也避免“实现者自行宣布完成”。Story 只有在独立验证通过、证据已协调且计划已更新后才进入 `done`。

## 端到端闭环

1. Planning 把 Goal 和黄金案例一次写成可领取计划；黄金案例可由 Agent 依据权威资料推导，用户样例优先。
2. Orchestrator 根据依赖和写入冲突选择一个或一组 ready Story，并记录领取状态。
3. Worker 在单一 Story session 中实现并给出可观察证据；修复仍留在同一 Story 边界。
4. 独立 Validator 对不变的验收契约判断继续、补丁、插入 Story 或重规划。
5. Orchestrator 统一更新计划、运行整合检查，并为已验证结果建立 Git checkpoint。
6. 系统根据新证据释放下一批 Story；最终 Story 在同一 acceptance commit 上复验全部黄金案例。
7. 只有全部 Story、综合门禁和远端交付都成立时，Goal 才完成。

`worker_done` 和 validator 往返是 `in_progress` 内的执行阶段，不扩展计划的状态词表。Story 完成也不等于整个 Goal 完成。

## 权限与失败模型

用户拥有 Goal、黄金判据以及产品、发布和运维形态。Agent 在这些边界内拥有可逆的技术选择、计划调整和恢复动作，并把非显然决定写回权威计划。

失败应尽量局部化：一次模型配额、provider 或 session 故障属于执行 attempt，不等于 Story 失败；只阻塞耗尽恢复路径的依赖链，其他 ready 工作继续。重试必须保留已有工作和证据，并以新的 attempt 恢复同一个 Story，而不是静默换 Story 或降低验收标准。

本地 notebook 只补充计划尚未覆盖的稀有恢复事实。它不是状态源，也不能成为平行项目日志。

## 运行历史与复盘

三个载体回答不同问题：Plan 说明目标和当前权威状态；`<repository>/.local/large-task-orchestrator/run-history.json` 说明同一 checkout 最近怎样运行；notebook 只解释异常恢复上下文。恢复和复盘都按 Plan → history → notebook 的顺序读取，冲突时以 Plan、Git 和验收证据为准。

History 由 orchestrator 的确定性脚本维护，只保存 attempt 结果、固定原因码、计划变化、checkpoint 和 Git 交付事实，不保存完整对话、diff、测试日志或计划理由。它最多保留一个 active run、十二个 terminal run 和每 run 最近三十个事件；更老事件进入 run 指标，更老 run 进入固定维度 rollup，避免随任务数量无限增长。

这是同一持久 checkout 的本地复盘缓存，不是跨 clone、跨机器或永久审计。记录失败只产生告警，不改变计划状态或已经证明的交付。复盘 Agent 先运行 `orchestration_history.py show`，再按 `plan_ref` 和近期热点回查权威证据：高 attempt 数检查 Story 拆分和 route；validator 返工检查验收与 worker 输入；反复 plan change 检查应前移的假设验证；blocked episode 检查 readiness、权限和环境预检。确认后的改进写回真正拥有规则的 Skill、配置或测试，不写入 history 充当新状态。

## 完成边界

系统同时满足以下条件才报告完成：

- 所有执行卡均为 `done`，依赖、仪表盘和证据一致；
- 最终黄金验收在固定 acceptance commit 上全部通过；
- 跨 Story 整合检查通过，未授权或并发修改未混入交付；
- 经过验证的提交已到达目标远端，剩余风险和交接可追溯。

## 维护边界

计划产物、schema、readiness 和黄金验收语义由 `large-task-planning` 维护；路由、session 连续性、worker/validator 生命周期、恢复和交付由 `large-task-orchestrator` 维护。跨两者的理由与不变量在本文维护一次，操作细节留在所属 Skill。

修改任一侧时，先判断变化属于单方机制还是共享契约。共享契约变化先更新本文，再在真正负责强制执行的一侧更新规则或测试，避免复制同一规范。
