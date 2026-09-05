#!/usr/bin/env python3
"""Store readiness reports locally and maintain a bounded run history.

Definition: persists one full report JSON per run and one minimal-fact
history record (level, pass rate, engine/model, evaluated/skipped counts).
It writes only local files and never performs any network request; there is
no remote reporting endpoint by design.
Parameters: use ``store``, ``show``, or ``check``; ``--cache`` overrides the
XDG cache root for tests and diagnostics.
Outputs: successful commands print JSON. Exit 0 means success, 1 means invalid
history or operation, and 2 means invalid CLI arguments.

Storage layout under ``<cache>/readiness-report/<repo-slug>/``:
  reports/<UTC timestamp>.json  full per-run reports (kept)
  history.json                 bounded minimal-fact history

History contract:
  - minimal facts only (repo, level, pass_rate, engine, model, evaluated,
    skipped, stable run id); rationale text lives in the report JSON, not here.
  - rolling window of the latest MAX_RECENT runs plus a fixed-dimension rollup;
    live window and rollup never double-count.
  - repeating a run id overwrites instead of appending.
  - recording failures are warnings for the caller and never change the audit
    result.

Examples:
  python3 report_history.py store --repo https://github.com/o/r.git --level 3 \
    --pass-rate 55.5 --evaluated 40 --skipped 5 --engine droid \
    --model unknown
  python3 report_history.py show --repo https://github.com/o/r.git
  python3 report_history.py check --repo https://github.com/o/r.git
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
LEVELS = range(1, 6)
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+/@:-]{0,255}$")
OUTCOME_KEYS = ("stored", "failed")


class HistoryError(RuntimeError):
    """The stored history or requested mutation violates the contract."""


def cache_root() -> Path:
    override = os.environ.get("XDG_CACHE_HOME")
    base = Path(override).expanduser() if override else Path.home() / ".cache"
    return base / "readiness-report"


def validate_repo(repo: str) -> str:
    """Accept remote URLs and plain local paths.

    Remote forms must match the strict token pattern; absolute or relative
    local paths are allowed so a repo can be audited without a remote.
    The check mirrors the characters slug_for_repo can sanitize.
    """
    value = repo.strip()
    if not value:
        raise HistoryError("invalid repo: empty value")
    if TOKEN_RE.fullmatch(value):
        return value
    if value.startswith(("/", "./", "../", "~")) and not re.search(r"[\s\"'\\]", value):
        return value
    raise HistoryError(f"invalid repo: {value!r}")


def slug_for_repo(repo: str) -> str:
    """Map a repo URL or path to a filesystem-safe slug.

    Remote URLs, SSH forms, and local paths must land on one stable slug so
    repeated runs against the same repository converge on one directory.
    """
    value = repo.strip().lower()
    value = re.sub(r"^[a-z]+://", "", value)  # strip scheme
    value = re.sub(r"^(git@)", "", value)  # strip ssh user
    value = value.replace(":", "/")  # ssh colon to path
    value = value.removeprefix("/")
    value = value.removesuffix(".git")
    value = value.removesuffix("/")
    value = value.removeprefix("~")
    value = value.removeprefix("/")
    slug = re.sub(r"[^a-z0-9]+", "-", value).strip("-") or "unnamed"
    return slug[:80]


def repo_dir(root: Path, repo: str) -> Path:
    return root / slug_for_repo(repo)


def usage() -> str:
    return f"""Usage:
  python3 report_history.py [--cache <dir>] store <options>
  python3 report_history.py [--cache <dir>] show --repo <repo>
  python3 report_history.py [--cache <dir>] check --repo <repo>

Notes:
  Store readiness reports locally under {cache_root()}/<repo-slug>/.
  No network access happens anywhere; remote reporting is intentionally absent.

Parameters:
  --cache <dir>    Override the cache root (mainly for tests).
  store            Write one report JSON plus one minimal history record.
  show             Print aggregated history plus deterministic review hooks.
  check            Read-only validation of the stored history.

Options for store:
  --repo <url>          Repository URL or path being evaluated.
  --level <1-5>        Achieved readiness level.
  --pass-rate <0-100>  Overall pass rate percentage.
  --evaluated <n>      Number of non-skipped signals.
  --skipped <k>        Number of skipped signals.
  --run-id <id>        Stable run id; default is an auto timestamp id.
                       Repeating an id overwrites the same record.
  --engine <name>       Host engine name (e.g. droid, codex).
  --model <name>       Model name; write 'unknown' when not controlled.
  --report <path>      Optional full report JSON file to persist verbatim.
  --at <iso-time>      Timezone-aware ISO-8601 time; default current UTC.

Outputs:
  Success prints JSON to stdout. Exit codes: 0=success, 1=history or
  operation error, 2=CLI usage error. At most {MAX_RECENT} recent records are
  kept; older ones only enter the fixed-dimension rollup.
