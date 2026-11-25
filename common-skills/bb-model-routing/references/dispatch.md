# Configuration and dispatch

Requires Python 3.10+, PyYAML, and `bb` on PATH. The entry point is `scripts/bb-dispatch` in the skill directory; it can also be symlinked as the user command `~/.local/bin/bb-dispatch`.

## First-time configuration and migration (首次配置与迁移)

Configuration path precedence: `--config` > `BB_DISPATCH_CONFIG` > `~/.config/bb-dispatch/config.yaml`. When the file does not exist, follow [First-time configuration bootstrap](bootstrap.md) to detect the environment, propose a configuration, and write it after user confirmation. When adjusting existing mappings, reuse the read-only commands from bootstrap step 1 to see which providers and models the target environment actually offers (use the returned IDs), check `permissionModes` and the model's `supportedReasoningEfforts`, and ask the user when several candidates lack a basis for choosing. The catalog proves availability, not price or task quality. The structure follows [config.example.yaml](config.example.yaml); angle-bracket values must be replaced and cannot be dispatched as-is. Write the choice under any alias, e.g. `primary`, then configure the default alias for each difficulty. Configuration contains no credentials; authentication is managed by the BB provider.

The configuration format is `version: 2`. When migrating, move flat `agents.<alias>.model/reasoning` into `agents.<alias>.routes.<difficulty>`; different models and difficulties of the same provider stay under this alias. The script does not accept the old format. When configuration serves multiple environments, use `environments` overrides. The script only reads configuration; it does not install providers or overwrite configuration. Run `--dry-run` on new configuration to verify before dispatching. The model catalog does not automatically produce the user's model preferences.

## Project minimum difficulty (项目最低难度)

User configuration can add `projects: {<project-id>: {min_difficulty: medium}}`, with values `simple`, `medium`, or `complex`. The project ID follows `--project` resolution: in ID mode it defaults to the project owning the target environment, in path mode to the current project. When not configured, the original difficulty is kept; when below the floor it is raised automatically, and route, model, and title are chosen by the actual difficulty.

The project floor applies only to work threads (default `--purpose work`). Review threads use `--purpose review` to be exempt from the project floor and are routed by the requested difficulty. Redispatch keeps the original purpose and requested difficulty.

`selection`, the ledger and dispatch events all record `purpose`. `selection.difficulty` and the ledger's `difficulty` are the actual difficulty; `requested_difficulty` keeps the original request. The raise notice appears both on stderr and in `selection.warnings`, and is visible in dry-run too. Historical statistics count by actual difficulty.

## Dispatch and configuration rules (派发与配置规则)

```bash
bb-dispatch --difficulty simple --task 'Add README examples' --dry-run
bb-dispatch --difficulty medium --task 'Change the tenant isolation boundary; passing tests is not enough to prove there is no leak'
bb-dispatch --difficulty complex --task 'Oracle: rule on the specified technical question' --dry-run
```

`--task` carries only the task itself: goal, scope, necessary inputs, and acceptance requirements. Provider, model, reasoning level, permissions, and catalog validation are handled by the script and configuration; they must not be written into the child-thread prompt, and the child agent is not asked to re-check them. When the user directly gives a provider or model requirement, the caller must adjust the user configuration, then call the script.

Permission precedence: `--permission-mode` > `agents.<alias>.permission_mode` > environment configuration > top-level configuration. When none is configured, native Codex providers that support `auto` default to Approve for me (`auto`), other providers default to `accept-edits`. When an explicitly configured permission is incompatible, report an error.

`fast` controls whether dispatch requests BB's Fast service tier. Defaults to `false` when omitted; a human editing the configuration file to `true` turns it on. The script provides no command-line override and does not accept model-side selection. Precedence: `agents.<alias>.fast` > environment configuration `environments.<id>.fast` > top-level `fast`. If `force_fast: true` is set at top level or in agent configuration, Fast is forced on and exempted from the patrol automatic circuit breaker; `quota_fuse` can also customize the breaker threshold (e.g. break at 95% used) and automatically restore the default threshold after `restore_at` expires. When on and the model supports fast, pass `--service-tier fast`; when off or the model does not support fast, as long as the provider lists service tiers (including `default`), explicitly pass `--service-tier default`, hard-overriding project history memory preferences; omit the parameter only when the whole provider does not support service tiers.

