# mason-skills

A collection of [Cursor Agent Skills](https://docs.cursor.com/context/skills) shared for the tech community.

Skills are reusable instruction sets that teach AI agents how to perform specialized workflows — code review, documentation, automation, and more.

## What's inside

Each skill lives in its own directory under `skills/` and includes a `SKILL.md` file with YAML frontmatter and markdown instructions.

```
skills/
└── example-skill/
    ├── SKILL.md          # Required — main skill instructions
    ├── reference.md      # Optional — detailed reference
    ├── examples.md       # Optional — usage examples
    └── scripts/          # Optional — helper scripts
```

## Usage

### Cursor IDE

1. Clone this repository or copy the skill directory you need.
2. Place skills in one of these locations:
   - **Personal** — `~/.cursor/skills/<skill-name>/` (available across all projects)
   - **Project** — `.cursor/skills/<skill-name>/` (shared with the repository)
3. Cursor discovers skills automatically from the `SKILL.md` frontmatter.

### Other agents

Skills are plain markdown. You can adapt the instructions for other AI coding tools that support custom system prompts or skill files.

## Available skills

| Skill | Description |
|-------|-------------|
| [article-polish](skills/article-polish/) | Article polishing (quick / normal / refined). Derivative work based on [baoyu-translate](https://github.com/JimLiu/baoyu-skills/tree/main/skills/baoyu-translate). |

## Contributing

This is a personal skills collection. Feel free to fork, adapt, and use the skills under the [MIT License](LICENSE).

If you find a bug or have a suggestion, open an issue or pull request.

## License

MIT — see [LICENSE](LICENSE).

## Attributions

Some skills are derivative works based on third-party projects. See [NOTICE](NOTICE) for upstream credits and license text.
