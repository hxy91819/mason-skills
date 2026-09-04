# Docs

This directory holds maintained repository design notes and examples. Skill source remains under `common-skills/`.

| Path | What it is |
| --- | --- |
| [large-task-system-design.md](large-task-system-design.md) | Shared design principles and boundaries for planning and orchestrating large tasks |
| [largeplan-example/](largeplan-example/) | Valid v2 two-audience example for token login |

Validate the example from the repository root:

```bash
python3 common-skills/large-task-planning/scripts/epic_story.py check \
  --plan docs/largeplan-example/agent/plan.json \
  --stories-dir docs/largeplan-example/agent/stories
```
