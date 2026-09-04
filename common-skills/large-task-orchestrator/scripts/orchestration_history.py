#!/usr/bin/env python3
"""维护 large-task-orchestrator 的 checkout-local 滚动运行历史。

脚本定义：在 Git 仓库固定路径 `.local/large-task-orchestrator/run-history.json`
记录最小运行事实，供同一持久 checkout 的后续复盘使用；它不是计划状态源，也不是跨机器审计。
参数定义：所有命令必须传 `--repository`；mutation 使用 run/event/attempt 的稳定 ID，
时间默认由脚本采集，可用 `--at` 注入带时区 ISO-8601 时间；枚举值见 `--help`。
输出定义：成功时 stdout 输出 JSON；记录文件最多保留 1 个 active run、12 个 terminal run，
每 run 最近 30 个事件，旧 run 只汇入固定维度 rollup。退出码 0=成功，1=历史/Git 事实错误，
2=参数错误。脚本不保存 prompt、回复、diff、自由文本错误或 remote URL。
关键设计：完整读改写持有 flock，stable key 重试幂等，同目录 fsync+replace 原子落盘；
`delivered` 先验证 v2 计划完成且计划目录已提交，再用真实 `git ls-remote` 证明当前 HEAD 已到 upstream。损坏文件原样保留并 fail closed。
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Sequence, cast


SCRIPT_PATH = Path(__file__).resolve()
PLANNING_SCRIPT = SCRIPT_PATH.parents[2] / "large-task-planning" / "scripts" / "epic_story.py"
HISTORY_RELATIVE = Path(".local/large-task-orchestrator/run-history.json")
LOCK_RELATIVE = Path(".local/large-task-orchestrator/run-history.lock")
SCHEMA_VERSION = 1
MAX_TERMINAL_RUNS = 12
MAX_RECENT_EVENTS = 30
MAX_MUTATION_KEYS = 240

RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
EVENT_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+/@:^~-]{0,127}$")
STORY_RE = re.compile(r"^STORY-[0-9]+(?:\.[0-9]+)?$")
HEX_RE = re.compile(r"^[0-9a-f]{7,64}$")

# `validator` remains readable for existing local history; new runs use `reviewer`.
ROLES = ("worker", "reviewer", "validator")
WORKER_OUTCOMES = ("worker-done", "blocked", "failed", "quota-exhausted")
REVIEW_OUTCOMES = (
    "continue",
    "patch-prompt",
    "insert-story",
    "replan",
    "blocked",
    "failed",
    "quota-exhausted",
)
ATTEMPT_OUTCOMES = tuple(dict.fromkeys((*WORKER_OUTCOMES, *REVIEW_OUTCOMES)))
REASON_CODES = (
    "none",
    "quota",
    "route",
    "provider",
    "session",
    "environment",
    "authority",
    "concurrent-edit",
    "implementation",
    "validation",
    "plan-gap",
    "goal-change",
    "user-decision",
    "abandoned",
    "other",
)
CHANGE_KINDS = ("reorder", "insert", "split", "merge", "rewrite", "replan")
EVENT_TYPES = ("plan-change", "blocked", "checkpoint")
TERMINAL_OUTCOMES = ("delivered", "abandoned")
SUCCESS_ATTEMPT_OUTCOMES = ("worker-done", "continue")


class HistoryError(RuntimeError):
    """运行历史、参数语义或 Git 事实不满足契约。"""


def usage() -> str:
    return f"""用法:
  python3 {SCRIPT_PATH.name} --repository <repo> start --run-id <id> --plan-ref <path>
  python3 {SCRIPT_PATH.name} --repository <repo> attempt start [options]
  python3 {SCRIPT_PATH.name} --repository <repo> attempt finish [options]
  python3 {SCRIPT_PATH.name} --repository <repo> event [options]
  python3 {SCRIPT_PATH.name} --repository <repo> finish [options]
  python3 {SCRIPT_PATH.name} --repository <repo> show [--run-id <id>]
  python3 {SCRIPT_PATH.name} --repository <repo> check

说明:
  在 {HISTORY_RELATIVE.as_posix()} 维护同一 checkout 的复盘缓存。Plan 决定当前工作；
  history 只解释近期运行模式。文件缺失或记录失败不得改变 Story 状态或交付结论。
  该文件被 Git ignore，不提供跨 clone、跨机器或永久审计保证。

滚动规则:
  最多 1 个 active run、{MAX_TERMINAL_RUNS} 个 terminal run；每 run 保留最近
  {MAX_RECENT_EVENTS} 个事件。更老事件保留固定指标，更老 run 汇入固定维度 rollup。

命令:
  start             创建或幂等恢复 active run，并自动采集 Git baseline。
  attempt start     用稳定 attempt ID 记录 worker/reviewer 尝试开始。
  attempt finish    自动计算 duration，并记录固定 outcome/reason。
  event             记录 plan-change、blocked 或机械 checkpoint。
  finish            结束为 delivered 或 abandoned；delivered 会校验计划并查询真实远端。
  show              输出近期 run、聚合指标、热点和确定性复盘关注点。
  check             只读校验文件 schema、滚动上限和 active 状态。

输出:
  所有成功命令在 stdout 输出 UTF-8 JSON。错误写 stderr。脚本不记录 prompt、回复、
  diff、测试日志、自由文本错误、绝对 provider 命令或 remote URL。

