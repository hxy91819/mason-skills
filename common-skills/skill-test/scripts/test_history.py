#!/usr/bin/env python3
"""Maintain bounded local history for native-subagent skill tests.

Definition: stores only stable test identity, engine/model, duration, outcome,
context isolation, and the main agent's disposition. It never stores prompts,
responses, diffs, logs, paths, or secrets.
Parameters: use ``record``, ``decide``, ``show``, or ``check``; ``--history``
overrides the XDG cache path for tests and diagnostics.
Outputs: successful commands print JSON. Exit 0 means success, 1 means invalid
history or operation, and 2 means invalid CLI arguments.
Examples:
  python3 test_history.py record --test-id demo-1 --skill demo --engine codex \
    --model small --model-class non-frontier --duration-ms 1200 \
    --outcome passed --context-isolated yes
  python3 test_history.py decide --test-id demo-1 --disposition accepted
  python3 test_history.py show

History writes are atomic and locked. A caller should treat recording failures as
warnings so observability never changes the behavior-test conclusion.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import sys
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


SCHEMA_VERSION = 1
MAX_RECENT = 50
MAX_RETIRED_IDS = 200
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SKILL_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+/@:-]{0,127}$")
OUTCOMES = ("passed", "partial", "failed", "infrastructure-failed")
DISPOSITIONS = ("accepted", "rejected")
MODEL_CLASSES = ("non-frontier", "frontier", "unknown")
ISOLATION_VALUES = ("yes", "no", "unknown")


class HistoryError(RuntimeError):
    """The stored history or requested mutation violates the contract."""


def default_history_path() -> Path:
    cache_root = os.environ.get("XDG_CACHE_HOME")
    base = Path(cache_root).expanduser() if cache_root else Path.home() / ".cache"
    return base / "skill-test" / "history.json"


def usage() -> str:
    return f"""用法:
  python3 test_history.py [--history <path>] record <options>
  python3 test_history.py [--history <path>] decide <options>
  python3 test_history.py [--history <path>] show
  python3 test_history.py [--history <path>] check

说明:
  维护原生 subagent skill 测试的最小滚动历史。默认文件为
  {default_history_path()}。不记录 prompt、回复、diff、日志、路径或密钥。

参数:
  --history <path>         覆盖默认历史路径，主要用于测试。
  record                   记录或覆盖 recent 窗口中的稳定 test ID。
  decide                   回写 accepted/rejected；未知或已滚出的 ID 会拒绝。
  show                     输出 live + rollup 聚合和确定性复盘关注项。
  check                    只读校验 schema、上限、唯一性和计数。

输出:
  成功时 stdout 输出 JSON。退出码 0=成功，1=历史或操作错误，2=参数错误。
  最多保留 {MAX_RECENT} 条 recent 记录；更旧记录只进入固定维度 rollup，
  并保留最近 {MAX_RETIRED_IDS} 个 retired ID 防止重试双计。

示例:
  python3 test_history.py record --test-id demo-1 --skill demo --engine codex \
    --model small --model-class non-frontier --duration-ms 1200 \
    --outcome passed --context-isolated yes
  python3 test_history.py decide --test-id demo-1 --disposition accepted
  python3 test_history.py show
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="维护 skill-test 的最小滚动运行历史。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=usage(),
    )
    parser.add_argument("--history", type=Path, default=default_history_path())
    commands = parser.add_subparsers(dest="command", required=True)

    record = commands.add_parser("record", help="记录一次 skill 测试")
    record.add_argument("--test-id", required=True)
    record.add_argument("--skill", required=True)
    record.add_argument("--engine", required=True)
    record.add_argument("--model", required=True)
    record.add_argument("--model-class", required=True, choices=MODEL_CLASSES)
    record.add_argument("--duration-ms", required=True, type=int)
    record.add_argument("--outcome", required=True, choices=OUTCOMES)
    record.add_argument("--context-isolated", required=True, choices=ISOLATION_VALUES)
    record.add_argument("--at", help="带时区的 ISO-8601 时间；默认当前 UTC")

    decide = commands.add_parser("decide", help="回写主 Agent 对测试证据的裁决")
    decide.add_argument("--test-id", required=True)
    decide.add_argument("--disposition", required=True, choices=DISPOSITIONS)

    commands.add_parser("show", help="显示聚合统计与复盘关注项")
    commands.add_parser("check", help="校验历史文件")
    return parser


