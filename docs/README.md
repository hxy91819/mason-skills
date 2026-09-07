# Docs

This directory holds maintained repository design notes and examples. Skill source remains under `common-skills/`.

| Path | What it is |
| --- | --- |
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
