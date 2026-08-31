#!/usr/bin/env python3
"""从一次 ACPX prompt 的 NDJSON 事件流读出确定性的外部 Agent 执行结果。

脚本定义：`acpx --format json --json-strict` 输出的是 JSON-RPC NDJSON，不是单个 JSON
文档，整体 `json.loads` 必然失败。本脚本是 large-task-orchestrator 读取 worker/validator
结果的唯一入口：解析该流，定位本次 prompt 的回合结果，抽取最终 agent 消息与角色契约块，
并给出 provider session 连续性、运行时错误、权限结局和工具调用摘要。它只读流，不改计划状态、
不写运行历史、不重试、不自动分类 quota。
参数定义：必须传 `--stream <ndjson>`；`--expect` 选 worker/validator 时才校验角色契约；
`--session` 传 dispatch 前记录的 provider session 标识以判定连续性；`--acpx-exit` 可传包装命令
记录的 ACPX 退出码；`--message-tail` 控制 stdout 里的消息尾巴长度（0 表示不输出）；
`--message-out` 把完整最终消息落到文件。
输出定义：成功时 stdout 输出 JSON，含 ok、lines、prompt、session、turn、errors、permissions、
tool_calls、message、report、failure、problems、warnings。`failure.classification` 在
验证器遇到权限提示不可用或 ACPX 退出码 5 时为 `permission_policy_mismatch`。退出码 0=拿到可信结果（含 worker 报告
status=blocked 这类可信坏消息），1=流可读但本次执行没有干净结果或契约不合法，2=参数或 IO 错误。
关键设计：回合结果只认与 `session/prompt` 相同 `id` 的响应，避免把 `session/request_permission`
的客户端响应误当结果；契约块优先取末尾 fenced JSON，其次取「后面只剩空白」的末尾 JSON object，
以匹配「最终回复以该块结尾」的契约；`problems` 非空即 ok=false，`warnings` 只提示需要人看一眼
的事实，不改变退出码。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence


SCRIPT_PATH = Path(__file__).resolve()
CONTRACTS = ("none", "worker", "validator")
WORKER_FIELDS = (
    "story_id",
    "status",
    "summary",
    "files_changed",
    "verification",
    "remaining_work",
    "blocker",
    "handoff",
)
WORKER_STATUSES = ("worker_done", "blocked", "failed", "quota_exhausted")
VERIFICATION_FIELDS = ("command", "result", "evidence")
CONCLUSIONS = ("CONTINUE", "PATCH_PROMPT", "INSERT_STORY", "REPLAN")
CLEAN_STOP_REASON = "end_turn"
PERMISSION_POLICY_MISMATCH_CLASS = "permission_policy_mismatch"
PERMISSION_PROMPT_UNAVAILABLE_CODE = "PERMISSION_PROMPT_UNAVAILABLE"
PERMISSION_PROMPT_UNAVAILABLE_RE = re.compile(
    r"permission\s+prompt\s+unavailable", re.IGNORECASE
)
MAX_ERRORS = 5
MAX_FAILED_TOOL_CALLS = 10
MAX_TITLE_CHARS = 200
DEFAULT_MESSAGE_TAIL = 2000

FENCED_JSON_RE = re.compile(r"```(?:json|JSON)?[ \t]*\r?\n(.*?)```", re.DOTALL)
CONCLUSION_RE = re.compile(r"(?:结论|Conclusion)\s*[:：]\s*(.+)")


class StreamError(RuntimeError):
    """事件流不可读，或参数指向的路径不是可读普通文件。"""


def usage() -> str:
    return f"""用法:
  python3 {SCRIPT_PATH.name} --stream <ndjson> [--expect worker|validator]
      [--session <provider-session-id>] [--acpx-exit <code>] [--message-tail <chars>]
      [--message-out <path>]

