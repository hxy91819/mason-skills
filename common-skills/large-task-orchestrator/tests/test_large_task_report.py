"""验证 Worker、Validator 与 Judge 报告的写入、读取和严格 schema 门禁。"""
from __future__ import annotations

import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPORTER = Path(__file__).resolve().parent.parent / "scripts" / "large_task_report.py"


def valid_report() -> dict[str, object]:
    return {
        "result": "worker_done",
        "changes": [{"path": "scripts/example.py", "summary": "新增公开入口"}],
        "verification": [{"command": "python3 -m unittest", "outcome": "passed", "summary": "3 项通过"}],
        "remaining": [],
        "handoff": "下一张 Story 可复用该入口。",
    }


def valid_validator_report() -> dict[str, object]:
    return {
        "verdict": "PASS",
        "acceptance": [
            {"id": "AC-01", "outcome": "holds", "evidence": "公开命令退出码为 0"},
            {"id": "AC-02", "outcome": "holds", "evidence": "公开接口返回预期结果"},
        ],
        "worker_paths": ["src/feature.py"],
        "gaps": [],
        "new_facts": [],
    }


def valid_judge_report() -> dict[str, object]:
    return {"action": "patch", "note": "补齐 AC-02 对应的公开行为。"}


class ReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.output = self.root / "worker.json"
        self.validator_output = self.root / "validator.json"
        self.judge_output = self.root / "judge.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_reporter(self, *arguments: str, payload: dict[str, object] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(REPORTER), *arguments],
            input=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
            capture_output=True,
            text=True,
            check=False,
        )

    def submit(self, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
        return self.run_reporter(
            "worker", "--output", str(self.output), "--story-id", "STORY-03",
            "--attempt", "2", "--intent-version", "4", payload=payload,
        )

    def submit_validator(self, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
        return self.run_reporter(
            "validator", "--output", str(self.validator_output), "--story-id", "STORY-03",
            "--attempt", "2", "--intent-version", "4", "--validation-round", "3",
            "--acceptance-id", "AC-01", "--acceptance-id", "AC-02", payload=payload,
        )

    def submit_judge(self, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
        return self.run_reporter(
            "judge", "--output", str(self.judge_output), "--story-id", "STORY-03",
            "--attempt", "2", "--intent-version", "4", "--judge-round", "2", payload=payload,
        )

    def test_valid_report_is_written_atomically_and_read_with_expected_identity(self) -> None:
        submitted = self.submit(valid_report())
        self.assertEqual(submitted.returncode, 0, submitted.stderr)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)

        read = self.run_reporter(
            "read-worker", "--file", str(self.output), "--story-id", "STORY-03",
            "--attempt", "2", "--intent-version", "4",
        )
        self.assertEqual(read.returncode, 0, read.stderr)
        envelope = json.loads(read.stdout)
        self.assertEqual(envelope["schema_version"], 1)
        self.assertEqual(envelope["role"], "worker")
        self.assertEqual(envelope["story_id"], "STORY-03")
        self.assertEqual(envelope["report"], valid_report())

    def test_unknown_field_and_unsafe_change_path_are_rejected_without_output(self) -> None:
        for mutation in ("unknown", "absolute_path", "non_normalized_path"):
            with self.subTest(mutation=mutation):
                payload = valid_report()
                if mutation == "unknown":
                    payload["extra"] = True
                elif mutation == "non_normalized_path":
                    payload["changes"] = [{"path": "scripts//example.py", "summary": "非规范路径"}]
                else:
                    payload["changes"] = [{"path": "/tmp/example.py", "summary": "越界"}]
                result = self.submit(payload)
                self.assertEqual(result.returncode, 2)
                self.assertIn("ERROR:", result.stderr)
                self.assertFalse(self.output.exists())

    def test_read_rejects_stale_attempt(self) -> None:
        self.assertEqual(self.submit(valid_report()).returncode, 0)
        read = self.run_reporter(
            "read-worker", "--file", str(self.output), "--story-id", "STORY-03",
            "--attempt", "3", "--intent-version", "4",
        )
        self.assertEqual(read.returncode, 2)
        self.assertIn("attempt", read.stderr)

    def test_invalid_resubmission_removes_previous_valid_report(self) -> None:
        self.assertEqual(self.submit(valid_report()).returncode, 0)
        invalid = valid_report()
        invalid["extra"] = True

        rejected = self.submit(invalid)

        self.assertEqual(rejected.returncode, 2)
        self.assertFalse(self.output.exists())

    def test_validator_report_requires_exact_acceptance_set_and_consistent_pass(self) -> None:
        submitted = self.submit_validator(valid_validator_report())
        self.assertEqual(submitted.returncode, 0, submitted.stderr)
        self.assertEqual(stat.S_IMODE(self.validator_output.stat().st_mode), 0o600)
        read = self.run_reporter(
            "read-validator", "--file", str(self.validator_output), "--story-id", "STORY-03",
            "--attempt", "2", "--intent-version", "4", "--validation-round", "3",
            "--acceptance-id", "AC-01", "--acceptance-id", "AC-02",
        )
        self.assertEqual(read.returncode, 0, read.stderr)
        self.assertEqual(json.loads(read.stdout)["report"], valid_validator_report())

        incomplete = valid_validator_report()
        incomplete["acceptance"] = incomplete["acceptance"][:1]
        rejected = self.submit_validator(incomplete)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("exactly equal", rejected.stderr)
        self.assertFalse(self.validator_output.exists())

        inconsistent = valid_validator_report()
        inconsistent["acceptance"][0]["outcome"] = "missing"
        rejected = self.submit_validator(inconsistent)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("PASS requires", rejected.stderr)

    def test_validator_read_rejects_stale_round(self) -> None:
        self.assertEqual(self.submit_validator(valid_validator_report()).returncode, 0)
        read = self.run_reporter(
            "read-validator", "--file", str(self.validator_output), "--story-id", "STORY-03",
            "--attempt", "2", "--intent-version", "4", "--validation-round", "4",
            "--acceptance-id", "AC-01", "--acceptance-id", "AC-02",
        )
        self.assertEqual(read.returncode, 2)
        self.assertIn("validation_round", read.stderr)

    def test_validator_report_rejects_unsafe_or_duplicate_worker_paths(self) -> None:
        unsafe = valid_validator_report()
        unsafe["worker_paths"] = ["../parallel.txt"]
        rejected = self.submit_validator(unsafe)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("normalized repository-relative path", rejected.stderr)

        duplicate = valid_validator_report()
        duplicate["worker_paths"] = ["src/feature.py", "src/feature.py"]
        rejected = self.submit_validator(duplicate)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("duplicate path", rejected.stderr)

    def test_judge_report_rejects_unknown_action_and_invalidates_previous_report(self) -> None:
        submitted = self.submit_judge(valid_judge_report())
        self.assertEqual(submitted.returncode, 0, submitted.stderr)
        read = self.run_reporter(
            "read-judge", "--file", str(self.judge_output), "--story-id", "STORY-03",
            "--attempt", "2", "--intent-version", "4", "--judge-round", "2",
        )
        self.assertEqual(read.returncode, 0, read.stderr)
        self.assertEqual(json.loads(read.stdout)["report"], valid_judge_report())

        invalid = valid_judge_report()
        invalid["action"] = "continue"
        rejected = self.submit_judge(invalid)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("report.action", rejected.stderr)
        self.assertFalse(self.judge_output.exists())


if __name__ == "__main__":
    unittest.main()
