#!/usr/bin/env python3
"""用 BB 协调 distill 的阶段性复盘，不保存会话正文或修改仓库。

定义：`discover` 从 BB 的有界线程列表输出按时间窗筛出的候选；`plan` 对显式选中的
会话做只读预检，并校验 Review 聚合的 bb-dispatch 路由；`apply` 才向空闲会话发送
`$distill`，等待全部完成后创建一个只读聚合会话。脚本不能判断候选是否值得沉淀，
也不会执行 Phase 3 的文件修改。

参数：所有阶段复盘都必须给出带时区的 `--since` 和精确 `--threads`；当前只支持
`--scope repo-harness`。可重复的 `--continuation 原会话=续接会话` 把中断链折叠到
最终会话。`--until` 默认脚本启动时的 UTC 时间。`--project`、`--environment` 和
`--dispatch-config` 仅在默认 BB 上下文不适用时覆盖。

输出：成功时 stdout 输出 JSON；错误写 stderr。退出码 0=成功，1=BB 或流程状态错误，
2=参数错误。脚本不创建本地账本、不会保存 prompt、输出、日志、截图或密钥。

关键设计：BB 的线程记录是唯一运行事实源。`apply` 只对预检为空闲的最终会话使用
`bb thread tell --mode auto`，从不 steer 运行中的会话；任一蒸馏未完成即停止，不创建
聚合线程。显式 continuation 使中断和续接不被错误地统计为两次复发。

示例：
  python3 bb-stage-retro.py discover --since 2026-09-09T15:00:00+08:00
  python3 bb-stage-retro.py plan --scope repo-harness --since 2026-09-09T15:00:00+08:00 \
    --threads thr_a,thr_b --continuation thr_a=thr_b
  python3 bb-stage-retro.py apply --scope repo-harness --since 2026-09-09T15:00:00+08:00 \
    --threads thr_a,thr_b --continuation thr_a=thr_b
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SKILL_DIR = Path(__file__).resolve().parent.parent
DISPATCH_SCRIPT = SKILL_DIR.parent / "bb-model-routing" / "scripts" / "bb-dispatch"
THREAD_ID_RE = re.compile(r"^thr_[A-Za-z0-9]+$")
SCOPE = "repo-harness"
BUSY_STATUSES = {"pending", "starting", "active", "stopping"}


class RetroError(RuntimeError):
    """BB 返回值或阶段复盘计划不满足安全契约。"""


def parse_timestamp(value: str) -> datetime:
    """接受带时区 ISO-8601 时间并归一为 UTC，拒绝含糊的本地时间。"""
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "时间必须是带时区的 ISO-8601，例如 2026-09-09T15:00:00+08:00。"
        ) from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError(
            "时间必须带时区，例如 2026-09-09T15:00:00+08:00。"
        )
    return parsed.astimezone(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def command_json(command: list[str], timeout: int = 120) -> Any:
    """调用 JSON 形式的 BB 命令；失败时不给调用者伪造可继续的状态。"""
    try:
        result = subprocess.run(
            [*command, "--json"], capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RetroError(f"无法执行 {' '.join(command[:3])}：{exc}") from exc
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RetroError(f"{' '.join(command[:3])} 失败：{detail[:1200]}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RetroError(f"{' '.join(command[:3])} 返回非 JSON。") from exc


def bb(*args: str, timeout: int = 120) -> Any:
    return command_json(["bb", *args], timeout=timeout)


def record_from_show(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("thread"), dict):
        return value["thread"]
    if isinstance(value, dict):
        return value
    raise RetroError("bb thread show 返回格式未知。")


def require_thread_id(value: str) -> str:
    candidate = value.strip()
    if not THREAD_ID_RE.fullmatch(candidate):
        raise RetroError(f"无效会话 ID：{value!r}；应为 thr_ 开头的 BB thread ID。")
    return candidate


def parse_thread_ids(value: str) -> list[str]:
    ids = [require_thread_id(item) for item in value.split(",") if item.strip()]
    if not ids:
        raise RetroError("--threads 至少要包含一个会话 ID。")
    if len(ids) != len(set(ids)):
        raise RetroError("--threads 含有重复会话 ID。")
    return ids


def parse_continuations(values: Iterable[str], selected: set[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise RetroError("--continuation 必须为 原会话=续接会话。")
        source_raw, successor_raw = value.split("=", 1)
        source, successor = require_thread_id(source_raw), require_thread_id(successor_raw)
        if source == successor:
            raise RetroError("--continuation 的原会话和续接会话不能相同。")
        if source not in selected or successor not in selected:
            raise RetroError("--continuation 两端都必须包含在 --threads 中。")
        if source in mapping and mapping[source] != successor:
            raise RetroError(f"会话 {source} 有多个不同的续接会话。")
        mapping[source] = successor

    for source in mapping:
        seen: set[str] = set()
        current = source
        while current in mapping:
            if current in seen:
                raise RetroError("--continuation 不能形成环。")
            seen.add(current)
            current = mapping[current]
    return mapping


def final_successor(thread_id: str, continuations: dict[str, str]) -> str:
    current = thread_id
    while current in continuations:
        current = continuations[current]
    return current


def coverage_rows(selected: list[str], continuations: dict[str, str]) -> tuple[list[dict[str, str | None]], list[str]]:
    rows: list[dict[str, str | None]] = []
    workers: list[str] = []
    for thread_id in selected:
        final = final_successor(thread_id, continuations)
        covered_by = final if final != thread_id else None
        rows.append({"threadId": thread_id, "coveredBy": covered_by})
        if covered_by is None:
            workers.append(thread_id)
    return rows, workers


def resolve_context(project: str | None, environment: str | None) -> tuple[str, str]:
    context = bb("status")
    current_project = ((context.get("project") or {}).get("id")) if isinstance(context, dict) else None
    current_environment = (
        (((context.get("thread") or {}).get("environment") or {}).get("display") or {}).get("id")
        if isinstance(context, dict)
        else None
    )
    resolved_project, resolved_environment = project or current_project, environment or current_environment
    if not resolved_project or not resolved_environment:
        raise RetroError("无法从 bb status 确定项目或环境；请提供 --project 和 --environment。")
    return resolved_project, resolved_environment


def thread_record(thread_id: str, project: str) -> dict[str, Any]:
    record = record_from_show(bb("thread", "show", thread_id))
    if record.get("id") != thread_id:
        raise RetroError(f"bb thread show {thread_id} 返回了不匹配的会话。")
    if record.get("projectId") != project:
        raise RetroError(f"会话 {thread_id} 不属于目标项目 {project}。")
    return record


def title(record: dict[str, Any]) -> str:
    value = record.get("title") or record.get("titleFallback") or ""
    return " ".join(str(value).split())[:160]


@dataclass(frozen=True)
class ReviewPlan:
    project: str
    environment: str
    scope: str
    since: str
    until: str
    coverage: list[dict[str, str | None]]
    workers: list[str]
    records: dict[str, dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "environment": self.environment,
            "scope": self.scope,
            "window": {"since": self.since, "until": self.until},
            "coverage": self.coverage,
            "workers": [
                {"id": thread_id, "title": title(self.records[thread_id])}
                for thread_id in self.workers
            ],
        }


def make_plan(args: argparse.Namespace) -> ReviewPlan:
    if args.scope != SCOPE:
        raise RetroError(f"当前只支持 --scope {SCOPE}。")
    since, until = args.since, args.until or datetime.now(timezone.utc)
    if until < since:
        raise RetroError("--until 必须不早于 --since。")
    project, environment = resolve_context(args.project, args.environment)
    selected = parse_thread_ids(args.threads)
    continuations = parse_continuations(args.continuation, set(selected))
    coverage, workers = coverage_rows(selected, continuations)
    records = {thread_id: thread_record(thread_id, project) for thread_id in selected}
    for worker in workers:
        record = records[worker]
        if record.get("status") in BUSY_STATUSES:
            raise RetroError(
                f"最终会话 {worker} 当前为 {record.get('status')}；请等待其结束后再启动阶段复盘。"
            )
        if record.get("status") != "idle":
            raise RetroError(
                f"最终会话 {worker} 当前为 {record.get('status')}；请提供已完成的续接会话，或先处理该会话。"
            )
        if record.get("hasPendingInteraction"):
            raise RetroError(f"最终会话 {worker} 有待处理交互；先完成或取消该交互。")
    return ReviewPlan(
        project=project,
        environment=environment,
        scope=args.scope,
        since=iso_utc(since),
        until=iso_utc(until),
        coverage=coverage,
        workers=workers,
        records=records,
    )


def worker_prompt(plan: ReviewPlan, worker: str) -> str:
    coverage = next(row for row in plan.coverage if row["threadId"] == worker)
    return f"""$distill

