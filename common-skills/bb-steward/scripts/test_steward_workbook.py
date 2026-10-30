"""验证 BB 管家工作簿门禁、提交节流与收尾对账逻辑。"""
from datetime import datetime
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import steward_workbook as sw

NOW = datetime(2026, 10, 26, 18, 0)

RECONCILED_WORKBOOK = """# 把维护教训落到新仓库

更新：2026-10-26

## 路线

- [x] 阶段 1：盘点仓库
- [ ] 阶段 2：布局整理 ← 进行中 thr_aaaaaa1111
- [ ] 阶段 3：真机验收 ← 等用户
- [ ] 阶段 4：主服切换窗口 ← 定时 10-26 22:10 打开窗口
- [ ] 阶段 5：发布镜像 ← 排在 阶段 4 后：用窗口切换后的新版本

## 关键决策

- 2026-10-26 环境名只用 test/prod。原因：避免撞名。影响：部署。

## 用户待办

| 状态 | 事项 | 为什么只能用户做 | 挡住 | 提出 |
| --- | --- | --- | --- | --- |
| 待办 | iPad 打开更新页验收 | 真机线下：只有用户有设备 | 阶段 3 | 2026-10-26 |
| 待办 | 轮换令牌 | 凭据账号：令牌归用户 | 不挡 | 2026-10-26 |
"""


def thread(tid, status="idle", idle_minutes=120, **flags):
    info = {"id": tid, "status": status, "archived": False, "queued": False, "interaction": False,
            "background": False, "updated_at": NOW.timestamp() - idle_minutes * 60, "parent": None}
    info.update(flags)
    return info


