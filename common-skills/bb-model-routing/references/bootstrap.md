# First-time configuration bootstrap (Bootstrap)

Entry condition: there is truly no file at the resolved configuration path (`--config` > `BB_DISPATCH_CONFIG` > `~/.config/bb-dispatch/config.yaml`). When `bb-dispatch` reports `cannot read config <path>`, check this path first: enter bootstrap only if the file does not exist; if the file exists but cannot be read (corrupt YAML, path is a directory, no permission), it is a fault in existing configuration — report the verbatim error to the user and repair that file, do not create a new one over it.

Goal: within the same conversation, detect the providers and models actually available in BB, propose a configuration that can dispatch directly, write it after user confirmation and verify it with `--dry-run`, then return to the original dispatch task. Keep progress visible to the user throughout: before each stage, say in one or two sentences what you are doing and what you just found, in the reply body. Digest the raw JSON of detection commands yourself; give the user organized conclusions. Unattended callers (orchestration drivers, automation scripts) have nobody to confirm, so they fail with missing configuration and report as usual, without entering bootstrap.

Detection, writing, and self-test all reuse the original dispatch's explicit parameters: `--config`, `--project`, `--environment`, and any explicitly given `--permission-mode`, `--reasoning`; only when not specified use the current thread's context and configuration defaults.

## 1. Inform and start detection

First tell the user: no dispatch configuration was found at <path>; adding one lets dispatch continue; you are now detecting the providers and models connected to local BB, running only a few read-only commands. Then run:

```bash
bb status --json                       # thread.id is <thread-id>; thread.environment.display.id is <env>
bb thread show <thread-id> --json      # thread.providerId is the provider the current session is using
bb provider list --environment <env> --json
bb provider models <provider-id> --environment <env> --json   # run once for each available provider
```

When the original dispatch specified an environment ID, provider queries use that ID; when it specified a directory path, queries still use the current thread's environment as a proxy (consistent with the script), and the path is passed back as-is only during self-test. When not running inside a BB thread (`bb status --json` has no `thread`) and no environment ID is specified, omit `--environment` and `thread show`, and use the local default directory.

For each provider record `id`, `displayName`, `available`, `capabilities.permissionModes`, and for each catalog entry `id`, `displayName`, `description`, `supportedReasoningEfforts[*].reasoningEffort`, `defaultReasoningEffort`, `isDefault`. Catalogs may have hundreds of entries; extract only these fields, optionally summarizing with a one-off script. `maintenance` is a plugin maintenance capability flag, not an availability signal; do not exclude based on it.

