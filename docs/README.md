# Docs

This directory holds maintained repository design notes and examples. Skill source remains under `common-skills/`.

| Path | What it is |
| --- | --- |
| [skill-authoring.md](skill-authoring.md) | 创建或修改 skill 时读取：触发分类、按需加载、授权边界与必要验证 |
| [skill-distribution.md](skill-distribution.md) | 增删、重命名或同步 user-scope skill 时读取：清单与软链规则 |
| [skill-observability.md](skill-observability.md) | 新建或大改外部引擎、重试或人工裁决流程时读取：可观测设计 |
| [large-task-system-design.md](large-task-system-design.md) | Shared design principles and boundaries for planning and orchestrating large tasks |
| [recommended-global-skills.md](recommended-global-skills.md) | 推荐全局技能规范与清单（仅推荐 19 个核心工程与治理技能） |
| [authenticated-html-preview.md](authenticated-html-preview.md) | 单服务器 HTTPS、Cookie 登录和临时 HTML 预览，无需 Tailscale |
| [largeplan-example/](largeplan-example/) | Valid v2 two-audience example for token login |

Validate the example from the repository root:

```bash
python3 common-skills/large-task-planning/scripts/epic_story.py check \
  --plan docs/largeplan-example/agent/plan.json \
  --stories-dir docs/largeplan-example/agent/stories
```
