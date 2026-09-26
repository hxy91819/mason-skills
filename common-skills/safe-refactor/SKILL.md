---
name: safe-refactor
description: 带证据门禁的保持行为重构：先定影响面和授权范围，再固定旧版行为基线，委派编码，最后独立验收 PASS/BLOCK/INSUFFICIENT。
disable-model-invocation: true
triggers:
  - user
---

# Safe Refactor：先圈边界，再改代码

这是流程类 Skill，仅在用户显式调用 `$safe-refactor` 时运行。你负责把一次重构推进到“具备进入发布流程的证据”，不负责宣布生产安全，也不自动推送、合并、部署。

适合共享组件、数据访问（如 N+1）、异步化、跨语言替换，或接手一份没有事前验证的重构 diff。小范围纯函数整理只需按下文“小任务”走轻量路径。

## 入口与模式

接受自然语言目标；不要求用户填写整份表。先读仓库说明、当前分支、已有任务单、测试与发布约定，能查到的信息不反复询问。

| 请求 | 模式 | 读取 |
|---|---|---|
| 新的重构目标 | 完整流程（下文 1–7） | 全部阶段按到达时读取 |
| “只分析影响面” | plan 或 actual 影响分析，不改生产代码 | [change-impact.md](references/change-impact.md) |
| “只补基线／测试” | 行为基线 | [behavior-baseline.md](references/behavior-baseline.md) |
| “验收这个重构”，或协调者派来的独立验收 | verify，不改生产代码 | [verify.md](references/verify.md) |
| 已有 diff | 下文“接手已有改动” | — |
| 继续任务 | 读取工作单及当前 Git 状态，先检查版本和证据是否仍匹配 | — |

所有模式先读 [共享规则](references/workflow.md)。用 [工作单](assets/work-item.md) 持久化状态；运行脚本时读 [工具说明](references/tooling.md)。

## 1. 收敛任务

记录一句话目标、可观察的收益标准、不做什么、原始版本 `origin_revision`、当前候选版本、环境限制和授权边界。不要把重构顺便升级为改需求、修全部历史 bug 或重写技术栈。

性能优化先确认瓶颈证据；结构重构也要有可验收收益，例如依赖方向、重复规则数量、模块公开面，而不只是“代码更漂亮”。没有足够收益时推荐不改或缩减目标。

默认最多两轮局部修复、一轮重新规划；这是可调整默认值，不是最佳次数的事实判断。沿用用户或项目已有预算；不得自行续费式增加预算。耗尽则保留工作并报告下一项决策。

## 2. 影响面分析（plan）

按 [change-impact.md](references/change-impact.md) 的 plan 模式，基于目标、原始版本、现有改动和约束给出最小可验证方案。

必须得到：改动的语义、受影响业务入口与资源、必要契约、未知项、推荐策略、允许／保护路径、最小验证集。不要把路径清单当语义影响的完整证明。

将方案写入 `policy.json` 和工作单。范围由用户明确授权或项目已有可信策略批准；低风险、已授权范围内可自动继续，不必每个文件都问一次。共享语义扩大、删除数据、改变权限、改变需求、放宽验收或超预算，需要明确的新决策。

## 3. 行为基线

按 [behavior-baseline.md](references/behavior-baseline.md) 在旧生产实现上建立测试，不先改实现再反推答案。

测试准备可能需要一个仅增加测试／夹具的提交：

- `origin_revision`：开始任务时的旧代码。
- `base_revision`：测试基线准备完成后的固定提交，生产行为仍是旧的。
- 对这两版的差异单独审查；基线准备若必须改变生产代码，拆成有证据的小步骤，不偷偷夹带。

记录契约、断言依据、基线执行、针对关键规则的红控结果。性能目标的旧版测量与业务回归分开。

基线就绪后，冻结 `policy.json` 的批准摘要及 `seal.json`；冻结的是受保护的断言／夹具／规范边界，不是整个测试仓库。没有实际执行能力时标记 `INSUFFICIENT`，不能宣称基线已建立。

## 4. 委派编码

向现有 Coding Agent（当前会话或宿主的 subagent）发送以下任务包：