`defaults` maps simple/medium/complex to routes. A string or ordered alias list uses `fallback`: the script validates in configured order and dispatches the first available candidate. To spread independent tasks across candidates, use explicit configuration:

```yaml
defaults:
  simple:
    mode: load-balance
    candidates: [primary, backup]
```

`load-balance` uses a stable hash of the route entry and full task text to order equal-weight candidates for each task. To spread by quota ratio, use a weight mapping:

```yaml
defaults:
  complex:
    mode: weighted-load-balance
    candidates:
      weekly-quota: 2
      monthly-quota: 1
      paused-quota: 0  # restore a positive weight once quota recovers
```

`weighted-load-balance` accepts non-negative finite numbers; `0` pauses that candidate: sampling, fallback, and `--fallback-from` never use it, and its provider or model is not validated. Each tier needs at least one positive-weight candidate; all `0` is an explicit error. Long-run selection probability is proportional to positive weight; weights express only relative proportion, not a concurrency cap. Neither load mode maintains counters; different tasks spread out, and the same task keeps a stable selection and fallback order. All modes continue to same-tier candidates when the first choice fails validation. Each `agents.<alias>` writes `provider` once, and writes `model` and optional `reasoning` in `routes.<difficulty>` or `routes.default`; candidates lacking both are skipped, and switching candidates does not change difficulty. The same provider can thus pick different models by difficulty without creating aliases for model combinations. Explicit reasoning must still pass model catalog validation; when omitted or set to null the provider default is used.

Each dispatch creates an independent BB session; load balancing does not split or migrate the context of one session. Whether a provider's prefix cache hits across independent sessions depends on the provider, account, and model; when candidates land on different providers or models, do not assume they share cache.

The route entry is determined only by `--difficulty simple|medium|complex`; a candidate participates only when it has that difficulty or an explicit `default`. Difficulty grading criteria are maintained only in SKILL.md "Judgment and invocation (判断与调用)" and are not repeated here. If nothing matches, it errors; it does not guess a model.

Precedence: command-line override > `agents.<alias>` configuration > environment configuration > top-level configuration. Candidates are always determined by defaults; the script provides no `--agent` override. `environments.<exact-environment-ID>` can override defaults, agents, permission_mode, fast; a same-named agent is replaced wholesale and must spell out provider and routes. Each agent can control Fast individually via `fast: true|false`. Directory path mode has no environment ID yet, so `environments.<id>` overrides do not apply; only top-level configuration is used. Explicit model requirements are expressed by adjusting configuration, explicit thinking-depth requirements by `--reasoning`, Fast only by editing the configuration file; when configuration is missing, fill it in first, do not silently substitute.

`--fallback-from <alias>` truncates this dispatch's candidates to the suffix starting at that alias, for callers that need to name the continuation candidate; an alias not among the candidates is an error, and the named alias itself is not skipped for cooldown. On actual dispatch, candidates before that alias in the chain are cooled for 15 minutes per provider and model. When the thread already has an ID and `--on-failure` returns `cooled`, use `--redispatch` per SKILL.md "Waiting and concurrency (等待与并发)", which by default keeps the original thread's environment and parent notification mode. When spawn failed and it is confirmed no thread was created, rerunning the original dispatch command skips already-cooled candidates.

`--escalate-from <thread-ID>` and `--unknown <reason>` are both optional ledger annotations: the former records the prior thread where the same task failed or needed rework (the script verifies the thread exists), the latter records a one-sentence grading reason. Grading follows SKILL.md "Judgment and invocation (判断与调用)"; conditions are not repeated here.