说明:
  读取一次 `acpx --format json --json-strict ... > <ndjson>` 的事件流，输出这次执行的
  确定性事实。流里最后一个 `session/prompt` 是受检回合；回合结果只认与它 `id` 相同的
  响应。脚本不检查仓库改动是否落地，编排者仍需独立看 diff 与测试证据。

参数:
  --stream <ndjson>       ACPX NDJSON 事件流文件（必填）。
  --expect <contract>     none（默认）、worker 或 validator；只有后两者校验角色契约。
  --session <id>          dispatch 前记录的 provider session 标识，用于连续性判定。
  --acpx-exit <code>      外层 ACPX 命令的退出码；任何非零码都会阻止信任，验证器为 5
                          另标记权限策略不匹配。
  --message-tail <chars>  stdout 中最终消息尾巴的字符数，默认 {DEFAULT_MESSAGE_TAIL}，0 表示不输出。
  --message-out <path>    把完整最终 agent 消息写入该文件（UTF-8）。
  -h, --help              显示帮助。

输出:
  stdout 输出 UTF-8 JSON：
    ok            是否拿到可信回合结果（problems 为空）。
    lines         total/parsed/unparsed 行数。
    prompt        受检回合的 request_id、session_id 与流中 prompt 总数。
    session       expected/observed/continuity（match|mismatch|unknown）。
    turn          kind（result|error|missing）、stop_reason、usage、error。
    errors        流中错误响应（最多 {MAX_ERRORS} 条：code/message/acpx_code/detail_code/origin）。
    permissions   权限请求数与结局计数。
    tool_calls    总数、状态分布与失败列表（最多 {MAX_FAILED_TOOL_CALLS} 条）。
    message       最终 agent 消息字符数与尾巴（不含 thought）。
    report        --expect 指定时的契约块：found/source/contract/valid/problems/value。
    failure       可供编排路由的机器可读失败分类；权限策略不匹配为
                  permission_policy_mismatch；同时保留 acpx_exit。
    problems      使 ok=false 的固定原因码。
    warnings      需要人看一眼但不改变退出码的事实。
  worker 报告 status=blocked/failed/quota_exhausted 仍是可信结果，退出码 0；由编排者按
  report.value.status 或 report.value.conclusion 路由。错误写 stderr。
  退出码：0=可信结果，1=没有干净结果或契约不合法，2=参数或 IO 错误。

示例:
  python3 {SCRIPT_PATH.name} \\
    --stream .local/large-task-orchestrator/run-STORY-01-worker-1.ndjson \\
    --expect worker --session 01a05684-0eef-7231-997f-96396480d5bf
  python3 {SCRIPT_PATH.name} \\
    --stream .local/large-task-orchestrator/run-STORY-01-validator-1.ndjson \\
    --expect validator --session 01a05684-0eef-7231-997f-96396480d5bf \\
    --message-out /tmp/story-01-review.txt
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="解析 ACPX NDJSON 事件流并输出一次外部 Agent 执行结果。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=usage(),
    )
    parser.add_argument("--stream", required=True, type=Path, help="ACPX NDJSON 事件流文件")
    parser.add_argument(
        "--expect",
        default="none",
        choices=CONTRACTS,
        help="要校验的角色契约，默认 none",
    )
    parser.add_argument("--session", help="dispatch 前记录的 provider session 标识")
    parser.add_argument(
        "--acpx-exit",
        type=int,
        help="外层 ACPX 命令退出码；非零码阻止信任并用于识别权限提示不可用",
    )
    parser.add_argument(
        "--message-tail",
        type=int,
        default=DEFAULT_MESSAGE_TAIL,
        help=f"stdout 中消息尾巴字符数，默认 {DEFAULT_MESSAGE_TAIL}，0 表示不输出",
    )
    parser.add_argument("--message-out", type=Path, help="完整最终消息的输出文件")
    return parser


def _read_lines(path: Path) -> list[str]:
    if path.is_dir():
        raise StreamError(f"{path}: --stream 必须是文件而不是目录")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError as error:
        raise StreamError(f"{path}: 事件流文件不存在") from error
    except (OSError, UnicodeError) as error:
        raise StreamError(f"{path}: 无法读取事件流: {error}") from error
    return text.splitlines()


