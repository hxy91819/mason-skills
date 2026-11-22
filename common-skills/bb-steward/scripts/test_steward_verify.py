import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import steward_workbook as sw

SCRIPTS = Path(__file__).resolve().parent
WORKBOOK = """# 测试工作簿

## 路线

- [x] 阶段 1：完成一
- [x] 阶段 2：完成二

## 关键决策

## 用户待办
"""


class VerifyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.book = Path(temp.name) / "项目.md"
        self.ledger = self.book.with_name("要求帳.md")
        self.ledger.write_bytes((SCRIPTS / "fixtures/要求帳.md").read_bytes())
        self.with_link = WORKBOOK.replace("## 路线", "[要求帳](要求帳.md)\n\n## 路线")
        self.book.write_text(self.with_link)

    def run_cli(self, *flags, mode="verify"):
        proc = subprocess.run(
            [sys.executable, "-B", str(SCRIPTS / "steward_workbook.py"),
             "--mode", mode, "--file", str(self.book), *flags],
            capture_output=True, text=True, timeout=10,
        )
        self.assertFalse(proc.stderr, proc.stderr)
        return proc

    def cli(self, *flags, mode="verify"):
        proc = self.run_cli("--json", *flags, mode=mode)
        return proc.returncode, json.loads(proc.stdout)

    def test_summary_reports_success_and_reconcile_problems(self):
        proc = self.run_cli("--dry-run")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(len(proc.stdout.splitlines()), 1)
        self.assertIn("ok，问题 0 项", proc.stdout)

        self.book.write_text(self.with_link.replace("- [x]", "- [ ]", 1))
        proc = self.run_cli("--dry-run")
        problems = self.cli("--dry-run")[1]["steps"]["reconcile"]["problems"]
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(len(proc.stdout.splitlines()), 1)
        self.assertIn(f"失败（reconcile），问题 {len(problems)} 项", proc.stdout)

    def test_bad_todo_row_reports_original_line_without_writing(self):
        row = "| 待办 | 缺列 |"
        self.book.write_text(self.with_link + f"\n| 状态 | 事项 | 挡住 |\n| --- | --- | --- |\n{row}\n")
        before = self.book.read_text()
        lineno = before.splitlines().index(row) + 1
        proc = self.run_cli()
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(len(proc.stdout.splitlines()), 1)
        self.assertIn("失败（format）", proc.stdout)
        self.assertIn(f"第 {lineno} 行", proc.stdout)
        self.assertIn(row, proc.stdout)
        self.assertEqual(self.book.read_text(), before)

    def test_dry_run_uses_formatted_text_without_writing(self):
        before = self.book.read_bytes()
        rc, res = self.cli("--dry-run")
        self.assertEqual(rc, 0, res)
        self.assertEqual(list(res["steps"]), ["format", "check", "ledger-check", "reconcile"])
        self.assertTrue(res["steps"]["format"]["changed"])
        self.assertEqual(self.book.read_bytes(), before)
        self.assertEqual(len(res["steps"]["format"]["warnings"]), 1)
        self.assertIn("2 条", res["steps"]["format"]["warnings"][0])
        rc, res = self.cli("--verbose-warnings")
        self.assertEqual(rc, 0, res)
        self.assertEqual(len(res["steps"]["format"]["warnings"]), 2)
        self.assertNotEqual(self.book.read_bytes(), before)
        self.assertEqual(self.cli("--dry-run")[1]["steps"]["format"]["changed"], False)

    def test_explicit_ledger_overrides_absent_header_link(self):
        self.book.write_text(WORKBOOK)
        rc, res = self.cli("--dry-run")
        self.assertNotEqual(rc, 0)
        self.assertEqual(res["failed_step"], "check")
        self.assertEqual(list(res["steps"]), ["format", "check"])
        rc, res = self.cli("--dry-run", "--ledger", str(self.ledger))
        self.assertEqual(rc, 0, res)

    def test_invalid_ledger_stops_before_reconcile(self):
        self.ledger.write_text("不符合要求帐结构")
        rc, res = self.cli("--dry-run")
        self.assertNotEqual(rc, 0)
        self.assertEqual(res["failed_step"], "ledger-check")
        self.assertNotIn("reconcile", res["steps"])

    def test_reconcile_failure_returns_nonzero(self):
        self.book.write_text(self.with_link.replace("- [x]", "- [ ]", 1))
        rc, res = self.cli("--dry-run")
        self.assertNotEqual(rc, 0)
        self.assertEqual(res["failed_step"], "reconcile")
        self.assertIn("no_state", [p["kind"] for p in res["steps"]["reconcile"]["problems"]])

    def test_format_folds_only_known_warnings(self):
        with patch.object(sw, "format_timeline", return_value=(
                self.with_link, ["阶段 1：历史完成时间待核实", "新增异常"])):
            _, res = sw.format_workbook(self.book, dry_run=True)
        self.assertIn("新增异常", res["warnings"])
        self.assertIn("1 条", res["warnings"][1])

    def test_format_cli_reports_missing_file_as_failure(self):
        self.book.unlink()
        rc, res = self.cli(mode="format")
        self.assertNotEqual(rc, 0)
        self.assertFalse(res["ok"])