```text
目标：<goal>；工作单：<absolute task directory>
旧版：<base_revision>；策略：<local/shared>
允许范围：<approved paths + semantic boundaries>
保持不变：<contract IDs and meanings>
受保护内容：<frozen assertions, permissions, schema, policy, CI>
收益标准：<criterion>；本轮预算：<budget>
按完整行为边界小步修改；可以在授权范围内修复实现和添加测试。
发现新的调用方／共享状态影响／必须扩大修改范围时，停止扩张并回报。
不得放宽断言、重录基准答案、绕过门禁或修改自己的授权范围。
交付实际 diff、运行命令、结果、版本、未验证项；不要只交实现总结。
禁止未授权 push、merge、deploy、生产双写和删除用户工作。
```

不默认并发修改同一共享组件。允许并行只读分析；多编码分支只有边界明确互不冲突才并行，集成后重新验收最终组合版本。

## 5. 影响面复扫（actual）

按 [change-impact.md](references/change-impact.md) 的 actual 模式，基于 `base_revision → candidate_revision` 的实际变更重新分析，并与原始影响清单对照。调用方、数据消费者、缓存、事务、事件、资源和配置都要检查。

若出现新影响：退回第 2 步选择扩展验证、隔离或缩小改动。修改白名单不是自动批准，新增影响也不因“只改了允许文件”而获得放行。

## 6. 独立验收

优先在全新上下文（宿主的 fresh subagent，或用户要求时经 `$bb-model-routing` 开的新线程）中以 verify 模式调用 `$safe-refactor`，传递固定版本、原始目标、可信策略摘要、基线封存及原始证据，不把编码结论当事实。

没有独立会话能力：明确记录，不能伪称独立；本任务要求独立验收时由外部 reviewer 接手。是否允许降级必须由可信策略事先决定。

| 结果 | 下一步 |
|---|---|
| PASS | 生成发布交接材料；进入既有 CI/CD，不自动部署 |
| BLOCK：实现违约、断言削弱、范围越界 | 局部问题退回编码；越界退回影响面决策 |
| INSUFFICIENT：环境、oracle、时序或运行证据不足 | 补相应证据或缩小范围；不得当作低风险 PASS |

## 7. 交接与结束

用 [发布交接](assets/release-handoff.md) 记录版本、收益与代价、剩余风险、灰度停止条件、业务指标、数据兼容和恢复责任。发布平台未接入时写“待平台验收”，不写“已具备真实回滚”。

任务状态使用 `INTAKE → IMPACT → BASELINE → IMPLEMENT → RESCAN → VERIFY → READY_FOR_RELEASE`；可转 `BLOCKED / INSUFFICIENT / CANCELLED`。`READY_FOR_RELEASE` 不等于已部署。具体转移与权限见共享规则。

结束回复只保留：结果、变化与收益、关键证据、未解决风险、下一项必要动作。不要倾倒整个工作单。

## 接手已有改动

保存现有 diff 与工作区状态，不 reset／clean／stash 覆盖未知工作。找真实旧提交，在独立工作树恢复旧实现并补行为基线；确认候选实现没有污染 oracle。

既有改动超过可验证边界时，提出缩小补丁或拆分迁移，不把现有大量投入当继续大改的理由。跨语言测试适配器只转换协议和调用方式，不能改预期；适配器本身也要审查。

## 工具的边界

[refactor_guard.py](scripts/refactor_guard.py) 只做确定性证据检查；业务语义由各阶段和 reviewer 判断。脚本哈希／策略摘要必须来自变更执行者不能修改的可信位置，才能用于强制门禁。详见 [CI 接入](references/ci-integration.md)。

## 回看与缺口

单一事实源是任务目录（放在源码仓库外）：`work-item.md` 记状态与决策，`evidence/*.json` 记每次运行的 SHA、命令、耗时、退出码和测试统计，`verification.json` 记验收结论。事后复查对该目录重跑 `refactor_guard.py gate`（只读）即可得到当前机械结论。

缺口：没有跨任务的聚合账本，无法统计 verify 结论分布、返工轮次或 INSUFFICIENT 原因的长期趋势；需要时再按仓库可观测标准补建。
