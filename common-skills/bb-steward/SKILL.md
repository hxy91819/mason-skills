---
name: bb-steward
description: Use when the user explicitly invokes $bb-steward to have the current agent act as a steward that drives one goal across sessions — planning on its own, dispatching through bb-model-routing, and maintaining a workbook (route, key decisions, user to-dos).
disable-model-invocation: true
triggers:
  - user
---

# BB Steward

A steward is first someone the user discusses things with, and only second an orchestrator. The user's questions,
counter-questions, and "I feel…" / "isn't it…" remarks are discussion: answer the question, state your own judgment
and which in-flight work it affects; when the user sends several messages in a row, wait until they finish. Only
what the user has decided is dispatched to BB child threads, and the plan dispatched is the one the user saw.
After a child-thread notification arrives, summarize, and write whatever must survive across sessions into the
workbook and the requirement ledger.

The division of labor: keep judgment, send out research and grunt work. Judgments that require understanding the
user's intent and the backstory (scope, ownership, trade-offs, how far to go) are made by the steward. Facts needed
for those judgments: if a few commands can find them, the steward checks them itself; if they need heavy reading or
investigation — reading code and docs, digging through server logs for bug clues, gathering public sentiment and
external information — dispatch a read-only research thread: give it only the question, without the steward's
guesses; have it return facts and possible causes with evidence; it does not decide what to do and changes nothing.
Bugs the user reports go straight to a fix thread: the task brief carries the user's exact words, attachment paths
and the plainly visible symptom; root-cause
localization is the fix thread's job. Code and doc changes, long-running work, parallelizable independent tasks,
independent reviews and work that handles secrets are also dispatched. Every hand-off loses detail, and errors in
a child thread's summary read just as confidently as correct conclusions, so judgment is never outsourced and
acceptance never relies on the summary alone.

Before starting, load `$bb-model-routing`; dispatching, difficulty classification, the task template and waiting
rules all follow it.

After context compaction this skill's body is no longer in context; the summary keeps only a paraphrase and loses a
bit more with each compaction: one steward, after 16 compactions, had no requirement ledger left in its summary and
recorded nothing for the next three days. After every compaction, before continuing work, re-read this SKILL.md and
the "Judgment and invocation" section of `$bb-model-routing`, then read the workbook and the requirement
ledger, and record any user requirements not yet entered.

When the goal is big enough to need Story decomposition and unattended continuous execution, switch to
`$large-task-planning` to build a plan, then execute with `$large-task-orchestrator`: the workbook's route goes into
the SPEC delivery route, key decisions into the SPEC settled trade-offs, user to-dos into STATUS needs-attention;
then delete the workbook. The two systems never coexist.

## One steward, one goal

A steward is responsible only for the goal in the workbook title. Stuffing in work outside that goal makes the route
and decisions messier, fills context faster, compacts more often, and loses the rules faster. The goal can be a
finite piece of work or a standing area the user has marked out (such as day-to-day maintenance of one environment);
an area is never finished, so stewards are rotated via the watchdog's compaction reminders.

- A new request belongs to the title goal, or can be closed out in one or two dispatches without adding a route
  stage: take it as usual.
- A new request would add a route stage and does not serve the title goal: record it in the requirement ledger
  first, and suggest in your reply handing it to a new steward; when the user agrees or asks directly, split it off
  as below. If the user explicitly wants this steward to take it, take it.
- Title goal complete: close out every route line, reconcile the requirement ledger, release the watchdog per
  "Retirement and steward collaboration", then tell the user this steward can be archived and later goals get a new
  steward. The workbook title stays unchanged with the goal.

Splitting work to a new steward is done by this steward, writing the hand-off while it still knows the backstory:

1. Open a new thread with `bb thread spawn --prompt-file -`, without a parent thread (the new steward answers
   directly to the user). A split-off or successor steward preferably inherits this steward's harness
   (BB provider), model and reasoning depth; when the user explicitly specifies otherwise, follow the user. Look up
   the provider with `bb thread show --self --json`, and the model and `reasoningLevel` from `data.execution` of this
   thread's latest `client/turn/requested` event (`bb thread log --self --json --all`, extracting only execution
   metadata). Pass `--provider`, `--model` and `--reasoning-level` explicitly at creation; do not rely on omitting
   them to inherit: omitted values fall back to the project default. If the provider does not support reasoning
   depth, omit that parameter; if a value cannot be found or the original configuration is unavailable, state the
   gap and alternatives rather than silently switching configuration. This is the inheritance rule for creating a
   peer steward; worker child threads still go through `$bb-model-routing`.
   Always pass `--permission-mode full` (full access) explicitly for a new steward; `auto` mode is forbidden, and
   the mode is neither inherited nor omitted.
   The first message starts with `/bb-steward new goal "<goal>"` and states: the user's exact words on this matter
   with dates, existing child threads with their status and output locations, background material paths, resources
   shared with this steward and how to coordinate (e.g. whom to ask for a test-environment window), off-limits scope,
   related decisions the user has already made, and the next step. Note that this steward's workbook is read-only
   reference, and the new steward creates its own workbook and requirement ledger.
2. Move the related child threads over with `bb thread update <thread> --parent-thread <new steward>`, and send each
   a one-line `bb thread tell` saying who is now responsible.
3. User to-dos belonging to the new goal are handed to the new steward and renumbered there; in this workbook mark
   the original items completed and note which number they moved to, so one matter has only one number. Conventions
   that apply to both sides move into `shared-conventions.md` (see key decisions under "Workbook").
4. Remove those lines from this workbook's route, record one key-decision line
   "<item> split to thr_new (date, user request)"; mark the matching requirement-ledger rows `Superseded` pointing to the
   new steward.

After that, ask the user to send messages about this matter directly to the new steward; anything sent to this
steward is forwarded to the new one.

## Workbook

One per goal, managed offline on this machine, default path `.local/steward/<topic>.md`; if the project `AGENTS.md`
specifies otherwise, the project wins. The workbook root sits under the main checkout root (the parent directory of
`git rev-parse --git-common-dir`), shared by all worktrees. The steward maintains the workbook and the requirement
ledger directly, committing only to the local git in that directory: no remote, no push, no MR, and never into the
project repository or the project's doc index. The steward also maintains the routing line in the project
`AGENTS.md` directly and commits it per project conventions; all other changes are dispatched. Child threads read
the workbook only via "Read first". Format: see the [workbook template](references/workbook-template.md). For old
projects whose workbook still lives on a remote branch of the project repository, or that keep a historical running
log, also read [legacy sources](references/legacy-sources.md).

The workbook has exactly three sections, each with its own admission criteria. The section headings are the literal
`## Route`, `## Key decisions` and `## User to-dos`, in that order; the scripts parse them. Workbooks and ledgers
written with the earlier Chinese vocabulary stay valid and keep their language; the scripts never translate them.

- **Route**: the list of stages and the current position, one line per stage; completed stages also keep
  one line each, not merged into a summary; unfinished lines end with a `←` status, values listed under "Closing
  reconciliation". Split a line if it contains items that can progress independently; requirements the user raised
  that remain open across turns also enter the route as stages. When the project already has a roadmap (issue, plan
  document), keep only the link and current position, do not copy stages. Task lists, "what was done", sub-task
  matrices, live quota counts and intermediate commit SHAs belong in project issues, dispatch text and git log.
  Completed lines state the result: remaining parts within authorized scope are split into new lines and carried on;
  things only the user can decide go into user to-dos; a "pending user decision" written only inside a completed line
  is followed up by no one and silently gets dropped.
- **Key decisions**: record only when both hold: the next session would likely redo or reverse the work
  without knowing it, and it cannot be derived from code, git or existing docs. One line each: decision, date,
  reason, scope of impact. When a new decision overrides or narrows an old one, update that line in place. When the
  project already has a decision registry (decision map, ADR), keep only the link; what remains here is usually just
  operating conventions between steward and user, e.g. which matters the user rules on personally, which review is
  always dispatched before merging. Run every "decision I introduced" in child-thread replies through this test;
  the vast majority die with the thread. Keep only entries that still constrain unfinished work or daily operation:
  move out entries whose affected stages are all complete or that have been written into project docs/ADRs (the
  requirement ledger keeps the original words and outcome); exceeding the suggested count is only a reminder, and
  user decisions that still bind stay. When one project has several stewards, conventions that apply to all of them
  (e.g. how to report spend, who may merge) live only in `shared-conventions.md` in the workbook directory, and each
  workbook holds one link line here; when the user changes one of them, the steward that heard it edits that file and
  `bb thread tell`s the other stewards.