def empty_counts(keys: tuple[str, ...]) -> dict[str, int]:
    return {key: 0 for key in keys}


def empty_bucket() -> dict[str, Any]:
    return {
        "runs": 0,
        "duration_ms": 0,
        "outcomes": empty_counts(OUTCOMES),
        "dispositions": {"accepted": 0, "rejected": 0, "pending": 0},
        "context_isolated": empty_counts(ISOLATION_VALUES),
    }


def empty_rollup() -> dict[str, Any]:
    return {
        "total": empty_bucket(),
        "by_model_class": {key: empty_bucket() for key in MODEL_CLASSES},
    }


def empty_history() -> dict[str, Any]:
    return {
        "version": SCHEMA_VERSION,
        "recent": [],
        "retired_ids": [],
        "rollup": empty_rollup(),
        "updated_at": None,
    }


def parse_time(value: str | None) -> str:
    if value is None:
        parsed = datetime.now(timezone.utc)
    else:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as error:
            raise HistoryError(f"invalid ISO-8601 time: {value}") from error
        if parsed.tzinfo is None:
            raise HistoryError("time must include a timezone")
        parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")


def validate_token(value: str, label: str, pattern: re.Pattern[str] = TOKEN_RE) -> str:
    if not pattern.fullmatch(value):
        raise HistoryError(f"invalid {label}: {value!r}")
    return value


def validate_bucket(bucket: Any, label: str) -> None:
    if not isinstance(bucket, dict):
        raise HistoryError(f"{label} must be an object")
    if type(bucket.get("runs")) is not int or bucket["runs"] < 0:
        raise HistoryError(f"{label}.runs must be a non-negative integer")
    if type(bucket.get("duration_ms")) is not int or bucket["duration_ms"] < 0:
        raise HistoryError(f"{label}.duration_ms must be a non-negative integer")
    expected = {
        "outcomes": OUTCOMES,
        "dispositions": ("accepted", "rejected", "pending"),
        "context_isolated": ISOLATION_VALUES,
    }
    for field, keys in expected.items():
        counts = bucket.get(field)
        if not isinstance(counts, dict) or set(counts) != set(keys):
            raise HistoryError(f"{label}.{field} has invalid dimensions")
        if any(type(counts[key]) is not int or counts[key] < 0 for key in keys):
            raise HistoryError(f"{label}.{field} counts must be non-negative integers")
        if sum(counts.values()) != bucket["runs"]:
            raise HistoryError(f"{label}.{field} does not sum to runs")


def validate_record(record: Any) -> None:
    if not isinstance(record, dict):
        raise HistoryError("recent records must be objects")
    validate_token(record.get("test_id", ""), "test_id", ID_RE)
    validate_token(record.get("skill", ""), "skill", SKILL_RE)
    validate_token(record.get("engine", ""), "engine")
    validate_token(record.get("model", ""), "model")
    if record.get("model_class") not in MODEL_CLASSES:
        raise HistoryError("invalid stored model_class")
    if record.get("outcome") not in OUTCOMES:
        raise HistoryError("invalid stored outcome")
    if record.get("context_isolated") not in ISOLATION_VALUES:
        raise HistoryError("invalid stored context_isolated")
    if record.get("disposition") not in (*DISPOSITIONS, None):
        raise HistoryError("invalid stored disposition")
    if type(record.get("duration_ms")) is not int or record["duration_ms"] < 0:
        raise HistoryError("duration_ms must be a non-negative integer")
    parse_time(record.get("recorded_at"))


