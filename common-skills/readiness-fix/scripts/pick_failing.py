#!/usr/bin/env python3
"""List failing signals from the latest local readiness report.

Definition: reads only local report files produced by the readiness-report
skill and prints the failing signals (id, name, current score, category).
It never performs any network request; there is no remote reporting
endpoint by design.
Parameters: use ``list`` (default) or ``ids``; ``--repo`` selects the
repository; ``--cache`` overrides the XDG cache root for tests.
Outputs: list prints one JSON document with repo, run id, level, and the
failing signals array (empty when everything passes). ids prints only the
failing criterion IDs, one per line, for scripting. Exit 0 means success, 1
means missing or invalid report, and 2 means invalid CLI arguments.

Report layout under ``<cache>/<repo-slug>/``:
  history.json                 minimal-fact history (latest record)
  reports/<run id>.json        full per-run report

Examples:
  python3 pick_failing.py list --repo /data/code/my-repo
  python3 pick_failing.py ids --repo https://github.com/example/demo.git
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


class PickError(RuntimeError):
    """The local report or requested operation violates the contract."""


def cache_root() -> Path:
    override = os.environ.get("XDG_CACHE_HOME")
    base = Path(override).expanduser() if override else Path.home() / ".cache"
    return base / "readiness-report"


def slug_for_repo(repo: str) -> str:
    """Same sanitization as report_history.slug_for_repo."""
    value = repo.strip().lower()
    value = re.sub(r"^[a-z]+://", "", value)
    value = value.replace(":", "/")
    value = value.removeprefix("/")
    value = value.removesuffix(".git")
    value = value.removesuffix("/")
    value = value.removeprefix("~")
    value = value.removeprefix("/")
    slug = re.sub(r"[^a-z0-9]+", "-", value).strip("-") or "unnamed"
    return slug[:80]


def usage() -> str:
    return """Usage:
  python3 pick_failing.py [--cache <dir>] list --repo <repo>
  python3 pick_failing.py [--cache <dir>] ids  --repo <repo>

Notes:
  Reads the latest local readiness report only. No network access happens
  anywhere; remote reporting is intentionally absent.

Parameters:
  --cache <dir>   Override the cache root (mainly for tests).
  list             Print repo, run id, level, and failing signals as JSON.
  ids              Print only failing criterion IDs, one per line.

Outputs:
  Success prints to stdout. Exit codes: 0=success, 1=missing or invalid
  report, 2=CLI usage error.
"""


def load_history(directory: Path) -> dict[str, Any]:
    path = directory / "history.json"
    if not path.is_file() or path.is_symlink():
        raise PickError(f"no local readiness history at {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PickError(f"cannot read history: {error}") from error
    if not isinstance(data, dict) or not isinstance(data.get("recent"), list):
        raise PickError("invalid history structure")
    if not data["recent"]:
        raise PickError("history has no runs; generate a report first")
    return data


def load_report(directory: Path, run_id: str) -> dict[str, Any]:
    path = directory / "reports" / f"{run_id}.json"
    if not path.is_file() or path.is_symlink():
        raise PickError(f"no report file for run {run_id} at {path}")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PickError(f"cannot read report: {error}") from error
    if not isinstance(report, dict):
        raise PickError("report must be a JSON object")
    return report


def failing_signals(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract signals whose numerator is below their denominator.

    Skipped signals (null numerator) are excluded: they were not evaluated,
    so there is no failing verdict to fix.
    """
    criteria = report.get("criteria")
    if not isinstance(criteria, dict):
        raise PickError("report has no criteria object")
    failing = []
    for criterion_id, entry in criteria.items():
        if not isinstance(entry, dict):
            raise PickError(f"invalid criteria entry: {criterion_id}")
        numerator = entry.get("numerator")
        denominator = entry.get("denominator")
        if numerator is None:
            continue
        if not isinstance(numerator, int) or not isinstance(denominator, int):
            raise PickError(f"invalid score types for {criterion_id}")
        if numerator < denominator:
            failing.append(
                {
                    "id": criterion_id,
                    "name": entry.get("name", criterion_id),
                    "category": entry.get("category"),
                    "score": f"{numerator}/{denominator}",
                    "rationale": entry.get("rationale"),
                }
            )
    failing.sort(key=lambda item: item["id"])
    return failing


def command_list(args: argparse.Namespace) -> dict[str, Any]:
    directory = args.cache.expanduser() / slug_for_repo(args.repo)
    data = load_history(directory)
    latest = data["recent"][-1]
    report = load_report(directory, latest["run_id"])
    failing = failing_signals(report)
    return {
        "repo": args.repo,
        "run_id": latest["run_id"],
        "level": latest.get("level"),
        "pass_rate": latest.get("pass_rate"),
        "failing_count": len(failing),
        "failing": failing,
        "all_passing": not failing,
    }


def command_ids(args: argparse.Namespace) -> list[str]:
    result = command_list(args)
    return [item["id"] for item in result["failing"]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从本地 readiness 报告提取失败信号。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=usage(),
    )
    parser.add_argument("--cache", type=Path, default=cache_root())
    commands = parser.add_subparsers(dest="command", required=False)

    def add_repo(sub: argparse.ArgumentParser) -> None:
        # Each subcommand owns --repo so invocation order stays flexible
        # (command before or after the flag).
        sub.add_argument("--repo", required=True)

    listing = commands.add_parser("list", help="输出失败信号 JSON")
    add_repo(listing)
    ids = commands.add_parser("ids", help="只输出失败信号 ID")
    add_repo(ids)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = getattr(args, "command", None) or "list"
    if not hasattr(args, "repo"):
        parser.error("the following arguments are required: --repo")
    try:
        if command == "ids":
            for criterion_id in command_ids(args):
                print(criterion_id)
        else:
            result = command_list(args)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    except PickError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