执行 Session mode，只读复盘当前会话在阶段 {plan.since} 至 {plan.until} 内的工作。
范围固定为 {plan.scope}：只审计未来 Agent 在当前仓库会使用的 Skills、AGENTS.md、docs、脚本和本地验证入口。外部产品问题、个人偏好、凭据处置和一次性临时文件只标注为仓外、任务内或废弃，不扩张为仓内候选。

本会话的覆盖关系：thread={worker}，covered_by={coverage['coveredBy'] or 'none'}。遵守 distill 的全部证据、去重和权限规则；在第一次 Phase 3 决策简报处停止，不修改文件、Git、服务、数据库、外部系统或 BB 配置。

输出必须先给出一张简短表：模式键、证据边界、权威与范围、当前/建议权威落点、处置（采纳/已覆盖/仓外转交/废弃/待验证）。随后只呈现真正需要用户决定的 Phase 3 候选。"""


def aggregation_task(plan: ReviewPlan) -> str:
    workers = ", ".join(plan.workers)
    coverage = ", ".join(
        f"{row['threadId']}→{row['coveredBy'] or 'self'}" for row in plan.coverage
    )
    return f"""$distill

执行 Review mode 的 BB 阶段复盘。审计边界固定为 {plan.since} 至 {plan.until}，profile={plan.scope}，不得扩大范围。

