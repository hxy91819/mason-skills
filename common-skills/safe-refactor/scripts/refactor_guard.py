#!/usr/bin/env python3
"""Local evidence utilities. Not a semantic verifier, sandbox, or approval service."""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

VERSION = "1.0.0"
SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
IDENT = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{0,63}$")
KINDS = {"baseline", "regression", "benefit", "red-control", "check"}


class InputError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise InputError(message)


def text(value, label):
    require(isinstance(value, str) and bool(value.strip()), label + ": nonempty string required")
    return value


def obj(value, keys, label):
    require(isinstance(value, dict), label + ": object required")
    require(set(value) == set(keys), label + ": keys must be " + ", ".join(sorted(keys)))
    return value


def boolean(value, label):
    require(type(value) is bool, label + ": boolean required")


def array(value, label, nonempty=False):
    require(isinstance(value, list), label + ": array required")
    require(not nonempty or len(value) > 0, label + ": cannot be empty")
    return value


def string_list(value, label, nonempty=False):
    array(value, label, nonempty)
    for v in value:
        text(v, label)
    require(len(value) == len(set(value)), label + ": duplicates not allowed")
    return value


def relative_path(value, patterns=False):
    text(value, "path")
    require(not value.startswith("/") and "\\" not in value and ":" not in value,
            "path must be repository-relative POSIX: " + repr(value))
    require(len(value) <= 4096, "path is too long")
    parts = value.split("/")
    require(len(parts) <= 256, "too many path segments")
    require(all(p not in {"", ".", "..", ".git"} for p in parts), "unsafe path: " + repr(value))
    require(not any(ord(c) < 32 for c in value), "control characters in path")
    if patterns:
        require("[" not in value and "]" not in value, "only *, ** and ? patterns are supported")
        require(all("**" not in p or p == "**" for p in parts), "** must be an entire segment")
    else:
        require(not any(c in value for c in "*?[]"), "literal path required")
    return value


def matches(path, pattern):
    """Segment-aware matching: * cannot cross /; ** matches zero or more segments."""
    parts, pats = path.split("/"), pattern.split("/")
    memo = {}

    def walk(i, j):
        key = (i, j)
        if key not in memo:
            if j == len(pats):
                ans = i == len(parts)
            elif pats[j] == "**":
                ans = walk(i, j + 1) or (i < len(parts) and walk(i + 1, j))
            else:
                ans = i < len(parts) and fnmatch.fnmatchcase(parts[i], pats[j]) and walk(i + 1, j + 1)
            memo[key] = ans
        return memo[key]
    return walk(0, 0)


def any_match(path, patterns):
    return any(matches(path, p) for p in patterns)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def duplicate_keys(pairs):
    out = {}
    for k, v in pairs:
        require(k not in out, "duplicate JSON key: " + k)
        out[k] = v
    return out


def read_json(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink(), "missing/unsafe JSON file: " + str(p))
    require(p.stat().st_size <= 16 * 1024 * 1024, "JSON file too large")
    return json.loads(p.read_text(encoding="utf-8"), object_pairs_hook=duplicate_keys,
                      parse_constant=lambda s: (_ for _ in ()).throw(InputError("invalid JSON number: " + s)))


def create_bytes(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation; no silent overwrites of previous evidence or user work.
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def write_json(path, data):
    create_bytes(path, (json.dumps(data, ensure_ascii=True, indent=2) + "\n").encode("utf-8"))


def emit(data):
    print(json.dumps(data, ensure_ascii=True, indent=2))


def git(repo, *args, ok=(0,)):
    cmd = ["git", "--no-pager", "--literal-pathspecs", "-C", str(repo),
           "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false", *args]
    env = os.environ.copy()
    # Do not let environment variables silently select a different repository/index.
    for k in list(env):
        if k.startswith("GIT_") and k not in {"GIT_EXEC_PATH"}:
            del env[k]
    env["GIT_OPTIONAL_LOCKS"] = "0"
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=60)
    require(p.returncode in ok, "Git failed: " + p.stderr.decode("utf-8", "replace").strip())
    return p.stdout