def kinds(result):
    return [(p["kind"], p["severity"]) for p in result["problems"]]

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

    def test_route_stage_count_is_unbounded_by_default(self):
        extra = "\n".join(f"- [ ] 阶段 {i}：并行事项" for i in range(4, 16))
        text = VALID_WORKBOOK.replace(
            "- [ ] 阶段 3：浅色多图落地页重设计与发布",
            "- [ ] 阶段 3：浅色多图落地页重设计与发布\n" + extra,
        )
        res = sw.check_workbook(text)
        self.assertTrue(res["ok"], res["errors"])
        self.assertEqual(res["stats"]["route_items"], 15)
        capped = sw.check_workbook(text, max_route_items=10)
        self.assertFalse(capped["ok"])
        self.assertTrue(any("阶段数 15 超过上限 10" in e for e in capped["errors"]))

    def test_excess_lines_warn_without_failing(self):
        extra = "\n".join(f"- [x] 阶段 {i}：已交付" for i in range(4, 4 + sw.DEFAULT_MAX_NONEMPTY_LINES))
        text = VALID_WORKBOOK.replace(
            "- [ ] 阶段 3：浅色多图落地页重设计与发布",
            "- [ ] 阶段 3：浅色多图落地页重设计与发布\n" + extra,
        )
        res = sw.check_workbook(text)
        self.assertTrue(res["ok"], res["errors"])
        self.assertTrue(any("非空行总数" in w for w in res["warnings"]))

    def test_numbered_todo_table_with_background_parses(self):
        long_bg = "背景说明" * 60
        text = VALID_WORKBOOK.replace(
            "| 状态 | 事项 | 为什么只能用户做 | 挡住 | 提出 |\n| --- | --- | --- | --- | --- |\n"
            "| 待办 | 用公司账号抓取《揭榜方案模板》 | 乐享需要本人登录 | 阶段 3 | 2026-10-14 |",
            "| 编号 | 状态 | 事项 | 背景 | 建议 | 为什么只能用户做 | 挡住 | 提出 |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
            f"| D1 | 待办 | 用公司账号抓取《揭榜方案模板》 | {long_bg} | 现在抓 | 乐享需要本人登录 | 阶段 3 | 2026-10-14 |",
        )
        self.assertIn("| D1 |", text)
        res = sw.check_workbook(text)
        self.assertTrue(res["ok"], res["errors"])
        todos = sw.parse_todos(sw.parse_workbook(text))
        self.assertEqual([(t["status"], t["blocks"], t["reason"]) for t in todos],
                         [("待办", "阶段 3", "乐享需要本人登录")])

    def test_excess_decisions_warn_without_failing(self):
        extra = "\n".join(f"- 2026-10-14 决定 {i}。原因：用户确认。影响：阶段 2。" for i in range(sw.DEFAULT_MAX_DECISIONS))
        res = sw.check_workbook(VALID_WORKBOOK.replace("\n\n## 用户待办", "\n" + extra + "\n\n## 用户待办", 1))
        self.assertTrue(res["ok"])
        self.assertTrue(any("关键决策" in w for w in res["warnings"]))
        self.assertEqual(sw.check_workbook(VALID_WORKBOOK)["warnings"], [])

    def test_fetch_threads_filters_full_list_and_falls_back_to_archived(self):
        active = {"id": "thr_active", "status": "idle"}
        archived = {"id": "thr_old", "status": "idle", "archivedAt": 1}
        calls = []

        def fake_list(*args):
            calls.append(args)
            rows = [archived] if "--archived" in args else [active, {"id": "thr_other"}]
            return [sw.normalize_thread(r) for r in rows]

        with mock.patch.object(sw, "bb_thread_list", side_effect=fake_list):
            found = sw.fetch_threads(["thr_active", "thr_old"])
        self.assertEqual(set(found), {"thr_active", "thr_old"})
        self.assertTrue(found["thr_old"]["archived"])
        self.assertFalse(any("--thread" in a for a in calls))

    def test_overlong_line_is_rejected(self):
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
            (p.parent / "ledger.md").write_text("# 既有历史账")
            check_args = {
                "max_nonempty_lines": sw.DEFAULT_MAX_NONEMPTY_LINES,
                "max_line_chars": sw.DEFAULT_MAX_LINE_CHARS,
                "max_route_items": sw.DEFAULT_MAX_ROUTE_ITEMS,
                "max_decisions": sw.DEFAULT_MAX_DECISIONS,
            }
            # 1. 仅修改括号里的最近线程 ID 和微进度，不应触发 commit
            minor_edit = VALID_WORKBOOK.replace("thr_55yf6266zn", "thr_new123，已跑完第一轮测试")
            p.write_text(minor_edit.replace("更新：2026-10-14", "[要求帐（历史流水账）](ledger.md)"))
            r_minor = sw.should_commit_workbook(p, check_args, baseline_text=VALID_WORKBOOK)
            self.assertTrue(r_minor["ok"])
            self.assertFalse(r_minor["should_commit"])
            self.assertEqual(r_minor["reason"], "no_structural_state_change")

            # 2. 阶段 2 完成勾选并推进到阶段 3，应触发 commit
            stage_done = VALID_WORKBOOK.replace(
                "- [ ] 阶段 2：冷启动独立实例与 Playwright 回归 ← 进行中（最近线程 thr_55yf6266zn）\n- [ ] 阶段 3：浅色多图落地页重设计与发布",
                "- [x] 阶段 2：冷启动独立实例与 Playwright 回归\n- [ ] 阶段 3：浅色多图落地页重设计与发布 ← 进行中",
            )
            p.write_text(stage_done.replace("更新：2026-10-14", "[要求帐（历史流水账）](ledger.md)"))
            r_stage = sw.should_commit_workbook(p, check_args, baseline_text=VALID_WORKBOOK)
            self.assertTrue(r_stage["ok"])
            self.assertTrue(r_stage["should_commit"])
            self.assertIn("路线", r_stage["changed_sections"])

            # 3. 用户待办状态从“待办”变为“已完成”，应触发 commit
            todo_done = VALID_WORKBOOK.replace("| 待办 | 用公司账号", "| 已完成 | 用公司账号")
            p.write_text(todo_done.replace("更新：2026-10-14", "[要求帐（历史流水账）](ledger.md)"))
            r_todo = sw.should_commit_workbook(p, check_args, baseline_text=VALID_WORKBOOK)
            self.assertTrue(r_todo["ok"])
            self.assertTrue(r_todo["should_commit"])
            self.assertIn("用户待办", r_todo["changed_sections"])

    def test_should_commit_tracks_state_changes_but_not_thread_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "workbook.md"
            (p.parent / "ledger.md").write_text("# 既有历史账")
            check_args = {
                "max_nonempty_lines": sw.DEFAULT_MAX_NONEMPTY_LINES,
                "max_line_chars": sw.DEFAULT_MAX_LINE_CHARS,
                "max_route_items": sw.DEFAULT_MAX_ROUTE_ITEMS,
                "max_decisions": sw.DEFAULT_MAX_DECISIONS,
            }
            cases = [
                ("thr_aaaaaa1111", "thr_bbbbbb2222", False),
                ("阶段 3：真机验收 ← 等用户", "阶段 3：真机验收 ← 进行中 thr_cccccc3333", True),
                ("定时 10-26 22:10 打开窗口", "定时 10-27 08:00 打开窗口", True),
            ]
            for old, new, expected in cases:
                p.write_text(RECONCILED_WORKBOOK.replace(old, new).replace("更新：2026-10-26", "[要求帐（历史流水账）](ledger.md)"))
                res = sw.should_commit_workbook(p, check_args, baseline_text=RECONCILED_WORKBOOK)
                self.assertEqual(res["should_commit"], expected, (old, new))