`--on-failure <thread-ID>` handles an errored child thread, looking only at BB's structured information: a thread not in `error` state returns `not-failed`; when `bb provider-retry status` lists a BB automatic retry it returns `waiting`. Queued messages on an errored thread are sent only when the thread is retried and do not count as an existing retry. The ledger's `retries` records the number of original-session retries scheduled for the current fault, `retry_ts` the time of the most recent scheduling; when `retries` is greater than 0 it reads `bb thread log`: if no turn has ended since then, the last retry has not run yet, return `waiting`; if a turn ended successfully since then, that fault has recovered and this one counts from scratch (also reset when dispatch back-fills `completed`). When the decline reason of `bb provider-retry explain` is `no-rate-limit-state`, `not-resettable`, or `beyond-maximum-wait`, treat it as quota exhaustion: do not schedule an original-session retry, record `failed` with `quota`. The same handling applies when this fault's `provider/error` in the thread log is HTTP 429 (`errorInfo.httpStatusCode`, or detail starting with `429`) and the JSON `code`, `status`, or `type` is `RESOURCE_EXHAUSTED`, `model_cooldown`, `quota`, `insufficient_quota`, `quota_exceeded`; only these fields are checked, `message` is not scanned. `attempts-exhausted` still means original-session retries are exhausted. Other failures schedule the next attempt with `bb thread retry --send-at` (1, 2, 4 minutes) and return `retry-scheduled`; when BB replies that the turn already has a queued retry (`retry_already_queued`), return `waiting`. Quota cooldown durations are in SKILL.md "Observability (可观测性)". The `retryAt` of an `availability.kind` of `blocked`, or the blocked subscription window's `resetsAtMs` in `provider/rateLimits/updated`, extends the cooldown to that moment; `model_cooldown`'s `reset_seconds` is not used. When retries are exhausted, retry is impossible, or quota exhaustion is established, return `cooled`; the terminal state is not changed during retries, and the thread's earlier success still resets the cooldown. If thread status cannot be read, or the log cannot be read when confirming whether the last retry ran, exit with an error and rerun the same command later; if the log cannot be read when judging quota codes, treat it as undeterminable. Only threads in the ledger are handled; with `--dry-run` it only reports the action, schedules no retry, and does not write the ledger.

`completed` is recorded automatically by the script from BB thread status; `failed` is recorded by `--on-failure` after retries are exhausted or quota exhaustion is established. When detection is wrong or a task is abandoned, correct it with `--record-outcome <thread-ID> --outcome <terminal-state>` (the old name `--record-decision` still works), writing to the local ledger (default `~/.cache/bb-dispatch/ledger.json`); old values `failed_quota`, `failed_transient`, `failed_other` can still be written and count toward consecutive failures like `failed`. Only `quota: true` written by the script is timed as a quota cooldown; a manual `failed_quota` does not lengthen it. `--history-summary` (alias `--stats`) outputs, read-only, aggregate statistics by difficulty and candidate, active cooldowns, deterministic review hooks, and `retry_review`, the last-7-days retry and cooldown summary from the review log `ledger.events.jsonl` (fields in SKILL.md "Observability (可观测性)").

By default the environment is resolved from `bb status`, and the project is that environment's owning project. `--environment` accepts an existing environment ID or a directory path that exists locally: in ID mode `--project` must match the environment's owning project; in path mode the directory is resolved to an absolute path and handed to BB as-is to create a project-checkout attached environment, with the project taken from `--project` or the current `bb status`; when neither is available `--project` must be given explicitly. When dispatching inside a BB thread the current parent thread is linked, keeping the link across environments and projects.

Each call validates that the provider exists and is available, permissions are compatible, and the model and reasoning are in the catalog. When querying the model catalog it also passes the configured selected model, so models just released but not yet in the regular catalog can still be validated by the provider. ID mode validates against the target environment; path mode does not call `bb environment show` but uses the current `bb status` environment as a same-host proxy; when there is no current environment, run inside a BB thread or prepare a proxy environment first. The returned JSON's `selection.validation_environment` records the actual validation environment, equal to the target environment in ID mode. `--dry-run` performs the same read-only validation and outputs the argument array without creating a thread. Actual dispatch returns JSON with `selection` and BB's raw `result`; each call issues at most one spawn (fallback happens only in the pre-spawn validation phase); on timeout or abnormal response query threads first to avoid duplicate creation. `selection.attempts` records failed candidates along the chain and reasons (including cooling candidates), `selection.fallbacks` records untried same-tier aliases, `selection.reconciled` lists terminal states re-recorded from thread status in this call. The catalog is not persistently cached, to avoid using stale configuration after installation, account, or environment changes.

