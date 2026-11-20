#!/usr/bin/env python3
"""Materialize skill-test fixture templates into isolated skill directories.

Definition: test fixtures are stored with a ``.fixture`` filename suffix, so the
skill-test source tree contains no agent-facing file (``SKILL.md``,
``agents/openai.yaml``) and no skill scanner can load them. ``materialize``
copies one fixture into a fresh directory, restores the real filenames, and
drops a ``.skill-test-fixture.json`` marker used by cleanup. ``clean`` removes
only directories that carry that marker.
Parameters: ``materialize [--fixture NAME] [--dest DIR]`` and ``clean --dir DIR``.
Outputs: JSON on stdout. Exit 0 means success, 1 means operation error, and 2
means invalid CLI arguments.
Examples:
  python3 materialize_fixture.py materialize
  python3 materialize_fixture.py clean --dir /tmp/skill-test-echo-skill-xxxx
The caller hands the printed ``skill_md`` path to the test subagent and runs
``clean`` after evidence collection; nothing here touches the fixture source.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
MARKER_NAME = ".skill-test-fixture.json"
TEMPLATE_SUFFIX = ".fixture"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class FixtureError(RuntimeError):
    """The requested materialization or cleanup violates the contract."""


def available_fixtures() -> list[str]:
    if not FIXTURE_ROOT.is_dir():
        return []
    return sorted(
        entry.name
        for entry in FIXTURE_ROOT.iterdir()
        if entry.is_dir() and not entry.is_symlink() and NAME_RE.fullmatch(entry.name)
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="物化或清理 skill-test 的测试夹具模板。",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    materialize = commands.add_parser(
        "materialize", help="把 .fixture 模板复制到隔离目录并恢复真实文件名"
    )
    materialize.add_argument(
        "--fixture", default="echo-skill", choices=available_fixtures()
    )
    materialize.add_argument(
        "--dest", type=Path, default=None, help="目标目录；默认新建系统临时目录"
    )

    clean = commands.add_parser("clean", help="删除带夹具标记的物化目录")
    clean.add_argument("--dir", type=Path, required=True)
    return parser


def restore_template_names(root: Path) -> None:
    for path in sorted(root.rglob(f"*{TEMPLATE_SUFFIX}")):
        if path.is_file():
            path.rename(path.with_name(path.name[: -len(TEMPLATE_SUFFIX)]))


def command_materialize(args: argparse.Namespace) -> dict[str, str]:
    source = FIXTURE_ROOT / args.fixture
    if source.is_symlink() or not source.is_dir():
        raise FixtureError(f"unknown fixture: {args.fixture}")
    template = source / f"SKILL.md{TEMPLATE_SUFFIX}"
    if not template.is_file():
        raise FixtureError(f"fixture {args.fixture} has no SKILL.md template")

    if args.dest is None:
        destination = Path(tempfile.mkdtemp(prefix=f"skill-test-{args.fixture}-"))
    else:
        destination = args.dest.expanduser()
        destination = destination if destination.is_absolute() else Path.cwd() / destination
        destination = destination.resolve()
        if destination.exists():
            raise FixtureError(f"destination already exists: {destination}")

    shutil.copytree(source, destination, symlinks=False, dirs_exist_ok=True)
    restore_template_names(destination)
    skill_md = destination / "SKILL.md"
    if not skill_md.is_file():
        shutil.rmtree(destination, ignore_errors=True)
        raise FixtureError(f"fixture {args.fixture} did not restore a SKILL.md")
    marker = {
        "fixture": args.fixture,
        "materialized_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    }
    (destination / MARKER_NAME).write_text(
        json.dumps(marker, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "ok": True,
        "fixture": args.fixture,
        "dir": str(destination),
        "skill_md": str(skill_md),
    }


def command_clean(args: argparse.Namespace) -> dict[str, str]:
    target = args.dir.expanduser()
    target = target if target.is_absolute() else Path.cwd() / target
    target = target.resolve()
    if target.is_symlink() or not target.is_dir():
        raise FixtureError(f"not a materialized fixture directory: {target}")
    marker = target / MARKER_NAME
    if marker.is_symlink() or not marker.is_file():
        raise FixtureError(f"missing fixture marker; refusing to remove: {target}")
    shutil.rmtree(target)
    return {"ok": True, "removed": str(target)}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "materialize":
            result = command_materialize(args)
        else:
            result = command_clean(args)
    except FixtureError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