class ReconcileTests(unittest.TestCase):
    def test_running_references_exclude_completed_and_other_states(self):
        text = RECONCILED_WORKBOOK.replace("- [x] 阶段 1：盘点仓库", "- [x] 阶段 1：盘点仓库 ← 进行中 thr_done000001")
        text = text.replace("← 等用户", "← 等用户 thr_wait000001")
        self.assertEqual(sw.running_thread_ids(text), ["thr_aaaaaa1111"])
        self.assertIn("thr_done000001", sw.reconcile_workbook(text)["referenced_threads"])

    def test_every_open_row_in_a_valid_state_passes(self):
        res = sw.reconcile_workbook(RECONCILED_WORKBOOK, now=NOW)
        self.assertTrue(res["ok"], res["problems"])
        self.assertEqual(res["problems"], [])
        self.assertEqual(res["stats"]["open_rows"], 4)
        self.assertEqual(res["referenced_threads"], ["thr_aaaaaa1111"])

    def test_rows_without_a_concrete_state_are_flagged(self):
        broken = (RECONCILED_WORKBOOK
                  .replace("← 进行中 thr_aaaaaa1111", "← 进行中")
                  .replace("← 等用户", "← 随后")
                  .replace("定时 10-26 22:10 打开窗口", "定时 今晚")
                  .replace("：用窗口切换后的新版本", "")
                  .replace("- [x] 阶段 1：盘点仓库", "- [x] 阶段 1：盘点仓库\n- [ ] 阶段 6：远景规划"))
        res = sw.reconcile_workbook(broken, now=NOW)
        self.assertFalse(res["ok"])
        details = {p["label"]: p["detail"] for p in res["problems"] if p["kind"] == "no_state"}
        self.assertEqual(details["阶段 2"], "进行中但没写线程 ID")
        self.assertIn("不在四种之内", details["阶段 3"])
        self.assertEqual(details["阶段 4"], "定时没写 MM-DD HH:MM")
        self.assertEqual(details["阶段 5"], "排在…后 没写依赖的产出")
        self.assertEqual(details["阶段 6"], "缺状态")

    def test_passed_schedule_is_flagged_after_grace(self):
        res = sw.reconcile_workbook(RECONCILED_WORKBOOK, now=datetime(2026, 10, 26, 22, 30))
        self.assertTrue(res["ok"])
        late = sw.reconcile_workbook(RECONCILED_WORKBOOK, now=datetime(2026, 10, 26, 22, 41))
        self.assertIn(("schedule_passed", "nudge"), kinds(late))

    def test_waiting_on_user_needs_an_open_todo_that_blocks_that_row(self):
        unbacked = RECONCILED_WORKBOOK.replace("| 待办 | iPad", "| 已完成 | iPad")
        self.assertIn(("user_wait_unbacked", "nudge"), kinds(sw.reconcile_workbook(unbacked, now=NOW)))

        # 另一行也标等用户，但唯一的待办只挡阶段 3：只有新行被点名。
        two_waits = RECONCILED_WORKBOOK.replace("- [ ] 阶段 3：真机验收 ← 等用户",
                                                "- [ ] 阶段 3：真机验收 ← 等用户\n- [ ] 阶段 6：灰度 ← 等用户")
        res = sw.reconcile_workbook(two_waits, now=NOW)
        self.assertEqual([(p["kind"], p["label"]) for p in res["problems"]], [("user_wait_unbacked", "阶段 6")])

        ranged = two_waits.replace("| 真机线下：只有用户有设备 | 阶段 3 |", "| 真机线下：只有用户有设备 | 阶段 3–6 |")
        self.assertTrue(sw.reconcile_workbook(ranged, now=NOW)["ok"])

        by_title = (RECONCILED_WORKBOOK.replace("- [ ] 阶段 3：真机验收 ← 等用户", "- [ ] 团队试用反馈：等 #90 ← 等用户")
                    .replace("| 阶段 3 | 2026-10-26 |", "| 团队试用反馈 | 2026-10-26 |"))
        self.assertTrue(sw.reconcile_workbook(by_title, now=NOW)["ok"])

    def test_queued_row_must_move_once_its_dependency_is_done(self):
        self.assertTrue(sw.reconcile_workbook(RECONCILED_WORKBOOK, now=NOW)["ok"])
        done = RECONCILED_WORKBOOK.replace("- [ ] 阶段 4：主服切换窗口 ← 定时 10-26 22:10 打开窗口", "- [x] 阶段 4：主服切换窗口")
        self.assertIn(("dependency_done", "nudge"), kinds(sw.reconcile_workbook(done, now=NOW)))

        merged = (RECONCILED_WORKBOOK.replace("- [ ] 阶段 4：主服切换窗口 ← 定时 10-26 22:10 打开窗口\n", "")
                  .replace("- [x] 阶段 1：盘点仓库", "- [x] 阶段1–4、9：均已交付"))
        merged = merged.replace("- [ ] 阶段 2：布局整理 ← 进行中 thr_aaaaaa1111\n", "").replace(
            "- [ ] 阶段 3：真机验收 ← 等用户", "- [ ] 阶段 7：真机验收 ← 等用户").replace("| 阶段 3 |", "| 阶段 7 |")
        self.assertEqual(kinds(sw.reconcile_workbook(merged, now=NOW)), [("dependency_done", "nudge")])

        external = RECONCILED_WORKBOOK.replace("排在 阶段 4 后：用窗口切换后的新版本", "排在 上游 MR 合入后：用合入后的版本")
        self.assertTrue(sw.reconcile_workbook(external, now=NOW)["ok"])

    def test_bb_queue_and_status_fields_map_to_liveness(self):
        tid = "thr_aaaaaa1111"
        waiting = sw.normalize_thread({"id": tid, "status": "idle", "queuedWork": "waiting", "updatedAt": 0})
        failed = sw.normalize_thread({"id": tid, "status": "error", "queuedWork": "failed", "updatedAt": 0})
        self.assertTrue(waiting["queued"])
        self.assertFalse(failed["queued"])
        self.assertEqual(sw.thread_state(failed, NOW.timestamp(), 1800), "failed")
        for status in ("pending", "starting", "stopping"):
            self.assertEqual(sw.thread_state(thread(tid, status=status), NOW.timestamp(), 1800), "alive", status)

    def test_todo_reason_needs_a_category_and_only_blocking_ones_fail(self):
        blocking = RECONCILED_WORKBOOK.replace("真机线下：只有用户有设备", "只有用户有设备")
        self.assertIn(("todo_category_missing", "nudge"), kinds(sw.reconcile_workbook(blocking, now=NOW)))
        idle = RECONCILED_WORKBOOK.replace("凭据账号：令牌归用户", "令牌归用户")
        res = sw.reconcile_workbook(idle, now=NOW)
        self.assertTrue(res["ok"])
        self.assertEqual(kinds(res), [("todo_category_missing", "minor")])

    def test_live_check_flags_running_rows_whose_threads_stopped(self):
        tid = "thr_aaaaaa1111"
        alive_cases = [
            thread(tid, status="active"),
            thread(tid, queued=True),
            thread(tid, background=True),
            thread(tid, idle_minutes=10),
        ]
        for info in alive_cases:
            res = sw.reconcile_workbook(RECONCILED_WORKBOOK, now=NOW, threads={tid: info})
            self.assertTrue(res["ok"], (info, res["problems"]))

        stopped_cases = {
            "已空闲": thread(tid, idle_minutes=120),
            "失败": thread(tid, status="error"),
            "已归档": thread(tid, archived=True),
            "找不到": None,
        }
        for word, info in stopped_cases.items():
            res = sw.reconcile_workbook(RECONCILED_WORKBOOK, now=NOW, threads={} if info is None else {tid: info})
            self.assertEqual(kinds(res), [("stale_running", "nudge")])
            self.assertIn(word, res["problems"][0]["detail"])

        waiting = sw.reconcile_workbook(RECONCILED_WORKBOOK, now=NOW, threads={tid: thread(tid, interaction=True)})
        self.assertEqual(kinds(waiting), [("child_waiting", "nudge")])

        lenient = sw.reconcile_workbook(RECONCILED_WORKBOOK, now=NOW, threads={tid: thread(tid)}, unlisted_alive=1)
        self.assertTrue(lenient["ok"])
        self.assertEqual(kinds(lenient), [("stale_running", "minor")])


if __name__ == "__main__":
    unittest.main()