class Stream:
    """一次 prompt 事件流的解析结果。"""

    def __init__(self, lines: Sequence[str]) -> None:
        self.total = 0
        self.parsed = 0
        self.unparsed = 0
        self.prompts: list[dict[str, Any]] = []
        self.responses: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.sessions: list[str] = []
        self.message_parts: list[str] = []
        self.tool_calls: dict[str, dict[str, Any]] = {}
        self.permission_requests = 0
        self.permission_outcomes: dict[str, int] = {}
        self._entries: list[dict[str, Any]] = []
        for line in lines:
            if not line.strip():
                continue
            self.total += 1
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                self.unparsed += 1
                continue
            if not isinstance(entry, dict):
                self.unparsed += 1
                continue
            self.parsed += 1
            self._entries.append(entry)
            self._classify(entry)
        self.prompt = self.prompts[-1] if self.prompts else None
        self.prompt_session = self._prompt_session()
        self._collect_updates()

    def _classify(self, entry: dict[str, Any]) -> None:
        method = entry.get("method")
        params = entry.get("params") if isinstance(entry.get("params"), dict) else {}
        session_id = params.get("sessionId")
        if isinstance(session_id, str) and session_id not in self.sessions:
            self.sessions.append(session_id)
        if method == "session/prompt":
            self.prompts.append(entry)
            return
        if method == "session/request_permission":
            self.permission_requests += 1
            return
        if method is not None:
            return
        if "error" in entry:
            self.errors.append(entry)
            error = entry["error"]
            data = error.get("data") if isinstance(error, dict) else None
            if isinstance(data, dict):
                error_session = data.get("sessionId")
                if isinstance(error_session, str) and error_session not in self.sessions:
                    self.sessions.append(error_session)
            return
        if "result" in entry:
            self.responses.append(entry)

    def _prompt_session(self) -> str | None:
        if self.prompt is None:
            return None
        params = self.prompt.get("params")
        if not isinstance(params, dict):
            return None
        session_id = params.get("sessionId")
        return session_id if isinstance(session_id, str) else None

    def _collect_updates(self) -> None:
        # 权限结局响应与回合结果都是无 method 的响应；先排除受检回合 id，再按 outcome 归类。
        prompt_id = self.prompt.get("id") if self.prompt is not None else None
        for entry in self._entries:
            if entry.get("method") is None and "result" in entry:
                if self.prompt is not None and entry.get("id") == prompt_id:
                    continue
                result = entry["result"]
                outcome = result.get("outcome") if isinstance(result, dict) else None
                if isinstance(outcome, dict):
                    kind = outcome.get("outcome")
                    key = kind if isinstance(kind, str) else "unknown"
                    self.permission_outcomes[key] = self.permission_outcomes.get(key, 0) + 1
                continue
            params = entry.get("params")
            if not isinstance(params, dict):
                continue
            if self.prompt_session is not None and params.get("sessionId") not in (
                None,
                self.prompt_session,
            ):
                continue
            update = params.get("update")
            if not isinstance(update, dict):
                continue
            kind = update.get("sessionUpdate")
            if kind == "agent_message_chunk":
                content = update.get("content")
                if isinstance(content, dict) and content.get("type") == "text":
                    text = content.get("text")
                    if isinstance(text, str):
                        self.message_parts.append(text)
            elif kind in ("tool_call", "tool_call_update"):
                self._record_tool_call(update)

    def _record_tool_call(self, update: dict[str, Any]) -> None:
        call_id = update.get("toolCallId")
        if not isinstance(call_id, str):
            return
        record = self.tool_calls.setdefault(call_id, {"title": None, "status": None})
        title = update.get("title")
        if isinstance(title, str) and title and record["title"] is None:
            record["title"] = title[:MAX_TITLE_CHARS]
        status = update.get("status")
        if isinstance(status, str) and status:
            record["status"] = status

    @property
    def message(self) -> str:
        return "".join(self.message_parts)

    def turn_response(self) -> dict[str, Any] | None:
        if self.prompt is None:
            return None
        prompt_id = self.prompt.get("id")
        for entry in reversed(self.responses):
            if entry.get("id") == prompt_id:
                return entry
        return None

    def turn_error(self) -> dict[str, Any] | None:
        if self.prompt is not None:
            prompt_id = self.prompt.get("id")
            for entry in reversed(self.errors):
                if entry.get("id") == prompt_id:
                    return entry
        return self.errors[-1] if self.errors else None


