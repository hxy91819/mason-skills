from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock


SKILL_DIR = Path(__file__).parents[1]
SCRIPT = SKILL_DIR / "scripts" / "orchestration_history.py"
PLANNING_SCRIPT = SKILL_DIR.parent / "large-task-planning" / "scripts" / "epic_story.py"
HISTORY = Path(".local/large-task-orchestrator/run-history.json")
STORY_REF = "docs/plan/agent/stories/STORY-01-创建并验证问候文件.json"
MODULE_SPEC = importlib.util.spec_from_file_location("orchestration_history", SCRIPT)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
HISTORY_MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(HISTORY_MODULE)


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
        stories = plan / "agent" / "stories"
        stories.mkdir(parents=True)
        plan_data = {
            "kind": "large-task-plan",
            "schema_version": 2,
            "id": "EPIC-FORWARD",
            "title": "创建并验证问候文件",
            "goal_version": 1,
            "updated": "2026-08-30",
            "language": "zh-Hans",
            "spec": {
                "problem_statement": "仓库还不能提供可验证的问候结果。",
                "solution": "用户运行公开检查命令即可确认问候文件正确。",
                "user_stories": [
                    {
                        "id": "US-01",
                        "actor": "使用者",
                        "want": "运行公开命令验证问候文件",
                        "benefit": "确认交付结果真实可用",
                    }
                ],
                "boundaries": ["只修改任务范围内文件。"],
                "decisions": [],
                "testing": {
                    "seams": ["公开检查命令的输出和退出码。"],
                    "strategy": "通过已知输出独立判断结果。",
                },
                "out_of_scope": ["不发布额外产物。"],
            },
            "golden_acceptance": [
                {
                    "id": "GC-01",
                    "title": "问候输出",
                    "fixture": ["固定仓库版本。"],
                    "actions": ["运行公开检查命令。"],
                    "oracle": ["输出预期问候。"],
                    "evidence": ["保存命令和退出码。"],
                }
            ],
            "final_story": "STORY-01",
        }
        story_data = {
            "kind": "large-task-story",
            "schema_version": 2,
            "id": "STORY-01",
            "plan": "EPIC-FORWARD",
            "title": "创建并验证问候文件",
            "intent_version": 1,
            "status": "todo",
            "blocked_by": [],
            "covers": ["GC-01"],
            "outcome": "公开检查命令可以验证问候文件。",
            "acceptance": [
                {
                    "id": "AC-01",
                    "criterion": "问候文件通过公开检查命令。",
                    "passed": False,
                }
            ],
            "context": {
                "test_seams": ["公开检查命令。"],
                "code_anchors": ["README.md"],
                "authoritative_inputs": [],
                "write_scope": ["问候文件。"],
                "stop_conditions": ["公开行为需要改变。"],
            },
            "owner": None,
            "blocker": None,
            "updated": "2026-08-30",
            "handoff": None,
        }
        (plan / "agent" / "plan.json").write_text(
            json.dumps(plan_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (self.repository / STORY_REF).write_text(
            json.dumps(story_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        subprocess.run(
            [
                sys.executable,
                str(PLANNING_SCRIPT),
                "render",
                "--plan",
                str(plan / "agent" / "plan.json"),
                "--stories-dir",
                str(stories),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
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

    def delivery_args(self) -> tuple[str, ...]:
        return (
            "--plan",
            "docs/plan/agent/plan.json",
            "--stories-dir",
            "docs/plan/agent/stories",
        )

    def complete_plan(self) -> None:
        story = self.repository / STORY_REF
        content = json.loads(story.read_text(encoding="utf-8"))
        content["status"] = "done"
        content["owner"] = "orchestrator"
        content["acceptance"][0]["passed"] = True
        content["handoff"] = {
            "summary": "公开检查命令已经验证问候文件。",
            "verification": ["公开检查命令退出码 0。"],
            "remaining": [],
            "risks": [],
            "next": "计划已完成。",
        }
        story.write_text(
            json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        subprocess.run(
            [
                sys.executable,
                str(PLANNING_SCRIPT),
                "render",
                "--plan",
                str(self.repository / "docs/plan/agent/plan.json"),
                "--stories-dir",
                str(self.repository / "docs/plan/agent/stories"),
            ],
            capture_output=True,
            text=True,
            check=True,
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
            "pi",
            "--route",
            "default",
            "--model",
            "gpt-5.6-codex",
            "--effort",
            "high",
            "--plan-ref",
            STORY_REF,
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
        self.assertEqual(run["metrics"]["by_agent"], {"pi": 1})
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
            "pi",
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
                STORY_REF,
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
            "pi",
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

    def test_delivered_requires_complete_tracked_plan_and_real_remote_head(self) -> None:
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

        incomplete, _ = self.run_cli(
            "finish",
            "--run-id",
            "run-1",
            "--outcome",
            "delivered",
            *self.delivery_args(),
            expected=1,
        )
        self.assertIn("仍有未完成 Story: STORY-01", incomplete.stderr)

        (self.repository / "delivery.txt").write_text("delivered\n", encoding="utf-8")
        self.complete_plan()
        self.git("add", "delivery.txt", "docs/plan")
        self.git("commit", "-m", "feat: local delivery")
        unpushed, _ = self.run_cli(
            "finish",
            "--run-id",
            "run-1",
            "--outcome",
            "delivered",
            *self.delivery_args(),
            expected=1,
        )
        self.assertIn("尚未到达真实远端", unpushed.stderr)

        self.git("push")
        _, finished = self.run_cli(
            "finish",
            "--run-id",
            "run-1",
            "--outcome",
            "delivered",
            *self.delivery_args(),
        )
        self.assertTrue(finished["delivery"]["pushed"])
        self.assertEqual(
            finished["delivery"]["head"], finished["delivery"]["remote_head"]
        )

    def test_delivered_rejects_uncommitted_or_untracked_plan_state(self) -> None:
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
        self.complete_plan()

        dirty, _ = self.run_cli(
            "finish",
            "--run-id",
            "run-1",
            "--outcome",
            "delivered",
            *self.delivery_args(),
            expected=1,
        )
        self.assertIn("计划目录仍有未提交变更", dirty.stderr)

        self.git("add", "docs/plan")
        self.git("commit", "-m", "docs: complete plan")
        self.git("push")
        evidence = self.repository / "docs" / "plan" / "evidence"
        evidence.mkdir()
        (evidence / "untracked.txt").write_text("local evidence\n", encoding="utf-8")
        untracked, _ = self.run_cli(
            "finish",
            "--run-id",
            "run-1",
            "--outcome",
            "delivered",
            *self.delivery_args(),
            expected=1,
        )
        self.assertIn("计划目录仍有未提交变更", untracked.stderr)

    def test_delivered_rejects_tracked_plan_input_symlinks(self) -> None:
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
        self.complete_plan()

        story = self.repository / STORY_REF
        outside = self.root / "outside-story.json"
        outside.write_bytes(story.read_bytes())
        story.unlink()
        story.symlink_to(outside)
        self.git("add", "docs/plan")
        self.git("commit", "-m", "test: link Story outside repository")
        self.git("push")
        external_link, _ = self.run_cli(
            "finish",
            "--run-id",
            "run-1",
            "--outcome",
            "delivered",
            *self.delivery_args(),
            expected=1,
        )
        self.assertIn("普通非 symlink 文件", external_link.stderr)

        shared = self.repository / "shared-story.json"
        shared.write_bytes(outside.read_bytes())
        story.unlink()
        story.symlink_to(shared)
        self.git("add", "docs/plan", "shared-story.json")
        self.git("commit", "-m", "test: link Story inside repository")
        self.git("push")
        internal_link, _ = self.run_cli(
            "finish",
            "--run-id",
            "run-1",
            "--outcome",
            "delivered",
            *self.delivery_args(),
            expected=1,
        )
        self.assertIn("普通非 symlink 文件", internal_link.stderr)

    def test_delivery_detects_head_drift_during_remote_lookup(self) -> None:
        original_head = "a" * 40
        moved_head = "b" * 40
        original = {
            "head": original_head,
            "branch": "main",
            "upstream": {"remote": "origin", "ref": "refs/heads/main"},
        }
        moved = {**original, "head": moved_head}
        remote = subprocess.CompletedProcess(
            args=["git", "ls-remote"],
            returncode=0,
            stdout=f"{original_head}\trefs/heads/main\n",
            stderr="",
        )
        with (
            mock.patch.object(
                HISTORY_MODULE,
                "_git_local_facts",
                side_effect=[original, moved],
            ),
            mock.patch.object(HISTORY_MODULE, "_run_git", return_value=remote),
            self.assertRaisesRegex(
                HISTORY_MODULE.HistoryError,
                "查询远端交付事实期间",
            ),
        ):
            HISTORY_MODULE._git_delivery_facts(
                self.repository,
                original,
                original_head,
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
            "pi",
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
        self.assertEqual(shown["recovery_order"], ["agent-json", "git", "history"])

    def test_reserved_capacity_still_allows_abandon_to_close_attempts(self) -> None:
        self.start()
        for role, suffix in (("worker", "worker-1"), ("reviewer", "reviewer-1")):
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
                "pi",
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
            "pi",
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
            "pi",
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
