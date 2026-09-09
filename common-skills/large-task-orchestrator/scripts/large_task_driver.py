#!/usr/bin/env python3
"""确定性 driver：用 BB 线程持续执行 large-task-planning v2 计划。

happy path 不调用任何强模型：脚本选 frontier、领取 Story、通过 bb-dispatch 派 Worker 与 Validator、
等待线程、解析结构化报告、更新计划 JSON 并创建 Git checkpoint。只有异常（Worker 报告 blocked/failed、
Validator 多轮 FAIL、越界写入、线程出错、待处理交互）才派一次性的 strong judge 线程，让它在固定动作集里
选一个。真正需要用户的情况 driver 停下并打印原因。

权威状态在计划 JSON 与 Git；Story.owner 保存 Worker 线程 ID。本地状态文件只缓存阶段、Validator 线程与
尝试计数，丢失后可从计划 JSON 与 BB 线程记录恢复。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PLANNING_SCRIPT = SKILL_DIR.parent / "large-task-planning" / "scripts" / "epic_story.py"
DEFAULT_DISPATCH_SCRIPT = SKILL_DIR.parent / "bb-model-routing" / "scripts" / "bb-dispatch"
STATE_ROOT_RELATIVE = Path(".local/large-task-orchestrator")
STATE_FILENAME = "state.json"
LOG_FILENAME = "log.jsonl"
PID_FILENAME = "driver.pid"
LAST_STOP_FILENAME = "last-stop.txt"
OUTPUT_FILENAME = "driver.out"

DIFFICULTIES = ("simple", "medium", "complex")
WORKER_RESULTS = ("worker_done", "blocked", "failed")
VERDICTS = ("PASS", "FAIL")
JUDGE_ACTIONS = ("retry", "escalate", "patch", "block", "replan", "stop")
THREAD_BUSY = ("pending", "starting", "active", "stopping")
MAX_VALIDATOR_PARSE_FAILURES = 2
HANDOFF_TEXT_LIMIT = 400
HANDOFF_ITEM_LIMIT = 200
HANDOFF_LIST_LIMIT = 8


class DriverError(RuntimeError):
    """driver 自身的契约或环境错误；不是 Story 失败。"""


class DriverStop(RuntimeError):
    """driver 需要停下交给用户；message 是给用户的原因。"""


class DriverAlreadyRunning(DriverError):
    """同一 (repository, plan) 已有存活的 driver。"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def topic_slug(repository: Path, plan_path: Path) -> str:
    """给计划位置生成可读且无碰撞的状态目录名。"""
    try:
        relative = plan_path.parent.parent.relative_to(repository).as_posix()
    except ValueError:
        relative = plan_path.parent.parent.as_posix()
    readable = re.sub(r"[^a-z0-9]+", "-", relative.casefold()).strip("-") or "plan"
    digest = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:10]
    return f"{readable}-{digest}"


