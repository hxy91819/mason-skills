#!/usr/bin/env python3
"""BB 管家看门狗：由 BB 脚本 automation 每 30 分钟运行一次，不调模型。

对每个登记的管家：
- 线程归档或已删除：移除登记。
- 在跑、有排队消息、等待交互或有后台活动：跳过。
- 回合失败且没有排队的重试：`bb thread retry`，间隔 0/30/60/120/240/240 分钟，最多 6 次；
  失败满 60 分钟记为需要用户看一眼。恢复后发一次提醒，让管家核对失败期间到达的通知。
- 空闲（回合结束满 10 分钟）：读工作簿跑收尾对账（steward_workbook.reconcile_workbook），有 nudge 级
  问题就把问题行发给管家。同一问题最多发 2 次，同一管家两次催办至少隔 2 小时；发满仍未解决的
  记为需要用户看一眼。

用法：
  steward_watch.py register --workbook <路径> [--ref origin/main] [--name 简称] [--thread thr_x] [--project proj_x]
  steward_watch.py unregister --thread thr_x
  steward_watch.py run [--dry-run]
  steward_watch.py report [--since 60]
  steward_watch.py summary [--days 7] [--json]

登记与运行状态在 ${XDG_STATE_HOME:-~/.local/state}/bb-steward/watch.json（可用 BB_STEWARD_WATCH_STATE
或 --state 改），事件日志在同目录 watch.events.jsonl，超过 2 MB 丢掉较早的一半。首次登记会在当前项目
创建脚本 automation。run 无事可报时不输出，automation 记为静默跳过。
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
except ImportError:  # Windows 没有 fcntl，退回无锁读写。
    fcntl = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
import steward_workbook as sw  # noqa: E402

AUTOMATION_NAME = "管家看门狗（bb-steward）"
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
TAG = "[bb-steward 看门狗]"


class WatchError(Exception):
    pass


class Bb:
    """bb CLI 的薄封装；测试用同接口的假对象替换。"""

    def _run(self, args, stdin=None, timeout=60):
        try:
            res = subprocess.run(["bb", *args, "--json"], input=stdin, capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise WatchError(f"bb {' '.join(args[:2])} 调用失败：{exc}") from exc
        try:
            data = json.loads(res.stdout) if res.stdout.strip() else {}
        except ValueError:
            data = {}
        if res.returncode or (isinstance(data, dict) and data.get("ok") is False):
            error = data.get("error") if isinstance(data, dict) else None
            detail = json.dumps(error, ensure_ascii=False) if error else (res.stderr.strip() or res.stdout.strip())
            raise WatchError(f"bb {' '.join(args[:2])} 失败：{detail[:300]}")
        return data

    def threads(self, ids):
        try:
            return sw.fetch_threads(ids)
        except RuntimeError as exc:
            raise WatchError(str(exc)) from exc

    def children(self, parent):
        try:
            return sw.bb_thread_list("--parent-thread", parent)
        except RuntimeError as exc:
            raise WatchError(str(exc)) from exc

    def tell(self, thread, message):
        self._run(["thread", "tell", thread, "--message-file", "-", "--mode", "queue"], stdin=message)

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


# ---------- 状态与事件 ----------

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
        raise WatchError(f"看门狗状态文件不是 JSON：{path}：{exc}") from exc
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("stewards"), dict):
        raise WatchError(f"看门狗状态文件格式无效：{path}")
    return data


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    tmp.replace(path)


@contextlib.contextmanager
def state_lock(path):
    """串行化登记与运行；拿不到锁说明另一轮还在跑，本轮直接退出。"""
    if fcntl is None:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_name(path.name + ".lock"), "a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise WatchError("另一轮看门狗还在运行") from exc
        yield


def append_events(state_path, events):
    """每行一个 JSON 事件；写入失败只告警，不改变本轮结果。"""
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
        print(f"warning: 看门狗事件写入失败（已旁路忽略）：{exc}", file=sys.stderr)


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


# ---------- 工作簿 ----------

def git(*args, timeout=60):
    return subprocess.run(["git", *args], capture_output=True, text=True, timeout=timeout)


def git_toplevel(path):
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    res = git("-C", str(probe if probe.is_dir() else probe.parent), "rev-parse", "--show-toplevel")
    if res.returncode:
        raise WatchError(f"{path} 不在 git 仓库里：{res.stderr.strip()[:200]}")
    return Path(res.stdout.strip())


def read_workbook(entry):
    """无 ref 读工作区文件；有 ref 先 fetch 再读远端分支上的版本（fetch 失败沿用本地已有的 ref）。"""
    if not entry.get("ref"):
        return Path(entry["workbook"]).read_text()
    remote, _, branch = entry["ref"].partition("/")
    if branch:
        with contextlib.suppress(Exception):
            git("-C", entry["repo"], "fetch", "-q", remote, branch)
    res = git("-C", entry["repo"], "show", f"{entry['ref']}:{entry['path']}")
    if res.returncode:
        raise WatchError(res.stderr.strip()[:200] or "git show 失败")
    return res.stdout


# ---------- 检查一个管家 ----------

def problem_key(problem):
    return f"{problem['kind']}|{problem['label']}"


def hhmm(ts):
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")


def nudge_message(entry, sent, others):
    """sent 是本次计入催办次数的问题；others 只报数量（含还没轮到展示的和不急的）。"""
    where = entry["workbook"] + (f" @ {entry['ref']}" if entry.get("ref") else "")
    lines = [f"{TAG} 工作簿对账有 {len(sent)} 处要处理（{where}）："]
    for p in sent:
        loc = f"第 {p['line']} 行" if p.get("line") else ""
        lines.append(f"- {loc}「{p['label']}」：{p['detail']}")
    if others:
        lines.append(f"- 另有 {others} 处，跑对账命令查看")
    lines.append(
        "按 bb-steward「收尾对账」逐项处理：能推进的现在派出去；确实在等的，把状态写准并提交工作簿。"
        f"状态只用四种：{sw.STATE_HINT}；等用户的行要有“挡住”栏写着它的待办；"
        f"用户待办的原因以{'、'.join(sw.TODO_CATEGORIES)}之一开头。规则在 bb-steward 的 SKILL.md「收尾对账」一节，"
        "没读过这一节先重读。对账命令：steward_workbook.py --mode reconcile --live --file <工作簿>。不用回复看门狗。"
    )
    return "\n".join(lines)


def recovery_message(outage):
    retried = f"看门狗重试了 {outage['retries']} 次，" if outage.get("retries") else ""
    return (f"{TAG} 你的回合从 {hhmm(outage['since'])} 起连续失败，{retried}现在已恢复。"
            "这段时间到达的子线程通知和消息可能没处理：先用 `bb thread log --self` 核对，"
            "再按 bb-steward「收尾对账」继续。不用回复看门狗。")


class Checker:
    def __init__(self, state, state_path, bb, now, dry_run=False):
        self.state = state
        self.state_path = state_path
        self.bb = bb
        self.now = now
        self.dry_run = dry_run
        self.events = []

    def persist(self):
        """副作用（tell/retry）之前先落盘：即使发送后进程中断，也不会下一轮重复催办。"""
        if not self.dry_run:
            save_state(self.state_path, self.state)

    def check(self, tid, entry, info):
        name = entry.get("name") or tid
        if info is None or info["archived"]:
            reason = "线程已删除" if info is None else "线程已归档"
            self.events.append(event(self.now, tid, "unregister", reason=reason))
            return {"result": "unregistered", "remove": True, "report": f"{name}：{reason}，已移除登记"}
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
            notes.append("需要用户看一眼")
        if due:
            outage["retries"] = n + 1
            outage["last_retry"] = self.now
            self.persist()
            ok, err = True, ""
            if not self.dry_run:
                try:
                    self.bb.retry(tid, f"{TAG} 管家回合失败后自动重试（第 {n + 1} 次）")
                except WatchError as exc:
                    ok, err = False, str(exc)
            self.events.append(event(self.now, tid, "retry", attempt=n + 1, ok=ok))
            notes.insert(0, f"已重试第 {n + 1} 次" + ("" if ok else f"（重试失败：{err[:120]}）"))
        if not notes:
            self.events.append(event(self.now, tid, "check", result="failed"))
            return {"result": "failed"}
        return {"result": "failed", "report": f"{name}：回合失败 {minutes:.0f} 分钟，" + "，".join(notes)}

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
                "report": f"{name}：已从回合失败恢复（约 {minutes} 分钟），" + ("已提醒核对失败期间的通知" if ok else "提醒发送失败")}

    def reconcile(self, tid, entry, name):
        try:
            text = read_workbook(entry)
        except Exception as exc:
            problems = [{"kind": "workbook_unreadable", "severity": "nudge", "line": None, "label": "工作簿",
                         "detail": f"读不到工作簿，路径变了就重新登记：{str(exc)[:160]}"}]
        else:
            ids = sw.reconcile_workbook(text, now=datetime.fromtimestamp(self.now))["referenced_threads"]
            threads = self.bb.threads(ids) if ids else {}
            unlisted = 0
            if entry.get("ref"):
                # 远端工作簿可能还没提交新线程 ID：管家另有在跑的子线程时，「线程已停」只记 minor。
                grace = sw.DEFAULT_GRACE_MINUTES * 60
                unlisted = sum(1 for child in self.bb.children(tid)
                               if child["id"] not in threads
                               and sw.thread_state(child, self.now, grace) in ("alive", "recent"))
            problems = sw.reconcile_workbook(text, now=datetime.fromtimestamp(self.now), threads=threads,
                                             unlisted_alive=unlisted)["problems"]

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
                notes.append(f"「{problem['label']}」已催 {record['count']} 次仍未处理，需要用户看一眼")
        # 只发还有额度的问题，且发出去的、计数的、记进 pending 的是同一组。
        sent_keys = [k for k in urgent if tracked[k]["count"] < MAX_NUDGES_PER_PROBLEM][:MESSAGE_MAX_PROBLEMS]
        last = entry.get("last_nudge")
        if sent_keys and (last is None or self.now - last >= MIN_NUDGE_INTERVAL_MINUTES * 60):
            sent = [urgent[k] for k in sent_keys]
            for key in sent_keys:
                tracked[key]["count"] += 1
                tracked[key]["last_nudged"] = self.now
            entry["last_nudge"] = self.now
            entry["pending_nudge"] = {"ts": self.now, "keys": sent_keys}
            self.persist()
            ok = True
            if not self.dry_run:
                try:
                    self.bb.tell(tid, nudge_message(entry, sent, len(problems) - len(sent)))
                except WatchError:
                    ok = False
            labels = [f"{p['label']} {p['detail'][:20]}" for p in sent]
            self.events.append(event(self.now, tid, "nudge", ok=ok, count=len(sent),
                                     problems=[{"kind": p["kind"], "label": p["label"]} for p in sent]))
            notes.insert(0, f"已催（{len(sent)} 处：{'；'.join(labels[:3])}{'…' if len(labels) > 3 else ''}）"
                         + ("" if ok else "，但消息发送失败"))
            return {"result": "nudged", "report": f"{name}：" + "，".join(notes)}
        self.events.append(event(self.now, tid, "check", result="problems", count=len(urgent)))
        return {"result": "problems", "report": f"{name}：" + "，".join(notes) if notes else None}


def run(state, state_path, bb, now=None, dry_run=False):
    now = now if now is not None else time.time()
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
                outcome = {"result": "error", "report": f"{entry.get('name') or tid}：检查出错：{str(exc)[:200]}"}
            if outcome.get("remove"):
                del stewards[tid]
            results[tid] = outcome
    if not dry_run:
        save_state(state_path, state)
        append_events(state_path, checker.events)
    return results, checker.events


# ---------- 登记 ----------

def ensure_automation(state, bb, project, script_path, state_path):
    # 写死状态文件路径：automation 运行时的 HOME/XDG 变量可能和登记时不同。
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
        return {"status": "skipped", "reason": "不在 BB 线程里且没传 --project，未创建 automation"}
    created = bb.automation_create(project, script)
    state["automation"] = {"id": created["id"], "project": project, "script": script}
    return {"id": created["id"], "project": project, "status": "created"}


def main_worktree(top):
    """worktree 会被删掉，远端分支模式记主工作区：git-common-dir 的上一级。"""
    res = git("-C", str(top), "rev-parse", "--path-format=absolute", "--git-common-dir")
    common = Path(res.stdout.strip()) if res.returncode == 0 else None
    return common.parent if common is not None and common.name == ".git" else top


def register(state, bb, thread, workbook, ref=None, name=None, project=None, script_path=None,
             state_path=None, manage_automation=True, now=None):
    if not thread:
        raise WatchError("缺少 --thread，且当前不在 BB 线程里（没有 BB_THREAD_ID）")
    workbook = Path(workbook).expanduser().absolute()
    entry = {"workbook": str(workbook), "registered_at": round(now or time.time(), 3)}
    top = None
    if ref:
        top = git_toplevel(workbook)
        try:
            rel = workbook.resolve().relative_to(top.resolve()).as_posix()
        except ValueError as exc:
            raise WatchError(f"工作簿 {workbook} 不在仓库 {top} 里") from exc
        entry.update(repo=str(main_worktree(top)), path=rel, ref=ref)
        read_workbook(entry)
    elif not workbook.is_file():
        raise WatchError(f"工作簿不存在：{workbook}；工作簿以远端分支为准时传 --ref")
    else:
        with contextlib.suppress(WatchError):
            top = git_toplevel(workbook)
    entry["name"] = name or (top.name if top else workbook.stem)
    previous = state["stewards"].get(thread, {})
    runtime = {k: previous[k] for k in ("problems", "last_nudge", "pending_nudge", "outage") if k in previous}
    state["stewards"][thread] = {**entry, **runtime}
    if not manage_automation:
        automation = {"status": "skipped", "reason": "--no-automation"}
    else:
        automation = ensure_automation(state, bb, project, script_path or Path(__file__).resolve(),
                                       state_path or state_path_from(None))
    return {"thread": thread, **entry, "automation": automation}


# ---------- 汇报与复盘 ----------

RESULT_TEXT = {
    "busy": "管家在跑或有排队消息，跳过",
    "settling": "管家刚结束回合，下轮再看",
    "ok": "对账通过",
    "problems": "对账有问题，还没到再催的时间",
    "failed": "回合失败",
    "nudged": "已催",
    "recovered": "已从失败恢复",
}


def report(state, events, now, since_minutes):
    start = now - since_minutes * 60
    window = [e for e in events if e.get("ts", 0) >= start]
    lines = [f"看门狗记录（{hhmm(start)} 到 {hhmm(now)}，{sum(1 for e in window if e['event'] == 'run')} 轮）"]
    attention = []
    for tid, entry in state["stewards"].items():
        name = entry.get("name") or tid
        evs = [e for e in window if e.get("thread") == tid]
        lines.append(f"- {name}（{tid}，工作簿 {entry['workbook']}" + (f" @ {entry['ref']}" if entry.get("ref") else "") + "）")
        status = [e for e in evs if e["event"] in ("check", "nudge", "retry", "recovered", "error")]
        if status:
            last = status[-1]
            kind = last.get("result") if last["event"] == "check" else {"nudge": "nudged", "retry": "failed"}.get(last["event"], last["event"])
            text = RESULT_TEXT.get(kind or "") or f"检查出错：{last.get('detail', '')}"
            lines.append(f"  最近检查 {hhmm(last['ts'])}：{text}")
        else:
            lines.append("  这段时间没有检查记录")
        for e in evs:
            if e["event"] == "nudge":
                labels = "、".join(f"{p['label']}（{p['kind']}）" for p in e.get("problems", [])[:4])
                lines.append(f"  {hhmm(e['ts'])} 已催 {e.get('count', 0)} 处：{labels}" + ("" if e.get("ok", True) else "，发送失败"))
            elif e["event"] == "nudge_outcome":
                lines.append(f"  {hhmm(e['ts'])} 上次催办后：解决 {e['resolved']} 处，仍在 {e['persisted']} 处")
            elif e["event"] == "retry":
                lines.append(f"  {hhmm(e['ts'])} 回合失败，重试第 {e['attempt']} 次" + ("" if e.get("ok") else "（重试命令失败）"))
            elif e["event"] == "recovered":
                lines.append(f"  {hhmm(e['ts'])} 从失败恢复（约 {e.get('minutes', 0)} 分钟）")
        outage = entry.get("outage")
        if outage and outage.get("escalated"):
            attention.append(f"{name}：回合失败已 {(now - outage['since']) / 60:.0f} 分钟，看门狗已重试 {outage['retries']} 次")
        for key, record in (entry.get("problems") or {}).items():
            if record.get("escalated"):
                kind, _, label = key.partition("|")
                attention.append(f"{name}：「{label}」（{kind}）已催 {record['count']} 次仍未处理")
    for e in window:
        if e["event"] == "unregister":
            lines.append(f"- {e['thread']}：{e.get('reason')}，已移除登记")
    lines.append("需要用户看一眼：" + ("无" if not attention else ""))
    lines += [f"  - {a}" for a in attention]
    return "\n".join(lines)


COUNTED_EVENTS = {"retry": "retries", "outage": "outages", "escalate": "escalations",
                  "unregister": "unregistered", "error": "errors"}


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
    stewards, hooks = {}, []
    for tid, c in per.items():
        name = (state["stewards"].get(tid) or {}).get("name") or tid
        handled = c["resolved"] + c["persisted"]
        share = round(c["resolved"] / handled, 2) if handled else None
        stewards[tid] = {"name": name, **dict(c), "resolve_share": share}
        if c["nudges"] >= SUMMARY_MIN_NUDGES and share is not None and share < SUMMARY_LOW_RESOLVE_SHARE:
            hooks.append({"hook": "nudge_ignored", "thread": tid,
                          "detail": f"{name} 催办后解决率 {share:.0%}（{c['resolved']}/{handled}）：看对账规则是否过严，或管家没读新版收尾对账"})
        if c["outages"] >= SUMMARY_FREQUENT_OUTAGES:
            hooks.append({"hook": "frequent_outage", "thread": tid,
                          "detail": f"{name} {days} 天内回合失败 {c['outages']} 次：查账号额度或模型路由"})
    return {"days": days, "stewards": stewards, "hooks": hooks}


# ---------- CLI ----------

def parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--state", help="状态文件路径，默认见上")
    sub = p.add_subparsers(dest="cmd", required=True)
    reg = sub.add_parser("register", help="登记或更新一个管家，并确保看门狗 automation 存在")
    reg.add_argument("--workbook", required=True, help="工作簿路径；配合 --ref 时可以是工作区里不存在的路径")
    reg.add_argument("--ref", help="工作簿以该远端分支为准，如 origin/main")
    reg.add_argument("--name", help="汇报里用的简称，默认取仓库目录名")
    reg.add_argument("--thread", default=os.environ.get("BB_THREAD_ID"), help="管家线程 ID，默认当前线程")
    reg.add_argument("--project", default=os.environ.get("BB_PROJECT_ID"), help="首次创建 automation 的项目，默认当前项目")
    reg.add_argument("--no-automation", action="store_true", help="只登记，不检查也不创建 automation（测试或手动运行时用）")
    unreg = sub.add_parser("unregister", help="移除一个管家的登记")
    unreg.add_argument("--thread", required=True)
    run_p = sub.add_parser("run", help="检查所有登记的管家（automation 调用）")
    run_p.add_argument("--dry-run", action="store_true", help="只输出判断，不发消息、不重试、不写状态")
    rep = sub.add_parser("report", help="最近一段时间的检查记录与需要用户看一眼的事")
    rep.add_argument("--since", type=int, default=60, help="分钟，默认 60")
    summ = sub.add_parser("summary", help="按天聚合的催办、解决率、重试与复盘提示")
    summ.add_argument("--days", type=int, default=7)
    summ.add_argument("--json", action="store_true")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    path = state_path_from(args.state)
    bb = Bb()
    try:
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
                        print(f"{s['name']}：检查 {s.get('checks', 0)}，催办 {s.get('nudges', 0)}，解决率 {s['resolve_share']}，"
                              f"重试 {s.get('retries', 0)}，失败 {s.get('outages', 0)} 次")
                    for h in res["hooks"]:
                        print(f"复盘提示 {h['hook']}：{h['detail']}")
            return 0
        with state_lock(path):
            state = load_state(path)
            if args.cmd == "register":
                res = register(state, bb, args.thread, args.workbook, args.ref, args.name, args.project,
                               state_path=path, manage_automation=not args.no_automation)
                save_state(path, state)
                append_events(path, [event(time.time(), res["thread"], "register", workbook=res["workbook"])])
                print(json.dumps(res, ensure_ascii=False, indent=2))
            elif args.cmd == "unregister":
                removed = state["stewards"].pop(args.thread, None)
                save_state(path, state)
                if removed:
                    append_events(path, [event(time.time(), args.thread, "unregister", reason="手动移除")])
                print(json.dumps({"thread": args.thread, "removed": bool(removed)}, ensure_ascii=False))
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
        # 已知故障照常退出 0：automation 连续三次失败会自动暂停，看门狗不能因为一次 bb 抖动或磁盘问题停掉。
        print(f"看门狗未完成：{exc}")
        if args.cmd == "run" and not getattr(args, "dry_run", False):
            append_events(path, [event(time.time(), None, "error", detail=str(exc)[:300])])
        return 0 if args.cmd == "run" else 2


if __name__ == "__main__":
    sys.exit(main())
