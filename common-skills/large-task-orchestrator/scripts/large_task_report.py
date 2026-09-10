#!/usr/bin/env python3
"""提交和读取 large-task Worker 的结构化报告。

定义：Worker 用 ``worker`` 子命令从 stdin 或 JSON 文件提交报告；Driver 用
``read-worker`` 按 Story、attempt 和 intent version 读取同一报告。脚本严格校验
字段、枚举、长度和相对路径，成功后以 0600 权限原子写入 JSON。

输出：成功提交时打印报告路径和 SHA256；读取时向 stdout 输出 canonical JSON。
schema、身份或文件错误写入 stderr 并返回退出码 2。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA_VERSION = 1
RESULTS = ("worker_done", "blocked", "failed")
VERIFICATION_OUTCOMES = ("passed", "failed", "not_run")
REPORT_FIELDS = {"result", "changes", "verification", "remaining", "handoff"}
ENVELOPE_FIELDS = {
    "schema_version", "role", "story_id", "attempt", "intent_version", "submitted_at", "report",
}
ITEM_LIMIT = 8
SUMMARY_LIMIT = 400
COMMAND_LIMIT = 1000
HANDOFF_LIMIT = 400
STORY_PATTERN = re.compile(r"^STORY-[A-Za-z0-9.-]+$")


class ReportError(ValueError):
    """报告不满足可恢复执行所需的 schema 或身份约束。"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReportError(f"{label} must be a JSON object")
    return value


def require_exact_fields(value: dict[str, Any], expected: set[str], label: str) -> None:
    missing = sorted(expected - value.keys())
    unknown = sorted(value.keys() - expected)
    if missing:
        raise ReportError(f"{label} missing field(s): {', '.join(missing)}")
    if unknown:
        raise ReportError(f"{label} has unknown field(s): {', '.join(unknown)}")


