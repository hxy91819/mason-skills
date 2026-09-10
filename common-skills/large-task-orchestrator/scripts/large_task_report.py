#!/usr/bin/env python3
"""提交和读取 large-task Worker / Validator / Judge 的结构化报告。

定义：执行线程用对应的角色子命令从 stdin / JSON 文件提交报告；Driver 用
``read-*`` 命令按 Story、attempt、intent version 和角色 round 读取。脚本严格校验
字段、枚举、长度、Acceptance 集合和相对路径，成功后以 0600 权限原子写入 JSON。

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
VALIDATOR_VERDICTS = ("PASS", "FAIL")
ACCEPTANCE_OUTCOMES = ("holds", "missing")
JUDGE_ACTIONS = ("retry", "escalate", "patch", "block", "replan", "stop")
WORKER_REPORT_FIELDS = {"result", "changes", "verification", "remaining", "handoff"}
VALIDATOR_REPORT_FIELDS = {"verdict", "acceptance", "gaps", "new_facts"}
JUDGE_REPORT_FIELDS = {"action", "note"}
BASE_ENVELOPE_FIELDS = {
    "schema_version", "role", "story_id", "attempt", "intent_version", "submitted_at", "report",
}
WORKER_ENVELOPE_FIELDS = BASE_ENVELOPE_FIELDS
VALIDATOR_ENVELOPE_FIELDS = BASE_ENVELOPE_FIELDS | {"validation_round"}
JUDGE_ENVELOPE_FIELDS = BASE_ENVELOPE_FIELDS | {"judge_round"}
ITEM_LIMIT = 8
ACCEPTANCE_LIMIT = 32
SUMMARY_LIMIT = 400
COMMAND_LIMIT = 1000
HANDOFF_LIMIT = 400
STORY_PATTERN = re.compile(r"^STORY-[A-Za-z0-9.-]+$")
ACCEPTANCE_PATTERN = re.compile(r"^AC-[A-Za-z0-9.-]+$")


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


def require_acceptance_ids(values: list[str]) -> list[str]:
    if not values:
        raise ReportError("at least one acceptance_id is required")
    if len(values) > ACCEPTANCE_LIMIT:
        raise ReportError(f"acceptance_ids contains more than {ACCEPTANCE_LIMIT} items")
    result: list[str] = []
    for value in values:
        if not ACCEPTANCE_PATTERN.fullmatch(value):
            raise ReportError(f"invalid acceptance_id: {value!r}")
        if value in result:
            raise ReportError(f"duplicate acceptance_id: {value}")
        result.append(value)
    return result


def validate_change_path(value: Any, label: str) -> str:
    path = require_text(value, label, limit=500)
    candidate = PurePosixPath(path)
    unsafe_parts = any(part in ("", ".", "..") for part in candidate.parts)
    if candidate.is_absolute() or "\\" in path or candidate.as_posix() != path or unsafe_parts:
        raise ReportError(f"{label} must be a normalized repository-relative path")
    return candidate.as_posix()


def require_identity_match(envelope: dict[str, Any], field: str, expected: Any) -> None:
    actual = envelope[field]
    if type(actual) is not type(expected) or actual != expected:
        raise ReportError(f"{field} mismatch: expected {expected!r}, got {actual!r}")


def validate_worker_report(value: Any) -> dict[str, Any]:
    report = require_object(value, "report")
    require_exact_fields(report, WORKER_REPORT_FIELDS, "report")

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


def validate_validator_report(value: Any, *, acceptance_ids: list[str]) -> dict[str, Any]:
    expected_ids = require_acceptance_ids(acceptance_ids)
    report = require_object(value, "report")
    require_exact_fields(report, VALIDATOR_REPORT_FIELDS, "report")
    verdict = report["verdict"]
    if verdict not in VALIDATOR_VERDICTS:
        raise ReportError(f"report.verdict must be one of: {', '.join(VALIDATOR_VERDICTS)}")

    raw_acceptance = report["acceptance"]
    if not isinstance(raw_acceptance, list):
        raise ReportError("report.acceptance must be an array")
    if len(raw_acceptance) > ACCEPTANCE_LIMIT:
        raise ReportError(f"report.acceptance contains more than {ACCEPTANCE_LIMIT} items")
    acceptance = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_acceptance):
        item = require_object(raw, f"report.acceptance[{index}]")
        require_exact_fields(item, {"id", "outcome", "evidence"}, f"report.acceptance[{index}]")
        acceptance_id = require_text(item["id"], f"report.acceptance[{index}].id", limit=100)
        if acceptance_id in seen_ids:
            raise ReportError(f"report.acceptance contains duplicate id: {acceptance_id}")
        seen_ids.add(acceptance_id)
        outcome = item["outcome"]
        if outcome not in ACCEPTANCE_OUTCOMES:
            raise ReportError(
                f"report.acceptance[{index}].outcome must be one of: {', '.join(ACCEPTANCE_OUTCOMES)}"
            )
        acceptance.append({
            "id": acceptance_id,
            "outcome": outcome,
            "evidence": require_text(
                item["evidence"], f"report.acceptance[{index}].evidence", limit=SUMMARY_LIMIT,
            ),
        })
    actual_ids = [item["id"] for item in acceptance]
    if actual_ids != expected_ids:
        raise ReportError(f"report.acceptance ids must exactly equal: {', '.join(expected_ids)}")

    gaps = [
        require_text(item, f"report.gaps[{index}]", limit=SUMMARY_LIMIT)
        for index, item in enumerate(require_list(report["gaps"], "report.gaps"))
    ]
    new_facts = [
        require_text(item, f"report.new_facts[{index}]", limit=SUMMARY_LIMIT)
        for index, item in enumerate(require_list(report["new_facts"], "report.new_facts"))
    ]
    missing = [item["id"] for item in acceptance if item["outcome"] == "missing"]
    if verdict == "PASS" and (missing or gaps):
        raise ReportError("PASS requires every acceptance to hold and gaps to be empty")
    if verdict == "FAIL" and not (missing or gaps):
        raise ReportError("FAIL requires at least one missing acceptance or gap")
    return {"verdict": verdict, "acceptance": acceptance, "gaps": gaps, "new_facts": new_facts}


def validate_judge_report(value: Any) -> dict[str, Any]:
    report = require_object(value, "report")
    require_exact_fields(report, JUDGE_REPORT_FIELDS, "report")
    action = report["action"]
    if action not in JUDGE_ACTIONS:
        raise ReportError(f"report.action must be one of: {', '.join(JUDGE_ACTIONS)}")
    return {"action": action, "note": require_text(report["note"], "report.note", limit=1000)}


def validate_identity(story_id: str, attempt: int, intent_version: int) -> None:
    if not STORY_PATTERN.fullmatch(story_id):
        raise ReportError("story_id must match STORY-<id>")
    if attempt < 1:
        raise ReportError("attempt must be a positive integer")
    if intent_version < 1:
        raise ReportError("intent_version must be a positive integer")


def build_worker_envelope(report: Any, *, story_id: str, attempt: int, intent_version: int) -> dict[str, Any]:
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


def validate_worker_envelope(
    value: Any, *, story_id: str, attempt: int, intent_version: int,
) -> dict[str, Any]:
    envelope = require_object(value, "envelope")
    require_exact_fields(envelope, WORKER_ENVELOPE_FIELDS, "envelope")
    if type(envelope["schema_version"]) is not int or envelope["schema_version"] != SCHEMA_VERSION:
        raise ReportError(f"schema_version must be {SCHEMA_VERSION}")
    if envelope["role"] != "worker":
        raise ReportError("role must be worker")
    validate_identity(story_id, attempt, intent_version)
    for field, expected in (("story_id", story_id), ("attempt", attempt), ("intent_version", intent_version)):
        require_identity_match(envelope, field, expected)
    require_text(envelope["submitted_at"], "submitted_at", limit=64)
    envelope["report"] = validate_worker_report(envelope["report"])
    return envelope


def build_validator_envelope(
    report: Any, *, story_id: str, attempt: int, intent_version: int,
    validation_round: int, acceptance_ids: list[str],
) -> dict[str, Any]:
    validate_identity(story_id, attempt, intent_version)
    if validation_round < 1:
        raise ReportError("validation_round must be a positive integer")
    return {
        "schema_version": SCHEMA_VERSION,
        "role": "validator",
        "story_id": story_id,
        "attempt": attempt,
        "intent_version": intent_version,
        "validation_round": validation_round,
        "submitted_at": utc_now(),
        "report": validate_validator_report(report, acceptance_ids=acceptance_ids),
    }


def validate_validator_envelope(
    value: Any, *, story_id: str, attempt: int, intent_version: int,
    validation_round: int, acceptance_ids: list[str],
) -> dict[str, Any]:
    envelope = require_object(value, "envelope")
    require_exact_fields(envelope, VALIDATOR_ENVELOPE_FIELDS, "envelope")
    if type(envelope["schema_version"]) is not int or envelope["schema_version"] != SCHEMA_VERSION:
        raise ReportError(f"schema_version must be {SCHEMA_VERSION}")
    if envelope["role"] != "validator":
        raise ReportError("role must be validator")
    validate_identity(story_id, attempt, intent_version)
    expected_identity = (
        ("story_id", story_id), ("attempt", attempt), ("intent_version", intent_version),
        ("validation_round", validation_round),
    )
    for field, expected in expected_identity:
        require_identity_match(envelope, field, expected)
    require_text(envelope["submitted_at"], "submitted_at", limit=64)
    envelope["report"] = validate_validator_report(envelope["report"], acceptance_ids=acceptance_ids)
    return envelope


def build_judge_envelope(
    report: Any, *, story_id: str, attempt: int, intent_version: int, judge_round: int,
) -> dict[str, Any]:
    validate_identity(story_id, attempt, intent_version)
    if judge_round < 1:
        raise ReportError("judge_round must be a positive integer")
    return {
        "schema_version": SCHEMA_VERSION,
        "role": "judge",
        "story_id": story_id,
        "attempt": attempt,
        "intent_version": intent_version,
        "judge_round": judge_round,
        "submitted_at": utc_now(),
        "report": validate_judge_report(report),
    }


def validate_judge_envelope(
    value: Any, *, story_id: str, attempt: int, intent_version: int, judge_round: int,
) -> dict[str, Any]:
    envelope = require_object(value, "envelope")
    require_exact_fields(envelope, JUDGE_ENVELOPE_FIELDS, "envelope")
    if type(envelope["schema_version"]) is not int or envelope["schema_version"] != SCHEMA_VERSION:
        raise ReportError(f"schema_version must be {SCHEMA_VERSION}")
    if envelope["role"] != "judge":
        raise ReportError("role must be judge")
    validate_identity(story_id, attempt, intent_version)
    expected_identity = (
        ("story_id", story_id), ("attempt", attempt), ("intent_version", intent_version),
        ("judge_round", judge_round),
    )
    for field, expected in expected_identity:
        require_identity_match(envelope, field, expected)
    require_text(envelope["submitted_at"], "submitted_at", limit=64)
    envelope["report"] = validate_judge_report(envelope["report"])
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
    envelope = build_worker_envelope(
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
    validated = validate_worker_envelope(
        envelope, story_id=args.story_id, attempt=args.attempt, intent_version=args.intent_version,
    )
    print(json.dumps(validated, ensure_ascii=False))
    return 0


def command_validator(args: argparse.Namespace) -> int:
    output = Path(args.output).resolve()
    output.unlink(missing_ok=True)
    envelope = build_validator_envelope(
        read_json_input(args.source), story_id=args.story_id, attempt=args.attempt,
        intent_version=args.intent_version, validation_round=args.validation_round,
        acceptance_ids=args.acceptance_id,
    )
    digest = atomic_write(output, envelope)
    print(f"VALIDATOR_REPORT_WRITTEN: {output}")
    print(f"SHA256: {digest}")
    return 0


def command_read_validator(args: argparse.Namespace) -> int:
    path = Path(args.file).resolve()
    with path.open(encoding="utf-8") as handle:
        envelope = json.load(handle)
    validated = validate_validator_envelope(
        envelope, story_id=args.story_id, attempt=args.attempt,
        intent_version=args.intent_version, validation_round=args.validation_round,
        acceptance_ids=args.acceptance_id,
    )
    print(json.dumps(validated, ensure_ascii=False))
    return 0


def command_judge(args: argparse.Namespace) -> int:
    output = Path(args.output).resolve()
    output.unlink(missing_ok=True)
    envelope = build_judge_envelope(
        read_json_input(args.source), story_id=args.story_id, attempt=args.attempt,
        intent_version=args.intent_version, judge_round=args.judge_round,
    )
    digest = atomic_write(output, envelope)
    print(f"JUDGE_REPORT_WRITTEN: {output}")
    print(f"SHA256: {digest}")
    return 0


def command_read_judge(args: argparse.Namespace) -> int:
    path = Path(args.file).resolve()
    with path.open(encoding="utf-8") as handle:
        envelope = json.load(handle)
    validated = validate_judge_envelope(
        envelope, story_id=args.story_id, attempt=args.attempt,
        intent_version=args.intent_version, judge_round=args.judge_round,
    )
    print(json.dumps(validated, ensure_ascii=False))
    return 0


def add_identity_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--story-id", required=True, help="当前 Story ID，例如 STORY-03")
    parser.add_argument("--attempt", required=True, type=int, help="当前 Worker attempt，必须为正整数")
    parser.add_argument("--intent-version", required=True, type=int, help="当前 Story intent_version")


def add_input_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--from", dest="source", default="-", help="输入 JSON；默认 - 表示 stdin")


def add_acceptance_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--acceptance-id", action="append", required=True,
        help="Story 的 Acceptance ID，按计划顺序重复传入",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="严格校验并原子保存 large-task Worker、Validator 与 Judge 报告。",
        epilog="""输出:
  提交成功时打印目标路径与 SHA256；read-* 成功时打印 canonical JSON；错误返回 2。

