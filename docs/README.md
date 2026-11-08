# Docs

This directory holds maintained repository design notes and examples. Skill source remains under `common-skills/`.

| Path | What it is |
| --- | --- |
| [PPT 制作复盘](ppt-making-lessons.md) | 工程成果汇报的叙事、实践表达、视觉审查和交付经验；供类似需求参考，不是固定模板或技能入口 |
| [领域设计不跑偏](domain-guardrails.md) | 规则只住聚合、用例只编排、规则与呈现一句判准、事务与版本、七项 CI 必过的守护、领域影响评估让 Agent 自己停下；适合单体单库的业务系统 |
| [项目 Y 架构参考](project-y-architecture.md) | 单体 Go + PostgreSQL + 对象存储、两端 React 前端与原型共用呈现层的仓库布局、请求路径、认证、附件、测试分层、部署与文档链；去业务名词的已跑通形状 |
| [架构不腐化](architecture-anti-erosion.md) | 唯一来源加生成与一致性检查、文档与代码不分叉、棘轮基线只能缩、派发与合并边界、升级过滤器；与领域设计不跑偏配套 |
| [客户确认原型复盘](client-confirmation-prototype-lessons.md) | 用点击原型让客户把规则改定：示范层与产品层分开、没答的题按默认做并标暂定、获奖标准加自审的视觉提示词、空数据路径、固定走查工具、发布门禁与踩坑；原型冻结前的那一段 |
| [原型到正式实现复盘](prototype-to-production-lessons.md) | 原型分两条线承载（UI 抽共用包加截图比对；需求走文档链加编号测试）、领域驱动轻量版与七项守护、派发合并流程、测试分层、前端薄化、本地入口与踩坑；供同类项目参考 |
| [原型复刻审查](prototype-replication-review.md) | 原型是三层规格（视觉、功能设计、领域规则）各需一条审查线；错误五类来源与对应审查；每个 PR 合并前的四层审查组合；像素基准逐张看；建议做成「原型对齐审查」通用技能加项目级移转约定 |
| [云端执行平台复盘](cloud-platform-lessons.md) | 控制面、执行面、guest 与暖池的架构形状；时延花在阶段之间的等待、容量取整条链的最小值、就绪要证明能干活；环境只从主干来；新云账号头一周的时间花在哪；合入与发布链的补充；Agent 工具链的坑 |
| [UI 间距与对齐复盘](ui-spacing-alignment-lessons.md) | 从六张截图追到间距拥有者与门禁盲区；token／类型化插槽、全页不变量与负向自测、独立看图验收及可复用检查清单 |
| [Fork 维护决策](adr/0001-two-tier-fork-maintenance.md) | 面向人的简短决策记录：独立来源、可选领域与新旧项目接入；不属于 Agent 默认加载材料 |
| [large-task system design](../common-skills/large-task-planning/references/large-task-system-design.md) | Shared design principles and boundaries for planning and orchestrating large tasks; owned by `large-task-planning` |
| [Agent 管家生产灰度复盘](agent-steward-production-rollout-lessons.md) | 候选组合回归、失败归因、合并晋级、夜间窗口与回滚裁决、工作簿和沟通交接；供类似发布参考 |
| [云实例平台可靠性复盘](instance-platform-reliability-lessons.md) | 数据就绪、远端完成性、锁与重试、超时分层、凭据轮换、制品兼容和容量供给 |
| [生产运维 Harness 复盘](harness/production-operations-lessons.md) | 只读监视、告警与重试预算、审批合并读回、共享节点限制、检出故障和工作区清理边界 |
| [面向 Agent 的云端执行平台复盘](agent-platform-lessons.md) | 报错写给模型读、MCP 工具设计、Skill/CLI/SDK 随站点分版本发布、控制台状态只从一处来、不可逆清单与数值时间契约；新用户体验测试与走查清单；任务书固定授权、按返工风险定档、管家少醒、合入后弄红主干的几类原因；仓库规则与知识点 |
| [harness/](harness/) | Harness 大全：按主题收录真实项目验证过的 pre-commit、测试分层、testcontainers、迁移、覆盖率门禁和 Agent 工作面做法，附新项目接入清单；[新用户体验测试](harness/agent-new-user-trial.md)让便宜模型只凭公开入口扮演新用户的 Agent |
| [recommended-global-skills.md](recommended-global-skills.md) | 推荐全局技能的准入标准与同步方式；完整清单以 `config/skill-symlinks.yaml` 为准 |
| [authenticated HTML preview](../common-skills/local-test/references/authenticated-html-preview.md) | 单服务器 HTTPS、Cookie 登录和临时 HTML 预览；由 `local-test` 持有共享基础设施契约 |
| [largeplan-example/](largeplan-example/) | Valid v2 two-audience example for token login |

Validate the example from the repository root:

```bash
python3 common-skills/large-task-planning/scripts/epic_story.py check \
  --plan docs/largeplan-example/agent/plan.json \
  --stories-dir docs/largeplan-example/agent/stories
```