Verification: `python3 -m unittest discover -s scripts -p 'test_*.py'` (run from the skill directory).

## Provider concurrency limits (Provider 并发限制)

Configure `max_concurrency: 1` in `agents.<alias>` (positive integer; omitted means unlimited). By default it limits all models of that provider; `concurrency_models` can specify the model IDs that share the slots. Below, only amp's medium and complex together run at most 1, while grok46 used by simple is unlimited:

```yaml
agents:
  amp:
    provider: acp-amp
    max_concurrency: 1
    concurrency_models: [medium, high]
    routes:
      simple: {model: grok46, reasoning: medium}
      medium: {model: medium, reasoning: medium}
      complex: {model: high, reasoning: medium}
```

Slots are shared by actual provider ID, not split by alias, difficulty, project, or parent thread. `concurrency_models` must be a non-empty list of model IDs and requires `max_concurrency` too; listed models share the cap together, unlisted models are not capacity-limited. When multiple aliases in the same effective environment configuration point to the same provider, take the minimum of the configured caps and merge the limited model sets; if any alias with a cap omits the model scope, all models are limited. Same-named environment aliases are still replaced wholesale, so keep the needed cap in the replacement. Multiple callers should use consistent limit configuration; script calls without a configured cap dispatch as before.

Script processes on the same machine, same OS user, and same BB service serialize query, reservation, and creation through the fixed `~/.cache/bb-dispatch/concurrency.lock`; `--config`, `--ledger`, and `BB_DISPATCH_LEDGER_PATH` do not change the location of the lock and reservations. Different machines or OS users do not share limits. The lock protects only one creation and is not held while the task runs; when the lock is busy for about 10 seconds it exits explicitly without creating a thread, and can be retried later.

Before dispatch, it reads live status from `bb thread list --include-hidden`; by default all active threads of that provider count toward occupancy (including threads created by other entry points). When a model scope is configured, only threads explicitly registered as out-of-scope models are excluded from the pool; the BB list does not return models, so the script identifies its own dispatches by the model ID in reservations. Old reservations and threads from other entry points lacking model info are still conservatively counted in the limited pool and released after the corresponding turn ends; out-of-scope new dispatches themselves get no capacity check. Archived threads (`archivedAt` non-null) do not occupy slots, and residual queues, interactions, and registered reservations are excluded with them. Archiving is the capacity boundary here; BB archiving may give an existing running turn about 30 seconds of grace, so a slot freed by archiving does not mean the run stopped immediately. Pending interactions, running, and unknown states of unarchived threads still conservatively occupy slots; `idle` releases only with explicitly no queued messages and no pending interactions. For `error` with explicitly no pending interactions, known queue states `none`, `waiting`, `failed` do not occupy slots: ordinary queued messages are sent only after the failed turn is retried, and queuing itself does not mean running; unknown queue states still count. Apart from archiving releasing directly, threads newly created by the script additionally keep a reservation until a post-dispatch `turn/completed` appears in the log, so the initial `idle` after creation is not mistaken for completion. If an interruption has no end event, the reservation is kept and handled by the recovery commands below. Active threads and their reservations are de-duplicated when counting.

When a candidate is full, it records `selection.attempts` and tries the next same-tier candidate; when all are full it errors explicitly, without waiting, creating a queue, or counting failure or circuit-breaker cooldown. All candidates cooling, or naming one with `--fallback-from`, cannot bypass the capacity limit either. `selection.concurrency` returns the selected provider's `limit` and pre-dispatch `used`, plus `models` when there is a model scope; out-of-scope models return no capacity limit. `--dry-run` only checks capacity read-only, makes no reservation, does not change concurrency state, and the result is only a snapshot of that moment.

