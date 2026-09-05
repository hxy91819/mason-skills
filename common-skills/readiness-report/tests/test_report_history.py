from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "report_history.py"
REPO = "https://github.com/example/demo.git"


class TestReportHistoryCli(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.cache = Path(self.temporary.name)

    def run_cli(self, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["python3", str(SCRIPT), "--cache", str(self.cache), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(expected, result.returncode, result.stderr)
        return result

    def store(self, run_id: str, *, level: int = 3, at: str = "2026-09-05T00:00:00Z") -> None:
        self.run_cli(
            "store",
            "--repo",
            REPO,
            "--level",
            str(level),
            "--pass-rate",
            "55.5",
            "--evaluated",
            "40",
            "--skipped",
            "5",
            "--run-id",
            run_id,
            "--engine",
            "droid",
            "--model",
            "unknown",
            "--at",
            at,
        )

    def test_repeat_run_id_overwrites_without_double_counting(self) -> None:
        self.store("same-run", level=2)
        self.store("same-run", level=4)

        shown = json.loads(self.run_cli("show", "--repo", REPO).stdout)
        total = shown["aggregate"]["rollup"]
        self.assertEqual(1, total["runs"])
        self.assertEqual(1, total["levels"]["4"])
        self.assertEqual(0, total["levels"]["2"])
        self.assertEqual(4, shown["latest"]["level"])

    def test_rollup_and_live_window_count_once(self) -> None:
        for index in range(52):
            self.store(f"run-{index:02d}")

        shown = json.loads(self.run_cli("show", "--repo", REPO).stdout)
        self.assertEqual(50, shown["recent_count"])
        self.assertEqual(52, shown["aggregate"]["rollup"]["runs"])
        checked = json.loads(self.run_cli("check", "--repo", REPO).stdout)
        self.assertEqual(2, checked["rolled_count"])
        self.assertEqual(0, checked["report_files"])

    def test_report_file_persisted_verbatim(self) -> None:
        with tempfile.TemporaryDirectory() as report_dir:
            report_path = Path(report_dir) / "report.json"
            payload = {"level": 3, "criteria": {"readme": {"numerator": 1, "denominator": 1}}}
            report_path.write_text(json.dumps(payload), encoding="utf-8")
            result = self.run_cli(
                "store",
                "--repo",
                REPO,
                "--level",
                "3",
                "--pass-rate",
                "50",
                "--evaluated",
                "1",
                "--skipped",
                "0",
                "--run-id",
                "with-report",
                "--engine",
                "droid",
                "--model",
                "unknown",
                "--report",
                str(report_path),
            )
        stored_path = json.loads(result.stdout)["report"]
        stored = json.loads(Path(stored_path).read_text(encoding="utf-8"))
        self.assertEqual(payload, stored)

    def test_remote_url_forms_converge_on_one_slug(self) -> None:
        # https and ssh forms of the same remote must converge on one slug;
        # a local path is accepted but keeps its own slug.
        self.store("https-form")
        self.run_cli(
            "store",
            "--repo",
            "git@github.com:example/demo.git",
            "--level",
            "1",
            "--pass-rate",
            "10",
            "--evaluated",
            "1",
            "--skipped",
            "0",
            "--run-id",
            "ssh-form",
            "--engine",
            "droid",
            "--model",
            "unknown",
        )
        slugs = [p.name for p in self.cache.iterdir() if p.is_dir()]
        self.assertEqual(1, len(slugs), slugs)
        shown = json.loads(
            self.run_cli("show", "--repo", "git@github.com:example/demo.git").stdout
        )
        self.assertEqual(2, shown["aggregate"]["rollup"]["runs"])
        self.run_cli(
            "store",
            "--repo",
            "/data/code/demo",
            "--level",
            "1",
            "--pass-rate",
            "10",
            "--evaluated",
            "1",
            "--skipped",
            "0",
            "--run-id",
            "local-form",
            "--engine",
            "droid",
            "--model",
            "unknown",
        )
        self.assertEqual(2, len([p for p in self.cache.iterdir() if p.is_dir()]))

    def test_invalid_level_and_unknown_repo_rejected(self) -> None:
        result = self.run_cli(
            "store",
            "--repo",
            REPO,
            "--level",
            "9",
            "--pass-rate",
            "50",
            "--evaluated",
            "1",
            "--skipped",
            "0",
            "--engine",
            "droid",
            "--model",
            "unknown",
            expected=2,
        )
        self.assertIn("invalid choice", result.stderr)
        empty = self.run_cli("show", "--repo", "never-stored", expected=0)
        self.assertEqual(0, json.loads(empty.stdout)["recent_count"])

    def test_local_path_roundtrip_show_after_store(self) -> None:
        # Regression: validate_history must accept a stored local-path repo,
        # not just remote URLs, or show/check fail after a local store.
        self.run_cli(
            "store",
            "--repo",
            "/data/code/demo",
            "--level",
            "1",
            "--pass-rate",
            "10",
            "--evaluated",
            "1",
            "--skipped",
            "0",
            "--run-id",
            "local-roundtrip",
            "--engine",
            "droid",
            "--model",
            "unknown",
        )
        shown = json.loads(self.run_cli("show", "--repo", "/data/code/demo").stdout)
        self.assertEqual(1, shown["recent_count"])
        checked = json.loads(self.run_cli("check", "--repo", "/data/code/demo").stdout)
        self.assertTrue(checked["ok"])

    def test_no_network_surface(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("requests", "urllib", "http.client", "socket"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