示例:
  python3 large_task_report.py worker --output /tmp/worker.json --story-id STORY-03 --attempt 1 --intent-version 2 < report.json
  python3 large_task_report.py validator --output /tmp/validator.json --story-id STORY-03 --attempt 1 --intent-version 2 --validation-round 1 --acceptance-id AC-01 < report.json
  python3 large_task_report.py judge --output /tmp/judge.json --story-id STORY-03 --attempt 1 --intent-version 2 --judge-round 1 < report.json
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)

    worker = commands.add_parser("worker", help="从 JSON 输入提交 Worker 报告")
    worker.add_argument("--output", required=True, help="Driver 指定的报告文件路径")
    add_input_argument(worker)
    add_identity_arguments(worker)
    worker.set_defaults(handler=command_worker)

    reader = commands.add_parser("read-worker", help="校验已提交报告及其执行身份")
    reader.add_argument("--file", required=True, help="报告文件路径")
    add_identity_arguments(reader)
    reader.set_defaults(handler=command_read_worker)

    validator = commands.add_parser("validator", help="从 JSON 输入提交 Validator 报告")
    validator.add_argument("--output", required=True, help="Driver 指定的报告文件路径")
    validator.add_argument("--validation-round", required=True, type=int, help="当前 Validator round")
    add_acceptance_arguments(validator)
    add_input_argument(validator)
    add_identity_arguments(validator)
    validator.set_defaults(handler=command_validator)

    validator_reader = commands.add_parser("read-validator", help="校验 Validator 报告及执行身份")
    validator_reader.add_argument("--file", required=True, help="报告文件路径")
    validator_reader.add_argument("--validation-round", required=True, type=int, help="当前 Validator round")
    add_acceptance_arguments(validator_reader)
    add_identity_arguments(validator_reader)
    validator_reader.set_defaults(handler=command_read_validator)

    judge = commands.add_parser("judge", help="从 JSON 输入提交 Judge 报告")
    judge.add_argument("--output", required=True, help="Driver 指定的报告文件路径")
    judge.add_argument("--judge-round", required=True, type=int, help="当前 Judge round")
    add_input_argument(judge)
    add_identity_arguments(judge)
    judge.set_defaults(handler=command_judge)

    judge_reader = commands.add_parser("read-judge", help="校验 Judge 报告及执行身份")
    judge_reader.add_argument("--file", required=True, help="报告文件路径")
    judge_reader.add_argument("--judge-round", required=True, type=int, help="当前 Judge round")
    add_identity_arguments(judge_reader)
    judge_reader.set_defaults(handler=command_read_judge)
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
