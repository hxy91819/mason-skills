import importlib.util
import json
import os
from pathlib import Path
import py_compile
import re
import subprocess
import sys
import unittest

from test_guard import GitFixture, ROOT, SCRIPTS
import refactor_guard as g


class ExtraGuardCases(GitFixture):
    # Inherited tests are suppressed below: this class adds only new fixture cases.
    def test_existing_stale_bytecode_cannot_hide_red_control(self):
        rc, result = self.run_tests("baseline", "baseline")
        self.assertEqual(rc, 0, result)
        source = self.repo / "src/api.py"
        old_stat = source.stat()
        py_compile.compile(str(source), doraise=True)
        self.put("src/api.py", "def value():\n    return 0\n")
        self.commit("same-size deliberate defect")
        os.utime(source, (old_stat.st_atime, old_stat.st_mtime))
        rc, result = self.run_tests("red", "red-control", ("--control-of", self.base))
        self.assertEqual(rc, 0, result)
        self.assertEqual(g.read_json(self.task / "evidence/red.json")["test_summary"]["failures"], 1)

    def test_wrong_named_test_is_not_coverage(self):
        self.complete()
        self.v["contracts"][0]["tests"] = ["tests.test_contract.Contract.not_actually_run"]
        self.json_write(self.verdict_path, self.v)
        self.assertEqual(self.gate()[0], 2)

    def test_red_control_compile_error_does_not_count(self):
        self.put("src/api.py", "def value(:\n")
        self.commit("syntactically invalid, not a meaningful red control")
        rc, _ = self.run_tests("red-error", "red-control", ("--control-of", self.base))
        self.assertEqual(rc, 1)
        summary = g.read_json(self.task / "evidence/red-error.json")["test_summary"]
        self.assertGreater(summary["errors"], 0)
        self.assertEqual(summary["failures"], 0)

    def test_set_up_class_errors_produce_junit(self):
        self.put("tests/test_contract.py", "import unittest\nclass Broken(unittest.TestCase):\n    @classmethod\n    def setUpClass(cls):\n        raise RuntimeError('environment failed')\n    def test_never_runs(self):\n        pass\n")
        self.commit("fixture setup fails")
        rc, _ = self.run_tests("setup-error", "regression")
        self.assertEqual(rc, 1)
        summary = g.read_json(self.task / "evidence/setup-error.json")["test_summary"]
        self.assertGreater(summary["errors"], 0)

    def test_empty_suite_cannot_support_contract(self):
        out = self.task / "empty.junit.xml"
        p = subprocess.run([sys.executable, str(SCRIPTS / "unittest_junit.py"), "--output", str(out),
                            "--start", "tests", "--top", ".", "--pattern", "never-match*.py"],
                           cwd=self.repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(g.parse_junit(out)["executed"], 0)


# unittest discovers inherited test_* methods too. Retain setUp/helpers but not duplicate cases.
for name in list(GitFixture.__dict__):
    if name.startswith("test_") and name not in ExtraGuardCases.__dict__:
        setattr(ExtraGuardCases, name, None)


class Bundle(unittest.TestCase):
    def test_markdown_links_resolve_inside_skill(self):
        broken = []
        for p in ROOT.rglob("*.md"):
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", p.read_text(encoding="utf-8")):
                if target.startswith(("https://", "http://", "#")):
                    continue
                resolved = (p.parent / target.split("#", 1)[0]).resolve()
                if not resolved.exists() or ROOT not in resolved.parents:
                    broken.append(f"{p.relative_to(ROOT)} -> {target}")
        self.assertEqual(broken, [])

    def test_cli_python39_syntax_compatibility(self):
        import ast
        for p in list(SCRIPTS.glob("*.py")) + list((ROOT / "examples").rglob("*.py")):
            ast.parse(p.read_text(), feature_version=(3, 9))

    def test_agent_eval_cases_are_explicitly_not_run(self):
        rows = [json.loads(x) for x in (ROOT / "tests/agent-evals.jsonl").read_text().splitlines()]
        self.assertEqual(len(rows), 8)
        self.assertTrue(all(x["execution_status"] == "NOT_RUN" for x in rows))


# Avoid importing the base class into unittest discovery under its original name.
del GitFixture

if __name__ == "__main__":
    unittest.main()
