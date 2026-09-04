#!/usr/bin/env python3
"""检查 Droid 配置并维护脱敏滚动审计。

脚本定义：`check` 只读检查 settings.json 并输出脱敏摘要；`record`/`decide`
维护用户缓存中的最小运行事实；`show`/`history-check` 聚合复盘；`self-test`
验证脱敏、滚动、覆盖、双计和未知 ID 拒绝语义。
参数定义：配置默认 ~/.factory/settings.json；历史默认
~/.cache/droid-config/run-history.json，可用 DROID_CONFIG_STATE_DIR 覆盖。
输出定义：成功时 stdout 输出 JSON；错误写 stderr。退出码 0=成功，1=数据或
文件错误，2=参数错误。历史不保存 prompt、配置正文、URL、日志或密钥。
关键设计：历史窗口固定为 100 次，旧记录折入固定维度 rollup；同一 run ID
覆盖而不追加，decision 也覆盖。写入使用 flock、0600 临时文件和原子替换。
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse


HISTORY_VERSION = 1
MAX_LIVE_RUNS = 100
OPERATIONS = ("inspect", "upgrade", "configure", "verify")
OUTCOMES = ("success", "failure", "blocked")
DECISIONS = ("accepted", "rejected")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,191}$")


class AuditError(RuntimeError):
    """配置或审计事实不满足脚本契约。"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="检查 Droid 配置并维护不含密钥的本地滚动审计。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""输出:
  check/history-check/show 输出 JSON 且不包含 apiKey、配置正文、URL 或日志。
  record/decide 成功后输出更新后的脱敏记录。退出码 0=成功，1=数据错误，2=参数错误。

示例:
  python3 droid_config_audit.py check
  python3 droid_config_audit.py record --run-id droid-config-20260904T030000Z \\
    --operation configure --outcome success --version-before 0.197.0 \\
    --version-after 0.212.0 --duration-ms 12000 --model glm-5.3
  python3 droid_config_audit.py decide --run-id droid-config-20260904T030000Z \\
    --decision accepted
  python3 droid_config_audit.py show
