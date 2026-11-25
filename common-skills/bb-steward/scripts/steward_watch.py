#!/usr/bin/env python3
"""BB steward watchdog: run by a BB script automation every 30 minutes, without calling a model.

For each registered steward:
- Thread archived or deleted: drop the registration.
- Title lacks the shared "🎩" steward mark: add it; an existing mark is not repeated, only the prefix is added and
  the title goal is untouched.
- Each run incrementally reads the model BB requested, and for Claude Code stewards also the actual model in the
  session transcript; the first value is the baseline, each new deviation is reported once, a return to the
  baseline is only logged.
- The same scan counts context compactions: after a compaction the skill body is gone from context, so every new
  compaction asks the steward to re-read the rules, workbook and requirement ledger; at 8 in total (then every 4
  more) the steward is asked to tell the user to switch stewards. The count follows the thread; a successor
  thread starts from 0.
- Running, queued messages, pending interaction or background activity: skip reconciliation and retries.
- Turn failed with no retry queued: `bb thread retry` at 0/30/60/120/240/240-minute intervals, at most 6 times;
  a failure lasting 60 minutes needs the user's attention. After recovery one reminder asks the steward to check
  notifications that arrived during the failure.
- Idle (10 minutes after the turn ended): read the workbook and run closing reconciliation
  (steward_workbook.reconcile_workbook); nudge-level problems are sent to the steward. Each problem is sent at
  most twice, with at least 2 hours between nudges to the same steward; problems still open after that need the
  user's attention, and the steward is asked to tell the user in this turn's reply.
- Reconciliation also checks the requirement ledger: when the user sent 5 messages, the earliest over 3 hours ago,
  and the ledger has not been updated since, the same nudge rules apply. Local workbooks use the ledger file's
  modification time, Git-ref mode its last commit time on that branch; history logs and missing entries are skipped.

Usage:
  steward_watch.py register --workbook <path> [--ref origin/main] [--name <short name>] [--thread thr_x] [--project proj_x]
  steward_watch.py retire [--thread thr_x] --reason <reason> [--successor thr_y]
  steward_watch.py roster [--thread thr_x]
  steward_watch.py unregister [--thread thr_x]
  steward_watch.py run [--dry-run]
  steward_watch.py report [--since 60]
  steward_watch.py summary [--days 7] [--json]

Registrations and run state live in ${XDG_STATE_HOME:-~/.local/state}/bb-steward/watch.json (override with
BB_STEWARD_WATCH_STATE or --state); the event log is watch.events.jsonl in the same directory and drops its older
half beyond 2 MB. The first registration creates the script automation in the current project. Model changes,
problems nudged twice and escalated outage recoveries reach the user through the steward's reply. Registering the
same workbook from another thread is a takeover: the new registration is saved first, then moving child threads,
cancelling old retries and the handover notice are each attempted independently, and the output's ledger_gap
reports how many user messages the old steward left unrecorded. run prints nothing when there is nothing to
report, so the automation records a silent skip.
"""
import argparse
from collections import Counter, defaultdict
import contextlib
from datetime import datetime
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

try:
    import fcntl
except ImportError:  # Windows has no fcntl; fall back to unlocked reads and writes.
    fcntl = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
import steward_workbook as sw  # noqa: E402

AUTOMATION_NAME = "Steward watchdog (bb-steward)"
AUTOMATION_CRON = "25,55 * * * *"
AUTOMATION_TIMEOUT_MS = "300000"
SETTLE_MINUTES = 10
MIN_NUDGE_INTERVAL_MINUTES = 120
MAX_NUDGES_PER_PROBLEM = 2
RETRY_WAIT_MINUTES = (0, 30, 60, 120, 240, 240)
ESCALATE_OUTAGE_MINUTES = 60
EVENTS_MAX_BYTES = 2 * 1024 * 1024
MESSAGE_MAX_PROBLEMS = 8
SUMMARY_LOW_RESOLVE_SHARE = 0.5
SUMMARY_MIN_NUDGES = 3
SUMMARY_FREQUENT_OUTAGES = 3
LOG_UNREADABLE = "BB model log unreadable"
HANDOVER_COMPACTIONS = 8
HANDOVER_REPEAT_COMPACTIONS = 4
LEDGER_STALE_MESSAGES = 5
LEDGER_STALE_MINUTES = 180
USER_MESSAGES_KEPT = 50
STEWARD_MARK = "🎩"
TAG = "[bb-steward watchdog]"
HANDOVER_TAG = "[bb-steward handover]"
# Script messages are recorded as user input in BB; they are told apart by a leading tag. The prefix also covers
# the legacy "[bb-steward 看门狗]" / "[bb-steward 交接]" tags still present in older thread logs.
SCRIPT_MESSAGE_PREFIX = "[bb"


class WatchError(Exception):
    pass


