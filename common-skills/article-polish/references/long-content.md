# Long content

Use for normal/refined mode when the source reaches `chunk_threshold` (default 4000 words). Quick mode stays a single pass; if length may affect quality, mention the tradeoff briefly and continue the requested mode.

1. Analyze the whole article and establish shared voice, terminology, audience, and goals.
2. Resolve the chunk helper runtime: `bun` when installed, otherwise `npx -y bun` if package execution is permitted. If neither route is available, split at Markdown block boundaries directly or report the unavailable tooling; keep useful polishing work moving.
3. Run `<runtime> <skill-dir>/scripts/main.ts <source> --max-words <chunk_max_words> --output-dir <output-dir>/chunks`. The helper preserves Markdown blocks, falling back to lines and words for oversized blocks. `chunk_max_words` defaults to 5000.
4. Build shared `02-prompt.md` from the analysis. When delegating chunks, use [subagent-prompt-template.md](subagent-prompt-template.md), including each chunk's position, adjacent context, and applicable style rules. Use subagents only when available, authorized, and useful; sequential polishing uses the same context.
5. Preserve chunk drafts in `chunks/`. Merge in source order, prepend `chunks/frontmatter.md` when present, and save `polished.md` for normal or `03-draft.md` for refined mode.
6. Check the merged result for missing or duplicated passages and inconsistent voice, terminology, and transitions. Shared prompts support consistency; this final read verifies it. Continue the selected mode through its final output.

The helper only chunks Markdown. Mode/style/audience/goal flags belong to the skill request, not to this script.