def _describe_error(entry: dict[str, Any]) -> dict[str, Any]:
    error = entry.get("error")
    if not isinstance(error, dict):
        return {"code": None, "message": None, "acpx_code": None, "detail_code": None, "origin": None}
    data = error.get("data") if isinstance(error.get("data"), dict) else {}
    message = error.get("message")
    return {
        "code": error.get("code"),
        "message": message[:MAX_TITLE_CHARS] if isinstance(message, str) else None,
        "acpx_code": data.get("acpxCode", data.get("acpx_code")),
        "detail_code": data.get("detailCode", data.get("detail_code")),
        "origin": data.get("origin"),
    }


def _is_permission_policy_mismatch(
    contract: str,
    stream: Stream,
    turn: dict[str, Any],
    acpx_exit: int | None,
) -> bool:
    """识别验证器权限策略错误，不把它误当成配额或审查结论。"""
    if contract != "validator":
        return False
    if acpx_exit == 5:
        return True
    # 重定向文件通常只有一个 prompt，但异常重试可能包含多个；只让最后一个受检
    # prompt 之后的错误参与分类，避免旧权限错误污染后续已经干净的结论。
    prompt_index = -1
    if stream.prompt is not None:
        prompt_index = max(
            (
                index
                for index, entry in enumerate(stream._entries)
                if entry is stream.prompt
            ),
            default=-1,
        )
    descriptions = [
        _describe_error(entry)
        for entry in stream._entries[prompt_index + 1 :]
        if "error" in entry
    ]
    if isinstance(turn.get("error"), dict):
        descriptions.append(turn["error"])
    for error in descriptions:
        if error.get("acpx_code") == PERMISSION_PROMPT_UNAVAILABLE_CODE:
            return True
        message = error.get("message")
        if isinstance(message, str) and PERMISSION_PROMPT_UNAVAILABLE_RE.search(message):
            return True
    return False


