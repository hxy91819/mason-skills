#!/usr/bin/env python3
"""BB steward workbook gates: structure, size, commit throttling and closing reconciliation.

Usage:
  python3 steward_workbook.py --mode ledger-check --file .local/steward/<topic>-requirements.md
  python3 steward_workbook.py --mode check --file .local/steward/<topic>.md
  python3 steward_workbook.py --mode verify --file .local/steward/<topic>.md
  python3 steward_workbook.py --mode should-commit --file .local/steward/<topic>.md
  python3 steward_workbook.py --mode reconcile [--live] --file .local/steward/<topic>.md

reconcile checks the state marker of every open route line and the category of every user to-do; --live also
checks through `bb thread list` that threads marked "in progress" are still alive.
Prints JSON on stdout; exit code 0 means pass, 2 means the gate failed or the arguments are invalid.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import steward_source as source
import steward_vocab as vocab
from steward_vocab import DECISIONS, REQUIRED_SECTIONS, ROUTE, TODOS
from workbook_timeline import HISTORICAL_WARNING, format_timeline

HISTORY_NOT_APPLICABLE = "History log; standard five-column statistics do not apply"
DEFAULT_MAX_NONEMPTY_LINES = 45
DEFAULT_MAX_LINE_CHARS = 180
DEFAULT_MAX_ROUTE_ITEMS = None  # No cap on route stages by default; set one explicitly with --max-route-items.
DEFAULT_MAX_DECISIONS = 12

MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
WIKI_LINK_RE = re.compile(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]")
CHECKBOX_RE = re.compile(r"^-\s*\[([ xX])\]\s*(.+)$")

# Closing reconciliation: the four states after `←` on open route lines, and the user to-do categories.
STATE_RUNNING, STATE_WAITING_USER, STATE_SCHEDULED, STATE_QUEUED_AFTER = vocab.STATES
STATE_KEYWORDS = vocab.STATES
STATE_HINT = vocab.STATE_HINT
TODO_CATEGORIES = vocab.TODO_CATEGORIES
STATE_STATS = {STATE_RUNNING: "in_progress", STATE_WAITING_USER: "waiting_on_user",
               STATE_SCHEDULED: "scheduled", STATE_QUEUED_AFTER: "queued_after"}
THREAD_ID_RE = re.compile(r"(?<![A-Za-z0-9_])thr_[a-z0-9]{6,}")
SCHEDULE_RE = re.compile(r"(?:(\d{4})-)?(\d{1,2})-(\d{1,2})\s*(\d{1,2})[:：](\d{2})")
# Stage numbers such as "Stage 5", "Release 1-6", "Stage 1-4, 9, 12-14" (legacy Chinese prefixes too), used to
# match a to-do's Blocks cell or a dependency to route lines.
_RANGE = r"\d+(?:\s*(?:[–—\-~～至到]|to\b)\s*\d+)?"
_LIST_SEP = r"\s*(?:[、,，/和]|and\b)\s*"
STAGE_ID_RE = re.compile(rf"(阶段|發佈|发布|階段|stage|phase|release)\s*({_RANGE}(?:{_LIST_SEP}{_RANGE})*)", re.I)
STAGE_PREFIXES = {"阶段": "stage", "階段": "stage", "发布": "release", "發佈": "release"}
# Only idle and error are settled BB thread states; pending/starting/active/stopping count as moving.
SETTLED_STATUSES = ("idle", "error")
DEFAULT_GRACE_MINUTES = 30
# While any of these background activities run, an idle thread still counts as working; plan approvals do not.
ALIVE_ACTIVITY_KEYS = ("activeBackgroundAgentCount", "activeBackgroundCommandCount", "activeGoalCount", "activeWorkflowCount")


def visible_length(line: str) -> int:
    """Visible character count after stripping Markdown link targets."""
    s = MD_LINK_RE.sub(r"\1", re.sub(r"<!--.*?-->", "", line))
    s = WIKI_LINK_RE.sub(r"\1", s)
    return len(s.strip())


def parse_workbook(text: str):
    lines = text.splitlines()
    title = None
    sections = {}
    section_order = []
    current_section = None
    subheadings = []

    for lineno, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if stripped.startswith("# ") and title is None and current_section is None:
            title = stripped[2:].strip()
            continue
        if stripped.startswith("## "):
            sec_name = stripped[3:].strip()
            sec_name = vocab.section_name(sec_name)
            section_order.append(sec_name)
            current_section = sec_name
            sections.setdefault(sec_name, [])
            continue
        if stripped.startswith("###"):
            subheadings.append((lineno, stripped))
        if current_section is not None:
            sections[current_section].append((lineno, raw))

    return {
        "lines": lines,
        "title": title,
        "section_order": section_order,
        "sections": sections,
        "subheadings": subheadings,
    }


def check_workbook(text: str, max_nonempty_lines=DEFAULT_MAX_NONEMPTY_LINES,
                   max_line_chars=DEFAULT_MAX_LINE_CHARS,
                   max_route_items=DEFAULT_MAX_ROUTE_ITEMS,
                   max_decisions=DEFAULT_MAX_DECISIONS):
    parsed = parse_workbook(text)
    errors = []
    nonempty_lines = [ln for ln in parsed["lines"] if ln.strip()]

    if not parsed["title"]:
        errors.append("Missing the level-1 title (# <goal in one sentence>).")

    if parsed["section_order"] != REQUIRED_SECTIONS:
        errors.append(
            f"Level-2 headings must be exactly {REQUIRED_SECTIONS} in that order; found {parsed['section_order']}."
        )

    if parsed["subheadings"]:
        first_ln, first_h = parsed["subheadings"][0]
        errors.append(f"Line {first_ln}: subheading {first_h!r} is not allowed; the workbook keeps three flat sections.")

    todo_linenos = {ln for ln, _ in parsed["sections"].get(TODOS, [])}
    for lineno, raw in enumerate(parsed["lines"], start=1):
        if lineno in todo_linenos:
            continue  # To-dos carry background and recommendations; no per-line limit.
        vlen = visible_length(raw)
        if vlen > max_line_chars:
            errors.append(
                f"Line {lineno}: {vlen} visible characters exceed the limit of {max_line_chars}; route and decision "
                "lines keep only the conclusion, not a running log."
            )

    route_lines = parsed["sections"].get(ROUTE, [])
    route_items = []
    for lineno, raw in route_lines:
        s = raw.strip()
        if not s:
            continue
        if s.startswith("|") and s.endswith("|"):
            errors.append(
                f"Line {lineno}: a table in \"{ROUTE}\"; sub-task matrices belong in a project issue or plan "
                "document, the route keeps only stage lines and the current position."
            )
        m = CHECKBOX_RE.match(s)
        if m:
            route_items.append((lineno, m.group(1).lower() == "x", "←" in s, m.group(2)))

    if max_route_items is not None and len(route_items) > max_route_items:
        errors.append(f"\"{ROUTE}\" has {len(route_items)} stages, over the limit of {max_route_items}.")

    decision_lines = parsed["sections"].get(DECISIONS, [])
    decisions = [raw.strip() for _, raw in decision_lines if raw.strip().startswith("- ")]
    warnings = []
    # Line and decision counts only warn: the goal is to keep clutter out, not to squeeze out necessary facts.
    if len(nonempty_lines) > max_nonempty_lines:
        warnings.append(
            f"{len(nonempty_lines)} non-empty lines exceed the suggested {max_nonempty_lines}; check for running "
            "logs or detailed matrices that belong back in project docs/issues. Completed stages and entries that "
            "still bind stay."
        )
    if len(decisions) > max_decisions:
        warnings.append(
            f"\"{DECISIONS}\" has {len(decisions)} entries, over the suggested {max_decisions}; review each: move out "
            "those whose affected stages are all complete or that are written into project docs/ADRs (the "
            "requirement ledger keeps the original record); keep those that still constrain unfinished work."
        )

    return {
        "ok": len(errors) == 0,
        "warnings": warnings,
        "stats": {
            "nonempty_lines": len(nonempty_lines),
            "route_items": len(route_items),
            "decision_items": len(decisions),
        },
        "errors": errors,
    }


# Chinese alternatives in the sets and patterns below are legacy aliases kept for existing ledgers.
LEDGER_COLUMNS = vocab.LEDGER_COLUMNS
LEDGER_STATES = set(vocab.LEDGER_STATES)
EMPTY_CELL = {"", "-", "—", "...", "…", "none", "n/a", "tbd", "无", "無", "待补", "待補"}
EMPTY_RESULTS = {"ok", "done", "完成", "已完成", "已採納", "採納", "已采纳", "采纳", "已處理", "已处理",
                 "處理完畢", "处理完毕", "已落實", "已落实", "已解决", "已解決"}
# Results that only restate the status ("done", "all completed", "has been handled") say nothing concrete.
VACUOUS_RESULT_RE = re.compile(
    r"(?:it|this|everything|all)?(?:is|was|has|have|been|already|fully|all)*"
    r"(?:done|complete|completed|handled|adopted|accepted|resolved|finished|implemented)(?:already)?"
    r"|(?:已|已经|已經)?(?:全部|全數|全部都|均|都)?(?:完成|處理|处理|採納|采纳|落實|落实|解决|解決)(?:了|完畢|完毕)?")
SUPERSEDED_RE = re.compile(
    r"(?:superseded|replaced|overridden|covered)\s+by\s+(.+)|^by\s+(.+)"
    r"|(?:replacement|successor|replaced with|changed to|switched to)[:：]?\s+(.+)"
    r"|(?:被|由)\s*(.+?)\s*(?:取代|替代|覆蓋|覆盖)|(?:取代者|替代者|覆蓋者|覆盖者|改為|改为|改由)[:：]?\s*(.+)", re.I)
VAGUE_TARGETS = {"a later requirement", "later requirement", "later requirements", "a later request", "later request",
                 "follow-up", "a follow-up", "follow-up requirement", "other requirement", "other requirements",
                 "another requirement", "後續要求", "后续要求", "後續需求", "后续需求", "其他要求", "其他需求"}
NO_REASON_RE = re.compile(
    r"(?:already)?(?:excluded|cancell?ed|dropped|rejected|skipped|notdoing|wontdo|won'tdo|notadopted|notpursued)"
    r"(?:this|the|that)?(?:requirement|request|item|task)?|noactionneeded|nothingtodo"
    r"|(?:已|已经|已經)?(?:排除|取消|不做|不採納|不采纳|不執行|不执行)"
    r"(?:(?:這|这|該|该|此)(?:個|个)?(?:要求|需求|事項|事项|任務|任务))?|無需處理|无需处理")
LEDGER_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
LOCATED_RE = re.compile(r"https?://\S+|(?:/|\./|\.\./|~/)[^\s、；;]+|\bPR\s*#?\d+|\b[0-9a-f]{7,40}\b|"
                        + vocab.SESSION_REPLY_RE)


def check_ledger(text: str):
    """Check periods, tables and per-row results; does not judge business truth or whether every request is recorded."""
    errors, rows, periods = [], 0, 0
    counts = dict.fromkeys(vocab.LEDGER_STATES, 0)
    in_period, tables, header, separator = False, 0, False, False
    fenced = False
    lines = text.splitlines()
    columns_hint = " | ".join(LEDGER_COLUMNS)

    def error(lineno, message):
        raw = lines[lineno - 1]
        errors.append(f"Line {lineno}: {message} Original: {raw}")

    def close_period(lineno):
        if in_period and tables != 1:
            error(lineno, "Each period must have exactly one requirement table.")
        if header and not separator:
            error(lineno, "The header row needs a five-column Markdown separator row.")

    last_line = 1
    for lineno, raw in enumerate(lines, 1):
        last_line = lineno
        line = raw.strip()
        if line.startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        if line.startswith("## "):
            close_period(lineno)
            in_period = bool(vocab.PERIOD_RE.fullmatch(line))
            if not in_period:
                error(lineno, f"Period headings must read {vocab.PERIOD_HINT}.")
            periods += int(in_period)
            tables, header, separator = 0, False, False
            continue
        if not line.startswith("|"):
            if header and not separator:
                error(lineno, "The header row needs a five-column Markdown separator row.")
            header, separator = False, False
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip("|"))]
        if not in_period:
            error(lineno, "Requirement tables must sit under a period heading.")
        if not header:
            tables += 1
            header = True
            separator = False
            if cells not in (LEDGER_COLUMNS, vocab.LEDGER_COLUMN_ALIASES):
                error(lineno, f"The header must be | {columns_hint} |.")
            continue
        if not separator:
            separator = True
            if len(cells) == 5 and all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                continue
            error(lineno, "The header row needs a five-column Markdown separator row.")
        if len(cells) != 5:
            error(lineno, f"Requirement rows need five columns; found {len(cells)}.")
            continue
        rows += 1
        date, requirement, raw_status, result, material = cells
        if date.lower() in EMPTY_CELL or requirement.lower() in EMPTY_CELL:
            error(lineno, "Date and requirement must not be empty.")
        status = vocab.ledger_state(raw_status)
        if status is None:
            error(lineno, f"Unknown status \"{raw_status}\"; allowed: {', '.join(vocab.LEDGER_STATES)}.")
        else:
            counts[status] += 1
        normalized = re.sub(r"[\s`*。.!！；;]+", "", result).lower()
        vacuous = normalized in EMPTY_RESULTS or bool(VACUOUS_RESULT_RE.fullmatch(normalized))
        if result.lower() in EMPTY_CELL or vacuous:
            error(lineno, "The result must state a concrete conclusion, not just \"done\" or \"completed\".")
        if status in {vocab.DONE, vocab.ADOPTED}:
            # A file path also locates local material; a bare preview name is not an address.
            located = (any(m.group(2).strip().lower() not in EMPTY_CELL for m in LEDGER_LINK_RE.finditer(material))
                       or LOCATED_RE.search(material))
            if not located:
                error(lineno, f"{status} needs a material link, file path, commit, PR, or the literal \"session reply\".")
        if status == vocab.SUPERSEDED:
            target = SUPERSEDED_RE.search(result)
            named = next((g for g in target.groups() if g), "").strip().rstrip(".。").lower() if target else ""
            if named in EMPTY_CELL | VAGUE_TARGETS:
                error(lineno, "A superseded result must name the row or matter that replaced it, e.g. \"replaced by <X>\".")
        if status == vocab.EXCLUDED:
            if result.lower() in EMPTY_CELL or vacuous or NO_REASON_RE.fullmatch(normalized):
                error(lineno, "An excluded result must state the reason.")
    close_period(last_line)
    if not periods:
        errors.append(f"Missing period heading: {vocab.PERIOD_HINT}.")
    summary = {**counts, **{legacy: counts[state] for state, legacy in vocab.PLUGIN_SUMMARY_KEYS.items()}}
    return {"ok": not errors, "stats": {"periods": periods, "rows": rows}, "summary": summary, "errors": errors}


def check_workbook_source(file, text, read, git_source=False, **check_args):
    res = check_workbook(text, **check_args)
    try:
        target, kind = source.ledger_entry(text)
        ledger = source.resolve_link(file, target, git_source)
        read(ledger)
        res['ledger'] = {'path': ledger, 'kind': kind}
    except (source.SourceError, OSError, ValueError) as exc:
        res['errors'].append(str(exc))
    res['ok'] = not res['errors']
    return res


def check_workbook_file(file_path: Path, **check_args):
    return check_workbook_source(str(file_path), file_path.read_text(), lambda path: Path(path).read_text(), **check_args)


def route_stem(body: str) -> str:
    """Stage name before the first colon or opening parenthesis; a row identity that survives edits."""
    return re.split(r"[（(—\-:：]", body.split("←", 1)[0].strip(), maxsplit=1)[0].strip()


def parse_schedule(text: str, now: datetime):
    """Parse `MM-DD HH:MM` (optionally with a year) as local time; without a year pick the year closest to now."""
    m = SCHEDULE_RE.search(text)
    if not m:
        return None
    year, month, day, hour, minute = m.groups()
    try:
        if year:
            return datetime(int(year), int(month), int(day), int(hour), int(minute))
        candidates = [datetime(now.year + d, int(month), int(day), int(hour), int(minute)) for d in (-1, 0, 1)]
    except ValueError:
        return None
    return min(candidates, key=lambda c: abs((c - now).total_seconds()))


def parse_marker(body: str, now: datetime):
    """Parse the state after `←` on an open line. Returns (state, detail): state is one of the four canonical
    states, or None with detail giving the reason."""
    if "←" not in body:
        return None, "no state"
    marker = body.rsplit("←", 1)[1].strip()
    matched = vocab.match_state(marker)
    if matched is None:
        return None, f"state \"{marker[:16]}\" is not one of the four"
    state, literal, rest = matched
    if state == STATE_RUNNING and not THREAD_ID_RE.search(body):
        return None, "in progress without a thread ID"
    if state == STATE_SCHEDULED and parse_schedule(rest, now) is None:
        return None, "scheduled without MM-DD HH:MM"
    if state == STATE_QUEUED_AFTER and vocab.queued_target(literal, rest) is None:
        return None, "after <item> without the dependent output"
    return state, marker


def state_signature(body: str):
    """State signature: in progress / waiting on user compare the state only (a new thread ID is not a transition),
    scheduled compares the time, after compares the dependency."""
    if "←" not in body:
        return None
    marker = body.rsplit("←", 1)[1].strip()
    matched = vocab.match_state(marker)
    if matched is None:
        return ("other", marker)
    state, literal, rest = matched
    if state == STATE_SCHEDULED:
        m = SCHEDULE_RE.search(marker)
        return (state, m.group(0) if m else marker)
    if state == STATE_QUEUED_AFTER:
        target = vocab.queued_target(literal, rest)
        return (state, target[0] if target else rest)
    return (state,)


def table_cells(line: str):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_todos(parsed):
    """Parse the user to-do table by header name (Chinese headers map to English); without a header use template order."""
    columns = {"Status": 0, "Item": 1, "Why only the user": 2, "Blocks": 3, "Raised": 4}
    todos = []
    for lineno, raw in parsed["sections"].get(TODOS, []):
        s = raw.strip()
        if not (s.startswith("|") and s.endswith("|")):
            continue
        cells = table_cells(s)
        if all(set(c) <= {"-", ":", " "} for c in cells):
            continue
        names = [vocab.todo_column(c) for c in cells]
        if "Status" in names and "Item" in names:
            columns = {name: idx for idx, name in enumerate(names)}
            continue

        def cell(name):
            idx = columns.get(name)
            return cells[idx] if idx is not None and idx < len(cells) else ""

        todos.append({
            "line": lineno,
            "status": cell("Status"),
            "item": cell("Item"),
            "reason": cell("Why only the user"),
            "blocks": cell("Blocks"),
        })
    return todos


def is_open_todo(todo) -> bool:
    return vocab.todo_status(todo["status"]) == vocab.TODO_OPEN


def plain_label(text: str, limit=24) -> str:
    s = WIKI_LINK_RE.sub(r"\1", MD_LINK_RE.sub(r"\1", text)).replace("`", "").replace("*", "").strip()
    return s if len(s) <= limit else s[:limit] + "…"


def row_head(body: str) -> str:
    """Title part before the route line's first colon (links expanded first so URL colons do not cut it)."""
    head = MD_LINK_RE.sub(r"\1", body.split("←", 1)[0])
    return re.split(r"[:：]", head, maxsplit=1)[0]