示例:
  python3 {SCRIPT_PATH.name} --repository . start \\
    --run-id mission-20260830 --plan-ref docs/plan
  python3 {SCRIPT_PATH.name} --repository . attempt start \\
    --run-id mission-20260830 --attempt-id STORY-01-worker-1 \\
    --story STORY-01 --role worker --agent native --route host-native \\
    --model default --effort high --session <subagent-id> \\
    --plan-ref docs/plan/agent/stories/STORY-01-example.json
  python3 {SCRIPT_PATH.name} --repository . attempt finish \\
    --run-id mission-20260830 --attempt-id STORY-01-worker-1 --outcome worker-done
  python3 {SCRIPT_PATH.name} --repository . finish \\
    --run-id mission-20260830 --outcome delivered \\
    --plan docs/plan/agent/plan.json --stories-dir docs/plan/agent/stories
  python3 {SCRIPT_PATH.name} --repository . show
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="维护 large-task-orchestrator 的本地滚动运行历史。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=usage(),
    )
    parser.add_argument("--repository", required=True, type=Path, help="Git 仓库根目录")
    commands = parser.add_subparsers(dest="command", required=True)

    start = commands.add_parser("start", help="开始或恢复一个 run")
    start.add_argument("--run-id", required=True)
    start.add_argument("--plan-ref", required=True)
    start.add_argument("--at", help="带时区 ISO-8601 时间；默认当前 UTC")

    attempt = commands.add_parser("attempt", help="记录一个 subagent attempt")
    attempt_commands = attempt.add_subparsers(dest="attempt_command", required=True)
    attempt_start = attempt_commands.add_parser("start", help="开始 attempt")
    attempt_start.add_argument("--run-id", required=True)
    attempt_start.add_argument("--attempt-id", required=True)
    attempt_start.add_argument("--story", required=True)
    attempt_start.add_argument("--role", required=True, choices=ROLES)
    attempt_start.add_argument("--agent", required=True)
    attempt_start.add_argument("--route", required=True)
    attempt_start.add_argument("--model")
    attempt_start.add_argument("--effort")
    attempt_start.add_argument("--session")
    attempt_start.add_argument("--plan-ref")
    attempt_start.add_argument("--at", help="带时区 ISO-8601 时间；默认当前 UTC")

    attempt_finish = attempt_commands.add_parser("finish", help="结束 attempt")
    attempt_finish.add_argument("--run-id", required=True)
    attempt_finish.add_argument("--attempt-id", required=True)
    attempt_finish.add_argument("--outcome", required=True, choices=ATTEMPT_OUTCOMES)
    attempt_finish.add_argument("--reason", default="none", choices=REASON_CODES)
    attempt_finish.add_argument("--at", help="带时区 ISO-8601 时间；默认当前 UTC")

    event = commands.add_parser("event", help="记录计划变化、阻塞或 checkpoint")
    event.add_argument("--run-id", required=True)
    event.add_argument("--event-key", required=True)
    event.add_argument("--type", required=True, choices=EVENT_TYPES)
    event.add_argument("--story", action="append", default=[])
    event.add_argument("--change", choices=CHANGE_KINDS)
    event.add_argument("--reason", default="none", choices=REASON_CODES)
    event.add_argument("--plan-ref")
    event.add_argument("--at", help="带时区 ISO-8601 时间；默认当前 UTC")

    finish = commands.add_parser("finish", help="结束 run")
    finish.add_argument("--run-id", required=True)
    finish.add_argument("--outcome", required=True, choices=TERMINAL_OUTCOMES)
    finish.add_argument("--reason", default="none", choices=REASON_CODES)
    finish.add_argument("--plan-ref")
    finish.add_argument("--plan", help="delivered 必填：repository 内 v2 agent/plan.json 相对路径")
    finish.add_argument("--stories-dir", help="delivered 必填：同一 agent/ 下的 stories/ 相对路径")
    finish.add_argument("--at", help="带时区 ISO-8601 时间；默认当前 UTC")

    show = commands.add_parser("show", help="输出聚合历史与复盘关注点")
    show.add_argument("--run-id")
    commands.add_parser("check", help="校验历史文件")
    return parser


