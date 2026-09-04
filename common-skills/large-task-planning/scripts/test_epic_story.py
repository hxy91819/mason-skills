from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from typing import Any


SCRIPT = Path(__file__).with_name("epic_story.py")


def plan_data(*, final_story: str = "STORY-02") -> dict[str, Any]:
    return {
        "kind": "large-task-plan",
        "schema_version": 2,
        "id": "EPIC-DEMO",
        "title": "可恢复的演示任务",
        "goal_version": 1,
        "updated": "2026-09-04",
        "language": "zh-Hans",
        "spec": {
            "problem_statement": "用户现在无法从公开入口得到稳定结果。",
            "solution": "提供一条可复现、可验证的完整路径。",
            "user_stories": [
                {
                    "id": "US-01",
                    "actor": "演示用户",
                    "want": "通过公开入口获得结果",
                    "benefit": "可以确认能力真实可用",
                }
            ],
            "boundaries": ["保持现有公开接口兼容。"],
            "decisions": [
                {
                    "id": "D-01",
                    "decision": "复用现有公开入口",
                    "rationale": "它是最高且稳定的行为边界。",
                    "impact": "测试不绑定内部实现。",
                    "owner": "agent",
                }
            ],
            "testing": {
                "seams": ["公开命令的退出码与输出。"],
                "strategy": "每个纵向切片先得到失败证据，再做最小实现。",
            },
            "out_of_scope": ["不执行正式发布。"],
        },
        "golden_acceptance": [
            {
                "id": "GC-01",
                "title": "完整路径",
                "fixture": ["固定输入和版本。"],
                "actions": ["用户执行一次公开命令。"],
                "oracle": ["返回已知正确结果。"],
                "evidence": ["保存输出与退出码。"],
            }
        ],
        "final_story": final_story,
    }


def story_data(
    story_id: str,
    *,
    blocked_by: list[str],
    status: str = "todo",
    passed: bool = False,
    handoff: dict[str, Any] | None = None,
) -> dict[str, Any]:
    titles = {
        "STORY-01": "先让公开入口返回可信结果",
        "STORY-02": "复验完整使用路径",
        "STORY-03": "补齐独立结果",
    }
    return {
        "kind": "large-task-story",
        "schema_version": 2,
        "id": story_id,
        "plan": "EPIC-DEMO",
        "title": titles.get(story_id, "交付一个可验证结果"),
        "intent_version": 1,
        "status": status,
        "blocked_by": blocked_by,
        "covers": ["GC-01"],
        "outcome": "用户可以从公开入口观察到计划中的结果。",
        "acceptance": [
            {"id": "AC-01", "criterion": "公开入口返回已知结果。", "passed": passed}
        ],
        "context": {
            "test_seams": ["公开命令。"],
            "code_anchors": ["src/demo.py:main"],
            "authoritative_inputs": ["README.md"],
            "write_scope": ["src/ 与 tests/。"],
            "stop_conditions": ["公开契约需要变化。"],
        },
        "owner": None if status == "todo" else "orchestrator",
        "blocker": None,
        "updated": "2026-09-04",
        "handoff": handoff,
    }


def completed_handoff(summary: str = "可观察结果已经交付。") -> dict[str, Any]:
    return {
        "summary": summary,
        "verification": ["python -m unittest：退出码 0。"],
        "remaining": [],
        "risks": [],
        "next": "读取下一张 Story。",
    }


class EpicStoryCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "plan"
        self.agent = self.root / "agent"
        self.stories = self.agent / "stories"
        self.stories.mkdir(parents=True)
        self.plan = self.agent / "plan.json"
        self.write_json(self.plan, plan_data())
        self.story_1 = self.stories / "STORY-01-first.json"
        self.story_2 = self.stories / "STORY-02-final.json"
        self.write_json(self.story_1, story_data("STORY-01", blocked_by=[]))
        self.write_json(self.story_2, story_data("STORY-02", blocked_by=["STORY-01"]))
        self.run_cli("render", *self.project_args())

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def write_json(path: Path, value: dict[str, Any]) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def run_cli(self, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, expected, result.stderr or result.stdout)
        return result

    def project_args(self) -> tuple[str, ...]:
        return ("--plan", str(self.plan), "--stories-dir", str(self.stories))

    def test_human_documents_answer_human_questions_without_agent_noise(self) -> None:
        self.run_cli("check", *self.project_args())
        spec = (self.root / "SPEC.md").read_text(encoding="utf-8")
        status = (self.root / "STATUS.md").read_text(encoding="utf-8")
        self.assertIn("## 为什么要做", spec)
        self.assertIn("[查看当前进展](STATUS.md)", spec)
        self.assertIn("## 对使用者的承诺", spec)
        self.assertIn("## 已经做出的关键取舍", spec)
        self.assertIn("#### 完整路径", spec)
        self.assertIn("## 我们会怎样走到终点", spec)
        self.assertIn("## 接下来", status)
        self.assertIn("[查看目标与验收](SPEC.md)", status)
        self.assertIn("尚未开始。第一项结果已经明确", status)
        self.assertIn("先让公开入口返回可信结果", status)
        self.assertIn("## 之后的路线", status)
        self.assertIn("## 需要关注", status)
        self.assertNotIn("STORY-01", spec)
        self.assertNotIn("STORY-01", status)
        self.assertNotIn("Agent", spec)
        self.assertNotIn("Agent", status)
        self.assertNotIn("src/demo.py", spec)
        self.assertNotIn("src/demo.py", status)
        self.assertNotIn("owner", status)

    def test_human_status_prefers_verified_result_and_surfaces_residual_risk(self) -> None:
        first = story_data(
            "STORY-01",
            blocked_by=[],
            status="done",
            passed=True,
            handoff={
                **completed_handoff("用户已经能稳定得到公开结果。"),
                "risks": ["首次真实流量到来后仍需观察容量。"],
            },
        )
        self.write_json(self.story_1, first)
        self.run_cli("render", *self.project_args())
        status = (self.root / "STATUS.md").read_text(encoding="utf-8")
        self.assertIn("用户已经能稳定得到公开结果", status)
        self.assertIn("首次真实流量到来后仍需观察容量", status)
        self.assertNotIn("python -m unittest", status)

    def test_status_and_brief_separate_frontier_from_agent_context(self) -> None:
        status = json.loads(self.run_cli("status", *self.project_args(), "--json").stdout)
        self.assertEqual(status["ready"], ["STORY-01"])
        brief = json.loads(
            self.run_cli("brief", *self.project_args(), "--story", "STORY-01").stdout
        )
        self.assertEqual(brief["story"]["context"]["code_anchors"], ["src/demo.py:main"])
        self.assertEqual([item["id"] for item in brief["golden_acceptance"]], ["GC-01"])
        self.assertEqual(brief["plan"]["out_of_scope"], ["不执行正式发布。"])
        self.assertEqual(brief["plan"]["testing"]["seams"], ["公开命令的退出码与输出。"])
        self.assertEqual(brief["dependency_handoffs"], [])

    def test_transition_uses_expected_state_and_refreshes_status(self) -> None:
        self.run_cli(
            "transition",
            "--story",
            str(self.story_1),
            "--expect",
            "todo",
            "--status",
            "in_progress",
            "--owner",
            "worker-1",
            "--at",
            "2026-09-05",
        )
        data = json.loads(self.story_1.read_text(encoding="utf-8"))
        self.assertEqual(data["owner"], "worker-1")
        self.assertIn(
            "先让公开入口返回可信结果",
            (self.root / "STATUS.md").read_text(encoding="utf-8"),
        )
        failed = self.run_cli(
            "transition",
            "--story",
            str(self.story_1),
            "--expect",
            "todo",
            "--status",
            "in_progress",
            expected=1,
        )
        self.assertIn("期望状态 todo，实际为 in_progress", failed.stderr)

    def test_done_requires_acceptance_and_handoff_evidence(self) -> None:
        self.run_cli(
            "transition",
            "--story",
            str(self.story_1),
            "--status",
            "in_progress",
            "--owner",
            "worker-1",
        )
        rejected = self.run_cli(
            "transition", "--story", str(self.story_1), "--status", "done", expected=1
        )
        self.assertIn("acceptance 必须全部 passed=true", rejected.stderr)
        current = json.loads(self.story_1.read_text(encoding="utf-8"))
        current["acceptance"][0]["passed"] = True
        current["handoff"] = completed_handoff()
        self.write_json(self.story_1, current)
        self.run_cli("transition", "--story", str(self.story_1), "--status", "done")

    def test_completion_requires_all_stories_and_fresh_human_projection(self) -> None:
        incomplete = self.run_cli("completion-check", *self.project_args(), expected=1)
        self.assertIn("仍有未完成 Story", incomplete.stderr)
        self.write_json(
            self.story_1,
            story_data(
                "STORY-01",
                blocked_by=[],
                status="done",
                passed=True,
                handoff=completed_handoff(),
            ),
        )
        self.write_json(
            self.story_2,
            story_data(
                "STORY-02",
                blocked_by=["STORY-01"],
                status="done",
                passed=True,
                handoff=completed_handoff("同一提交上重跑 GC-01。"),
            ),
        )
        stale = self.run_cli("completion-check", *self.project_args(), expected=1)
        self.assertIn("人读投影已过期", stale.stderr)
        self.run_cli("render", *self.project_args())
        completed = self.run_cli("completion-check", *self.project_args())
        self.assertIn("golden_cases=1/1", completed.stdout)

    def test_final_story_must_close_all_paths(self) -> None:
        orphan = self.stories / "STORY-03-orphan.json"
        self.write_json(orphan, story_data("STORY-03", blocked_by=[]))
        result = self.run_cli("status", *self.project_args(), expected=1)
        self.assertIn("final_story 必须直接或间接阻塞于全部 Story", result.stderr)

    def test_cycle_is_rejected(self) -> None:
        first = story_data("STORY-01", blocked_by=["STORY-02"])
        self.write_json(self.story_1, first)
        result = self.run_cli("status", *self.project_args(), expected=1)
        self.assertIn("Story blocker 成环", result.stderr)

    def test_write_rejects_schema_sediment(self) -> None:
        invalid = deepcopy(plan_data())
        invalid["extra_rule"] = True
        payload = self.root / "invalid.json"
        self.write_json(payload, invalid)
        result = self.run_cli(
            "write", "--file", str(self.plan), "--from", str(payload), expected=1
        )
        self.assertIn("未知字段: extra_rule", result.stderr)


class MigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.legacy = self.root / "legacy"
        (self.legacy / "epics").mkdir(parents=True)
        (self.legacy / "stories").mkdir()
        (self.legacy / "agent").mkdir()
        self.epic = self.legacy / "epics" / "EPIC-DEMO.md"
        self.epic.write_text(
            """---
kind: epic
id: EPIC-DEMO
title: 旧计划
updated: 2026-09-04
goal_version: 1
language: zh-Hans
---

<!-- large-task-planning:vision -->
## 愿景

用户通过公开入口获得结果。

<!-- large-task-planning:global-design -->
## 全局设计

沿用现有系统。

<!-- large-task-planning:manual-acceptance -->
## 人工验收

执行完整路径。

<!-- large-task-planning:success-criteria -->
## 成功标准

全部通过。

<!-- large-task-planning:story-map -->
## Story 地图

两个 Story。

<!-- large-task-planning:project-boundaries -->
## 项目边界

- 保持公开接口兼容。
""",
            encoding="utf-8",
        )
        for number in (1, 2):
            story_id = f"STORY-{number:02d}"
            dependency = "[]" if number == 1 else "[STORY-01]"
            (self.legacy / "stories" / f"Story-{number:02d}-demo.md").write_text(
                f"""---
kind: story
id: {story_id}
epic: EPIC-DEMO
title: 旧 Story {number}
depends_on: {dependency}
updated: 2026-09-04
intent_version: 1
---

<!-- large-task-planning:vision -->
## 愿景

交付结果 {number}。

<!-- large-task-planning:scope -->
## 范围

修改公开入口；后台管理不在本 Story 内。

<!-- large-task-planning:acceptance-criteria -->
## 验收标准

- 公开入口返回结果 {number}。
""",
                encoding="utf-8",
            )
            card = {
                "kind": "agent-card",
                "story": story_id,
                "status": "todo",
                "owner": "待领取",
                "blocker": "无",
                "acceptance_cases": ["GC-01"],
                "technical_plan": "src/demo.py:main",
                "authoritative_inputs": "README.md",
                "verification": "待执行。",
                "stop_conditions": "公开契约变化。",
                "handoff": "未开始。",
            }
            (self.legacy / "agent" / f"{story_id}-demo.json").write_text(
                json.dumps(card, ensure_ascii=False), encoding="utf-8"
            )
        golden = {
            "kind": "golden-acceptance",
            "cases": [
                {
                    "id": "GC-01",
                    "title": "完整路径",
                    "fixture": ["固定版本。"],
                    "interaction": ["执行公开入口。"],
                    "oracle": ["得到已知结果。"],
                    "evidence": ["保存输出。"],
                }
            ],
        }
        (self.legacy / "agent" / "黄金验收.json").write_text(
            json.dumps(golden, ensure_ascii=False), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_cli(self, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *arguments], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, expected, result.stderr or result.stdout)
        return result

    def test_migration_creates_both_audiences_and_preserves_v1(self) -> None:
        output = self.root / "v2"
        migrated = self.run_cli(
            "migrate-v1",
            "--epic",
            str(self.epic),
            "--stories-dir",
            str(self.legacy / "stories"),
            "--output-dir",
            str(output),
        )
        self.assertIn("review problem_statement", migrated.stdout)
        self.assertTrue(self.epic.exists())
        self.assertTrue((output / "SPEC.md").is_file())
        self.assertTrue((output / "STATUS.md").is_file())
        self.assertTrue((output / "agent" / "plan.json").is_file())
        check = self.run_cli(
            "check",
            "--plan",
            str(output / "agent" / "plan.json"),
            "--stories-dir",
            str(output / "agent" / "stories"),
        )
        self.assertIn("projections=fresh", check.stdout)
        final = json.loads((output / "agent" / "stories" / "STORY-02.json").read_text(encoding="utf-8"))
        self.assertEqual(final["blocked_by"], ["STORY-01"])
        refused = self.run_cli(
            "migrate-v1",
            "--epic",
            str(self.epic),
            "--stories-dir",
            str(self.legacy / "stories"),
            "--output-dir",
            str(output),
            expected=1,
        )
        self.assertIn("输出目录必须为空", refused.stderr)


if __name__ == "__main__":
    unittest.main()