def require_text(value: Any, label: str, *, limit: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ReportError(f"{label} must be a string")
    text = value.strip()
    if not text and not allow_empty:
        raise ReportError(f"{label} must not be empty")
    if len(text) > limit:
        raise ReportError(f"{label} exceeds {limit} characters")
    return text


def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ReportError(f"{label} must be an array")
    if len(value) > ITEM_LIMIT:
        raise ReportError(f"{label} contains more than {ITEM_LIMIT} items")
    return value


def validate_change_path(value: Any, label: str) -> str:
    path = require_text(value, label, limit=500)
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or "\\" in path or any(part in ("", ".", "..") for part in candidate.parts):
        raise ReportError(f"{label} must be a normalized repository-relative path")
    return candidate.as_posix()


def validate_worker_report(value: Any) -> dict[str, Any]:
    report = require_object(value, "report")
    require_exact_fields(report, REPORT_FIELDS, "report")

    result = report["result"]
    if result not in RESULTS:
        raise ReportError(f"report.result must be one of: {', '.join(RESULTS)}")

    changes = []
    seen_paths: set[str] = set()
    for index, raw in enumerate(require_list(report["changes"], "report.changes")):
        item = require_object(raw, f"report.changes[{index}]")
        require_exact_fields(item, {"path", "summary"}, f"report.changes[{index}]")
        path = validate_change_path(item["path"], f"report.changes[{index}].path")
        if path in seen_paths:
            raise ReportError(f"report.changes contains duplicate path: {path}")
        seen_paths.add(path)
        changes.append({
            "path": path,
            "summary": require_text(item["summary"], f"report.changes[{index}].summary", limit=SUMMARY_LIMIT),
        })

    verification = []
    for index, raw in enumerate(require_list(report["verification"], "report.verification")):
        item = require_object(raw, f"report.verification[{index}]")
        require_exact_fields(item, {"command", "outcome", "summary"}, f"report.verification[{index}]")
        outcome = item["outcome"]
        if outcome not in VERIFICATION_OUTCOMES:
            raise ReportError(
                f"report.verification[{index}].outcome must be one of: {', '.join(VERIFICATION_OUTCOMES)}"
            )
        verification.append({
            "command": require_text(item["command"], f"report.verification[{index}].command", limit=COMMAND_LIMIT),
            "outcome": outcome,
            "summary": require_text(
                item["summary"], f"report.verification[{index}].summary", limit=SUMMARY_LIMIT
            ),
        })

    remaining = [
        require_text(item, f"report.remaining[{index}]", limit=SUMMARY_LIMIT)
        for index, item in enumerate(require_list(report["remaining"], "report.remaining"))
    ]
    if result == "worker_done" and not verification:
        raise ReportError("worker_done requires at least one verification item")
    if result in ("blocked", "failed") and not remaining:
        raise ReportError(f"{result} requires at least one remaining item")

    return {
        "result": result,
        "changes": changes,
        "verification": verification,
        "remaining": remaining,
        "handoff": require_text(report["handoff"], "report.handoff", limit=HANDOFF_LIMIT),
    }


def validate_identity(story_id: str, attempt: int, intent_version: int) -> None:
    if not STORY_PATTERN.fullmatch(story_id):
        raise ReportError("story_id must match STORY-<id>")
    if attempt < 1:
        raise ReportError("attempt must be a positive integer")
    if intent_version < 1:
        raise ReportError("intent_version must be a positive integer")


def build_envelope(report: Any, *, story_id: str, attempt: int, intent_version: int) -> dict[str, Any]:
    validate_identity(story_id, attempt, intent_version)
    return {
        "schema_version": SCHEMA_VERSION,
        "role": "worker",
        "story_id": story_id,
        "attempt": attempt,
        "intent_version": intent_version,
        "submitted_at": utc_now(),
        "report": validate_worker_report(report),
    }


def validate_envelope(
    value: Any, *, story_id: str, attempt: int, intent_version: int,
) -> dict[str, Any]:
    envelope = require_object(value, "envelope")
    require_exact_fields(envelope, ENVELOPE_FIELDS, "envelope")
    if envelope["schema_version"] != SCHEMA_VERSION:
        raise ReportError(f"schema_version must be {SCHEMA_VERSION}")
    if envelope["role"] != "worker":
        raise ReportError("role must be worker")
    validate_identity(story_id, attempt, intent_version)
    for field, expected in (("story_id", story_id), ("attempt", attempt), ("intent_version", intent_version)):
        if envelope[field] != expected:
            raise ReportError(f"{field} mismatch: expected {expected!r}, got {envelope[field]!r}")
    require_text(envelope["submitted_at"], "submitted_at", limit=64)
    envelope["report"] = validate_worker_report(envelope["report"])
    return envelope


def read_json_input(source: str) -> Any:
    if source == "-":
        return json.load(sys.stdin)
    with Path(source).open(encoding="utf-8") as handle:
        return json.load(handle)


def atomic_write(path: Path, value: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command_worker(args: argparse.Namespace) -> int:
    output = Path(args.output).resolve()
    # A rejected resubmission must not leave an earlier report consumable.
    output.unlink(missing_ok=True)
    envelope = build_envelope(
        read_json_input(args.source), story_id=args.story_id,
        attempt=args.attempt, intent_version=args.intent_version,
    )
    digest = atomic_write(output, envelope)
    print(f"WORKER_REPORT_WRITTEN: {output}")
    print(f"SHA256: {digest}")
    return 0


def command_read_worker(args: argparse.Namespace) -> int:
    path = Path(args.file).resolve()
    with path.open(encoding="utf-8") as handle:
        envelope = json.load(handle)
    validated = validate_envelope(
        envelope, story_id=args.story_id, attempt=args.attempt, intent_version=args.intent_version,
    )
    print(json.dumps(validated, ensure_ascii=False))
    return 0


def add_identity_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--story-id", required=True, help="当前 Story ID，例如 STORY-03")
    parser.add_argument("--attempt", required=True, type=int, help="当前 Worker attempt，必须为正整数")
    parser.add_argument("--intent-version", required=True, type=int, help="当前 Story intent_version")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="严格校验并原子保存 large-task Worker 报告。",
        epilog="""输出:
  worker 成功时打印目标路径与 SHA256；read-worker 成功时打印 canonical JSON；错误返回 2。

示例:
  python3 large_task_report.py worker --output /tmp/worker.json --story-id STORY-03 --attempt 1 --intent-version 2 < report.json
  python3 large_task_report.py read-worker --file /tmp/worker.json --story-id STORY-03 --attempt 1 --intent-version 2
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)

    worker = commands.add_parser("worker", help="从 JSON 输入提交 Worker 报告")
    worker.add_argument("--output", required=True, help="Driver 指定的报告文件路径")
    worker.add_argument("--from", dest="source", default="-", help="输入 JSON；默认 - 表示 stdin")
    add_identity_arguments(worker)
    worker.set_defaults(handler=command_worker)

    reader = commands.add_parser("read-worker", help="校验已提交报告及其执行身份")
    reader.add_argument("--file", required=True, help="报告文件路径")
    add_identity_arguments(reader)
    reader.set_defaults(handler=command_read_worker)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        return int(args.handler(args))
    except (ReportError, OSError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