class Bb:
    """Thin wrapper over the bb CLI; tests substitute a fake with the same interface."""

    def _run(self, args, stdin=None, timeout=60):
        try:
            res = subprocess.run(["bb", *args, "--json"], input=stdin, capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise WatchError(f"bb {' '.join(args[:2])} could not run: {exc}") from exc
        try:
            data = json.loads(res.stdout) if res.stdout.strip() else {}
        except ValueError:
            data = {}
        if res.returncode or (isinstance(data, dict) and data.get("ok") is False):
            error = data.get("error") if isinstance(data, dict) else None
            detail = json.dumps(error, ensure_ascii=False) if error else (res.stderr.strip() or res.stdout.strip())
            raise WatchError(f"bb {' '.join(args[:2])} failed: {detail[:300]}")
        return data

    def steward(self, command, **values):
        args = ["steward", command]
        for key, value in values.items():
            args.extend(["--" + key.replace("_", "-"), str(value)])
        return self._run(args, timeout=65)

    def threads(self, ids):
        try:
            return sw.fetch_threads(ids)
        except RuntimeError as exc:
            raise WatchError(str(exc)) from exc

    def children(self, parent, include_hidden=False):
        try:
            return sw.bb_thread_list("--parent-thread", parent, *(["--include-hidden"] if include_hidden else []))
        except RuntimeError as exc:
            raise WatchError(str(exc)) from exc

    def tell(self, thread, message):
        self._run(["thread", "tell", thread, "--message-file", "-", "--mode", "queue"], stdin=message)

    def log(self, thread, after):
        return self._run(["thread", "log", thread, "--after-seq", str(after), "--limit", "10000"])

    def reparent(self, thread, parent=None):
        self._run(["thread", "update", thread, *(["--parent-thread", parent] if parent else ["--clear-parent-thread"])])

    def set_title(self, thread, title):
        self._run(["thread", "update", thread, "--title", title])

    def cancel_retry(self, thread):
        try:
            self._run(["provider-retry", "cancel", thread])
        except WatchError as exc:
            # No queued retry is exactly the desired outcome, not a failed takeover step.
            if "no_pending_retry" not in str(exc):
                raise

    def retry(self, thread, reason):
        self._run(["thread", "retry", thread, "--reason", reason])

    def automation_show(self, automation_id, project):
        try:
            data = self._run(["automation", "show", automation_id, "--project", project])
        except WatchError:
            return None
        return data.get("automation", data) if isinstance(data, dict) else None

    def automation_create(self, project, script):
        data = self._run(["automation", "create", "--project", project, "--name", AUTOMATION_NAME,
                          "--cron", AUTOMATION_CRON, "--timezone", "UTC", "--script", script,
                          "--interpreter", "bash", "--timeout", AUTOMATION_TIMEOUT_MS,
                          "--working-directory", "automation-storage"])
        return data.get("automation", data)

    def automation_update_script(self, automation_id, project, script):
        self._run(["automation", "update", automation_id, "--project", project, "--script", script,
                   "--interpreter", "bash", "--timeout", AUTOMATION_TIMEOUT_MS])


# ---------- State and events ----------

def state_path_from(arg):
    raw = arg or os.environ.get("BB_STEWARD_WATCH_STATE")
    if raw:
        return Path(raw).expanduser()
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    return base / "bb-steward" / "watch.json"


def events_path(state_path):
    return state_path.with_name(state_path.stem + ".events.jsonl")


def empty_state():
    return {"version": 1, "automation": None, "stewards": {}}


def load_state(path):
    if not path.exists():
        return empty_state()
    try:
        data = json.loads(path.read_text())
    except ValueError as exc:
        raise WatchError(f"Watchdog state file is not JSON: {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("stewards"), dict):
        raise WatchError(f"Watchdog state file has an invalid format: {path}")
    return data


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    tmp.replace(path)


@contextlib.contextmanager
def state_lock(path):
    """Serialize registration and runs; failing to get the lock means another run is active, so this one exits."""
    if fcntl is None:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_name(path.name + ".lock"), "a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise WatchError("Another watchdog run is still in progress") from exc
        yield


def append_events(state_path, events):
    """One JSON event per line; a write failure only warns and never changes this run's result."""
    if not events:
        return
    try:
        target = events_path(state_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a") as handle:
            handle.writelines(json.dumps(e, ensure_ascii=False) + "\n" for e in events)
        if target.stat().st_size > EVENTS_MAX_BYTES:
            lines = target.read_text().splitlines(keepends=True)
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_text("".join(lines[len(lines) // 2:]))
            tmp.replace(target)
    except Exception as exc:
        print(f"warning: watchdog event write failed (ignored): {exc}", file=sys.stderr)


def read_events(state_path):
    target = events_path(state_path)
    if not target.exists():
        return []
    events = []
    for line in target.read_text().splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    return events


def event(now, thread, what, **fields):
    return {"ts": round(now, 3), "thread": thread, "event": what, **fields}


# ---------- Workbook ----------

def git(*args, timeout=60):
    return subprocess.run(["git", *args], capture_output=True, text=True, timeout=timeout)


def git_toplevel(path):
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    res = git("-C", str(probe if probe.is_dir() else probe.parent), "rev-parse", "--show-toplevel")
    if res.returncode:
        raise WatchError(f"{path} is not inside a git repository: {res.stderr.strip()[:200]}")
    return Path(res.stdout.strip())


def read_source(entry):
    """Return (workbook text, pinned SHA); the SHA is None for a local workbook."""
    if not entry.get("ref"):
        return Path(entry["workbook"]).read_text(), None
    try:
        sha = sw.source.pin(entry['repo'], entry['ref'])
        return sw.source.read(entry['repo'], sha, entry['path']), sha
    except sw.source.SourceError as exc:
        raise WatchError(str(exc)) from exc


def read_workbook(entry):
    return read_source(entry)[0]


def ledger_updated_at(entry, text, sha):
    """Timestamp of the ledger's last update; None without a comparable standard ledger (no entry, history log,
    unreadable)."""
    try:
        target, kind = sw.source.ledger_entry(text)
        if kind != "standard":
            return None
        if sha:
            path = sw.source.resolve_link(entry["path"], target, True)
            stamp = sw.source.git(entry["repo"], "log", "-1", "--format=%ct", sha, "--", path).strip()
            return float(stamp) if stamp else None
        return Path(sw.source.resolve_link(entry["workbook"], target)).stat().st_mtime
    except (sw.source.SourceError, OSError, ValueError):
        return None


def ledger_problem(entry, text, sha, now):
    """The user sent a batch of messages and the ledger did not move: return a nudge-level problem, else None.
    Uses timestamps only, never message bodies."""
    stamps = (entry.get("model_observation") or {}).get("user_messages") or []
    if len(stamps) < LEDGER_STALE_MESSAGES:
        return None
    updated = ledger_updated_at(entry, text, sha)
    if updated is None:
        return None
    waiting = [t for t in stamps if t > updated]
    if len(waiting) < LEDGER_STALE_MESSAGES or now - waiting[0] < LEDGER_STALE_MINUTES * 60:
        return None
    more = "at least " if len(stamps) >= USER_MESSAGES_KEPT and len(waiting) == len(stamps) else ""
    return {"kind": "ledger_stale", "severity": "nudge", "line": None, "label": "Requirement ledger",
            "detail": f"not updated since {hhmm(updated)}; the user has since sent {more}{len(waiting)} messages "
                      f"(earliest {hhmm(waiting[0])}). Per bb-steward \"Requirement ledger\", record each request "
                      "from that period and commit; sync key decisions and user to-dos into the workbook"}


# ---------- Model observation (read-only sources; the caller keeps cursors and baselines) ----------

def claude_model(provider_thread_id):
    """Read the tail backwards in chunks and stop at the last real assistant entry, avoiding a full read."""
    if not provider_thread_id or Path(provider_thread_id).name != provider_thread_id:
        raise WatchError("No usable Claude providerThreadId")
    root = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    paths = list((root / "projects").glob(f"*/{provider_thread_id}.jsonl"))
    if not paths:
        raise WatchError("Claude session file not found")
    for path in sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True):
        with path.open("rb") as handle:
            handle.seek(0, 2)
            offset, tail = handle.tell(), b""
            while offset:
                size = min(offset, 65536)
                offset -= size
                handle.seek(offset)
                parts = (handle.read(size) + tail).split(b"\n")
                tail = parts.pop(0) if offset else b""
                for line in reversed(parts):
                    try:
                        row = json.loads(line)
                    except (ValueError, UnicodeDecodeError):
                        continue
                    msg = row.get("message") or {}
                    model = msg.get("model")
                    if row.get("type") == "assistant" and model and model != "<synthetic>":
                        return model
    raise WatchError("Claude session has no real assistant model")


def read_models(bb, tid, previous, claude=True):
    """Incremental scan in large pages; returns minimal facts only and never stores event bodies.
    claude=False skips the Claude Code transcript.

    The same scan counts context compactions and records user-message timestamps (only the latest
    USER_MESSAGES_KEPT). Older registrations lacking these rescan from the start once to recover the totals since
    thread creation; if the log becomes unreadable mid-rescan the whole pass is discarded and retried next run, so
    historical compactions are not mistaken for new ones.
    """
    observed = dict(previous)
    rescan = "compactions" not in observed
    if rescan:
        observed.update(seq=0, compactions=0, user_messages=[])
    after = observed.get("seq", 0)
    warnings = []
    while True:
        try:
            rows = bb.log(tid, after)
        except (OSError, WatchError) as exc:
            warnings.append(f"{LOG_UNREADABLE}: {exc}")
            if rescan:
                observed = dict(previous)
                after = observed.get("seq", 0)
            break
        if not isinstance(rows, list):
            raise WatchError("thread log returned a non-array")
        for row in rows:
            data = row.get("data") or {}
            if row.get("type") == "client/turn/requested":
                execution = data.get("execution") or {}
                if execution.get("model"):
                    observed["requested"] = {"model": execution["model"], "reasoningLevel": execution.get("reasoningLevel")}
                if is_user_message(data) and row.get("createdAt"):
                    observed["user_messages"] = (observed["user_messages"] + [row["createdAt"] / 1000])[-USER_MESSAGES_KEPT:]
            elif row.get("type") == "thread/compacted":
                observed["compactions"] += 1
            elif row.get("type") == "thread/identity" and data.get("providerThreadId"):
                observed["providerThreadId"] = data["providerThreadId"]
        if not rows:
            break
        cursor = max(row["seq"] for row in rows)
        if cursor <= after:
            raise WatchError("thread log cursor did not advance")
        after = cursor
        if len(rows) < 10000:
            break
    observed["seq"] = after
    values = {}
    if observed.get("requested"):
        values["requested"] = observed["requested"]
    else:
        warnings.append("BB requested model unreadable")
    if claude:
        try:
            values["actual"] = claude_model(observed.get("providerThreadId"))
        except (OSError, WatchError) as exc:
            warnings.append(str(exc))
    return observed, values, warnings


def is_user_message(data):
    """A message the user typed. Script messages (watchdog, handover notice) are also recorded as user in BB and
    are told apart only by their leading `[bb` tag."""
    if data.get("initiator") != "user":
        return False
    text = next((i.get("text") or "" for i in data.get("input") or [] if i.get("type") == "text"), "")
    return not text.lstrip().startswith(SCRIPT_MESSAGE_PREFIX)


MODEL_SOURCES = {"requested": "BB requested model", "actual": "Claude Code actual model"}


def model_text(value):
    if isinstance(value, dict):
        level = value.get("reasoningLevel")
        return f"{value.get('model')} ({level})" if level else str(value.get("model"))
    return str(value)


# ---------- Checking one steward ----------

def problem_key(problem):
    return f"{problem['kind']}|{problem['label']}"


def hhmm(ts):
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")


def nudge_message(entry, sent, others):
    """sent are the problems counted as nudged this time; others is only a count (not yet shown or not urgent)."""
    where = entry["workbook"] + (f" @ {entry['ref']}" if entry.get("ref") else "")
    lines = [f"{TAG} Workbook reconciliation found {len(sent)} items to handle ({where}):"]
    for p in sent:
        loc = f"line {p['line']} " if p.get("line") else ""
        lines.append(f"- {loc}\"{p['label']}\": {p['detail']}")
    if others:
        lines.append(f"- {others} more; run the reconcile command to see them")
    lines.append(
        "Handle each per bb-steward \"Closing reconciliation\": dispatch what can move now; for lines that really "
        f"wait, write the state accurately and commit the workbook. Use only the four states: {sw.STATE_HINT}; a "
        "waiting-on-user line needs a to-do whose Blocks cell names it; a user to-do reason starts with one of "
        f"{', '.join(sw.TODO_CATEGORIES)}. The rules are in the \"Closing reconciliation\" section of bb-steward's "
        "SKILL.md; re-read it if you have not. Reconcile command: steward_workbook.py --mode reconcile --live "
        "--file <workbook>. No reply to the watchdog needed."
    )
    return "\n".join(lines)


def recovery_message(outage):
    retried = f"the watchdog retried {outage['retries']} times, " if outage.get("retries") else ""
    return (f"{TAG} Your turns kept failing from {hhmm(outage['since'])}; {retried}and you have now recovered. "
            "Child-thread notifications and messages that arrived meanwhile may be unhandled: check with "
            "`bb thread log --self`, then continue per bb-steward \"Closing reconciliation\". "
            + ("Tell the user in this turn's reply that the outage is over and what it affected."
               if outage.get("escalated") else "No reply to the watchdog needed."))


class Checker:
    def __init__(self, state, state_path, bb, now, dry_run=False):
        self.state = state
        self.state_path = state_path
        self.bb = bb
        self.now = now
        self.dry_run = dry_run
        self.events = []

    def persist(self):
        """Persist before side effects (tell/retry): even if the process dies after sending, the next run will not
        nudge again."""
        if not self.dry_run:
            save_state(self.state_path, self.state)

    def check(self, tid, entry, info):
        name = entry.get("name") or tid
        if info is None or info["archived"]:
            reason = "thread deleted" if info is None else "thread archived"
            self.events.append(event(self.now, tid, "unregister", reason=reason))
            return {"result": "unregistered", "remove": True, "report": f"{name}: {reason}, registration removed"}
        self.mark_title(tid, info)
        self.check_models(tid, entry, info)
        busy = (info["status"] not in sw.SETTLED_STATUSES or info["queued"]
                or info["interaction"] or info["background"])
        if busy:
            self.events.append(event(self.now, tid, "check", result="busy"))
            return {"result": "busy"}
        if info["status"] == "error":
            return self.handle_failure(tid, entry, info, name)
        if entry.get("outage"):
            return self.handle_recovery(tid, entry, name)
        if self.now - info["updated_at"] < SETTLE_MINUTES * 60:
            self.events.append(event(self.now, tid, "check", result="settling"))
            return {"result": "settling"}
        return self.reconcile(tid, entry, name)

    def mark_title(self, tid, info):
        """Every run restores the steward mark, whether the title was changed or registration missed it."""
        if self.dry_run:
            return
        marked = marked_title(info.get("title"))
        if marked is None:
            return
        try:
            self.bb.set_title(tid, marked)
            info["title"] = marked
            self.events.append(event(self.now, tid, "title_marked", title=marked))
        except Exception as exc:
            self.events.append(event(self.now, tid, "warning", source="title", detail=str(exc)[:200]))

    def check_models(self, tid, entry, info):
        # Only Claude Code transcripts reveal the actual model; other providers use the model BB requested.
        claude = info.get("provider") in (None, "claude-code")
        try:
            observed, values, warnings = read_models(self.bb, tid, entry.get("model_observation", {}), claude)
        except Exception as exc:
            self.events.append(event(self.now, tid, "warning", source="models", detail=str(exc)[:200]))
            return
        entry["model_observation"] = observed
        for detail in warnings:
            self.events.append(event(self.now, tid, "warning", source="models", detail=detail[:200]))
        if "compactions" in observed:
            self.check_compactions(tid, entry, observed["compactions"])
        for source, value in values.items():
            tracked = entry.setdefault("models", {})
            if source not in tracked:
                tracked[source] = {"baseline": value, "current": value, "notified": []}
                self.events.append(event(self.now, tid, "model_baseline", source=source, value=value))
                continue
            record = tracked[source]
            if record["current"] == value:
                continue
            before = record["current"]
            record["current"] = value
            returned = value == record["baseline"]
            notify = not returned and value not in record["notified"]
            if notify:
                record["notified"].append(value)
            self.persist()
            change = event(self.now, tid, "model_change", source=source, before=before, value=value,
                           returned=returned, notified=notify)
            if notify and not self.dry_run:
                try:
                    self.bb.tell(tid, f"{TAG} {MODEL_SOURCES.get(source, source)} changed from {model_text(before)} to "
                                 f"{model_text(value)} (at registration: {model_text(record['baseline'])}). Tell the "
                                 "user in this turn's reply about the change and its impact, with options: switch "
                                 "back to the original model, or open a new thread to take over "
                                 "(bb-steward \"Takeover\").")
                    change["ok"] = True
                except Exception as exc:
                    change.update(ok=False, detail=str(exc)[:200])
            self.events.append(change)

    def check_compactions(self, tid, entry, count):
        record = entry.get("compaction")
        if record is None:
            # First observation only records a baseline: no re-read reminder for past compactions, but a reached
            # threshold still triggers the switch reminder.
            record = entry["compaction"] = {"seen": count, "handover_notified": 0}
            fresh = 0
        else:
            fresh = count - record["seen"]
            record["seen"] = count
        last = record["handover_notified"]
        handover_due = count >= HANDOVER_COMPACTIONS and (not last or count - last >= HANDOVER_REPEAT_COMPACTIONS)
        if fresh <= 0 and not handover_due:
            return
        parts = []
        if fresh > 0:
            parts.append(f"Your context was just compacted (compaction {count} in total). The skill body is no longer "
                         "in context and the summary keeps only a paraphrase: before continuing, re-read bb-steward's "
                         "SKILL.md and the \"Judgment and invocation\" section of bb-model-routing, then read the "
                         "workbook and requirement ledger, and record user requests from around the compaction "
                         "not yet entered. ")
        if handover_due:
            record["handover_notified"] = count
            parts.append(f"This session has been compacted {count} times; the rules survive only as layered "
                         "paraphrase and more gets lost each time. Tell the user in this turn's reply: suggest opening a "
                         "same-model thread to take over (bb-steward \"Takeover\"), and first bring the requirement "
                         "ledger and workbook up to date, since they are all a new steward can take over from. ")
        self.persist()
        note = event(self.now, tid, "compaction", count=count, new=max(fresh, 0), handover=handover_due)
        if not self.dry_run:
            try:
                self.bb.tell(tid, f"{TAG} " + "".join(parts) + ("" if handover_due else "No reply to the watchdog needed."))
                note["ok"] = True
            except Exception as exc:
                note.update(ok=False, detail=str(exc)[:200])
        self.events.append(note)

    def handle_failure(self, tid, entry, info, name):
        outage = entry.get("outage")
        if not outage:
            outage = {"since": info["updated_at"] or self.now, "retries": 0, "last_retry": None, "escalated": False}
            self.events.append(event(self.now, tid, "outage"))
        entry["outage"] = outage
        notes = []
        n = outage["retries"]
        due = n < len(RETRY_WAIT_MINUTES) and (
            outage["last_retry"] is None or self.now - outage["last_retry"] >= RETRY_WAIT_MINUTES[n] * 60)
        minutes = (self.now - outage["since"]) / 60
        escalate = minutes >= ESCALATE_OUTAGE_MINUTES and not outage["escalated"]
        if escalate:
            outage["escalated"] = True
            self.events.append(event(self.now, tid, "escalate", reason="outage", minutes=round(minutes)))
            notes.append("needs the user's attention")
        if due:
            outage["retries"] = n + 1
            outage["last_retry"] = self.now
            self.persist()
            ok, err = True, ""
            if not self.dry_run:
                try:
                    self.bb.retry(tid, f"{TAG} automatic retry after a failed steward turn (attempt {n + 1})")
                except WatchError as exc:
                    ok, err = False, str(exc)
            self.events.append(event(self.now, tid, "retry", attempt=n + 1, ok=ok))
            notes.insert(0, f"retried (attempt {n + 1})" + ("" if ok else f" (retry failed: {err[:120]})"))
        if not notes:
            self.events.append(event(self.now, tid, "check", result="failed"))
            return {"result": "failed"}
        return {"result": "failed", "report": f"{name}: turn failing for {minutes:.0f} min, " + ", ".join(notes)}

    def handle_recovery(self, tid, entry, name):
        outage = entry.pop("outage")
        entry["last_nudge"] = self.now
        self.persist()
        ok = True
        if not self.dry_run:
            try:
                self.bb.tell(tid, recovery_message(outage))
            except WatchError:
                ok = False
        minutes = round((self.now - outage["since"]) / 60)
        self.events.append(event(self.now, tid, "recovered", minutes=minutes, retries=outage["retries"], ok=ok))
        return {"result": "recovered",
                "report": f"{name}: recovered from failed turns (about {minutes} min), "
                          + ("reminded to check notifications from the outage" if ok else "reminder failed to send")}

    def reconcile(self, tid, entry, name):
        try:
            text, sha = read_source(entry)
        except Exception as exc:
            problems = [{"kind": "workbook_unreadable", "severity": "nudge", "line": None, "label": "Workbook",
                         "detail": f"cannot read the workbook; re-register if its path changed: {str(exc)[:160]}"}]
        else:
            ids = sw.reconcile_workbook(text, now=datetime.fromtimestamp(self.now))["referenced_threads"]
            threads = self.bb.threads(ids) if ids else {}
            unlisted = 0
            if entry.get("ref"):
                # A remote workbook may not have the new thread IDs yet: while the steward has other running
                # children, "thread stopped" is only minor.
                grace = sw.DEFAULT_GRACE_MINUTES * 60
                unlisted = sum(1 for child in self.bb.children(tid)
                               if child["id"] not in threads
                               and sw.thread_state(child, self.now, grace) in ("alive", "recent"))
            problems = sw.reconcile_workbook(text, now=datetime.fromtimestamp(self.now), threads=threads,
                                             unlisted_alive=unlisted)["problems"]
            stale = ledger_problem(entry, text, sha, self.now)
            if stale:
                problems.append(stale)

        urgent = {problem_key(p): p for p in problems if p["severity"] == "nudge"}
        tracked = entry.setdefault("problems", {})
        pending = entry.pop("pending_nudge", None)
        if pending:
            resolved = sum(1 for k in pending["keys"] if k not in urgent)
            self.events.append(event(self.now, tid, "nudge_outcome", resolved=resolved,
                                     persisted=len(pending["keys"]) - resolved))
        for key in list(tracked):
            if key not in urgent:
                del tracked[key]
        if not urgent:
            self.events.append(event(self.now, tid, "check", result="ok", minor=len(problems)))
            return {"result": "ok"}

        notes = []
        for key, problem in urgent.items():
            record = tracked.setdefault(key, {"count": 0, "first_seen": self.now})
            if record["count"] >= MAX_NUDGES_PER_PROBLEM and not record.get("escalated"):
                record["escalated"] = True
                self.events.append(event(self.now, tid, "escalate", reason="problem",
                                         kind=problem["kind"], label=problem["label"]))
                notes.append(f"\"{problem['label']}\" nudged {record['count']} times and still open, needs the user's attention")
        if notes:
            self.persist()
            if not self.dry_run:
                try:
                    self.bb.tell(tid, f"{TAG} " + "; ".join(notes) + ". Tell the user in this turn's reply about the problem and its impact.")
                except WatchError as exc:
                    self.events.append(event(self.now, tid, "warning", source="escalation", detail=str(exc)[:200]))
        # Send only problems with nudges left; the sent, counted and pending sets are the same.
        sent_keys = [k for k in urgent if tracked[k]["count"] < MAX_NUDGES_PER_PROBLEM][:MESSAGE_MAX_PROBLEMS]
        last = entry.get("last_nudge")
        if sent_keys and (last is None or self.now - last >= MIN_NUDGE_INTERVAL_MINUTES * 60):
            sent = [urgent[k] for k in sent_keys]
            for key in sent_keys:
                tracked[key]["count"] += 1
                tracked[key]["last_nudged"] = self.now
            entry["last_nudge"] = self.now
            entry["pending_nudge"] = {"ts": self.now, "keys": sent_keys}
            full = [urgent[k] for k in sent_keys if tracked[k]["count"] >= MAX_NUDGES_PER_PROBLEM]
            for problem in full:
                tracked[problem_key(problem)]["escalated"] = True
                self.events.append(event(self.now, tid, "escalate", reason="problem", kind=problem["kind"], label=problem["label"]))
            self.persist()
            ok = True
            if not self.dry_run:
                try:
                    message = nudge_message(entry, sent, len(problems) - len(sent))
                    if full:
                        message += ("\nThese problems have now been nudged twice: " + ", ".join(p["label"] for p in full)
                                    + ". Tell the user in this turn's reply about the problem and its impact.")
                    self.bb.tell(tid, message)
                except WatchError:
                    ok = False
            labels = [f"{p['label']} {p['detail'][:20]}" for p in sent]
            self.events.append(event(self.now, tid, "nudge", ok=ok, count=len(sent),
                                     problems=[{"kind": p["kind"], "label": p["label"]} for p in sent]))
            notes.insert(0, f"nudged ({len(sent)} items: {'; '.join(labels[:3])}{'…' if len(labels) > 3 else ''})"
                         + ("" if ok else ", but the message failed to send"))
            return {"result": "nudged", "report": f"{name}: " + ", ".join(notes)}
        self.events.append(event(self.now, tid, "check", result="problems", count=len(urgent)))
        return {"result": "problems", "report": f"{name}: " + ", ".join(notes) if notes else None}


def run(state, state_path, bb, now=None, dry_run=False):
    now = now if now is not None else time.time()
    if not dry_run:
        retry_plugin_unregistrations(state, bb, state_path)
    checker = Checker(state, state_path, bb, now, dry_run)
    stewards = state["stewards"]
    results = {}
    if stewards:
        infos = bb.threads(list(stewards))
        for tid in list(stewards):
            entry = stewards[tid]
            try:
                outcome = checker.check(tid, entry, infos.get(tid))
            except Exception as exc:
                checker.events.append(event(now, tid, "error", detail=str(exc)[:300]))
                outcome = {"result": "error", "report": f"{entry.get('name') or tid}: check failed: {str(exc)[:200]}"}
            if outcome.get("remove"):
                remember_retirement(state, tid, entry, "thread archived or deleted", now=now)
                del stewards[tid]
                if not dry_run:
                    outcome["plugin"] = unregister_plugin(state, bb, tid, state_path)
            results[tid] = outcome
    if not dry_run:
        save_state(state_path, state)
        append_events(state_path, checker.events)
    return results, checker.events


# ---------- Registration ----------

def ensure_automation(state, bb, project, script_path, state_path):
    # Hard-code the state file path: the automation's HOME/XDG variables may differ from registration time.
    script = f"exec python3 {shlex.quote(str(script_path))} --state {shlex.quote(str(state_path))} run"
    auto = state.get("automation")
    if auto:
        shown = bb.automation_show(auto["id"], auto["project"])
        if shown is not None:
            current = (shown.get("execution") or {}).get("script")
            if current != script:
                bb.automation_update_script(auto["id"], auto["project"], script)
                auto["script"] = script
                return {"id": auto["id"], "project": auto["project"], "status": "updated"}
            return {"id": auto["id"], "project": auto["project"], "status": "exists"}
    if not project:
        return {"status": "skipped", "reason": "not in a BB thread and no --project given; automation not created"}
    created = bb.automation_create(project, script)
    state["automation"] = {"id": created["id"], "project": project, "script": script}
    return {"id": created["id"], "project": project, "status": "created"}


def main_worktree(top):
    """Worktrees get deleted, so remote-branch mode records the main worktree: the parent of git-common-dir."""
    res = git("-C", str(top), "rev-parse", "--path-format=absolute", "--git-common-dir")
    common = Path(res.stdout.strip()) if res.returncode == 0 else None
    return common.parent if common is not None and common.name == ".git" else top


def workbook_identity(workbook):
    path = Path(workbook).expanduser().resolve()
    try:
        top = git_toplevel(path).resolve()
        return str(main_worktree(top).resolve()), path.relative_to(top).as_posix()
    except WatchError:
        return None, str(path)


def entry_identity(entry):
    if entry.get("repo") and entry.get("path"):
        return str(main_worktree(Path(entry["repo"])).resolve()), entry["path"]
    return workbook_identity(entry["workbook"])


def ledger_gap(bb, old, old_entry, entry):
    """User messages the old steward left unrecorded: messages the old thread received after the ledger's last
    update. None when there is no gap or nothing to compare."""
    observed, _, warnings = read_models(bb, old, old_entry.get("model_observation", {}), claude=False)
    unreadable = [w for w in warnings if w.startswith(LOG_UNREADABLE)]
    if unreadable:
        raise WatchError(f"Old thread log unreadable; cannot judge the ledger gap: {unreadable[0]}")
    text, sha = read_source(entry)
    updated = ledger_updated_at(entry, text, sha)
    stamps = observed["user_messages"]
    waiting = [t for t in stamps if updated is not None and t > updated]
    if not waiting:
        return None
    return {"since": hhmm(updated), "messages": len(waiting),
            "capped": len(stamps) >= USER_MESSAGES_KEPT and len(waiting) == len(stamps)}


def handover(bb, old, new, entry, now, old_entry=None):
    """Each external step fails independently; register has already saved the registration, nothing rolls back."""
    results = []

    def attempt(step, call):
        try:
            value = call()
            results.append({"step": step, "ok": True})
            return value
        except Exception as exc:
            results.append({"step": step, "ok": False, "detail": str(exc)[:200]})
            return None

    infos = attempt("threads", lambda: bb.threads([old, new])) or {}
    if (infos.get(new) or {}).get("parent") == old:
        attempt("clear_parent", lambda: bb.reparent(new))
    referenced = set(attempt("workbook", lambda: sw.running_thread_ids(read_workbook(entry))) or [])
    children = attempt("children", lambda: bb.children(old, include_hidden=True)) or []
    for child in children:
        if child["id"] != new and not child["archived"] and (
                child["id"] in referenced or sw.thread_state(child, now, sw.DEFAULT_GRACE_MINUTES * 60) in ("alive", "recent")):
            attempt("reparent:" + child["id"], lambda child=child: bb.reparent(child["id"], new))
    attempt("cancel_retry", lambda: bb.cancel_retry(old))
    if old in infos and not infos[old]["archived"]:
        attempt("notify", lambda: bb.tell(old, f"{HANDOVER_TAG} @thread:{new} has taken over. Stop dispatching and "
                                          "editing the workbook; point the user to the new thread if they come "
                                          "to you. No reply needed."))
    gap = attempt("ledger_gap", lambda: ledger_gap(bb, old, old_entry or {}, entry))
    return {"old": old, "new": new, "steps": results, **({"ledger_gap": gap} if gap else {})}


def marked_title(title):
    """Prefix the title with the shared steward mark; None when already marked or the title is empty."""
    text = (title or "").strip()
    if not text:
        return None
    if text.startswith(STEWARD_MARK):
        return None
    return f"{STEWARD_MARK} {text}"


def mark_thread_title(bb, thread, title=None):
    """Ensure the thread title carries the steward mark; failures are reported, never block registration or the
    watchdog."""
    try:
        if title is None:
            info = (bb.threads([thread]) or {}).get(thread)
            if info is None:
                return {"status": "skipped", "reason": "thread not found"}
            title = info.get("title")
        marked = marked_title(title)
        if marked is None:
            return {"status": "unchanged"}
        bb.set_title(thread, marked)
        return {"status": "marked", "title": marked}
    except Exception as exc:
        return {"status": "skipped", "reason": str(exc)[:200]}


def sync_plugin(bb, command, thread, entry=None):
    try:
        values = {"thread": thread}
        if command == "register":
            git_source = bool(entry.get('ref'))
            file = entry['path'] if git_source else entry['workbook']
            target, kind = sw.source.ledger_entry(read_workbook(entry))
            ledger = sw.source.resolve_link(file, target, git_source)
            values.update(topic=entry['name'], workbook=file, ledger=ledger,
                          checker=str(Path(sw.__file__).resolve()), ledger_kind=kind)
            if git_source:
                values.update(repo=entry['repo'], ref=entry['ref'])
        bb.steward(command, **values)
        return {"status": "registered" if command == "register" else "unregistered"}
    except (sw.source.SourceError, WatchError, OSError, ValueError) as exc:
        return {"status": "skipped", "reason": str(exc)}
    except Exception:
        return {"status": "skipped", "reason": "steward plugin not installed or not ready; the watchdog keeps running"}


def unregister_plugin(state, bb, thread, state_path):
    pending = list(dict.fromkeys(state.get("pending_plugin_unregistrations", [])))
    if thread not in pending:
        pending.append(thread)
    state["pending_plugin_unregistrations"] = pending
    save_state(state_path, state)
    result = sync_plugin(bb, "unregister", thread)
    if result["status"] == "unregistered":
        pending.remove(thread)
        state["pending_plugin_unregistrations"] = pending
        save_state(state_path, state)
    return result


def retry_plugin_unregistrations(state, bb, state_path):
    for thread in list(state.get("pending_plugin_unregistrations", []))[:20]:
        active = state["stewards"].get(thread)
        if active:
            state["pending_plugin_unregistrations"].remove(thread)
            save_state(state_path, state)
        else:
            result = unregister_plugin(state, bb, thread, state_path)
            if result["status"] == "skipped":
                pending = state["pending_plugin_unregistrations"]
                pending.remove(thread)
                pending.append(thread)
                save_state(state_path, state)


def remember_retirement(state, thread, entry, reason, successor=None, now=None):
    state.setdefault("retired", {})[thread] = {
        "name": entry.get("name", thread), "workbook": entry.get("workbook"),
        "reason": reason, "successor": successor,
        "retired_at": round(time.time() if now is None else now, 3),
    }


def retire(state, bb, thread, state_path, reason="watchdog released manually", successor=None):
    if not thread:
        raise WatchError("Missing --thread and not in a BB thread (no BB_THREAD_ID)")
    if successor and (successor == thread or successor not in state["stewards"]):
        raise WatchError("The successor must be another registered serving steward")
    removed = state["stewards"].pop(thread, None)
    if removed or thread not in state.get("retired", {}):
        remember_retirement(state, thread, removed or {}, reason, successor)
    # Save the retirement first so a failed plugin sync cannot make the next run keep nudging.
    save_state(state_path, state)
    plugin = unregister_plugin(state, bb, thread, state_path)
    try:
        bb.cancel_retry(thread)
        retry = {"status": "cancelled"}
    except Exception as exc:
        retry = {"status": "skipped", "reason": str(exc)[:200]}
    if removed:
        append_events(state_path, [event(time.time(), thread, "unregister", reason=reason, successor=successor)])
    return {"thread": thread, "removed": bool(removed), "plugin": plugin, "retry": retry,
            **state["retired"][thread]}


def roster(state, bb, thread=None):
    """Registration and retirement facts on this host; run state comes live from BB, and idle never means retired."""
    active = state["stewards"]
    retired = state.get("retired", {})
    ids = [thread] if thread else list(dict.fromkeys([*active, *retired]))
    infos = bb.threads([tid for tid in ids if tid in active]) if any(tid in active for tid in ids) else {}
    rows = []
    for tid in ids:
        if tid in active:
            info = infos.get(tid)
            available = info is not None and not info["archived"]
            rows.append({"thread": tid, "name": active[tid].get("name", tid),
                         "workbook": active[tid].get("workbook"),
                         "lifecycle": "serving" if available else "unavailable",
                         "runtime": info["status"] if info else "missing"})
        elif tid in retired:
            rows.append({"thread": tid, "lifecycle": "retired", **retired[tid]})
        else:
            rows.append({"thread": tid, "lifecycle": "unknown"})
    return {"scope": "local-host", "stewards": rows}


def register(state, bb, thread, workbook, ref=None, name=None, project=None, script_path=None,
             state_path=None, manage_automation=True, now=None):
    if not thread:
        raise WatchError("Missing --thread and not in a BB thread (no BB_THREAD_ID)")
    now = time.time() if now is None else now
    workbook = Path(workbook).expanduser().resolve()
    identity = workbook_identity(workbook)
    ref = ref if ref is not None else state["stewards"].get(thread, {}).get("ref")
    olds = [(tid, e) for tid, e in state["stewards"].items()
            if tid != thread and entry_identity(e) == identity and e.get("ref") == ref]
    previous = state["stewards"].get(thread, {})
    inherited = olds[0][1] if olds else previous
    ref = ref if ref is not None else inherited.get("ref")
    entry = {"workbook": str(workbook), "registered_at": round(now, 3)}
    if identity[0]:
        entry.update(repo=identity[0], path=identity[1])
    if ref:
        if not identity[0]:
            raise WatchError("--ref needs a Git repository")
        entry["ref"] = ref
        if not olds:
            read_workbook(entry)
    elif not olds and not workbook.is_file():
        raise WatchError(f"Workbook not found: {workbook}; pass --ref when the remote branch is the source of truth")
    entry["name"] = name if name is not None else inherited.get("name") or (Path(identity[0]).name if identity[0] else workbook.stem)
    runtime = {k: previous[k] for k in ("problems", "last_nudge", "pending_nudge", "outage", "models", "model_observation", "compaction") if k in previous}
    state.get("retired", {}).pop(thread, None)
    state["stewards"][thread] = {**entry, **runtime}
    for old, old_entry in olds:
        remember_retirement(state, old, old_entry, "taken over", thread, now)
        del state["stewards"][old]
    path = state_path or state_path_from(None)
    handovers = []
    if olds:
        save_state(path, state)
        for old, old_entry in olds:
            result = handover(bb, old, thread, entry, now, old_entry)
            handovers.append(result)
            append_events(path, [event(now, thread, "handover", **result)])
    if not manage_automation:
        automation = {"status": "skipped", "reason": "--no-automation"}
    else:
        automation = ensure_automation(state, bb, project, script_path or Path(__file__).resolve(), path)
    plugin_result = sync_plugin(bb, "register", thread, entry)
    if thread in state.get("pending_plugin_unregistrations", []):
        state["pending_plugin_unregistrations"].remove(thread)
    title_result = mark_thread_title(bb, thread)
    return {"thread": thread, **entry, "automation": automation, "handovers": handovers,
            "plugin": plugin_result, "title": title_result}


# ---------- Reports and review ----------

RESULT_TEXT = {
    "busy": "steward running or has queued messages, skipped",
    "settling": "steward just finished a turn, check next run",
    "ok": "reconciliation passed",
    "problems": "reconciliation has problems, not yet time to nudge again",
    "failed": "turn failed",
    "nudged": "nudged",
    "recovered": "recovered from failure",
}


def report(state, events, now, since_minutes):
    start = now - since_minutes * 60
    window = [e for e in events if e.get("ts", 0) >= start]
    lines = [f"Watchdog log ({hhmm(start)} to {hhmm(now)}, {sum(1 for e in window if e['event'] == 'run')} runs)"]
    attention = []
    for tid, entry in state["stewards"].items():
        name = entry.get("name") or tid
        evs = [e for e in window if e.get("thread") == tid]
        lines.append(f"- {name} ({tid}, workbook {entry['workbook']}" + (f" @ {entry['ref']}" if entry.get("ref") else "") + ")")
        status = [e for e in evs if e["event"] in ("check", "nudge", "retry", "recovered", "error")]
        if status:
            last = status[-1]
            kind = last.get("result") if last["event"] == "check" else {"nudge": "nudged", "retry": "failed"}.get(last["event"], last["event"])
            text = RESULT_TEXT.get(kind or "") or f"check failed: {last.get('detail', '')}"
            lines.append(f"  last check {hhmm(last['ts'])}: {text}")
        else:
            lines.append("  no checks in this period")
        for e in evs:
            if e["event"] == "nudge":
                labels = ", ".join(f"{p['label']} ({p['kind']})" for p in e.get("problems", [])[:4])
                lines.append(f"  {hhmm(e['ts'])} nudged {e.get('count', 0)} items: {labels}" + ("" if e.get("ok", True) else ", send failed"))
            elif e["event"] == "nudge_outcome":
                lines.append(f"  {hhmm(e['ts'])} after the last nudge: {e['resolved']} resolved, {e['persisted']} persist")
            elif e["event"] == "retry":
                lines.append(f"  {hhmm(e['ts'])} turn failed, retry attempt {e['attempt']}" + ("" if e.get("ok") else " (retry command failed)"))
            elif e["event"] == "handover":
                moved = sum(1 for s in e["steps"] if s["step"].startswith("reparent:") and s["ok"])
                failed = [s["step"] for s in e["steps"] if not s["ok"]]
                lines.append(f"  {hhmm(e['ts'])} takeover {e['old']} → {e['new']}: moved {moved} child threads"
                             + (f", failed steps: {', '.join(failed)}" if failed else "")
                             + (f", ledger missing {e['ledger_gap']['messages']} user messages since {e['ledger_gap']['since']}"
                                if e.get("ledger_gap") else ""))
            elif e["event"] == "model_change":
                lines.append(f"  {hhmm(e['ts'])} model change, {MODEL_SOURCES.get(e['source'], e['source'])}: "
                             f"{model_text(e['before'])} → {model_text(e['value'])}"
                             + (" (back to baseline)" if e.get("returned") else "")
                             + (" (reminder failed to send)" if e.get("ok") is False else ""))
            elif e["event"] == "recovered":
                lines.append(f"  {hhmm(e['ts'])} recovered from failure (about {e.get('minutes', 0)} min)")
            elif e["event"] == "compaction":
                lines.append(f"  {hhmm(e['ts'])} context compacted {e['count']} times in total"
                             + (", asked to re-read the rules" if e.get("new") else "")
                             + (", reminded to switch stewards" if e.get("handover") else "")
                             + (" (reminder failed to send)" if e.get("ok") is False else ""))
        outage = entry.get("outage")
        if outage and outage.get("escalated"):
            attention.append(f"{name}: turns failing for {(now - outage['since']) / 60:.0f} min, watchdog retried {outage['retries']} times")
        compactions = (entry.get("compaction") or {}).get("seen", 0)
        if compactions >= HANDOVER_COMPACTIONS:
            attention.append(f"{name}: context compacted {compactions} times, suggest a new thread take over")
        for key, record in (entry.get("problems") or {}).items():
            if record.get("escalated"):
                kind, _, label = key.partition("|")
                attention.append(f"{name}: \"{label}\" ({kind}) nudged {record['count']} times and still open")
    for e in window:
        if e["event"] == "unregister":
            lines.append(f"- {e['thread']}: {e.get('reason')}, registration removed")
    lines.append("Needs the user's attention: " + ("none" if not attention else ""))
    lines += [f"  - {a}" for a in attention]
    return "\n".join(lines)


COUNTED_EVENTS = {"retry": "retries", "outage": "outages", "escalate": "escalations",
                  "unregister": "unregistered", "error": "errors", "handover": "handovers", "model_change": "model_changes"}


def summary(state, events, now, days):
    start = now - days * 86400
    per = defaultdict(Counter)
    for e in events:
        if e.get("ts", 0) < start or not e.get("thread"):
            continue
        c = per[e["thread"]]
        kind = e["event"]
        if kind == "check":
            c["checks"] += 1
        elif kind == "nudge":
            c["checks"] += 1
            c["nudges"] += 1
        elif kind == "nudge_outcome":
            c["resolved"] += e.get("resolved", 0)
            c["persisted"] += e.get("persisted", 0)
        elif kind in COUNTED_EVENTS:
            c[COUNTED_EVENTS[kind]] += 1
        elif kind == "recovered":
            c["outage_minutes"] += e.get("minutes", 0)
        elif kind == "compaction":
            c["compactions"] += e.get("new", 0)
    stewards, hooks = {}, []
    for tid, c in per.items():
        name = (state["stewards"].get(tid) or {}).get("name") or tid
        handled = c["resolved"] + c["persisted"]
        share = round(c["resolved"] / handled, 2) if handled else None
        stewards[tid] = {"name": name, **dict(c), "resolve_share": share}
        if c["nudges"] >= SUMMARY_MIN_NUDGES and share is not None and share < SUMMARY_LOW_RESOLVE_SHARE:
            hooks.append({"hook": "nudge_ignored", "thread": tid,
                          "detail": f"{name} resolved {share:.0%} after nudges ({c['resolved']}/{handled}): check whether the reconciliation rules are too strict, or the steward has not read the current closing reconciliation"})
        total = ((state["stewards"].get(tid) or {}).get("compaction") or {}).get("seen", 0)
        if total >= HANDOVER_COMPACTIONS:
            hooks.append({"hook": "long_lived_steward", "thread": tid,
                          "detail": f"{name} compacted {total} times in total ({c['compactions']} in {days} days): switch stewards, or split new goals to a new steward"})
        if c["outages"] >= SUMMARY_FREQUENT_OUTAGES:
            hooks.append({"hook": "frequent_outage", "thread": tid,
                          "detail": f"{name} had {c['outages']} turn outages in {days} days: check account quota or model routing"})
    return {"days": days, "stewards": stewards, "hooks": hooks}


# ---------- CLI ----------

def parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--state", help="State file path; default above")
    sub = p.add_subparsers(dest="cmd", required=True)
    reg = sub.add_parser("register", help="Register or update a steward and ensure the watchdog automation exists")
    reg.add_argument("--workbook", required=True, help="Workbook path; with --ref it may be absent from the worktree")
    reg.add_argument("--ref", help="Only for legacy in-repo workbooks: the remote branch is the source of truth, e.g. origin/main; omit for offline workbooks")
    reg.add_argument("--name", help="Short name used in reports; defaults to the repository directory name")
    reg.add_argument("--thread", default=os.environ.get("BB_THREAD_ID"), help="Steward thread ID; defaults to the current thread")
    reg.add_argument("--project", default=os.environ.get("BB_PROJECT_ID"), help="Project for the first automation; defaults to the current project")
    reg.add_argument("--no-automation", action="store_true", help="Register only; neither check nor create the automation (for tests or manual runs)")
    unreg = sub.add_parser("unregister", help="Remove a steward's registration")
    unreg.add_argument("--thread", default=os.environ.get("BB_THREAD_ID"))
    retirement = sub.add_parser("retire", help="Retire and release checks, keeping the reason and successor; sends no message and archives no thread")
    retirement.add_argument("--thread", default=os.environ.get("BB_THREAD_ID"))
    retirement.add_argument("--reason", required=True)
    retirement.add_argument("--successor", help="Thread ID of the registered successor steward")
    listing = sub.add_parser("roster", help="List serving and retired stewards on this host as JSON; sends nothing, writes no state")
    listing.add_argument("--thread", help="Query only this thread; unregistered threads return unknown")
    run_p = sub.add_parser("run", help="Check every registered steward (called by the automation)")
    run_p.add_argument("--dry-run", action="store_true", help="Print decisions only; no messages, retries or state writes")
    rep = sub.add_parser("report", help="Recent check log and items needing the user's attention")
    rep.add_argument("--since", type=int, default=60, help="Minutes, default 60")
    summ = sub.add_parser("summary", help="Nudges, resolve share, retries and review hooks aggregated over days")
    summ.add_argument("--days", type=int, default=7)
    summ.add_argument("--json", action="store_true")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    path = state_path_from(args.state)
    bb = Bb()
    try:
        if args.cmd == "roster":
            print(json.dumps(roster(load_state(path), bb, args.thread), ensure_ascii=False, indent=2))
            return 0
        if args.cmd in ("report", "summary"):
            state = load_state(path)
            events = read_events(path)
            if args.cmd == "report":
                print(report(state, events, time.time(), args.since))
            else:
                res = summary(state, events, time.time(), args.days)
                if args.json:
                    print(json.dumps(res, ensure_ascii=False, indent=2))
                else:
                    for s in res["stewards"].values():
                        print(f"{s['name']}: checks {s.get('checks', 0)}, nudges {s.get('nudges', 0)}, resolve share {s['resolve_share']}, "
                              f"retries {s.get('retries', 0)}, outages {s.get('outages', 0)}, takeovers {s.get('handovers', 0)}, "
                              f"model changes {s.get('model_changes', 0)}, compactions {s.get('compactions', 0)}")
                    for h in res["hooks"]:
                        print(f"review hook {h['hook']}: {h['detail']}")
            return 0
        with state_lock(path):
            state = load_state(path)
            if args.cmd == "register":
                res = register(state, bb, args.thread, args.workbook, args.ref, args.name, args.project,
                               state_path=path, manage_automation=not args.no_automation)
                save_state(path, state)
                append_events(path, [event(time.time(), res["thread"], "register", workbook=res["workbook"])])
                print(json.dumps(res, ensure_ascii=False, indent=2))
            elif args.cmd in ("unregister", "retire"):
                res = retire(state, bb, args.thread, path,
                             getattr(args, "reason", "watchdog released manually"), getattr(args, "successor", None))
                print(json.dumps(res, ensure_ascii=False))
            else:
                started = time.time()
                results, events = run(state, path, bb, now=started, dry_run=args.dry_run)
                if not args.dry_run:
                    append_events(path, [event(time.time(), None, "run", stewards=len(results),
                                               seconds=round(time.time() - started, 1))])
                if args.dry_run:
                    print(json.dumps({"results": results, "events": events}, ensure_ascii=False, indent=2))
                else:
                    reports = [r["report"] for r in results.values() if r.get("report")]
                    if reports:
                        print("\n".join(reports))
        return 0
    except (WatchError, OSError) as exc:
        # Known failures still exit 0: the automation pauses after three failures in a row, and one bb hiccup or
        # disk problem must not stop the watchdog.
        print(f"Watchdog did not finish: {exc}")
        if args.cmd == "run" and not getattr(args, "dry_run", False):
            append_events(path, [event(time.time(), None, "error", detail=str(exc)[:300])])
        return 0 if args.cmd == "run" else 2


if __name__ == "__main__":
    sys.exit(main())
