"""验证 BB 管家看门狗：催办节流与升级、失败重试与恢复、登记与 automation、事件日志与复盘。"""
from pathlib import Path
import json
import contextlib
import io
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
        self.reparents = []
        self.cancelled = []
        self.logs = []
        self.log_calls = []
        self.plugin_calls = []

    def steward(self, command, **values):
        self.plugin_calls.append((command, values))
        return {}

    def set(self, tid=TID, status="idle", idle=2 * HOUR, now=NOW, **flags):
        info = {"id": tid, "status": status, "archived": False, "queued": False, "interaction": False,
                "background": False, "updated_at": now - idle, "parent": None}
        info.update(flags)
        self.infos[tid] = info

    def threads(self, ids):
        return {i: self.infos[i] for i in ids if i in self.infos}

    def children(self, parent, include_hidden=False):
        return self.kids.get(parent, [])

    def tell(self, thread, message):
        if self.fail_tell:
            raise watch.WatchError("发送失败")
        self.tells.append((thread, message))

    def log(self, thread, after):
        self.log_calls.append(after)
        return [r for r in self.logs if r["seq"] > after][:10000]

    def reparent(self, thread, parent=None):
        self.reparents.append((thread, parent))

    def cancel_retry(self, thread):
        self.cancelled.append(thread)

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
        subprocess.run(["git", "-C", str(repo), "branch", "main"], check=True)
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(repo)], check=True)
        self.state["stewards"] = {}
        watch.register(self.state, self.bb, TID, str(wb), ref="origin/main", name="A", now=NOW, state_path=self.state_path)
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
        subprocess.run(git + ["remote", "add", "origin", str(repo)], check=True)
        res = watch.register(self.state, self.bb, TID, str(tree / "docs" / "wb.md"), ref="origin/env", manage_automation=False, state_path=self.state_path)
        self.assertEqual(Path(res["repo"]).resolve(), repo.resolve())
        self.bb.set("thr_new00001")
        takeover = watch.register(self.state, self.bb, "thr_new00001", str(repo / "docs" / "wb.md"),
                                  state_path=self.state_path, manage_automation=False, ref="origin/env")
        self.assertEqual(takeover["ref"], "origin/env")
        self.assertEqual(takeover["name"], res["name"])
        self.assertNotIn(TID, self.state["stewards"])
        self.assertEqual(takeover["handovers"][0]["old"], TID)
        subprocess.run(git + ["worktree", "remove", "--force", str(tree)], check=True)
        self.assertIn("阶段 1", watch.read_workbook(self.state["stewards"]["thr_new00001"]))

    def test_register_creates_automation_once_and_follows_script_moves(self):
        state = watch.empty_state()
        res = watch.register(state, self.bb, TID, str(self.workbook), project="proj_x",
                             script_path=Path("/a/steward_watch.py"), state_path=self.state_path)
        self.assertEqual(res["automation"]["status"], "created")
        self.assertEqual(self.bb.created, [("proj_x", f"exec python3 /a/steward_watch.py --state {self.state_path} run")])
        res = watch.register(state, self.bb, "thr_other0001", str(self.workbook), project="proj_y",
                             script_path=Path("/a/steward_watch.py"), state_path=self.state_path)
        self.assertEqual(res["automation"]["status"], "exists")
        res = watch.register(state, self.bb, TID, str(self.workbook), script_path=Path("/b/steward_watch.py"),
                             state_path=self.state_path)
        self.assertEqual(res["automation"]["status"], "updated")
        self.assertEqual(len(self.bb.created), 1)
        self.assertEqual(set(state["stewards"]), {TID})

    def test_register_keeps_runtime_state_and_rejects_missing_workbook(self):
        self.tick(NOW)
        before = dict(self.state["stewards"][TID]["problems"])
        watch.register(self.state, self.bb, TID, str(self.workbook), name="A2", manage_automation=False, state_path=self.state_path)
        self.assertEqual(self.state["stewards"][TID]["problems"], before)
        self.assertEqual(self.state["stewards"][TID]["name"], "A2")
        with self.assertRaises(watch.WatchError):
            watch.register(self.state, self.bb, TID, str(self.dir / "missing.md"), manage_automation=False, state_path=self.state_path)

    def test_handover_lists_hidden_children_without_changing_reconciliation_lookup(self):
        bb = watch.Bb()
        with mock.patch.object(watch.sw, "bb_thread_list", return_value=[]) as listed:
            bb.children(TID)
            listed.assert_called_with("--parent-thread", TID)
            bb.children(TID, include_hidden=True)
            listed.assert_called_with("--parent-thread", TID, "--include-hidden")
        self.bb.children = mock.Mock(return_value=[])
        watch.register(self.state, self.bb, "thr_new00001", str(self.workbook),
                       state_path=self.state_path, manage_automation=False)
        self.bb.children.assert_called_once_with(TID, include_hidden=True)

    def test_handover_persists_first_filters_children_and_notifies(self):
        old, new = TID, "thr_new00001"
        self.workbook.write_text(GOOD.replace("← 等用户", "← 进行中 thr_failed0001"))
        watch.register(self.state, self.bb, old, str(self.workbook), name="原名", manage_automation=False, state_path=self.state_path)
        self.bb.set(new, parent=old)
        flags = [("thr_alive0001", {"status": "active"}), ("thr_recent001", {"idle": 60}),
                 ("thr_failed0001", {"status": "error"}), ("thr_stopped001", {}),
                 ("thr_archived01", {"status": "active", "archived": True}),
                 ("thr_interact01", {"interaction": True})]
        for tid, kwargs in flags:
            self.bb.set(tid, **kwargs)
        self.bb.kids[old] = [self.bb.infos[tid] for tid, _ in flags] + [self.bb.infos[new]]
        real_reparent = self.bb.reparent
        def reparent(tid, parent=None):
            saved = watch.load_state(self.state_path)
            self.assertEqual(set(saved["stewards"]), {new})
            real_reparent(tid, parent)
            if tid == "thr_alive0001":
                raise watch.WatchError("转移失败")
        self.bb.reparent = reparent
        res = watch.register(self.state, self.bb, new, str(self.workbook), now=NOW,
                             state_path=self.state_path, manage_automation=False)
        self.assertEqual(res["name"], "原名")
        self.assertEqual(self.bb.reparents, [(new, None), ("thr_alive0001", new),
                                             ("thr_recent001", new), ("thr_failed0001", new)])
        self.assertEqual(self.bb.cancelled, [old])
        self.assertIn("[bb-steward 交接]", self.bb.tells[-1][1])
        self.assertIn("@thread:" + new, self.bb.tells[-1][1])
        self.assertFalse(next(step for step in res["handovers"][0]["steps"] if step["step"] == "reparent:thr_alive0001")["ok"])
        evs = watch.read_events(self.state_path)
        self.assertEqual(evs[-1]["event"], "handover")
        self.assertIn("接任", watch.report(self.state, evs, NOW, 10))
        self.assertEqual(watch.summary(self.state, evs, NOW, 7)["stewards"][new]["handovers"], 1)
        self.bb.reparents.clear()
        self.bb.cancelled.clear()
        self.bb.tells.clear()
        res = watch.register(self.state, self.bb, new, str(self.workbook), state_path=self.state_path, manage_automation=False)
        self.assertEqual(res["handovers"], [])
        self.assertEqual((self.bb.reparents, self.bb.cancelled, self.bb.tells), ([], [], []))

    def test_handover_failures_do_not_block_other_steps_and_archived_is_not_notified(self):
        self.bb.set(archived=True)
        self.bb.set("thr_new00001")
        self.bb.children = mock.Mock(side_effect=watch.WatchError("children down"))
        self.bb.cancel_retry = mock.Mock(side_effect=watch.WatchError("cancel down"))
        res = watch.register(self.state, self.bb, "thr_new00001", str(self.workbook), state_path=self.state_path, manage_automation=False)
        self.assertEqual(set(self.state["stewards"]), {"thr_new00001"})
        self.bb.cancel_retry.assert_called_once_with(TID)
        self.assertFalse(any(step["step"] == "notify" for step in res["handovers"][0]["steps"]))
        self.assertEqual(self.bb.tells, [])

    def test_model_baselines_changes_returns_dedup_and_busy_observation(self):
        self.bb.set(status="active")
        def requested(seq, model="opus", reasoning="high"):
            return {"seq": seq, "type": "client/turn/requested", "data": {"execution": {"model": model, "reasoningLevel": reasoning}}}
        self.bb.logs = [requested(1), {"seq": 2, "type": "thread/identity", "data": {"providerThreadId": "session"}}]
        with mock.patch.object(watch, "claude_model", return_value="opus") as reader:
            self.tick(NOW)
            self.assertEqual(self.bb.tells, [])
            self.assertEqual(self.state["stewards"][TID]["model_observation"]["seq"], 2)
            self.bb.logs.append(requested(3, reasoning="low"))
            reader.return_value = "older-opus"
            self.tick(NOW + 60)
            self.assertEqual(len(self.bb.tells), 2)
            self.assertTrue(all("本回合回复里告诉用户" in msg for _, msg in self.bb.tells))
            self.bb.logs.append(requested(4))
            reader.return_value = "opus"
            self.tick(NOW + 120)
            self.bb.logs.append(requested(5, reasoning="low"))
            reader.return_value = "older-opus"
            self.tick(NOW + 180)
            self.assertEqual(len(self.bb.tells), 2)
            self.assertEqual(self.bb.log_calls, [0, 2, 3, 4])
        changes = [e for e in watch.read_events(self.state_path) if e["event"] == "model_change"]
        self.assertEqual(len(changes), 6)
        self.assertEqual(sum(e["returned"] for e in changes), 2)
        self.assertIn("模型变化", self.report(NOW + 180))
        self.assertEqual(watch.summary(self.state, changes, NOW + 180, 7)["stewards"][TID]["model_changes"], 6)

    def test_model_errors_warn_but_allow_reconcile(self):
        self.bb.log = mock.Mock(side_effect=watch.WatchError("unreadable"))
        self.assertEqual(self.tick(NOW)["result"], "nudged")
        self.assertTrue(any(e["event"] == "warning" for e in watch.read_events(self.state_path)))

    def test_actual_model_still_read_when_bb_log_is_unavailable(self):
        self.bb.log = mock.Mock(side_effect=watch.WatchError("unreadable"))
        with mock.patch.object(watch, "claude_model", return_value="actual") as reader:
            observed, values, warnings = watch.read_models(self.bb, TID, {"seq": 5, "providerThreadId": "session"})
        reader.assert_called_once_with("session")
        self.assertEqual(values["actual"], "actual")
        self.assertEqual(observed["seq"], 5)
        self.assertTrue(warnings)

    def test_handover_unreadable_workbook_does_not_block_cancel_and_notification(self):
        self.workbook.unlink()
        res = watch.register(self.state, self.bb, "thr_new00001", str(self.workbook), state_path=self.state_path, manage_automation=False)
        steps = {step["step"]: step for step in res["handovers"][0]["steps"]}
        self.assertFalse(steps["workbook"]["ok"])
        self.assertTrue(steps["cancel_retry"]["ok"])
        self.assertTrue(steps["notify"]["ok"])

    def test_model_scan_pages_and_claude_tail_ignores_synthetic(self):
        self.bb.logs = [{"seq": i, "type": "ignored"} for i in range(1, 20002)]
        self.bb.logs[-1].update(type="client/turn/requested", data={"execution": {"model": "opus"}})
        with mock.patch.object(watch, "claude_model", side_effect=watch.WatchError("not Claude")):
            observed, values, warnings = watch.read_models(self.bb, TID, {})
        self.assertEqual(self.bb.log_calls, [0, 10000, 20000])
        self.assertEqual(observed["seq"], 20001)
        self.assertEqual(values["requested"]["model"], "opus")
        self.assertTrue(warnings)
        root = self.dir / "claude"
        path = root / "projects" / "project" / "session.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"type": "assistant", "message": {"model": "old"}}) + "\n" +
                        json.dumps({"type": "assistant", "message": {"model": "real", "content": "长" * 70000}}) + "\n" +
                        json.dumps({"type": "assistant", "message": {"model": "<synthetic>"}}) + "\n{partial")
        with mock.patch.dict("os.environ", {"CLAUDE_CONFIG_DIR": str(root)}):
            self.assertEqual(watch.claude_model("session"), "real")

    def test_non_claude_steward_skips_session_lookup_and_change_message_is_readable(self):
        self.bb.set(status="active", provider="pi")
        def requested(seq, reasoning):
            return {"seq": seq, "type": "client/turn/requested", "data": {"execution": {"model": "opus", "reasoningLevel": reasoning}}}
        self.bb.logs = [requested(1, "high")]
        with mock.patch.object(watch, "claude_model") as reader:
            self.tick(NOW)
            self.bb.logs.append(requested(2, "low"))
            self.tick(NOW + 60)
        reader.assert_not_called()
        self.assertFalse(any(e["event"] == "warning" for e in watch.read_events(self.state_path)))
        self.assertEqual(len(self.bb.tells), 1)
        self.assertIn("opus（high） 变为 opus（low）", self.bb.tells[0][1])
        self.assertIn("新开线程接任", self.bb.tells[0][1])

    def test_cancel_retry_without_pending_retry_counts_as_done(self):
        bb = watch.Bb()
        with mock.patch.object(bb, "_run", side_effect=watch.WatchError('bb provider-retry 失败：{"code": "no_pending_retry"}')):
            bb.cancel_retry(TID)
        with mock.patch.object(bb, "_run", side_effect=watch.WatchError("bb provider-retry 失败：plugin missing")):
            with self.assertRaises(watch.WatchError):
                bb.cancel_retry(TID)

    def test_user_relay_for_second_nudge_and_escalated_recovery(self):
        self.tick(NOW)
        self.tick(NOW + 2 * HOUR)
        self.assertIn("本回合回复里告诉用户", self.bb.tells[-1][1])
        self.assertIn("催满 2 次", self.bb.tells[-1][1])
        self.workbook.write_text(GOOD)
        self.bb.set(status="error", idle=2 * HOUR)
        self.tick(NOW + 3 * HOUR)
        self.bb.set()
        self.tick(NOW + 4 * HOUR)
        self.assertIn("本回合回复里告诉用户", self.bb.tells[-1][1])
        self.assertNotIn("告诉用户", watch.recovery_message({"since": NOW, "retries": 1}))

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


