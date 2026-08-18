import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("epic_story.py")
EPIC_MERMAID_BLOCK = """```mermaid
%%{init: {"securityLevel": "strict", "htmlLabels": false}}%%
flowchart LR
    A["输入"] --> B["交付"]
```"""


def card_payload(story_id: str = "STORY-01", coverage: str = "TEST", slug: str = "测试") -> dict[str, object]:
    return {
        "kind": "agent-card",
        "schema_version": 1,
        "story": story_id,
        "intent_version": 1,
        "status": "todo",
        "owner": "待领取",
        "blocker": "无",
        "status_updated": "2026-08-17",
        "refreshed": "待领取",
        "code_baseline": "待领取",
        "owns": [coverage],
        "verifies": [],
        "goal": "产出可验证结果。",
        "decision_boundary": "愿景和验收由人维护。",
        "technical_plan": "固定输入后验证。",
        "authoritative_inputs": "读取当前 Story。",
        "claim_checks": "开始前刷新代码入口和基线。",
        "checklist": [
            {"done": True, "text": "已完成项"},
            {"done": False, "text": "待完成项"},
            {"done": False, "text": "后续项"},
        ],
        "steps": "1. 运行检查，退出码为零时完成。",
        "verification": "保存退出码。",
        "stop_conditions": "输入漂移时停止。",
        "handoff": "提交结果与版本。",
    }


def risk_payload(epic_id: str = "EPIC-TEST") -> dict[str, object]:
    return {
        "kind": "risk-register",
        "schema_version": 1,
        "epic": epic_id,
        "updated": "2026-08-17",
        "pending_decisions": [],
        "watch_items": ["上游变化时重新验证。"],
    }


class EpicStoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.epics = self.root / "epics"
        self.epics.mkdir()
        self.stories = self.root / "stories"
        self.stories.mkdir()
        self.agent = self.root / "agent"
        self.agent.mkdir()
        self.epic = self.epics / "EPIC-TEST.md"
        self.overview = self.root / "README.md"
        self.dashboard = self.root / "项目进展.md"
        self.risks = self.agent / "风险与阻塞.json"
        self.overview.write_text(
            "# 项目\n\n## 项目一览\n看进展。\n\n## Epic\n- Epic。\n\n## Agent 入口\n- Agent。\n",
            encoding="utf-8",
        )
        self.epic.write_text(
            """---
kind: epic
id: EPIC-TEST
title: 测试 Epic
updated: 2026-08-17
coverage: [TEST]
---
# Epic
## 愿景
愿景。
## 全局设计
统一设计。
{EPIC_MERMAID_BLOCK}
## 成功标准
- 交付。
## Story 地图
- [Story](../stories/Story-01-测试.md)
""".format(EPIC_MERMAID_BLOCK=EPIC_MERMAID_BLOCK),
            encoding="utf-8",
        )
        self.story = self.stories / "Story-01-测试.md"
        self.story.write_text(
            """---
kind: story
id: STORY-01
epic: EPIC-TEST
title: 完成测试
gate: G1
depends_on: []
updated: 2026-08-17
intent_version: 1
---
# Story
## 愿景
可验证。
## 范围
完成本次可观察结果。
## 关键决策
1. **固定输入。**
   - 决定者：用户。
   - Agent 建议：采用固定输入，用户采纳。
   - 结果与影响：输出可复现。
## 验收标准
- 二元通过。
""",
            encoding="utf-8",
        )
        self.card = self.agent / "STORY-01-测试.json"
        self.write_json(self.card, card_payload())
        self.write_json(self.risks, risk_payload())
        self.dashboard.write_text("旧内容\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_json(self, path: Path, payload: object) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def read_json(self, path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))

    def run_cli(self, *arguments: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *(str(argument) for argument in arguments)],
            text=True,
            capture_output=True,
            check=False,
        )

    def common_args(self) -> tuple[str, ...]:
        return ("--epic", str(self.epic), "--stories-dir", str(self.stories))

    def add_story(self, story_id: str, slug: str, dependency: str, coverage: str) -> Path:
        suffix = story_id.removeprefix("STORY-")
        story_name = f"Story-{suffix}-{slug}.md"
        story_path = self.stories / story_name
        story_path.write_text(
            self.story.read_text(encoding="utf-8")
            .replace("STORY-01", story_id)
            .replace("Story-01-测试", f"Story-{suffix}-{slug}")
            .replace("title: 完成测试", f"title: {slug}")
            .replace("depends_on: []", f"depends_on: [{dependency}]")
            .replace("# Story", f"# {story_id}"),
            encoding="utf-8",
        )
        self.write_json(self.agent / f"{story_id}-{slug}.json", card_payload(story_id, coverage, slug))
        epic_text = self.epic.read_text(encoding="utf-8").replace(
            "coverage: [", f"coverage: [{coverage}, ", 1
        )
        self.epic.write_text(
            epic_text.rstrip() + f"\n- [{story_id}](../stories/{story_name})\n", encoding="utf-8"
        )
        return story_path

    def mark_done(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        story_id = next(line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("id: "))
        for card in self.agent.glob(f"{story_id}-*.json"):
            data = self.read_json(card)
            data["status"] = "done"
            data["owner"] = "Agent"
            data["blocker"] = "无"
            data["refreshed"] = "2026-08-18"
            data["code_baseline"] = "testhash"
            data["checklist"] = [
                {"done": True, "text": item["text"]} for item in data["checklist"]
            ]
            self.write_json(card, data)

    def test_render_check_and_status_report_observable_project_state(self) -> None:
        rendered = self.run_cli("render", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(0, rendered.returncode, rendered.stderr)
        output = self.dashboard.read_text(encoding="utf-8")
        self.assertIn("状态 | 进度 | 当前结果或下一步", output)
        self.assertIn("1/3", output)
        self.assertIn("可领取：STORY-01", output)
        self.assertIn("后续关注", output)
        self.assertNotIn("门禁状态", output)
        self.assertNotIn("关键基线", output)
        self.assertIn("本文由脚本根据 Agent JSON 状态源生成", output)

        checked = self.run_cli("check", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(0, checked.returncode, checked.stderr)

        overview_checked = self.run_cli("check", *self.common_args(), "--overview", self.overview)
        self.assertEqual(0, overview_checked.returncode, overview_checked.stderr)

        status = self.run_cli("status", *self.common_args(), "--json")
        self.assertEqual(0, status.returncode, status.stderr)
        payload = json.loads(status.stdout)
        self.assertEqual(["STORY-01"], payload["epic"]["ready_stories"])
        self.assertEqual(["TEST"], payload["epic"]["coverage"])
        self.assertEqual(3000, payload["epic"]["content_limit"])
        self.assertLess(payload["epic"]["content_chars"], payload["epic"]["content_limit"])
        self.assertEqual(2200, payload["stories"][0]["content_limit"])
        self.assertEqual(1, payload["stories"][0]["checklist_done"])
        self.assertEqual(3, payload["stories"][0]["checklist_total"])
        self.assertEqual("待完成项", payload["stories"][0]["next_item"])
        self.assertEqual(str(self.card), payload["stories"][0]["card"])

    def test_done_dashboard_shows_the_last_completed_result(self) -> None:
        data = self.read_json(self.card)
        data["status"] = "done"
        data["owner"] = "Agent"
        data["refreshed"] = "2026-08-17"
        data["code_baseline"] = "abc123"
        data["checklist"] = [{"done": True, "text": item["text"]} for item in data["checklist"]]
        self.write_json(self.card, data)
        result = self.run_cli("render", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("| 已完成 | 3/3 | 后续项 |", self.dashboard.read_text(encoding="utf-8"))

    def test_done_requires_all_todos_checked(self) -> None:
        data = self.read_json(self.card)
        data["status"] = "done"
        data["owner"] = "Agent"
        data["refreshed"] = "2026-08-17"
        data["code_baseline"] = "abc123"
        self.write_json(self.card, data)
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("所有执行清单项必须勾选", result.stderr)

    def test_missing_dependency_fails(self) -> None:
        text = self.story.read_text(encoding="utf-8").replace("depends_on: []", "depends_on: [STORY-99]")
        self.story.write_text(text, encoding="utf-8")
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("不存在的 STORY-99", result.stderr)

    def test_forward_dependency_fails(self) -> None:
        second = self.stories / "Story-02-后续.md"
        second.write_text(
            self.story.read_text(encoding="utf-8")
            .replace("id: STORY-01", "id: STORY-02")
            .replace("Story-01-测试", "Story-02-后续")
            .replace("# Story", "# 后续 Story"),
            encoding="utf-8",
        )
        self.write_json(self.agent / "STORY-02-后续.json", card_payload("STORY-02", "NEXT", "后续"))
        self.epic.write_text(
            self.epic.read_text(encoding="utf-8").replace(
                "- [Story](../stories/Story-01-测试.md)",
                "- [Story](../stories/Story-01-测试.md)\n- [后续](../stories/Story-02-后续.md)",
            ),
            encoding="utf-8",
        )
        self.story.write_text(
            self.story.read_text(encoding="utf-8").replace("depends_on: []", "depends_on: [STORY-02]"),
            encoding="utf-8",
        )
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("不得前向依赖 STORY-02", result.stderr)

    def test_project_defined_gate_id_is_supported(self) -> None:
        self.story.write_text(
            self.story.read_text(encoding="utf-8").replace("gate: G1", "gate: RELEASE"),
            encoding="utf-8",
        )

        result = self.run_cli("check", *self.common_args())
        self.assertEqual(0, result.returncode, result.stderr)

    def test_inserted_story_ids_sort_by_numeric_segment(self) -> None:
        self.add_story("STORY-01.2", "插入二", "STORY-01", "INSERT_2")
        self.add_story("STORY-01.10", "插入十", "STORY-01.2", "INSERT_10")
        self.add_story("STORY-02", "后续", "STORY-01.10", "NEXT")

        result = self.run_cli("status", *self.common_args(), "--json")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(
            ["STORY-01", "STORY-01.2", "STORY-01.10", "STORY-02"],
            [story["id"] for story in payload["stories"]],
        )

    def test_inserted_story_cannot_depend_on_later_insert(self) -> None:
        self.add_story("STORY-01.2", "插入二", "STORY-01.10", "INSERT_2")
        self.add_story("STORY-01.10", "插入十", "STORY-01", "INSERT_10")

        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("不得前向依赖 STORY-01.10", result.stderr)

    def test_inserted_story_requires_existing_base_story(self) -> None:
        self.add_story("STORY-02.1", "孤立插入", "STORY-01", "INSERT")

        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("插入 Story 缺少主编号 STORY-02", result.stderr)

    def test_inserted_story_suffix_must_be_positive_without_leading_zero(self) -> None:
        invalid = "STORY-01.0"
        renamed_story = self.stories / "Story-01.0-测试.md"
        self.story.rename(renamed_story)
        renamed_story.write_text(
            renamed_story.read_text(encoding="utf-8")
            .replace("STORY-01", invalid)
            .replace("Story-01-测试", "Story-01.0-测试"),
            encoding="utf-8",
        )
        renamed_card = self.agent / "STORY-01.0-测试.json"
        self.card.rename(renamed_card)
        data = self.read_json(renamed_card)
        data["story"] = invalid
        self.write_json(renamed_card, data)
        self.epic.write_text(
            self.epic.read_text(encoding="utf-8").replace("Story-01-测试", "Story-01.0-测试"),
            encoding="utf-8",
        )

        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("Story id 必须匹配 STORY-NN 或 STORY-NN.M", result.stderr)

    def test_checklist_count_outside_agent_card_contract_fails(self) -> None:
        data = self.read_json(self.card)
        data["checklist"] = data["checklist"][:2]
        self.write_json(self.card, data)
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("执行清单必须包含 3～7 个复选项", result.stderr)

    def test_human_story_rejects_todo_heading(self) -> None:
        text = self.story.read_text(encoding="utf-8").replace(
            "## 验收标准",
            "## TODO\n- [x] 历史项。\n\n## 验收标准",
        )
        self.story.write_text(text, encoding="utf-8")
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("不允许的二级标题: TODO", result.stderr)

    def test_human_story_rejects_delivery_evidence(self) -> None:
        self.story.write_text(
            self.story.read_text(encoding="utf-8")
            + "\n## 交付证据\n\n- Agent 记录的测试结果。\n",
            encoding="utf-8",
        )
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("不允许的二级标题: 交付证据", result.stderr)

    def test_human_documents_reject_visible_dynamic_state(self) -> None:
        self.overview.write_text(
            self.overview.read_text(encoding="utf-8").replace(
                "# 项目\n", "# 项目\n\n- 状态：进行中\n"
            ),
            encoding="utf-8",
        )
        result = self.run_cli("check", *self.common_args(), "--overview", self.overview)
        self.assertEqual(1, result.returncode)
        self.assertIn("人读文档不保存手工动态状态“状态”", result.stderr)

    def test_human_story_rejects_solution_overview(self) -> None:
        self.story.write_text(
            self.story.read_text(encoding="utf-8").replace(
                "## 验收标准", "## 解决方案概览\n- 历史方案。\n\n## 验收标准"
            ),
            encoding="utf-8",
        )
        self.mark_done(self.story)
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("不允许的二级标题: 解决方案概览", result.stderr)

    def test_epic_must_be_a_standalone_file(self) -> None:
        misplaced = self.root / "README.md"
        text = self.epic.read_text(encoding="utf-8").replace("../stories/", "stories/")
        misplaced.write_text(text, encoding="utf-8")
        result = self.run_cli("check", "--epic", misplaced, "--stories-dir", self.stories)
        self.assertEqual(1, result.returncode)
        self.assertIn("Epic 必须独立保存", result.stderr)

    def test_epic_requires_global_design(self) -> None:
        text = self.epic.read_text(encoding="utf-8").replace("## 全局设计", "## 其他设计")
        self.epic.write_text(text, encoding="utf-8")
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("缺少二级标题 ## 全局设计", result.stderr)

    def test_epic_global_design_requires_architecture_diagram(self) -> None:
        text = self.epic.read_text(encoding="utf-8").replace(EPIC_MERMAID_BLOCK, "只有文字。")
        self.epic.write_text(text, encoding="utf-8")
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("必须包含至少一张", result.stderr)

    def test_epic_global_design_accepts_multiple_independent_diagrams(self) -> None:
        second_diagram = """```mermaid
%%{init: {"securityLevel": "strict", "htmlLabels": false}}%%
flowchart LR
    C["独立输入"] --> D["独立交付"]
```"""
        text = self.epic.read_text(encoding="utf-8").replace(
            EPIC_MERMAID_BLOCK,
            EPIC_MERMAID_BLOCK + "\n\n**能力二：独立流程。**\n\n" + second_diagram,
        )
        self.epic.write_text(text, encoding="utf-8")
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(0, result.returncode, result.stderr)

    def test_epic_global_design_accepts_text_architecture_diagram(self) -> None:
        text = self.epic.read_text(encoding="utf-8").replace(
            EPIC_MERMAID_BLOCK,
            "```text\n[输入] --> [交付]\n```",
        )
        self.epic.write_text(text, encoding="utf-8")
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(0, result.returncode, result.stderr)

    def test_epic_content_budget_is_enforced(self) -> None:
        text = self.epic.read_text(encoding="utf-8").replace("愿景。", "愿景。" + "甲" * 3001)
        self.epic.write_text(text, encoding="utf-8")
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("超过上限 3000", result.stderr)

    def test_overview_content_budget_is_enforced(self) -> None:
        text = self.overview.read_text(encoding="utf-8").replace("看进展。", "看进展。" + "丁" * 1501)
        self.overview.write_text(text, encoding="utf-8")
        result = self.run_cli("check", *self.common_args(), "--overview", self.overview)
        self.assertEqual(1, result.returncode)
        self.assertIn("超过上限 1500", result.stderr)

    def test_story_content_budget_is_enforced(self) -> None:
        text = self.story.read_text(encoding="utf-8").replace("可验证。", "可验证。" + "乙" * 2201)
        self.story.write_text(text, encoding="utf-8")
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("超过上限 2200", result.stderr)

    def test_stale_dashboard_fails_check(self) -> None:
        rendered = self.run_cli("render", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(0, rendered.returncode, rendered.stderr)
        text = self.story.read_text(encoding="utf-8").replace("title: 完成测试", "title: 完成新测试")
        self.story.write_text(text, encoding="utf-8")
        result = self.run_cli("check", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(1, result.returncode)
        self.assertIn("仪表盘已过期", result.stderr)

    def test_render_replaces_the_entire_dashboard(self) -> None:
        self.dashboard.write_text("# 手工状态\n\n## 执行命令\n旧内容。\n", encoding="utf-8")
        result = self.run_cli("render", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(0, result.returncode, result.stderr)
        output = self.dashboard.read_text(encoding="utf-8")
        self.assertNotIn("执行命令", output)
        self.assertIn("本文由脚本根据 Agent JSON 状态源生成", output)

    def test_dashboard_content_budget_is_enforced(self) -> None:
        data = self.read_json(self.risks)
        data["watch_items"] = ["上游变化时重新验证。" + "丙" * 3001]
        self.write_json(self.risks, data)
        result = self.run_cli("render", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(1, result.returncode)
        self.assertIn("超过上限 3000", result.stderr)

    def test_dashboard_allows_six_risks_and_rejects_seven(self) -> None:
        data = self.read_json(self.risks)
        data["watch_items"] = [f"风险 {index}" for index in range(1, 7)]
        self.write_json(self.risks, data)
        allowed = self.run_cli("render", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(0, allowed.returncode, allowed.stderr)

        data["watch_items"].append("风险 7")
        self.write_json(self.risks, data)
        rejected = self.run_cli("render", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(1, rejected.returncode)
        self.assertIn("待决策与后续关注合计最多 6 项", rejected.stderr)

    def test_check_rejects_manually_edited_dashboard(self) -> None:
        rendered = self.run_cli("render", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(0, rendered.returncode, rendered.stderr)
        self.dashboard.write_text(
            self.dashboard.read_text(encoding="utf-8") + "\n## 执行命令\n运行细节。\n",
            encoding="utf-8",
        )
        result = self.run_cli("check", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(1, result.returncode)
        self.assertIn("仪表盘已过期", result.stderr)

    def test_story_requires_one_direct_agent_card(self) -> None:
        self.card.unlink()
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("必须有且仅有一份", result.stderr)

    def test_markdown_agent_card_is_rejected(self) -> None:
        self.card.unlink()
        (self.agent / "STORY-01-测试执行卡.md").write_text("# 旧执行卡\n", encoding="utf-8")
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("Agent 执行卡必须是 JSON", result.stderr)

    def test_agent_card_requires_structured_fields(self) -> None:
        data = self.read_json(self.card)
        del data["goal"]
        self.write_json(self.card, data)
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("缺少字段 goal", result.stderr)

    def test_agent_card_intent_version_must_match_story(self) -> None:
        data = self.read_json(self.card)
        data["intent_version"] = 2
        self.write_json(self.card, data)
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("intent_version 必须与", result.stderr)

    def test_key_decision_requires_decider_agent_advice_and_impact(self) -> None:
        text = self.story.read_text(encoding="utf-8").replace("Agent 建议：", "实现建议：")
        self.story.write_text(text, encoding="utf-8")
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("关键决策 1 缺少 Agent 建议：", result.stderr)

    def test_pending_key_decision_requires_blocked_story(self) -> None:
        text = self.story.read_text(encoding="utf-8").replace("决定者：用户", "决定者：待用户确认")
        self.story.write_text(text, encoding="utf-8")
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("存在待用户确认的关键决策时 status 必须为 blocked", result.stderr)

    def test_human_documents_reject_dynamic_status_fields(self) -> None:
        self.story.write_text(
            self.story.read_text(encoding="utf-8").replace("gate: G1", "status: todo\ngate: G1"),
            encoding="utf-8",
        )
        self.epic.write_text(
            self.epic.read_text(encoding="utf-8").replace("title: 测试 Epic", "title: 测试 Epic\nowner: Agent"),
            encoding="utf-8",
        )
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("人读文档不保存动态字段 status", result.stderr)
        self.assertIn("人读文档不保存动态字段 owner", result.stderr)

    def test_risk_register_is_required(self) -> None:
        self.risks.unlink()
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("风险与阻塞.json", result.stderr)

    def test_every_epic_coverage_item_requires_one_owner(self) -> None:
        data = self.read_json(self.card)
        data["owns"] = []
        self.write_json(self.card, data)
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("owns 至少包含一个覆盖项", result.stderr)
        self.assertIn("覆盖项 TEST 没有 Story 主责", result.stderr)

    def test_agent_card_rejects_duplicate_coverage_claims(self) -> None:
        data = self.read_json(self.card)
        data["owns"] = ["TEST", "TEST"]
        self.write_json(self.card, data)
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("owns 不得包含重复覆盖项", result.stderr)

    def test_coverage_item_must_not_have_multiple_story_owners(self) -> None:
        second = self.stories / "Story-02-测试.md"
        second.write_text(
            self.story.read_text(encoding="utf-8").replace("STORY-01", "STORY-02").replace(
                "Story-01-测试", "Story-02-测试"
            ),
            encoding="utf-8",
        )
        self.write_json(self.agent / "STORY-02-测试.json", card_payload("STORY-02", "TEST", "测试"))
        self.epic.write_text(
            self.epic.read_text(encoding="utf-8").replace(
                "- [Story](../stories/Story-01-测试.md)",
                "- [Story](../stories/Story-01-测试.md)\n- [Story](../stories/Story-02-测试.md)",
            ),
            encoding="utf-8",
        )
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("覆盖项 TEST 被多个 Story 主责: STORY-01, STORY-02", result.stderr)

    def test_render_clears_finished_dependency_blocker(self) -> None:
        self.add_story("STORY-02", "后续", "STORY-01", "NEXT")
        self.mark_done(self.story)
        second_card = next(self.agent.glob("STORY-02-*.json"))
        data = self.read_json(second_card)
        data["status"] = "blocked"
        data["blocker"] = "STORY-01 未完成"
        self.write_json(second_card, data)

        rendered = self.run_cli("render", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(0, rendered.returncode, rendered.stderr)
        self.assertIn("已同步依赖阻塞: STORY-02", rendered.stdout)
        updated = self.read_json(second_card)
        self.assertEqual("todo", updated["status"])
        self.assertEqual("无", updated["blocker"])
        self.assertIn("可领取：STORY-02", self.dashboard.read_text(encoding="utf-8"))

    def test_render_marks_waiting_story_blocked(self) -> None:
        self.add_story("STORY-02", "后续", "STORY-01", "NEXT")
        stale = self.run_cli("check", *self.common_args())
        self.assertEqual(1, stale.returncode)
        self.assertIn("依赖阻塞已过期，请运行 render: STORY-02", stale.stderr)

        rendered = self.run_cli("render", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(0, rendered.returncode, rendered.stderr)
        self.assertIn("已同步依赖阻塞: STORY-02", rendered.stdout)
        second_card = next(self.agent.glob("STORY-02-*.json"))
        updated = self.read_json(second_card)
        self.assertEqual("blocked", updated["status"])
        self.assertEqual("STORY-01 未完成", updated["blocker"])

    def test_render_keeps_non_dependency_blocker(self) -> None:
        self.add_story("STORY-02", "后续", "STORY-01", "NEXT")
        self.mark_done(self.story)
        second_card = next(self.agent.glob("STORY-02-*.json"))
        data = self.read_json(second_card)
        data["status"] = "blocked"
        data["blocker"] = "证书未就绪"
        self.write_json(second_card, data)

        rendered = self.run_cli("render", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(0, rendered.returncode, rendered.stderr)
        self.assertNotIn("已同步依赖阻塞", rendered.stdout)
        updated = self.read_json(second_card)
        self.assertEqual("blocked", updated["status"])
        self.assertEqual("证书未就绪", updated["blocker"])

        checked = self.run_cli("check", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(0, checked.returncode, checked.stderr)

    def test_check_fails_when_dependency_blocker_is_stale(self) -> None:
        self.add_story("STORY-02", "后续", "STORY-01", "NEXT")
        self.mark_done(self.story)
        second_card = next(self.agent.glob("STORY-02-*.json"))
        data = self.read_json(second_card)
        data["status"] = "blocked"
        data["blocker"] = "STORY-01 未完成"
        self.write_json(second_card, data)

        checked = self.run_cli("check", *self.common_args())
        self.assertEqual(1, checked.returncode)
        self.assertIn("依赖阻塞已过期，请运行 render: STORY-02", checked.stderr)

    def test_started_story_requires_refreshed_code_baseline(self) -> None:
        data = self.read_json(self.card)
        data["status"] = "in_progress"
        data["owner"] = "Agent"
        self.write_json(self.card, data)
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("refreshed 不能为待领取", result.stderr)
        self.assertIn("code_baseline 必须记录实际版本", result.stderr)

    def test_write_canonicalizes_agent_card(self) -> None:
        payload = card_payload()
        payload["status"] = "todo"
        source = self.root / "incoming.json"
        self.write_json(source, payload)
        target = self.agent / "STORY-01-测试.json"
        result = self.run_cli("write", "--file", target, "--from", source)
        self.assertEqual(0, result.returncode, result.stderr)
        written = target.read_text(encoding="utf-8")
        self.assertTrue(written.startswith("{\n  \"kind\": \"agent-card\""))
        self.assertIn("schema_version", written)

    def test_write_rejects_invalid_card(self) -> None:
        payload = card_payload()
        payload["status"] = "mystery"
        source = self.root / "incoming.json"
        self.write_json(source, payload)
        result = self.run_cli("write", "--file", self.card, "--from", source)
        self.assertEqual(1, result.returncode)
        self.assertIn("status 必须是", result.stderr)

    def test_patch_updates_card_status_and_checklist(self) -> None:
        result = self.run_cli(
            "patch",
            "--file",
            self.card,
            "--set",
            "status=in_progress",
            "--set",
            "owner=Codex",
            "--set",
            "refreshed=2026-08-18",
            "--set",
            "code_baseline=abc123",
            "--check-item",
            "2",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        data = self.read_json(self.card)
        self.assertEqual("in_progress", data["status"])
        self.assertEqual("Codex", data["owner"])
        self.assertEqual("2026-08-18", data["status_updated"])
        self.assertTrue(data["checklist"][1]["done"])

    def test_patch_can_update_risk_register(self) -> None:
        result = self.run_cli(
            "patch",
            "--file",
            self.risks,
            "--set",
            'watch_items=["需要复核上游。"]',
        )
        self.assertEqual(0, result.returncode, result.stderr)
        data = self.read_json(self.risks)
        self.assertEqual(["需要复核上游。"], data["watch_items"])
        self.assertEqual("2026-08-18", data["updated"])

    def test_template_writes_card_scaffold(self) -> None:
        target = self.agent / "STORY-09-脚手架.json"
        result = self.run_cli(
            "template",
            "agent-card",
            "--story",
            "STORY-09",
            "--file",
            target,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        data = self.read_json(target)
        self.assertEqual("agent-card", data["kind"])
        self.assertEqual("STORY-09", data["story"])
        self.assertEqual(3, len(data["checklist"]))

    def test_optional_agent_reference_must_be_valid_json(self) -> None:
        self.write_json(
            self.agent / "核心决策.json",
            {
                "kind": "agent-reference",
                "schema_version": 1,
                "id": "core-decisions",
                "title": "核心决策",
                "updated": "2026-08-17",
                "body": {"D-01": "破坏性 v2"},
            },
        )
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(0, result.returncode, result.stderr)

        self.write_json(self.agent / "坏文档.json", {"kind": "agent-reference"})
        rejected = self.run_cli("check", *self.common_args())
        self.assertEqual(1, rejected.returncode)
        self.assertIn("缺少非空字段", rejected.stderr)


if __name__ == "__main__":
    unittest.main()
