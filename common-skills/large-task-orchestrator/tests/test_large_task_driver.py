"""用假 bb / bb-dispatch 验证 driver 的可观察行为：计划状态、Git checkpoint、线程调用序列与退出码。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
DRIVER = SKILL_DIR / "scripts" / "large_task_driver.py"
PLANNING = SKILL_DIR.parent / "large-task-planning" / "scripts" / "epic_story.py"

# 假 bb：所有线程状态在 world.json 里；每个线程按脚本化的 outputs 队列依次回复。
FAKE_BB = r'''#!/usr/bin/env python3
import fcntl, json, os, shlex, subprocess, sys
world_path = os.environ["FAKE_WORLD"]
world_handle = open(world_path, "r+", encoding="utf-8")
fcntl.flock(world_handle, fcntl.LOCK_EX)
world = json.load(world_handle)
args = [a for a in sys.argv[1:] if a != "--json"]
def save():
    world_handle.seek(0); json.dump(world, world_handle, ensure_ascii=False, indent=1)
    world_handle.truncate(); world_handle.flush()
def out(v): print(json.dumps(v, ensure_ascii=False)); sys.exit(0)
world.setdefault("calls", []).append(args)
save()
if args[:1] == ["status"]:
    out({"project": {"id": "proj"}, "thread": {"id": "thr_parent", "environment": {"display": {"id": "env"}}}})
if args[:2] == ["thread", "show"]:
    t = world["threads"][args[2]]
    thread = {"id": args[2], "status": t["status"]}
    if "updatedAt" in t:
        thread["updatedAt"] = t["updatedAt"]
    out({"thread": thread})
if args[:2] == ["thread", "wait"]:
    t = world["threads"][args[2]]
    wait_exit = 0
    # 每次 wait 消耗一条脚本化回复：线程从 active 变为 idle/error 并写入 output；副作用写文件模拟 Worker 改动。
    if t["status"] != "idle" and t["queue"]:
        step = t["queue"].pop(0)
        wait_exit = step.get("wait_exit", 0)
        t["status"] = step.get("status", "idle")
        t["output"] = step.get("output", "")
        for rel, content in step.get("files", {}).items():
            path = os.path.join(os.environ["FAKE_REPO"], rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "w").write(content)
        for role in ("worker", "validator", "judge"):
            report = step.get(f"{role}_report")
            if report is None:
                continue
            command_line = next(line for line in t["task"].splitlines() if f"large_task_report.py {role}" in line)
            command_line = command_line.split(" <<", 1)[0]
            subprocess.run(
                shlex.split(command_line), input=json.dumps(report, ensure_ascii=False),
                text=True, check=True, capture_output=True,
            )
        for thread_id in step.get("clear_interactions_for", []):
            world["threads"][thread_id]["interactions"] = []
        if step.get("render_plan"):
            subprocess.run([sys.executable, os.environ["FAKE_PLANNING"], "render",
                            "--plan", os.environ["FAKE_PLAN"], "--stories-dir", os.environ["FAKE_STORIES"]],
                           check=True, capture_output=True)
        save()
    print(json.dumps({"status": t["status"]}, ensure_ascii=False)); sys.exit(wait_exit)
if args[:2] == ["thread", "output"]:
    out({"output": world["threads"][args[2]]["output"]})
if args[:3] == ["thread", "interactions", "list"]:
    out(world["threads"][args[3]].get("interactions", []))
if args[:2] == ["thread", "tell"]:
    t = world["threads"][args[2]]
    t["status"] = "active"; t.setdefault("tells", []).append(args[3]); save()
    out({"ok": True})
if args[:2] == ["thread", "retry"]:
    world["threads"][args[2]]["status"] = "active"; save(); out({"ok": True})
if args[:2] == ["thread", "stop"]:
    world["threads"][args[2]]["status"] = "error"; save(); out({"ok": True})
print("unknown fake bb call: " + " ".join(args), file=sys.stderr); sys.exit(1)
'''

FAKE_DISPATCH = r'''#!/usr/bin/env python3
import fcntl, json, os, sys
world_path = os.environ["FAKE_WORLD"]
world_handle = open(world_path, "r+", encoding="utf-8")
fcntl.flock(world_handle, fcntl.LOCK_EX)
world = json.load(world_handle)
args = sys.argv[1:]
def get(flag):
    return args[args.index(flag) + 1] if flag in args else None
if "--dry-run" in args:
    print(json.dumps({"dry_run": True, "selection": {"difficulty": get("--difficulty"), "kind": get("--kind")}}))
    sys.exit(0)
title = get("--title"); role = title.split()[-1]; story = title.split()[0]
key = f"{story}:{role}"
scripts = world["scripts"].get(key) or []
index = world.setdefault("spawned", {}).get(key, 0)
queue = scripts[index] if index < len(scripts) else [{"output": "Result: failed\nChanged: none\nVerified: none\nRemaining: all\nHandoff: no script"}]
world["spawned"][key] = index + 1
thread_id = f"thr_{role}_{story.lower().replace('-', '')}_{index + 1}"
world["threads"][thread_id] = {"status": "active", "output": "", "queue": list(queue), "task": get("--task"),
                               "difficulty": get("--difficulty"), "kind": get("--kind"),
                               "interactions": list(world.get("interactions", {}).get(key, []))}
world.setdefault("dispatches", []).append({"thread": thread_id, "difficulty": get("--difficulty"), "kind": get("--kind"), "title": title})
world_handle.seek(0); json.dump(world, world_handle, ensure_ascii=False, indent=1)
world_handle.truncate(); world_handle.flush()
print(json.dumps({"dry_run": False, "selection": {"provider": "p", "model": "m", "difficulty": get("--difficulty"), "kind": get("--kind")},
                  "result": {"id": thread_id, "status": "queued"}}))
'''

WORKER_DONE = "Result: worker_done\nChanged: 新增 src/feature.py 提供公开入口\nVerified: python3 -m unittest：退出码 0\nRemaining: none\nHandoff: 公开入口在 src/feature.py。"
WORKER_FILES = {"src/feature.py": "def feature():\n    return 1\n"}
VALIDATOR_PASS = "Verdict: PASS\nAcceptance:\n- AC-01: holds — 运行公开入口返回 1\nGaps: none\nNew facts: none"
VALIDATOR_FAIL = "Verdict: FAIL\nAcceptance:\n- AC-01: missing — 入口返回 None\nGaps: 缺少返回值\nNew facts: none"


def plan_data() -> dict[str, Any]:
    return {
        "kind": "large-task-plan", "schema_version": 2, "id": "EPIC-DEMO", "title": "演示", "goal_version": 1,
        "updated": "2026-09-09", "language": "zh-Hans",
        "spec": {
            "problem_statement": "缺少公开入口。", "solution": "提供公开入口。",
            "user_stories": [{"id": "US-01", "actor": "用户", "want": "调用入口", "benefit": "得到结果"}],
            "boundaries": ["兼容。"],
            "decisions": [{"id": "D-01", "decision": "复用入口", "rationale": "稳定。", "impact": "无。", "owner": "agent"}],
            "testing": {"seams": ["公开函数。"], "strategy": "先失败再实现。"},
            "out_of_scope": ["发布。"],
        },
        "golden_acceptance": [{"id": "GC-01", "title": "调用", "fixture": ["无"], "actions": ["调用"], "oracle": ["返回 1"], "evidence": ["输出"]}],
        "final_story": "STORY-02",
    }


def story_data(story_id: str, blocked_by: list[str]) -> dict[str, Any]:
    return {
        "kind": "large-task-story", "schema_version": 2, "id": story_id, "plan": "EPIC-DEMO",
        "title": f"{story_id} 结果", "intent_version": 1, "status": "todo", "blocked_by": blocked_by, "covers": ["GC-01"],
        "outcome": "公开入口可用。",
        "acceptance": [{"id": "AC-01", "criterion": "调用入口返回 1。", "passed": False}],
        "context": {"test_seams": ["feature()"], "code_anchors": ["src/feature.py"], "authoritative_inputs": ["SPEC"],
                    "write_scope": ["src/"], "stop_conditions": ["改变边界。"]},
        "owner": None, "blocker": None, "updated": "2026-09-09", "handoff": None,
    }


class DriverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        (self.repo / "plan" / "agent" / "stories").mkdir(parents=True)
        for name, content in (("bb", FAKE_BB), ("bb-dispatch", FAKE_DISPATCH)):
            path = self.bin / name
            path.write_text(content, encoding="utf-8")
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        self.world = self.root / "world.json"
        self.plan = self.repo / "plan" / "agent" / "plan.json"
        self.stories = self.repo / "plan" / "agent" / "stories"
        (self.repo / ".gitignore").write_text(".local/\n", encoding="utf-8")
        self.write_json(self.plan, plan_data())
        self.write_json(self.stories / "STORY-01-first.json", story_data("STORY-01", []))
        self.write_json(self.stories / "STORY-02-final.json", story_data("STORY-02", ["STORY-01"]))
        self.planning("render")
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "plan")
        self.background_pids: list[int] = []

    def tearDown(self) -> None:
        for pid in reversed(self.background_pids):
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                continue
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.05)
            else:
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        self.temporary.cleanup()

    @staticmethod
    def write_json(path: Path, value: dict[str, Any]) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def git(self, *arguments: str) -> str:
        return subprocess.run(["git", *arguments], cwd=self.repo, capture_output=True, text=True, check=True).stdout

    def planning(self, command: str, *, plan: Path | None = None, stories: Path | None = None) -> None:
        subprocess.run([sys.executable, str(PLANNING), command, "--plan", str(plan or self.plan),
                        "--stories-dir", str(stories or self.stories)],
                       check=True, capture_output=True)

    def set_world(self, scripts: dict[str, list[list[dict[str, Any]]]]) -> None:
        interactions = scripts.get("interactions", {})
        normalized: dict[str, Any] = {}
        value_aliases = {"完成": "worker_done", "已完成": "worker_done", "阻塞": "blocked", "失败": "failed"}
        verdict_aliases = {"通过": "PASS", "未通过": "FAIL", "失败": "FAIL"}
        action_aliases = {"重试": "retry", "升档": "escalate", "修补": "patch", "阻塞": "block",
                          "重规划": "replan", "停止": "stop"}
        for key, attempts in scripts.items():
            if key == "interactions":
                continue
            normalized[key] = []
            for queue in attempts:
                normalized_queue = []
                queue_paths = sorted({
                    path
                    for queued_step in queue
                    for path in queued_step.get("files", {})
                    if not path.startswith(("plan/", ".local/"))
                })
                for original in queue:
                    step = dict(original)
                    output = str(step.get("output") or "")
                    match = re.search(
                        r"^(?:Result|结果|状态)\s*[:：]\s*(worker_done|blocked|failed|完成|已完成|阻塞|失败)",
                        output, re.MULTILINE,
                    )
                    if key.endswith(":worker") and match and "worker_report" not in step:
                        result = value_aliases.get(match.group(1), match.group(1))
                        step["worker_report"] = {
                            "result": result,
                            "changes": [{"path": path, "summary": "脚本化 Worker 改动"} for path in queue_paths],
                            "verification": [{
                                "command": "scripted verification", "outcome": "passed", "summary": "脚本化结果",
                            }],
                            "remaining": [] if result == "worker_done" else ["脚本化未完成事项"],
                            "handoff": "脚本化交接。",
                        }
                    verdict_match = re.search(
                        r"^(?:Verdict|结论|判定)\s*[:：]\s*(PASS|FAIL|通过|未通过|失败)", output, re.MULTILINE,
                    )
                    if key.endswith(":validator") and verdict_match and "validator_report" not in step:
                        verdict = verdict_aliases.get(verdict_match.group(1), verdict_match.group(1))
                        worker_key = f"{key.split(':', 1)[0]}:worker"
                        worker_attempt = scripts.get(worker_key, [[]])[-1]
                        explicit_reports = [
                            queued_step["worker_report"]
                            for queued_step in worker_attempt
                            if "worker_report" in queued_step
                        ]
                        if explicit_reports:
                            attributed_paths = [item["path"] for item in explicit_reports[-1]["changes"]]
                        else:
                            attributed_paths = sorted({
                                path
                                for queued_step in worker_attempt
                                for path in queued_step.get("files", {})
                                if not path.startswith(("plan/", ".local/"))
                            })
                        acceptance = []
                        for acceptance_id, raw_outcome, evidence in re.findall(
                            r"^\s*[-*]?\s*(AC-[A-Za-z0-9.-]+)\s*[:：]\s*(holds|missing|成立|缺失|不成立)\s*(?:[—-]\s*)?(.*)$",
                            output, re.MULTILINE,
                        ):
                            outcome = "holds" if raw_outcome in ("holds", "成立") else "missing"
                            acceptance.append({"id": acceptance_id, "outcome": outcome,
                                               "evidence": evidence.strip() or "脚本化证据"})
                        gap_match = re.search(r"^(?:Gaps|缺口)\s*[:：]\s*(.*)$", output, re.MULTILINE)
                        facts_match = re.search(r"^(?:New facts|新事实)\s*[:：]\s*(.*)$", output, re.MULTILINE)
                        gap = gap_match.group(1).strip() if gap_match else ""
                        fact = facts_match.group(1).strip() if facts_match else ""
                        step["validator_report"] = {
                            "verdict": verdict,
                            "acceptance": acceptance,
                            "worker_paths": attributed_paths,
                            "gaps": [] if gap.lower() in ("", "none", "无", "无。") else [gap],
                            "new_facts": [] if fact.lower() in ("", "none", "无", "无。") else [fact],
                        }
                    action_match = re.search(
                        r"^(?:Action|动作|决定)\s*[:：]\s*(retry|escalate|patch|block|replan|stop|重试|升档|修补|阻塞|重规划|停止)",
                        output, re.MULTILINE,
                    )
                    if key.endswith(":judge") and action_match and "judge_report" not in step:
                        action = action_aliases.get(action_match.group(1), action_match.group(1))
                        note_match = re.search(r"^(?:Note|说明|备注|原因)\s*[:：]\s*(.*)$", output, re.MULTILINE)
                        step["judge_report"] = {
                            "action": action,
                            "note": note_match.group(1).strip() if note_match else "脚本化裁决。",
                        }
                    normalized_queue.append(step)
                normalized[key].append(normalized_queue)
        self.write_json(self.world, {
            "threads": {},
            "scripts": normalized,
            "interactions": interactions,
        })

    def read_world(self) -> dict[str, Any]:
        return json.loads(self.world.read_text(encoding="utf-8"))

    def worker_report_path(self, story_id: str, attempt: int) -> Path:
        digest = hashlib.sha256(b"plan").hexdigest()[:10]
        return (
            self.repo / ".local" / "large-task-orchestrator" / f"plan-{digest}"
            / "reports" / story_id / f"attempt-{attempt}-worker.json"
        )

    def run_command(self, command: str, *extra: str, expected: int = 0, plan: Path | None = None,
                    stories: Path | None = None) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
               "FAKE_WORLD": str(self.world), "FAKE_REPO": str(self.repo),
               "FAKE_PLANNING": str(PLANNING), "FAKE_PLAN": str(self.plan), "FAKE_STORIES": str(self.stories)}
        result = subprocess.run(
            [sys.executable, str(DRIVER), command, "--plan", str(plan or self.plan),
             "--stories-dir", str(stories or self.stories),
             "--repository", str(self.repo), "--dispatch", str(self.bin / "bb-dispatch"), "--poll-seconds", "1", *extra],
            cwd=self.repo, env=env, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, expected, result.stderr + result.stdout)
        return result

    def run_driver(self, *extra: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        return self.run_command("run", *extra, expected=expected)

    def start_driver(self, *extra: str, plan: Path | None = None, stories: Path | None = None) -> int:
        result = self.run_command("start", *extra, plan=plan, stories=stories)
        marker = "STARTED: pid="
        pid = int(next(line[len(marker):] for line in result.stdout.splitlines() if line.startswith(marker)))
        self.background_pids.append(pid)
        return pid

    def status_payload(self, *, plan: Path | None = None, stories: Path | None = None) -> dict[str, Any]:
        result = self.run_command("status", "--json", plan=plan, stories=stories)
        return json.loads(result.stdout)

    def wait_for(self, predicate: Any, *, timeout: float = 5) -> Any:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(0.05)
        self.fail("等待后台 driver 状态超时")

    def wait_for_driver_exit(self, *, plan: Path | None = None, stories: Path | None = None) -> dict[str, Any]:
        return self.wait_for(lambda: payload if not (payload := self.status_payload(plan=plan, stories=stories))["alive"] else None)

    def add_one_story_plan(self, topic: str, story_id: str) -> tuple[Path, Path]:
        plan = self.repo / topic / "agent" / "plan.json"
        stories = plan.parent / "stories"
        stories.mkdir(parents=True)
        data = plan_data()
        data["id"] = f"EPIC-{story_id}"
        data["final_story"] = story_id
        self.write_json(plan, data)
        story = story_data(story_id, [])
        story["plan"] = data["id"]
        self.write_json(stories / f"{story_id}.json", story)
        self.planning("render", plan=plan, stories=stories)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", f"add {topic}")
        return plan, stories

    def story(self, story_id: str) -> dict[str, Any]:
        for path in self.stories.glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            if data["id"] == story_id:
                return data
        raise AssertionError(story_id)

    def add_story(self, story_id: str, blocked_by: list[str]) -> None:
        self.write_json(self.stories / f"{story_id}-extra.json", story_data(story_id, blocked_by))
        final = self.story("STORY-02")
        final["blocked_by"].append(story_id)
        self.write_json(self.stories / "STORY-02-final.json", final)
        self.planning("render")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", f"add {story_id}")

    def test_happy_path_completes_plan_with_checkpoints_and_validator(self) -> None:
        self.set_world({
            "STORY-01:worker": [[{"output": WORKER_DONE, "files": WORKER_FILES}]],
            "STORY-01:validator": [[{"output": VALIDATOR_PASS}]],
            "STORY-02:worker": [[{"output": WORKER_DONE, "files": {"src/final.py": "x = 1\n"}}]],
            "STORY-02:validator": [[{"output": VALIDATOR_PASS}]],
        })
        result = self.run_driver()
        self.assertIn("DONE", result.stdout)
        self.assertEqual(self.story("STORY-01")["status"], "done")
        self.assertEqual(self.story("STORY-02")["status"], "done")
        self.assertTrue(self.story("STORY-01")["acceptance"][0]["passed"])
        self.assertIn("thr_worker_story01_1", self.story("STORY-01")["handoff"]["next"])
        log = self.git("log", "--oneline")
        self.assertIn("checkpoint(STORY-01)", log)
        self.assertIn("checkpoint(STORY-02)", log)
        self.assertEqual(self.git("status", "--short").strip(), "")
        dispatches = self.read_world()["dispatches"]
        self.assertEqual([d["title"] for d in dispatches],
                         ["STORY-01 worker", "STORY-01 validator", "STORY-02 worker", "STORY-02 validator"])
        self.assertEqual(dispatches[1]["kind"], "test")
        self.assertEqual(dispatches[1]["difficulty"], "simple")
        self.assertFalse(any(call[:2] == ["thread", "output"] for call in self.read_world()["calls"]))
        worker_task = self.read_world()["threads"]["thr_worker_story01_1"]["task"]
        self.assertIn("large_task_report.py worker", worker_task)
        self.assertIn("src/", worker_task)
        validator_task = self.read_world()["threads"]["thr_validator_story01_1"]["task"]
        self.assertIn("large_task_report.py validator", validator_task)

    def test_validator_fail_is_sent_back_to_same_worker_then_passes(self) -> None:
        self.set_world({
            "STORY-01:worker": [[{"output": WORKER_DONE, "files": WORKER_FILES},
                                 {"output": WORKER_DONE, "files": {"src/feature.py": "def feature():\n    return 1  # fixed\n"}}]],
            "STORY-01:validator": [[{"output": VALIDATOR_FAIL}], [{"output": VALIDATOR_PASS}]],
        })
        self.run_driver("--max-stories", "1")
        self.assertEqual(self.story("STORY-01")["status"], "done")
        world = self.read_world()
        tells = world["threads"]["thr_worker_story01_1"]["tells"]
        self.assertEqual(len(tells), 1)
        self.assertIn("AC-01", tells[0])
        self.assertIn("缺少返回值", tells[0])
        self.assertEqual(world["spawned"]["STORY-01:validator"], 2)
        self.assertEqual(world["spawned"]["STORY-01:worker"], 1)

    def test_worker_human_reply_language_does_not_affect_structured_report(self) -> None:
        worker_cn = "结果：worker_done\n已变更：新增 src/feature.py\n已验证：python3 -m unittest：退出码 0\n剩余工作：无\n交接说明：入口在 src/feature.py。"
        validator_cn = "结论：PASS\n验收：\n- AC-01: 成立 — 返回 1\n缺口：无\n新事实：无"
        self.set_world({
            "STORY-01:worker": [[{"output": worker_cn, "files": WORKER_FILES}]],
            "STORY-01:validator": [[{"output": validator_cn}]],
        })
        self.run_driver("--max-stories", "1")
        self.assertEqual(self.story("STORY-01")["status"], "done")
        self.assertNotIn("STORY-01:judge", self.read_world().get("spawned", {}))
        self.assertEqual(self.story("STORY-01")["handoff"]["risks"], [])

    def test_worker_artifact_is_authoritative_instead_of_final_text(self) -> None:
        report_path = self.worker_report_path("STORY-01", 1)
        report = {
            "schema_version": 1,
            "role": "worker",
            "story_id": "STORY-01",
            "attempt": 1,
            "intent_version": 1,
            "submitted_at": "2026-09-10T12:00:00+00:00",
            "report": {
                "result": "worker_done",
                "changes": [{"path": "src/feature.py", "summary": "新增公开入口"}],
                "verification": [{"command": "python3 -m unittest", "outcome": "passed", "summary": "通过"}],
                "remaining": [],
                "handoff": "公开入口可供下一张 Story 使用。",
            },
        }
        report_file = os.path.relpath(report_path, self.repo)
        self.set_world({
            "STORY-01:worker": [[
                {
                    "output": "报告已提交。",
                    "files": {**WORKER_FILES, report_file: json.dumps(report, ensure_ascii=False)},
                },
                {"output": "报告已提交。"},
            ]],
            "STORY-01:validator": [[{"output": VALIDATOR_PASS}]],
            "STORY-01:judge": [[{"output": "Action: stop\nNote: 不应依赖自然语言终答。"}]],
        })

        self.run_driver("--max-stories", "1")

        self.assertEqual(self.story("STORY-01")["status"], "done")
        self.assertNotIn("STORY-01:judge", self.read_world().get("spawned", {}))
        task = self.read_world()["threads"]["thr_worker_story01_1"]["task"]
        self.assertIn("large_task_report.py worker", task)

    def test_validator_artifact_is_authoritative_instead_of_final_text(self) -> None:
        validator_report = {
            "verdict": "PASS",
            "acceptance": [{"id": "AC-01", "outcome": "holds", "evidence": "公开入口返回 1"}],
            "worker_paths": ["src/feature.py"],
            "gaps": [],
            "new_facts": [],
        }
        self.set_world({
            "STORY-01:worker": [[{"output": WORKER_DONE, "files": WORKER_FILES}]],
            "STORY-01:validator": [[{
                "output": "Verdict: FAIL\nAcceptance:\n- AC-01: missing — 不应读取此文本\nGaps: 文本无效",
                "validator_report": validator_report,
            }]],
        })

        self.run_driver("--max-stories", "1")

        self.assertEqual(self.story("STORY-01")["status"], "done")
        self.assertNotIn("STORY-01:judge", self.read_world().get("spawned", {}))

    def test_judge_artifact_is_authoritative_instead_of_final_text(self) -> None:
        self.set_world({
            "STORY-01:worker": [[{
                "output": "Result: failed\nChanged: none\nVerified: failed\nRemaining: 实现失败\nHandoff: 交给 Judge",
            }]],
            "STORY-01:judge": [[{
                "output": "Action: patch\nNote: 不应读取此文本。",
                "judge_report": {"action": "stop", "note": "结构化裁决要求用户处理。"},
            }]],
        })

        result = self.run_driver(expected=3)

        self.assertIn("结构化裁决要求用户处理", result.stderr)

    def test_missing_validator_artifact_gets_one_same_thread_report_request(self) -> None:
        self.set_world({
            "STORY-01:worker": [[{"output": WORKER_DONE, "files": WORKER_FILES}]],
            "STORY-01:validator": [[{"output": "核验完成。"}, {"output": VALIDATOR_PASS}]],
        })

        self.run_driver("--max-stories", "1")

        world = self.read_world()
        self.assertEqual(self.story("STORY-01")["status"], "done")
        self.assertEqual(world["spawned"]["STORY-01:validator"], 1)
        tells = world["threads"]["thr_validator_story01_1"]["tells"]
        self.assertEqual(len(tells), 1)
        self.assertIn("large_task_report.py validator", tells[0])

    def test_missing_judge_artifact_gets_one_same_thread_report_request(self) -> None:
        self.set_world({
            "STORY-01:worker": [[{
                "output": "Result: failed\nChanged: none\nVerified: failed\nRemaining: 实现失败\nHandoff: 交给 Judge",
            }]],
            "STORY-01:judge": [[
                {"output": "已完成裁决。"},
                {"output": "Action: stop\nNote: 第二次提交结构化裁决。"},
            ]],
        })

        result = self.run_driver(expected=3)

        self.assertIn("第二次提交结构化裁决", result.stderr)
        world = self.read_world()
        self.assertEqual(world["spawned"]["STORY-01:judge"], 1)
        tells = world["threads"]["thr_judge_story01_1"]["tells"]
        self.assertEqual(len(tells), 1)
        self.assertIn("large_task_report.py judge", tells[0])

    def test_missing_worker_artifact_gets_one_report_request_before_judge(self) -> None:
        self.set_world({
            "STORY-01:worker": [[{"output": "我做完了，测试都通过。", "files": WORKER_FILES},
                                 {"output": WORKER_DONE}]],
            "STORY-01:validator": [[{"output": VALIDATOR_PASS}]],
        })
        self.run_driver("--max-stories", "1")
        self.assertEqual(self.story("STORY-01")["status"], "done")
        world = self.read_world()
        self.assertNotIn("STORY-01:judge", world.get("spawned", {}))
        tells = world["threads"]["thr_worker_story01_1"]["tells"]
        self.assertEqual(len(tells), 1)
        self.assertIn("large_task_report.py worker", tells[0])

    def test_validator_task_marks_driver_managed_paths_as_not_out_of_scope(self) -> None:
        self.set_world({
            "STORY-01:worker": [[{"output": WORKER_DONE, "files": WORKER_FILES}]],
            "STORY-01:validator": [[{"output": VALIDATOR_PASS}]],
        })
        self.run_driver("--max-stories", "1")
        task = self.read_world()["threads"]["thr_validator_story01_1"]["task"]
        self.assertIn("不算越界", task)
        self.assertIn("plan/STATUS.md", task)
        self.assertIn("plan/agent/stories/STORY-01-first.json", task)
        self.assertIn("large_task_report.py validator", task)
        self.assertIn("--acceptance-id AC-01", task)
        self.assertIn("bb thread log thr_worker_story01_1 --all --json", task)
        self.assertIn("mtime 和 Worker 活跃时间窗口都不能证明归属", task)
        self.assertIn("只有确认由当前 Worker 修改", task)

    def test_standard_up_explicitly_skips_validator_for_simple_story(self) -> None:
        self.set_world({"STORY-01:worker": [[{"output": WORKER_DONE, "files": WORKER_FILES}]]})
        self.run_driver("--max-stories", "1", "--default-difficulty", "simple", "--validator", "standard-up")
        self.assertEqual(self.story("STORY-01")["status"], "done")
        self.assertNotIn("STORY-01:validator", self.read_world().get("spawned", {}))
        self.assertTrue(any("Validator skipped" in item for item in self.story("STORY-01")["handoff"]["verification"]))

    def test_story_routing_overrides_default_difficulty_and_kind(self) -> None:
        first = self.story("STORY-01")
        first["difficulty"] = "simple"
        self.write_json(self.stories / "STORY-01-first.json", first)
        second = self.story("STORY-02")
        second["difficulty"] = "complex"
        second["kind"] = "debug"
        self.write_json(self.stories / "STORY-02-final.json", second)
        self.planning("render")
        self.set_world({
            "STORY-01:worker": [[{"output": WORKER_DONE, "files": WORKER_FILES}]],
            "STORY-02:worker": [[{"output": WORKER_DONE, "files": {"src/final.py": "done = True\n"}}]],
            "STORY-02:validator": [[{"output": VALIDATOR_PASS}]],
        })
        self.run_driver("--default-difficulty", "medium", "--validator", "standard-up")
        workers = [item for item in self.read_world()["dispatches"] if item["title"].endswith("worker")]
        self.assertEqual(
            [(item["title"], item["difficulty"], item["kind"]) for item in workers],
            [("STORY-01 worker", "simple", "general"), ("STORY-02 worker", "complex", "debug")],
        )
        self.assertNotIn("STORY-01:validator", self.read_world().get("spawned", {}))

    def test_stalled_worker_is_stopped_then_retried(self) -> None:
        self.set_world({"STORY-01:worker": [[{"status": "active"}]]})
        self.run_driver("--once")
        self.run_driver("--once", "--stall-minutes", "0")
        world = self.read_world()
        self.assertIn(["thread", "stop", "thr_worker_story01_1"], world["calls"])
        self.assertIn(["thread", "retry", "thr_worker_story01_1"], world["calls"])
        payload = self.status_payload()
        self.assertTrue(any(event["event"] == "thread.stalled" for event in payload["recent_events"]))

    def test_external_worker_resume_refreshes_stall_watchdog(self) -> None:
        self.set_world({"STORY-01:worker": [[{"status": "active"}]]})
        self.run_driver("--once")
        state_path = next((self.repo / ".local" / "large-task-orchestrator").glob("*/state.json"))
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["thread_events"]["thr_worker_story01_1"] = time.time() - 7200
        self.write_json(state_path, state)
        world = self.read_world()
        world["threads"]["thr_worker_story01_1"]["updatedAt"] = int(time.time() * 1000)
        self.write_json(self.world, world)

        self.run_driver("--once", "--stall-minutes", "1")

        calls = self.read_world()["calls"]
        self.assertNotIn(["thread", "stop", "thr_worker_story01_1"], calls)
        self.assertNotIn(["thread", "retry", "thr_worker_story01_1"], calls)

    def test_stalled_validator_is_reassigned(self) -> None:
        self.set_world({
            "STORY-01:worker": [[{"output": WORKER_DONE, "files": WORKER_FILES}]],
            "STORY-01:validator": [[{"status": "active"}], [{"output": VALIDATOR_PASS}]],
        })
        self.run_driver("--once")
        self.run_driver("--once")
        self.run_driver("--once", "--stall-minutes", "0")
        world = self.read_world()
        self.assertIn(["thread", "stop", "thr_validator_story01_1"], world["calls"])
        self.assertEqual(world["spawned"]["STORY-01:validator"], 2)

    def test_no_progress_watchdog_stops_a_busy_driver(self) -> None:
        self.set_world({"STORY-01:worker": [[{"status": "active"}]]})
        result = self.run_driver("--no-progress-hours", "0.0001", "--stall-minutes", "90", expected=3)
        self.assertIn("没有新的 story.done", result.stderr)
        self.assertIn("没有新的 story.done", self.status_payload()["last_stop"])

    def test_global_worker_and_judge_limits_stop_before_new_thread(self) -> None:
        self.set_world({
            "STORY-01:worker": [[{
                "output": "Result: failed\nChanged: none\nVerified: 红\nRemaining: all\nHandoff: 需要重试"
            }]],
            "STORY-01:judge": [[{"output": "Action: retry\nNote: 重试。"}]],
        })
        workers_limited = self.run_driver("--max-workers-total", "1", expected=3)
        self.assertIn("全局 Worker 总量已达上限 1/1", workers_limited.stderr)
        payload = self.status_payload()
        self.assertEqual(payload["safeguards"]["counters"]["workers_total"], 1)
        self.assertEqual(payload["safeguards"]["thresholds"]["max_workers_total"], 1)

    def test_global_judge_limit_stops_before_judge_thread(self) -> None:
        self.set_world({
            "STORY-01:worker": [[{
                "output": "Result: blocked\nChanged: none\nVerified: none\nRemaining: 缺少凭据\nHandoff: 等待凭据"
            }]],
        })
        result = self.run_driver("--max-judges-total", "0", expected=3)
        self.assertIn("全局 Judge 总量已达上限 0/0", result.stderr)
        payload = self.status_payload()
        self.assertEqual(payload["safeguards"]["counters"]["judges_total"], 0)
        self.assertEqual(payload["safeguards"]["thresholds"]["max_judges_total"], 0)

    def test_second_block_of_reopened_story_stops_with_persistent_counter(self) -> None:
        blocked_worker = {
            "output": "Result: blocked\nChanged: none\nVerified: none\nRemaining: 缺少凭据\nHandoff: 等待凭据"
        }
        self.set_world({
            "STORY-01:worker": [[blocked_worker]],
            "STORY-01:judge": [[{"output": "Action: block\nNote: 等待凭据。"}]],
        })
        self.run_driver(expected=3)
        reopened = self.story("STORY-01")
        reopened.update({"status": "todo", "owner": None, "blocker": None})
        self.write_json(self.stories / "STORY-01-first.json", reopened)
        self.planning("render")
        self.set_world({
            "STORY-01:worker": [[blocked_worker]],
            "STORY-01:judge": [[{"output": "Action: block\nNote: 仍在等待凭据。"}]],
        })
        result = self.run_driver(expected=3)
        self.assertIn("累计进入 blocked 2 次", result.stderr)
        payload = self.status_payload()
        self.assertEqual(payload["safeguards"]["counters"]["blocked_by_story"]["STORY-01"], 2)

    def test_worker_blocked_consults_judge_and_stop_returns_to_user(self) -> None:
        self.set_world({
            "STORY-01:worker": [[{"output": "Result: blocked\nChanged: none\nVerified: none\nRemaining: 缺少凭据\nHandoff: 需要 API key"}]],
            "STORY-01:judge": [[{"output": "Action: stop\nNote: 需要用户提供 API key 才能继续。"}]],
        })
        result = self.run_driver(expected=3)
        self.assertIn("需要用户提供 API key", result.stderr)
        self.assertEqual(self.story("STORY-01")["status"], "in_progress")
        dispatches = self.read_world()["dispatches"]
        self.assertEqual(dispatches[-1]["title"], "STORY-01 judge")
        self.assertEqual(dispatches[-1]["difficulty"], "complex")
        self.assertEqual(dispatches[-1]["kind"], "judge")
        judge_task = self.read_world()["threads"][dispatches[-1]["thread"]]["task"]
        self.assertIn("Worker 报告 blocked", judge_task)

    def test_judge_escalate_spawns_higher_difficulty_worker(self) -> None:
        self.set_world({
            "STORY-01:worker": [[{"output": "Result: failed\nChanged: none\nVerified: 测试仍红\nRemaining: 全部\nHandoff: 实现不出来"}],
                                [{"output": WORKER_DONE, "files": WORKER_FILES}]],
            "STORY-01:judge": [[{"output": "Action: escalate\nNote: 能力不足。"}]],
            "STORY-01:validator": [[{"output": VALIDATOR_PASS}]],
        })
        self.run_driver("--max-stories", "1")
        self.assertEqual(self.story("STORY-01")["status"], "done")
        workers = [d for d in self.read_world()["dispatches"] if d["title"] == "STORY-01 worker"]
        self.assertEqual([d["difficulty"] for d in workers], ["medium", "complex"])
        self.assertEqual([d["kind"] for d in workers], ["general", "general"])
        judge = next(d for d in self.read_world()["dispatches"] if d["title"] == "STORY-01 judge")
        self.assertEqual((judge["difficulty"], judge["kind"]), ("complex", "judge"))

    def test_extensionless_root_file_reaches_validator(self) -> None:
        first = self.story("STORY-01")
        first["context"]["write_scope"] = ["Dockerfile"]
        self.write_json(self.stories / "STORY-01-first.json", first)
        self.planning("render")
        self.set_world({
            "STORY-01:worker": [[{"output": WORKER_DONE, "files": {"Dockerfile": "FROM scratch\n"}}]],
            "STORY-01:validator": [[{"output": VALIDATOR_PASS}]],
        })

        self.run_driver("--max-stories", "1")

        self.assertEqual(self.story("STORY-01")["status"], "done")
        self.assertNotIn("STORY-01:judge", self.read_world().get("spawned", {}))

    def test_path_outside_planned_scope_is_delegated_to_validator(self) -> None:
        self.set_world({
            "STORY-01:worker": [[{"output": WORKER_DONE, "files": {**WORKER_FILES, "README.md": "oops\n"}}]],
            "STORY-01:validator": [[{"output": VALIDATOR_PASS}]],
        })
        self.run_driver("--max-stories", "1")
        world = self.read_world()
        self.assertEqual(self.story("STORY-01")["status"], "done")
        self.assertNotIn("STORY-01:judge", world.get("spawned", {}))
        validator_task = world["threads"]["thr_validator_story01_1"]["task"]
        self.assertIn("README.md", validator_task)
        self.assertIn("文件不在预估区域不自动等于越界", validator_task)

    def test_checkpoint_uses_only_validator_confirmed_worker_paths(self) -> None:
        worker_report = {
            "result": "worker_done",
            "changes": [{"path": "src/feature.py", "summary": "实现公开入口"}],
            "verification": [{
                "command": "scripted verification", "outcome": "passed", "summary": "通过",
            }],
            "remaining": [],
            "handoff": "公开入口可用。",
        }
        validator_report = {
            "verdict": "PASS",
            "acceptance": [{"id": "AC-01", "outcome": "holds", "evidence": "公开入口返回 1"}],
            "worker_paths": ["src/feature.py"],
            "gaps": [],
            "new_facts": ["parallel.txt 属共享工作区并行改动。"],
        }
        self.set_world({
            "STORY-01:worker": [[{
                "output": "报告已提交。",
                "files": {**WORKER_FILES, "parallel.txt": "other work\n"},
                "worker_report": worker_report,
            }]],
            "STORY-01:validator": [[{
                "output": "结构化报告已提交。", "validator_report": validator_report,
            }]],
        })

        self.run_driver("--max-stories", "1")

        committed = self.git("show", "--format=", "--name-only", "HEAD").splitlines()
        self.assertIn("src/feature.py", committed)
        self.assertNotIn("parallel.txt", committed)
        self.assertIn("?? parallel.txt", self.git("status", "--short"))

    def test_resume_reuses_thread_recorded_in_owner(self) -> None:
        self.set_world({
            "STORY-01:worker": [[{"status": "active"}, {"output": WORKER_DONE, "files": WORKER_FILES}]],
            "STORY-01:validator": [[{"output": VALIDATOR_PASS}]],
        })
        first = self.run_driver("--once")
        self.assertIn("ONCE", first.stdout)
        self.assertEqual(self.story("STORY-01")["status"], "in_progress")
        self.assertTrue(self.story("STORY-01")["owner"].startswith("thr_"))
        shutil.rmtree(self.repo / ".local")  # 丢失本地状态，只剩计划与线程
        self.run_driver("--max-stories", "1")
        self.assertEqual(self.story("STORY-01")["status"], "done")
        self.assertEqual(self.read_world()["spawned"]["STORY-01:worker"], 1)

    def test_repair_baseline_attributes_only_confirmed_dirty_worker_paths(self) -> None:
        story = self.story("STORY-01")
        story["status"] = "in_progress"
        story["owner"] = "thr_existing_worker"
        self.write_json(self.stories / "STORY-01-first.json", story)
        self.planning("render")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "feature.py").write_text("value = 1\n", encoding="utf-8")
        (self.repo / "parallel.txt").write_text("other work\n", encoding="utf-8")

        repaired = self.run_command(
            "repair-baseline", "--story", "STORY-01", "--worker-path", "src/feature.py",
        )

        self.assertIn("REPAIRED: STORY-01", repaired.stdout)
        state_file = next((self.repo / ".local" / "large-task-orchestrator").glob("*/state.json"))
        state = json.loads(state_file.read_text(encoding="utf-8"))["stories"]["STORY-01"]
        self.assertEqual(state["worker_thread"], "thr_existing_worker")
        self.assertEqual(state["attempts"], 1)
        self.assertIn("parallel.txt", state["baseline_dirty"])
        self.assertNotIn("src/feature.py", state["baseline_dirty"])

    def test_repair_baseline_rejects_driver_management_path(self) -> None:
        story = self.story("STORY-01")
        story["status"] = "in_progress"
        story["owner"] = "thr_existing_worker"
        self.write_json(self.stories / "STORY-01-first.json", story)
        self.planning("render")

        rejected = self.run_command(
            "repair-baseline", "--story", "STORY-01",
            "--worker-path", "plan/agent/stories/STORY-01-first.json", expected=2,
        )

        self.assertIn("Driver 管理的计划状态", rejected.stderr)

    def test_worker_error_retries_once_then_judge_replaces_worker(self) -> None:
        self.set_world({
            "STORY-01:worker": [
                [{"status": "error"}, {"status": "error"}],
                [{"output": WORKER_DONE, "files": WORKER_FILES}],
            ],
            "STORY-01:judge": [[{"output": "Action: retry\nNote: 线程故障，换 fresh Worker。"}]],
            "STORY-01:validator": [[{"output": VALIDATOR_PASS}]],
        })
        self.run_driver("--max-stories", "1")
        world = self.read_world()
        self.assertEqual(world["spawned"]["STORY-01:worker"], 2)
        self.assertEqual(world["spawned"]["STORY-01:judge"], 1)
        retries = [call for call in world["calls"] if call[:2] == ["thread", "retry"]]
        self.assertEqual(retries, [["thread", "retry", "thr_worker_story01_1"]])

    def test_validator_error_retries_once_then_reassigns_validator(self) -> None:
        self.set_world({
            "STORY-01:worker": [[{"output": WORKER_DONE, "files": WORKER_FILES}]],
            "STORY-01:validator": [
                [{"status": "error"}, {"status": "error"}],
                [{"output": VALIDATOR_PASS}],
            ],
        })
        self.run_driver("--max-stories", "1")
        world = self.read_world()
        self.assertEqual(world["spawned"]["STORY-01:validator"], 2)
        retries = [call for call in world["calls"] if call[:2] == ["thread", "retry"]]
        self.assertEqual(retries, [["thread", "retry", "thr_validator_story01_1"]])

    def test_pending_interaction_goes_to_judge_then_original_worker_continues(self) -> None:
        self.set_world({
            "STORY-01:worker": [[{"status": "active"}, {"output": WORKER_DONE, "files": WORKER_FILES}]],
            "STORY-01:judge": [[{
                "output": "Action: patch\nNote: interaction handled",
                "clear_interactions_for": ["thr_worker_story01_1"],
            }]],
            "STORY-01:validator": [[{"output": VALIDATOR_PASS}]],
            "interactions": {
                "STORY-01:worker": [{"id": "int-credential", "status": "pending", "question": "确认在测试环境读取令牌"}],
            },
        })
        self.run_driver("--max-stories", "1")
        world = self.read_world()
        judge = next(item for item in world["dispatches"] if item["title"] == "STORY-01 judge")
        judge_task = world["threads"][judge["thread"]]["task"]
        self.assertIn("int-credential", judge_task)
        self.assertIn("读取令牌", judge_task)
        self.assertEqual(world["spawned"]["STORY-01:worker"], 1)
        self.assertEqual(self.story("STORY-01")["status"], "done")

    def test_judge_block_continues_independent_ready_story_then_stops(self) -> None:
        self.add_story("STORY-03", [])
        self.set_world({
            "STORY-01:worker": [[{"output": "Result: blocked\nChanged: none\nVerified: none\nRemaining: 缺少凭据\nHandoff: 等待凭据"}]],
            "STORY-01:judge": [[{"output": "Action: block\nNote: 等待用户提供测试凭据。"}]],
            "STORY-03:worker": [[{"output": WORKER_DONE, "files": {"src/independent.py": "value = 3\n"}}]],
            "STORY-03:validator": [[{"output": VALIDATOR_PASS}]],
        })
        result = self.run_driver(expected=3)
        self.assertIn("STORY-01: 等待用户提供测试凭据", result.stderr)
        self.assertEqual(self.story("STORY-01")["status"], "blocked")
        self.assertEqual(self.story("STORY-03")["status"], "done")

    def test_judge_replan_refreshes_plan_then_driver_continues(self) -> None:
        replanned = story_data("STORY-01", [])
        replanned["status"] = "todo"
        replan_contents = json.dumps(replanned, ensure_ascii=False, indent=2) + "\n"
        self.set_world({
            "STORY-01:worker": [
                [{"output": "Result: failed\nChanged: none\nVerified: 红\nRemaining: 全部\nHandoff: 需要重排"}],
                [{"output": WORKER_DONE, "files": WORKER_FILES}],
            ],
            "STORY-01:judge": [[{
                "output": "Action: replan\nNote: 已将当前 Story 放回 todo 并更新执行路线。",
                "files": {"plan/agent/stories/STORY-01-first.json": replan_contents},
                "render_plan": True,
            }]],
            "STORY-01:validator": [[{"output": VALIDATOR_PASS}]],
        })
        self.run_driver("--max-stories", "1")
        self.assertEqual(self.story("STORY-01")["status"], "done")
        self.assertEqual(self.read_world()["spawned"]["STORY-01:worker"], 2)

    def test_once_calls_resume_a_simple_story_until_done(self) -> None:
        self.set_world({"STORY-01:worker": [[{"output": WORKER_DONE, "files": WORKER_FILES}]]})
        self.run_driver("--once", "--default-difficulty", "simple", "--validator", "standard-up")
        self.assertEqual(self.story("STORY-01")["status"], "in_progress")
        self.run_driver("--once", "--default-difficulty", "simple", "--validator", "standard-up")
        self.assertEqual(self.story("STORY-01")["status"], "done")

    def test_wait_timeout_exit_two_is_a_paced_wait_not_a_driver_error(self) -> None:
        self.set_world({"STORY-01:worker": [[{"status": "active", "wait_exit": 2}] ]})
        self.run_driver("--once")
        waiting = self.run_driver("--once")
        self.assertIn("ONCE: waiting", waiting.stdout)
        self.assertEqual(self.story("STORY-01")["status"], "in_progress")

    def test_empty_worker_change_goes_to_judge_unless_explicitly_allowed(self) -> None:
        self.set_world({
            "STORY-01:worker": [[{"output": WORKER_DONE}]],
            "STORY-01:judge": [[{"output": "Action: stop\nNote: 没有可验证的改动。"}]],
        })
        result = self.run_driver("--default-difficulty", "simple", expected=3)
        self.assertIn("没有可验证的改动", result.stderr)
        self.assertEqual(self.read_world()["spawned"]["STORY-01:judge"], 1)

    def test_allow_empty_story_completes_without_judge(self) -> None:
        self.set_world({"STORY-01:worker": [[{"output": WORKER_DONE}]]})
        self.run_driver("--default-difficulty", "simple", "--validator", "standard-up",
                        "--allow-empty-story", "--max-stories", "1")
        self.assertEqual(self.story("STORY-01")["status"], "done")
        self.assertNotIn("STORY-01:judge", self.read_world().get("spawned", {}))

    def test_complete_story_caps_handoff_to_planning_limits(self) -> None:
        long_report = (
            "Result: worker_done\n"
            f"Changed: {'改动' * 300}\n"
            f"Verified: {'验证' * 160}\n"
            "Remaining: none\n"
            f"Handoff: {'交接' * 300}"
        )
        self.set_world({"STORY-01:worker": [[{"output": long_report, "files": WORKER_FILES}]]})
        self.run_driver("--default-difficulty", "simple", "--validator", "standard-up", "--max-stories", "1")
        handoff = self.story("STORY-01")["handoff"]
        self.assertLessEqual(len(handoff["summary"]), 400)
        self.assertLessEqual(len(handoff["next"]), 400)
        self.assertTrue(all(len(item) <= 200 for item in handoff["verification"]))

    def test_validator_runs_for_a_simple_story_by_default(self) -> None:
        self.set_world({
            "STORY-01:worker": [[{"output": WORKER_DONE, "files": WORKER_FILES}]],
            "STORY-01:validator": [[{"output": VALIDATOR_PASS}]],
        })
        self.run_driver("--default-difficulty", "simple", "--max-stories", "1")
        self.assertEqual(self.read_world()["spawned"]["STORY-01:validator"], 1)

    def test_missing_validator_report_is_bounded_then_stops(self) -> None:
        self.set_world({
            "STORY-01:worker": [[{"output": WORKER_DONE, "files": WORKER_FILES}]],
            "STORY-01:validator": [[{"output": WORKER_DONE}, {"output": WORKER_DONE}]],
        })
        result = self.run_driver(expected=3)
        self.assertIn("两次未提交有效结构化报告", result.stderr)
        world = self.read_world()
        self.assertEqual(world["spawned"]["STORY-01:validator"], 1)
        self.assertNotIn("STORY-01:judge", world.get("spawned", {}))
        self.assertEqual(len(world["threads"]["thr_validator_story01_1"]["tells"]), 1)

    def test_checkpoint_excludes_preexisting_staged_change(self) -> None:
        (self.repo / "README.md").write_text("并发暂存改动\n", encoding="utf-8")
        self.git("add", "README.md")
        self.set_world({"STORY-01:worker": [[{"output": WORKER_DONE, "files": WORKER_FILES}]]})
        self.run_driver("--default-difficulty", "simple", "--validator", "standard-up", "--max-stories", "1")
        committed = self.git("show", "--format=", "--name-only", "HEAD").splitlines()
        self.assertNotIn("README.md", committed)
        staged = subprocess.run(["git", "diff", "--cached", "--quiet", "--", "README.md"], cwd=self.repo)
        self.assertEqual(staged.returncode, 1)

    def test_push_updates_the_configured_upstream_head(self) -> None:
        remote = self.root / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "-q", "--set-upstream", "origin", "main")
        self.set_world({
            "STORY-01:worker": [[{"output": WORKER_DONE, "files": WORKER_FILES}]],
            "STORY-02:worker": [[{"output": WORKER_DONE, "files": {"src/final.py": "done = True\n"}}]],
        })
        self.run_driver("--default-difficulty", "simple", "--validator", "standard-up", "--push")
        remote_head = subprocess.run(["git", "--git-dir", str(remote), "rev-parse", "main"],
                                     capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(remote_head, self.git("rev-parse", "HEAD").strip())

    def test_start_runs_in_background_status_exposes_thread_and_rejects_duplicate(self) -> None:
        self.set_world({"STORY-01:worker": [[{"status": "active"}]]})
        self.start_driver("--max-stories", "1")
        payload = self.wait_for(lambda: value if (value := self.status_payload())["alive"]
                                and value["in_progress"] else None)
        story = payload["in_progress"][0]
        self.assertEqual(story["id"], "STORY-01")
        self.assertEqual(story["stage"], "working")
        self.assertTrue(story["worker_thread"].startswith("thr_worker_story01_"))
        duplicate = self.run_command("start", "--max-stories", "1", expected=4)
        self.assertIn("已在运行", duplicate.stderr)

    def test_stale_pid_file_does_not_block_start(self) -> None:
        self.set_world({"STORY-01:worker": [[{"status": "active"}]]})
        state_dir = Path(self.status_payload()["state_dir"])
        state_dir.mkdir(parents=True)
        (state_dir / "driver.pid").write_text('{"pid": 999999, "started_at": "old"}\n', encoding="utf-8")
        self.start_driver("--max-stories", "1")
        payload = self.wait_for(lambda: value if (value := self.status_payload())["alive"] else None)
        self.assertNotEqual(payload["pid"], 999999)

    def test_two_plans_in_one_repository_have_isolated_background_state_and_resume_to_done(self) -> None:
        plan_a, stories_a = self.add_one_story_plan("plan-a", "STORY-03")
        plan_b, stories_b = self.add_one_story_plan("plan-b", "STORY-04")
        self.set_world({
            "STORY-03:worker": [[{"status": "active"}, {"output": WORKER_DONE}]],
            "STORY-04:worker": [[{"status": "active"}, {"output": WORKER_DONE}]],
        })
        self.start_driver("--default-difficulty", "simple", "--validator", "standard-up",
                          "--allow-empty-story", "--max-stories", "1",
                          plan=plan_a, stories=stories_a)
        self.start_driver("--default-difficulty", "simple", "--validator", "standard-up",
                          "--allow-empty-story", "--max-stories", "1",
                          plan=plan_b, stories=stories_b)
        payload_a = self.wait_for(lambda: value if (value := self.status_payload(plan=plan_a, stories=stories_a))["alive"]
                                  and value["in_progress"] else None)
        payload_b = self.wait_for(lambda: value if (value := self.status_payload(plan=plan_b, stories=stories_b))["alive"]
                                  and value["in_progress"] else None)
        self.assertNotEqual(payload_a["state_dir"], payload_b["state_dir"])
        self.run_command("stop", "--wait", "--wait-timeout", "5", plan=plan_a, stories=stories_a)
        self.run_command("stop", "--wait", "--wait-timeout", "5", plan=plan_b, stories=stories_b)
        self.run_command("run", "--default-difficulty", "simple", "--validator", "standard-up",
                         "--allow-empty-story", "--max-stories", "1",
                         plan=plan_a, stories=stories_a)
        self.run_command("run", "--default-difficulty", "simple", "--validator", "standard-up",
                         "--allow-empty-story", "--max-stories", "1",
                         plan=plan_b, stories=stories_b)
        self.assertEqual(json.loads((stories_a / "STORY-03.json").read_text(encoding="utf-8"))["status"], "done")
        self.assertEqual(json.loads((stories_b / "STORY-04.json").read_text(encoding="utf-8"))["status"], "done")
        log_a = (Path(payload_a["state_dir"]) / "log.jsonl").read_text(encoding="utf-8")
        log_b = (Path(payload_b["state_dir"]) / "log.jsonl").read_text(encoding="utf-8")
        self.assertIn("STORY-03", log_a)
        self.assertNotIn("STORY-04", log_a)
        self.assertIn("STORY-04", log_b)
        self.assertNotIn("STORY-03", log_b)

    def test_stop_preserves_in_progress_story_then_restart_reuses_worker(self) -> None:
        self.set_world({
            "STORY-01:worker": [[{"status": "active"}, {"output": WORKER_DONE, "files": WORKER_FILES}]],
        })
        self.start_driver("--default-difficulty", "simple", "--validator", "standard-up", "--max-stories", "1")
        self.wait_for(lambda: value if (value := self.status_payload())["alive"] and value["in_progress"] else None)
        self.run_command("stop", "--wait", "--wait-timeout", "5")
        self.assertEqual(self.story("STORY-01")["status"], "in_progress")
        stopped = self.status_payload()
        self.assertFalse(stopped["alive"])
        self.assertFalse((Path(stopped["state_dir"]) / "driver.pid").exists())
        self.start_driver("--default-difficulty", "simple", "--validator", "standard-up", "--max-stories", "1")
        self.wait_for_driver_exit()
        self.assertEqual(self.story("STORY-01")["status"], "done")
        self.assertEqual(self.read_world()["spawned"]["STORY-01:worker"], 1)

    def test_legacy_inflight_validator_resumes_with_structured_round_one_report(self) -> None:
        self.set_world({
            "STORY-01:worker": [[{"output": WORKER_DONE, "files": WORKER_FILES}]],
            "STORY-01:validator": [[{"output": "核验完成。"}, {"output": VALIDATOR_PASS}]],
        })
        self.run_driver("--once")
        self.run_driver("--once")
        state_path = Path(self.status_payload()["state_dir"]) / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        story_state = state["stories"]["STORY-01"]
        story_state.pop("validator_rounds")
        story_state.pop("validator_report_requests")
        story_state["validator_parse_failures"] = 0
        self.write_json(state_path, state)

        self.run_driver("--max-stories", "1")

        self.assertEqual(self.story("STORY-01")["status"], "done")
        world = self.read_world()
        self.assertEqual(world["spawned"]["STORY-01:validator"], 1)
        tells = world["threads"]["thr_validator_story01_1"]["tells"]
        self.assertEqual(len(tells), 1)
        self.assertIn("--validation-round 1", tells[0])

    def test_status_json_reports_last_stop_reason_after_exit_three(self) -> None:
        self.set_world({
            "STORY-01:worker": [[{"output": "Result: blocked\nChanged: none\nVerified: none\nRemaining: 缺少凭据\nHandoff: 等待凭据"}]],
            "STORY-01:judge": [[{"output": "Action: stop\nNote: 需要用户提供测试凭据。"}]],
        })
        self.start_driver("--max-stories", "1")
        payload = self.wait_for_driver_exit()
        self.assertIn("需要用户提供测试凭据", payload["last_stop"])
        self.assertFalse((Path(payload["state_dir"]) / "driver.pid").exists())


if __name__ == "__main__":
    unittest.main()
