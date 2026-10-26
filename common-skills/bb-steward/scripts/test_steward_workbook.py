"""验证 BB 管家工作簿门禁与提交节流逻辑。"""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import steward_workbook as sw

VALID_WORKBOOK = """# 项目介绍与 demo 的持续完善

更新：2026-10-14

## 路线

- [x] 阶段 1：既有原型与常规修复已交付
- [ ] 阶段 2：冷启动独立实例与 Playwright 回归 ← 进行中（最近线程 thr_55yf6266zn）
- [ ] 阶段 3：浅色多图落地页重设计与发布

## 关键决策

- 2026-10-14 用户指定当前 Agent 作为 BB 管家，只做规划、派发和工作簿维护。原因：保持主上下文清晰。影响：全部阶段。
- 2026-10-14 demo 启动时预建独立工作区并加载到 DSH。原因：减少首次操作步骤。影响：阶段 2。

## 用户待办

| 状态 | 事项 | 为什么只能用户做 | 挡住 | 提出 |
| --- | --- | --- | --- | --- |
| 待办 | 用公司账号抓取《揭榜方案模板》 | 乐享需要本人登录 | 阶段 3 | 2026-10-14 |
"""


class StewardWorkbookTests(unittest.TestCase):
    def test_valid_workbook_passes_check(self):
        res = sw.check_workbook(VALID_WORKBOOK)
        self.assertTrue(res["ok"], res["errors"])
        self.assertEqual(res["stats"]["route_items"], 3)
        self.assertEqual(res["stats"]["decision_items"], 2)

    def test_traditional_chinese_headings_pass_check(self):
        text = (VALID_WORKBOOK.replace("## 路线", "## 路線")
                .replace("## 关键决策", "## 關鍵決策")
                .replace("## 用户待办", "## 用戶待辦"))
        self.assertTrue(sw.check_workbook(text)["ok"])

    def test_extra_section_or_table_in_route_is_rejected(self):
        with_extra = VALID_WORKBOOK + "\n## 追加任务\n\n- [ ] 临时事项\n"
        res1 = sw.check_workbook(with_extra)
        self.assertFalse(res1["ok"])
        self.assertTrue(any("二级标题必须且只能按顺序" in e for e in res1["errors"]))

        with_route_table = VALID_WORKBOOK.replace(
            "- [ ] 阶段 3：浅色多图落地页重设计与发布",
            "- [ ] 阶段 3：浅色多图落地页重设计与发布\n\n| 方向 | 状态 |\n| --- | --- |\n| A | 299次 |",
        )
        res2 = sw.check_workbook(with_route_table)
        self.assertFalse(res2["ok"])
        self.assertTrue(any("在「路线」中使用了表格" in e for e in res2["errors"]))

    def test_overlong_line_and_excess_decisions_are_rejected(self):
        long_line = "- [ ] 阶段 2：" + ("校准修了某问题、" * 30)
        bloated = VALID_WORKBOOK.replace(
            "- [ ] 阶段 2：冷启动独立实例与 Playwright 回归 ← 进行中（最近线程 thr_55yf6266zn）",
            long_line,
        )
        res = sw.check_workbook(bloated)
        self.assertFalse(res["ok"])
        self.assertTrue(any("可见字符数" in e for e in res["errors"]))

    def test_should_commit_ignores_micro_progress_and_detects_state_transitions(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "workbook.md"
            check_args = {
                "max_nonempty_lines": sw.DEFAULT_MAX_NONEMPTY_LINES,
                "max_line_chars": sw.DEFAULT_MAX_LINE_CHARS,
                "max_route_items": sw.DEFAULT_MAX_ROUTE_ITEMS,
                "max_decisions": sw.DEFAULT_MAX_DECISIONS,
            }
            # 1. 仅修改括号里的最近线程 ID 和微进度，不应触发 commit
            minor_edit = VALID_WORKBOOK.replace("thr_55yf6266zn", "thr_new123，已跑完第一轮测试")
            p.write_text(minor_edit)
            r_minor = sw.should_commit_workbook(p, check_args, baseline_text=VALID_WORKBOOK)
            self.assertTrue(r_minor["ok"])
            self.assertFalse(r_minor["should_commit"])
            self.assertEqual(r_minor["reason"], "no_structural_state_change")

            # 2. 阶段 2 完成勾选并推进到阶段 3，应触发 commit
            stage_done = VALID_WORKBOOK.replace(
                "- [ ] 阶段 2：冷启动独立实例与 Playwright 回归 ← 进行中（最近线程 thr_55yf6266zn）\n- [ ] 阶段 3：浅色多图落地页重设计与发布",
                "- [x] 阶段 2：冷启动独立实例与 Playwright 回归\n- [ ] 阶段 3：浅色多图落地页重设计与发布 ← 进行中",
            )
            p.write_text(stage_done)
            r_stage = sw.should_commit_workbook(p, check_args, baseline_text=VALID_WORKBOOK)
            self.assertTrue(r_stage["ok"])
            self.assertTrue(r_stage["should_commit"])
            self.assertIn("路线", r_stage["changed_sections"])

            # 3. 用户待办状态从“待办”变为“已完成”，应触发 commit
            todo_done = VALID_WORKBOOK.replace("| 待办 | 用公司账号", "| 已完成 | 用公司账号")
            p.write_text(todo_done)
            r_todo = sw.should_commit_workbook(p, check_args, baseline_text=VALID_WORKBOOK)
            self.assertTrue(r_todo["ok"])
            self.assertTrue(r_todo["should_commit"])
            self.assertIn("用户待办", r_todo["changed_sections"])


if __name__ == "__main__":
    unittest.main()