def read_pid_record(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("pid"), int):
        return None
    return data


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        # 已退出但尚未被 init 回收的 zombie 不能继续占用计划锁。
        if (Path("/proc") / str(pid) / "stat").read_text(encoding="utf-8").split()[2] == "Z":
            return False
    except OSError:
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def write_pid_record(path: Path, pid: int, *, started_at: str | None = None) -> None:
    record = {"pid": pid, "started_at": started_at or utc_now()}
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def acquire_pid_lock(path: Path) -> None:
    """以 O_EXCL 预占锁，避免两个 start 在校验期间同时通过。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            record = read_pid_record(path)
            if record and process_alive(record["pid"]):
                raise DriverAlreadyRunning(
                    f"该计划的 driver 已在运行：pid={record['pid']}，started_at={record.get('started_at', 'unknown')}。"
                )
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            continue
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "started_at": utc_now()}, handle, ensure_ascii=False)
            handle.write("\n")
        return


def clear_pid_lock(path: Path, pid: int) -> None:
    record = read_pid_record(path)
    if record and record.get("pid") == pid:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


# --------------------------------------------------------------------------- 报告解析


def parse_fields(text: str, keys: Sequence[str]) -> dict[str, str]:
    """解析 `Key: value` 段落；同一 key 之后的续行归入该 key，直到遇到下一个已知 key。"""
    result: dict[str, list[str]] = {}
    current: str | None = None
    pattern = re.compile(r"^\s*(%s)\s*:\s*(.*)$" % "|".join(re.escape(key) for key in keys))
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            current = match.group(1)
            result[current] = [match.group(2).strip()]
        elif current is not None:
            result[current].append(line.rstrip())
    return {key: "\n".join(lines).strip() for key, lines in result.items()}


def parse_worker_report(text: str) -> dict[str, str] | None:
    fields = parse_fields(text, ("Result", "Changed", "Verified", "Remaining", "Handoff"))
    result = fields.get("Result", "").split()[0].strip("`") if fields.get("Result") else ""
    if result not in WORKER_RESULTS:
        return None
    fields["Result"] = result
    return fields


def parse_validator_report(text: str) -> dict[str, Any] | None:
    fields = parse_fields(text, ("Verdict", "Acceptance", "Gaps", "New facts"))
    verdict = fields.get("Verdict", "").split()[0].strip("`") if fields.get("Verdict") else ""
    if verdict not in VERDICTS:
        return None
    holds: dict[str, str] = {}
    for line in fields.get("Acceptance", "").splitlines():
        match = re.match(r"^\s*-\s*(AC-\d+)\s*:\s*(holds|missing)\b\s*(.*)$", line)
        if match:
            holds[match.group(1)] = match.group(2)
    return {"verdict": verdict, "acceptance": holds, "gaps": fields.get("Gaps", ""),
            "new_facts": fields.get("New facts", ""), "raw": text}


def parse_judge_report(text: str) -> dict[str, str] | None:
    fields = parse_fields(text, ("Action", "Note"))
    action = fields.get("Action", "").split()[0].strip("`").lower() if fields.get("Action") else ""
    if action not in JUDGE_ACTIONS:
        return None
    return {"action": action, "note": fields.get("Note", "")}


def split_items(text: str) -> list[str]:
    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower() == "none":
            continue
        items.append(line.lstrip("-* ").strip())
    return items


def limit_text(text: str, limit: int) -> str:
    value = text.strip()
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def limited_items(text: str) -> list[str]:
    return [limit_text(item, HANDOFF_ITEM_LIMIT) for item in split_items(text)[:HANDOFF_LIST_LIMIT]]


# --------------------------------------------------------------------------- 外部命令


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def run(command: Sequence[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(list(command), cwd=cwd, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        raise DriverError(f"命令失败 ({result.returncode}): {' '.join(command)}\n{result.stderr.strip()}")
    return result


def run_json(command: Sequence[str], *, cwd: Path | None = None) -> Any:
    result = run(command, cwd=cwd)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise DriverError(f"命令未返回 JSON: {' '.join(command)}\n{result.stdout[:500]}") from error


# --------------------------------------------------------------------------- 状态


@dataclass
class StoryState:
    phase: str = "working"  # working | validating
    difficulty: str = ""
    worker_thread: str | None = None
    validator_thread: str | None = None
    attempts: int = 0
    patch_rounds: int = 0
    thread_retries: int = 0
    validator_parse_failures: int = 0
    judge_rounds: int = 0
    baseline_commit: str = ""
    baseline_dirty: list[str] = field(default_factory=list)
    last_worker: dict[str, str] = field(default_factory=dict)
    last_validator: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StoryState":
        known = {name for name in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in data.items() if key in known})

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase, "difficulty": self.difficulty, "worker_thread": self.worker_thread,
            "validator_thread": self.validator_thread, "attempts": self.attempts,
            "patch_rounds": self.patch_rounds, "thread_retries": self.thread_retries,
            "validator_parse_failures": self.validator_parse_failures,
            "judge_rounds": self.judge_rounds, "baseline_commit": self.baseline_commit,
            "baseline_dirty": self.baseline_dirty, "last_worker": self.last_worker,
            "last_validator": self.last_validator,
        }


class Driver:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.repository = Path(args.repository).resolve()
        self.plan_path = Path(args.plan).resolve()
        self.stories_dir = Path(args.stories_dir).resolve()
        self.topic_dir = self.plan_path.parent.parent
        self.planning_script = Path(args.planning_script).resolve()
        self.dispatch = self._resolve_dispatch(args.dispatch)
        self.state_dir = self.repository / STATE_ROOT_RELATIVE / topic_slug(self.repository, self.plan_path)
        self.state_path = self.state_dir / STATE_FILENAME
        self.log_path = self.state_dir / LOG_FILENAME
        self.pid_path = self.state_dir / PID_FILENAME
        self.last_stop_path = self.state_dir / LAST_STOP_FILENAME
        self.output_path = self.state_dir / OUTPUT_FILENAME
        self.state: dict[str, Any] = self._load_state()
        self.stop_requested = False

    # ----------------------------------------------------------------- 基础设施

    @staticmethod
    def _resolve_dispatch(value: str | None) -> list[str]:
        if value:
            return [value]
        found = shutil.which("bb-dispatch")
        if found:
            return [found]
        if DEFAULT_DISPATCH_SCRIPT.exists():
            return [sys.executable, str(DEFAULT_DISPATCH_SCRIPT)]
        raise DriverError("找不到 bb-dispatch；用 --dispatch 指定路径。")

    def _load_state(self) -> dict[str, Any]:
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data.setdefault("plan_path", str(self.plan_path))
                    data.setdefault("stories", {})
                    return data
            except json.JSONDecodeError:
                pass
        return {"kind": "large-task-driver-state", "plan_path": str(self.plan_path), "stories": {}}

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".driver-state.", dir=self.state_path.parent)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(self.state, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, self.state_path)

    def clear_last_stop(self) -> None:
        try:
            self.last_stop_path.unlink()
        except FileNotFoundError:
            pass

    def write_last_stop(self, reason: str) -> None:
        self.last_stop_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".last-stop.", dir=self.last_stop_path.parent)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"{utc_now()}\n{reason.strip()}\n")
        os.replace(temporary, self.last_stop_path)

    def story_state(self, story_id: str) -> StoryState:
        return StoryState.from_dict(self.state["stories"].get(story_id, {}))

    def set_story_state(self, story_id: str, state: StoryState | None) -> None:
        if state is None:
            self.state["stories"].pop(story_id, None)
        else:
            self.state["stories"][story_id] = state.to_dict()
        self._save_state()

    def log(self, event: str, **facts: Any) -> None:
        record = {"at": utc_now(), "event": event, **facts}
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as error:  # 记录失败只告警
            print(f"WARN: 写入 driver 日志失败: {error}", file=sys.stderr)
        print(f"[{record['at']}] {event} " + " ".join(f"{k}={v}" for k, v in facts.items() if k != "text"))

    def planning(self, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = run([sys.executable, str(self.planning_script), *arguments], check=False)
        if result.returncode != expected:
            raise DriverError(f"epic_story.py {arguments[0]} 失败 ({result.returncode}):\n{result.stderr.strip()}")
        return result

    def project_args(self) -> list[str]:
        return ["--plan", str(self.plan_path), "--stories-dir", str(self.stories_dir)]

    def git(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return run(["git", *arguments], cwd=self.repository, check=check)

    def bb(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return run(["bb", *arguments], cwd=self.repository, check=check)

    def bb_json(self, *arguments: str) -> Any:
        return run_json(["bb", *arguments, "--json"], cwd=self.repository)

    def validate_dispatch(self) -> None:
        command = [*self.dispatch, "--difficulty", self.args.default_difficulty,
                   "--kind", "debug" if self.args.kind == "debug" else "general",
                   "--task", "校验 large-task driver 路由；不创建线程。", "--dry-run"]
        if self.args.environment:
            command += ["--environment", self.args.environment]
        run_json(command, cwd=self.repository)

    def request_stop(self) -> None:
        self.stop_requested = True

    # ----------------------------------------------------------------- 计划读写

    def status(self) -> dict[str, Any]:
        return json.loads(self.planning("status", *self.project_args(), "--json").stdout)

    def check(self) -> None:
        self.planning("check", *self.project_args())

    def story_path(self, story_id: str) -> Path:
        matches = [path for path in sorted(self.stories_dir.glob("*.json"))
                   if json.loads(path.read_text(encoding="utf-8")).get("id") == story_id]
        if len(matches) != 1:
            raise DriverError(f"Story 文件不唯一或不存在: {story_id}")
        return matches[0]

    def read_story(self, story_id: str) -> dict[str, Any]:
        return json.loads(self.story_path(story_id).read_text(encoding="utf-8"))

    def write_story(self, story_id: str, data: dict[str, Any]) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            temporary = handle.name
        try:
            self.planning("write", "--file", str(self.story_path(story_id)), "--from", temporary)
        finally:
            os.unlink(temporary)

    def brief(self, story_id: str) -> str:
        return self.planning("brief", *self.project_args(), "--story", story_id).stdout

    def transition(self, story_id: str, status: str, *, expect: str | None = None,
                   owner: str | None = None, blocker: str | None = None) -> None:
        arguments = ["transition", "--story", str(self.story_path(story_id)), "--status", status]
        if expect:
            arguments += ["--expect", expect]
        if owner:
            arguments += ["--owner", owner]
        if blocker:
            arguments += ["--blocker", blocker]
        self.planning(*arguments)

    # ----------------------------------------------------------------- Git 事实

    def dirty_paths(self) -> list[str]:
        output = self.git("status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
        records = output.split("\0")
        paths: list[str] = []
        index = 0
        while index < len(records):
            record = records[index]
            index += 1
            if not record:
                continue
            paths.append(record[3:])
            # Porcelain v1 puts the original path after a rename/copy record.
            if len(record) >= 2 and (record[0] in "RC" or record[1] in "RC"):
                index += 1
        return paths

    def head(self) -> str:
        return self.git("rev-parse", "HEAD").stdout.strip()

    def story_changes(self, state: StoryState) -> list[str]:
        baseline = set(state.baseline_dirty)
        return [path for path in self.dirty_paths() if path not in baseline]

    @staticmethod
    def path_within(path: str, boundary: str) -> bool:
        normalized = boundary.strip().strip("/")
        if not normalized or normalized == ".":
            return normalized == "."
        if boundary.rstrip().endswith("/"):
            return path.startswith(normalized + "/")
        return path == normalized or path.startswith(normalized + "/")

    def management_paths(self, story_id: str) -> list[str]:
        topic = os.path.relpath(self.topic_dir, self.repository)
        prefix = "" if topic == "." else f"{topic}/"
        return [
            os.path.relpath(self.story_path(story_id), self.repository),
            f"{prefix}SPEC.md",
            f"{prefix}STATUS.md",
        ]

    def is_driver_management_path(self, path: str) -> bool:
        """忽略并行 driver 的投影，避免把它们的状态转换算进业务改动。"""
        candidate = (self.repository / path).resolve()
        state_root = self.repository / STATE_ROOT_RELATIVE
        for state_path in state_root.glob("*/" + STATE_FILENAME):
            try:
                cached = json.loads(state_path.read_text(encoding="utf-8"))
                plan_value = cached.get("plan_path") if isinstance(cached, dict) else None
                plan_path = Path(str(plan_value)).resolve()
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            topic = plan_path.parent.parent
            stories = topic / "agent" / "stories"
            if candidate in (plan_path, topic / "SPEC.md", topic / "STATUS.md"):
                return True
            try:
                candidate.relative_to(stories)
            except ValueError:
                continue
            return True
        return False

    def implementation_changes(self, story_id: str, state: StoryState) -> list[str]:
        management = set(self.management_paths(story_id))
        return [path for path in self.story_changes(state)
                if path not in management and not self.is_driver_management_path(path)]

    @staticmethod
    def path_scopes(scopes: Sequence[str]) -> list[str]:
        prefixes: list[str] = []
        for scope in scopes:
            for token in re.split(r"[\s,，、;；]+", scope):
                candidate = token.strip("`'\"。:：()（）[]{}")
                if candidate.startswith("./"):
                    candidate = candidate[2:]
                candidate = candidate.rstrip("*")
                if "/" in candidate or re.fullmatch(r"[A-Za-z0-9_.-]+\.[A-Za-z0-9_-]+", candidate):
                    prefixes.append(candidate)
        return prefixes

    def out_of_scope(self, story: dict[str, Any], changes: list[str]) -> list[str]:
        scopes = [scope.strip() for scope in story.get("context", {}).get("write_scope", []) if scope.strip()]
        topic = os.path.relpath(self.topic_dir, self.repository)
        allowed_prefixes = [topic, ".local/"]
        offenders = []
        for path in changes:
            if any(self.path_within(path, prefix) for prefix in allowed_prefixes):
                continue
            # 只从 write_scope 中提取明确的路径 token，文字性边界留给 judge 裁决。
            if any(self.path_within(path, prefix) for prefix in self.path_scopes(scopes)):
                continue
            offenders.append(path)
        return offenders

    def checkpoint(self, story_id: str, state: StoryState) -> str:
        baseline = set(state.baseline_dirty)
        candidates = [*self.implementation_changes(story_id, state), *self.management_paths(story_id)]
        targets = list(dict.fromkeys(
            path for path in candidates if path not in baseline and not self.path_within(path, ".local/")
        ))
        if not targets:
            return self.head()
        self.git("add", "--", *targets)
        staged = self.git("diff", "--cached", "--quiet", "--", *targets, check=False)
        if staged.returncode == 0:
            return self.head()
        # --only keeps another agent's pre-existing index entries out of this checkpoint.
        self.git("commit", "-q", "--only", "-m", f"checkpoint({story_id}): {self.read_story(story_id)['title']}",
                 "--", *targets)
        return self.head()

    # ----------------------------------------------------------------- BB 线程

    def dispatch_thread(self, *, difficulty: str, kind: str, title: str, task: str) -> str:
        command = [*self.dispatch, "--difficulty", difficulty, "--kind", kind, "--title", title, "--task", task]
        if self.args.environment:
            command += ["--environment", self.args.environment]
        payload = run_json(command, cwd=self.repository)
        receipt = payload.get("result") or {}
        thread_id = ((receipt.get("thread") or {}).get("id") or receipt.get("id"))
        if not thread_id:
            raise DriverError(f"bb-dispatch 未返回线程 ID: {json.dumps(payload, ensure_ascii=False)[:500]}")
        selection = payload.get("selection", {})
        self.log("thread.spawned", thread=thread_id, difficulty=difficulty, kind=kind,
                 provider=selection.get("provider"), model=selection.get("model"), title=title)
        return thread_id

    def thread_status(self, thread_id: str) -> dict[str, Any]:
        payload = self.bb_json("thread", "show", thread_id)
        return payload.get("thread") or payload

    def thread_output(self, thread_id: str) -> str:
        payload = self.bb_json("thread", "output", thread_id)
        return str(payload.get("output") or "")

    def thread_interactions(self, thread_id: str) -> list[dict[str, Any]]:
        payload = self.bb_json("thread", "interactions", "list", thread_id)
        return [item for item in (payload if isinstance(payload, list) else payload.get("interactions", []))
                if item.get("status", "pending") == "pending"]

    def wait_thread(self, thread_id: str) -> str:
        """阻塞到线程 idle / error / 有待处理交互；返回 idle | error | interaction | busy。"""
        started = time.monotonic()
        timeout = min(self.args.poll_seconds, self.args.wait_timeout)
        if timeout <= 0:
            raise DriverError("--poll-seconds 与 --wait-timeout 必须为正整数。")
        result = self.bb("thread", "wait", thread_id, "--timeout", str(timeout), check=False)
        status = str(self.thread_status(thread_id).get("status") or "")
        if status == "idle":
            return "idle"
        if status == "error":
            return "error"
        if self.thread_interactions(thread_id):
            return "interaction"
        if status not in THREAD_BUSY:
            raise DriverError(f"线程 {thread_id} 处于未知状态: {status!r}")
        if result.returncode not in (0, 2):
            raise DriverError(f"bb thread wait 失败 ({result.returncode}): {result.stderr.strip()}")
        # BB 在 timeout 时以退出码 2 返回；补足过快返回的间隔，使主循环不会忙等。
        remaining = timeout - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(remaining)
        return "busy"

    def tell_thread(self, thread_id: str, message: str) -> None:
        self.bb("thread", "tell", thread_id, message, "--mode", "auto")
        self.log("thread.told", thread=thread_id, chars=len(message))

    # ----------------------------------------------------------------- 任务文本

    def repo_context(self) -> str:
        parts = [f"仓库根目录：{self.repository}", f"当前 HEAD：{self.head()}"]
        rules = self.repository / "AGENTS.md"
        if rules.exists():
            parts.append(f"仓库规则文件：{rules}（先读它）")
        if self.args.context:
            parts.append(self.args.context)
        return "\n".join(parts)

    def worker_task(self, story_id: str, story: dict[str, Any], brief: str, *, resume_note: str = "") -> str:
        scope = "\n".join(f"- {item}" for item in story.get("context", {}).get("write_scope", [])) or "- （计划未限定）"
        return f"""你是 Story {story_id} 的 Worker，一次只实现这一张 Story。不要修改计划 JSON、SPEC.md、STATUS.md，不要提交或推送，不要派生其他线程。

