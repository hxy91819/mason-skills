"""Real temporary Git repositories and command executions; no production access."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import refactor_guard as g


def invoke(args):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        rc = g.main(args)
    return rc, json.loads(stream.getvalue())


class Patterns(unittest.TestCase):
    def test_star_does_not_cross_directory(self):
        self.assertTrue(g.matches("src/a.py", "src/*.py"))
        self.assertFalse(g.matches("src/x/a.py", "src/*.py"))

    def test_double_star_zero_or_multiple_segments(self):
        self.assertTrue(g.matches("tests/a.py", "tests/**/*.py"))
        self.assertTrue(g.matches("tests/a/b/c.py", "tests/**/*.py"))

    def test_question_mark(self):
        self.assertTrue(g.matches("src/a1.py", "src/a?.py"))
        self.assertFalse(g.matches("src/a12.py", "src/a?.py"))

    def test_unsafe_paths_rejected(self):
        for p in ("/etc/passwd", "../a", "src/../a", "a\\b", "a//b", "C:/a", ".git/config", "a\nb"):
            with self.subTest(path=p), self.assertRaises(g.InputError):
                g.relative_path(p, patterns=True)

    def test_invalid_patterns_rejected(self):
        for p in ("src/a**.py", "src/[a].py"):
            with self.assertRaises(g.InputError):
                g.relative_path(p, patterns=True)

    def test_literal_spaces_supported(self):
        self.assertEqual(g.relative_path("src/a b.py"), "src/a b.py")


class GitFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="refactor-guard-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.task = self.root / "task"
        self.task.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Refactor fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.put(".gitignore", "__pycache__/\n*.pyc\n")
        self.put("src/__init__.py", "")
        self.put("tests/__init__.py", "")
        self.put("src/api.py", "def value():\n    return 1\n")
        self.put("src/shared.py", "UNCHANGED = True\n")
        self.put("tests/test_contract.py", "import unittest\nfrom src.api import value\nclass Contract(unittest.TestCase):\n    def test_value(self):\n        self.assertEqual(value(), 1)\n")
        self.base = self.commit("baseline")
        self.policy = {
            "schema_version": 1, "task_id": "fixture", "goal": "synthetic equivalent rewrite", "non_goals": ["deployment"],
            "origin_revision": self.base, "base_revision": self.base,
            "scope": {"strategy": "local", "allowed_paths": ["src/api.py", "src/new/**", "tests/**", "docs/**"],
                      "protected_paths": ["src/shared.py", ".github/**"], "baseline_paths": ["tests/**"],
                      "frozen_paths": ["tests/test_contract.py"]},
            "contracts": [{"id": "C1", "behavior": "return 1", "oracle": {"kind": "contract", "source": "fixture specification"},
                           "baseline_required": True, "red_control_required": False}],
            "benefit": {"required": False, "criterion": "not measured in this mechanical fixture"},
            "review": {"independent_required": True}, "budget": {"max_repairs": 2, "max_replans": 1}}
        self.policy_path = self.task / "policy.json"
        self.seal_path = self.task / "seal.json"
        self.verdict_path = self.task / "verification.json"
        self.seal()

    def git(self, *args):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("GIT_"):
                del env[key]
        return subprocess.check_output(["git", "-C", str(self.repo), *args], stderr=subprocess.PIPE, env=env).decode().strip()

    def put(self, name, data):
        p = self.repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data, encoding="utf-8")

    def commit(self, msg):
        self.git("add", "-A")
        self.git("commit", "-qm", msg)
        return self.git("rev-parse", "HEAD")

    def json_write(self, p, value):
        Path(p).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def seal(self):
        self.json_write(self.policy_path, self.policy)
        self.json_write(self.seal_path, g.make_seal(self.repo, self.policy, self.policy_path))
        self.policy_hash = g.sha256(self.policy_path)
        self.seal_hash = g.sha256(self.seal_path)

    def run_tests(self, name, kind, extra=()):
        out = self.task / "evidence" / (name + ".json")
        report = out.with_suffix(".junit.xml")
        args = ["run", "--repo", str(self.repo), "--out", str(out), "--kind", kind,
                "--contract", "C1", "--environment", "isolated temporary test fixture; no production services",
                "--junit", str(report), *extra, "--", sys.executable,
                str(SCRIPTS / "unittest_junit.py"), "--output", str(report), "--start", "tests", "--top", "."]
        # unittest discovery with explicit top requires an importable tests package.
        return invoke(args)

    def complete(self, red=False):
        baseline_rc, _ = self.run_tests("baseline", "baseline")
        self.assertEqual(baseline_rc, 0)
        refs = ["evidence/baseline.json", "evidence/candidate.json"]
        if red:
            self.policy["contracts"][0]["red_control_required"] = True
            self.seal()
            self.put("src/api.py", "def value():\n    return 0\n")
            self.commit("isolated deliberate defect")
            rc, _ = self.run_tests("red", "red-control", ("--control-of", self.base))
            self.assertEqual(rc, 0)
            refs.append("evidence/red.json")
            self.git("checkout", "-q", self.base)
        self.put("src/api.py", "def value():\n    return sum([1])\n")
        self.candidate = self.commit("equivalent fixture candidate")
        candidate_rc, _ = self.run_tests("candidate", "regression")
        self.assertEqual(candidate_rc, 0)
        self.v = {"schema_version": 1, "task_id": "fixture", "base_revision": self.base,
                  "candidate_revision": self.candidate, "policy_sha256": self.policy_hash, "seal_sha256": self.seal_hash,
                  "decision": "PASS", "implementer_session_id": "synthetic-implementer",
                  "reviewer": {"session_id": "synthetic-reviewer", "independent": True,
                               "note": "test fixture metadata, not an actual independent Agent review"},
                  "impact": {"reviewed_revision": self.candidate, "all_changed_paths_reviewed": True,
                             "shared_state_reviewed": True, "unresolved": []},
                  "contracts": [{"id": "C1", "status": "PASS", "tests": ["tests.test_contract.Contract.test_value"],
                                 "assertion": "value() must remain exactly 1", "assertions_reviewed": True,
                                 "red_control_confirmed": red, "evidence": refs}],
                  "benefit": {"status": "NOT_REQUIRED", "evidence": [], "note": "not required in this fixture"},
                  "blocking_findings": [], "residual_risks": ["synthetic fixture only"]}
        self.json_write(self.verdict_path, self.v)
        return self.v

    def gate(self):
        return invoke(["gate", "--repo", str(self.repo), "--policy", str(self.policy_path), "--seal", str(self.seal_path),
                       "--verification", str(self.verdict_path), "--approved-policy-sha256", self.policy_hash,
                       "--approved-seal-sha256", self.seal_hash])

    def test_valid_end_to_end_gate(self):
        self.complete()
        rc, result = self.gate()
        self.assertEqual((rc, result["result"]), (0, "PASS_MECHANICAL"), result)

    def test_red_control_end_to_end(self):
        self.complete(red=True)
        rc, result = self.gate()
        self.assertEqual(rc, 0, result)

    def test_protected_shared_path_blocks(self):
        self.complete()
        self.put("src/shared.py", "UNCHANGED = False\n")
        self.commit("outside boundary")
        rc, result = self.gate()
        self.assertEqual(rc, 1, result)
        self.assertTrue(any("protected" in s for s in result["blocked"]))

    def test_rename_checks_old_path(self):
        self.git("mv", "src/shared.py", "src/api-new.py")
        self.commit("rename")
        result = g.scope_result(self.repo, self.policy)
        self.assertIn("src/shared.py", result["changed_paths"])
        self.assertIn("src/api-new.py", result["changed_paths"])
        self.assertEqual(result["result"], "BLOCK")

    def test_worktree_covers_untracked_and_staged(self):
        self.put("surprise.txt", "outside\n")
        self.put("src/api.py", "def value():\n    return 2\n")
        self.git("add", "src/api.py")
        result = g.scope_result(self.repo, self.policy, True)
        self.assertIn("surprise.txt", result["changed_paths"])
        self.assertIn("src/api.py", result["changed_paths"])

    def test_test_assertion_change_blocks(self):
        self.complete()
        self.put("tests/test_contract.py", "# removed assertions\n")
        self.commit("weaken assertions")
        rc, result = self.gate()
        self.assertEqual(rc, 1, result)
        self.assertTrue(any("frozen" in s for s in result["blocked"]))

    def test_candidate_evidence_stales_after_new_commit(self):
        self.complete()
        self.put("docs/note.md", "new commit\n")
        self.commit("documentation also changes candidate identity")
        rc, result = self.gate()
        self.assertEqual((rc, result["result"]), (2, "INSUFFICIENT"), result)

    def test_no_candidate_evidence_is_insufficient(self):
        self.complete()
        self.v["contracts"][0]["evidence"] = ["evidence/baseline.json"]
        self.json_write(self.verdict_path, self.v)
        self.assertEqual(self.gate()[0], 2)

    def test_no_baseline_evidence_is_insufficient(self):
        self.complete()
        self.v["contracts"][0]["evidence"] = ["evidence/candidate.json"]
        self.json_write(self.verdict_path, self.v)
        self.assertEqual(self.gate()[0], 2)

    def test_unreviewed_assertions_insufficient(self):
        self.complete()
        self.v["contracts"][0]["assertions_reviewed"] = False
        self.json_write(self.verdict_path, self.v)
        self.assertEqual(self.gate()[0], 2)

    def test_unresolved_shared_state_insufficient(self):
        self.complete()
        self.v["impact"]["unresolved"] = ["unknown cache consumer"]
        self.json_write(self.verdict_path, self.v)
        self.assertEqual(self.gate()[0], 2)

    def test_self_review_insufficient(self):
        self.complete()
        self.v["reviewer"]["session_id"] = self.v["implementer_session_id"]
        self.json_write(self.verdict_path, self.v)
        self.assertEqual(self.gate()[0], 2)

    def test_semantic_block_remains_block(self):
        self.complete()
        self.v["decision"] = "BLOCK"
        self.v["blocking_findings"] = ["confirmed wrong permission semantics"]
        self.json_write(self.verdict_path, self.v)
        self.assertEqual(self.gate()[0], 1)

    def test_policy_cannot_self_expand(self):
        self.complete()
        self.policy["scope"]["allowed_paths"].append("**")
        self.json_write(self.policy_path, self.policy)
        rc, result = self.gate()
        self.assertEqual(rc, 1, result)
        self.assertTrue(any("trusted approved" in s for s in result["blocked"]))

    def test_seal_tamper_blocks(self):
        self.complete()
        seal = g.read_json(self.seal_path)
        seal["files"] = {}
        self.json_write(self.seal_path, seal)
        self.assertEqual(self.gate()[0], 1)

    def test_log_tamper_insufficient(self):
        self.complete()
        (self.task / "evidence/candidate.log").write_text("invented PASS\n")
        rc, result = self.gate()
        self.assertEqual(rc, 2, result)
        self.assertTrue(any("digest mismatch" in s for s in result["missing"]))

    def test_fake_counts_do_not_override_xml(self):
        self.complete()
        record = g.read_json(self.task / "evidence/candidate.json")
        record["test_summary"]["tests"] = 999
        self.json_write(self.task / "evidence/candidate.json", record)
        self.assertEqual(self.gate()[0], 2)

    def test_missing_report_insufficient(self):
        self.complete()
        (self.task / "evidence/candidate.junit.xml").unlink()
        self.assertEqual(self.gate()[0], 2)

    def test_evidence_path_escape_rejected(self):
        self.complete()
        self.v["contracts"][0]["evidence"].append("../secrets.json")
        self.json_write(self.verdict_path, self.v)
        self.assertEqual(self.gate()[0], 2)

    def test_evidence_symlink_rejected(self):
        self.complete()
        (self.task / "evidence/alias.json").symlink_to(self.task / "evidence/candidate.json")
        self.v["contracts"][0]["evidence"].append("evidence/alias.json")
        self.json_write(self.verdict_path, self.v)
        self.assertEqual(self.gate()[0], 2)

    def test_required_benefit_without_execution_insufficient(self):
        self.complete()
        self.policy["benefit"]["required"] = True
        self.seal()
        self.v.update(policy_sha256=self.policy_hash, seal_sha256=self.seal_hash)
        self.v["benefit"]["status"] = "PASS"
        self.json_write(self.verdict_path, self.v)
        self.assertEqual(self.gate()[0], 2)

    def test_dirty_checkout_insufficient(self):
        self.complete()
        self.put("src/api.py", "uncommitted\n")
        self.assertEqual(self.gate()[0], 2)

    def test_assume_unchanged_refused(self):
        self.git("update-index", "--assume-unchanged", "src/api.py")
        with self.assertRaises(g.InputError):
            g.snapshot(self.repo)

    def test_baseline_must_not_hide_production_changes(self):
        self.put("src/api.py", "def value():\n    return 0\n")
        self.policy["base_revision"] = self.commit("not tests only")
        with self.assertRaises(g.InputError):
            g.make_seal(self.repo, self.policy, self.policy_path)

    def test_empty_frozen_pattern_is_not_silent_success(self):
        self.policy["scope"]["frozen_paths"] = ["tests/missing.py"]
        with self.assertRaises(g.InputError):
            g.make_seal(self.repo, self.policy, self.policy_path)

    def test_frozen_symlink_refused(self):
        (self.repo / "tests/link.py").symlink_to("../src/api.py")
        head = self.commit("symlink")
        with self.assertRaises(g.InputError):
            g.selected_entries(self.repo, head, ["tests/link.py"])

    def test_existing_report_refused_before_execution(self):
        existing = self.task / "already.xml"
        existing.write_text("<testsuite/>")
        rc, _ = invoke(["run", "--repo", str(self.repo), "--out", str(self.task / "x.json"),
                        "--kind", "check", "--environment", "test", "--junit", str(existing),
                        "--", sys.executable, "-c", "print('should not run')"])
        self.assertEqual(rc, 2)
        self.assertFalse((self.task / "x.log").exists())

    def test_output_inside_repo_refused(self):
        rc, _ = invoke(["run", "--repo", str(self.repo), "--out", str(self.repo / "x.json"),
                        "--kind", "check", "--environment", "test", "--", sys.executable, "-c", "print('x')"])
        self.assertEqual(rc, 2)

    def test_source_mutation_recorded_not_accepted(self):
        rc, _ = invoke(["run", "--repo", str(self.repo), "--out", str(self.task / "mutating.json"),
                        "--kind", "check", "--environment", "test", "--", sys.executable, "-c",
                        "from pathlib import Path; Path('src/api.py').write_text('changed')"])
        self.assertEqual(rc, 1)
        self.assertIs(g.read_json(self.task / "mutating.json")["source_unchanged"], False)

    def test_timeout_saved_and_not_accepted(self):
        rc, _ = invoke(["run", "--repo", str(self.repo), "--out", str(self.task / "timeout.json"),
                        "--kind", "check", "--environment", "test", "--timeout", "0.05", "--",
                        sys.executable, "-c", "import time; time.sleep(2)"])
        self.assertEqual(rc, 1)
        self.assertIs(g.read_json(self.task / "timeout.json")["timed_out"], True)

    def test_records_never_overwritten(self):
        args = ["run", "--repo", str(self.repo), "--out", str(self.task / "once.json"),
                "--kind", "check", "--environment", "test", "--", sys.executable, "-c", "print('ok')"]
        self.assertEqual(invoke(args)[0], 0)
        first = (self.task / "once.json").read_bytes()
        self.assertEqual(invoke(args)[0], 2)
        self.assertEqual((self.task / "once.json").read_bytes(), first)

    def test_init_is_draft_and_refuses_overwrite(self):
        target = self.root / "new-task"
        args = ["init", "--repo", str(self.repo), "--task-dir", str(target), "--id", "example", "--goal", "keep value"]
        self.assertEqual(invoke(args)[0], 0)
        self.assertEqual(invoke(args)[0], 2)
        with self.assertRaises(g.InputError):
            g.validate_policy(g.read_json(target / "policy.json"))

    def test_unknown_policy_fields_rejected(self):
        self.policy["scope"]["allow_paths"] = ["**"]
        with self.assertRaises(g.InputError):
            g.validate_policy(self.policy)

    def test_duplicate_contract_ids_rejected(self):
        self.policy["contracts"].append(copy.deepcopy(self.policy["contracts"][0]))
        with self.assertRaises(g.InputError):
            g.validate_policy(self.policy)


class Reports(unittest.TestCase):
    def parse(self, xml):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "junit.xml"
            p.write_text(xml)
            return g.parse_junit(p)

    def test_empty_suite_has_zero_executed(self):
        self.assertEqual(self.parse('<testsuite tests="100"/>')["executed"], 0)

    def test_nested_suites_not_double_counted(self):
        xml = '<testsuites><testsuite><testsuite><testcase name="one"/></testsuite></testsuite></testsuites>'
        self.assertEqual(self.parse(xml)["tests"], 1)

    def test_skip_error_failure_counted(self):
        xml = '<testsuite><testcase><skipped/></testcase><testcase name="bad"><failure/></testcase><testcase><error/></testcase></testsuite>'
        result = self.parse(xml)
        self.assertEqual((result["executed"], result["skipped"], result["failures"], result["errors"]), (2, 1, 1, 1))

    def test_entities_rejected(self):
        with self.assertRaises(g.InputError):
            self.parse('<!DOCTYPE x [<!ENTITY a "b">]><testsuite/>')

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "bad.json"
            p.write_text('{"decision":"BLOCK","decision":"PASS"}')
            with self.assertRaises(g.InputError):
                g.read_json(p)


if __name__ == "__main__":
    unittest.main()
