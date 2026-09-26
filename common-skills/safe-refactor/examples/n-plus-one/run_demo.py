#!/usr/bin/env python3
"""Reproducible SQLite example in a NEW directory; never touches an existing repo."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parents[1]
TOOLS = PACKAGE / "scripts"
sys.path.insert(0, str(TOOLS))
import refactor_guard as g


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, help="new directory, outside the skills package")
    args = p.parse_args(argv)
    root = Path(args.output).expanduser().resolve()
    if root.exists() or root.is_symlink() or root == PACKAGE or PACKAGE in root.parents:
        p.error("output must be a NEW directory outside the package")
    root.mkdir(parents=True)
    repo, task = root / "repo", root / "task"
    shutil.copytree(HERE / "fixture", repo, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    task.mkdir()

    def git(*a):
        return g.git(repo, *a).decode().strip()

    def commit(message):
        git("add", "-A")
        git("commit", "-qm", message)
        return git("rev-parse", "HEAD")

    def call(args, expected=0):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            rc = g.main(args)
        result = json.loads(stream.getvalue())
        if rc != expected:
            raise RuntimeError(json.dumps(result, indent=2))
        return result

    def save(path, value):
        Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    git("init", "-q")
    git("config", "user.name", "Local refactor demonstration")
    git("config", "user.email", "demo@example.invalid")
    base = commit("old implementation and fixed behavioral baseline")
    policy = {
        "schema_version": 1, "task_id": "n-plus-one-demo", "goal": "only endpoint A batches reads; keep other callers unchanged",
        "non_goals": ["no production deployment", "no schema change", "no rewrite of shared authorization"],
        "origin_revision": base, "base_revision": base,
        "scope": {"strategy": "local", "allowed_paths": ["src/api.py", "src/batch.py", "docs/**"],
                  "protected_paths": ["src/shared.py", "src/store.py", "src/other_api.py"],
                  "baseline_paths": ["tests/**"], "frozen_paths": ["tests/**", "benchmark.py"]},
        "contracts": [
            {"id": "C1", "behavior": "tenant authorization unchanged", "oracle": {"kind": "contract", "source": "fixture spec: tenants cannot see other tenants"}, "baseline_required": True, "red_control_required": True},
            {"id": "C2", "behavior": "ordering, duplicates, missing and empty semantics unchanged", "oracle": {"kind": "characterization", "source": "fixed old entry and contract tests"}, "baseline_required": True, "red_control_required": False},
            {"id": "C3", "behavior": "other entry, ownership and failure semantics unchanged", "oracle": {"kind": "contract", "source": "fixture contract"}, "baseline_required": True, "red_control_required": False}],
        "benefit": {"required": True, "criterion": "SQLite SELECT count <= ceil(N/100), preserving rows"},
        "review": {"independent_required": False},
        "budget": {"max_repairs": 2, "max_replans": 1}}
    # DEMO ONLY: no actual independent Agent is run, so the fixture explicitly records
    # independent_required=false. The production template requires independence.
    save(task / "policy.json", policy)
    call(["seal", "--repo", str(repo), "--policy", str(task / "policy.json"), "--out", str(task / "seal.json")])
    ph, sh = g.sha256(task / "policy.json"), g.sha256(task / "seal.json")

    def run(name, kind, contracts=(), red=False, benefit=False, expected=0):
        out = task / "evidence" / (name + ".json")
        a = ["run", "--repo", str(repo), "--out", str(out), "--kind", kind,
             "--environment", "local isolated in-memory SQLite example, no external services"]
        for c in contracts:
            a += ["--contract", c]
        if red:
            a += ["--control-of", base]
        if benefit:
            command = [sys.executable, "-B", "benchmark.py"] + (["--require-batch"] if kind == "benefit" else [])
        else:
            report = out.with_suffix(".junit.xml")
            a += ["--junit", str(report)]
            command = [sys.executable, str(TOOLS / "unittest_junit.py"), "--output", str(report), "--start", "tests", "--top", "."]
        return call(a + ["--"] + command, expected)

    run("baseline", "baseline", ("C1", "C2", "C3"))
    run("before-queries", "check", benefit=True)
    # Use a distinct worktree rather than overwriting the old/candidate tree.
    control_repo = root / "red-control-repo"
    git("worktree", "add", "--detach", str(control_repo), base)
    shared = control_repo / "src/shared.py"
    shared.write_text(shared.read_text().replace('row is not None and row["tenant"] == tenant', 'row is not None'))
    g.git(control_repo, "add", "src/shared.py")
    g.git(control_repo, "commit", "-qm", "DELIBERATE DEFECT: remove tenant check, never merge")
    old_repo = repo
    repo = control_repo
    run("red-control", "red-control", ("C1",), red=True)
    repo = old_repo
    for src in (HERE / "candidate").glob("*.py"):
        shutil.copy2(src, repo / "src" / src.name)
    candidate = commit("endpoint A only: bounded batch reads")
    run("candidate", "regression", ("C1", "C2", "C3"))
    run("benefit", "benefit", benefit=True)
    test_prefix = "tests.test_contract.UserContract."
    tests = {"C1": ["test_tenant_filter"],
             "C2": ["test_order_and_duplicates", "test_missing_rows", "test_empty", "test_multiple_batch_boundaries"],
             "C3": ["test_other_entry_keeps_behavior", "test_returned_objects_do_not_alias", "test_database_failure_is_not_silenced"]}
    verdict = {
        "schema_version": 1, "task_id": policy["task_id"], "base_revision": base, "candidate_revision": candidate,
        "policy_sha256": ph, "seal_sha256": sh, "decision": "PASS", "implementer_session_id": "demo-script",
        "reviewer": {"session_id": "demo-script", "independent": False,
                     "note": "prewritten fixture expectations; NOT an independent Agent/human acceptance"},
        "impact": {"reviewed_revision": candidate, "all_changed_paths_reviewed": True, "shared_state_reviewed": True, "unresolved": []},
        "contracts": [{"id": c["id"], "status": "PASS", "tests": [test_prefix + n for n in tests[c["id"]]],
                       "assertion": c["behavior"], "assertions_reviewed": True, "red_control_confirmed": c["id"] == "C1",
                       "evidence": ["evidence/baseline.json", "evidence/candidate.json"] + (["evidence/red-control.json"] if c["id"] == "C1" else [])} for c in policy["contracts"]],
        "benefit": {"status": "PASS", "evidence": ["evidence/benefit.json"], "note": "actual SQLite SELECT count, not production latency"},
        "blocking_findings": [], "residual_risks": ["demo data only; no true concurrent DB load or independent Agent assessment"]}
    save(task / "verification.json", verdict)
    gate_args = ["gate", "--repo", str(repo), "--policy", str(task / "policy.json"), "--seal", str(task / "seal.json"),
                 "--verification", str(task / "verification.json"), "--approved-policy-sha256", ph, "--approved-seal-sha256", sh]
    passed = call(gate_args)
    save(task / "gate-valid.json", passed)
    (repo / "docs").mkdir()
    (repo / "docs/note.md").write_text("New commit; old candidate evidence must not be reused.\n")
    commit("demonstrate stale candidate evidence")
    stale = call(gate_args, 2)
    save(task / "gate-stale.json", stale)
    shared = repo / "src/shared.py"
    shared.write_text(shared.read_text() + "\nCACHE_FORMAT_VERSION = 2\n")
    commit("demonstrate protected shared-path modification")
    blocked = call(gate_args, 1)
    save(task / "gate-blocked.json", blocked)
    before_measurement = json.loads((task / "evidence/before-queries.log").read_text())["results"]
    after_measurement = json.loads((task / "evidence/benefit.log").read_text())["results"]
    before_queries = next(x["sqlite_selects"] for x in before_measurement if x["rows"] == 205)
    after_queries = next(x["sqlite_selects"] for x in after_measurement if x["rows"] == 205)
    summary = {"valid_candidate": passed["result"], "new_commit_old_evidence": stale["result"],
               "shared_path_expansion": blocked["result"], "baseline_contract_cases": g.read_json(task / "evidence/baseline.json")["test_summary"]["executed"],
               "candidate_contract_cases": g.read_json(task / "evidence/candidate.json")["test_summary"]["executed"],
               "before_selects_N205": before_queries, "after_selects_N205": after_queries,
               "output": str(root), "note": "local reproducible fixture; no production or independent Agent validation"}
    save(root / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