Candidate providers: `available: true` with a non-empty model catalog. For unavailable providers record the name and cause hints (`strings.signInHint`, etc.); record empty-catalog ones too; neither goes into the proposal. If there are no candidates at all, stop bootstrap: tell the user to first connect and sign in to at least one provider in BB (BB's built-in `acp-provider` skill can guide the setup), then come back to dispatch.

## 2. Report detection results

List candidate providers in a short table: display name, provider id, supported permission modes, model count, models marked `isDefault`; mark the provider the current session is using — it has already proven it runs. After the table, list unavailable or empty-catalog providers in one sentence.

## 3. Generate the proposed configuration

Write a minimal proposal following the structure of [config.example.yaml](config.example.yaml), with `defaults` as a string or ordered alias list (fallback form). Decide in the order below, taking the first matching rule for each; keywords are case-insensitive substring matches, and ties go to the entry earlier in the catalog:

- Primary provider: the one the current session is using; when it is not a candidate or you are not in a BB thread, choose the candidate whose catalog has text descriptions and the most models.
- Permission mode: if the original dispatch explicitly passed `--permission-mode`, use it, and the primary provider must support it; otherwise native Codex supporting `auto` uses `auto` (Approve for me); other providers use `accept-edits` if supported, otherwise a mode they support, explaining what permission the child thread gets as a result (`full` is fully autonomous execution). When keeping the provider default, omit top-level `permission_mode`; for individual overrides write `agents.<alias>.permission_mode`.
- Fast: configuration explicitly writes `fast: false`; a human changes it to `true` when needed. This is a consumption switch toggled by hand-editing the file; when omitted the script defaults to off; do not infer it from the current session or the model catalog.
- `simple` model: description contains fast, affordable, flash, lite, mini; next, id contains these words; next, `isDefault`; if none, choose by your own knowledge of model tiers.
- `medium` model: description contains latest workhorse; next, contains workhorse or everyday; next, `isDefault`; if none, same as above. When the matched model is the same as `simple` and the catalog has other models, move on to the next rule.
- `complex` model: description contains frontier, most capable, most demanding; next, id contains pro, opus, max; if none, same as above.
- With only one model, all three tiers use it. Mark entries chosen by id words or your own knowledge as "unsure, please confirm".
- `reasoning`: write only exact strings from `supportedReasoningEfforts[*].reasoningEffort`. `simple` uses `defaultReasoningEffort`; `medium` uses `medium`, else the default; `complex` uses `xhigh`, else `high`, else the default. When the model has only one level, write it for all three tiers and explain that reasoning cannot differentiate them; when there is no level information, omit the field.
- Backup provider: among the remaining candidates it must support the chosen permission mode; prefer those whose catalog has text descriptions; if still several, take the one earliest in `provider list` order, and explain this is a stable selection rule, not a quality ranking. If there is one, append a fallback alias to each tier, choosing models from its catalog by the same rules; if not, use a single alias.
- Keep model ids as-is, wrapped in single quotes, with single quotes in the value written as two single quotes. Ids may contain `/`, `[`, or `"`; wrapping an id containing double quotes in double quotes without escaping produces invalid YAML.

Give the user the whole proposed YAML, with one sentence explaining the basis for each choice. After the YAML give a numbered decision list: the first item is "write as proposed", the rest are common alternatives: switch primary provider, switch a tier's model or reasoning level, change permission mode, switch to load balancing (format in [Configuration and dispatch](dispatch.md)). When the host has a native question tool you may use it to collect the choice; otherwise end the turn and wait for the user's reply.

## 4. Write and verify

After user confirmation, create the directory and write the configuration file, then run one self-test per tier; when the proposal includes a backup alias, also run each tier once starting from the backup alias and confirm `selection.agent` equals that alias:

```bash
bb-dispatch --difficulty simple --task 'config self-test' --dry-run
bb-dispatch --difficulty medium --task 'config self-test' --dry-run
bb-dispatch --difficulty complex --task 'config self-test' --dry-run
bb-dispatch --difficulty simple --task 'config self-test' --dry-run --fallback-from <backup-alias>
bb-dispatch --difficulty medium --task 'config self-test' --dry-run --fallback-from <backup-alias>
bb-dispatch --difficulty complex --task 'config self-test' --dry-run --fallback-from <backup-alias>
```

When the original dispatch carried `--config`, `--environment`, `--project`, or `--permission-mode`, the self-test carries the same parameters; when the original dispatch explicitly passed `--reasoning`, run one extra self-test with it for that difficulty. When not inside a BB thread you must explicitly pass `--environment <existing-environment-ID>`; the script cannot validate without an environment.

After all pass, tell the user: where the configuration file is, which provider and model each of the three tiers will use, whether the backup candidates also passed, and that editing the file directly adjusts it later; then continue the original dispatch task with all original parameters. When a tier fails, tell the user the verbatim error and a fix, apply it in the direction the user confirms, and rerun that tier; handle a backup alias failing a tier the same way — the primary passing does not count as all passing. Fixes are limited to fields within the scope the user has confirmed; switching to an unconfirmed model or provider requires going back to step 3.

## Completion criteria

The configuration file is written, all three tier self-tests (including backup aliases) pass, the user knows the configuration path and how to adjust it, and the original dispatch task has continued.
