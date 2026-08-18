#!/usr/bin/env python3
"""用固定提示词触发 large-task-planning 示例，并归档当次门户和校验结果。

参数定义：--agent/--model/--timeout 控制 acpx；--fresh（默认）先清空 docs/largeplan-example；--keep-existing 则在现有快照上续写。
输出定义：更新仓库 docs/largeplan-example/；把当次提示词、门户副本和 check 日志写入 examples/token-login/runs/<id>/。
退出码：0 生成且 check 通过，1 Agent 或 check 失败，2 参数/环境错误。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


EXAMPLE_DIR = Path(__file__).resolve().parent
SKILL_DIR = EXAMPLE_DIR.parents[1]
REPO_ROOT = EXAMPLE_DIR.parents[3]
PROMPT_TEMPLATE = EXAMPLE_DIR / "prompt.txt"
PORTAL_DIR = REPO_ROOT / "docs" / "largeplan-example"
RUNS_DIR = EXAMPLE_DIR / "runs"
CHECK_SCRIPT = SKILL_DIR / "scripts" / "epic_story.py"
DEFAULT_AGENT = "opencode"
DEFAULT_MODEL = "zai-coding-plan/glm-5.2"
DEFAULT_TIMEOUT = 1800


def usage() -> str:
    return f"""用法:
  python3 {Path(__file__).name} [options]

说明:
  读取本目录 prompt.txt，经 acpx 一次性会话生成 large-task-planning 示例门户，
  并把当次提示词、门户副本和脚本校验结果归档到 runs/<id>/。

选项:
  --agent <name>       acpx Agent，默认 {DEFAULT_AGENT}
  --model <id>         模型 ID，默认 {DEFAULT_MODEL}
  --timeout <seconds>  acpx 超时秒数，默认 {DEFAULT_TIMEOUT}
  --fresh              生成前清空 docs/largeplan-example（默认）
  --keep-existing      保留现有门户，让 Agent 在其上修改
  --dry-run            只打印将发送的提示词和命令，不调用 Agent
  -h, --help           显示帮助

输出:
  docs/largeplan-example/              最新门户
  examples/token-login/runs/<id>/      当次归档
  examples/token-login/last-run.json   最近一次运行摘要

退出码:
  0 生成完成且 epic_story.py check 通过
  1 Agent 失败，或 check/status 失败
  2 缺少 acpx、提示词或路径错误