def stage_ids(text: str):
    ids = set()
    for m in STAGE_ID_RE.finditer(text):
        prefix = STAGE_PREFIXES.get(m.group(1), m.group(1).lower())
        for part in re.split(_LIST_SEP, m.group(2), flags=re.I):
            nums = [int(n) for n in re.findall(r"\d+", part)]
            if len(nums) >= 2 and 0 <= nums[1] - nums[0] < 100:
                ids.update((prefix, n) for n in range(nums[0], nums[1] + 1))
            elif nums:
                ids.add((prefix, nums[0]))
    return ids


def squash(text: str) -> str:
    return re.sub(r"\s+", "", plain_label(text, limit=10**6)).lower()


def refers_to(text: str, head: str) -> bool:
    """Whether text (a to-do's Blocks cell or a dependency) points at the route line titled head: compare stage
    numbers when present, otherwise the whitespace-free title."""
    ids = stage_ids(head)
    if ids:
        return bool(ids & stage_ids(text))
    h, t = squash(head), squash(text)
    return len(h) >= 2 and len(t) >= 2 and (h in t or t in h)


def normalize_thread(raw: dict) -> dict:
    activity = raw.get("activity") or {}
    return {
        "id": raw.get("id"),
        "status": raw.get("status"),
        "archived": bool(raw.get("archivedAt")),
        # Only queuedWork == waiting means messages still await delivery; failed is a failed delivery, not motion.
        "queued": raw.get("queuedWork") == "waiting",
        "interaction": bool(raw.get("hasPendingInteraction")),
        "background": any((activity.get(k) or 0) > 0 for k in ALIVE_ACTIVITY_KEYS),
        "updated_at": (raw.get("updatedAt") or 0) / 1000,
        "parent": raw.get("parentThreadId"),
        "provider": raw.get("providerId"),
        "title": raw.get("title"),
    }