class PluginSyncTests(unittest.TestCase):
    def test_register_reads_actual_header_link_and_skips_unavailable_plugin(self):
        with tempfile.TemporaryDirectory() as temp:
            workbook = Path(temp) / "workbook.md"
            workbook.write_text("# 目标\n\n[要求帳](different%20ledger.md)\n\n## 路线\n")
            entry = {"workbook": str(workbook), "name": "目标"}
            bb = FakeBb()
            self.assertEqual(watch.sync_plugin(bb, "register", TID, entry)["status"], "registered")
            self.assertEqual(bb.plugin_calls[0][1]["ledger"], str(Path(temp) / "different ledger.md"))
            with mock.patch.object(bb, "steward", side_effect=watch.WatchError("not installed")):
                self.assertEqual(watch.sync_plugin(bb, "register", TID, entry)["status"], "skipped")
            self.assertEqual(watch.sync_plugin(bb, "unregister", TID)["status"], "unregistered")

    def test_failed_unregister_survives_reload_and_retries_without_a_steward(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "watch.json"
            state = watch.empty_state()
            bb = FakeBb()
            watch.save_state(path, state)
            with mock.patch.object(bb, "steward", side_effect=watch.WatchError("unavailable")), mock.patch.object(watch, "Bb", return_value=bb), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(watch.main(["--state", str(path), "unregister", "--thread", TID]), 0)
                self.assertEqual(json.loads(output.getvalue())["plugin"]["status"], "skipped")
            state = watch.load_state(path)
            self.assertEqual(state["pending_plugin_unregistrations"], [TID])
            watch.run(state, path, bb, now=NOW, dry_run=True)
            self.assertEqual(bb.plugin_calls, [])
            watch.run(state, path, bb, now=NOW)
            self.assertEqual(watch.load_state(path)["pending_plugin_unregistrations"], [])
            self.assertEqual(bb.plugin_calls, [("unregister", {"thread": TID})])

    def test_pending_cleanup_rotates_failures_instead_of_starving_later_threads(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "watch.json"
            state = watch.empty_state()
            blocked = [f"blocked-{i:02d}" for i in range(20)]
            state["pending_plugin_unregistrations"] = [*blocked, "ready"]
            bb = FakeBb()
            real_steward = bb.steward
            def steward(command, **values):
                if values["thread"] in blocked:
                    raise watch.WatchError("unavailable")
                return real_steward(command, **values)
            bb.steward = steward
            watch.run(state, path, bb, now=NOW)
            watch.run(state, path, bb, now=NOW)
            self.assertEqual(bb.plugin_calls, [("unregister", {"thread": "ready"})])
            self.assertNotIn("ready", state["pending_plugin_unregistrations"])

    def test_git_ref_reregistration_and_reload_keep_source_binding_and_cancel_pending_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / 'repo'
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            git = ['git', '-C', str(repo)]
            subprocess.run(git + ['config', 'user.name', 'Test'], check=True)
            subprocess.run(git + ['config', 'user.email', 'test@example.invalid'], check=True)
            workbook = repo / 'workbook.md'
            workbook.write_text(GOOD.replace('更新：2026-10-26', '[要求帐（历史流水账）](history.md)'))
            (repo / 'history.md').write_text('# 历史流水账')
            subprocess.run(git + ['add', '.'], check=True)
            subprocess.run(git + ['commit', '-qm', 'initial'], check=True)
            subprocess.run(git + ['branch', '-M', 'main'], check=True)
            subprocess.run(git + ['remote', 'add', 'origin', str(repo)], check=True)
            path = Path(temp) / 'watch.json'
            state = watch.empty_state()
            state['pending_plugin_unregistrations'] = [TID]
            bb = FakeBb()
            result = watch.register(state, bb, TID, str(workbook), ref='origin/main', state_path=path, manage_automation=False)
            self.assertEqual(result['plugin']['status'], 'registered')
            watch.save_state(path, state)
            state = watch.load_state(path)
            watch.retry_plugin_unregistrations(state, bb, path)
            result = watch.register(state, bb, TID, str(workbook), state_path=path, manage_automation=False)
            self.assertEqual(result['ref'], 'origin/main')
            self.assertEqual([cmd for cmd, _ in bb.plugin_calls], ['register', 'register'])
            self.assertEqual(bb.plugin_calls[-1][1]['workbook'], 'workbook.md')
            self.assertEqual(bb.plugin_calls[-1][1]['repo'], str(repo))
            self.assertEqual(bb.plugin_calls[-1][1]['ledger_kind'], 'history')
            self.assertEqual(state['pending_plugin_unregistrations'], [])
            other = watch.register(state, bb, 'other', str(workbook), state_path=path, manage_automation=False)
            self.assertEqual(other['handovers'], [])
            self.assertIn(TID, state['stewards'])


if __name__ == "__main__":
    unittest.main()