示例:
  python3 {Path(__file__).name} --dry-run
  python3 {Path(__file__).name}
  python3 {Path(__file__).name} --keep-existing --timeout 2400
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="用固定提示词触发 large-task-planning 示例并归档当次结果。",
        epilog=usage(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="store_true", help="显示帮助")
    parser.add_argument("--agent", default=DEFAULT_AGENT, help=f"acpx Agent，默认 {DEFAULT_AGENT}")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"模型 ID，默认 {DEFAULT_MODEL}")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="acpx 超时秒数")
    parser.add_argument("--fresh", action="store_true", default=True, help="生成前清空现有门户")
    parser.add_argument(
        "--keep-existing",
        action="store_false",
        dest="fresh",
        help="保留现有门户，让 Agent 在其上修改",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印提示词和命令")
    return parser


def render_prompt() -> str:
    if not PROMPT_TEMPLATE.is_file():
        raise FileNotFoundError(f"找不到提示词: {PROMPT_TEMPLATE}")
    return PROMPT_TEMPLATE.read_text(encoding="utf-8").format(skill_dir=SKILL_DIR)


def copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def run_checked(command: Sequence[str], cwd: Path, log_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if log_path is not None:
        log_path.write_text(
            f"$ {' '.join(command)}\nexit={result.returncode}\n\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            encoding="utf-8",
        )
    return result


def command_preview(args: argparse.Namespace, prompt_file: Path) -> list[str]:
    return [
        "acpx",
        "--cwd",
        str(REPO_ROOT),
        "--format",
        "json",
        "--timeout",
        str(args.timeout),
        "--approve-all",
        "--model",
        args.model,
        args.agent,
        "exec",
        "--file",
        str(prompt_file),
    ]


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def snapshot_portal(label: Path, source: Path) -> None:
    if source.is_dir():
        copy_tree(source, label)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.help:
        print(usage())
        return 0
    if args.timeout <= 0:
        print("ERROR: --timeout 必须是正整数", file=sys.stderr)
        return 2

    try:
        prompt = render_prompt()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(prompt, end="" if prompt.endswith("\n") else "\n")
        print("---")
        print(" ".join(command_preview(args, RUNS_DIR / "<id>" / "prompt.sent.txt")))
        print(f"fresh={args.fresh}")
        print(f"portal={PORTAL_DIR}")
        return 0

    if shutil.which("acpx") is None:
        print("ERROR: 找不到 acpx，请先安装并加入 PATH", file=sys.stderr)
        return 2
    if not CHECK_SCRIPT.is_file():
        print(f"ERROR: 找不到校验脚本 {CHECK_SCRIPT}", file=sys.stderr)
        return 2

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    sent_prompt = run_dir / "prompt.sent.txt"
    sent_prompt.write_text(prompt, encoding="utf-8")
    acpx_out = run_dir / "acpx.ndjson"
    acpx_err = run_dir / "acpx.err"

    if args.fresh and PORTAL_DIR.exists():
        snapshot_portal(run_dir / "before", PORTAL_DIR)
        shutil.rmtree(PORTAL_DIR)

    command = command_preview(args, sent_prompt)
    print(f"INFO: run_id={run_id}")
    print(f"INFO: {' '.join(command)}")
    with acpx_out.open("w", encoding="utf-8") as out, acpx_err.open("w", encoding="utf-8") as err:
        acpx = subprocess.run(command, cwd=REPO_ROOT, stdout=out, stderr=err, check=False)

    snapshot_portal(run_dir / "portal", PORTAL_DIR)
    check_log = run_dir / "check.log"
    status_path = run_dir / "status.json"
    check_ok = False
    status_ok = False
    if PORTAL_DIR.is_dir():
        epic = PORTAL_DIR / "epics"
        epic_files = sorted(epic.glob("EPIC-*.md")) if epic.is_dir() else []
        stories = PORTAL_DIR / "stories"
        overview = PORTAL_DIR / "README.md"
        dashboard = PORTAL_DIR / "项目进展.md"
        if epic_files and stories.is_dir():
            common = [
                sys.executable,
                str(CHECK_SCRIPT),
                "--epic",
                str(epic_files[0]),
                "--stories-dir",
                str(stories),
            ]
            checked = run_checked(
                [*common[:2], "check", *common[2:], "--overview", str(overview), "--dashboard", str(dashboard)],
                REPO_ROOT,
                check_log,
            )
            check_ok = checked.returncode == 0
            status = run_checked([*common[:2], "status", *common[2:], "--json"], REPO_ROOT)
            status_ok = status.returncode == 0
            status_path.write_text(status.stdout or status.stderr, encoding="utf-8")
        else:
            check_log.write_text("ERROR: 未找到 Epic 或 stories 目录\n", encoding="utf-8")
    else:
        check_log.write_text("ERROR: 未生成 docs/largeplan-example\n", encoding="utf-8")

    meta = {
        "run_id": run_id,
        "agent": args.agent,
        "model": args.model,
        "timeout": args.timeout,
        "fresh": args.fresh,
        "acpx_exit": acpx.returncode,
        "check_ok": check_ok,
        "status_ok": status_ok,
        "portal": str(PORTAL_DIR),
        "archive": str(run_dir),
        "prompt_file": str(PROMPT_TEMPLATE),
        "skill_dir": str(SKILL_DIR),
    }
    write_json(run_dir / "meta.json", meta)
    write_json(EXAMPLE_DIR / "last-run.json", meta)
    print(f"INFO: archive={run_dir}")
    print(f"INFO: acpx_exit={acpx.returncode} check_ok={check_ok}")

    if acpx.returncode != 0:
        print(f"ERROR: acpx 失败，见 {acpx_err}", file=sys.stderr)
        return 1
    if not check_ok:
        print(f"ERROR: 示例 check 未通过，见 {check_log}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
