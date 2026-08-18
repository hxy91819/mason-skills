import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("epic_story.py")


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
        self.overview.write_text(
            "# 项目\n\n## 项目一览\n看进展。\n\n## Epic\n- Epic。\n\n## Agent 入口\n- Agent。\n",
            encoding="utf-8",
        )
        self.epic.write_text(
            """---
kind: epic
id: EPIC-TEST
title: 测试 Epic
status: in_progress
owner: 团队
updated: 2026-08-17
coverage: [TEST]
---
# Epic
## 愿景
愿景。
## 成功标准
- 交付。
## Story 地图
- [Story](../stories/Story-01-测试.md)
""",
            encoding="utf-8",
        )
        self.story = self.stories / "Story-01-测试.md"
        self.story.write_text(
            """---
kind: story
id: STORY-01
epic: EPIC-TEST
title: 完成测试
status: todo
gate: G1
owner: 待领取
depends_on: []
blocker: 无
updated: 2026-08-17
intent_version: 1
---
# Story
## 愿景
可验证。
## 范围
- [执行卡](../agent/STORY-01-测试执行卡.md)。
## 解决方案概览
- 固定输入。
- 运行验证。
## TODO
- [x] 已完成项
- [ ] 待完成项
- [ ] 后续项
## 验收标准
- 二元通过。
""",
            encoding="utf-8",
        )
        self.card = self.agent / "STORY-01-测试执行卡.md"
        self.card.write_text(
            """---
story: STORY-01
intent_version: 1
refreshed: 待领取
code_baseline: 待领取
owns: [TEST]
verifies: []
---
# STORY-01 测试执行卡

- 对应：[STORY-01](../stories/Story-01-测试.md)

## 目标与完成信号
产出可验证结果。
## 决策边界
愿景和验收由人维护。
## 技术方案
固定输入后验证。
## 权威输入
读取当前 Story。
## 领取检查
开始前刷新代码入口和基线。
## 执行步骤
1. 运行检查，退出码为零时完成。
## 验证与证据
保存退出码。
## 停止条件
输入漂移时停止。
## 交接
提交结果与版本。
""",
            encoding="utf-8",
        )
        self.dashboard.write_text(
            "# 进展\n\n<!-- epic-story-dashboard:start -->\n旧内容\n"
            "<!-- epic-story-dashboard:end -->\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

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
            .replace("测试执行卡", f"{slug}执行卡")
            .replace("title: 完成测试", f"title: {slug}")
            .replace("depends_on: []", f"depends_on: [{dependency}]")
            .replace("# Story", f"# {story_id}"),
            encoding="utf-8",
        )
        card_name = f"{story_id}-{slug}执行卡.md"
        (self.agent / card_name).write_text(
            self.card.read_text(encoding="utf-8")
            .replace("STORY-01", story_id)
            .replace("Story-01-测试", f"Story-{suffix}-{slug}")
            .replace("owns: [TEST]", f"owns: [{coverage}]")
            .replace("测试执行卡", f"{slug}执行卡"),
            encoding="utf-8",
        )
        epic_text = self.epic.read_text(encoding="utf-8").replace(
            "coverage: [", f"coverage: [{coverage}, ", 1
        )
        self.epic.write_text(
            epic_text.rstrip() + f"\n- [{story_id}](../stories/{story_name})\n", encoding="utf-8"
        )
        return story_path

    def test_render_check_and_status_report_observable_project_state(self) -> None:
        rendered = self.run_cli("render", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(0, rendered.returncode, rendered.stderr)
        output = self.dashboard.read_text(encoding="utf-8")
        self.assertIn("TODO | 依赖", output)
        self.assertIn("1/3", output)
        self.assertIn("可领取：STORY-01", output)

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
        self.assertEqual("待完成项", payload["stories"][0]["next_todo"])

    def test_done_requires_all_todos_checked(self) -> None:
        text = self.story.read_text(encoding="utf-8").replace("status: todo", "status: done").replace(
            "owner: 待领取", "owner: Agent"
        )
        self.story.write_text(text, encoding="utf-8")
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("所有 TODO 必须勾选", result.stderr)

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
            .replace("STORY-01-测试", "STORY-02-后续")
            .replace("# Story", "# 后续 Story"),
            encoding="utf-8",
        )
        second_card = self.agent / "STORY-02-后续执行卡.md"
        second_card.write_text(
            self.card.read_text(encoding="utf-8")
            .replace("STORY-01", "STORY-02")
            .replace("Story-01-测试", "Story-02-后续"),
            encoding="utf-8",
        )
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
        renamed_card = self.agent / "STORY-01.0-测试执行卡.md"
        self.card.rename(renamed_card)
        renamed_card.write_text(
            renamed_card.read_text(encoding="utf-8")
            .replace("STORY-01", invalid)
            .replace("Story-01-测试", "Story-01.0-测试"),
            encoding="utf-8",
        )
        self.epic.write_text(
            self.epic.read_text(encoding="utf-8").replace("Story-01-测试", "Story-01.0-测试"),
            encoding="utf-8",
        )

        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("Story id 必须匹配 STORY-NN 或 STORY-NN.M", result.stderr)

    def test_todo_count_outside_story_contract_fails(self) -> None:
        text = self.story.read_text(encoding="utf-8").replace("- [ ] 后续项\n", "")
        self.story.write_text(text, encoding="utf-8")
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("TODO 必须包含 3～7 个复选项", result.stderr)

    def test_epic_must_be_a_standalone_file(self) -> None:
        misplaced = self.root / "README.md"
        text = self.epic.read_text(encoding="utf-8").replace("../stories/", "stories/")
        misplaced.write_text(text, encoding="utf-8")
        result = self.run_cli("check", "--epic", misplaced, "--stories-dir", self.stories)
        self.assertEqual(1, result.returncode)
        self.assertIn("Epic 必须独立保存", result.stderr)

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
        text = self.story.read_text(encoding="utf-8").replace("- 固定输入。", "- 固定输入。" + "乙" * 2201)
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

    def test_reversed_dashboard_markers_fail_without_traceback(self) -> None:
        self.dashboard.write_text(
            "<!-- epic-story-dashboard:end -->\n<!-- epic-story-dashboard:start -->\n",
            encoding="utf-8",
        )
        result = self.run_cli("render", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(1, result.returncode)
        self.assertIn("仪表盘标记顺序错误", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_dashboard_content_budget_is_enforced(self) -> None:
        self.dashboard.write_text(
            "# 进展\n" + "丙" * 3001 + "\n<!-- epic-story-dashboard:start -->\n旧内容\n"
            "<!-- epic-story-dashboard:end -->\n",
            encoding="utf-8",
        )
        result = self.run_cli("render", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(1, result.returncode)
        self.assertIn("超过上限 3000", result.stderr)

    def test_dashboard_allows_six_risks_and_rejects_seven(self) -> None:
        risks = "\n".join(f"| 风险 {index} | 关闭路径 {index} |" for index in range(1, 7))
        self.dashboard.write_text(
            "# 进展\n\n<!-- epic-story-dashboard:start -->\n旧内容\n"
            "<!-- epic-story-dashboard:end -->\n\n"
            "## 门禁状态\n\n| 门禁 | 状态 |\n| --- | --- |\n| G1 | 执行中 |\n\n"
            "## 关键基线\n\n| 项目 | 事实 |\n| --- | --- |\n| 基线 | 固定 |\n\n"
            f"## 风险与阻塞\n\n| 风险 | 关闭路径 |\n| --- | --- |\n{risks}\n",
            encoding="utf-8",
        )
        allowed = self.run_cli("render", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(0, allowed.returncode, allowed.stderr)

        text = self.dashboard.read_text(encoding="utf-8").replace(
            "| 风险 6 | 关闭路径 6 |", "| 风险 6 | 关闭路径 6 |\n| 风险 7 | 关闭路径 7 |"
        )
        self.dashboard.write_text(text, encoding="utf-8")
        rejected = self.run_cli("render", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(1, rejected.returncode)
        self.assertIn("风险与阻塞 最多 6 行", rejected.stderr)

    def test_dashboard_rejects_execution_detail_section(self) -> None:
        self.dashboard.write_text(
            "# 进展\n\n## 执行命令\n运行细节。\n\n<!-- epic-story-dashboard:start -->\n旧内容\n"
            "<!-- epic-story-dashboard:end -->\n",
            encoding="utf-8",
        )
        result = self.run_cli("render", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(1, result.returncode)
        self.assertIn("不允许的二级标题", result.stderr)

    def test_story_requires_one_direct_agent_card(self) -> None:
        self.card.unlink()
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("必须有且仅有一份", result.stderr)

    def test_agent_card_requires_structured_sections(self) -> None:
        text = self.card.read_text(encoding="utf-8").replace("## 停止条件", "## 其他")
        self.card.write_text(text, encoding="utf-8")
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("停止条件", result.stderr)
        self.assertIn("不允许的二级标题", result.stderr)

    def test_agent_card_intent_version_must_match_story(self) -> None:
        text = self.card.read_text(encoding="utf-8").replace("intent_version: 1", "intent_version: 2")
        self.card.write_text(text, encoding="utf-8")
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("intent_version 必须与", result.stderr)

    def test_every_epic_coverage_item_requires_one_owner(self) -> None:
        text = self.card.read_text(encoding="utf-8").replace("owns: [TEST]", "owns: []")
        self.card.write_text(text, encoding="utf-8")
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("owns 至少包含一个覆盖项", result.stderr)
        self.assertIn("覆盖项 TEST 没有 Story 主责", result.stderr)

    def test_agent_card_rejects_duplicate_coverage_claims(self) -> None:
        text = self.card.read_text(encoding="utf-8").replace("owns: [TEST]", "owns: [TEST, TEST]")
        self.card.write_text(text, encoding="utf-8")
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
        second_card = self.agent / "STORY-02-测试执行卡.md"
        second_card.write_text(
            self.card.read_text(encoding="utf-8").replace("STORY-01", "STORY-02").replace(
                "Story-01-测试", "Story-02-测试"
            ),
            encoding="utf-8",
        )
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

    def mark_done(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        text = text.replace("status: todo", "status: done").replace("status: blocked", "status: done")
        text = text.replace("owner: 待领取", "owner: Agent")
        text = text.replace("- [ ] ", "- [x] ")
        path.write_text(text, encoding="utf-8")
        story_id = next(line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("id: "))
        for card in self.agent.glob(f"{story_id}-*执行卡.md"):
            card.write_text(
                card.read_text(encoding="utf-8")
                .replace("refreshed: 待领取", "refreshed: 2026-08-18")
                .replace("code_baseline: 待领取", "code_baseline: testhash"),
                encoding="utf-8",
            )

    def test_render_clears_finished_dependency_blocker(self) -> None:
        second = self.add_story("STORY-02", "后续", "STORY-01", "NEXT")
        self.mark_done(self.story)
        second.write_text(
            second.read_text(encoding="utf-8")
            .replace("status: todo", "status: blocked")
            .replace("blocker: 无", "blocker: STORY-01 未完成"),
            encoding="utf-8",
        )

        rendered = self.run_cli("render", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(0, rendered.returncode, rendered.stderr)
        self.assertIn("已同步依赖阻塞: STORY-02", rendered.stdout)
        updated = second.read_text(encoding="utf-8")
        self.assertIn("status: todo", updated)
        self.assertIn("blocker: 无", updated)
        self.assertIn("可领取：STORY-02", self.dashboard.read_text(encoding="utf-8"))

    def test_render_marks_waiting_story_blocked(self) -> None:
        second = self.add_story("STORY-02", "后续", "STORY-01", "NEXT")
        stale = self.run_cli("check", *self.common_args())
        self.assertEqual(1, stale.returncode)
        self.assertIn("依赖阻塞已过期，请运行 render: STORY-02", stale.stderr)

        rendered = self.run_cli("render", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(0, rendered.returncode, rendered.stderr)
        self.assertIn("已同步依赖阻塞: STORY-02", rendered.stdout)
        updated = second.read_text(encoding="utf-8")
        self.assertIn("status: blocked", updated)
        self.assertIn("blocker: STORY-01 未完成", updated)

    def test_render_keeps_non_dependency_blocker(self) -> None:
        second = self.add_story("STORY-02", "后续", "STORY-01", "NEXT")
        self.mark_done(self.story)
        second.write_text(
            second.read_text(encoding="utf-8")
            .replace("status: todo", "status: blocked")
            .replace("blocker: 无", "blocker: 证书未就绪"),
            encoding="utf-8",
        )

        rendered = self.run_cli("render", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(0, rendered.returncode, rendered.stderr)
        self.assertNotIn("已同步依赖阻塞", rendered.stdout)
        updated = second.read_text(encoding="utf-8")
        self.assertIn("status: blocked", updated)
        self.assertIn("blocker: 证书未就绪", updated)

        checked = self.run_cli("check", *self.common_args(), "--dashboard", self.dashboard)
        self.assertEqual(0, checked.returncode, checked.stderr)

    def test_check_fails_when_dependency_blocker_is_stale(self) -> None:
        second = self.add_story("STORY-02", "后续", "STORY-01", "NEXT")
        self.mark_done(self.story)
        second.write_text(
            second.read_text(encoding="utf-8")
            .replace("status: todo", "status: blocked")
            .replace("blocker: 无", "blocker: STORY-01 未完成"),
            encoding="utf-8",
        )

        checked = self.run_cli("check", *self.common_args())
        self.assertEqual(1, checked.returncode)
        self.assertIn("依赖阻塞已过期，请运行 render: STORY-02", checked.stderr)

    def test_started_story_requires_refreshed_code_baseline(self) -> None:
        text = self.story.read_text(encoding="utf-8").replace("status: todo", "status: in_progress").replace(
            "owner: 待领取", "owner: Agent"
        )
        self.story.write_text(text, encoding="utf-8")
        result = self.run_cli("check", *self.common_args())
        self.assertEqual(1, result.returncode)
        self.assertIn("refreshed 不能为待领取", result.stderr)
        self.assertIn("code_baseline 必须记录实际版本", result.stderr)


if __name__ == "__main__":
    unittest.main()
