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
- Use one consistent language per skill. Choose the language that best serves its intended users; English is recommended for the broadest reach but is not required.

## Optional files

| File | Purpose |
|------|---------|
| `reference.md` | Long-form reference material the agent can read on demand |
| `examples.md` | Input/output examples |
| `scripts/` | Helper scripts the agent can execute |

See the [Cursor skills documentation](https://docs.cursor.com/context/skills) for full authoring guidance.
