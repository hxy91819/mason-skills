"""验证 Worker 结构化报告的写入、读取和严格 schema 门禁。"""
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


class WorkerReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.output = self.root / "worker.json"

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
        for mutation in ("unknown", "absolute_path"):
            with self.subTest(mutation=mutation):
                payload = valid_report()
                if mutation == "unknown":
                    payload["extra"] = True
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


if __name__ == "__main__":
    unittest.main()