def _numeric_fields(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    numbers = {
        key: item
        for key, item in value.items()
        if isinstance(item, (int, float)) and not isinstance(item, bool)
    }
    return numbers or None


def _tool_call_summary(calls: dict[str, dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    failed: list[dict[str, Any]] = []
    for record in calls.values():
        status = record["status"] or "unknown"
        by_status[status] = by_status.get(status, 0) + 1
        if status == "failed":
            failed.append({"title": record["title"], "status": status})
    return {
        "total": len(calls),
        "by_status": by_status,
        "failed": failed[:MAX_FAILED_TOOL_CALLS],
        "failed_truncated": len(failed) > MAX_FAILED_TOOL_CALLS,
    }


def _trailing_json_object(message: str) -> dict[str, Any] | None:
    """取「后面只剩空白」的末尾 JSON object，匹配最终回复以契约块结尾的要求。"""
    decoder = json.JSONDecoder()
    index = message.rfind("{")
    while index >= 0:
        try:
            value, end = decoder.raw_decode(message[index:])
        except json.JSONDecodeError:
            value = None
            end = 0
        if isinstance(value, dict) and not message[index + end :].strip():
            return value
        index = message.rfind("{", 0, index)
    return None


def _extract_json_report(message: str) -> tuple[dict[str, Any] | None, str | None]:
    for match in reversed(FENCED_JSON_RE.findall(message)):
        try:
            value = json.loads(match)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value, "fenced-json-block"
    trailing = _trailing_json_object(message)
    if trailing is not None:
        return trailing, "trailing-object"
    return None, None


def _validate_worker_report(value: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    missing = [field for field in WORKER_FIELDS if field not in value]
    if missing:
        problems.append(f"missing fields {missing}")
    for field in ("story_id", "summary", "handoff"):
        if field in value and not isinstance(value[field], str):
            problems.append(f"{field} must be a string")
    if "story_id" in value and isinstance(value["story_id"], str) and not value["story_id"]:
        problems.append("story_id must be non-empty")
    if "status" in value and value["status"] not in WORKER_STATUSES:
        problems.append(f"status must be one of {list(WORKER_STATUSES)}")
    for field in ("files_changed", "remaining_work"):
        if field in value and not isinstance(value[field], list):
            problems.append(f"{field} must be an array")
    if "blocker" in value and value["blocker"] is not None and not isinstance(value["blocker"], str):
        problems.append("blocker must be null or a string")
    if "verification" in value:
        verification = value["verification"]
        if not isinstance(verification, list):
            problems.append("verification must be an array")
        else:
            for index, item in enumerate(verification):
                if not isinstance(item, dict):
                    problems.append(f"verification[{index}] must be an object")
                    continue
                for field in VERIFICATION_FIELDS:
                    if not isinstance(item.get(field), str) or not item[field]:
                        problems.append(
                            f"verification[{index}].{field} must be a non-empty string"
                        )
    return problems


def _worker_report(message: str) -> dict[str, Any]:
    value, source = _extract_json_report(message)
    if value is None:
        return {
            "found": False,
            "source": None,
            "contract": "worker",
            "valid": False,
            "problems": ["no trailing strict JSON block found in the final message"],
            "value": None,
        }
    problems = _validate_worker_report(value)
    return {
        "found": True,
        "source": source,
        "contract": "worker",
        "valid": not problems,
        "problems": problems,
        "value": value,
    }


def _conclusion_candidates(message: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for number, line in enumerate(message.splitlines(), start=1):
        match = CONCLUSION_RE.search(line)
        if match is None:
            continue
        rest = match.group(1)
        tokens = [name for name in CONCLUSIONS if re.search(rf"\b{name}\b", rest)]
        # 模板回显把四个结论写在同一行；只有恰好一个 token 的行才是真正的结论。
        if len(tokens) == 1:
            candidates.append(
                {"conclusion": tokens[0], "line": number, "text": line.strip()[:MAX_TITLE_CHARS]}
            )
    return candidates


def _validator_report(message: str) -> dict[str, Any]:
    candidates = _conclusion_candidates(message)
    if not candidates:
        return {
            "found": False,
            "source": None,
            "contract": "validator",
            "valid": False,
            "problems": [f"no single-conclusion line found among {list(CONCLUSIONS)}"],
            "value": None,
        }
    chosen = candidates[-1]
    distinct = sorted({candidate["conclusion"] for candidate in candidates})
    problems: list[str] = []
    if len(distinct) > 1:
        problems.append(f"conflicting conclusions {distinct}")
    return {
        "found": True,
        "source": "conclusion-line",
        "contract": "validator",
        "valid": not problems,
        "problems": problems,
        "value": chosen,
    }


def _report(contract: str, message: str) -> dict[str, Any] | None:
    if contract == "worker":
        return _worker_report(message)
    if contract == "validator":
        return _validator_report(message)
    return None


def _write_message(path: Path, message: str) -> None:
    try:
        path.write_text(message, encoding="utf-8")
    except OSError as error:
        raise StreamError(f"{path}: 无法写出完整消息: {error}") from error


def inspect(args: argparse.Namespace) -> dict[str, Any]:
    if args.message_tail < 0:
        raise StreamError("--message-tail 必须是非负整数")
    acpx_exit = getattr(args, "acpx_exit", None)
    if acpx_exit is not None and acpx_exit < 0:
        raise StreamError("--acpx-exit 必须是非负整数")
    stream_path = args.stream.expanduser()
    stream = Stream(_read_lines(stream_path))

    observed = list(stream.sessions)
    if args.session is None:
        continuity = "unknown"
    elif observed == [args.session]:
        continuity = "match"
    else:
        continuity = "mismatch"

    response = stream.turn_response()
    error_entry = stream.turn_error()
    if response is not None:
        result = response.get("result") if isinstance(response.get("result"), dict) else {}
        turn = {
            "kind": "result",
            "stop_reason": result.get("stopReason"),
            "usage": _numeric_fields(result.get("usage")),
            "error": None,
        }
    elif error_entry is not None:
        turn = {
            "kind": "error",
            "stop_reason": None,
            "usage": None,
            "error": _describe_error(error_entry),
        }
    else:
        turn = {"kind": "missing", "stop_reason": None, "usage": None, "error": None}

    message = stream.message
    report = _report(args.expect, message)
    permission_policy_mismatch = _is_permission_policy_mismatch(
        args.expect, stream, turn, acpx_exit
    )

    problems: list[str] = []
    if stream.prompt is None:
        problems.append("prompt-missing")
    if acpx_exit is not None and acpx_exit != 0:
        problems.append("acpx-exit-nonzero")
    if turn["kind"] == "missing":
        problems.append("turn-missing")
    elif turn["kind"] == "error":
        problems.append("turn-error")
    elif turn["stop_reason"] != CLEAN_STOP_REASON:
        problems.append("stop-reason-not-end-turn")
    if continuity == "mismatch":
        problems.append("session-mismatch")
    if report is not None:
        if not report["found"]:
            problems.append("report-missing")
        elif not report["valid"]:
            problems.append("report-invalid")
    if permission_policy_mismatch:
        problems.append("permission-policy-mismatch")

    tool_calls = _tool_call_summary(stream.tool_calls)
    warnings: list[str] = []
    if stream.unparsed:
        warnings.append("unparsed-lines")
    if len(stream.prompts) > 1:
        warnings.append("multiple-prompts")
    if stream.permission_requests and any(
        key != "selected" for key in stream.permission_outcomes
    ):
        warnings.append("permission-not-granted")
    if stream.permission_requests > sum(stream.permission_outcomes.values()):
        warnings.append("permission-unanswered")
    if tool_calls["failed"]:
        warnings.append("tool-call-failed")
    if not message:
        warnings.append("no-agent-message")

    if args.message_out is not None:
        _write_message(args.message_out.expanduser(), message)

    result_payload: dict[str, Any] = {
        "ok": not problems,
        "stream": str(stream_path),
        "lines": {
            "total": stream.total,
            "parsed": stream.parsed,
            "unparsed": stream.unparsed,
        },
        "prompt": {
            "request_id": stream.prompt.get("id") if stream.prompt is not None else None,
            "session_id": stream.prompt_session,
            "total": len(stream.prompts),
        },
        "session": {
            "expected": args.session,
            "observed": observed,
            "continuity": continuity,
        },
        "turn": turn,
        "errors": [_describe_error(entry) for entry in stream.errors[-MAX_ERRORS:]],
        "permissions": {
            "requests": stream.permission_requests,
            "outcomes": stream.permission_outcomes,
        },
        "tool_calls": tool_calls,
        "message": {
            "chars": len(message),
            "tail": message[-args.message_tail :] if args.message_tail else None,
            "out": str(args.message_out.expanduser()) if args.message_out is not None else None,
        },
        "report": report,
        "failure": {
            "classification": (
                PERMISSION_POLICY_MISMATCH_CLASS
                if permission_policy_mismatch
                else None
            ),
            "acpx_exit": acpx_exit,
        },
        "problems": problems,
        "warnings": warnings,
    }
    return result_payload


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = inspect(args)
    except StreamError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