def thread_state(info, now_ts: float, grace_seconds: float) -> str:
    """alive = running, queued or with background activity; recent = finished within the grace period (the
    completion notice may still be on its way)."""
    if info is None:
        return "missing"
    if info["archived"]:
        return "archived"
    if info["interaction"]:
        return "interaction"
    if info["status"] not in SETTLED_STATUSES or info["queued"] or info["background"]:
        return "alive"
    if info["status"] == "error":
        return "failed"
    if now_ts - info["updated_at"] < grace_seconds:
        return "recent"
    return "stopped"


def describe_thread(tid: str, state: str, info, now_ts: float) -> str:
    if state == "stopped":
        hours = (now_ts - info["updated_at"]) / 3600
        return f"{tid} idle for {hours:.1f} h"
    return f"{tid} " + {"missing": "not found", "archived": "archived", "failed": "failed with no retry queued",
                        "interaction": "waiting for interaction"}.get(state, state)


def bb_thread_list(*args):
    """Run `bb thread list ... --json` and return normalized threads; raises RuntimeError on failure."""
    try:
        res = subprocess.run(["bb", "thread", "list", *args, "--json"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"bb thread list could not run: {exc}") from exc
    try:
        data = json.loads(res.stdout)
    except ValueError as exc:
        raise RuntimeError(f"bb thread list returned non-JSON: {res.stderr.strip()[:300]}") from exc
    if res.returncode or not isinstance(data, list):
        raise RuntimeError(f"bb thread list failed: {res.stdout.strip()[:300] or res.stderr.strip()[:300]}")
    return [normalize_thread(t) for t in data]


def fetch_threads(ids):
    """Look up threads by ID and return {id: info}; IDs not found are absent."""
    # bb thread list cannot filter by ID: fetch the whole list, then look up misses in the archived list.
    wanted = set(ids)
    if not wanted:
        return {}
    found = {info["id"]: info for info in bb_thread_list("--include-hidden") if info["id"] in wanted}
    if wanted - found.keys():
        for info in bb_thread_list("--archived", "--include-hidden"):
            if info["id"] in wanted:
                found[info["id"]] = info
    for info in found.values():
        if info["status"] == "idle" and not (info["archived"] or info["queued"] or info["background"]):
            info["background"] = waiting_on_background(info["id"])
    return found


def waiting_on_background(tid: str) -> bool:
    """Whether an idle thread waits on something that will wake it; neither shows in activity, so skipping this
    check would report a false stall.

    - a running child thread, e.g. an independent review it dispatched, which reports back on completion;
    - a running thread-level persistent terminal (bb terminal) nobody has typed into, hosting a long wait. An
      interactive shell a person opened has typed input and does not count.
    """
    try:
        children = bb_thread_list("--parent-thread", tid, "--include-hidden")
    except RuntimeError:
        children = []
    if any(c["status"] not in SETTLED_STATUSES or c["queued"] or c["background"] for c in children):
        return True
    return any(isinstance(s, dict) and s.get("status") == "running" and not s.get("lastUserInputAt")
               for s in bb_terminal_sessions(tid))


def bb_terminal_sessions(tid: str):
    """Sessions from `bb terminal list --thread <id> --json` (unfinished only); on failure return an empty list
    and keep judging the thread as settled."""
    try:
        res = subprocess.run(["bb", "terminal", "list", "--thread", tid, "--json"],
                             capture_output=True, text=True, timeout=30)
        sessions = json.loads(res.stdout).get("sessions")
    except (OSError, subprocess.TimeoutExpired, ValueError, AttributeError):
        return []
    return sessions if isinstance(sessions, list) else []


def running_thread_ids(text: str):
    """Thread IDs on open route lines marked "in progress" only; reconcile's referenced_threads is unchanged."""
    ids = set()
    for _, raw in parse_workbook(text)["sections"].get(ROUTE, []):
        match = CHECKBOX_RE.match(raw.strip())
        if match and match.group(1).lower() != "x":
            body = match.group(2)
            if parse_marker(body, datetime.now())[0] == STATE_RUNNING:
                ids.update(THREAD_ID_RE.findall(body))
    return sorted(ids)


def reconcile_workbook(text: str, now: datetime | None = None, threads: dict | None = None,
                       unlisted_alive: int = 0, grace_minutes: int = DEFAULT_GRACE_MINUTES):
    """Closing reconciliation. With threads None only static checks run; otherwise "in progress" threads are
    checked for liveness.

    unlisted_alive > 0 means the steward has running child threads not yet written into the route (the workbook
    comes from a remote and may lack the new thread IDs); "in progress but the thread stopped" then drops to
    minor. Any problem with severity nudge makes ok False.
    """
    now = now or datetime.now()
    now_ts = now.timestamp()
    grace = grace_minutes * 60
    parsed = parse_workbook(text)
    problems = []
    stats = {"open_rows": 0, **{key: 0 for key in STATE_STATS.values()}}
    referenced = set()

    def add(kind, severity, line, label, detail):
        problems.append({"kind": kind, "severity": severity, "line": line, "label": label, "detail": detail})

    rows = []
    for lineno, raw in parsed["sections"].get(ROUTE, []):
        m = CHECKBOX_RE.match(raw.strip())
        if m:
            rows.append({"line": lineno, "done": m.group(1).lower() == "x", "body": m.group(2), "head": row_head(m.group(2))})
    todos = parse_todos(parsed)
    open_todos = [t for t in todos if is_open_todo(t)]
    blocking = [t for t in open_todos if vocab.is_blocking(t["blocks"])]

    for row in rows:
        lineno, body = row["line"], row["body"]
        referenced.update(THREAD_ID_RE.findall(body))
        if row["done"]:
            continue
        stats["open_rows"] += 1
        label = plain_label(route_stem(body))
        state, detail = parse_marker(body, now)
        if state is None:
            add("no_state", "nudge", lineno, label, detail)
            continue
        stats[STATE_STATS[state]] += 1
        if state == STATE_WAITING_USER:
            if not any(refers_to(t["blocks"], row["head"]) for t in blocking):
                add("user_wait_unbacked", "nudge", lineno, label,
                    "marked waiting on user, but no open to-do has a Blocks cell pointing at this line")
        elif state == STATE_QUEUED_AFTER:
            _, literal, rest = vocab.match_state(detail)
            target = vocab.queued_target(literal, rest)[0]
            # When the dependency matches route lines here and all are done, this line can move; unmatched
            # dependencies are external and not judged.
            matched = [r for r in rows if r is not row and refers_to(target, r["head"])]
            if matched and all(r["done"] for r in matched):
                add("dependency_done", "nudge", lineno, label,
                    f"prerequisite \"{plain_label(target)}\" is done; this line should move")
        elif state == STATE_SCHEDULED:
            due = parse_schedule(vocab.match_state(detail)[2], now)
            if due is not None and now_ts - due.timestamp() > grace:
                add("schedule_passed", "nudge", lineno, label, f"scheduled time {due:%m-%d %H:%M} has passed")
        elif state == STATE_RUNNING and threads is not None:
            ids = THREAD_ID_RE.findall(body)
            states = {tid: thread_state(threads.get(tid), now_ts, grace) for tid in ids}
            waiting = [tid for tid, st in states.items() if st == "interaction"]
            if waiting:
                add("child_waiting", "nudge", lineno, label, "; ".join(f"{tid} waiting for interaction" for tid in waiting))
            if not waiting and not any(st in ("alive", "recent") for st in states.values()):
                detail = "marked in progress, but " + "; ".join(
                    describe_thread(tid, st, threads.get(tid), now_ts) for tid, st in states.items())
                if unlisted_alive:
                    add("stale_running", "minor", lineno, label,
                        detail + f" ({unlisted_alive} more child threads not in the route are running)")
                else:
                    add("stale_running", "nudge", lineno, label, detail)
            elif not waiting:
                # With several threads on one line, one running thread makes the line look healthy and hides
                # the stopped ones; report each of them.
                stopped = {tid: st for tid, st in states.items() if st not in ("alive", "recent")}
                if stopped:
                    detail = "a thread on this line is running, but " + "; ".join(
                        describe_thread(tid, st, threads.get(tid), now_ts) for tid, st in stopped.items())
                    add("stale_sibling", "minor" if unlisted_alive else "nudge", lineno, label,
                        detail + "; split them into separate lines or update this line")

    for todo in open_todos:
        if not vocab.has_category(todo["reason"]):
            severity = "nudge" if todo in blocking else "minor"
            add("todo_category_missing", severity, todo["line"], plain_label(todo["item"]),
                "the user to-do reason does not start with a category (" + ", ".join(TODO_CATEGORIES) + ")")

    return {
        "ok": not any(p["severity"] == "nudge" for p in problems),
        "stats": stats,
        "referenced_threads": sorted(referenced),
        "problems": problems,
    }


def extract_state_signature(text: str):
    """Signature that decides whether the workbook made a real state transition; ignores wording tweaks in
    parentheses."""
    parsed = parse_workbook(text)
    route_sig = []
    for _, raw in parsed["sections"].get(ROUTE, []):
        s = raw.strip()
        m = CHECKBOX_RE.match(s)
        if m:
            checked = m.group(1).lower() == "x"
            route_sig.append((route_stem(m.group(2)), checked, state_signature(m.group(2))))

    decision_sig = []
    for _, raw in parsed["sections"].get(DECISIONS, []):
        s = raw.strip()
        if s.startswith("- "):
            decision_sig.append(re.sub(r"\s+", " ", s[2:].strip()))

    todo_sig = [(vocab.todo_status(t["status"]), t["item"], t["blocks"]) for t in parse_todos(parsed)]

    return {
        "route": route_sig,
        "decisions": decision_sig,
        "todos": todo_sig,
    }


def head_content_for(file_path: Path):
    file_path = file_path.resolve()
    try:
        top = subprocess.run(
            ["git", "-C", str(file_path.parent), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()
        rel = file_path.relative_to(Path(top).resolve()).as_posix()
        shown = subprocess.run(
            ["git", "-C", top, "show", f"HEAD:{rel}"],
            capture_output=True, text=True, timeout=10,
        )
        if shown.returncode != 0:
            return None
        return shown.stdout
    except Exception:
        return None


def should_commit_workbook(file_path: Path, check_args: dict, baseline_text: str | None = None):
    text = file_path.read_text()
    check_res = check_workbook_file(file_path, **check_args)
    if not check_res["ok"]:
        return {
            **check_res,
            "file": str(file_path),
            "should_commit": False,
            "reason": "check_failed",
            "changed_sections": [],
        }

    old_text = baseline_text if baseline_text is not None else head_content_for(file_path)
    if old_text is None:
        return {
            **check_res,
            "file": str(file_path),
            "should_commit": True,
            "reason": "new_file",
            "changed_sections": REQUIRED_SECTIONS,
        }

    old_sig = extract_state_signature(old_text)
    new_sig = extract_state_signature(text)
    changed = []
    if old_sig["route"] != new_sig["route"]:
        changed.append(ROUTE)
    if old_sig["decisions"] != new_sig["decisions"]:
        changed.append(DECISIONS)
    if old_sig["todos"] != new_sig["todos"]:
        changed.append(TODOS)

    return {
        **check_res,
        "file": str(file_path),
        "should_commit": len(changed) > 0,
        "reason": "state_changed" if changed else "no_structural_state_change",
        "changed_sections": changed,
    }


def workbook_location(repo=None):
    """Resolve the shared primary checkout, including when invoked in a worktree."""
    cwd = Path(repo or Path.cwd()).expanduser().resolve()
    result = subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True, text=True, check=True, timeout=10,
    )
    common = Path(result.stdout.strip()).resolve()
    return common.parent / ".local" / "steward", common


def init_workbook(repo=None):
    path, common = workbook_location(repo)
    root = common.parent
    created = not path.exists()
    path.mkdir(parents=True, exist_ok=True)
    # Check from the project, never from the nested local repository.
    def ignored():
        return subprocess.run(
            ["git", "-C", str(root), "check-ignore", "-v", ".local/steward/"],
            capture_output=True, text=True, timeout=10,
        )
    result = ignored()
    if result.returncode == 1:
        exclude = common / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        old = exclude.read_text() if exclude.exists() else ""
        with exclude.open("a") as handle:
            handle.write(("\n" if old and not old.endswith("\n") else "") + "/.local/\n")
        result = ignored()
    if result.returncode:
        raise RuntimeError("Cannot confirm the project ignores .local/steward: " + result.stderr.strip())
    imported = []
    legacy = root / "docs" / "steward"
    if not any(child.name != ".git" for child in path.iterdir()) and legacy.is_dir():
        for child in legacy.iterdir():
            if child.name == ".git":
                continue
            target = path / child.name
            if child.is_dir():
                shutil.copytree(child, target)
            else:
                shutil.copy2(child, target)
            imported.append(child.name)
        if imported:
            print("Delete the repository copies via MR and point the AGENTS.md routing line at .local/steward/", file=sys.stderr)
    # rev-parse alone would find the enclosing project; require a git marker here.
    if not (path / ".git").exists():
        subprocess.run(["git", "-C", str(path), "init"], capture_output=True,
                       text=True, check=True, timeout=10)
    return {"path": str(path), "created": created,
            "ignored_by": result.stdout.strip(), "imported": sorted(imported)}


def format_workbook(path, *, dry_run=False, verbose_warnings=False):
    original = path.read_text()
    formatted, warnings = format_timeline(original, head_content_for(path))
    changed = formatted != original
    if changed and not dry_run:
        path.write_text(formatted)
    if not verbose_warnings:
        historical = HISTORICAL_WARNING
        count = sum(warning.endswith(historical) for warning in warnings)
        warnings = [warning for warning in warnings if not warning.endswith(historical)]
        if count:
            warnings.append(f"historical completion time unverified: {count} items (expand with --verbose-warnings)")
    return formatted, {"ok": True, "file": str(path), "changed": changed,
                       "timezone": "Asia/Singapore", "warnings": warnings}


def reconcile_local(text, live):
    threads = fetch_threads(reconcile_workbook(text)["referenced_threads"]) if live else None
    return reconcile_workbook(text, threads=threads)


def verify_workbook(path, args, check_args):
    steps = {}
    stage = "format"
    try:
        text, steps[stage] = format_workbook(path, dry_run=args.dry_run,
                                             verbose_warnings=args.verbose_warnings)
        stage = "check"
        ledger_path = Path(args.ledger).expanduser().resolve() if args.ledger else None
        if ledger_path is None:
            steps[stage] = check_workbook_source(str(path), text, lambda p: Path(p).read_text(), **check_args)
        else:
            steps[stage] = check_workbook(text, **check_args)
            steps[stage]["ledger"] = {"path": str(ledger_path), "kind": "standard"}
        if steps[stage]["ok"]:
            stage = "ledger-check"
            ledger = steps["check"]["ledger"]
            if ledger["kind"] == "history":
                steps[stage] = {"ok": False, "applicable": False, "errors": ["History log; pass a standard requirement ledger with --ledger"]}
            else:
                steps[stage] = check_ledger(Path(ledger["path"]).read_text())
            if steps[stage]["ok"]:
                stage = "reconcile"
                steps[stage] = reconcile_local(text, args.live)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        steps[stage] = {"ok": False, "errors": [str(exc)]}
    ok = steps[stage]["ok"]
    return {"ok": ok, "file": str(path), "dry_run": args.dry_run, "steps": steps,
            **({"failed_step": stage} if not ok else {})}


def parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", required=True, choices=["init", "path", "format", "check", "should-commit", "reconcile", "ledger-check", "verify"],
                   help="verify=run format, check, ledger-check and reconcile in order; ledger-check=validate the requirement "
                        "ledger; check=validate structure, size and the ledger entry; should-commit=validate and decide "
                        "whether the state changed relative to HEAD; reconcile=closing reconciliation")
    p.add_argument("--file", help="Workbook or requirement ledger Markdown file")
    p.add_argument("--ledger", help="verify: override the workbook header's ledger entry (local path)")
    p.add_argument("--dry-run", action="store_true", help="verify: format in memory without writing the workbook")
    p.add_argument("--json", action="store_true", help="verify/ledger-check: print the full JSON")
    p.add_argument("--verbose-warnings", action="store_true", help="verify --json/format: list each historical-time warning")
    p.add_argument("--repo", help="init/path: project path; other modes: absolute path of the Git source repository")
    revision = p.add_mutually_exclusive_group()
    revision.add_argument("--ref", help="Verify the remote and pin a SHA, e.g. origin/main")
    revision.add_argument("--revision", help="40-character SHA already pinned by this operation; not claimed to be latest")
    p.add_argument("--ledger-kind", choices=['standard', 'history'], default='standard')
    p.add_argument("--live", action="store_true", help="reconcile: check through bb thread list that \"in progress\" threads are alive")
    p.add_argument("--max-nonempty-lines", type=int, default=DEFAULT_MAX_NONEMPTY_LINES)
    p.add_argument("--max-line-chars", type=int, default=DEFAULT_MAX_LINE_CHARS)
    p.add_argument("--max-route-items", type=int, default=DEFAULT_MAX_ROUTE_ITEMS)
    p.add_argument("--max-decisions", type=int, default=DEFAULT_MAX_DECISIONS)
    return p


def report_result(args, res):
    if args.json or args.mode not in ("verify", "ledger-check"):
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        steps = res.get("steps", {})
        results = steps.values() if steps else [res]
        errors = [error for result in results for error in result.get("errors", [])]
        problems = sum(len(result.get("problems", [])) for result in results)
        warnings = sum(len(result.get("warnings", [])) for result in results)
        status = "ok" if res["ok"] else f"failed ({res.get('failed_step', args.mode)})"
        summary = f"{args.mode} {status}, {len(errors) + problems} problems, {warnings} warnings"
        if errors:
            summary += ". " + " ".join(errors[0].splitlines())
        print(summary)
    return 0 if res["ok"] else 2


def main():
    cli = parser()
    args = cli.parse_args()
    if (args.ledger is not None or args.dry_run) and args.mode != "verify":
        cli.error("--ledger/--dry-run apply only to verify")
    if args.verbose_warnings and args.mode not in ("format", "verify"):
        cli.error("--verbose-warnings applies only to format/verify")
    if args.ledger_kind != "standard" and args.mode != "ledger-check":
        cli.error("--ledger-kind applies only to ledger-check")
    if args.mode in ("init", "path"):
        if args.file or args.ref or args.revision:
            parser().error("init/path take no --file, --ref or --revision")
        try:
            if args.mode == "path":
                print(workbook_location(args.repo)[0])
            else:
                print(json.dumps(init_workbook(args.repo), ensure_ascii=False, indent=2))
            return 0
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False))
            return 2
    if not args.file:
        parser().error("this mode needs --file")
    if args.mode in ("format", "verify") and (args.repo or args.ref or args.revision):
        cli.error("format/verify accept only a locally edited file; check out the Git source branch first")
    if args.mode == "format":
        try:
            _, res = format_workbook(Path(args.file).expanduser().resolve(),
                                     verbose_warnings=args.verbose_warnings)
        except (OSError, ValueError) as exc:
            res = {"ok": False, "errors": [str(exc)]}
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["ok"] else 2
    fpath = Path(args.file).expanduser()
    if not args.repo and not fpath.is_file():
        return report_result(args, {"ok": False, "file": str(fpath), "errors": [f"File not found: {fpath}"]})
    check_args = {
        "max_nonempty_lines": args.max_nonempty_lines,
        "max_line_chars": args.max_line_chars,
        "max_route_items": args.max_route_items,
        "max_decisions": args.max_decisions,
    }
    if args.mode == "verify":
        res = verify_workbook(fpath.resolve(), args, check_args)
    elif args.repo or args.ref or args.revision:
        try:
            if not args.repo or not Path(args.repo).is_absolute() or not (args.ref or args.revision) or args.mode == 'should-commit':
                raise source.SourceError('A Git source needs --repo and --ref/--revision; should-commit is not supported')
            sha = source.pin(args.repo, args.ref) if args.ref else args.revision
            file = source.relative_path(args.file)

            def read(path):
                return source.read(args.repo, sha, path)

            text = read(file)
            if args.mode == 'check':
                res = check_workbook_source(file, text, read, True, **check_args)
            elif args.mode == 'ledger-check':
                res = check_ledger(text) if args.ledger_kind == 'standard' else {'ok': False, 'applicable': False, 'errors': [HISTORY_NOT_APPLICABLE]}
            else:
                threads = fetch_threads(reconcile_workbook(text)['referenced_threads']) if args.live else None
                res = reconcile_workbook(text, threads=threads)
            res['snapshot'] = {'repo': str(Path(args.repo).resolve()), 'ref': args.ref, 'sha': sha}
        except (source.SourceError, OSError, ValueError, RuntimeError) as exc:
            res = {'ok': False, 'errors': [str(exc)]}
    elif args.mode == "check":
        res = {"file": str(fpath), **check_workbook_file(fpath, **check_args)}
    elif args.mode == "ledger-check":
        try:
            res = check_ledger(fpath.read_text()) if args.ledger_kind == "standard" else {
                "ok": False, "applicable": False, "errors": [HISTORY_NOT_APPLICABLE]}
        except (OSError, ValueError) as exc:
            res = {"ok": False, "errors": [str(exc)]}
        res["file"] = str(fpath)
    elif args.mode == "reconcile":
        text = fpath.read_text()
        threads, warnings = None, []
        if args.live:
            try:
                threads = fetch_threads(reconcile_workbook(text)["referenced_threads"])
            except RuntimeError as exc:
                warnings.append(f"thread check skipped: {exc}")
        res = {"file": str(fpath), **reconcile_workbook(text, threads=threads)}
        if warnings:
            res["warnings"] = warnings
    else:
        res = should_commit_workbook(fpath, check_args)
    return report_result(args, res)


if __name__ == "__main__":
    sys.exit(main())