Concurrency reservations are stored in `concurrency.json` in the same directory, independent of the bypass-on-failure statistics ledger, and store only reservation ID, provider, model ID, time, and thread ID. Out-of-scope models are registered too, so later dispatches can explicitly exclude them; they do not occupy the limited model pool. When the reservation file is corrupt, cannot be locked, or cannot be saved, it fails explicitly; when live thread status cannot be queried, limited candidates are skipped. Limits are never cancelled because the statistics ledger failed. The reservation is written before spawn; after timeout, exception, or process crash, unknown creation results are not released automatically, to avoid duplicate dispatch:

```bash
bb-dispatch --concurrency-status
bb thread list --include-hidden --json
bb thread show <thread-ID> --json
bb-dispatch --release-reservation <reservation-ID>
```

`--concurrency-status` outputs, read-only, the whole provider's live occupancy and minimal facts of reservations still occupying, without writing state; its `usage` is the total over all models, actual usage of a model scope is per `selection.concurrency.used` at dispatch time, and registered models can be seen in `reservations`. After confirming that creation did not succeed, or the corresponding turn has ended, release by stable reservation ID; unknown IDs are rejected, repeated release does not delete other reservations by mistake; with `--dry-run` it only previews. Releasing a reservation does not stop the thread; still-active threads continue to be counted from BB status. Reservations that ended normally are cleaned up automatically on later dispatches; pending reservations are kept for recovery and are not force-expired by time.

The limit covers the script's new-dispatch entry. Continuing old threads, `--on-failure` original-session retries, BB automatic retries, and directly created threads do not request a slot first and may still overlap with dispatched tasks; while active they affect the next script dispatch. BB already persists thread status, turn logs, and parent thread notifications, reviewable with `bb thread show` / `bb thread log <thread-ID> --all --json`. Only current capacity and recovery queries are provided here, with no separate history ledger; concurrency wait time and full-skip counts are not aggregated yet, and historical dispatch and quality verdicts continue to use the existing `--history-summary`.

## Route unavailable (路由不可用)

Candidate switching covers only pre-dispatch validation: when the provider does not exist or is unavailable, permissions are incompatible, or the model or reasoning is not in the catalog, record that candidate's error and try the next; when all fail, aggregate each candidate's errors. Once spawn is issued there is no retry, and the failed candidate is cooled immediately: on failure or unclear result, first confirm with `bb thread list`/`bb thread show` whether it was created; after confirming it was not, rerun the same command keeping difficulty and task text. Runtime thread errors (quota exhaustion, provider interruption, session error) run `--on-failure` per SKILL.md "Waiting and concurrency (等待与并发)" and wait or switch candidates per its returned `action`; deterministic callers (e.g. an orchestration driver) can also persist `selection.fallbacks` and name candidates themselves with `--fallback-from`. Before continuing an existing thread, confirm the original turn has ended and check completed work, and use the continuation method that provider supports; do not pass off recreating the whole task as continuation.

## Session titles (会话标题)

The script prefixes titles by `--difficulty` and candidate agent:
- **Colour represents difficulty**: `simple` is green, `medium` yellow, `complex` red.
- **Shape represents account**: identified via the agent configuration's `shape` or the default alias mapping:
  - Circle (default / `codex`): `🟢` / `🟡` / `🔴`
  - Square (`codexl` / `codex-l` / `shape: square`): `🟩` / `🟨` / `🟥`
  - Heart (`codexb` / `codex-b` / `shape: heart`): `💚` / `💛` / `❤️`
  - Book (`codexm` / `codex-m` / `shape: book`): `📗` / `📒` / `📕`

`--title` sets the body; when omitted or whitespace-only, the task text is used. The script collapses whitespace, removes an existing leading old `[Agent]`, difficulty dot, or shape prefix, then adds the prefix for this dispatch's difficulty and account; the body is at most 80 characters (including the ellipsis). The create command always passes `--title`, and `selection.title` returns the title actually submitted. Passing a short title is recommended, to keep task details out of the session list. Later explicit renames can still change the title; existing threads are not renamed automatically.
