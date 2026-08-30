from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


SCRIPT = Path(__file__).parents[1] / "scripts" / "orchestration_history.py"
HISTORY = Path(".local/large-task-orchestrator/run-history.json")


class OrchestrationHistoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "History Test")
        self.git("config", "user.email", "history@example.invalid")
        (self.repository / "README.md").write_text("fixture\n", encoding="utf-8")
        plan = self.repository / "docs" / "plan"
        (plan / "agent").mkdir(parents=True)
        (plan / "agent" / "STORY-01.json").write_text("{}\n", encoding="utf-8")
        self.git("add", "README.md", "docs")
        self.git("commit", "-m", "test: initialize history fixture")
        exclude = self.repository / ".git" / "info" / "exclude"
        with exclude.open("a", encoding="utf-8") as handle:
            handle.write(".local/\n")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repository), *arguments],
            capture_output=True,
            text=True,
            check=check,
        )

    def run_cli(
        self, *arguments: str, expected: int = 0
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--repository",
                str(self.repository),
                *arguments,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, expected, result.stderr or result.stdout)
        payload: dict[str, Any] = {}
        if result.stdout.strip():
            parsed = json.loads(result.stdout)
            if not isinstance(parsed, dict):
                self.fail(f"CLI JSON must be an object: {parsed!r}")
            payload = parsed
        return result, payload

    def read_history(self) -> dict[str, Any]:
        parsed = json.loads((self.repository / HISTORY).read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            self.fail(f"history JSON must be an object: {parsed!r}")
        return parsed

    def start(self, run_id: str = "run-1", at: str = "2026-08-30T00:00:00Z") -> None:
        self.run_cli(
            "start",
            "--run-id",
            run_id,
            "--plan-ref",
            "docs/plan",
            "--at",
            at,
        )

    def test_start_and_attempt_retries_are_idempotent(self) -> None:
        self.start()
        _, repeated_start = self.run_cli(
            "start",
            "--run-id",
            "run-1",
            "--plan-ref",
            "docs/plan",
            "--at",
            "2026-08-30T00:00:01Z",
        )
        self.assertTrue(repeated_start["idempotent"])

        attempt = (
            "attempt",
            "start",
            "--run-id",
            "run-1",
            "--attempt-id",
            "STORY-01-worker-1",
            "--story",
            "STORY-01",
            "--role",
            "worker",
            "--agent",
            "codexp",
            "--route",
            "default",
            "--model",
            "gpt-5.6-codex",
            "--effort",
            "high",
            "--plan-ref",
            "docs/plan/agent/STORY-01.json",
            "--at",
            "2026-08-30T00:01:00Z",
        )
        self.run_cli(*attempt)
        _, repeated_attempt = self.run_cli(*attempt)
        self.assertTrue(repeated_attempt["idempotent"])

        finish = (
            "attempt",
            "finish",
            "--run-id",
            "run-1",
            "--attempt-id",
            "STORY-01-worker-1",
            "--outcome",
            "worker-done",
            "--at",
            "2026-08-30T00:02:30Z",
        )
        _, first_finish = self.run_cli(*finish)
        _, repeated_finish = self.run_cli(*finish)
        self.assertEqual(first_finish["duration_seconds"], 90)
        self.assertTrue(repeated_finish["idempotent"])

        run = self.read_history()["runs"][0]
        self.assertEqual(run["metrics"]["attempts"], 1)
        self.assertEqual(run["metrics"]["attempt_seconds"], 90)
        self.assertEqual(run["metrics"]["by_agent"], {"codexp": 1})
        self.assertEqual(run["active_attempts"], [])

    def test_rollover_preserves_active_attempt_and_aggregate(self) -> None:
        self.start()
        self.run_cli(
            "attempt",
            "start",
            "--run-id",
            "run-1",
            "--attempt-id",
            "STORY-01-worker-1",
            "--story",
            "STORY-01",
            "--role",
            "worker",
            "--agent",
            "codexp",
            "--route",
            "default",
            "--at",
            "2026-08-30T00:01:00Z",
        )
        for index in range(35):
            self.run_cli(
                "event",
                "--run-id",
                "run-1",
                "--event-key",
                f"blocked-{index}",
                "--type",
                "blocked",
                "--story",
                "STORY-01",
                "--reason",
                "environment",
                "--plan-ref",
                "docs/plan/agent/STORY-01.json",
                "--at",
                f"2026-08-30T00:{index + 2:02d}:00Z",
            )
        self.run_cli(
            "attempt",
            "finish",
            "--run-id",
            "run-1",
            "--attempt-id",
            "STORY-01-worker-1",
            "--outcome",
            "failed",
            "--reason",
            "environment",
            "--at",
            "2026-08-30T01:00:00Z",
        )

        run = self.read_history()["runs"][0]
        self.assertEqual(len(run["recent_events"]), 30)
        self.assertGreater(run["compacted_events"], 0)
        self.assertEqual(run["metrics"]["blocked_events"], 35)
        self.assertEqual(run["metrics"]["attempts"], 1)
        self.assertEqual(run["active_attempts"], [])

    def test_thirteenth_terminal_run_rolls_into_fixed_lifetime_counts(self) -> None:
        for index in range(13):
            run_id = f"run-{index:02d}"
            self.start(run_id, f"2026-08-{index + 1:02d}T00:00:00Z")
            self.run_cli(
                "finish",
                "--run-id",
                run_id,
                "--outcome",
                "abandoned",
                "--reason",
                "user-decision",
                "--at",
                f"2026-08-{index + 1:02d}T00:01:00Z",
            )

        history = self.read_history()
        self.assertEqual(len(history["runs"]), 12)
        self.assertEqual(history["rollup"]["terminal_runs"], 1)
        self.assertEqual(history["rollup"]["run_outcomes"], {"abandoned": 1})
        self.assertNotIn("run-00", [run["run_id"] for run in history["runs"]])
        _, check = self.run_cli("check")
        self.assertEqual(check["retained_runs"], 12)
        self.assertEqual(check["rolled_up_runs"], 1)

    def test_concurrent_writers_do_not_lose_events(self) -> None:
        self.start()
        processes: list[subprocess.Popen[str]] = []
        for index in range(20):
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--repository",
                        str(self.repository),
                        "event",
                        "--run-id",
                        "run-1",
                        "--event-key",
                        f"concurrent-{index}",
                        "--type",
                        "blocked",
                        "--reason",
                        "environment",
                        "--plan-ref",
                        "docs/plan",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        results = [process.communicate(timeout=20) for process in processes]
        self.assertTrue(
            all(process.returncode == 0 for process in processes),
            "\n".join(stderr for _, stderr in results if stderr),
        )
        run = self.read_history()["runs"][0]
        self.assertEqual(run["metrics"]["blocked_events"], 20)
        self.assertEqual(len(run["seen_event_keys"]), 20)

    def test_different_run_is_rejected_until_active_run_is_abandoned(self) -> None:
        self.start()
        result, _ = self.run_cli(
            "start",
            "--run-id",
            "run-2",
            "--plan-ref",
            "docs/plan",
            expected=1,
        )
        self.assertIn("已有 active run", result.stderr)
        self.run_cli(
            "finish",
            "--run-id",
            "run-1",
            "--outcome",
            "abandoned",
            "--reason",
            "user-decision",
        )
        self.start("run-2", "2026-08-30T02:00:00Z")

    def test_abandon_closes_active_attempt_but_delivery_rejects_it(self) -> None:
        self.start()
        self.run_cli(
            "attempt",
            "start",
            "--run-id",
            "run-1",
            "--attempt-id",
            "STORY-01-worker-1",
            "--story",
            "STORY-01",
            "--role",
            "worker",
            "--agent",
            "codexp",
            "--route",
            "default",
            "--at",
            "2026-08-30T00:01:00Z",
        )
        result, _ = self.run_cli(
            "finish",
            "--run-id",
            "run-1",
            "--outcome",
            "delivered",
            "--at",
            "2026-08-30T00:02:00Z",
            expected=1,
        )
        self.assertIn("active attempts", result.stderr)
        self.run_cli(
            "finish",
            "--run-id",
            "run-1",
            "--outcome",
            "abandoned",
            "--reason",
            "user-decision",
            "--at",
            "2026-08-30T00:03:00Z",
        )
        run = self.read_history()["runs"][0]
        self.assertEqual(run["active_attempts"], [])
        self.assertEqual(run["metrics"]["by_reason"], {"abandoned": 1})

    def test_delivered_requires_real_remote_head_equality(self) -> None:
        remote = self.root / "origin.git"
        subprocess.run(
            ["git", "init", "--bare", str(remote)],
            capture_output=True,
            text=True,
            check=True,
        )
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "-u", "origin", "main")
        self.start()

        (self.repository / "delivery.txt").write_text("delivered\n", encoding="utf-8")
        self.git("add", "delivery.txt")
        self.git("commit", "-m", "feat: local delivery")
        result, _ = self.run_cli(
            "finish",
            "--run-id",
            "run-1",
            "--outcome",
            "delivered",
            expected=1,
        )
        self.assertIn("尚未到达真实远端", result.stderr)

        self.git("push")
        _, finished = self.run_cli(
            "finish", "--run-id", "run-1", "--outcome", "delivered"
        )
        self.assertTrue(finished["delivery"]["pushed"])
        self.assertEqual(
            finished["delivery"]["head"], finished["delivery"]["remote_head"]
        )

    def test_show_exposes_deterministic_review_focus(self) -> None:
        self.start()
        self.run_cli(
            "attempt",
            "start",
            "--run-id",
            "run-1",
            "--attempt-id",
            "STORY-01-worker-1",
            "--story",
            "STORY-01",
            "--role",
            "worker",
            "--agent",
            "codexp",
            "--route",
            "default",
        )
        self.run_cli(
            "attempt",
            "finish",
            "--run-id",
            "run-1",
            "--attempt-id",
            "STORY-01-worker-1",
            "--outcome",
            "quota-exhausted",
            "--reason",
            "quota",
        )
        self.run_cli(
            "event",
            "--run-id",
            "run-1",
            "--event-key",
            "plan-insert-1",
            "--type",
            "plan-change",
            "--change",
            "insert",
            "--reason",
            "plan-gap",
            "--plan-ref",
            "docs/plan",
        )
        _, shown = self.run_cli("show")
        codes = {item["code"] for item in shown["review_focus"]}
        self.assertIn("insufficient-data", codes)
        self.assertIn("route-reliability", codes)
        self.assertIn("plan-volatility", codes)
        self.assertEqual(shown["recovery_order"], ["plan", "history", "notebook"])

    def test_reserved_capacity_still_allows_abandon_to_close_attempts(self) -> None:
        self.start()
        for role, suffix in (("worker", "worker-1"), ("validator", "validator-1")):
            self.run_cli(
                "attempt",
                "start",
                "--run-id",
                "run-1",
                "--attempt-id",
                f"STORY-01-{suffix}",
                "--story",
                "STORY-01",
                "--role",
                role,
                "--agent",
                "codexp",
                "--route",
                "default",
            )
        path = self.repository / HISTORY
        history = self.read_history()
        seen = history["runs"][0]["seen_event_keys"]
        for index in range(236):
            seen[f"synthetic-{index}"] = "0" * 64
        path.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        result, _ = self.run_cli(
            "event",
            "--run-id",
            "run-1",
            "--event-key",
            "one-too-many",
            "--type",
            "blocked",
            "--reason",
            "environment",
            "--plan-ref",
            "docs/plan",
            expected=1,
        )
        self.assertIn("收尾容量", result.stderr)
        self.run_cli(
            "finish",
            "--run-id",
            "run-1",
            "--outcome",
            "abandoned",
            "--reason",
            "user-decision",
        )
        run = self.read_history()["runs"][0]
        self.assertEqual(run["outcome"], "abandoned")
        self.assertEqual(run["active_attempts"], [])
        self.assertEqual(len(run["seen_event_keys"]), 240)
        self.assertEqual(run["metrics"]["by_reason"], {"abandoned": 2})

    def test_structural_damage_fails_check_without_traceback_or_overwrite(self) -> None:
        self.start()
        self.run_cli(
            "attempt",
            "start",
            "--run-id",
            "run-1",
            "--attempt-id",
            "STORY-01-worker-1",
            "--story",
            "STORY-01",
            "--role",
            "worker",
            "--agent",
            "codexp",
            "--route",
            "default",
        )
        path = self.repository / HISTORY
        history = self.read_history()
        attempt = history["runs"][0]["active_attempts"][0]
        history["runs"][0]["active_attempts"][0] = {
            "attempt_id": attempt["attempt_id"],
            "started_at": attempt["started_at"],
        }
        damaged = json.dumps(history, ensure_ascii=False, indent=2) + "\n"
        path.write_text(damaged, encoding="utf-8")

        checked, _ = self.run_cli("check", expected=1)
        self.assertIn("active_attempts[0] 字段漂移", checked.stderr)
        self.assertNotIn("Traceback", checked.stderr)
        finished, _ = self.run_cli(
            "attempt",
            "finish",
            "--run-id",
            "run-1",
            "--attempt-id",
            "STORY-01-worker-1",
            "--outcome",
            "worker-done",
            expected=1,
        )
        self.assertNotIn("Traceback", finished.stderr)
        self.assertEqual(path.read_text(encoding="utf-8"), damaged)

    def test_boolean_counts_and_numeric_tokens_are_rejected(self) -> None:
        self.start()
        self.run_cli(
            "attempt",
            "start",
            "--run-id",
            "run-1",
            "--attempt-id",
            "STORY-01-worker-1",
            "--story",
            "STORY-01",
            "--role",
            "worker",
            "--agent",
            "codexp",
            "--route",
            "default",
        )
        path = self.repository / HISTORY
        valid = self.read_history()

        boolean_damage = json.loads(json.dumps(valid))
        boolean_damage["runs"][0]["metrics"]["events"] = True
        boolean_text = json.dumps(boolean_damage, ensure_ascii=False, indent=2) + "\n"
        path.write_text(boolean_text, encoding="utf-8")
        checked, _ = self.run_cli("check", expected=1)
        self.assertIn("必须是非负整数", checked.stderr)
        mutated, _ = self.run_cli(
            "finish",
            "--run-id",
            "run-1",
            "--outcome",
            "abandoned",
            "--reason",
            "user-decision",
            expected=1,
        )
        self.assertNotIn("Traceback", mutated.stderr)
        self.assertEqual(path.read_text(encoding="utf-8"), boolean_text)

        numeric_damage = json.loads(json.dumps(valid))
        numeric_damage["runs"][0]["active_attempts"][0]["attempt_id"] = 7
        numeric_damage["runs"][0]["recent_events"][0]["attempt_id"] = 7
        numeric_text = json.dumps(numeric_damage, ensure_ascii=False, indent=2) + "\n"
        path.write_text(numeric_text, encoding="utf-8")
        checked, _ = self.run_cli("check", expected=1)
        self.assertIn("attempt_id 必须是字符串", checked.stderr)
        self.assertEqual(path.read_text(encoding="utf-8"), numeric_text)

        retention_damage = json.loads(json.dumps(valid))
        retention_damage["retention"] = {
            "terminal_runs": 12.0,
            "recent_events_per_run": 30.0,
        }
        retention_text = json.dumps(retention_damage, ensure_ascii=False, indent=2) + "\n"
        path.write_text(retention_text, encoding="utf-8")
        checked, _ = self.run_cli("check", expected=1)
        self.assertIn("retention.terminal_runs", checked.stderr)
        mutated, _ = self.run_cli(
            "event",
            "--run-id",
            "run-1",
            "--event-key",
            "must-not-write",
            "--type",
            "blocked",
            "--reason",
            "environment",
            "--plan-ref",
            "docs/plan",
            expected=1,
        )
        self.assertNotIn("Traceback", mutated.stderr)
        self.assertEqual(path.read_text(encoding="utf-8"), retention_text)

    def test_corrupt_history_is_preserved(self) -> None:
        self.start()
        path = self.repository / HISTORY
        path.write_text("{broken\n", encoding="utf-8")
        result, _ = self.run_cli("check", expected=1)
        self.assertIn("已保留原文件", result.stderr)
        self.assertEqual(path.read_text(encoding="utf-8"), "{broken\n")

    def test_start_refuses_unignored_history_path(self) -> None:
        exclude = self.repository / ".git" / "info" / "exclude"
        exclude.write_text("\n", encoding="utf-8")
        result, _ = self.run_cli(
            "start",
            "--run-id",
            "run-1",
            "--plan-ref",
            "docs/plan",
            expected=1,
        )
        self.assertIn("尚未被 Git ignore", result.stderr)
        self.assertFalse((self.repository / HISTORY).exists())


if __name__ == "__main__":
    unittest.main()