""",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="只读检查 Droid settings.json")
    check.add_argument(
        "--settings", type=Path, default=Path.home() / ".factory" / "settings.json"
    )

    record = commands.add_parser("record", help="记录一次发生写入的配置运行")
    record.add_argument("--run-id", required=True)
    record.add_argument("--operation", required=True, choices=OPERATIONS)
    record.add_argument("--outcome", required=True, choices=OUTCOMES)
    record.add_argument("--version-before", required=True)
    record.add_argument("--version-after", required=True)
    record.add_argument("--duration-ms", required=True, type=int)
    record.add_argument("--model", action="append", default=[])
    record.add_argument("--at", help="带时区 ISO-8601 时间；默认当前 UTC")

    decide = commands.add_parser("decide", help="覆盖写入用户对某次运行的决定")
    decide.add_argument("--run-id", required=True)
    decide.add_argument("--decision", required=True, choices=DECISIONS)

    show = commands.add_parser("show", help="只读输出近期记录、聚合与复盘提示")
    show.add_argument("--last", type=int, default=10)
    commands.add_parser("history-check", help="只读校验历史 schema 和滚动上限")
    commands.add_parser("self-test", help="在临时目录验证关键记账与脱敏语义")
    return parser


def state_dir() -> Path:
    override = os.environ.get("DROID_CONFIG_STATE_DIR")
    if override:
        return Path(override).expanduser()
    cache = os.environ.get("XDG_CACHE_HOME")
    root = Path(cache).expanduser() if cache else Path.home() / ".cache"
    return root / "droid-config"


def history_path() -> Path:
    return state_dir() / "run-history.json"


def lock_path() -> Path:
    return state_dir() / "run-history.lock"


def empty_rollup() -> dict[str, Any]:
    return {
        "runs": 0,
        "duration_ms": 0,
        "outcomes": {name: 0 for name in OUTCOMES},
        "operations": {name: 0 for name in OPERATIONS},
        "decisions": {name: 0 for name in DECISIONS},
    }


def empty_history() -> dict[str, Any]:
    return {"version": HISTORY_VERSION, "rollup": empty_rollup(), "runs": []}


def parse_time(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise AuditError("--at 必须是 ISO-8601 时间") from error
    if parsed.tzinfo is None:
        raise AuditError("--at 必须包含时区")
    return parsed.isoformat()


def validate_token(value: str, pattern: re.Pattern[str], label: str) -> str:
    if not pattern.fullmatch(value):
        raise AuditError(f"{label} 格式非法: {value!r}")
    return value


def load_settings(path: Path) -> tuple[dict[str, Any], os.stat_result]:
    target = path.expanduser()
    if target.is_symlink() or not target.is_file():
        raise AuditError(f"settings 必须是普通文件且不能是 symlink: {target}")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AuditError(f"无法读取有效 JSON: {target}: {error}") from error
    if not isinstance(data, dict):
        raise AuditError("settings 顶层必须是对象")
    return data, target.stat()


def require_string(item: dict[str, Any], field: str, label: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value:
        raise AuditError(f"{label}.{field} 必须是非空字符串")
    return value


def check_settings(path: Path) -> dict[str, Any]:
    settings, file_stat = load_settings(path)
    models = settings.get("customModels", [])
    if not isinstance(models, list):
        raise AuditError("customModels 必须是数组")

    ids: set[str] = set()
    indexes: set[int] = set()
    summary: list[dict[str, Any]] = []
    has_secret = False
    for position, raw in enumerate(models):
        if not isinstance(raw, dict):
            raise AuditError(f"customModels[{position}] 必须是对象")
        label = f"customModels[{position}]"
        model_id = require_string(raw, "id", label)
        request_model = require_string(raw, "model", label)
        display = require_string(raw, "displayName", label)
        provider = require_string(raw, "provider", label)
        base_url = require_string(raw, "baseUrl", label)
        if model_id in ids:
            raise AuditError(f"重复自定义模型 ID: {model_id}")
        ids.add(model_id)
        index = raw.get("index")
        if not isinstance(index, int) or index < 0 or index in indexes:
            raise AuditError(f"{label}.index 必须是唯一的非负整数")
        indexes.add(index)
        maximum = raw.get("maxOutputTokens")
        if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum <= 0:
            raise AuditError(f"{label}.maxOutputTokens 必须是正整数")
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise AuditError(f"{label}.baseUrl 必须是有效 HTTP(S) URL")
        if provider not in {"anthropic", "openai", "generic-chat-completion-api"}:
            raise AuditError(f"{label}.provider 不受 Droid 支持: {provider}")
        if "apiKey" in raw or "apiKeyHelper" in raw:
            has_secret = True
        summary.append(
            {
                "id": model_id,
                "model": request_model,
                "display_name": display,
                "index": index,
                "provider": provider,
                "provider_host": parsed.hostname,
                "max_output_tokens": maximum,
                "image_support": not bool(raw.get("noImageSupport", False)),
            }
        )

    references = {
        "session_default": (settings.get("sessionDefaultSettings") or {}).get("model")
        if isinstance(settings.get("sessionDefaultSettings"), dict)
        else None,
        "mission_orchestrator": settings.get("missionOrchestratorModel"),
        "mission_worker": (settings.get("missionModelSettings") or {}).get("workerModel")
        if isinstance(settings.get("missionModelSettings"), dict)
        else None,
        "mission_validator": (settings.get("missionModelSettings") or {}).get(
            "validationWorkerModel"
        )
        if isinstance(settings.get("missionModelSettings"), dict)
        else None,
    }
    for label, reference in references.items():
        if isinstance(reference, str) and reference.startswith("custom:") and reference not in ids:
            raise AuditError(f"{label} 引用了不存在的自定义模型: {reference}")

    limits = settings.get("compactionTokenLimitPerModel", {})
    if not isinstance(limits, dict):
        raise AuditError("compactionTokenLimitPerModel 必须是对象")
    dangling_limits = sorted(
        key for key in limits if isinstance(key, str) and key.startswith("custom:") and key not in ids
    )
    if dangling_limits:
        raise AuditError(f"压缩映射包含悬空自定义模型: {dangling_limits}")
    for key, value in limits.items():
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise AuditError(f"压缩阈值必须是正整数: {key}")

    warnings: list[str] = []
    if has_secret and file_stat.st_mode & 0o077:
        warnings.append("settings contains credentials but is readable by group or others")
    return {
        "status": "ok",
        "settings": str(path.expanduser()),
        "models": summary,
        "references": references,
        "compaction_models": sorted(limits),
        "permissions": oct(file_stat.st_mode & 0o777),
        "warnings": warnings,
    }


def validate_count_map(value: Any, names: tuple[str, ...], label: str) -> None:
    if not isinstance(value, dict) or set(value) != set(names):
        raise AuditError(f"{label} 维度漂移")
    if any(not isinstance(value[name], int) or value[name] < 0 for name in names):
        raise AuditError(f"{label} 计数必须是非负整数")


def validate_run(run: Any) -> None:
    if not isinstance(run, dict):
        raise AuditError("history run 必须是对象")
    expected = {
        "run_id",
        "recorded_at",
        "operation",
        "outcome",
        "version_before",
        "version_after",
        "duration_ms",
        "models",
        "decision",
    }
    if set(run) != expected:
        raise AuditError("history run 字段漂移")
    validate_token(run["run_id"], RUN_ID_RE, "run_id")
    parse_time(run["recorded_at"])
    if run["operation"] not in OPERATIONS or run["outcome"] not in OUTCOMES:
        raise AuditError("history run 枚举值非法")
    validate_token(run["version_before"], VERSION_RE, "version_before")
    validate_token(run["version_after"], VERSION_RE, "version_after")
    if not isinstance(run["duration_ms"], int) or run["duration_ms"] < 0:
        raise AuditError("duration_ms 必须是非负整数")
    if not isinstance(run["models"], list) or run["models"] != sorted(set(run["models"])):
        raise AuditError("models 必须是排序去重后的数组")
    for model in run["models"]:
        validate_token(model, MODEL_RE, "model")
    if run["decision"] is not None and run["decision"] not in DECISIONS:
        raise AuditError("decision 枚举值非法")


def validate_history(history: Any) -> dict[str, Any]:
    if not isinstance(history, dict) or set(history) != {"version", "rollup", "runs"}:
        raise AuditError("history 顶层 schema 漂移")
    if history["version"] != HISTORY_VERSION:
        raise AuditError("history version 不支持")
    rollup = history["rollup"]
    if not isinstance(rollup, dict) or set(rollup) != set(empty_rollup()):
        raise AuditError("rollup schema 漂移")
    if not isinstance(rollup["runs"], int) or rollup["runs"] < 0:
        raise AuditError("rollup.runs 必须是非负整数")
    if not isinstance(rollup["duration_ms"], int) or rollup["duration_ms"] < 0:
        raise AuditError("rollup.duration_ms 必须是非负整数")
    validate_count_map(rollup["outcomes"], OUTCOMES, "rollup.outcomes")
    validate_count_map(rollup["operations"], OPERATIONS, "rollup.operations")
    validate_count_map(rollup["decisions"], DECISIONS, "rollup.decisions")
    runs = history["runs"]
    if not isinstance(runs, list) or len(runs) > MAX_LIVE_RUNS:
        raise AuditError("history runs 超过滚动上限")
    seen: set[str] = set()
    for run in runs:
        validate_run(run)
        if run["run_id"] in seen:
            raise AuditError(f"重复 run_id: {run['run_id']}")
        seen.add(run["run_id"])
    return history


def load_history(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_history()
    if path.is_symlink() or not path.is_file():
        raise AuditError(f"历史必须是普通文件且不能是 symlink: {path}")
    try:
        return validate_history(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as error:
        raise AuditError(f"无法读取有效历史: {path}: {error}") from error


def increment(mapping: dict[str, int], key: str) -> None:
    mapping[key] += 1


def fold_run(rollup: dict[str, Any], run: dict[str, Any]) -> None:
    rollup["runs"] += 1
    rollup["duration_ms"] += run["duration_ms"]
    increment(rollup["outcomes"], run["outcome"])
    increment(rollup["operations"], run["operation"])
    if run["decision"] is not None:
        increment(rollup["decisions"], run["decision"])


def roll(history: dict[str, Any]) -> None:
    while len(history["runs"]) > MAX_LIVE_RUNS:
        fold_run(history["rollup"], history["runs"].pop(0))


def atomic_write(path: Path, history: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.is_symlink() or path.is_symlink():
        raise AuditError("历史目录和文件不能是 symlink")
    descriptor, temporary = tempfile.mkstemp(prefix=".run-history.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(history, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.close(descriptor)
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


@contextlib.contextmanager
def locked_history() -> Iterator[tuple[Path, dict[str, Any]]]:
    directory = state_dir()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink() or not directory.is_dir():
        raise AuditError(f"历史目录必须是普通目录且不能是 symlink: {directory}")
    lock = lock_path()
    if lock.is_symlink():
        raise AuditError("历史锁不能是 symlink")
    with lock.open("a+", encoding="utf-8") as handle:
        os.chmod(lock, 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        path = history_path()
        history = load_history(path)
        yield path, history


def make_run(args: argparse.Namespace) -> dict[str, Any]:
    validate_token(args.run_id, RUN_ID_RE, "run_id")
    validate_token(args.version_before, VERSION_RE, "version_before")
    validate_token(args.version_after, VERSION_RE, "version_after")
    if args.duration_ms < 0:
        raise AuditError("--duration-ms 必须是非负整数")
    models = sorted(set(args.model))
    for model in models:
        validate_token(model, MODEL_RE, "model")
    return {
        "run_id": args.run_id,
        "recorded_at": parse_time(args.at),
        "operation": args.operation,
        "outcome": args.outcome,
        "version_before": args.version_before,
        "version_after": args.version_after,
        "duration_ms": args.duration_ms,
        "models": models,
        "decision": None,
    }


def record_run(args: argparse.Namespace) -> dict[str, Any]:
    run = make_run(args)
    with locked_history() as (path, history):
        for index, current in enumerate(history["runs"]):
            if current["run_id"] == run["run_id"]:
                run["decision"] = current["decision"]
                history["runs"][index] = run
                break
        else:
            history["runs"].append(run)
        roll(history)
        validate_history(history)
        atomic_write(path, history)
    return run


def decide_run(args: argparse.Namespace) -> dict[str, Any]:
    validate_token(args.run_id, RUN_ID_RE, "run_id")
    with locked_history() as (path, history):
        target = next(
            (run for run in history["runs"] if run["run_id"] == args.run_id), None
        )
        if target is None:
            raise AuditError(f"未知或已滚出的 run_id，拒绝写入决定: {args.run_id}")
        target["decision"] = args.decision
        validate_history(history)
        atomic_write(path, history)
        return dict(target)


def combined_summary(history: dict[str, Any]) -> dict[str, Any]:
    totals = json.loads(json.dumps(history["rollup"]))
    for run in history["runs"]:
        fold_run(totals, run)
    total_runs = totals["runs"]
    decided = sum(totals["decisions"].values())
    hooks: list[str] = []
    failures = totals["outcomes"]["failure"]
    if total_runs >= 5 and failures / total_runs >= 0.2:
        hooks.append("failure rate is at least 20%; review provider and Droid drift")
    rejected = totals["decisions"]["rejected"]
    if decided >= 5 and rejected / decided >= 0.3:
        hooks.append("rejection rate is at least 30%; review defaults and scope decisions")
    return {
        "total_runs": total_runs,
        "duration_ms": totals["duration_ms"],
        "outcomes": totals["outcomes"],
        "operations": totals["operations"],
        "decisions": totals["decisions"],
        "hooks": hooks,
    }


def show_history(last: int) -> dict[str, Any]:
    if last < 0:
        raise AuditError("--last 必须是非负整数")
    history = load_history(history_path())
    return {
        "status": "ok",
        "history": str(history_path()),
        "limits": {"live_runs": MAX_LIVE_RUNS},
        "summary": combined_summary(history),
        "recent": history["runs"][-last:] if last else [],
        "rolled_up_runs": history["rollup"]["runs"],
    }


def check_history() -> dict[str, Any]:
    history = load_history(history_path())
    return {
        "status": "ok",
        "history": str(history_path()),
        "live_runs": len(history["runs"]),
        "rolled_up_runs": history["rollup"]["runs"],
    }


def self_test() -> dict[str, Any]:
    previous = os.environ.get("DROID_CONFIG_STATE_DIR")
    try:
        with tempfile.TemporaryDirectory(prefix="droid-config-audit-test.") as temporary:
            os.environ["DROID_CONFIG_STATE_DIR"] = temporary
            settings = Path(temporary) / "settings.json"
            secret = "secret-must-not-appear"
            settings.write_text(
                json.dumps(
                    {
                        "customModels": [
                            {
                                "apiKey": secret,
                                "baseUrl": "https://example.invalid/v1",
                                "displayName": "Example",
                                "id": "custom:Example-0",
                                "index": 0,
                                "maxOutputTokens": 1024,
                                "model": "example",
                                "provider": "generic-chat-completion-api",
                            }
                        ],
                        "sessionDefaultSettings": {"model": "custom:Example-0"},
                        "compactionTokenLimitPerModel": {"custom:Example-0": 8192},
                    }
                ),
                encoding="utf-8",
            )
            os.chmod(settings, 0o600)
            summary = check_settings(settings)
            if secret in json.dumps(summary):
                raise AuditError("self-test: check 输出泄漏密钥")

            for index in range(MAX_LIVE_RUNS + 5):
                args = argparse.Namespace(
                    run_id=f"run-{index}",
                    operation="configure",
                    outcome="success",
                    version_before="0.1.0",
                    version_after="0.2.0",
                    duration_ms=10,
                    model=["example"],
                    at="2026-09-04T00:00:00+00:00",
                )
                record_run(args)
            history = load_history(history_path())
            aggregate = combined_summary(history)
            if len(history["runs"]) != MAX_LIVE_RUNS or history["rollup"]["runs"] != 5:
                raise AuditError("self-test: 滚动窗口语义错误")
            if aggregate["total_runs"] != MAX_LIVE_RUNS + 5:
                raise AuditError("self-test: live 与 rollup 发生双计或漏计")

            overwrite = argparse.Namespace(
                run_id="run-104",
                operation="verify",
                outcome="failure",
                version_before="0.2.0",
                version_after="0.2.0",
                duration_ms=20,
                model=["example"],
                at="2026-09-04T00:01:00+00:00",
            )
            record_run(overwrite)
            if combined_summary(load_history(history_path()))["total_runs"] != MAX_LIVE_RUNS + 5:
                raise AuditError("self-test: 重复 run_id 被追加")

            decide_run(argparse.Namespace(run_id="run-104", decision="accepted"))
            decide_run(argparse.Namespace(run_id="run-104", decision="rejected"))
            decided = load_history(history_path())
            target = next(run for run in decided["runs"] if run["run_id"] == "run-104")
            if target["decision"] != "rejected":
                raise AuditError("self-test: decision 未覆盖")
            if combined_summary(decided)["decisions"]["rejected"] != 1:
                raise AuditError("self-test: decision 被双计")

            try:
                decide_run(argparse.Namespace(run_id="unknown", decision="accepted"))
            except AuditError:
                pass
            else:
                raise AuditError("self-test: 未拒绝未知 run_id")
    finally:
        if previous is None:
            os.environ.pop("DROID_CONFIG_STATE_DIR", None)
        else:
            os.environ["DROID_CONFIG_STATE_DIR"] = previous
    return {
        "status": "ok",
        "checks": ["redaction", "rolling", "overwrite", "no-double-count", "unknown-id"],
    }


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            emit(check_settings(args.settings))
        elif args.command == "record":
            emit(record_run(args))
        elif args.command == "decide":
            emit(decide_run(args))
        elif args.command == "show":
            emit(show_history(args.last))
        elif args.command == "history-check":
            emit(check_history())
        elif args.command == "self-test":
            emit(self_test())
        else:
            parser.error(f"未知命令: {args.command}")
    except (AuditError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