def repository(path):
    raw = git(Path(path).resolve(), "rev-parse", "--show-toplevel")
    return Path(os.fsdecode(raw).strip()).resolve()


def commit(repo, ref):
    text(ref, "revision")
    require(ref == "HEAD" or bool(SHA.fullmatch(ref)), "use HEAD or a complete lowercase commit SHA")
    return git(repo, "rev-parse", "--verify", ref + "^{commit}").decode().strip()


def ancestor(repo, older, newer):
    # git() clears repository-selection environment variables for this query too.
    return git(repo, "merge-base", older, newer, ok=(0, 1)).decode().strip() == older


def tree_entries(repo, revision):
    result = {}
    for record in git(repo, "ls-tree", "-r", "-z", revision).split(b"\0"):
        if not record:
            continue
        meta, path = record.split(b"\t", 1)
        mode, kind, oid = meta.decode().split()
        result[os.fsdecode(path)] = {"mode": mode, "kind": kind, "oid": oid}
    return result


def snapshot(repo):
    revision = commit(repo, "HEAD")
    flags = git(repo, "ls-files", "-v", "-z").split(b"\0")
    require(not any(r and (chr(r[0]).islower() or r[:1] == b"S") for r in flags),
            "assume-unchanged/skip-worktree files unsupported; use a normal clean checkout")
    entries = tree_entries(repo, revision)
    require(not any(e["mode"] == "160000" for e in entries.values()),
            "submodules require a project-specific recursive evidence adapter; unsupported by this gate")
    dirty = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignore-submodules=none")
    require(not dirty, "checkout has staged, unstaged or untracked changes; preserve them and use an isolated clean commit")
    return {"commit": revision, "tree": git(repo, "rev-parse", revision + "^{tree}").decode().strip()}


def outside_repo(path, repo):
    p = Path(path).resolve()
    require(p != repo and repo not in p.parents, "task/evidence output must be outside the source checkout")
    return p


