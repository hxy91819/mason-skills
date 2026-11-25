# Repository Agent Rules

## Skill invocation policy

Before modifying a Skill, read [skill-authoring-gate](common-skills/skill-authoring-gate/SKILL.md). Per the user's maintenance preference, new skills are manual by default; enable automatic discovery, and state the invocation context, only for capabilities the agent must pick on its own during the current task, or for automatic downstreams that an already-started workflow genuinely depends on.

Do not classify by step count, approvals or write branches; capabilities such as DB/TAPD queries must not be wrongly set to manual just because they include an authentication flow. Keep existing policies the task did not ask to change; check configuration consistency and execution authorization against the gate.

## Global rules

The global rules body lives in this repository at `config/user-agents.md`, symlinked into `~/.agents/AGENTS.md`; each host's global entry point (e.g. `~/.codex/AGENTS.md`, `~/.claude/CLAUDE.md`) reuses that body rather than copying the rules.

## Skill manifest maintenance

`config/skill-symlinks.yaml` is the single source of truth for this repository's recommended user-scope symlinks: it records which skills are recommended to be symlinked globally (`~/.agents/skills`). External projects (such as mattpocock-skills) are registered by project name under `sources:`, and their entries add `source:` pointing to the project; a project's location resolves as `$SKILL_SOURCE_<NAME>_DIR` > `$SKILL_SOURCES_DIR/<project name>` > a sibling directory of this repository, and the manifest never contains machine-absolute paths. After pulling this repository on another machine, the same skill setup can be reproduced from it, with no word-of-mouth needed.

- When adding a skill under `common-skills/` and the user asks to symlink it to user scope, register it in the manifest in the same change:
  `python3 common-skills/skill-manifest-sync/scripts/sync_skill_symlinks.py --mode register --skill <name> [--note "..."]`
- Register an external project's skill with `--mode register --source <project name> --skill <name>`; the project must already be declared under `sources:` (one entry is added automatically if missing).
- When deleting or renaming a skill, sync the manifest with `--mode remove --skill <name>` so no dangling entries remain.
- Before delivering changes that add or remove skills, run `--mode check` once to confirm the manifest matches the actual symlinks on this machine.
- The local sync entry point is `$skill-manifest-sync`: `--mode check` previews, `--mode apply` executes. apply prompts one by one to delete symlinks that "point to this repository or a declared source project but are not in the manifest"; when the user explicitly says to keep one, write it to the local whitelist `~/.agents/skill-sync-whitelist.yaml`. The whitelist is a local environment preference: it is not committed to Git, and must not be added to any manifest file other than this repository's `.gitignore`.
- The script only manages symlinks pointing directly to this repository or a declared source project: real directories and links relayed through other workspaces are never touched; conflicts are only reported.

## Non-open-source Skills

Some skills contain content clearly unsuitable for open source, such as internal account mappings or intranet system information (e.g. the tccli account selector). For such skills:

- They must not be committed to this repository or pushed to the remote; if one is found under `common-skills/`, move it out before delivery.
- Place them directly as real directories in `~/.agents/skills/<name>/`: they trigger the same as the symlinked versions, and naturally stay outside the repository, the manifest (`config/skill-symlinks.yaml`) and `git add -A`.
- Classification and trigger policy still follow "Skill invocation policy"; if such content is found to have entered Git history, stop and report to the user; do not rewrite history on your own.

## Observable design for complex Skills

When creating or heavily changing a hard-to-observe skill, build in observable design per this repository's standard. A skill is hard to observe when it calls external engines/subprocesses, runs long with internal retry/fallback state transitions, produces advisory output that depends on human rulings, or fails in ways that are hard to locate afterwards. Reference implementations: `droid-config`'s `scripts/droid_config_audit.py` and `autoreview`'s review history (`--history-summary`).

Standard components (six items, all present in the two verified reference implementations). Exception: when an external system already persists equivalent facts (such as BB thread records), a separate ledger may be skipped, but SKILL.md must state which command to review them with and the remaining gaps:

1. **Single source of truth**: a local, Git-ignored run-history cache, maintained only by scripts, never hand-edited; stored outside the reviewed repository or in the user's home directory, never committed.
2. **Minimal facts**: record only fields needed for retrospectives (engine/model/duration/outcome/stable id); prompts, bodies, diffs, logs and secrets never enter the store.
3. **Decision loop**: the main agent's rulings (accept/reject etc.) are written back by stable id, so result quality is measurable; writing back the same id again overwrites rather than appends.
4. **Aggregate review**: provide a read-only aggregate command that outputs statistics along fixed dimensions plus deterministic review hooks (such as low acceptance rate, high fallback rate), with each based on an explicit numerator/denominator.
5. **Retention cap and rollup**: rolling window + fixed-dimension rollup to prevent unbounded growth; the live window and rollup must not double-count.
6. **Bypass on failure**: failure to record only warns and never changes the main flow's result; the self-test must cover the bookkeeping semantics (rolling, overwrite, double counting, unknown-id rejection).

When all six cannot be met, be conservative: at least provide a read-only check/show-style aggregate command, and state the gaps in SKILL.md.

## Mandatory wrap-up

Once the current task's changes are complete and verified, immediately close the delivery loop; the task must not be declared complete until the loop is closed:

1. Check the current branch, `git status --short` and `git worktree list` again to confirm the scope of files to deliver. Commit all changes from this task and any existing changes the user explicitly asked to deliver; when the user asks to "commit everything in the current repository", use `git add -A` after checking, without missing untracked files and without overwriting or discarding concurrent changes. Before staging, check the "Non-open-source Skills" boundary; such content must not enter a commit.
2. Push the commits to their corresponding remote branch.
3. If the commits are not on `main`, switch to `main`, merge the branch into `main` (fast-forward preferred; stop and report on conflicts), then push `main`. If the commits are already on `main`, confirming `main` has been pushed completes the merge step.
4. Wrap-up must end on `main`, with `git status --short` empty and no untracked files; these two plus a successful push together form the completion criteria. If any is not met, keep working or report the blocker explicitly.

## Owner delivery permission

When the current user is explicitly the repository owner, or ownership has been confirmed via the current authenticated identity and the remote repository's owner, after completing the user's requested changes and passing the necessary checks, you may commit and push directly to the current target branch without asking for further confirmation. Before pushing, still check the branch, workspace and worktrees, stage only files within this task's scope, and preserve unrelated concurrent changes.

This permission covers only delivering repository changes the user explicitly asked for; it does not expand the scope of changes, nor authorize deleting data, rewriting history or pushing unrelated content. When owner identity cannot be confirmed, committing may proceed, but confirm with the user before pushing.