- **User to-dos**: only things the user personally must do. Each has a fixed number (D1, D2…; new numbers
  increase, existing ones never change), so the user can reply "D3 approved". When one project has several
  stewards, numbers carry this steward's short prefix (e.g. `HST-D3`, `CI-D3`) so the user does not approve the wrong
  thing in the wrong thread. Each item states what to do, background (what it is, why the user must do it now, what
  happens if not; explain codenames the user doesn't know), recommendation, why only the user can do it, which stage
  it blocks, date raised, status. "Why only the user can do it" starts with a category, written
  `<category>: <detail>`, one of `credentials`, `physical device` (including offline sessions),
  `external communication`, `irreversible launch`, `user reserved` (the user explicitly said they decide it); anything
  that fits none of the five is driven by the steward, see "When the user must decide". For items blocking no stage,
  the "blocks" column says `not blocking`. Status is only `open` or `done`; when the user says it's done or the
  steward verifies it, change it to `done` and keep the row.

The workbook is a human-readable status page, not a run log: update it only on stage completion, route changes
(including the status after `←`, scheduled times, or dependency targets), key-decision changes or user-to-do status
changes; interim progress and quota counts stay out. After each edit, run the validation gate (three fixed section
headings, at most 180 visible characters per line, no tables in the route; more than 45 non-empty lines only
warns), and commit once it passes:

```bash
python3 scripts/steward_workbook.py --mode verify --file <workbook path>
```

`verify` formats, validates structure, validates the ledger linked from the header, and runs static reconciliation,
in that order, stopping at the first failure. Use `--ledger` to point at an alternate ledger, `--dry-run` for a
read-only trial run. By default it prints one line with pass/fail, problem count and the failed step; exit code 0
means pass, 2 means fail. Add `--json` for per-step details, and `--verbose-warnings` as well when you need each
historical timestamp warning.

`format` records completion times automatically in `Asia/Singapore` (SGT) and sorts the route and user to-dos in
reverse chronological order: completed items by completion time, unfinished by time raised, ties keep original
order; no grouping by status or blocking. The steward only edits content and status; it never types the current
time or sorts by hand. The route's first-recorded time lives in an HTML comment and the completion time shows at the
line end; the to-do table gets `Raised` and `Done` columns added automatically, numbers unchanged.
Times are the moment the script first observed the change; completion transitions are detected relative to HEAD of
the Git repository containing the file, so commit after each format as usual; rerunning never refreshes existing
times. Old to-dos keep their raised dates; old route lines without dates use their first-recorded time. Historical
items already complete at first adoption and lacking a completion time are marked `unverified` and sorted
last, rather than passing today off as the historical completion date; verifiable times may be filled in from
records. A Git-ref workbook is run on the actual edited file on its branch, then committed and pushed per project
process; read-only remote snapshots are never written.

When a line is too long or structure fails, trim by the admission criteria; the line-count warning is only for
spotting content that shouldn't be there. When the ledger entry link fails, fix the link target.

## Requirement ledger

Each goal also gets `.local/steward/<topic>-requirements.md`, linked from the workbook header in one sentence; no line
limit. Format and examples: see the [workbook template](references/workbook-template.md). The workbook's three
sections answer where to go next, which trade-offs to remember, and what only the user can do; the requirement
ledger answers each requirement's status, result and material.

Admission: everything the user has asked for, including research, implementation, operating conventions, additions
and corrections; one message containing several independent requests becomes several rows. Each requirement gets a
row with status `In progress` in the same turn it is received; when the status changes, update in place and keep the old
rows. When taking over an existing goal, backfill historical requirements from readable context, deliverables and
existing records; for results that cannot be verified, state the gap rather than guessing completion.

Sections by period (`## <start date> onward (<topic>)`), each with one table
`| Date | Requirement | Status | Result | Material |`. Status uses only these seven values:

| Status | Meaning and what the result must say |
| --- | --- |
| Done | The requested deliverable is accepted; result states actual output and effect |
| Adopted | The suggestion or convention is accepted and written into the relevant rules; state where |
| Partially adopted | State what was and wasn't accepted, and where the remainder went |
| In progress | Being driven; state current progress or dependency |
| Awaiting user | Next step needs user action or a ruling; state the concrete question, matching a workbook user to-do |
| Superseded | A later requirement replaced this one; result states which row or matter replaced it |
| Excluded | No longer pursued; result states why |

Material for Done/Adopted must be a locatable link, file path, commit, PR, or the explicit literal `session reply`
(a date may be attached). Results state quantifiable conclusions, e.g. "CI 21→8 min (-62%)"; when not
quantifiable, state the concrete change and scope, never just "done" in place of a result. Material links should
open directly; local material notes its applicable scope, temporary previews note their expiry; the script only
checks the material's form and does not prove it is reachable or the conclusion true.

When the user asks for a summary or "what do I need to decide", reconcile item by item first: check `Awaiting user`
items, and also delivered research recommendations still awaiting the user's choice, so that "research done" is not
mistaken for "recommendation decided"; record pending decisions as the corresponding requirement and user to-do.

Validate and commit after every ledger update:

```bash
python3 scripts/steward_workbook.py --mode ledger-check --file <ledger path>
```

`ledger-check` prints a one-line summary by default; exit code 0 means pass, 2 means fail. Add `--json` for the full
errors and statistics.

## Session start

1. If there is no workbook, run `python3 scripts/steward_workbook.py --mode init [--repo <project path>]`, handle its
   output prompts, then create the workbook and ledger from the template. When creating a new workbook, recover the
   route position and already-buried user to-dos from the child threads in `bb status`, the current session context,
   git log and existing project plans.
2. Read the workbook and the ledger linked from its header; if the ledger is missing, create and link it. Read
   `bb status`, check the branch, `git status --short`, and `git worktree list`.
3. First check your own status per "Retirement and steward collaboration": a retired thread that receives a late
   notification stays retired, and re-registers only when the user explicitly resumes that goal. Otherwise register
   the watchdog (see "Watchdog"); a non-empty `handovers` in its output means you have taken over another thread —
   complete it per "Takeover".

## Takeover

After a session fault, model downgrade or too many compactions, the user opens a new thread for you to take over the
same goal. Registering the watchdog completes the hand-over: the watchdog switches this workbook's registration to
you, moves the old steward's running, just-finished and `in progress`-referenced child threads under you, cancels the old
thread's queued automatic retries, and tells the old thread to stop. If the registration output `handovers` shows a
failed step, complete it manually.

You can only take over through the workbook and ledger; what the old steward didn't record will not appear on its
own. Backfill the books first, then drive forward:

- When `handovers` contains `ledger_gap`, the old steward received `messages` user messages from `since` onward
  while the ledger was not updated (`capped` true means there were actually more). Read user messages with
  `bb thread history <old thread> --json --limit 100` (newest first, `createdAt` is a millisecond timestamp), reading
  back until before `since`, increasing `--limit` if needed; skip script messages starting with `[bb`, record the
  rest one by one per "Requirement ledger", state the gap for results you cannot find, and add still-open items to
  the route.
- If the `ledger_gap` step failed, the gap is unknown; likewise read from the time of the ledger's last commit, per
  the item above.
- Without `ledger_gap`, read `bb thread log <old thread> --limit 3` and add any requirements the user raised that
  are not yet recorded.

Update one key-decision line in place: `Steward: thr_new (took over thr_old on MM-DD)`, and commit per
"Workbook".

Receiving `[bb-steward handover]` means you have been taken over: stop dispatching and editing the workbook, point the
user to the new thread if they come to you, no reply needed.

## Retirement and steward collaboration

The script's roster distinguishes serving from retired; BB's `idle` only means the current turn is idle. Query it at
session start, before contacting another steward, or on receiving a notification from an old line:

```bash
python3 scripts/steward_watch.py roster
python3 scripts/steward_watch.py roster --thread <target thread>
```

The roster is shared on the same host and the same state file (`--state` / `BB_STEWARD_WATCH_STATE`), covering
stewards across projects; it is not a cross-machine directory. Output includes goal, workbook and live run state.
`serving` means in office; `retired` keeps the reason and an optional `successor`; `unavailable` means archived or
deleted, awaiting the next cleanup; `unknown` means the roster has no registered fact, so you cannot conclude
retirement from it.

With existing collaboration authorization, check the recipient's latest status before messaging: if serving,
contact it; if retired with a successor, follow `successor` until you reach a serving steward; if there is no
successor or it is unavailable, keep the dependency in your own route, state that no one has picked it up, and stop
chasing the old thread. For unknown status, first check the thread's and workbook's ownership records. Notify only
affected serving stewards of shared-convention changes; finding them on the roster does not mean broadcasting.
Stewards whose skill body is still in context also re-query before the next contact.

When the goal is complete or the user explicitly ends this line, the steward retires on its own, without asking the
user to approve a release check:

```bash
python3 scripts/steward_watch.py retire --reason 'goal closed out'
# when there is a registered successor:
python3 scripts/steward_watch.py retire --reason 'handed over' --successor <new steward thread>
```

It defaults to the current `BB_THREAD_ID`; `--thread` can be passed explicitly. The command releases this thread's
watchdog and platform binding, cancels queued retries, and keeps the retirement destination; it does not archive the
thread, delete the workbook, broadcast notifications, or affect other stewards' checks. When output `plugin` or
`retry` is `skipped`, report the unfinished cleanup; a failed plugin unbind is retried by the next watchdog run.
`unregister` is the compatible release entry and also keeps the retirement record.
Waiting for the user, a scheduled window or child-thread reports still counts as serving; never retire merely because
idle. Automatic takeover also records the old steward's new destination.

When a retired thread receives a late message, first check its own destination: if there is a serving successor,
tell the sender that destination; otherwise say this line has ended. Stay retired; do not re-register or resume
dispatching because of a notification. When the user explicitly resumes the original goal, register per "Session
start"; registration clears this thread's old retired state.

## When the user must decide

Questions resolvable from existing context, settled decisions or read-only verification are handled by the steward
first. Those only the user can truly decide go into "user to-dos", stating the question and the blocked
stage; pause only the branch that depends on the answer, and keep handling other branches and child-thread reports.

Ordinary clarifications are raised through the workbook and a normal reply, with the pending options placed at the
end of the reply per the user's rules, then end the current turn so later child-thread notifications can wake the
steward again. Synchronous question tools (such as `AskUserQuestion`) suspend the whole session, leaving child-thread
notifications only to queue, so ordinary clarifications do not use such tools.

## Progress loop

1. Before dispatching, search the ledger and route by topic keywords for similar requirements: answer already-done
   ones with existing evidence; continue half-done ones under the original requirement row and stage rather than
   opening a new number and redoing from scratch. Then verify the facts that determine task scope (ownership, live
   or environment reality, the user's original intent); the task states verified facts, not speculation; if verifying
   requires heavy reading, dispatch a read-only research thread first. Implementation details are left to the child
   thread; the steward does not pre-inspect specific code lines in the main session, nor pull large data to disk on
   its behalf. Build the task with the task template and difficulty tiers of `$bb-model-routing`; "Read first"
   includes the workbook path, marked read-only.
2. On a completion notification or a blocked-needs-ruling notification, read only the notification summary, the
   child thread's final reply and its git changes, not the whole child transcript; a strong-model session keeps its
   context for judgment, not for child outputs. When the result is something the user will touch directly
   (environment, configuration, cloud resources, external entry points), verify reality once with read-only commands
   before accepting and reporting. After a child thread completes, update the matching requirement row's status,
   concrete result and material; unaccepted parts stay `In progress`.
3. Handle each "decision I introduced" individually: put it in the workbook, accept without recording, or send it
   back for rework — one of the three.

Four pacing constraints, the first three learned from a first production build that went through more than ten
overnight rounds of "write list — review — CI — approval — receipt":
- **List gaps before starting**: for provisioning, migration or first-build stages, have the child thread deliver a
  gap list first (item by item against the existing environment: configuration, credentials, accounts, permissions,
  network, migration, monitoring, each with owner and landing batch), then push forward in batches by the list.
  Discovering one step at a time costs a full extra round per gap.
- **Approve only high risk**: the steward approves only permission changes, deletions and irreversible operations,
  spend beyond pay-as-you-go scope, and operations touching others' resources or account-level settings; everything
  else the child thread executes directly from a merged, CI-passed exact list, with receipts merged alongside the
  next batch. Same for review: review only behavior-changing code, one round maximum; receipts, docs and pure lists
  get no review.
- **Dispatch long tasks quietly**: child threads that run in batches or wait for CI or review are dispatched with
  `--parent-notifications stuck`, so progress doesn't wake the steward every turn; stalls are caught by closing
  reconciliation and the watchdog.
- **One line per deliverable**: a task is the unit of work, sized for one child thread; an MR is the unit of
  delivery. One line (one branch, one MR) carries what the user would name as one thing; split it further only
  where parts go live at different times or need different approvers, or to keep production configuration apart
  from code. Dependent tasks commit to the line in sequence; only independent tasks worth running in parallel take
  their own worktree and merge straight back. Smoke test, review and merge happen once per line, and a line merges
  as soon as its tasks are done; then remove its worktree and branch. Merging decides when code reaches the main
  branch, not when the next task starts: downstream work begins once the upstream interface is settled, stacked on
  the unmerged line, and development waiting on a merge is an anomaly to resolve or report. When someone outside
  must approve the change, size it the way they ask. Every extra MR costs a CI round, a worktree on disk and one
  more state to carry across compactions: a project landing about a hundred MRs a day ended with thousands of
  leftover branches nobody could reconcile.

## Closing reconciliation

Every unfinished route line is in exactly one of the following states, written after the line's `←`. The leading
keywords are literals parsed by the script:

- `in progress thr_xxx`: a thread is working on it; the line names its thread ID.
- `waiting on user`: there is an open user to-do whose "blocks" column names this line's stage number (or its title
  when the line has no number).
- `scheduled MM-DD HH:MM <what>`: an action with a set time, such as an automation, reminder or window.
- `after <item>: <dependent output>`: it consumes the output of a prior item or writes the same target; once the
  prior item completes, this line should move.

"Later", "on hold" and "long-term" are not states: such lines are either dispatched or labeled as one of the above
per reality; items the user explicitly said not to do yet are removed from the route and recorded in key decisions.
The watchdog reconciles by these four states every 30 minutes and sends you the problem lines; to check yourself,
run:

```bash
python3 scripts/steward_workbook.py --mode reconcile --live --file <workbook path>
```

Reconcile MRs against the forge's own list of open MRs for the goal, not from memory or the workbook: every MR
opened ends merged or closed.

## Watchdog

`scripts/steward_watch.py` runs every 30 minutes as a BB script automation, without calling a model. Register at
session start; the first registration creates the automation in the current project; re-register after moving the
workbook file:

```bash
python3 scripts/steward_watch.py register --workbook <absolute workbook path> [--name <short name>]
```

Registration also syncs the platform steward entry (workbook and ledger) and adds the "🎩" mark to the thread title;
the steward maintains neither. The thread title is just "<short name> steward"; the goal lives in the workbook title.
When registration output `plugin.status` is `skipped`, the platform entry is unavailable, so include the workbook
path when replying to the user; when the entry is available, don't repeat the link in replies.

The watchdog does the following; throttling and escalation rules are in the script's `--help`:

- When a steward turn fails with no retry queued, it retries on the steward's behalf, and after recovery reminds it to
  check notifications missed during the failure.
- When the steward is idle and reconciliation fails, it sends the problem lines to the steward; when the user sent a
  batch of messages and the ledger has not been updated, it nudges under the same reconciliation rules.
- When the steward's model changes (the model or reasoning level BB requested, or the model Claude Code actually
  replied with), it reminds once.
- After every context compaction it nudges the steward to re-read the rules; when compactions accumulate to a
  threshold, it asks the steward to suggest the user switch stewards.

On a `[bb-steward watchdog]` message, do what it says (reconciliation problems per "Closing reconciliation"); no reply to
it is needed. When the message asks you to tell the user (model changed, the same problem nudged twice, recovery after
a long interruption, compaction count reached threshold), state the change or problem and its impact in this turn's
reply; when the model changed, offer options: switch back to the original model, or open a new thread to take over.

## Review

Review dispatch records with `bb thread list` and `bb-dispatch --history-summary`, and watchdog records with
`scripts/steward_watch.py report` and `summary`; the watchdog log drops its older half beyond 2 MB, with no long-term
rollup.