{self.repo_context()}

只允许修改这些区域（write scope）：
{scope}

工作区可能有他人并发改动：保留它们，不要回滚或格式化无关文件。

执行方式：先验证现状，在执行包指定的公开测试 seam 上按 red → green 的纵向小循环实现，每一步跑相关测试。Acceptance 全部成立才算完成；做不到就如实报告 blocked 或 failed，不要放宽验收。
{resume_note}
执行包（来自计划）：
```json
{brief}
```

最终回复只包含下面这段，字段顺序固定，不加其他内容：

Result: worker_done | blocked | failed
Changed: <可观察结果和文件，最多 8 行>
Verified: <运行过的命令与结果，最多 8 行>
Remaining: <未完成工作或 none>
Handoff: <替换 Worker 或下一张 Story 需要的事实，最多 400 字符>
"""

    def validator_task(self, story_id: str, story: dict[str, Any], brief: str, state: StoryState) -> str:
        acceptance = "\n".join(f"- {item['id']}: {item['criterion']}" for item in story["acceptance"])
        changes = "\n".join(f"- {path}" for path in self.story_changes(state)) or "- （无未提交改动）"
        worker = state.last_worker
        return f"""你是 Story {story_id} 的 Validator。你没有参与实现；只读，不修改任何文件，不提交。可以运行测试与验收命令。