"""


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


def default_run_id(recorded_at: str) -> str:
    return "run-" + recorded_at.replace(":", "").replace("-", "")[:-1]


def empty_bucket() -> dict[str, Any]:
    return {
        "runs": 0,
        "levels": {str(level): 0 for level in LEVELS},
        "outcomes": {key: 0 for key in OUTCOME_KEYS},
    }


def empty_history() -> dict[str, Any]:
    return {
        "version": SCHEMA_VERSION,
        "repo": None,
        "recent": [],
        "rollup": empty_bucket(),
        "updated_at": None,
    }


def validate_bucket(bucket: Any, label: str) -> None:
    if not isinstance(bucket, dict):
        raise HistoryError(f"{label} must be an object")
    if type(bucket.get("runs")) is not int or bucket["runs"] < 0:
        raise HistoryError(f"{label}.runs must be a non-negative integer")
    levels = bucket.get("levels")
    expected_levels = {str(level) for level in LEVELS}
    if not isinstance(levels, dict) or set(levels) != expected_levels:
        raise HistoryError(f"{label}.levels has invalid dimensions")
    if any(type(levels[key]) is not int or levels[key] < 0 for key in levels):
        raise HistoryError(f"{label}.levels counts must be non-negative integers")
    if sum(levels.values()) != bucket["runs"]:
        raise HistoryError(f"{label}.levels does not sum to runs")
    outcomes = bucket.get("outcomes")
    if not isinstance(outcomes, dict) or set(outcomes) != set(OUTCOME_KEYS):
        raise HistoryError(f"{label}.outcomes has invalid dimensions")
    if any(type(outcomes[key]) is not int or outcomes[key] < 0 for key in outcomes):
        raise HistoryError(f"{label}.outcomes counts must be non-negative integers")
    if sum(outcomes.values()) != bucket["runs"]:
        raise HistoryError(f"{label}.outcomes does not sum to runs")


def validate_record(record: Any) -> None:
    if not isinstance(record, dict):
        raise HistoryError("recent records must be objects")
    validate_token(record.get("run_id", ""), "run_id", ID_RE)
    if record.get("level") not in LEVELS:
        raise HistoryError("invalid stored level")
    rate = record.get("pass_rate")
    if not isinstance(rate, (int, float)) or not 0.0 <= float(rate) <= 100.0:
        raise HistoryError("pass_rate must be a number between 0 and 100")
    for field in ("evaluated", "skipped"):
        value = record.get(field)
        if type(value) is not int or value < 0:
            raise HistoryError(f"{field} must be a non-negative integer")
    if record.get("outcome") not in OUTCOME_KEYS:
        raise HistoryError("invalid stored outcome")
    validate_token(record.get("engine", ""), "engine")
    validate_token(record.get("model", ""), "model")
    parse_time(record.get("recorded_at"))


def validate_history(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("version") != SCHEMA_VERSION:
        raise HistoryError("unsupported or invalid history schema")
    if data.get("repo") is not None:
        validate_repo(data["repo"])
    recent = data.get("recent")
    if not isinstance(recent, list) or len(recent) > MAX_RECENT:
        raise HistoryError("recent window exceeds its bound")
    for record in recent:
        validate_record(record)
    ids = [record["run_id"] for record in recent]
    if len(ids) != len(set(ids)):
        raise HistoryError("run ids must be unique within the window")
    rollup = data.get("rollup")
    if not isinstance(rollup, dict):
        raise HistoryError("invalid rollup")
    validate_bucket(rollup, "rollup")
    if data.get("updated_at") is not None:
        parse_time(data["updated_at"])
    return data


def history_path(directory: Path) -> Path:
    return directory / "history.json"


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


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
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
        raise HistoryError(f"cannot write {path.name}: {error}") from error
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def add_to_bucket(bucket: dict[str, Any], record: dict[str, Any]) -> None:
    bucket["runs"] += 1
    bucket["levels"][str(record["level"])] += 1
    bucket["outcomes"][record["outcome"]] += 1


def command_store(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    repo = validate_repo(args.repo)
    recorded_at = parse_time(args.at)
    run_id = validate_token(args.run_id, "run_id", ID_RE) if args.run_id else default_run_id(recorded_at)
    if args.level not in LEVELS:
        raise HistoryError("level must be 1-5")
    if not 0.0 <= args.pass_rate <= 100.0:
        raise HistoryError("pass_rate must be between 0 and 100")
    if args.evaluated < 0 or args.skipped < 0:
        raise HistoryError("evaluated/skipped must be non-negative")

    directory = repo_dir(root, repo)
    reports_dir = directory / "reports"
    stored_report: str | None = None
    report_payload: dict[str, Any] | None = None
    if args.report:
        report_path = Path(args.report).expanduser()
        if report_path.is_symlink() or not report_path.is_file():
            raise HistoryError("report must be a regular non-symlink file")
        try:
            report_payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise HistoryError(f"cannot read report: {error}") from error
        if not isinstance(report_payload, dict):
            raise HistoryError("report must be a JSON object")
        target = reports_dir / f"{run_id}.json"
        write_json_atomic(target, report_payload)
        stored_report = str(target)

    record = {
        "run_id": run_id,
        "repo": repo,
        "level": args.level,
        "pass_rate": round(float(args.pass_rate), 2),
        "evaluated": args.evaluated,
        "skipped": args.skipped,
        "outcome": "stored",
        "engine": validate_token(args.engine, "engine"),
        "model": validate_token(args.model, "model"),
        "recorded_at": recorded_at,
    }

    path = history_path(directory)
    with locked(path, exclusive=True):
        data = load_history(path)
        existing = next(
            (item for item in data["recent"] if item["run_id"] == run_id), None
        )
        if existing is not None:
            # Overwrite by run id: remove the old record so the rollup below
            # never double-counts a retried run.
            data["recent"].remove(existing)
        data["repo"] = repo
        data["recent"].append(record)
        while len(data["recent"]) > MAX_RECENT:
            retired = data["recent"].pop(0)
            add_to_bucket(data["rollup"], retired)
        data["updated_at"] = recorded_at
        write_json_atomic(path, data)
    return {"ok": True, "run_id": run_id, "history": str(path), "report": stored_report}


def aggregate(data: dict[str, Any]) -> dict[str, Any]:
    combined = {"rollup": deepcopy(data["rollup"])}
    for record in data["recent"]:
        add_to_bucket(combined["rollup"], record)
    return combined


def retrospective_hooks(combined: dict[str, Any]) -> list[dict[str, Any]]:
    total = combined["rollup"]
    hooks: list[dict[str, Any]] = []
    runs = total["runs"]
    if runs == 0:
        return hooks
    best_level = max((level for level in LEVELS if total["levels"][str(level)] > 0), default=None)
    if best_level is not None and total["levels"][str(best_level)] == runs:
        hooks.append({"kind": "all-same-level", "level": best_level, "count": runs})
    if runs >= 4 and total["outcomes"]["failed"] > 0:
        hooks.append(
            {
                "kind": "any-failed-stores",
                "numerator": total["outcomes"]["failed"],
                "denominator": runs,
            }
        )
    return hooks


def command_show(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    repo = validate_repo(args.repo)
    path = history_path(repo_dir(root, repo))
    with locked(path, exclusive=False):
        data = load_history(path)
    combined = aggregate(data)
    return {
        "history": str(path),
        "repo": data.get("repo"),
        "recent_count": len(data["recent"]),
        "aggregate": combined,
        "latest": data["recent"][-1] if data["recent"] else None,
        "retrospective_hooks": retrospective_hooks(combined),
    }


def command_check(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    repo = validate_repo(args.repo)
    path = history_path(repo_dir(root, repo))
    with locked(path, exclusive=False):
        data = load_history(path)
    validate_history(data)
    reports_dir = repo_dir(root, repo) / "reports"
    report_files = sorted(reports_dir.glob("*.json")) if reports_dir.is_dir() else []
    return {
        "ok": True,
        "history": str(path),
        "recent_count": len(data["recent"]),
        "rolled_count": data["rollup"]["runs"],
        "report_files": len(report_files),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="本地维护 readiness-report 的报告存储与最小滚动历史。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=usage(),
    )
    parser.add_argument("--cache", type=Path, default=cache_root())
    commands = parser.add_subparsers(dest="command", required=True)

    store = commands.add_parser("store", help="存一份报告并记录一条最小历史")
    store.add_argument("--repo", required=True)
    store.add_argument("--level", required=True, type=int, choices=list(LEVELS))
    store.add_argument("--pass-rate", required=True, type=float)
    store.add_argument("--evaluated", required=True, type=int)
    store.add_argument("--skipped", required=True, type=int)
    store.add_argument("--run-id")
    store.add_argument("--engine", required=True)
    store.add_argument("--model", required=True)
    store.add_argument("--report")
    store.add_argument("--at", help="带时区的 ISO-8601 时间；默认当前 UTC")

    show = commands.add_parser("show", help="显示聚合统计与复盘关注项")
    show.add_argument("--repo", required=True)

    check = commands.add_parser("check", help="校验本地历史与报告文件")
    check.add_argument("--repo", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = args.cache.expanduser()
    try:
        if args.command == "store":
            result = command_store(args, root)
        elif args.command == "show":
            result = command_show(args, root)
        else:
            result = command_check(args, root)
    except HistoryError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