def validate_history(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("version") != SCHEMA_VERSION:
        raise HistoryError("unsupported or invalid history schema")
    recent = data.get("recent")
    retired = data.get("retired_ids")
    rollup = data.get("rollup")
    if not isinstance(recent, list) or len(recent) > MAX_RECENT:
        raise HistoryError("recent window exceeds its bound")
    if not isinstance(retired, list) or len(retired) > MAX_RETIRED_IDS:
        raise HistoryError("retired ID window exceeds its bound")
    for record in recent:
        validate_record(record)
    for test_id in retired:
        validate_token(test_id, "retired test_id", ID_RE)
    recent_ids = [record["test_id"] for record in recent]
    if len(recent_ids) != len(set(recent_ids)) or len(retired) != len(set(retired)):
        raise HistoryError("test IDs must be unique within each window")
    if set(recent_ids) & set(retired):
        raise HistoryError("recent and retired IDs overlap")
    if not isinstance(rollup, dict) or set(rollup) != {"total", "by_model_class"}:
        raise HistoryError("invalid rollup dimensions")
    validate_bucket(rollup["total"], "rollup.total")
    by_class = rollup["by_model_class"]
    if not isinstance(by_class, dict) or set(by_class) != set(MODEL_CLASSES):
        raise HistoryError("invalid rollup.by_model_class dimensions")
    for model_class in MODEL_CLASSES:
        validate_bucket(by_class[model_class], f"rollup.by_model_class.{model_class}")
    if sum(by_class[key]["runs"] for key in MODEL_CLASSES) != rollup["total"]["runs"]:
        raise HistoryError("model-class rollup does not sum to total")
    if data.get("updated_at") is not None:
        parse_time(data["updated_at"])
    return data


def load_history(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_history()
    if path.is_symlink() or not path.is_file():
        raise HistoryError("history path must be a regular non-symlink file")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HistoryError(f"cannot read history: {error}") from error
    return validate_history(data)


def lock_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.lock")


@contextlib.contextmanager
def locked(path: Path, *, exclusive: bool) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.is_symlink():
        raise HistoryError("history parent must not be a symlink")
    lock = lock_path(path)
    if lock.is_symlink() or (lock.exists() and not lock.is_file()):
        raise HistoryError("lock path must be a regular non-symlink file")
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def write_history(path: Path, data: dict[str, Any]) -> None:
    validate_history(data)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as error:
        raise HistoryError(f"cannot write history: {error}") from error
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def add_record(bucket: dict[str, Any], record: dict[str, Any]) -> None:
    bucket["runs"] += 1
    bucket["duration_ms"] += record["duration_ms"]
    bucket["outcomes"][record["outcome"]] += 1
    disposition = record["disposition"] or "pending"
    bucket["dispositions"][disposition] += 1
    bucket["context_isolated"][record["context_isolated"]] += 1


def add_to_rollup(rollup: dict[str, Any], record: dict[str, Any]) -> None:
    add_record(rollup["total"], record)
    add_record(rollup["by_model_class"][record["model_class"]], record)


def command_record(args: argparse.Namespace, path: Path) -> dict[str, Any]:
    test_id = validate_token(args.test_id, "test_id", ID_RE)
    record = {
        "test_id": test_id,
        "skill": validate_token(args.skill, "skill", SKILL_RE),
        "engine": validate_token(args.engine, "engine"),
        "model": validate_token(args.model, "model"),
        "model_class": args.model_class,
        "duration_ms": args.duration_ms,
        "outcome": args.outcome,
        "context_isolated": args.context_isolated,
        "disposition": None,
        "recorded_at": parse_time(args.at),
    }
    if record["duration_ms"] < 0:
        raise HistoryError("duration_ms must be non-negative")
    with locked(path, exclusive=True):
        data = load_history(path)
        if test_id in data["retired_ids"]:
            raise HistoryError("test_id has already rolled up; use a new stable ID")
        existing = next(
            (item for item in data["recent"] if item["test_id"] == test_id), None
        )
        if existing is not None:
            record["disposition"] = existing["disposition"]
            data["recent"][data["recent"].index(existing)] = record
        else:
            data["recent"].append(record)
        while len(data["recent"]) > MAX_RECENT:
            retired = data["recent"].pop(0)
            add_to_rollup(data["rollup"], retired)
            data["retired_ids"].append(retired["test_id"])
            data["retired_ids"] = data["retired_ids"][-MAX_RETIRED_IDS:]
        data["updated_at"] = record["recorded_at"]
        write_history(path, data)
    return {"ok": True, "test_id": test_id, "history": str(path)}


def command_decide(args: argparse.Namespace, path: Path) -> dict[str, Any]:
    test_id = validate_token(args.test_id, "test_id", ID_RE)
    with locked(path, exclusive=True):
        data = load_history(path)
        record = next(
            (item for item in data["recent"] if item["test_id"] == test_id), None
        )
        if record is None:
            raise HistoryError("unknown or retired test_id; disposition was not recorded")
        record["disposition"] = args.disposition
        data["updated_at"] = parse_time(None)
        write_history(path, data)
    return {
        "ok": True,
        "test_id": test_id,
        "disposition": args.disposition,
        "history": str(path),
    }


def aggregate(data: dict[str, Any]) -> dict[str, Any]:
    combined = deepcopy(data["rollup"])
    for record in data["recent"]:
        add_to_rollup(combined, record)
    return combined


def retrospective_hooks(combined: dict[str, Any]) -> list[dict[str, Any]]:
    total = combined["total"]
    hooks: list[dict[str, Any]] = []
    decided = total["dispositions"]["accepted"] + total["dispositions"]["rejected"]
    if decided >= 4:
        acceptance_rate = total["dispositions"]["accepted"] / decided
        if acceptance_rate < 0.5:
            hooks.append(
                {"kind": "low-acceptance-rate", "numerator": total["dispositions"]["accepted"], "denominator": decided}
            )
    if total["runs"] >= 4:
        infrastructure_failures = total["outcomes"]["infrastructure-failed"]
        if infrastructure_failures / total["runs"] > 0.25:
            hooks.append(
                {"kind": "high-infrastructure-failure-rate", "numerator": infrastructure_failures, "denominator": total["runs"]}
            )
    isolation_gaps = total["context_isolated"]["no"] + total["context_isolated"]["unknown"]
    if isolation_gaps:
        hooks.append(
            {"kind": "context-isolation-gaps", "numerator": isolation_gaps, "denominator": total["runs"]}
        )
    pending = total["dispositions"]["pending"]
    if pending:
        hooks.append({"kind": "pending-dispositions", "count": pending})
    return hooks


def command_show(path: Path) -> dict[str, Any]:
    with locked(path, exclusive=False):
        data = load_history(path)
    combined = aggregate(data)
    return {
        "history": str(path),
        "recent_count": len(data["recent"]),
        "retired_id_count": len(data["retired_ids"]),
        "aggregate": combined,
        "retrospective_hooks": retrospective_hooks(combined),
    }


def command_check(path: Path) -> dict[str, Any]:
    with locked(path, exclusive=False):
        data = load_history(path)
    validate_history(data)
    return {
        "ok": True,
        "history": str(path),
        "recent_count": len(data["recent"]),
        "rolled_count": data["rollup"]["total"]["runs"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    path = args.history.expanduser().resolve()
    try:
        if args.command == "record":
            result = command_record(args, path)
        elif args.command == "decide":
            result = command_decide(args, path)
        elif args.command == "show":
            result = command_show(path)
        else:
            result = command_check(path)
    except HistoryError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