{self.repo_context()}
本 Story 开始时的基线 commit：{state.baseline_commit}
本 Story 的未提交改动：
{changes}

Worker 报告：
Changed: {worker.get('Changed', '')}
Verified: {worker.get('Verified', '')}

任务：逐条核对下面每项 Acceptance 是否真正成立，以工作区、命令输出和黄金案例为准，Worker 报告不是证据。不做代码审查、风格或重构建议。

Acceptance：
{acceptance}

执行包（来自计划）：
```json
{brief}
```

最终回复只包含下面这段：

Verdict: PASS | FAIL
Acceptance:
- AC-01: holds | missing — <命令或观察证据>
Gaps: <遗漏、越界或与黄金案例冲突的事实；none>
New facts: <推翻后续 Story 前提或计划假设的发现；none>
"""

    def judge_task(self, story_id: str, story: dict[str, Any], state: StoryState, situation: str) -> str:
        return f"""你是 large-task driver 的 judge。driver 是确定性脚本，遇到它无法判断的情况时派你做一次决定。你只回答一个动作，不实现代码。

{self.repo_context()}
计划：{self.plan_path}
Story：{story_id} — {story['title']}
Story 文件：{self.story_path(story_id)}
Worker 线程：{state.worker_thread}（difficulty={state.difficulty}，attempts={state.attempts}，patch_rounds={state.patch_rounds}）
Validator 线程：{state.validator_thread}
基线 commit：{state.baseline_commit}

情况：
{situation}

最近的 Worker 报告：
{json.dumps(state.last_worker, ensure_ascii=False, indent=2)}

最近的 Validator 报告：
{json.dumps({k: v for k, v in state.last_validator.items() if k != 'raw'}, ensure_ascii=False, indent=2)}

可用命令：`bb thread show/output/log <id>`、`git status --short`、`git diff --stat`、
`python3 {self.planning_script} status|brief ...`。需要看细节时自己去看，但不要读超过必要的内容。

