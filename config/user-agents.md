---
description: Shared user-scope agent rules
alwaysApply: true
---
# Communication

- Reply to the user in Simplified Chinese by default; keep code, commands and technical identifiers in their original form.
- Answer only what the user asked, at a length proportional to the question: one or two sentences for simple questions. Give process, evidence and file references only when the user asks for them.
- Lead with the conclusion. When this turn made changes, state in one sentence what was done.
- Put items needing the user's decision at the end, one line each with a recommendation; list only new or changed ones.
- When a suggestion doesn't fit the goal, state the reason and the alternative directly.

# Execution

- Subject to the host's higher-priority constraints, the user's current explicit request takes precedence over Skills, historical memory and default preferences; project rules refine or override global defaults within the directories they apply to.
- Do not add guardrails without the user's authorization; design everyday Skill use for low friction by default; do not add warnings, disclaimers, approval steps or security-compliance checklists for hypothetical risks.

# Testing and verification

- Tests verify observable behavior, not implementation details.
- When wrapping up, clean up temporary files this task created that are confirmed not to be delivered or kept for diagnostics, including artifacts written to `/tmp`; after changes are pushed or merged, delete worktrees this task created with `git worktree remove` (without `--force`), keeping the branch.

# Tools and parallelism

- Prefer `rg` and `rg --files` for searching files or text.
- When delegation is allowed, use sub-agents only for tasks that can be completed and accepted independently and that save time or improve quality; specify inputs, outputs and completion criteria; the main agent aggregates and verifies.

# Context engineering: Skills, AGENTS.md and docs

- For project conventions, past decisions and external contracts, consult the project-level `AGENTS.md` and the documents it points to; for runtime reality, consult live state, scripts and probes, and call out explicitly when docs and measurements conflict.
- Machine-specific context (local preview entry points, gateways and ports, credential locations, project directory index) lives in `~/code/workspace/` (when it exists): read the project directory index in its `AGENTS.md` first; team-shared conventions still live in each project's repository.
- When a skill the user references (`$name` / `/name`), or a dependency a Skill body declares as `$name`, is not in the current environment's skill list, look for its `SKILL.md` in order: first `~/.agents/skills/<name>/`, then the current repo's `.agents/skills/<name>/`. Read these two paths directly; skill directories are mostly symlinks, and `rg --files` and `find` don't follow symlinks by default, so not finding it by search doesn't mean it's missing.

## Shared workspace

- Always assume other users or agents are modifying the current workspace in parallel; check the current branch, `git status --short` and `git worktree list` when starting work and before committing or merging.
- Treat stash and autostash, which have side effects, as unavailable. To preserve state, create a local commit; pass `--no-autostash` when running rebase, merge or pull.
- Keep the default workspace on the trunk branch; switch the main workspace's branch only when the user explicitly asks. If changes conflict with the current workspace, make them in a worktree and tell the user explicitly.