def diff_paths(repo, base, candidate=None, worktree=False):
    paths = set()
    args = ["diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--name-only", "-z", "--ignore-submodules=none"]
    commands = [args + [base, candidate or commit(repo, "HEAD"), "--"]]
    if worktree:
        commands.extend([args + [base, "--"], args + ["--cached", base, "--"]])
    for cmd in commands:
        paths.update(os.fsdecode(x) for x in git(repo, *cmd).split(b"\0") if x)
    if worktree:
        paths.update(os.fsdecode(x) for x in git(repo, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0") if x)
    return sorted(paths)


def validate_policy(p):
    obj(p, {"schema_version", "task_id", "goal", "non_goals", "origin_revision", "base_revision", "scope", "contracts", "benefit", "review", "budget"}, "policy")
    require(p["schema_version"] == 1 and type(p["schema_version"]) is int, "unsupported policy schema")
    require(bool(IDENT.fullmatch(text(p["task_id"], "task_id"))), "invalid task_id")
    text(p["goal"], "goal")
    string_list(p["non_goals"], "non_goals")
    for key in ("origin_revision", "base_revision"):
        require(isinstance(p[key], str) and bool(SHA.fullmatch(p[key])), key + ": full SHA required")
    scope = obj(p["scope"], {"strategy", "allowed_paths", "protected_paths", "baseline_paths", "frozen_paths"}, "scope")
    require(scope["strategy"] in {"local", "shared"}, "strategy must be local or shared")
    for key in ("allowed_paths", "protected_paths", "baseline_paths", "frozen_paths"):
        for pat in string_list(scope[key], key, key in {"allowed_paths", "frozen_paths"}):
            relative_path(pat, patterns=True)
    ids = []
    for c in array(p["contracts"], "contracts", True):
        obj(c, {"id", "behavior", "oracle", "baseline_required", "red_control_required"}, "contract")
        require(bool(IDENT.fullmatch(text(c["id"], "contract.id"))), "invalid contract id")
        ids.append(c["id"])
        text(c["behavior"], "behavior")
        obj(c["oracle"], {"kind", "source"}, "oracle")
        require(c["oracle"]["kind"] in {"contract", "characterization"}, "invalid oracle kind")
        text(c["oracle"]["source"], "oracle.source")
        for key in ("baseline_required", "red_control_required"):
            boolean(c[key], key)
        require(not c["red_control_required"] or c["baseline_required"], "red control requires passing baseline")
    require(len(ids) == len(set(ids)), "duplicate contract IDs")
    obj(p["benefit"], {"required", "criterion"}, "benefit")
    boolean(p["benefit"]["required"], "benefit.required")
    text(p["benefit"]["criterion"], "benefit.criterion")
    obj(p["review"], {"independent_required"}, "review")
    boolean(p["review"]["independent_required"], "independent_required")
    obj(p["budget"], {"max_repairs", "max_replans"}, "budget")
    for value in p["budget"].values():
        require(type(value) is int and value >= 0, "budget values must be nonnegative integers")
    return p


def scope_result(repo, policy, worktree=False):
    base = commit(repo, policy["base_revision"])
    head = commit(repo, "HEAD")
    changed = diff_paths(repo, base, head, worktree)
    allowed, protected = policy["scope"]["allowed_paths"], policy["scope"]["protected_paths"]
    violations = []
    for path in changed:
        relative_path(path)
        if any_match(path, protected):
            violations.append({"path": path, "reason": "protected path changed"})
        elif not any_match(path, allowed):
            violations.append({"path": path, "reason": "outside approved path scope"})
    return {"base_revision": base, "candidate_revision": head, "worktree_included": worktree,
            "changed_paths": changed, "violations": violations,
            "result": "BLOCK" if violations else "PATH_SCOPE_OK",
            "limitation": "Path scope is not semantic impact analysis."}


def selected_entries(repo, revision, patterns):
    entries = tree_entries(repo, revision)
    for pat in patterns:
        require(any(any_match(path, [pat]) for path in entries), "frozen pattern matched nothing: " + pat)
    selected = {}
    for path, entry in sorted(entries.items()):
        if any_match(path, patterns):
            require(entry["kind"] == "blob" and entry["mode"] in {"100644", "100755"},
                    "frozen paths must be ordinary Git files, not symlinks/submodules: " + path)
            data = git(repo, "cat-file", "blob", entry["oid"])
            selected[path] = {"mode": entry["mode"], "oid": entry["oid"], "sha256": hashlib.sha256(data).hexdigest()}
    return selected


def make_seal(repo, policy, policy_path):
    require(ancestor(repo, policy["origin_revision"], policy["base_revision"]), "origin is not an ancestor of base")
    changes = diff_paths(repo, policy["origin_revision"], policy["base_revision"])
    for path in changes:
        require(any_match(path, policy["scope"]["baseline_paths"]) and not any_match(path, policy["scope"]["protected_paths"]),
                "baseline preparation changed an unapproved path: " + path)
    return {"schema_version": 1, "task_id": policy["task_id"], "base_revision": policy["base_revision"],
            "policy_sha256": sha256(policy_path),
            "files": selected_entries(repo, policy["base_revision"], policy["scope"]["frozen_paths"])}


def parse_junit(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink(), "JUnit report missing or symlinked")
    require(p.stat().st_size <= 20 * 1024 * 1024, "JUnit report exceeds 20 MiB")
    data = p.read_bytes()
    require(b"<!DOCTYPE" not in data.upper() and b"<!ENTITY" not in data.upper(), "DTD/entities are not accepted in JUnit")
    root = ET.fromstring(data)
    cases = [x for x in root.iter() if x.tag.rsplit("}", 1)[-1] == "testcase"]
    result = {"tests": len(cases), "executed": 0, "failures": 0, "errors": 0, "skipped": 0, "failed_tests": [], "passed_tests": [], "skipped_tests": []}
    for case in cases:
        tags = {x.tag.rsplit("}", 1)[-1] for x in case}
        test_name = ".".join(x for x in (case.get("classname", ""), case.get("name", "")) if x)
        if "skipped" in tags:
            result["skipped"] += 1
            result["skipped_tests"].append(test_name)
        else:
            result["executed"] += 1
        for kind, field in (("failure", "failures"), ("error", "errors")):
            if kind in tags:
                result[field] += 1
        if {"failure", "error"} & tags:
            result["failed_tests"].append(test_name)
        elif "skipped" not in tags:
            result["passed_tests"].append(test_name)
    return result


def artifact(path, parent):
    return {"path": Path(path).relative_to(parent).as_posix(), "sha256": sha256(path)}


def run_record(args):
    repo = repository(args.repo)
    before = snapshot(repo)
    out = outside_repo(args.out, repo)
    log = out.with_suffix(".log")
    copied_report = out.with_suffix(".junit.xml")
    require(out.suffix == ".json", "--out must end in .json")
    paths = [out, log, copied_report]
    require(not any(p.exists() or p.is_symlink() for p in paths), "output/evidence already exists; use a new run name")
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    require(bool(command) and all(isinstance(x, str) and x for x in command), "command argv required after --")
    require(math.isfinite(args.timeout) and args.timeout > 0, "timeout must be finite and positive")
    text(args.environment, "environment")
    for cid in args.contract:
        require(bool(IDENT.fullmatch(cid)), "invalid contract id")
    require(len(args.contract) == len(set(args.contract)), "duplicate contract IDs")
    if args.kind in {"baseline", "regression", "red-control"}:
        require(args.contract, "test evidence requires at least one --contract")
    report_source = Path(args.junit).absolute() if args.junit else None
    if report_source:
        require(not report_source.exists() and not report_source.is_symlink(), "JUnit must be a fresh report path; an existing report cannot be reused")
        require(report_source.resolve() not in {out, log}, "JUnit path conflicts with evidence output")
    if args.kind == "red-control":
        require(args.control_of is not None, "red-control requires --control-of <baseline SHA>")
        commit(repo, args.control_of)
        require(args.control_of != before["commit"] and ancestor(repo, args.control_of, before["commit"]),
                "red-control must run on a separate descendant of its baseline")
    else:
        require(args.control_of is None, "--control-of is only valid for red-control")
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    t0 = time.monotonic()
    timed_out = False
    error = None
    log.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(log), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        try:
            # Commands must already be authorized. This runner grants no sandbox or credentials.
            proc = subprocess.Popen(command, cwd=str(repo), stdin=subprocess.DEVNULL, stdout=f,
                                    stderr=subprocess.STDOUT, start_new_session=(os.name == "posix"))
            try:
                code = proc.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                if os.name == "posix":
                    import signal
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    proc.kill()
                proc.wait()
                code = 124
        except OSError as exc:
            code = 127
            error = str(exc)
            f.write(("runner launch error: " + error + "\n").encode())
    elapsed = round(time.monotonic() - t0, 6)
    try:
        after = snapshot(repo)
        stable = before == after
        state_error = None
    except InputError as exc:
        after, stable, state_error = None, False, str(exc)
    summary, report_artifact, report_error = None, None, None
    if report_source:
        try:
            summary = parse_junit(report_source)
            if report_source.resolve() != copied_report:
                create_bytes(copied_report, report_source.read_bytes())
            report_artifact = artifact(copied_report, out.parent)
        except (InputError, OSError, ET.ParseError) as exc:
            report_error = str(exc)
    record = {"schema_version": 1, "tool_version": VERSION, "kind": args.kind,
              "contracts": args.contract, "source": before, "source_after": after,
              "source_unchanged": stable, "source_error": state_error,
              "control_of_revision": args.control_of, "command": command,
              "environment": text(args.environment, "environment"), "started_at": started,
              "duration_seconds": elapsed, "exit_code": code, "timed_out": timed_out,
              "launch_error": error, "test_summary": summary, "report_error": report_error,
              "log": artifact(log, out.parent), "report": report_artifact}
    write_json(out, record)
    normal = code == 0 and stable and not timed_out and not error and not report_error
    if summary is not None and (summary["failures"] or summary["errors"] or
                                (args.kind in {"baseline", "regression"} and summary["executed"] == 0)):
        normal = False
    expected_red = (args.kind == "red-control" and code != 0 and not timed_out and stable
                    and not error and not report_error and summary is not None
                    and summary["failures"] > 0 and summary["errors"] == 0)
    if args.kind == "red-control":
        normal = False
    emit({"record": str(out), "exit_code": code, "source_unchanged": stable,
          "result": "RECORDED" if normal or expected_red else "RUN_NOT_ACCEPTABLE",
          "note": "Captured execution is not a semantic approval."})
    return 0 if normal or expected_red else 1


def confined_file(parent, rel):
    relative_path(rel)
    parent = Path(parent).resolve()
    p = parent / rel
    cur = parent
    for part in Path(rel).parts:
        cur = cur / part
        require(not cur.is_symlink(), "symlinks not allowed in evidence references: " + rel)
    require(p.resolve() != parent and parent in p.resolve().parents, "evidence reference escapes task directory")
    require(p.is_file(), "evidence file missing: " + rel)
    return p


def checked_artifact(parent, a):
    obj(a, {"path", "sha256"}, "artifact")
    require(isinstance(a["sha256"], str) and bool(DIGEST.fullmatch(a["sha256"])), "invalid artifact digest")
    p = confined_file(parent, a["path"])
    require(sha256(p) == a["sha256"], "artifact digest mismatch: " + a["path"])
    return p


def load_run(path):
    r = read_json(path)
    obj(r, {"schema_version", "tool_version", "kind", "contracts", "source", "source_after", "source_unchanged", "source_error", "control_of_revision", "command", "environment", "started_at", "duration_seconds", "exit_code", "timed_out", "launch_error", "test_summary", "report_error", "log", "report"}, "run")
    require(r["schema_version"] == 1 and r["kind"] in KINDS and r["tool_version"] == VERSION, "invalid run schema/kind/tool version")
    obj(r["source"], {"commit", "tree"}, "run.source")
    for value in r["source"].values():
        require(isinstance(value, str) and bool(SHA.fullmatch(value)), "invalid source object ID")
    require(r["source_unchanged"] is True and r["source_after"] == r["source"], "source changed during execution")
    require(type(r["exit_code"]) is int, "invalid exit code")
    require(r["timed_out"] is False and r["launch_error"] is None and r["report_error"] is None and r["source_error"] is None,
            "run failed due to timeout, environment, report or source error")
    text(r["environment"], "run.environment")
    text(r["started_at"], "run.started_at")
    require(type(r["duration_seconds"]) in {int, float} and r["duration_seconds"] >= 0, "invalid duration")
    string_list(r["contracts"], "run.contracts")
    array(r["command"], "run.command", True)
    for a in r["command"]:
        text(a, "command argument")
    checked_artifact(Path(path).parent, r["log"])
    if r["report"] is not None:
        report = checked_artifact(Path(path).parent, r["report"])
        require(parse_junit(report) == r["test_summary"], "test summary does not match JUnit artifact")
    else:
        require(r["test_summary"] is None, "test summary has no underlying report")
    return r


def valid_tests(run, kind, revision, cid):
    s = run["test_summary"]
    return (run["kind"] == kind and run["source"]["commit"] == revision and cid in run["contracts"]
            and run["exit_code"] == 0 and s is not None and s["executed"] > 0
            and s["failures"] == 0 and s["errors"] == 0)


def verify_gate(args):
    blocked, missing = [], []
    repo = repository(args.repo)
    policy = validate_policy(read_json(args.policy))
    policy_hash = sha256(args.policy)
    seal_hash = sha256(args.seal)
    for actual, trusted, label in ((policy_hash, args.approved_policy_sha256, "policy"),
                                   (seal_hash, args.approved_seal_sha256, "seal")):
        require(isinstance(trusted, str) and bool(DIGEST.fullmatch(trusted)), "trusted SHA256 required for " + label)
        if actual != trusted:
            blocked.append(label + " differs from the trusted approved digest")
    seal = read_json(args.seal)
    expected_seal = make_seal(repo, policy, args.policy)
    if seal != expected_seal:
        blocked.append("seal does not describe the approved baseline files/policy")
    state = snapshot(repo)
    current = state["commit"]
    if not ancestor(repo, policy["base_revision"], current):
        blocked.append("baseline is not an ancestor of candidate; re-plan rather than silently changing the base")
    scope = scope_result(repo, policy)
    blocked.extend(v["path"] + ": " + v["reason"] for v in scope["violations"])
    if not scope["changed_paths"]:
        missing.append("candidate contains no changes from the baseline")
    try:
        now_frozen = selected_entries(repo, current, policy["scope"]["frozen_paths"])
        if now_frozen != expected_seal["files"]:
            blocked.append("frozen assertions/fixtures changed, disappeared, or were added without a new baseline approval")
    except InputError as exc:
        blocked.append(str(exc))
    v = read_json(args.verification)
    obj(v, {"schema_version", "task_id", "base_revision", "candidate_revision", "policy_sha256", "seal_sha256", "decision", "implementer_session_id", "reviewer", "impact", "contracts", "benefit", "blocking_findings", "residual_risks"}, "verification")
    require(v["schema_version"] == 1, "invalid verification schema")
    for key, expected in (("task_id", policy["task_id"]), ("base_revision", policy["base_revision"]),
                          ("candidate_revision", current), ("policy_sha256", policy_hash), ("seal_sha256", seal_hash)):
        if v[key] != expected:
            missing.append("verification has stale or mismatching " + key)
    require(v["decision"] in {"PASS", "BLOCK", "INSUFFICIENT"}, "invalid semantic decision")
    if v["decision"] == "BLOCK":
        blocked.append("reviewer blocked this change")
    elif v["decision"] != "PASS":
        missing.append("reviewer has not issued a semantic PASS")
    reviewer = obj(v["reviewer"], {"session_id", "independent", "note"}, "reviewer")
    text(v["implementer_session_id"], "implementer_session_id")
    text(reviewer["session_id"], "reviewer.session_id")
    text(reviewer["note"], "reviewer.note")
    boolean(reviewer["independent"], "reviewer.independent")
    if policy["review"]["independent_required"]:
        if not reviewer["independent"] or reviewer["session_id"] == v["implementer_session_id"]:
            missing.append("independent review required; session fields are records, not identity authentication")
    impact = obj(v["impact"], {"reviewed_revision", "all_changed_paths_reviewed", "shared_state_reviewed", "unresolved"}, "impact")
    string_list(impact["unresolved"], "impact.unresolved")
    if (impact["reviewed_revision"] != current or impact["all_changed_paths_reviewed"] is not True
            or impact["shared_state_reviewed"] is not True or impact["unresolved"]):
        missing.append("actual-diff or shared-state impact review is incomplete/stale")
    string_list(v["blocking_findings"], "blocking_findings")
    string_list(v["residual_risks"], "residual_risks")
    blocked.extend(v["blocking_findings"])
    rows = {}
    for row in array(v["contracts"], "verification.contracts"):
        obj(row, {"id", "status", "tests", "assertion", "assertions_reviewed", "red_control_confirmed", "evidence"}, "contract verdict")
        require(row["id"] not in rows, "duplicate contract verdict")
        require(row["status"] in {"PASS", "BLOCK", "INSUFFICIENT"}, "invalid contract status")
        string_list(row["tests"], "contract.tests", True)
        text(row["assertion"], "contract.assertion")
        boolean(row["assertions_reviewed"], "assertions_reviewed")
        boolean(row["red_control_confirmed"], "red_control_confirmed")
        string_list(row["evidence"], "contract.evidence")
        rows[row["id"]] = row
    expected_ids = {c["id"] for c in policy["contracts"]}
    require(set(rows) <= expected_ids, "verification contains unapproved contract IDs")
    cache = {}

    def evidence(refs):
        results = []
        for ref in refs:
            try:
                path = confined_file(Path(args.verification).parent, ref)
                if path not in cache:
                    cache[path] = load_run(path)
                run = cache[path]
                # Check the recorded Git tree against the repository object, not only its string format.
                actual_tree = git(repo, "rev-parse", commit(repo, run["source"]["commit"]) + "^{tree}").decode().strip()
                require(actual_tree == run["source"]["tree"], "recorded source tree mismatch")
                results.append(run)
            except (InputError, OSError, ValueError, ET.ParseError) as exc:
                missing.append(ref + ": " + str(exc))
        return results

    for c in policy["contracts"]:
        cid = c["id"]
        if cid not in rows:
            missing.append(cid + ": no contract verdict")
            continue
        row = rows[cid]
        if row["status"] == "BLOCK":
            blocked.append(cid + ": reviewer found a contract violation")
        elif row["status"] != "PASS" or not row["assertions_reviewed"]:
            missing.append(cid + ": assertion sufficiency not established")
        runs = evidence(row["evidence"])
        current_runs = [r for r in runs if valid_tests(r, "regression", current, cid)]
        if not current_runs:
            missing.append(cid + ": no passing, nonempty, exact-candidate regression evidence")
        passed_names = {name for r in current_runs for name in r["test_summary"]["passed_tests"]}
        if not set(row["tests"]) <= passed_names:
            missing.append(cid + ": required named tests were not actually passed in candidate reports")
        if c["baseline_required"] and not any(valid_tests(r, "baseline", policy["base_revision"], cid) for r in runs):
            missing.append(cid + ": no passing baseline evidence")
        if c["red_control_required"]:
            red_ok = False
            for r in runs:
                s = r["test_summary"]
                if (r["kind"] == "red-control" and cid in r["contracts"] and r["control_of_revision"] == policy["base_revision"]
                        and r["source"]["commit"] != policy["base_revision"] and r["exit_code"] != 0
                        and s is not None and s["failures"] > 0 and s["errors"] == 0):
                    if ancestor(repo, policy["base_revision"], r["source"]["commit"]):
                        try:
                            red_ok = selected_entries(repo, r["source"]["commit"], policy["scope"]["frozen_paths"]) == expected_seal["files"]
                        except InputError:
                            red_ok = False
                    if red_ok:
                        break
            if not row["red_control_confirmed"] or not red_ok:
                missing.append(cid + ": expected red-control failure with unchanged frozen tests not established")
    benefit = obj(v["benefit"], {"status", "evidence", "note"}, "benefit verdict")
    require(benefit["status"] in {"PASS", "BLOCK", "INSUFFICIENT", "NOT_REQUIRED"}, "invalid benefit status")
    string_list(benefit["evidence"], "benefit.evidence")
    text(benefit["note"], "benefit.note")
    if policy["benefit"]["required"]:
        runs = evidence(benefit["evidence"])
        if benefit["status"] == "BLOCK":
            blocked.append("required benefit not achieved")
        elif benefit["status"] != "PASS" or not any(r["kind"] == "benefit" and r["source"]["commit"] == current and r["exit_code"] == 0 for r in runs):
            missing.append("required benefit lacks exact-candidate execution evidence and reviewer approval")
    elif benefit["status"] != "NOT_REQUIRED":
        missing.append("benefit verdict does not match policy (expected NOT_REQUIRED)")
    result = "BLOCK" if blocked else "INSUFFICIENT" if missing else "PASS_MECHANICAL"
    emit({"schema_version": 1, "result": result, "candidate_revision": current,
          "blocked": blocked, "missing": missing, "changed_paths": scope["changed_paths"],
          "limitation": "Checks metadata, artifacts, scope and revisions only; no semantic equivalence, identity or deployment authorization is proved."})
    return {"PASS_MECHANICAL": 0, "BLOCK": 1, "INSUFFICIENT": 2}[result]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("fingerprint", help="SHA256 of a file; not an approval")
    p.add_argument("--file", required=True)
    p = sub.add_parser("init", help="Create task files outside the repository; never overwrite")
    p.add_argument("--repo", required=True)
    p.add_argument("--task-dir", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--goal", required=True)
    for name in ("scope", "seal", "gate"):
        p = sub.add_parser(name)
        p.add_argument("--repo", required=True)
        p.add_argument("--policy", required=True)
        if name == "scope":
            p.add_argument("--worktree", action="store_true")
        if name == "seal":
            p.add_argument("--out", required=True)
        if name == "gate":
            p.add_argument("--seal", required=True)
            p.add_argument("--verification", required=True)
            p.add_argument("--approved-policy-sha256", required=True)
            p.add_argument("--approved-seal-sha256", required=True)
    p = sub.add_parser("run", help="Capture an already-authorized command in a clean checkout")
    p.add_argument("--repo", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--kind", choices=sorted(KINDS), required=True)
    p.add_argument("--contract", action="append", default=[])
    p.add_argument("--environment", required=True)
    p.add_argument("--junit")
    p.add_argument("--control-of")
    p.add_argument("--timeout", type=float, default=300)
    p.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if args.action == "fingerprint":
            print(sha256(args.file))
            return 0
        if args.action == "run":
            return run_record(args)
        if args.action == "gate":
            return verify_gate(args)
        repo = repository(args.repo)
        if args.action == "init":
            state = snapshot(repo)
            require(bool(IDENT.fullmatch(args.id)), "invalid task id")
            target = outside_repo(args.task_dir, repo)
            require(not target.exists(), "task directory already exists; resume it rather than overwriting")
            assets = Path(__file__).resolve().parent.parent / "assets"
            policy = read_json(assets / "policy.template.json")
            policy.update(task_id=args.id, goal=args.goal, origin_revision=state["commit"], base_revision=state["commit"])
            target.mkdir(parents=True)
            write_json(target / "policy.json", policy)
            for source, dest in (("work-item.md", "work-item.md"), ("impact.md", "impact-plan.md"),
                                 ("impact.md", "impact-actual.md"), ("baseline.md", "baseline.md"),
                                 ("verification.md", "verification.md"), ("verification.template.json", "verification.json"),
                                 ("release-handoff.md", "release-handoff.md")):
                create_bytes(target / dest, (assets / source).read_bytes())
            (target / "evidence").mkdir()
            emit({"task_directory": str(target), "result": "DRAFT_CREATED", "note": "Empty scope/contracts are deliberately not approvable."})
            return 0
        policy = validate_policy(read_json(args.policy))
        if args.action == "scope":
            result = scope_result(repo, policy, args.worktree)
            emit(result)
            return 1 if result["violations"] else 0
        if args.action == "seal":
            out = outside_repo(args.out, repo)
            write_json(out, make_seal(repo, policy, args.policy))
            emit({"seal": str(out), "sha256": sha256(out), "result": "SEALED_NOT_APPROVED"})
            return 0
    except (InputError, OSError, ValueError, KeyError, TypeError, ET.ParseError, subprocess.TimeoutExpired) as exc:
        emit({"result": "INSUFFICIENT", "error": str(exc)})
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
