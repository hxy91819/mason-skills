# Workflow Mechanics

Details for source materialization, output directory creation, and conflict resolution.

## Materialize Source

| Input Type | Action |
|------------|--------|
| File | Use as-is (no copy needed) |
| Inline text | Save to `polish/{slug}.md` |
| URL | Fetch content, save to `polish/{slug}.md` |

`{slug}`: 2-4 word kebab-case slug derived from content topic.

## Create Output Directory

Create a subdirectory next to the source file: `{source-dir}/{source-basename}-polished/`

Examples:
- `posts/article.md` → `posts/article-polished/`
- `polish/slack-thread.md` → `polish/slack-thread-polished/`

## Conflict Resolution

If the output directory already exists, rename the existing one to `{name}.backup-YYYYMMDD-HHMMSS/` before creating the new one. Never overwrite existing results.
