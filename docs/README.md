# Docs

This directory holds maintained repository design notes and examples. Skill source remains under `common-skills/`.

| Path | What it is |
| --- | --- |
| [Fork 维护决策](adr/0001-two-tier-fork-maintenance.md) | 面向人的简短决策记录：独立来源、可选领域与新旧项目接入；不属于 Agent 默认加载材料 |
| [large-task system design](../common-skills/large-task-planning/references/large-task-system-design.md) | Shared design principles and boundaries for planning and orchestrating large tasks; owned by `large-task-planning` |
| [recommended-global-skills.md](recommended-global-skills.md) | 推荐全局技能规范与清单（仅推荐 19 个核心工程与治理技能） |
| [authenticated HTML preview](../common-skills/local-test/references/authenticated-html-preview.md) | 单服务器 HTTPS、Cookie 登录和临时 HTML 预览；由 `local-test` 持有共享基础设施契约 |
| [largeplan-example/](largeplan-example/) | Valid v2 two-audience example for token login |

Validate the example from the repository root:

```bash
python3 common-skills/large-task-planning/scripts/epic_story.py check \
  --plan docs/largeplan-example/agent/plan.json \
  --stories-dir docs/largeplan-example/agent/stories
```
