# Skills

Add each skill as a subdirectory here. Every skill must include a `SKILL.md` file.

## Minimal example

```markdown
---
name: my-skill
description: What this skill does and when the agent should use it.
---

# My Skill

Instructions for the agent go here.
```

## Naming

- Use lowercase kebab-case for directory names (e.g. `code-review`, `api-docs`).
- Keep names short and descriptive.
- Write all skill content in English.

## Optional files

| File | Purpose |
|------|---------|
| `reference.md` | Long-form reference material the agent can read on demand |
| `examples.md` | Input/output examples |
| `scripts/` | Helper scripts the agent can execute |

See the [Cursor skills documentation](https://docs.cursor.com/context/skills) for full authoring guidance.