def _run_git(
    repository: Path,
    *arguments: str,
    check: bool = True,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    if shutil.which("git") is None:
        raise HistoryError("找不到 git；无法验证 repository 和交付事实")
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise HistoryError(f"git {' '.join(arguments)} 超时") from error
    if check and result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise HistoryError(
            f"git {' '.join(arguments)} 失败 exit={result.returncode}: {message}"
        )
    return result


def resolve_repository(path: Path) -> Path:
    candidate = path.expanduser().resolve()
    if not candidate.is_dir():
        raise HistoryError(f"repository 目录不存在: {candidate}")
    root = Path(
        _run_git(candidate, "rev-parse", "--show-toplevel").stdout.strip()
    ).resolve()
    if root != candidate:
        raise HistoryError(f"--repository 必须是 Git 根目录；实际根目录为 {root}")
    return root


def history_path(repository: Path) -> Path:
    return repository / HISTORY_RELATIVE


def lock_path(repository: Path) -> Path:
    return repository / LOCK_RELATIVE


def _ensure_safe_parent(repository: Path) -> Path:
    target = history_path(repository)
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    resolved_parent = parent.resolve()
    if not resolved_parent.is_relative_to(repository):
        raise HistoryError(f"历史目录通过 symlink 逃逸 repository: {resolved_parent}")
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise HistoryError(f"历史路径必须是普通文件且不能是 symlink: {target}")
    lock = lock_path(repository)
    if lock.is_symlink() or (lock.exists() and not lock.is_file()):
        raise HistoryError(f"锁路径必须是普通文件且不能是 symlink: {lock}")
    return parent


def ensure_history_is_ignored(repository: Path) -> None:
    relative = HISTORY_RELATIVE.as_posix()
    result = _run_git(
        repository,
        "check-ignore",
        "--no-index",
        "-q",
        "--",
        relative,
        check=False,
    )
    if result.returncode != 0:
        raise HistoryError(
            f"{relative} 尚未被 Git ignore；先把 `.local/` 加入 .git/info/exclude"
        )


@contextlib.contextmanager
def history_lock(repository: Path, *, exclusive: bool) -> Iterator[None]:
    if exclusive:
        ensure_history_is_ignored(repository)
    _ensure_safe_parent(repository)
    lock = lock_path(repository)
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        with os.fdopen(descriptor, "a+", encoding="utf-8") as handle:
            fcntl.flock(
                handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            )
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except Exception:
        # fdopen owns descriptor after successful construction.
        raise


def parse_time(value: str | None) -> tuple[str, datetime]:
    if value is None:
        current = datetime.now(timezone.utc)
    else:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            current = datetime.fromisoformat(normalized)
        except ValueError as error:
            raise HistoryError(f"时间不是合法 ISO-8601: {value}") from error
        if current.tzinfo is None:
            raise HistoryError(f"时间必须带时区: {value}")
        current = current.astimezone(timezone.utc)
    return current.isoformat(timespec="seconds").replace("+00:00", "Z"), current


def _parse_stored_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise HistoryError(f"{label} 必须是 ISO-8601 字符串")
    _, parsed = parse_time(value)
    return parsed


def validate_token(value: str, label: str, pattern: re.Pattern[str] = TOKEN_RE) -> str:
    if not pattern.fullmatch(value):
        raise HistoryError(f"{label}={value!r} 格式非法")
    return value


def validate_optional_text(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    if not value or len(value.encode("utf-8")) > 240 or "\n" in value or "\r" in value:
        raise HistoryError(f"{label} 必须是 1～240 bytes 的单行文本")
    return value


def normalize_plan_ref(repository: Path, value: str) -> str:
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
        raise HistoryError(f"plan_ref 必须是 repository 内相对路径: {value}")
    resolved = (repository / Path(*candidate.parts)).resolve()
    if not resolved.is_relative_to(repository) or not resolved.exists():
        raise HistoryError(f"plan_ref 不存在或逃逸 repository: {value}")
    return resolved.relative_to(repository).as_posix()


def validate_stored_token(
    value: Any, label: str, pattern: re.Pattern[str] = TOKEN_RE
) -> str:
    if not isinstance(value, str):
        raise HistoryError(f"{label} 必须是字符串")
    return validate_token(value, label, pattern)


def is_nonnegative_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def _git_local_facts(repository: Path) -> dict[str, Any]:
    head = _run_git(repository, "rev-parse", "HEAD").stdout.strip()
    if not HEX_RE.fullmatch(head):
        raise HistoryError(f"Git HEAD 非法: {head!r}")
    branch_result = _run_git(
        repository, "symbolic-ref", "--quiet", "--short", "HEAD", check=False
    )
    if branch_result.returncode != 0:
        raise HistoryError("不支持 detached HEAD；先切回计划对应分支")
    branch = branch_result.stdout.strip()
    remote_result = _run_git(
        repository, "config", "--get", f"branch.{branch}.remote", check=False
    )
    merge_result = _run_git(
        repository, "config", "--get", f"branch.{branch}.merge", check=False
    )
    upstream: dict[str, str] | None = None
    if remote_result.returncode == 0 and merge_result.returncode == 0:
        remote = remote_result.stdout.strip()
        ref = merge_result.stdout.strip()
        if remote and ref.startswith("refs/heads/"):
            upstream = {"remote": remote, "ref": ref}
    return {"head": head, "branch": branch, "upstream": upstream}


def _plan_completion_gate(
    repository: Path,
    run: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    option_names = ("plan", "stories_dir")
    missing = [f"--{name.replace('_', '-')}" for name in option_names if not getattr(args, name)]
    if missing:
        raise HistoryError(f"delivered 需要计划完成门禁参数: {', '.join(missing)}")
    if not PLANNING_SCRIPT.is_file():
        raise HistoryError(f"找不到 sibling planning 校验脚本: {PLANNING_SCRIPT}")

    relative = {
        name: normalize_plan_ref(repository, str(getattr(args, name)))
        for name in option_names
    }
    paths = {name: (repository / value).resolve() for name, value in relative.items()}
    plan = paths["plan"]
    stories = paths["stories_dir"]
    if not plan.is_file() or plan.name != "plan.json" or plan.parent.name != "agent":
        raise HistoryError("--plan 必须指向 <topic>/agent/plan.json")
    if not stories.is_dir() or stories.name != "stories":
        raise HistoryError("--stories-dir 必须指向 <topic>/agent/stories/")
    agent_root = plan.parent
    if stories.parent != agent_root:
        raise HistoryError("plan.json 与 stories/ 必须属于同一个 agent/ 目录")
    plan_root = agent_root.parent
    run_plan_ref = (repository / run["plan_ref"]).resolve()
    if run_plan_ref not in {plan_root, plan} and not run_plan_ref.is_relative_to(plan_root):
        raise HistoryError("delivered 计划根目录与 run.plan_ref 不一致")

    validated_head = _git_local_facts(repository)["head"]
    try:
        checked = subprocess.run(
            [
                sys.executable,
                str(PLANNING_SCRIPT),
                "completion-check",
                "--plan",
                relative["plan"],
                "--stories-dir",
                relative["stories_dir"],
            ],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HistoryError(f"计划完成门禁无法执行: {error}") from error
    if checked.returncode != 0:
        detail = (checked.stderr.strip() or checked.stdout.strip() or "无诊断输出")[:2000]
        raise HistoryError(f"计划完成门禁失败: {detail}")

    critical_paths = [plan, plan_root / "SPEC.md", plan_root / "STATUS.md"]
    critical_paths.extend(sorted(stories.glob("*.json")))
    unsafe_inputs = [
        path
        for path in critical_paths
        if path.is_symlink()
        or not path.is_file()
        or not path.resolve().is_relative_to(plan_root)
    ]
    if unsafe_inputs:
        unsafe_relative = [
            path.relative_to(repository).as_posix() for path in unsafe_inputs
        ]
        raise HistoryError(
            "计划完成门禁输入必须是计划目录内的普通非 symlink 文件: "
            + ", ".join(unsafe_relative)
        )
    critical_relative = [path.relative_to(repository).as_posix() for path in critical_paths]
    tracked_result = _run_git(
        repository,
        "ls-files",
        "--cached",
        "-z",
        "--",
        *critical_relative,
    )
    tracked = {item for item in tracked_result.stdout.split("\0") if item}
    untracked_inputs = sorted(set(critical_relative) - tracked)
    if untracked_inputs:
        raise HistoryError(
            "计划完成门禁输入尚未进入当前提交: " + ", ".join(untracked_inputs)
        )
    root_relative = plan_root.relative_to(repository).as_posix() or "."
    status = _run_git(
        repository,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        root_relative,
    )
    if status.stdout:
        raise HistoryError(f"计划目录仍有未提交变更: {root_relative}")
    if _git_local_facts(repository)["head"] != validated_head:
        raise HistoryError("计划完成门禁执行期间 Git HEAD 发生变化")
    return {
        "root": root_relative,
        "check": "passed",
        "tracked_inputs": len(critical_relative),
        "head": validated_head,
    }


def _git_delivery_facts(
    repository: Path,
    baseline: dict[str, Any],
    expected_head: str,
) -> dict[str, Any]:
    local = _git_local_facts(repository)
    if local["head"] != expected_head:
        raise HistoryError(
            f"计划完成门禁后 Git HEAD 发生变化: {expected_head} -> {local['head']}"
        )
    if local["branch"] != baseline.get("branch"):
        raise HistoryError(
            f"delivered run 的 branch 漂移: {baseline.get('branch')} -> {local['branch']}"
        )
    baseline_upstream = baseline.get("upstream")
    upstream = local.get("upstream")
    if not isinstance(upstream, dict):
        raise HistoryError("delivered run 缺少 upstream；先完成 push -u")
    if baseline_upstream is not None and upstream != baseline_upstream:
        raise HistoryError("delivered run 的 upstream 在执行中发生漂移")
    remote = upstream["remote"]
    ref = upstream["ref"]
    if remote == ".":
        raise HistoryError("delivered run 的 upstream 必须是可查询的 Git remote")
    result = _run_git(repository, "ls-remote", "--exit-code", remote, ref)
    remote_heads = {
        line.split("\t", 1)[0]
        for line in result.stdout.splitlines()
        if "\t" in line and line.split("\t", 1)[1] == ref
    }
    if len(remote_heads) != 1:
        raise HistoryError(f"远端 {remote} {ref} 未返回唯一 HEAD")
    remote_head = next(iter(remote_heads))
    if remote_head != local["head"]:
        raise HistoryError(
            f"本地 HEAD 尚未到达真实远端 {remote}/{ref}: "
            f"{local['head']} != {remote_head}"
        )
    final_local = _git_local_facts(repository)
    if final_local != local:
        raise HistoryError("查询远端交付事实期间本地 branch、HEAD 或 upstream 发生变化")
    return {
        "head": local["head"],
        "branch": local["branch"],
        "remote": remote,
        "ref": ref,
        "remote_head": remote_head,
        "pushed": True,
    }


def _empty_metrics() -> dict[str, Any]:
    return {
        "events": 0,
        "attempts": 0,
        "attempt_seconds": 0,
        "by_story": {},
        "by_role": {},
        "by_agent": {},
        "by_route": {},
        "by_outcome": {},
        "by_reason": {},
        "plan_changes": {},
        "blocked_events": 0,
        "checkpoints": 0,
    }


def _empty_rollup() -> dict[str, Any]:
    return {
        "terminal_runs": 0,
        "run_outcomes": {},
        "attempts": 0,
        "attempt_seconds": 0,
        "by_role": {},
        "by_outcome": {},
        "by_reason": {},
        "plan_changes": {},
        "blocked_events": 0,
        "checkpoints": 0,
    }


def _empty_history(at: str) -> dict[str, Any]:
    return {
        "kind": "large-task-orchestration-history",
        "schema_version": SCHEMA_VERSION,
        "scope": "same-persistent-checkout-only",
        "retention": {
            "terminal_runs": MAX_TERMINAL_RUNS,
            "recent_events_per_run": MAX_RECENT_EVENTS,
        },
        "updated_at": at,
        "rollup": _empty_rollup(),
        "runs": [],
    }


def _increment(mapping: dict[str, int], key: str, value: int = 1) -> None:
    mapping[key] = mapping.get(key, 0) + value


def _append_event(run: dict[str, Any], event: dict[str, Any]) -> None:
    run["metrics"]["events"] += 1
    run["recent_events"].append(event)
    overflow = len(run["recent_events"]) - MAX_RECENT_EVENTS
    if overflow > 0:
        del run["recent_events"][:overflow]
        run["compacted_events"] += overflow


def _semantic_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _register_mutation(
    run: dict[str, Any],
    key: str,
    payload: dict[str, Any],
    *,
    new_attempt_reservations: int = 0,
    consume_attempt_reservation: bool = False,
) -> bool:
    validate_token(key, "stable key", EVENT_KEY_RE)
    digest = _semantic_digest(payload)
    seen = run["seen_event_keys"]
    previous = seen.get(key)
    if previous is not None:
        if previous != digest:
            raise HistoryError(f"stable key {key!r} 已用于不同 payload")
        return False
    projected = len(seen) + 1
    if not consume_attempt_reservation:
        projected += len(run["active_attempts"]) + new_attempt_reservations
    if projected > MAX_MUTATION_KEYS:
        raise HistoryError(
            f"run mutation 已达到固定上限 {MAX_MUTATION_KEYS}；"
            "保留 active attempt 的收尾容量后已无新事件空间"
        )
    seen[key] = digest
    return True


def _find_run(history: dict[str, Any], run_id: str) -> dict[str, Any]:
    matches = [run for run in history["runs"] if run.get("run_id") == run_id]
    if len(matches) != 1:
        raise HistoryError(f"找不到唯一 run_id={run_id!r}")
    return matches[0]


def _active_run(history: dict[str, Any]) -> dict[str, Any] | None:
    active = [run for run in history["runs"] if run.get("outcome") == "active"]
    if len(active) > 1:
        raise HistoryError("历史中存在多个 active run")
    return active[0] if active else None


def _merge_count_maps(target: dict[str, int], source: dict[str, int]) -> None:
    for key, value in source.items():
        _increment(target, key, value)


def _fold_run_into_rollup(rollup: dict[str, Any], run: dict[str, Any]) -> None:
    metrics = run["metrics"]
    rollup["terminal_runs"] += 1
    _increment(rollup["run_outcomes"], run["outcome"])
    rollup["attempts"] += metrics["attempts"]
    rollup["attempt_seconds"] += metrics["attempt_seconds"]
    for field in ("by_role", "by_outcome", "by_reason", "plan_changes"):
        _merge_count_maps(rollup[field], metrics[field])
    rollup["blocked_events"] += metrics["blocked_events"]
    rollup["checkpoints"] += metrics["checkpoints"]


def _roll_terminal_runs(history: dict[str, Any]) -> None:
    while True:
        terminal_indexes = [
            index
            for index, run in enumerate(history["runs"])
            if run.get("outcome") in TERMINAL_OUTCOMES
        ]
        if len(terminal_indexes) <= MAX_TERMINAL_RUNS:
            return
        index = terminal_indexes[0]
        run = history["runs"].pop(index)
        _fold_run_into_rollup(history["rollup"], run)


def _validate_count_map(
    value: Any,
    label: str,
    allowed_keys: Sequence[str] | None = None,
) -> None:
    if not isinstance(value, dict):
        raise HistoryError(f"{label} 必须是对象")
    for key, count in value.items():
        if not isinstance(key, str) or (allowed_keys is not None and key not in allowed_keys):
            raise HistoryError(f"{label} 包含非法 key={key!r}")
        if not is_nonnegative_int(count):
            raise HistoryError(f"{label}.{key} 必须是非负整数")


def _validate_metrics(metrics: Any, label: str) -> None:
    if not isinstance(metrics, dict):
        raise HistoryError(f"{label} 必须是对象")
    required = {
        "events",
        "attempts",
        "attempt_seconds",
        "by_story",
        "by_role",
        "by_agent",
        "by_route",
        "by_outcome",
        "by_reason",
        "plan_changes",
        "blocked_events",
        "checkpoints",
    }
    if set(metrics) != required:
        raise HistoryError(f"{label} 字段漂移")
    for field in ("events", "attempts", "attempt_seconds", "blocked_events", "checkpoints"):
        if not is_nonnegative_int(metrics[field]):
            raise HistoryError(f"{label}.{field} 必须是非负整数")
    _validate_count_map(metrics["by_story"], f"{label}.by_story")
    _validate_count_map(metrics["by_role"], f"{label}.by_role", ROLES)
    _validate_count_map(metrics["by_agent"], f"{label}.by_agent")
    _validate_count_map(metrics["by_route"], f"{label}.by_route")
    _validate_count_map(metrics["by_outcome"], f"{label}.by_outcome", ATTEMPT_OUTCOMES)
    _validate_count_map(metrics["by_reason"], f"{label}.by_reason", REASON_CODES)
    _validate_count_map(metrics["plan_changes"], f"{label}.plan_changes", CHANGE_KINDS)


def _validate_stored_text(
    value: Any, label: str, *, optional: bool = False, max_bytes: int = 500
) -> None:
    if optional and value is None:
        return
    if (
        not isinstance(value, str)
        or not value
        or "\n" in value
        or "\r" in value
        or len(value.encode("utf-8")) > max_bytes
    ):
        raise HistoryError(f"{label} 必须是有界单行字符串")


def _validate_upstream(value: Any, label: str) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {"remote", "ref"}:
        raise HistoryError(f"{label} 字段漂移")
    _validate_stored_text(value["remote"], f"{label}.remote", max_bytes=128)
    _validate_stored_text(value["ref"], f"{label}.ref", max_bytes=240)
    if not value["ref"].startswith("refs/heads/"):
        raise HistoryError(f"{label}.ref 必须是 refs/heads/*")


def _validate_local_git(value: Any, label: str) -> None:
    if not isinstance(value, dict) or set(value) != {"head", "branch", "upstream"}:
        raise HistoryError(f"{label} 字段漂移")
    if not isinstance(value["head"], str) or not HEX_RE.fullmatch(value["head"]):
        raise HistoryError(f"{label}.head 非法")
    _validate_stored_text(value["branch"], f"{label}.branch", max_bytes=240)
    _validate_upstream(value["upstream"], f"{label}.upstream")


def _validate_delivery(value: Any, label: str, outcome: str) -> None:
    if not isinstance(value, dict):
        raise HistoryError(f"{label} 必须是对象")
    if outcome == "delivered":
        required = {"head", "branch", "remote", "ref", "remote_head", "pushed"}
        if set(value) != required or value.get("pushed") is not True:
            raise HistoryError(f"{label} delivered 字段漂移")
        for field in ("head", "remote_head"):
            if not isinstance(value[field], str) or not HEX_RE.fullmatch(value[field]):
                raise HistoryError(f"{label}.{field} 非法")
        if value["head"] != value["remote_head"]:
            raise HistoryError(f"{label} delivered HEAD 不一致")
        _validate_stored_text(value["branch"], f"{label}.branch", max_bytes=240)
        _validate_stored_text(value["remote"], f"{label}.remote", max_bytes=128)
        _validate_stored_text(value["ref"], f"{label}.ref", max_bytes=240)
        if not value["ref"].startswith("refs/heads/"):
            raise HistoryError(f"{label}.ref 必须是 refs/heads/*")
        return
    required = {"head", "branch", "upstream", "pushed"}
    if set(value) != required or value.get("pushed") is not False:
        raise HistoryError(f"{label} abandoned 字段漂移")
    _validate_local_git(
        {key: value[key] for key in ("head", "branch", "upstream")}, label
    )


def _validate_attempt(value: Any, label: str) -> None:
    required = {
        "attempt_id",
        "story",
        "role",
        "agent",
        "route",
        "model",
        "effort",
        "session",
        "plan_ref",
        "started_at",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise HistoryError(f"{label} 字段漂移")
    validate_stored_token(value["attempt_id"], f"{label}.attempt_id", EVENT_KEY_RE)
    validate_stored_token(value["story"], f"{label}.story", STORY_RE)
    if value["role"] not in ROLES:
        raise HistoryError(f"{label}.role 非法")
    validate_stored_token(value["agent"], f"{label}.agent")
    validate_stored_token(value["route"], f"{label}.route")
    for field in ("model", "effort", "session"):
        _validate_stored_text(value[field], f"{label}.{field}", optional=True, max_bytes=240)
    _validate_stored_text(value["plan_ref"], f"{label}.plan_ref")
    _parse_stored_time(value["started_at"], f"{label}.started_at")


def _validate_recent_event(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        raise HistoryError(f"{label} 必须是对象")
    event_type = value.get("event")
    _parse_stored_time(value.get("time"), f"{label}.time")
    attempt_fields = {
        "attempt_id",
        "story",
        "role",
        "agent",
        "route",
        "model",
        "effort",
        "session",
        "plan_ref",
    }
    if event_type == "attempt-start":
        if set(value) != {"time", "event", *attempt_fields}:
            raise HistoryError(f"{label} attempt-start 字段漂移")
        _validate_attempt(
            {**{field: value[field] for field in attempt_fields}, "started_at": value["time"]},
            label,
        )
        return
    if event_type == "attempt-finish":
        required = {
            "time",
            "event",
            *attempt_fields,
            "started_at",
            "duration_seconds",
            "outcome",
            "reason",
        }
        if set(value) != required:
            raise HistoryError(f"{label} attempt-finish 字段漂移")
        _validate_attempt(
            {field: value[field] for field in (*attempt_fields, "started_at")}, label
        )
        if not is_nonnegative_int(value["duration_seconds"]):
            raise HistoryError(f"{label}.duration_seconds 非法")
        role = value["role"]
        allowed = WORKER_OUTCOMES if role == "worker" else REVIEW_OUTCOMES
        if value["outcome"] not in allowed or value["reason"] not in REASON_CODES:
            raise HistoryError(f"{label} outcome/reason 非法")
        return
    if event_type in EVENT_TYPES:
        required = {"time", "event", "type", "stories", "change", "reason", "plan_ref", "git"}
        if set(value) != required or value["type"] != event_type:
            raise HistoryError(f"{label} {event_type} 字段漂移")
        if not isinstance(value["stories"], list):
            raise HistoryError(f"{label}.stories 必须是数组")
        for story in value["stories"]:
            validate_stored_token(story, f"{label}.story", STORY_RE)
        if value["reason"] not in REASON_CODES:
            raise HistoryError(f"{label}.reason 非法")
        _validate_stored_text(value["plan_ref"], f"{label}.plan_ref")
        if event_type == "plan-change":
            if value["change"] not in CHANGE_KINDS or value["git"] is not None:
                raise HistoryError(f"{label} plan-change 字段非法")
        elif event_type == "blocked":
            if value["change"] is not None or value["reason"] == "none" or value["git"] is not None:
                raise HistoryError(f"{label} blocked 字段非法")
        else:
            if value["change"] is not None or not value["stories"]:
                raise HistoryError(f"{label} checkpoint 字段非法")
            _validate_local_git(value["git"], f"{label}.git")
        return
    if event_type == "run-finish":
        required = {"time", "event", "outcome", "reason", "plan_ref", "delivery"}
        if set(value) != required or value["outcome"] not in TERMINAL_OUTCOMES:
            raise HistoryError(f"{label} run-finish 字段漂移")
        if value["reason"] not in REASON_CODES:
            raise HistoryError(f"{label}.reason 非法")
        _validate_stored_text(value["plan_ref"], f"{label}.plan_ref")
        _validate_delivery(value["delivery"], f"{label}.delivery", value["outcome"])
        return
    raise HistoryError(f"{label}.event 非法: {event_type!r}")


def validate_history(history: Any) -> None:
    if not isinstance(history, dict):
        raise HistoryError("history 根节点必须是对象")
    if history.get("kind") != "large-task-orchestration-history":
        raise HistoryError("history kind 非法")
    if type(history.get("schema_version")) is not int or history.get("schema_version") != SCHEMA_VERSION:
        raise HistoryError(
            f"不支持 schema_version={history.get('schema_version')!r}；当前仅支持 {SCHEMA_VERSION}"
        )
    if history.get("scope") != "same-persistent-checkout-only":
        raise HistoryError("history scope 非法")
    retention = history.get("retention")
    if not isinstance(retention, dict) or set(retention) != {
        "terminal_runs",
        "recent_events_per_run",
    }:
        raise HistoryError("history retention 字段漂移")
    for field, expected in (
        ("terminal_runs", MAX_TERMINAL_RUNS),
        ("recent_events_per_run", MAX_RECENT_EVENTS),
    ):
        if type(retention[field]) is not int or retention[field] != expected:
            raise HistoryError(f"history retention.{field} 与固定契约不一致")
    _parse_stored_time(history.get("updated_at"), "updated_at")
    rollup = history.get("rollup")
    if not isinstance(rollup, dict) or set(rollup) != set(_empty_rollup()):
        raise HistoryError("rollup 字段漂移")
    for field in ("terminal_runs", "attempts", "attempt_seconds", "blocked_events", "checkpoints"):
        if not is_nonnegative_int(rollup[field]):
            raise HistoryError(f"rollup.{field} 必须是非负整数")
    _validate_count_map(rollup["run_outcomes"], "rollup.run_outcomes", TERMINAL_OUTCOMES)
    _validate_count_map(rollup["by_role"], "rollup.by_role", ROLES)
    _validate_count_map(rollup["by_outcome"], "rollup.by_outcome", ATTEMPT_OUTCOMES)
    _validate_count_map(rollup["by_reason"], "rollup.by_reason", REASON_CODES)
    _validate_count_map(rollup["plan_changes"], "rollup.plan_changes", CHANGE_KINDS)

    runs = history.get("runs")
    if not isinstance(runs, list):
        raise HistoryError("runs 必须是数组")
    run_ids: set[str] = set()
    active_count = 0
    terminal_count = 0
    for index, run in enumerate(runs):
        label = f"runs[{index}]"
        if not isinstance(run, dict):
            raise HistoryError(f"{label} 必须是对象")
        required = {
            "run_id",
            "plan_ref",
            "started_at",
            "ended_at",
            "outcome",
            "terminal_reason",
            "baseline",
            "delivery",
            "metrics",
            "active_attempts",
            "seen_event_keys",
            "recent_events",
            "compacted_events",
        }
        if set(run) != required:
            raise HistoryError(f"{label} 字段漂移")
        run_id = validate_stored_token(run["run_id"], f"{label}.run_id", RUN_ID_RE)
        if run_id in run_ids:
            raise HistoryError(f"重复 run_id={run_id}")
        run_ids.add(run_id)
        _parse_stored_time(run["started_at"], f"{label}.started_at")
        outcome = run["outcome"]
        if run["terminal_reason"] not in REASON_CODES:
            raise HistoryError(f"{label}.terminal_reason 非法")
        if outcome == "active":
            active_count += 1
            if run["ended_at"] is not None or run["delivery"] is not None:
                raise HistoryError(f"{label} active run 不得有 ended_at/delivery")
            if run["terminal_reason"] != "none":
                raise HistoryError(f"{label} active run 的 terminal_reason 必须为 none")
        elif outcome in TERMINAL_OUTCOMES:
            terminal_count += 1
            _parse_stored_time(run["ended_at"], f"{label}.ended_at")
            _validate_delivery(run["delivery"], f"{label}.delivery", outcome)
        else:
            raise HistoryError(f"{label}.outcome 非法: {outcome!r}")
        _validate_stored_text(run["plan_ref"], f"{label}.plan_ref")
        _validate_local_git(run["baseline"], f"{label}.baseline")
        _validate_metrics(run["metrics"], f"{label}.metrics")
        if not isinstance(run["active_attempts"], list):
            raise HistoryError(f"{label}.active_attempts 必须是数组")
        if outcome != "active" and run["active_attempts"]:
            raise HistoryError(f"{label} terminal run 仍有 active attempt")
        attempt_ids: set[str] = set()
        for attempt_index, attempt in enumerate(run["active_attempts"]):
            attempt_label = f"{label}.active_attempts[{attempt_index}]"
            _validate_attempt(attempt, attempt_label)
            attempt_id = attempt["attempt_id"]
            if attempt_id in attempt_ids:
                raise HistoryError(f"{label} 重复 active attempt={attempt_id}")
            attempt_ids.add(attempt_id)
        seen = run["seen_event_keys"]
        if not isinstance(seen, dict) or len(seen) > MAX_MUTATION_KEYS:
            raise HistoryError(f"{label}.seen_event_keys 非法")
        for key, digest in seen.items():
            validate_stored_token(key, "seen_event_key", EVENT_KEY_RE)
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise HistoryError(f"{label}.seen_event_keys digest 非法")
        events = run["recent_events"]
        if not isinstance(events, list) or len(events) > MAX_RECENT_EVENTS:
            raise HistoryError(f"{label}.recent_events 超出滚动上限")
        for event_index, event in enumerate(events):
            _validate_recent_event(event, f"{label}.recent_events[{event_index}]")
        if not is_nonnegative_int(run["compacted_events"]):
            raise HistoryError(f"{label}.compacted_events 非法")
    if active_count > 1:
        raise HistoryError("最多允许一个 active run")
    if terminal_count > MAX_TERMINAL_RUNS:
        raise HistoryError("terminal run 超出滚动上限")


def load_history(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise HistoryError(f"运行历史不存在或不是普通文件: {path}")
    try:
        history = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise HistoryError(f"运行历史损坏，已保留原文件: {path}: {error}") from error
    validate_history(history)
    return history


def write_history(path: Path, history: dict[str, Any]) -> None:
    validate_history(history)
    payload = json.dumps(history, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _output(action: str, path: Path, **values: Any) -> dict[str, Any]:
    return {"ok": True, "action": action, "history": str(path), **values}


def command_start(repository: Path, args: argparse.Namespace) -> dict[str, Any]:
    run_id = validate_token(args.run_id, "run_id", RUN_ID_RE)
    plan_ref = normalize_plan_ref(repository, args.plan_ref)
    at, _ = parse_time(args.at)
    path = history_path(repository)
    with history_lock(repository, exclusive=True):
        history = load_history(path) if path.exists() else _empty_history(at)
        existing = [run for run in history["runs"] if run["run_id"] == run_id]
        if existing:
            run = existing[0]
            if run["outcome"] == "active" and run["plan_ref"] == plan_ref:
                return _output("start", path, run_id=run_id, idempotent=True)
            raise HistoryError(f"run_id={run_id!r} 已存在且不能重新开始")
        active = _active_run(history)
        if active is not None:
            raise HistoryError(
                f"已有 active run={active['run_id']} plan_ref={active['plan_ref']}；"
                "先恢复它，或显式 finish --outcome abandoned"
            )
        history["runs"].append(
            {
                "run_id": run_id,
                "plan_ref": plan_ref,
                "started_at": at,
                "ended_at": None,
                "outcome": "active",
                "terminal_reason": "none",
                "baseline": _git_local_facts(repository),
                "delivery": None,
                "metrics": _empty_metrics(),
                "active_attempts": [],
                "seen_event_keys": {},
                "recent_events": [],
                "compacted_events": 0,
            }
        )
        history["updated_at"] = at
        write_history(path, history)
    return _output("start", path, run_id=run_id, idempotent=False)


def _load_active_for_mutation(
    history: dict[str, Any], run_id: str
) -> dict[str, Any]:
    validate_token(run_id, "run_id", RUN_ID_RE)
    run = _find_run(history, run_id)
    if run["outcome"] != "active":
        raise HistoryError(f"run_id={run_id!r} 已结束为 {run['outcome']}")
    return run


def command_attempt_start(repository: Path, args: argparse.Namespace) -> dict[str, Any]:
    at, _ = parse_time(args.at)
    attempt_id = validate_token(args.attempt_id, "attempt_id", EVENT_KEY_RE)
    story = validate_token(args.story, "story", STORY_RE)
    agent = validate_token(args.agent, "agent")
    route = validate_token(args.route, "route")
    model = validate_optional_text(args.model, "model")
    effort = validate_optional_text(args.effort, "effort")
    session = validate_optional_text(args.session, "session")
    path = history_path(repository)
    with history_lock(repository, exclusive=True):
        history = load_history(path)
        run = _load_active_for_mutation(history, args.run_id)
        plan_ref = normalize_plan_ref(repository, args.plan_ref or run["plan_ref"])
        semantic = {
            "attempt_id": attempt_id,
            "story": story,
            "role": args.role,
            "agent": agent,
            "route": route,
            "model": model,
            "effort": effort,
            "session": session,
            "plan_ref": plan_ref,
        }
        key = f"attempt-start:{attempt_id}"
        if not _register_mutation(
            run, key, semantic, new_attempt_reservations=1
        ):
            return _output(
                "attempt-start", path, run_id=args.run_id, attempt_id=attempt_id, idempotent=True
            )
        attempt = {**semantic, "started_at": at}
        run["active_attempts"].append(attempt)
        _append_event(run, {"time": at, "event": "attempt-start", **semantic})
        history["updated_at"] = at
        write_history(path, history)
    return _output(
        "attempt-start", path, run_id=args.run_id, attempt_id=attempt_id, idempotent=False
    )


def _finish_attempt(
    run: dict[str, Any], attempt: dict[str, Any], outcome: str, reason: str, at: str
) -> dict[str, Any]:
    role = attempt["role"]
    allowed = WORKER_OUTCOMES if role == "worker" else REVIEW_OUTCOMES
    if outcome not in allowed:
        raise HistoryError(f"{role} attempt 不允许 outcome={outcome}")
    if outcome not in SUCCESS_ATTEMPT_OUTCOMES and reason == "none":
        raise HistoryError(f"outcome={outcome} 必须提供非 none reason")
    started = _parse_stored_time(attempt["started_at"], "attempt.started_at")
    _, ended = parse_time(at)
    if ended < started:
        raise HistoryError("attempt finish 时间早于 start")
    duration = int((ended - started).total_seconds())
    event = {
        "time": at,
        "event": "attempt-finish",
        **{key: value for key, value in attempt.items() if key != "started_at"},
        "started_at": attempt["started_at"],
        "duration_seconds": duration,
        "outcome": outcome,
        "reason": reason,
    }
    metrics = run["metrics"]
    metrics["attempts"] += 1
    metrics["attempt_seconds"] += duration
    _increment(metrics["by_story"], attempt["story"])
    _increment(metrics["by_role"], role)
    _increment(metrics["by_agent"], attempt["agent"])
    route_key = "/".join(
        [
            role,
            attempt["route"],
            attempt["agent"],
            attempt.get("model") or "default",
            attempt.get("effort") or "default",
        ]
    )
    _increment(metrics["by_route"], route_key)
    _increment(metrics["by_outcome"], outcome)
    if reason != "none":
        _increment(metrics["by_reason"], reason)
    _append_event(run, event)
    run["active_attempts"].remove(attempt)
    return event


def command_attempt_finish(repository: Path, args: argparse.Namespace) -> dict[str, Any]:
    at, _ = parse_time(args.at)
    attempt_id = validate_token(args.attempt_id, "attempt_id", EVENT_KEY_RE)
    semantic = {"attempt_id": attempt_id, "outcome": args.outcome, "reason": args.reason}
    path = history_path(repository)
    with history_lock(repository, exclusive=True):
        history = load_history(path)
        run = _load_active_for_mutation(history, args.run_id)
        key = f"attempt-finish:{attempt_id}"
        if not _register_mutation(
            run, key, semantic, consume_attempt_reservation=True
        ):
            return _output(
                "attempt-finish", path, run_id=args.run_id, attempt_id=attempt_id, idempotent=True
            )
        matches = [
            attempt
            for attempt in run["active_attempts"]
            if attempt["attempt_id"] == attempt_id
        ]
        if len(matches) != 1:
            raise HistoryError(f"找不到唯一 active attempt={attempt_id!r}")
        event = _finish_attempt(run, matches[0], args.outcome, args.reason, at)
        history["updated_at"] = at
        write_history(path, history)
    return _output(
        "attempt-finish",
        path,
        run_id=args.run_id,
        attempt_id=attempt_id,
        duration_seconds=event["duration_seconds"],
        idempotent=False,
    )


def command_event(repository: Path, args: argparse.Namespace) -> dict[str, Any]:
    at, _ = parse_time(args.at)
    event_key = validate_token(args.event_key, "event_key", EVENT_KEY_RE)
    stories = [validate_token(story, "story", STORY_RE) for story in args.story]
    path = history_path(repository)
    with history_lock(repository, exclusive=True):
        history = load_history(path)
        run = _load_active_for_mutation(history, args.run_id)
        plan_ref = normalize_plan_ref(repository, args.plan_ref or run["plan_ref"])
        if args.type == "plan-change" and args.change is None:
            raise HistoryError("plan-change event 必须传 --change")
        if args.type != "plan-change" and args.change is not None:
            raise HistoryError("只有 plan-change event 可以传 --change")
        if args.type == "blocked" and args.reason == "none":
            raise HistoryError("blocked event 必须传非 none --reason")
        if args.type == "checkpoint" and not stories:
            raise HistoryError("checkpoint event 至少传一个 --story")
        git_facts = _git_local_facts(repository) if args.type == "checkpoint" else None
        semantic = {
            "type": args.type,
            "stories": stories,
            "change": args.change,
            "reason": args.reason,
            "plan_ref": plan_ref,
            "git": git_facts,
        }
        key = f"event:{event_key}"
        if not _register_mutation(run, key, semantic):
            return _output(
                "event", path, run_id=args.run_id, event_key=event_key, idempotent=True
            )
        event = {"time": at, "event": args.type, **semantic}
        if args.type == "plan-change":
            _increment(run["metrics"]["plan_changes"], args.change)
        elif args.type == "blocked":
            run["metrics"]["blocked_events"] += 1
        else:
            run["metrics"]["checkpoints"] += 1
        _append_event(run, event)
        history["updated_at"] = at
        write_history(path, history)
    return _output(
        "event", path, run_id=args.run_id, event_key=event_key, idempotent=False
    )


def command_finish(repository: Path, args: argparse.Namespace) -> dict[str, Any]:
    at, _ = parse_time(args.at)
    if args.outcome == "abandoned" and args.reason == "none":
        raise HistoryError("abandoned run 必须传非 none --reason")
    if args.outcome == "delivered" and args.reason != "none":
        raise HistoryError("delivered run 的 reason 必须是 none")
    path = history_path(repository)
    with history_lock(repository, exclusive=True):
        history = load_history(path)
        run = _find_run(history, validate_token(args.run_id, "run_id", RUN_ID_RE))
        if run["outcome"] in TERMINAL_OUTCOMES:
            if run["outcome"] == args.outcome and run["terminal_reason"] == args.reason:
                return _output(
                    "finish", path, run_id=args.run_id, outcome=args.outcome, idempotent=True
                )
            raise HistoryError(f"run 已结束为 {run['outcome']}，不能改写 terminal outcome")
        if args.plan_ref is not None:
            normalize_plan_ref(repository, args.plan_ref)
        if args.outcome == "delivered" and run["active_attempts"]:
            active_ids = [item["attempt_id"] for item in run["active_attempts"]]
            raise HistoryError(f"delivered 前仍有 active attempts: {active_ids}")
        if args.outcome == "abandoned":
            for attempt in list(run["active_attempts"]):
                semantic = {
                    "attempt_id": attempt["attempt_id"],
                    "outcome": "failed",
                    "reason": "abandoned",
                }
                _register_mutation(
                    run,
                    f"attempt-finish:{attempt['attempt_id']}",
                    semantic,
                    consume_attempt_reservation=True,
                )
                _finish_attempt(run, attempt, "failed", "abandoned", at)
        plan_gate = None
        if args.outcome == "delivered":
            plan_gate = _plan_completion_gate(repository, run, args)
            delivery = _git_delivery_facts(
                repository,
                run["baseline"],
                str(plan_gate["head"]),
            )
            post_delivery_status = _run_git(
                repository,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--",
                str(plan_gate["root"]),
            )
            if post_delivery_status.stdout:
                raise HistoryError("查询远端交付事实期间计划目录发生变化")
        else:
            delivery = {**_git_local_facts(repository), "pushed": False}
        run["outcome"] = args.outcome
        run["terminal_reason"] = args.reason
        run["ended_at"] = at
        run["delivery"] = delivery
        _append_event(
            run,
            {
                "time": at,
                "event": "run-finish",
                "outcome": args.outcome,
                "reason": args.reason,
                "plan_ref": run["plan_ref"],
                "delivery": delivery,
            },
        )
        history["updated_at"] = at
        _roll_terminal_runs(history)
        write_history(path, history)
    return _output(
        "finish",
        path,
        run_id=args.run_id,
        outcome=args.outcome,
        delivery=delivery,
        plan_gate=plan_gate,
        idempotent=False,
    )


def _combined_counts(history: dict[str, Any]) -> dict[str, Any]:
    rollup = deepcopy(history["rollup"])
    recent_agents: dict[str, int] = {}
    recent_stories: dict[str, int] = {}
    for run in history["runs"]:
        metrics = run["metrics"]
        if run["outcome"] in TERMINAL_OUTCOMES:
            rollup["terminal_runs"] += 1
            _increment(rollup["run_outcomes"], run["outcome"])
        rollup["attempts"] += metrics["attempts"]
        rollup["attempt_seconds"] += metrics["attempt_seconds"]
        for field in ("by_role", "by_outcome", "by_reason", "plan_changes"):
            _merge_count_maps(rollup[field], metrics[field])
        rollup["blocked_events"] += metrics["blocked_events"]
        rollup["checkpoints"] += metrics["checkpoints"]
        _merge_count_maps(recent_agents, metrics["by_agent"])
        _merge_count_maps(recent_stories, metrics["by_story"])
    return {
        "lifetime_fixed_dimensions": rollup,
        "recent_window_agents": recent_agents,
        "recent_window_story_attempts": recent_stories,
    }


def _review_focus(combined: dict[str, Any]) -> list[dict[str, Any]]:
    totals = combined["lifetime_fixed_dimensions"]
    terminal = totals["terminal_runs"]
    focus: list[dict[str, Any]] = []
    if terminal < 3:
        focus.append(
            {
                "code": "insufficient-data",
                "numerator": terminal,
                "denominator": 3,
                "window": "lifetime",
                "question": "样本不足；先积累至少 3 个 terminal run，再判断长期趋势。",
            }
        )
    abandoned = totals["run_outcomes"].get("abandoned", 0)
    if abandoned:
        focus.append(
            {
                "code": "abandoned-runs",
                "numerator": abandoned,
                "denominator": max(terminal, 1),
                "window": "lifetime",
                "question": "对照 plan_ref 与 Git 证据，区分目标变化、权限和环境导致的放弃。",
            }
        )
    route_failures = sum(
        totals["by_reason"].get(reason, 0)
        for reason in ("quota", "route", "provider", "session")
    )
    if route_failures:
        focus.append(
            {
                "code": "route-reliability",
                "numerator": route_failures,
                "denominator": max(totals["attempts"], 1),
                "window": "lifetime",
                "question": "比较近期 subagent 与失败原因，检查派发边界和恢复策略。",
            }
        )
    reviewer_rework = sum(
        totals["by_outcome"].get(outcome, 0)
        for outcome in ("patch-prompt", "insert-story", "replan")
    )
    if reviewer_rework:
        review_attempts = sum(
            totals["by_role"].get(role, 0) for role in ("reviewer", "validator")
        )
        focus.append(
            {
                "code": "reviewer-rework",
                "numerator": reviewer_rework,
                "denominator": max(review_attempts, 1),
                "window": "lifetime",
                "question": "回看对应 Story 验收和 worker prompt，判断是拆分、计划输入还是实现偏差。",
            }
        )
    plan_changes = sum(totals["plan_changes"].values())
    if plan_changes:
        focus.append(
            {
                "code": "plan-volatility",
                "numerator": plan_changes,
                "denominator": max(terminal, 1),
                "window": "lifetime",
                "question": "按 plan_ref 检查哪些初始假设反复失效，以及是否应前移验证。",
            }
        )
    if totals["blocked_events"]:
        focus.append(
            {
                "code": "blocked-episodes",
                "numerator": totals["blocked_events"],
                "denominator": max(terminal, 1),
                "window": "lifetime",
                "question": "按 reason 检查 readiness、权限和环境预检能否更早发现阻塞。",
            }
        )
    return focus


def command_show(repository: Path, args: argparse.Namespace) -> dict[str, Any]:
    path = history_path(repository)
    with history_lock(repository, exclusive=False):
        history = load_history(path)
        if args.run_id:
            run = deepcopy(_find_run(history, validate_token(args.run_id, "run_id", RUN_ID_RE)))
            return _output(
                "show",
                path,
                scope=history["scope"],
                run=run,
                recovery_order=["agent-json", "git", "history"],
            )
        combined = _combined_counts(history)
        runs = [
            {
                "run_id": run["run_id"],
                "plan_ref": run["plan_ref"],
                "started_at": run["started_at"],
                "ended_at": run["ended_at"],
                "outcome": run["outcome"],
                "metrics": run["metrics"],
                "compacted_events": run["compacted_events"],
                "active_attempts": run["active_attempts"],
                "delivery": run["delivery"],
            }
            for run in history["runs"]
        ]
        story_hotspots = sorted(
            combined["recent_window_story_attempts"].items(),
            key=lambda item: (-item[1], item[0]),
        )[:5]
        return _output(
            "show",
            path,
            scope=history["scope"],
            retention=history["retention"],
            recovery_order=["agent-json", "git", "history"],
            runs=runs,
            aggregate=combined,
            recent_story_hotspots=[
                {"story": story, "attempts": attempts}
                for story, attempts in story_hotspots
            ],
            review_focus=_review_focus(combined),
        )


def command_check(repository: Path) -> dict[str, Any]:
    path = history_path(repository)
    with history_lock(repository, exclusive=False):
        history = load_history(path)
    active = _active_run(history)
    active_run_id: str | None = None
    if active is not None:
        active_run_id = str(cast(dict[str, Any], active)["run_id"])
    return _output(
        "check",
        path,
        schema_version=history["schema_version"],
        active_run=active_run_id,
        retained_runs=len(history["runs"]),
        rolled_up_runs=history["rollup"]["terminal_runs"],
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        repository = resolve_repository(args.repository)
        if args.command == "start":
            result = command_start(repository, args)
        elif args.command == "attempt" and args.attempt_command == "start":
            result = command_attempt_start(repository, args)
        elif args.command == "attempt" and args.attempt_command == "finish":
            result = command_attempt_finish(repository, args)
        elif args.command == "event":
            result = command_event(repository, args)
        elif args.command == "finish":
            result = command_finish(repository, args)
        elif args.command == "show":
            result = command_show(repository, args)
        elif args.command == "check":
            result = command_check(repository)
        else:  # argparse 的 required subparsers 应使该分支不可达。
            raise HistoryError("未识别命令")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except HistoryError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except (KeyError, TypeError, ValueError) as error:
        print(f"ERROR: 运行历史结构损坏，已保留原文件: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
