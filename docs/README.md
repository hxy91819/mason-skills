# Docs

This directory holds maintained repository design notes and examples. Skill source remains under `common-skills/`.

| Path | What it is |
| --- | --- |
| [PPT 制作复盘](ppt-making-lessons.md) | 工程成果汇报的叙事、实践表达、视觉审查和交付经验；供类似需求参考，不是固定模板或技能入口 |
| [领域设计不跑偏](domain-guardrails.md) | 规则只住聚合、用例只编排、规则与呈现一句判准、事务与版本、七项 CI 必过的守护、领域影响评估让 Agent 自己停下；适合单体单库的业务系统 |
| [项目 Y 架构参考](project-y-architecture.md) | 单体 Go + PostgreSQL + 对象存储、两端 React 前端与原型共用呈现层的仓库布局、请求路径、认证、附件、测试分层、部署与文档链；去业务名词的已跑通形状 |
| [架构不腐化](architecture-anti-erosion.md) | 唯一来源加生成与一致性检查、文档与代码不分叉、棘轮基线只能缩、派发与合并边界、升级过滤器；与领域设计不跑偏配套 |
| [原型到正式实现复盘](prototype-to-production-lessons.md) | 原型分两条线承载（UI 抽共用包加截图比对；需求走文档链加编号测试）、领域驱动轻量版与七项守护、派发合并流程、测试分层、前端薄化、本地入口与踩坑；供同类项目参考 |
| [Fork 维护决策](adr/0001-two-tier-fork-maintenance.md) | 面向人的简短决策记录：独立来源、可选领域与新旧项目接入；不属于 Agent 默认加载材料 |
| [large-task system design](../common-skills/large-task-planning/references/large-task-system-design.md) | Shared design principles and boundaries for planning and orchestrating large tasks; owned by `large-task-planning` |
| [harness/](harness/) | Harness 大全：按主题收录真实项目验证过的 pre-commit、测试分层、testcontainers、迁移、覆盖率门禁和 Agent 工作面做法，附新项目接入清单 |
| [recommended-global-skills.md](recommended-global-skills.md) | 推荐全局技能的准入标准与同步方式；完整清单以 `config/skill-symlinks.yaml` 为准 |
| [authenticated HTML preview](../common-skills/local-test/references/authenticated-html-preview.md) | 单服务器 HTTPS、Cookie 登录和临时 HTML 预览；由 `local-test` 持有共享基础设施契约 |
| [largeplan-example/](largeplan-example/) | Valid v2 two-audience example for token login |

Validate the example from the repository root:

```bash
python3 common-skills/large-task-planning/scripts/epic_story.py check \
  --plan docs/largeplan-example/agent/plan.json \
  --stories-dir docs/largeplan-example/agent/stories
```
