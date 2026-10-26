"""验证 BB 管家看门狗：催办节流与升级、失败重试与恢复、登记与 automation、事件日志与复盘。"""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
from typing import Any
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import steward_watch as watch

NOW = 1793000000.0
HOUR = 3600
TID = "thr_steward001"

GOOD = """# 目标

更新：2026-10-26

## 路线

- [ ] 阶段 1：布局整理 ← 等用户

## 关键决策

- 无

## 用户待办

| 状态 | 事项 | 为什么只能用户做 | 挡住 | 提出 |
| --- | --- | --- | --- | --- |
| 待办 | 真机验收 | 真机线下：只有用户有设备 | 阶段 1 | 2026-10-26 |
"""
BROKEN = GOOD.replace("- [ ] 阶段 1：布局整理 ← 等用户", "- [ ] 阶段 1：布局整理 ← 等用户\n- [ ] 阶段 2：远景规划")


class FakeBb:
    def __init__(self):
        self.infos = {}
        self.kids = {}
        self.tells = []
        self.retries = []
        self.fail_tell = False
        self.automations = {}
        self.created = []
        self.updated = []

    def set(self, tid=TID, status="idle", idle=2 * HOUR, now=NOW, **flags):
        info = {"id": tid, "status": status, "archived": False, "queued": False, "interaction": False,
                "background": False, "updated_at": now - idle, "parent": None}
        info.update(flags)
        self.infos[tid] = info

    def threads(self, ids):
        return {i: self.infos[i] for i in ids if i in self.infos}

    def children(self, parent):
        return self.kids.get(parent, [])

    def tell(self, thread, message):
        if self.fail_tell:
            raise watch.WatchError("发送失败")
        self.tells.append((thread, message))

    def retry(self, thread, reason):
        self.retries.append(thread)

    def automation_show(self, automation_id, project):
        return self.automations.get(automation_id)

    def automation_create(self, project, script):
        aid = f"auto_{len(self.created) + 1}"
        self.automations[aid] = {"execution": {"script": script}}
        self.created.append((project, script))
        return {"id": aid}

    def automation_update_script(self, automation_id, project, script):
        self.automations[automation_id]["execution"]["script"] = script
        self.updated.append(automation_id)


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.state_path = self.dir / "watch.json"
        self.workbook = self.dir / "workbook.md"
        self.workbook.write_text(BROKEN)
        self.bb = FakeBb()
        self.bb.set()
        self.state = watch.empty_state()
        self.state["stewards"][TID] = {"name": "A", "workbook": str(self.workbook)}

    def tearDown(self):
        self.tmp.cleanup()

    def tick(self, now, dry_run=False):
        results, _ = watch.run(self.state, self.state_path, self.bb, now=now, dry_run=dry_run)
        return results.get(TID, {})

    def report(self, now):
        return watch.report(watch.load_state(self.state_path), watch.read_events(self.state_path), now, 6 * 60)

    def test_nudges_once_then_waits_then_escalates_to_user(self):
        self.assertEqual(self.tick(NOW)["result"], "nudged")
        self.assertEqual(len(self.bb.tells), 1)
        thread, message = self.bb.tells[0]
        self.assertEqual(thread, TID)
        self.assertIn("阶段 2", message)
        self.assertIn("缺状态", message)
        self.assertIn("等用户", message)

        self.assertEqual(self.tick(NOW + HOUR)["result"], "problems")
        self.assertEqual(len(self.bb.tells), 1)

        self.assertEqual(self.tick(NOW + 2 * HOUR + 60)["result"], "nudged")
        self.assertEqual(len(self.bb.tells), 2)

        self.tick(NOW + 5 * HOUR)
        self.assertEqual(len(self.bb.tells), 2)
        text = self.report(NOW + 5 * HOUR)
        self.assertIn("需要用户看一眼", text)
        self.assertIn("「阶段 2」（no_state）已催 2 次仍未处理", text)

    def test_resolved_problem_records_outcome_and_resets_count(self):
        self.tick(NOW)
        self.workbook.write_text(GOOD)
        self.assertEqual(self.tick(NOW + HOUR)["result"], "ok")
        outcomes = [e for e in watch.read_events(self.state_path) if e["event"] == "nudge_outcome"]
        self.assertEqual(outcomes[-1]["resolved"], 1)
        self.assertEqual(self.state["stewards"][TID]["problems"], {})

        self.workbook.write_text(BROKEN)
        self.assertEqual(self.tick(NOW + 3 * HOUR)["result"], "nudged")
        self.assertEqual(self.state["stewards"][TID]["problems"]["no_state|阶段 2"]["count"], 1)

    def test_busy_or_just_finished_steward_is_left_alone(self):
        busy_cases: list[dict[str, Any]] = [
            {"status": "active"}, {"status": "starting"}, {"status": "stopping"}, {"status": "pending"},
            {"queued": True}, {"interaction": True}, {"background": True},
        ]
        for flags in busy_cases:
            self.bb.set(**flags)
            self.assertEqual(self.tick(NOW)["result"], "busy", flags)
        self.bb.set(idle=5 * 60)
        self.assertEqual(self.tick(NOW)["result"], "settling")
        self.assertEqual(self.bb.tells, [])
        self.assertEqual(self.bb.retries, [])

    def test_restarting_steward_keeps_its_outage_until_it_settles(self):
        self.workbook.write_text(GOOD)
        self.bb.set(status="error", idle=5 * 60)
        self.tick(NOW)
        self.bb.set(status="starting", idle=60, now=NOW + 5 * 60)
        self.assertEqual(self.tick(NOW + 5 * 60)["result"], "busy")
        self.assertIn("outage", self.state["stewards"][TID])
        self.assertEqual(self.bb.tells, [])

    def test_failed_turn_retries_with_backoff_escalates_and_announces_recovery(self):
        self.workbook.write_text(GOOD)
        self.bb.set(status="error", idle=5 * 60)
        self.assertEqual(self.tick(NOW)["result"], "failed")
        self.assertEqual(self.bb.retries, [TID])
        self.tick(NOW + 10 * 60)
        self.assertEqual(len(self.bb.retries), 1)
        self.tick(NOW + 31 * 60)
        self.assertEqual(len(self.bb.retries), 2)
        res = self.tick(NOW + 70 * 60)
        self.assertEqual(len(self.bb.retries), 2)
        self.assertIn("需要用户看一眼", res["report"])
        self.assertIn("回合失败已", self.report(NOW + 70 * 60))

        self.bb.set(status="idle", idle=60, now=NOW + 80 * 60)
        res = watch.run(self.state, self.state_path, self.bb, now=NOW + 80 * 60)[0][TID]
        self.assertEqual(res["result"], "recovered")
        self.assertIn("连续失败", self.bb.tells[-1][1])
        self.assertNotIn("outage", self.state["stewards"][TID])
        self.assertEqual(self.tick(NOW + 3 * HOUR)["result"], "ok")
        self.assertEqual(len(self.bb.tells), 1)

    def test_archived_or_deleted_steward_is_unregistered(self):
        self.bb.set(archived=True)
        self.assertEqual(self.tick(NOW)["result"], "unregistered")
        self.assertNotIn(TID, self.state["stewards"])
        self.state["stewards"]["thr_gone000001"] = {"name": "X", "workbook": str(self.workbook)}
        results, _ = watch.run(self.state, self.state_path, self.bb, now=NOW)
        self.assertEqual(results["thr_gone000001"]["result"], "unregistered")
        self.assertEqual(self.state["stewards"], {})

    def test_unreadable_workbook_is_reported_to_the_steward(self):
        self.workbook.unlink()
        self.assertEqual(self.tick(NOW)["result"], "nudged")
        self.assertIn("读不到工作簿", self.bb.tells[0][1])

    def test_dry_run_sends_nothing_and_writes_nothing(self):
        self.assertEqual(self.tick(NOW, dry_run=True)["result"], "nudged")
        self.assertEqual(self.bb.tells, [])
        self.assertFalse(self.state_path.exists())

    def test_exhausted_problem_is_not_resent_with_new_problems(self):
        self.tick(NOW)
        self.tick(NOW + 2 * HOUR + 60)
        self.assertEqual(len(self.bb.tells), 2)
        self.workbook.write_text(BROKEN.replace("- [ ] 阶段 2：远景规划", "- [ ] 阶段 2：远景规划\n- [ ] 阶段 3：补文档"))
        self.assertEqual(self.tick(NOW + 5 * HOUR)["result"], "nudged")
        message = self.bb.tells[-1][1]
        self.assertIn("阶段 3", message)
        self.assertNotIn("「阶段 2」", message)
        self.assertEqual(self.state["stewards"][TID]["problems"]["no_state|阶段 2"]["count"], 2)

    def test_only_shown_problems_use_up_their_nudges(self):
        rows = "\n".join(f"- [ ] 阶段 {i}：事项{i}" for i in range(2, 12))
        self.workbook.write_text(GOOD.replace("- [ ] 阶段 1：布局整理 ← 等用户", "- [ ] 阶段 1：布局整理 ← 等用户\n" + rows))
        self.tick(NOW)
        message = self.bb.tells[0][1]
        self.assertIn("另有 2 处", message)
        counts = {k: v["count"] for k, v in self.state["stewards"][TID]["problems"].items()}
        self.assertEqual(sorted(counts.values()), [0, 0] + [1] * watch.MESSAGE_MAX_PROBLEMS)
        self.assertEqual(self.state["stewards"][TID]["pending_nudge"]["keys"],
                         [k for k, v in self.state["stewards"][TID]["problems"].items() if v["count"] == 1])

    def test_failed_send_is_not_repeated_on_the_next_tick(self):
        self.bb.fail_tell = True
        res = self.tick(NOW)
        self.assertIn("发送失败", res["report"])
        self.bb.fail_tell = False
        self.assertEqual(self.tick(NOW + 30 * 60)["result"], "problems")
        self.assertEqual(self.bb.tells, [])

    def test_remote_workbook_stale_thread_is_minor_while_other_children_run(self):
        repo = self.dir / "repo"
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        wb = repo / "docs" / "wb.md"
        wb.parent.mkdir(parents=True)
        wb.write_text(GOOD.replace("← 等用户", "← 进行中 thr_oldchild01"))
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "wb"], check=True)
        subprocess.run(["git", "-C", str(repo), "update-ref", "refs/remotes/origin/main", "HEAD"], check=True)
        self.state["stewards"] = {}
        watch.register(self.state, self.bb, TID, str(wb), ref="origin/main", name="A", now=NOW)
        self.bb.set("thr_oldchild01", idle=3 * HOUR)
        self.bb.kids[TID] = [dict(self.bb.infos["thr_oldchild01"]), {**self.bb.infos[TID], "id": "thr_newchild01", "status": "active"}]
        self.assertEqual(self.tick(NOW)["result"], "ok")
        self.bb.kids[TID] = []
        self.assertEqual(self.tick(NOW + 3 * HOUR)["result"], "nudged")
        self.assertIn("thr_oldchild01 已空闲", self.bb.tells[0][1])

    def test_register_from_a_worktree_reads_through_the_main_checkout(self):
        repo = self.dir / "repo"
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / "README").write_text("x")
        git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(git + ["add", "."], check=True)
        subprocess.run(git + ["commit", "-qm", "init"], check=True)
        tree = self.dir / "tree"
        subprocess.run(git + ["worktree", "add", "-q", "-b", "env", str(tree)], check=True)
        (tree / "docs").mkdir()
        (tree / "docs" / "wb.md").write_text(GOOD)
        subprocess.run(["git", "-C", str(tree), "add", "."], check=True)
        subprocess.run(["git", "-C", str(tree), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "wb"], check=True)
        subprocess.run(git + ["update-ref", "refs/remotes/origin/env", "env"], check=True)
        res = watch.register(self.state, self.bb, TID, str(tree / "docs" / "wb.md"), ref="origin/env", manage_automation=False)
        self.assertEqual(Path(res["repo"]).resolve(), repo.resolve())
        subprocess.run(git + ["worktree", "remove", "--force", str(tree)], check=True)
        self.assertIn("阶段 1", watch.read_workbook(self.state["stewards"][TID]))

    def test_register_creates_automation_once_and_follows_script_moves(self):
        state = watch.empty_state()
        res = watch.register(state, self.bb, TID, str(self.workbook), project="proj_x",
                             script_path=Path("/a/steward_watch.py"), state_path=Path("/s/watch.json"))
        self.assertEqual(res["automation"]["status"], "created")
        self.assertEqual(self.bb.created, [("proj_x", "exec python3 /a/steward_watch.py --state /s/watch.json run")])
        res = watch.register(state, self.bb, "thr_other0001", str(self.workbook), project="proj_y",
                             script_path=Path("/a/steward_watch.py"), state_path=Path("/s/watch.json"))
        self.assertEqual(res["automation"]["status"], "exists")
        res = watch.register(state, self.bb, TID, str(self.workbook), script_path=Path("/b/steward_watch.py"),
                             state_path=Path("/s/watch.json"))
        self.assertEqual(res["automation"]["status"], "updated")
        self.assertEqual(len(self.bb.created), 1)
        self.assertEqual(set(state["stewards"]), {TID, "thr_other0001"})

    def test_register_keeps_runtime_state_and_rejects_missing_workbook(self):
        self.tick(NOW)
        before = dict(self.state["stewards"][TID]["problems"])
        watch.register(self.state, self.bb, TID, str(self.workbook), name="A2", manage_automation=False)
        self.assertEqual(self.state["stewards"][TID]["problems"], before)
        self.assertEqual(self.state["stewards"][TID]["name"], "A2")
        with self.assertRaises(watch.WatchError):
            watch.register(self.state, self.bb, TID, str(self.dir / "missing.md"), manage_automation=False)

    def test_event_log_keeps_newest_half_when_over_cap(self):
        with mock.patch.object(watch, "EVENTS_MAX_BYTES", 2000):
            for i in range(100):
                watch.append_events(self.state_path, [watch.event(NOW + i, TID, "check", result="ok", i=i)])
        events = watch.read_events(self.state_path)
        self.assertLess(len(events), 100)
        self.assertEqual(events[-1]["i"], 99)

    def test_summary_flags_ignored_nudges_and_frequent_outages(self):
        events = []
        for i in range(3):
            events.append(watch.event(NOW + i, TID, "nudge", count=1))
            events.append(watch.event(NOW + i, TID, "nudge_outcome", resolved=0, persisted=1))
            events.append(watch.event(NOW + i, TID, "outage"))
            events.append(watch.event(NOW + i, TID, "recovered", minutes=20))
        res = watch.summary(self.state, events, NOW + 10, days=7)
        self.assertEqual(res["stewards"][TID]["nudges"], 3)
        self.assertEqual(res["stewards"][TID]["resolve_share"], 0.0)
        self.assertEqual({h["hook"] for h in res["hooks"]}, {"nudge_ignored", "frequent_outage"})
        old = watch.summary(self.state, events, NOW + 8 * 86400, days=7)
        self.assertEqual(old["stewards"], {})


class CliTests(unittest.TestCase):
    def test_run_is_silent_when_nothing_to_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "watch.json"
            state.write_text(json.dumps(watch.empty_state()))
            out = subprocess.run([sys.executable, str(SCRIPTS / "steward_watch.py"), "--state", str(state), "run"],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertEqual(out.stdout, "")

    def test_run_reports_storage_failure_without_failing_the_automation(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "not-a-dir"
            blocker.write_text("x")
            out = subprocess.run([sys.executable, str(SCRIPTS / "steward_watch.py"), "--state", str(blocker / "watch.json"), "run"],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("看门狗未完成", out.stdout)


if __name__ == "__main__":
    unittest.main()