只读取以下已完成 Session-mode 会话的最终输出：{workers}。使用 `bb thread output <id> --json` 获取它们；不得读取或复制原始会话日志、附件、截图、凭据，也不得向任何会话发送 follow-up。覆盖关系为：{coverage}。被续接会话只作为 covered_by 证据，不能增加 recurrence。

按 distill 证据规则去重，只保留未来 Agent 在当前仓库可使用的 Skills、AGENTS.md、docs、脚本和本地验证入口的候选。外部产品问题、凭据事件、个人偏好和一次性痕迹要明确标为仓外、废弃或待验证。

不修改任何文件或 BB 配置，在第一次 Phase 3 决策简报处停止。先输出固定去重表：模式键、证据与覆盖会话、权威与范围、唯一权威落点、处置；再按 distill 的正常格式给出真正需要用户决定的候选。"""


def dispatch_argv(plan: ReviewPlan, args: argparse.Namespace, dry_run: bool) -> list[str]:
    command = [
        str(DISPATCH_SCRIPT),
        "--difficulty",
        "complex",
        "--kind",
        "general",
        "--task",
        aggregation_task(plan),
        "--project",
        plan.project,
        "--environment",
        plan.environment,
        "--permission-mode",
        "accept-edits",
        "--title",
        "阶段复盘聚合",
    ]
    if args.dispatch_config:
        command += ["--config", args.dispatch_config]
    if dry_run:
        command.append("--dry-run")
    return command


def dispatch(plan: ReviewPlan, args: argparse.Namespace, dry_run: bool) -> Any:
    command = dispatch_argv(plan, args, dry_run)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RetroError(f"无法执行 bb-dispatch：{exc}") from exc
    if result.returncode:
        raise RetroError(f"bb-dispatch 失败：{(result.stderr.strip() or result.stdout.strip())[:1200]}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RetroError("bb-dispatch 返回非 JSON。") from exc


def command_discover(args: argparse.Namespace) -> dict[str, Any]:
    until = args.until or datetime.now(timezone.utc)
    if until < args.since:
        raise RetroError("--until 必须不早于 --since。")
    project, _ = resolve_context(args.project, None)
    records = bb("thread", "list", "--project", project)
    if not isinstance(records, list):
        raise RetroError("bb thread list 返回格式未知。")
    lower, upper = int(args.since.timestamp() * 1000), int(until.timestamp() * 1000)
    candidates = []
    for record in records:
        if not isinstance(record, dict):
            continue
        updated = record.get("updatedAt")
        if isinstance(updated, int) and lower <= updated <= upper:
            candidates.append(
                {
                    "id": record.get("id"),
                    "title": title(record),
                    "status": record.get("status"),
                    "createdAt": record.get("createdAt"),
                    "updatedAt": updated,
                    "parentThreadId": record.get("parentThreadId"),
                    "sourceThreadId": record.get("sourceThreadId"),
                }
            )
    return {
        "project": project,
        "window": {"since": iso_utc(args.since), "until": iso_utc(until)},
        "candidates": candidates,
        "coverage": "candidate-only：bb thread list 可能分页；请人工选择 material 会话后使用 plan。",
    }


def command_plan(args: argparse.Namespace) -> dict[str, Any]:
    plan = make_plan(args)
    return {
        "mode": "plan",
        "plan": plan.as_dict(),
        "workerPrompt": {worker: worker_prompt(plan, worker) for worker in plan.workers},
        "aggregateDispatch": dispatch(plan, args, dry_run=True),
    }


def command_apply(args: argparse.Namespace) -> dict[str, Any]:
    plan = make_plan(args)
    preflight = dispatch(plan, args, dry_run=True)
    deliveries: list[dict[str, Any]] = []
    for worker in plan.workers:
        delivery = bb("thread", "tell", "--mode", "auto", worker, worker_prompt(plan, worker))
        if isinstance(delivery, dict) and delivery.get("delivery") == "queued":
            raise RetroError(f"会话 {worker} 的 distill 请求被排队；未派发聚合者。先处理队列后重新 plan。")
        deliveries.append({"threadId": worker, "result": delivery})

    ready: list[dict[str, Any]] = []
    for worker in plan.workers:
        bb("thread", "wait", worker, "--status", "idle", "--timeout", str(args.wait_timeout_seconds), timeout=args.wait_timeout_seconds + 30)
        record = thread_record(worker, plan.project)
        if record.get("status") != "idle" or record.get("hasPendingInteraction"):
            raise RetroError(f"会话 {worker} 未完成 distill 或出现待处理交互；未派发聚合者。")
        ready.append({"threadId": worker, "status": record.get("status")})

    return {
        "mode": "apply",
        "plan": plan.as_dict(),
        "preflight": preflight,
        "workerDeliveries": deliveries,
        "workerReady": ready,
        "aggregateDispatch": dispatch(plan, args, dry_run=False),
    }


def add_window_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--since", required=True, type=parse_timestamp, help="带时区的 ISO-8601 起点。")
    parser.add_argument("--until", type=parse_timestamp, help="带时区的 ISO-8601 终点；默认当前 UTC。")
    parser.add_argument("--project", help="BB 项目 ID；默认从 bb status 获取。")


def add_review_arguments(parser: argparse.ArgumentParser) -> None:
    add_window_arguments(parser)
    parser.add_argument("--scope", required=True, choices=[SCOPE], help="当前仅支持 repo-harness。")
    parser.add_argument("--threads", required=True, help="逗号分隔的精确 BB 会话 ID。")
    parser.add_argument(
        "--continuation",
        action="append",
        default=[],
        metavar="原会话=续接会话",
        help="可重复；中断会话由最终续接会话覆盖。",
    )
    parser.add_argument("--environment", help="聚合会话使用的现有 BB 环境；默认当前环境。")
    parser.add_argument("--dispatch-config", help="可选 bb-dispatch 用户配置路径。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="用 BB 协调 distill 阶段复盘；默认只读，apply 才发送请求和创建聚合线程。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="输出：成功时 stdout 为 JSON；退出码 0=成功，1=流程或 BB 错误，2=参数错误。\n"
        "示例：\n"
        "  bb-stage-retro.py discover --since 2026-09-09T15:00:00+08:00\n"
        "  bb-stage-retro.py plan --scope repo-harness --since 2026-09-09T15:00:00+08:00 --threads thr_a,thr_b\n"
        "  bb-stage-retro.py apply --scope repo-harness --since 2026-09-09T15:00:00+08:00 --threads thr_a,thr_b\n",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    discover = commands.add_parser("discover", help="只读列出时间窗内的候选会话。")
    add_window_arguments(discover)

    plan = commands.add_parser("plan", help="只读预检会话和聚合路由。")
    add_review_arguments(plan)

    apply = commands.add_parser("apply", help="发送会话蒸馏并在成功后派发聚合者。")
    add_review_arguments(apply)
    apply.add_argument(
        "--wait-timeout-seconds",
        type=int,
        default=1200,
        help="等待每个 Session-mode 蒸馏空闲的秒数，默认 1200。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "discover":
            output = command_discover(args)
        elif args.command == "plan":
            output = command_plan(args)
        else:
            if args.wait_timeout_seconds <= 0:
                raise RetroError("--wait-timeout-seconds 必须大于 0。")
            output = command_apply(args)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except RetroError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