可选动作（只能选一个）：
- retry：换一个同难度的 fresh Worker 重做（原因是环境、配额、session 或线程本身，而不是能力）。
- escalate：换一个更高难度档的 fresh Worker（原因是实现能力不够；当前 {state.difficulty}）。
- patch：把 Note 作为修复提示发回同一 Worker 线程（遗漏明确且小）。
- block：把 Story 标记为 blocked，Note 写具体 blocker；driver 会继续其他 ready Story。
- replan：你已经用 `python3 {self.planning_script} write/transition` 修改了计划（插入、拆分、改写未开始的 Story，保留既有 ID，Outcome/Acceptance 变化时递增 intent_version），Note 说明改了什么；driver 会重新校验计划并继续。
- stop：必须由用户决定（缺凭据或权限、破坏性或外部动作、显著成本、改变 Goal/黄金判据/用户边界、无法协调的并发冲突）。Note 写证据、已尝试的恢复、影响范围和一个最小决策问题。

线程正在等待交互时，你可以用 `bb thread interactions list/show/approve/answer/deny` 处理属于计划已授权范围内的交互，处理后选 retry 之外的 `patch`（Note 写 "interaction handled"）让 driver 继续等待；越权的交互选 stop。

最终回复只包含：

Action: retry | escalate | patch | block | replan | stop
Note: <给 driver 或用户的说明>
"""

    # ----------------------------------------------------------------- Story 生命周期

    def claim_and_dispatch(self, story_id: str, *, difficulty: str | None = None, resume_note: str = "") -> StoryState:
        story = self.read_story(story_id)
        state = self.story_state(story_id)
        state.difficulty = difficulty or state.difficulty or self.args.default_difficulty
        if not state.baseline_commit:
            state.baseline_commit = self.head()
            state.baseline_dirty = self.dirty_paths()
        brief = self.brief(story_id)
        thread_id = self.dispatch_thread(
            difficulty=state.difficulty, kind="debug" if self.args.kind == "debug" else "general",
            title=f"{story_id} worker", task=self.worker_task(story_id, story, brief, resume_note=resume_note))
        state.worker_thread = thread_id
        state.validator_thread = None
        state.phase = "working"
        state.attempts += 1
        state.patch_rounds = 0
        state.thread_retries = 0
        state.validator_parse_failures = 0
        if story["status"] == "todo":
            self.transition(story_id, "in_progress", expect="todo", owner=thread_id)
        else:
            self.transition(story_id, "in_progress", owner=thread_id)
        self.set_story_state(story_id, state)
        self.log("story.dispatched", story=story_id, thread=thread_id, difficulty=state.difficulty, attempt=state.attempts)
        return state

    def dispatch_validator(self, story_id: str, state: StoryState) -> None:
        story = self.read_story(story_id)
        thread_id = self.dispatch_thread(
            difficulty="simple", kind="test", title=f"{story_id} validator",
            task=self.validator_task(story_id, story, self.brief(story_id), state))
        state.validator_thread = thread_id
        state.phase = "validating"
        self.set_story_state(story_id, state)

    def needs_validator(self, state: StoryState) -> bool:
        if self.args.validator == "always":
            return True
        return state.difficulty != "simple"

    def complete_story(self, story_id: str, state: StoryState) -> None:
        story = self.read_story(story_id)
        worker = state.last_worker
        validator = state.last_validator
        for item in story["acceptance"]:
            item["passed"] = True
        verification = limited_items(worker.get("Verified", ""))
        if validator:
            verification += [limit_text(
                f"Validator {state.validator_thread}: {validator['verdict']}; "
                + "; ".join(f"{k} {v}" for k, v in validator.get("acceptance", {}).items()),
                HANDOFF_ITEM_LIMIT,
            )]
        else:
            verification.append(f"Validator skipped (difficulty={state.difficulty}); worker evidence accepted by driver")
        risks = limited_items(validator.get("new_facts", "")) if validator else []
        thread_fact = f"线程: worker={state.worker_thread}, validator={state.validator_thread}"
        next_text = worker.get("Handoff", "").strip() or "读取下一张 Story。"
        next_text = limit_text(next_text, HANDOFF_TEXT_LIMIT - len(thread_fact) - 1)
        story["handoff"] = {
            "summary": limit_text(worker.get("Changed", "").strip() or story["outcome"], HANDOFF_TEXT_LIMIT),
            "verification": (verification or [f"worker thread {state.worker_thread}"])[:HANDOFF_LIST_LIMIT],
            "remaining": [],
            "risks": risks,
            "next": f"{next_text}\n{thread_fact}",
        }
        story["status"] = "in_progress"
        self.write_story(story_id, story)
        self.transition(story_id, "done", expect="in_progress", owner=state.worker_thread or "driver")
        self.check()
        commit = self.checkpoint(story_id, state)
        self.set_story_state(story_id, None)
        self.log("story.done", story=story_id, commit=commit, attempts=state.attempts, patch_rounds=state.patch_rounds)

    def block_story(self, story_id: str, reason: str) -> None:
        self.transition(story_id, "blocked", blocker=reason)
        self.set_story_state(story_id, None)
        self.log("story.blocked", story=story_id, reason=reason[:200])

    # ----------------------------------------------------------------- 异常 → judge

    def consult_judge(self, story_id: str, state: StoryState, situation: str) -> None:
        state.judge_rounds += 1
        self.set_story_state(story_id, state)
        if state.judge_rounds > self.args.max_judge_rounds:
            raise DriverStop(f"{story_id}: judge 已介入 {state.judge_rounds - 1} 次仍未收敛。最近情况：{situation}")
        story = self.read_story(story_id)
        thread_id = self.dispatch_thread(difficulty="complex", kind="general", title=f"{story_id} judge",
                                         task=self.judge_task(story_id, story, state, situation))
        outcome = self.wait_thread(thread_id)
        while outcome == "busy":
            outcome = self.wait_thread(thread_id)
        if outcome != "idle":
            raise DriverStop(f"{story_id}: judge 线程 {thread_id} 未正常结束（{outcome}）。情况：{situation}")
        report = parse_judge_report(self.thread_output(thread_id))
        if report is None:
            raise DriverStop(f"{story_id}: judge 线程 {thread_id} 的回复无法解析。情况：{situation}")
        self.log("judge.decided", story=story_id, thread=thread_id, action=report["action"], note=report["note"][:200])
        self.apply_judge(story_id, state, report)

    def apply_judge(self, story_id: str, state: StoryState, report: dict[str, str]) -> None:
        action, note = report["action"], report["note"]
        if action == "stop":
            raise DriverStop(f"{story_id}: 需要用户决定。\n{note}")
        if action == "block":
            self.block_story(story_id, note or "judge 标记为 blocked")
            return
        if action == "replan":
            self.check()
            self.set_story_state(story_id, None)
            return
        if action == "patch":
            if not state.worker_thread:
                raise DriverError(f"{story_id}: judge 选择 patch，但没有可接收提示的 Worker 线程。")
            if note.strip().lower() != "interaction handled":
                self.tell_thread(state.worker_thread, f"修复提示（来自 judge）：\n{note}\n\n修完后按原报告格式回复。")
            state.phase = "working"
            state.patch_rounds += 1
            self.set_story_state(story_id, state)
            return
        if action in ("retry", "escalate"):
            difficulty = state.difficulty
            if action == "escalate":
                index = DIFFICULTIES.index(difficulty)
                if index + 1 >= len(DIFFICULTIES):
                    raise DriverStop(f"{story_id}: 已是最高难度档仍失败，需要拆分或用户决定。\n{note}")
                difficulty = DIFFICULTIES[index + 1]
            if state.attempts >= self.args.max_attempts:
                raise DriverStop(f"{story_id}: Worker 已尝试 {state.attempts} 次。\n{note}")
            self.claim_and_dispatch(story_id, difficulty=difficulty,
                                    resume_note=f"\n这是第 {state.attempts + 1} 次尝试。上一轮事实：{json.dumps(state.last_worker, ensure_ascii=False)}\njudge 说明：{note}\n")

    # ----------------------------------------------------------------- 主循环

    def step_story(self, story_id: str) -> bool:
        """推进一张 in_progress Story 一步；返回 True 表示本步有进展（不含单纯等待）。"""
        state = self.story_state(story_id)
        story = self.read_story(story_id)
        if not state.worker_thread:
            owner = story.get("owner")
            if owner and owner.startswith("thr_"):
                state.worker_thread = owner
                state.baseline_commit = state.baseline_commit or self.head()
                self.set_story_state(story_id, state)
            else:
                self.claim_and_dispatch(story_id, resume_note="\n此 Story 之前已领取但线程丢失；先核对工作区已有改动。\n")
                return True
        thread_id = state.validator_thread if state.phase == "validating" else state.worker_thread
        assert thread_id
        outcome = self.wait_thread(thread_id)
        if outcome == "busy":
            return False
        if outcome == "interaction":
            pending = self.thread_interactions(thread_id)
            self.consult_judge(story_id, state, f"线程 {thread_id} 正在等待交互：{json.dumps(pending, ensure_ascii=False)[:1500]}")
            return True
        if outcome == "error":
            if state.thread_retries < 1:
                state.thread_retries += 1
                self.set_story_state(story_id, state)
                self.bb("thread", "retry", thread_id, check=False)
                self.log("thread.retried", story=story_id, thread=thread_id)
                return True
            if state.phase == "validating":
                self.dispatch_validator(story_id, state)
                return True
            self.consult_judge(story_id, state, f"Worker 线程 {thread_id} 重试后仍处于 error。")
            return True
        output = self.thread_output(thread_id)
        if state.phase == "working":
            return self.handle_worker_output(story_id, story, state, output)
        return self.handle_validator_output(story_id, state, output)

    def handle_worker_output(self, story_id: str, story: dict[str, Any], state: StoryState, output: str) -> bool:
        report = parse_worker_report(output)
        if report is None:
            self.consult_judge(story_id, state, f"Worker 回复无法按契约解析：\n{output[-1500:]}")
            return True
        state.last_worker = report
        self.set_story_state(story_id, state)
        self.log("worker.reported", story=story_id, thread=state.worker_thread, result=report["Result"])
        if report["Result"] != "worker_done":
            self.consult_judge(story_id, state, f"Worker 报告 {report['Result']}。")
            return True
        changes = self.implementation_changes(story_id, state)
        offenders = self.out_of_scope(story, changes)
        if offenders:
            self.consult_judge(story_id, state, f"Worker 修改了 write scope 之外的路径：{offenders}")
            return True
        if not changes and not self.args.allow_empty_story:
            self.consult_judge(story_id, state, "Worker 报告完成，但工作区没有任何新改动。")
            return True
        if self.needs_validator(state):
            self.dispatch_validator(story_id, state)
        else:
            self.complete_story(story_id, state)
        return True

    def handle_validator_output(self, story_id: str, state: StoryState, output: str) -> bool:
        report = parse_validator_report(output)
        if report is None:
            state.validator_parse_failures += 1
            self.set_story_state(story_id, state)
            if state.validator_parse_failures > MAX_VALIDATOR_PARSE_FAILURES:
                self.consult_judge(
                    story_id, state,
                    f"Validator 已有 {state.validator_parse_failures} 次回复无法按契约解析：\n{output[-1500:]}",
                )
                return True
            self.dispatch_validator(story_id, state)
            self.log("validator.unparsable", story=story_id, thread=state.validator_thread,
                     failures=state.validator_parse_failures)
            return True
        state.last_validator = report
        state.validator_parse_failures = 0
        self.set_story_state(story_id, state)
        self.log("validator.reported", story=story_id, thread=state.validator_thread, verdict=report["verdict"])
        if report["verdict"] == "PASS" and "missing" not in report["acceptance"].values():
            self.complete_story(story_id, state)
            return True
        if state.patch_rounds < self.args.max_patch_rounds and state.worker_thread:
            state.patch_rounds += 1
            state.phase = "working"
            self.set_story_state(story_id, state)
            missing = [key for key, value in report["acceptance"].items() if value == "missing"]
            self.tell_thread(state.worker_thread,
                             f"Validator 判定未完成。未成立的 Acceptance：{', '.join(missing) or '见 Gaps'}\n"
                             f"Gaps：\n{report['gaps']}\n\n只修这些遗漏，修完后按原报告格式回复。")
            return True
        self.consult_judge(story_id, state, f"Validator 连续 {state.patch_rounds + 1} 轮 FAIL。Gaps：{report['gaps']}")
        return True

    def run_once(self) -> str:
        """执行一轮；返回 progress | waiting | complete | idle。"""
        self.check()
        status = self.status()
        in_progress = [s["id"] for s in status["stories"] if s["status"] == "in_progress"]
        if in_progress:
            progressed = any(self.step_story(story_id) for story_id in in_progress)
            return "progress" if progressed else "waiting"
        if status["plan"]["completed"] == status["plan"]["total"]:
            return "complete"
        ready = status.get("ready") or []
        if not ready:
            return "idle"
        self.claim_and_dispatch(ready[0])
        return "progress"

    def finish(self) -> None:
        self.planning("completion-check", *self.project_args())
        if self.args.push:
            self.git("push")
            local, remote = self.head(), self.git("rev-parse", "@{upstream}").stdout.strip()
            if local != remote:
                raise DriverStop(f"推送后远端 HEAD {remote} 不等于本地 {local}。")
            self.log("delivered", commit=local, pushed=True)
        else:
            self.log("delivered", commit=self.head(), pushed=False)

    def run(self) -> int:
        stories_done = 0
        try:
            while True:
                outcome = self.run_once()
                if self.stop_requested:
                    raise DriverStop("收到 stop 请求；当前 run_once 已结束，保留 in_progress Story 供下次接回。")
                if outcome == "complete":
                    self.finish()
                    self.clear_last_stop()
                    print("DONE: 全部 Story 完成。")
                    return 0
                if outcome == "idle":
                    status = self.status()
                    blocked = [f"{s['id']}: {s['blocker']}" for s in status["stories"] if s["status"] == "blocked"]
                    reason = "没有可推进的 Story。\n" + "\n".join(blocked)
                    self.log("driver.stopped", reason=reason[:500])
                    self.write_last_stop(reason)
                    print("STOP: " + reason, file=sys.stderr)
                    return 3
                if outcome == "progress":
                    stories_done = self.status()["plan"]["completed"]
                if self.args.once:
                    print(f"ONCE: {outcome}; completed={stories_done}")
                    return 0
                if self.args.max_stories and stories_done >= self.args.max_stories:
                    print(f"LIMIT: 已完成 {stories_done} 张 Story，达到 --max-stories。")
                    return 0
        except DriverStop as stop:
            self.log("driver.stopped", reason=str(stop)[:500])
            self.write_last_stop(str(stop))
            print(f"STOP: {stop}", file=sys.stderr)
            return 3


# --------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="用 BB 线程持续执行 large-task-planning v2 计划的确定性 driver。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码：0 完成或本轮结束；2 driver 或环境错误；3 需要用户介入；4 同一计划已有 driver 在运行。")
    commands = parser.add_subparsers(dest="command", required=True, title="子命令")

    def add_common_arguments(target: argparse.ArgumentParser) -> None:
        target.add_argument("--plan", required=True, help="<topic>/agent/plan.json")
        target.add_argument("--stories-dir", required=True, help="同一 agent/ 下的 stories/")
        target.add_argument("--repository", default=".", help="Git 仓库根目录；默认当前目录")
        target.add_argument("--planning-script", default=str(DEFAULT_PLANNING_SCRIPT), help="epic_story.py 路径")
        target.add_argument("--dispatch", help="bb-dispatch 路径；默认 PATH 或 sibling bb-model-routing")
        target.add_argument("--environment", help="传给 bb-dispatch 的 BB 环境 ID")
        target.add_argument("--context", default="", help="附加给每个线程的仓库说明（基线、命令等）")
        target.add_argument("--default-difficulty", choices=DIFFICULTIES, default="medium", help="首轮 Worker 难度")
        target.add_argument("--kind", choices=["general", "debug"], default="general", help="Worker 的 bb-dispatch --kind")
        target.add_argument("--validator", choices=["always", "standard-up"], default="standard-up",
                            help="standard-up（默认）：simple 档 Story 跳过 Validator，采信 Worker 证据；always：每张都派")
        target.add_argument("--max-patch-rounds", type=int, default=2, help="Validator FAIL 后发回同一 Worker 的最大轮数")
        target.add_argument("--max-attempts", type=int, default=3, help="同一 Story 的最大 Worker 线程数")
        target.add_argument("--max-judge-rounds", type=int, default=3, help="同一 Story 的最大 judge 介入次数")
        target.add_argument("--wait-timeout", type=int, default=1800, help="单次等待线程的秒数上限；超过后返回 waiting")
        target.add_argument("--poll-seconds", type=int, default=120, help="bb thread wait 的 --timeout")
        target.add_argument("--allow-empty-story", action="store_true", help="允许 Worker 无改动即完成（纯验证类 Story）")
        target.add_argument("--once", action="store_true", help="只推进一步就退出；适合定时调用")
        target.add_argument("--max-stories", type=int, default=0, help="完成 N 张 Story 后退出；0 为不限")
        target.add_argument("--push", action="store_true", help="全部完成后推送当前分支并核对远端 HEAD")

    run_parser = commands.add_parser("run", help="在前台运行 driver")
    add_common_arguments(run_parser)
    run_parser.add_argument("--_pid-managed", action="store_true", help=argparse.SUPPRESS)
    start_parser = commands.add_parser("start", help="校验后在后台启动 driver")
    add_common_arguments(start_parser)
    start_parser.add_argument("--foreground", action="store_true", help="等价于 run，在前台运行")
    status_parser = commands.add_parser("status", help="显示某个计划的 driver 与计划状态")
    add_common_arguments(status_parser)
    status_parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    status_parser.add_argument("--log-events", type=int, default=10, help="输出最近 N 条日志事件")
    stop_parser = commands.add_parser("stop", help="请求后台 driver 在当前 run_once 后退出")
    add_common_arguments(stop_parser)
    stop_parser.add_argument("--wait", action="store_true", help="等待 driver 退出，最长 --wait-timeout 秒")
    return parser


def background_command(args: argparse.Namespace) -> list[str]:
    command = [sys.executable, str(Path(__file__).resolve()), "run",
               "--plan", str(args.plan), "--stories-dir", str(args.stories_dir),
               "--repository", str(args.repository), "--planning-script", str(args.planning_script),
               "--default-difficulty", args.default_difficulty, "--kind", args.kind,
               "--validator", args.validator, "--max-patch-rounds", str(args.max_patch_rounds),
               "--max-attempts", str(args.max_attempts), "--max-judge-rounds", str(args.max_judge_rounds),
               "--wait-timeout", str(args.wait_timeout), "--poll-seconds", str(args.poll_seconds),
               "--max-stories", str(args.max_stories), "--_pid-managed"]
    if args.dispatch:
        command += ["--dispatch", args.dispatch]
    if args.environment:
        command += ["--environment", args.environment]
    if args.context:
        command += ["--context", args.context]
    if args.allow_empty_story:
        command.append("--allow-empty-story")
    if args.once:
        command.append("--once")
    if args.push:
        command.append("--push")
    return command


def status_command(driver: Driver, args: argparse.Namespace) -> str:
    command = [sys.executable, str(Path(__file__).resolve()), "status", "--plan", str(driver.plan_path),
               "--stories-dir", str(driver.stories_dir), "--repository", str(driver.repository),
               "--planning-script", str(args.planning_script)]
    if args.dispatch:
        command += ["--dispatch", str(args.dispatch)]
    return shlex.join(command)


def recent_log_events(path: Path, count: int) -> list[dict[str, Any]]:
    if count <= 0 or not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-count:]
    except OSError:
        return []
    events = []
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events


def collect_status(driver: Driver, log_events: int) -> dict[str, Any]:
    plan = driver.status()
    record = read_pid_record(driver.pid_path)
    pid = record.get("pid") if record else None
    state_stories = driver.state.get("stories", {})
    in_progress = []
    blocked = []
    for story in plan.get("stories", []):
        if story.get("status") == "blocked":
            blocked.append({"id": story["id"], "blocker": story.get("blocker")})
        if story.get("status") != "in_progress":
            continue
        cached = StoryState.from_dict(state_stories.get(story["id"], {}))
        in_progress.append({
            "id": story["id"], "stage": cached.phase,
            "difficulty": cached.difficulty or None,
            "worker_thread": cached.worker_thread or story.get("owner"),
            "validator_thread": cached.validator_thread,
        })
    try:
        last_stop = driver.last_stop_path.read_text(encoding="utf-8").strip() or None
    except OSError:
        last_stop = None
    return {
        "repository": str(driver.repository), "plan": str(driver.plan_path), "state_dir": str(driver.state_dir),
        "alive": bool(pid and process_alive(pid)), "pid": pid,
        "started_at": record.get("started_at") if record else None,
        "completed": plan.get("plan", {}).get("completed"), "total": plan.get("plan", {}).get("total"),
        "in_progress": in_progress, "blocked": blocked, "last_stop": last_stop,
        "recent_events": recent_log_events(driver.log_path, log_events),
    }


def print_status(payload: dict[str, Any]) -> None:
    state = "running" if payload["alive"] else "stopped"
    print(f"Driver: {state}; pid={payload['pid'] or '-'}; started_at={payload['started_at'] or '-'}")
    print(f"Plan: completed={payload['completed']}/{payload['total']}")
    print(f"State: {payload['state_dir']}")
    for story in payload["in_progress"]:
        print("In progress: {id}; stage={stage}; difficulty={difficulty}; worker={worker_thread}; validator={validator_thread}".format(**story))
    for story in payload["blocked"]:
        print(f"Blocked: {story['id']}; reason={story['blocker']}")
    if payload["last_stop"]:
        print(f"Last stop:\n{payload['last_stop']}")
    if payload["recent_events"]:
        print("Recent events:")
        for event in payload["recent_events"]:
            print(f"- {event.get('at', '-')}: {event.get('event', '-')}")


def run_foreground(args: argparse.Namespace) -> int:
    driver = Driver(args)
    acquired = False
    pid_managed = getattr(args, "_pid_managed", False)
    try:
        if not pid_managed:
            acquire_pid_lock(driver.pid_path)
            acquired = True

        def request_stop(_signal: int, _frame: Any) -> None:
            driver.request_stop()

        previous_term = signal.signal(signal.SIGTERM, request_stop)
        previous_int = signal.signal(signal.SIGINT, request_stop)
        try:
            return driver.run()
        finally:
            signal.signal(signal.SIGTERM, previous_term)
            signal.signal(signal.SIGINT, previous_int)
    finally:
        if acquired or pid_managed:
            clear_pid_lock(driver.pid_path, os.getpid())


def start_background(args: argparse.Namespace) -> int:
    driver = Driver(args)
    acquire_pid_lock(driver.pid_path)
    try:
        driver.check()
        driver.validate_dispatch()
        driver.state_dir.mkdir(parents=True, exist_ok=True)
        with driver.output_path.open("a", encoding="utf-8") as output:
            process = subprocess.Popen(
                background_command(args), cwd=driver.repository, stdout=output, stderr=subprocess.STDOUT,
                start_new_session=True, close_fds=True,
            )
        write_pid_record(driver.pid_path, process.pid)
        if process.poll() is not None:
            clear_pid_lock(driver.pid_path, process.pid)
    except Exception:
        clear_pid_lock(driver.pid_path, os.getpid())
        raise
    print(f"STARTED: pid={process.pid}")
    print(f"Log: {driver.log_path}")
    print(f"Output: {driver.output_path}")
    print(f"Status: {status_command(driver, args)}")
    return 0


def stop_driver(args: argparse.Namespace) -> int:
    driver = Driver(args)
    record = read_pid_record(driver.pid_path)
    if not record or not process_alive(record["pid"]):
        if record:
            clear_pid_lock(driver.pid_path, record["pid"])
        print("STOPPED: 没有运行中的 driver。")
        return 0
    pid = record["pid"]
    os.kill(pid, signal.SIGTERM)
    if args.wait:
        deadline = time.monotonic() + args.wait_timeout
        while process_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        if process_alive(pid):
            raise DriverError(f"等待 pid {pid} 退出超时（{args.wait_timeout} 秒）。")
        clear_pid_lock(driver.pid_path, pid)
    print(f"STOP REQUESTED: pid={pid}" + ("; 已退出。" if args.wait else ""))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "run":
            return run_foreground(args)
        if args.command == "start":
            return run_foreground(args) if args.foreground else start_background(args)
        if args.command == "status":
            payload = collect_status(Driver(args), args.log_events)
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print_status(payload)
            return 0
        if args.command == "stop":
            return stop_driver(args)
        raise DriverError(f"未知子命令: {args.command}")
    except DriverAlreadyRunning as error:
        print(f"RUNNING: {error}", file=sys.stderr)
        return 4
    except DriverError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
