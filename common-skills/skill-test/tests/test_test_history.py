from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "test_history.py"


class TestHistoryCli(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.history = Path(self.temporary.name) / "history.json"

    def run_cli(self, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["python3", str(SCRIPT), "--history", str(self.history), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(expected, result.returncode, result.stderr)
        return result

    def record(self, test_id: str, *, outcome: str = "passed") -> None:
        self.run_cli(
            "record",
            "--test-id",
            test_id,
            "--skill",
            "fixture-skill",
            "--engine",
            "native",
            "--model",
            "small-model",
            "--model-class",
            "non-frontier",
            "--duration-ms",
            "10",
            "--outcome",
            outcome,
            "--context-isolated",
            "yes",
            "--at",
            "2026-09-04T00:00:00Z",
        )

    def show(self) -> dict[str, object]:
        return json.loads(self.run_cli("show").stdout)

    def test_repeated_record_replaces_without_double_counting(self) -> None:
        self.record("same-id", outcome="failed")
        self.record("same-id", outcome="passed")

        aggregate = self.show()["aggregate"]["total"]
        self.assertEqual(1, aggregate["runs"])
        self.assertEqual(1, aggregate["outcomes"]["passed"])
        self.assertEqual(0, aggregate["outcomes"]["failed"])

    def test_disposition_overwrites_and_unknown_id_is_rejected(self) -> None:
        self.record("decision-id")
        self.run_cli("decide", "--test-id", "decision-id", "--disposition", "accepted")
        self.run_cli("decide", "--test-id", "decision-id", "--disposition", "rejected")

        dispositions = self.show()["aggregate"]["total"]["dispositions"]
        self.assertEqual({"accepted": 0, "pending": 0, "rejected": 1}, dispositions)
        result = self.run_cli(
            "decide",
            "--test-id",
            "missing-id",
            "--disposition",
            "accepted",
            expected=1,
        )
        self.assertIn("unknown or retired test_id", result.stderr)

    def test_rollup_and_live_window_are_counted_once(self) -> None:
        for index in range(52):
            self.record(f"run-{index:02d}")

        shown = self.show()
        self.assertEqual(50, shown["recent_count"])
        self.assertEqual(2, shown["aggregate"]["total"]["runs"] - shown["recent_count"])
        self.assertEqual(52, shown["aggregate"]["total"]["runs"])
        checked = json.loads(self.run_cli("check").stdout)
        self.assertEqual(2, checked["rolled_count"])


if __name__ == "__main__":
    unittest.main()
