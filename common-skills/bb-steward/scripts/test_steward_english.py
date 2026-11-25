"""English canonical vocabulary end to end, plus mixed-language files and legacy compatibility points."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import steward_source as source
import steward_watch as watch
import steward_workbook as sw
from workbook_timeline import format_timeline

NOW = datetime(2026, 10, 26, 18, 0)
STAMP_NOW = datetime(2026, 11, 15, 4, 30, 45, tzinfo=timezone.utc)
LEDGER = (Path(__file__).parent / "fixtures" / "requirements.md").read_text()

EN_WORKBOOK = """# Carry maintenance lessons into the new repository

Updated: 2026-10-26; per-item status, results and material in [Requirements ledger](topic-requirements.md).

## Route

- [x] Stage 1: inventory the repository
- [ ] Stage 2: layout cleanup ← in progress thr_aaaaaa1111
- [ ] Stage 3: device acceptance ← waiting on user
- [ ] Stage 4: primary cutover window ← scheduled 10-26 22:10 open the window
- [ ] Stage 5: publish the image ← after Stage 4: the version built after the cutover

## Key decisions

- 2026-10-26 Environment names are only test/prod. Reason: avoid clashes. Impact: deployment.

## User to-dos

| ID | Status | Item | Background | Recommendation | Why only the user | Blocks | Raised | Done |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | open | Accept on the iPad | Only the user has the device | Do it tonight | physical device: only the user has it | Stage 3 | 2026-10-26 | — |
| D2 | open | Rotate the token | The token belongs to the user | Rotate now | credentials: the user owns the token | not blocking | 2026-10-26 | — |
"""


def ledger_row(status="Done", result="CI 21→8 min (-62%)", material="PR #117"):
    return ("# User requirement ledger\n\n## 2026-10-27 onward (Efficiency)\n\n"
            "| Date | Requirement | Status | Result | Material |\n"
            "| --- | --- | --- | --- | --- |\n"
            f"| 10-27 | Optimize CI | {status} | {result} | {material} |\n")


def kinds(result):
    return [(p["kind"], p["severity"]) for p in result["problems"]]


class EnglishCheckTests(unittest.TestCase):
    def test_english_workbook_and_ledger_entry_pass(self):
        res = sw.check_workbook(EN_WORKBOOK)
        self.assertTrue(res["ok"], res["errors"])
        self.assertEqual(res["stats"]["route_items"], 5)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "topic.md"
            path.write_text(EN_WORKBOOK)
            self.assertFalse(sw.check_workbook_file(path)["ok"])
            (Path(tmp) / "topic-requirements.md").write_text(LEDGER)
            res = sw.check_workbook_file(path)
            self.assertTrue(res["ok"], res["errors"])
            self.assertEqual(res["ledger"]["kind"], "standard")

    def test_header_entry_labels_and_history_kind(self):
        cases = {
            "[Requirements ledger](a.md)": "standard",
            "[ledger](topic-requirements.md)": "standard",
            "[Requirements ledger (history log)](index.md)": "history",
            "[要求帐](a.md)": "standard",  # legacy Chinese label
            "[要求帐（历史流水账）](index.md)": "history",  # legacy Chinese history label
        }
        for link, kind in cases.items():
            with self.subTest(link=link):
                self.assertEqual(source.ledger_entry(f"# Goal\n\n{link}\n\n## Route\n")[1], kind)
        with self.assertRaises(source.SourceError):
            source.ledger_entry("# Goal\n\n[notes](notes.md)\n\n## Route\n")

    def test_wrong_or_missing_sections_fail_with_english_names(self):
        res = sw.check_workbook(EN_WORKBOOK.replace("## Key decisions", "## Decisions"))
        self.assertFalse(res["ok"])
        self.assertTrue(any("['Route', 'Key decisions', 'User to-dos']" in e for e in res["errors"]))

    def test_mixed_language_workbook_does_not_crash(self):
        mixed = EN_WORKBOOK.replace("## Key decisions", "## 关键决策").replace(
            "| ID | Status | Item | Background | Recommendation | Why only the user | Blocks | Raised | Done |",
            "| 编号 | 状态 | 事项 | 背景 | 建议 | 为什么只能用户做 | 挡住 | 提出 | 完成 |")
        self.assertTrue(sw.check_workbook(mixed)["ok"])
        self.assertTrue(sw.reconcile_workbook(mixed, now=NOW)["ok"])
        format_timeline(mixed, mixed, STAMP_NOW)


class EnglishLedgerTests(unittest.TestCase):
    def test_fixture_passes_with_english_summary(self):
        res = sw.check_ledger(LEDGER)
        self.assertTrue(res["ok"], res["errors"])
        self.assertEqual(res["stats"], {"periods": 2, "rows": 8})
        self.assertEqual({s: res["summary"][s] for s in sw.vocab.LEDGER_STATES},
                         {"Done": 2, "Adopted": 1, "Partially adopted": 1, "In progress": 1,
                          "Awaiting user": 1, "Superseded": 1, "Excluded": 1})

    def test_structure_errors(self):
        valid = ledger_row()
        for text in (valid.replace("## 2026-10-27 onward (Efficiency)", "## Efficiency"),
                     valid.replace("Status | Result", "Result | Status"),
                     valid.replace("| --- | --- | --- | --- | --- |\n", ""),
                     "# Ledger\n"):
            with self.subTest(text=text):
                self.assertFalse(sw.check_ledger(text)["ok"])
        res = sw.check_ledger(ledger_row("Finished"))
        self.assertTrue(any('Unknown status "Finished"' in e for e in res["errors"]))

    def test_vacuous_results_are_rejected(self):
        for result in ("done", "Done.", "Completed", "**completed**", "handled", "All done", "has been completed",
                       "already done", "—", "none"):
            with self.subTest(result=result):
                res = sw.check_ledger(ledger_row("In progress", result))
                self.assertTrue(any("concrete conclusion" in e for e in res["errors"]), res["errors"])

    def test_done_and_adopted_need_locatable_material(self):
        for material in ("session reply", "Session reply 10-27", "PR #12", "[report](report.md)", "../a.md"):
            self.assertTrue(sw.check_ledger(ledger_row("Adopted", "Added to AGENTS.md", material))["ok"], material)
        for material in ("", "—", "delivered", "local preview batch-c"):
            self.assertFalse(sw.check_ledger(ledger_row("Done", material=material))["ok"], material)

    def test_superseded_needs_a_named_replacement(self):
        for result in ("Superseded", "replaced", "superseded by a later requirement", "by —", "due to new needs"):
            self.assertFalse(sw.check_ledger(ledger_row("Superseded", result))["ok"], result)
        for result in ("Replaced by the red-frame report row", "superseded by D7", "by the 10-28 rebuild request"):
            self.assertTrue(sw.check_ledger(ledger_row("Superseded", result))["ok"], result)

    def test_excluded_needs_a_reason(self):
        for result in ("", "Excluded", "excluded this requirement", "cancelled", "dropped", "won't do", "no action needed"):
            self.assertFalse(sw.check_ledger(ledger_row("Excluded", result))["ok"], result)
        self.assertTrue(sw.check_ledger(ledger_row("Excluded", "The user adopted only 1, 3 and 5"))["ok"])


class EnglishFormatTests(unittest.TestCase):
    def test_completion_adds_english_suffix_and_columns(self):
        book = EN_WORKBOOK.replace(" | Raised | Done |", " |").replace(" | --- | --- | --- |", " | --- |").replace(
            " | 2026-10-26 | — |", " |")
        before, _ = format_timeline(book, book, STAMP_NOW)
        self.assertIn("| Blocks | Raised | Done |", before)
        edited = before.replace("[ ] Stage 2", "[x] Stage 2").replace("| D1 | open |", "| D1 | done |")
        after, warnings = format_timeline(edited, before, STAMP_NOW)
        self.assertIn("Stage 2: layout cleanup ← in progress thr_aaaaaa1111 (done: 2026-11-15 12:30:45 SGT)", after)
        self.assertIn("| Stage 3 | 2026-11-15 12:30:45 SGT | 2026-11-15 12:30:45 SGT |", after)
        self.assertEqual(warnings, ['Stage 1: historical completion time unverified'])
        self.assertNotIn("完成", after)
        self.assertNotIn("提出", after)

    def test_unknown_history_is_unverified_in_english(self):
        done = EN_WORKBOOK.replace("| D1 | open |", "| D1 | done |")
        after, warnings = format_timeline(done, done, STAMP_NOW)
        self.assertIn("Stage 1: inventory the repository (done: unverified)", after)
        self.assertIn("| 2026-10-26 | unverified |", after)
        self.assertEqual(len(warnings), 2)
        self.assertTrue(all(w.endswith("historical completion time unverified") for w in warnings))

    def test_existing_suffix_keeps_its_language(self):
        legacy = EN_WORKBOOK.replace("Stage 1: inventory the repository", "Stage 1: inventory the repository （完成：2026-10-01）")
        after, _ = format_timeline(legacy, legacy, STAMP_NOW)
        self.assertIn("（完成：2026-10-01）", after)
        self.assertNotIn("(done: 2026-10-01)", after)

    def test_chinese_table_in_english_file_gets_chinese_additions(self):
        mixed = EN_WORKBOOK.replace(
            "| ID | Status | Item | Background | Recommendation | Why only the user | Blocks | Raised | Done |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            "| 编号 | 状态 | 事项 | 背景 | 建议 | 为什么只能用户做 | 挡住 |\n| --- | --- | --- | --- | --- | --- | --- |").replace(
            " | 2026-10-26 | — |", " |").replace("| D1 | open |", "| D1 | 已完成 |")
        after, _ = format_timeline(mixed, mixed, STAMP_NOW)
        self.assertIn("| 挡住 | 提出 | 完成 |", after)
        self.assertIn("| 待核实 |", after)
        self.assertIn("(done: unverified)", after)


class EnglishReconcileTests(unittest.TestCase):
    def test_every_english_state_passes(self):
        res = sw.reconcile_workbook(EN_WORKBOOK, now=NOW)
        self.assertTrue(res["ok"], res["problems"])
        self.assertEqual(res["stats"], {"open_rows": 4, "in_progress": 1, "waiting_on_user": 1,
                                        "scheduled": 1, "queued_after": 1})
        self.assertEqual(sw.running_thread_ids(EN_WORKBOOK), ["thr_aaaaaa1111"])

    def test_malformed_states_are_flagged(self):
        broken = (EN_WORKBOOK.replace("← in progress thr_aaaaaa1111", "← in progress")
                  .replace("← waiting on user", "← later")
                  .replace("scheduled 10-26 22:10 open the window", "scheduled tonight")
                  .replace(": the version built after the cutover", "")
                  .replace("- [x] Stage 1: inventory the repository",
                           "- [x] Stage 1: inventory the repository\n- [ ] Stage 6: long-term plans"))
        details = {p["label"]: p["detail"] for p in sw.reconcile_workbook(broken, now=NOW)["problems"]
                   if p["kind"] == "no_state"}
        self.assertEqual(details, {
            "Stage 2": "in progress without a thread ID",
            "Stage 3": 'state "later" is not one of the four',
            "Stage 4": "scheduled without MM-DD HH:MM",
            "Stage 5": "after <item> without the dependent output",
            "Stage 6": "no state",
        })

    def test_dependency_schedule_and_waiting_rules(self):
        done = EN_WORKBOOK.replace("- [ ] Stage 4: primary cutover window ← scheduled 10-26 22:10 open the window",
                                   "- [x] Stage 4: primary cutover window")
        self.assertIn(("dependency_done", "nudge"), kinds(sw.reconcile_workbook(done, now=NOW)))
        late = sw.reconcile_workbook(EN_WORKBOOK, now=datetime(2026, 10, 26, 22, 41))
        self.assertIn(("schedule_passed", "nudge"), kinds(late))
        unbacked = EN_WORKBOOK.replace("| D1 | open |", "| D1 | done |")
        self.assertIn(("user_wait_unbacked", "nudge"), kinds(sw.reconcile_workbook(unbacked, now=NOW)))
        ranged = EN_WORKBOOK.replace(
            "- [ ] Stage 3: device acceptance ← waiting on user",
            "- [ ] Stage 3: device acceptance ← waiting on user\n- [ ] Stage 6: rollout ← waiting on user").replace(
            "| Stage 3 |", "| Stage 3 to 6 |")
        self.assertTrue(sw.reconcile_workbook(ranged, now=NOW)["ok"])

    def test_categories_and_non_blocking_values(self):
        for category in sw.vocab.TODO_CATEGORIES:
            text = EN_WORKBOOK.replace("physical device: only the user has it", f"{category.capitalize()}: detail")
            self.assertTrue(sw.reconcile_workbook(text, now=NOW)["ok"], category)
        blocking = EN_WORKBOOK.replace("physical device: only the user has it", "only the user has it")
        self.assertIn(("todo_category_missing", "nudge"), kinds(sw.reconcile_workbook(blocking, now=NOW)))
        for value in ("none", "not blocking", "-"):
            idle = EN_WORKBOOK.replace("credentials: the user owns the token", "the user owns the token").replace(
                "| not blocking |", f"| {value} |")
            res = sw.reconcile_workbook(idle, now=NOW)
            self.assertTrue(res["ok"], value)
            self.assertEqual(kinds(res), [("todo_category_missing", "minor")])

    def test_state_change_drives_should_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "topic.md"
            (Path(tmp) / "topic-requirements.md").write_text(LEDGER)
            args = {"max_nonempty_lines": 45, "max_line_chars": 180, "max_route_items": None, "max_decisions": 12}
            for old, new, expected in (("thr_aaaaaa1111", "thr_bbbbbb2222", False),
                                       ("← waiting on user", "← in progress thr_cccccc3333", True),
                                       ("| D1 | open |", "| D1 | done |", True)):
                path.write_text(EN_WORKBOOK.replace(old, new))
                res = sw.should_commit_workbook(path, args, baseline_text=EN_WORKBOOK)
                self.assertEqual(res["should_commit"], expected, (old, new))


class ScriptMessageTagTests(unittest.TestCase):
    def test_current_and_legacy_tags_are_not_user_requests(self):
        for text in (f"{watch.TAG} reconcile", f"{watch.HANDOVER_TAG} taken over",
                     "[bb-steward 看门狗] 对账", "[bb-steward 交接] 已接任"):
            self.assertFalse(watch.is_user_message({"initiator": "user", "input": [{"type": "text", "text": text}]}))
        self.assertTrue(watch.is_user_message({"initiator": "user", "input": [{"type": "text", "text": "check it"}]}))


if __name__ == "__main__":
    unittest.main()
