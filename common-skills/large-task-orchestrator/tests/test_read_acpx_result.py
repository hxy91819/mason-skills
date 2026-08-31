from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


SCRIPT = Path(__file__).parents[1] / "scripts" / "read_acpx_result.py"
POLICY = Path(__file__).parents[1] / "references" / "validator-permission-policy.json"
ACPX_REFERENCE = Path(__file__).parents[1] / "references" / "acpx.md"
SESSION = "01a05684-0eef-7231-997f-96396480d5bf"


def prompt(session: str = SESSION, request_id: Any = 3) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "session/prompt",
        "params": {"sessionId": session, "prompt": [{"type": "text", "text": "task"}]},
    }


def chunk(text: str, session: str = SESSION) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": session,
            "update": {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": text},
            },
        },
    }


def thought(text: str, session: str = SESSION) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {
            "sessionId": session,
            "update": {
                "sessionUpdate": "agent_thought_chunk",
                "content": {"type": "text", "text": text},
            },
        },
    }


def tool_call(
    call_id: str,
    title: str,
    status: str | None = None,
    kind: str = "tool_call",
    session: str = SESSION,
) -> dict[str, Any]:
    update: dict[str, Any] = {"sessionUpdate": kind, "toolCallId": call_id, "title": title}
    if status is not None:
        update["status"] = status
    return {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {"sessionId": session, "update": update},
    }


def result(request_id: Any = 3, stop_reason: str = "end_turn") -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "stopReason": stop_reason,
            "usage": {"totalTokens": 12, "inputTokens": 4, "_meta": {"nested": 1}},
        },
    }


def permission_request(session: str = SESSION) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "method": "session/request_permission",
        "params": {
            "sessionId": session,
            "toolCall": {"toolCallId": "call-1", "title": "Reading files"},
            "options": [{"optionId": "allow_once", "name": "Yes", "kind": "allow_once"}],
        },
    }


def permission_response(outcome: str, request_id: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"outcome": outcome}
    if outcome == "selected":
        payload["optionId"] = "allow_once"
    return {"jsonrpc": "2.0", "id": request_id, "result": {"outcome": payload}}


def runtime_error(session: str = SESSION) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": None,
        "error": {
            "code": -32072,
            "message": "Permission prompt unavailable in non-interactive mode",
            "data": {
                "acpxCode": "PERMISSION_PROMPT_UNAVAILABLE",
                "detailCode": "QUEUE_RUNTIME_PROMPT_FAILED",
                "origin": "runtime",
                "sessionId": session,
            },
        },
    }


def worker_report(**overrides: Any) -> dict[str, Any]:
    report = {
        "story_id": "STORY-01",
        "status": "worker_done",
        "summary": "observable outcome",
        "files_changed": ["a.py"],
        "verification": [
            {"command": "pytest", "result": "pass", "evidence": "3 passed"}
        ],
        "remaining_work": [],
        "blocker": None,
        "handoff": "context for the validator",
    }
    report.update(overrides)
    return report


class ReadAcpxResultTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_validator_permission_policy_is_exact_and_fail_closed(self) -> None:
        expected = {
            "autoApprove": ["read", "search", "execute"],
            "autoDeny": ["edit", "delete", "move", "fetch", "switch_mode"],
            "defaultAction": "deny",
        }
        self.assertEqual(json.loads(POLICY.read_text(encoding="utf-8")), expected)
        match = re.search(
            r"```json\s*([\s\S]*?)\s*```",
            ACPX_REFERENCE.read_text(encoding="utf-8"),
        )
        self.assertIsNotNone(match)
        self.assertEqual(json.loads(match.group(1)), expected)

    def write_stream(self, entries: list[Any], name: str = "stream.ndjson") -> Path:
        path = self.root / name
        lines = [
            entry if isinstance(entry, str) else json.dumps(entry, ensure_ascii=False)
            for entry in entries
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def run_script(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )

    def inspect(self, *arguments: str, expected_code: int = 0) -> dict[str, Any]:
        completed = self.run_script(*arguments)
        self.assertEqual(
            completed.returncode,
            expected_code,
            f"stdout={completed.stdout}\nstderr={completed.stderr}",
        )
        return json.loads(completed.stdout)

    def test_worker_stream_with_fenced_report_is_trusted(self) -> None:
        stream = self.write_stream(
            [
                prompt(),
                thought("internal reasoning that must stay out of the message"),
                chunk("完成。\n\n```json\n"),
                chunk(json.dumps(worker_report(), ensure_ascii=False)),
                chunk("\n```"),
                tool_call("call-1", "pytest"),
                tool_call("call-1", "pytest", status="completed", kind="tool_call_update"),
                result(),
            ]
        )
        payload = self.inspect("--stream", str(stream), "--expect", "worker", "--session", SESSION)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["problems"], [])
        self.assertEqual(payload["prompt"], {"request_id": 3, "session_id": SESSION, "total": 1})
        self.assertEqual(payload["session"]["continuity"], "match")
        self.assertEqual(payload["turn"]["kind"], "result")
        self.assertEqual(payload["turn"]["stop_reason"], "end_turn")
        self.assertEqual(payload["turn"]["usage"], {"totalTokens": 12, "inputTokens": 4})
        self.assertEqual(payload["report"]["source"], "fenced-json-block")
        self.assertTrue(payload["report"]["valid"])
        self.assertEqual(payload["report"]["value"]["status"], "worker_done")
        self.assertEqual(payload["tool_calls"]["by_status"], {"completed": 1})
        self.assertNotIn("internal reasoning", payload["message"]["tail"])

    def test_trailing_object_without_fence_is_accepted(self) -> None:
        stream = self.write_stream(
            [
                prompt(),
                chunk("done\n"),
                chunk(json.dumps(worker_report(), ensure_ascii=False) + "\n"),
                result(),
            ]
        )
        payload = self.inspect("--stream", str(stream), "--expect", "worker")
        self.assertEqual(payload["report"]["source"], "trailing-object")
        self.assertTrue(payload["report"]["valid"])
        self.assertEqual(payload["session"]["continuity"], "unknown")

    def test_json_object_before_trailing_prose_is_not_a_report(self) -> None:
        stream = self.write_stream(
            [
                prompt(),
                chunk(json.dumps(worker_report(), ensure_ascii=False)),
                chunk("\n还有一些补充说明。\n"),
                result(),
            ]
        )
        payload = self.inspect("--stream", str(stream), "--expect", "worker", expected_code=1)
        self.assertFalse(payload["report"]["found"])
        self.assertIn("report-missing", payload["problems"])

    def test_invalid_worker_contract_reports_each_problem(self) -> None:
        broken = worker_report(status="done", verification=[{"command": "pytest"}])
        del broken["handoff"]
        stream = self.write_stream(
            [
                prompt(),
                chunk("```json\n" + json.dumps(broken, ensure_ascii=False) + "\n```"),
                result(),
            ]
        )
        payload = self.inspect("--stream", str(stream), "--expect", "worker", expected_code=1)
        self.assertTrue(payload["report"]["found"])
        self.assertFalse(payload["report"]["valid"])
        problems = " | ".join(payload["report"]["problems"])
        self.assertIn("missing fields ['handoff']", problems)
        self.assertIn("status must be one of", problems)
        self.assertIn("verification[0].result", problems)
        self.assertEqual(payload["problems"], ["report-invalid"])

    def test_blocked_worker_report_stays_trusted(self) -> None:
        blocked = worker_report(
            status="blocked", blocker="missing credentials", verification=[]
        )
        stream = self.write_stream(
            [
                prompt(),
                chunk("```json\n" + json.dumps(blocked, ensure_ascii=False) + "\n```"),
                result(),
            ]
        )
        payload = self.inspect("--stream", str(stream), "--expect", "worker")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["report"]["value"]["status"], "blocked")

    def test_refused_turn_reports_permissions_and_runtime_error(self) -> None:
        stream = self.write_stream(
            [
                prompt(request_id=2),
                chunk("我先读取审查材料。"),
                permission_request(),
                permission_response("selected", "d61ad9f0"),
                permission_request(),
                permission_request(),
                permission_response("cancelled", "8472f4ea"),
                permission_response("cancelled", "542c2c16"),
                result(request_id=2, stop_reason="refusal"),
                runtime_error(),
            ]
        )
        payload = self.inspect(
            "--stream", str(stream), "--expect", "validator", expected_code=1
        )
        self.assertEqual(payload["turn"]["stop_reason"], "refusal")
        self.assertEqual(payload["permissions"], {
            "requests": 3,
            "outcomes": {"selected": 1, "cancelled": 2},
        })
        self.assertEqual(payload["errors"][-1]["acpx_code"], "PERMISSION_PROMPT_UNAVAILABLE")
        self.assertEqual(
            payload["failure"]["classification"], "permission_policy_mismatch"
        )
        self.assertIn("permission-policy-mismatch", payload["problems"])
        self.assertIn("stop-reason-not-end-turn", payload["problems"])
        self.assertIn("report-missing", payload["problems"])
        self.assertIn("permission-not-granted", payload["warnings"])

    def test_permission_policy_classification_is_validator_only(self) -> None:
        stream = self.write_stream([prompt(), runtime_error()])
        payload = self.inspect(
            "--stream", str(stream), "--expect", "worker", expected_code=1
        )
        self.assertIsNone(payload["failure"]["classification"])
        self.assertNotIn("permission-policy-mismatch", payload["problems"])

    def test_auto_resolved_permission_events_do_not_block_validator(self) -> None:
        events: list[Any] = [prompt()]
        for index in range(2):
            events.extend(
                [
                    permission_request(),
                    permission_response("selected", f"permission-{index}"),
                ]
            )
        events.extend([chunk("结论：CONTINUE\n"), result()])
        stream = self.write_stream(events)
        payload = self.inspect(
            "--stream", str(stream), "--expect", "validator", "--acpx-exit", "0"
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["permissions"]["requests"], 2)
        self.assertEqual(payload["permissions"]["outcomes"], {"selected": 2})
        self.assertEqual(payload["report"]["value"]["conclusion"], "CONTINUE")

    def test_validator_exit_five_is_classified_even_without_error_event(self) -> None:
        stream = self.write_stream([prompt(), result()])
        payload = self.inspect(
            "--stream",
            str(stream),
            "--expect",
            "validator",
            "--acpx-exit",
            "5",
            expected_code=1,
        )
        self.assertEqual(
            payload["failure"],
            {"classification": "permission_policy_mismatch", "acpx_exit": 5},
        )
        self.assertIn("acpx-exit-nonzero", payload["problems"])
        self.assertIn("permission-policy-mismatch", payload["problems"])

    def test_any_other_nonzero_acpx_exit_blocks_a_clean_stream(self) -> None:
        stream = self.write_stream([prompt(), result()])
        payload = self.inspect(
            "--stream",
            str(stream),
            "--expect",
            "validator",
            "--acpx-exit",
            "1",
            expected_code=1,
        )
        self.assertIn("acpx-exit-nonzero", payload["problems"])
        self.assertIsNone(payload["failure"]["classification"])

    def test_old_permission_error_does_not_poison_a_later_validator_turn(self) -> None:
        second_prompt = prompt(request_id=9)
        stream = self.write_stream(
            [
                prompt(request_id=2),
                runtime_error(),
                second_prompt,
                chunk("结论：CONTINUE\n"),
                result(request_id=9),
            ]
        )
        payload = self.inspect(
            "--stream", str(stream), "--expect", "validator"
        )
        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["failure"]["classification"])
        self.assertNotIn("permission-policy-mismatch", payload["problems"])

    def test_missing_turn_response_falls_back_to_error(self) -> None:
        stream = self.write_stream([prompt(), chunk("partial"), runtime_error()])
        payload = self.inspect("--stream", str(stream), expected_code=1)
        self.assertEqual(payload["turn"]["kind"], "error")
        self.assertEqual(payload["turn"]["error"]["code"], -32072)
        self.assertEqual(payload["problems"], ["turn-error"])
        self.assertIsNone(payload["report"])

    def test_validator_conclusion_ignores_template_echo(self) -> None:
        stream = self.write_stream(
            [
                prompt(),
                chunk("结论：CONTINUE | PATCH_PROMPT | INSERT_STORY | REPLAN\n"),
                chunk("结论：CONTINUE\n\n大局判断：\n- 方向成立\n"),
                result(),
            ]
        )
        payload = self.inspect("--stream", str(stream), "--expect", "validator")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["report"]["value"]["conclusion"], "CONTINUE")
        self.assertEqual(payload["report"]["value"]["line"], 2)

    def test_conflicting_validator_conclusions_are_invalid(self) -> None:
        stream = self.write_stream(
            [
                prompt(),
                chunk("结论：PATCH_PROMPT\n"),
                chunk("Conclusion: REPLAN\n"),
                result(),
            ]
        )
        payload = self.inspect(
            "--stream", str(stream), "--expect", "validator", expected_code=1
        )
        self.assertIn("conflicting conclusions", payload["report"]["problems"][0])
        self.assertEqual(payload["problems"], ["report-invalid"])

    def test_session_mismatch_blocks_trust(self) -> None:
        other = "735e6c65-1f89-4763-9042-f237dd4e83a9"
        stream = self.write_stream(
            [
                prompt(session=other),
                chunk("```json\n" + json.dumps(worker_report(), ensure_ascii=False) + "\n```", session=other),
                result(),
            ]
        )
        payload = self.inspect(
            "--stream", str(stream), "--expect", "worker", "--session", SESSION, expected_code=1
        )
        self.assertEqual(payload["session"]["continuity"], "mismatch")
        self.assertEqual(payload["session"]["observed"], [other])
        self.assertIn("session-mismatch", payload["problems"])

    def test_ndjson_is_parsed_line_by_line_and_bad_lines_are_counted(self) -> None:
        stream = self.write_stream(
            [
                prompt(),
                "{truncated",
                chunk("```json\n" + json.dumps(worker_report(), ensure_ascii=False) + "\n```"),
                result(),
            ]
        )
        with self.assertRaises(json.JSONDecodeError):
            json.loads(stream.read_text(encoding="utf-8"))
        payload = self.inspect("--stream", str(stream), "--expect", "worker")
        self.assertEqual(payload["lines"], {"total": 4, "parsed": 3, "unparsed": 1})
        self.assertIn("unparsed-lines", payload["warnings"])
        self.assertTrue(payload["ok"])

    def test_last_prompt_is_the_inspected_turn(self) -> None:
        stream = self.write_stream(
            [
                prompt(request_id=1),
                result(request_id=1),
                prompt(request_id=5),
                chunk("```json\n" + json.dumps(worker_report(), ensure_ascii=False) + "\n```"),
                result(request_id=5),
            ]
        )
        payload = self.inspect("--stream", str(stream), "--expect", "worker")
        self.assertEqual(payload["prompt"]["request_id"], 5)
        self.assertEqual(payload["prompt"]["total"], 2)
        self.assertIn("multiple-prompts", payload["warnings"])

    def test_message_out_writes_the_full_message(self) -> None:
        stream = self.write_stream([prompt(), chunk("第一段。"), chunk("第二段。"), result()])
        destination = self.root / "message.txt"
        payload = self.inspect(
            "--stream",
            str(stream),
            "--message-tail",
            "0",
            "--message-out",
            str(destination),
        )
        self.assertEqual(destination.read_text(encoding="utf-8"), "第一段。第二段。")
        self.assertIsNone(payload["message"]["tail"])
        self.assertEqual(payload["message"]["chars"], 8)

    def test_help_and_argument_errors(self) -> None:
        completed = self.run_script("--help")
        self.assertEqual(completed.returncode, 0)
        self.assertIn("--expect", completed.stdout)

        self.assertEqual(self.run_script().returncode, 2)
        self.assertEqual(
            self.run_script("--stream", str(self.root / "absent.ndjson")).returncode, 2
        )
        self.assertEqual(self.run_script("--stream", str(self.root)).returncode, 2)

        stream = self.write_stream([prompt(), result()])
        self.assertEqual(
            self.run_script("--stream", str(stream), "--message-tail", "-1").returncode, 2
        )
        self.assertEqual(
            self.run_script("--stream", str(stream), "--expect", "reviewer").returncode, 2
        )


if __name__ == "__main__":
    unittest.main()
