from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "pick_failing.py"
REPO = "https://github.com/example/demo.git"


def slug_of(repo: str) -> str:
    """Compute the slug exactly as pick_failing.py does."""
    probe = subprocess.run(
        [
            "python3",
            "-c",
            "import sys; sys.path.insert(0, sys.argv[1]);"
            "import pick_failing as pf; print(pf.slug_for_repo(sys.argv[2]))",
            str(SCRIPT.parent),
            repo,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return probe.stdout.strip()


def write_report(cache: Path, run_id: str, criteria: dict) -> None:
    directory = cache / slug_of(REPO)
    (directory / "reports").mkdir(parents=True, exist_ok=True)
    (directory / "reports" / f"{run_id}.json").write_text(
        json.dumps({"criteria": criteria}), encoding="utf-8"
    )
    history = directory / "history.json"
    recent = []
    if history.exists():
        recent = json.loads(history.read_text(encoding="utf-8"))["recent"]
    recent.append(
        {
            "run_id": run_id,
            "repo": REPO,
            "level": 3,
            "pass_rate": 50.0,
            "evaluated": len(criteria),
            "skipped": 0,
            "outcome": "stored",
            "engine": "droid",
            "model": "unknown",
            "recorded_at": "2026-09-05T00:00:00Z",
        }
    )
    history.write_text(
        json.dumps(
            {
                "version": 1,
                "repo": REPO,
                "recent": recent,
                "rollup": {
                    "runs": 0,
                    "levels": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
                    "outcomes": {"stored": 0, "failed": 0},
                },
                "updated_at": "2026-09-05T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )


class TestPickFailingCli(unittest.TestCase):
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

    def test_extracts_failing_and_excludes_skipped(self) -> None:
        write_report(
            self.cache,
            "run-1",
            {
                "readme": {
                    "name": "README File",
                    "category": "Documentation",
                    "numerator": 1,
                    "denominator": 1,
                    "rationale": "present",
                },
                "lint_config": {
                    "name": "Linter Configuration",
                    "category": "Style & Validation",
                    "numerator": 0,
                    "denominator": 1,
                    "rationale": "no linter",
                },
                "unit_tests_exist": {
                    "name": "Unit Tests Exist",
                    "category": "Testing",
                    "numerator": 0,
                    "denominator": 3,
                    "rationale": "tests in 0 of 3 apps",
                },
                "branch_protection": {
                    "name": "Branch Protection",
                    "category": "Security",
                    "numerator": None,
                    "denominator": 1,
                    "rationale": "skipped: no admin",
                },
            },
        )
        listed = json.loads(self.run_cli("list", "--repo", REPO).stdout)
        self.assertEqual(2, listed["failing_count"])
        self.assertFalse(listed["all_passing"])
        by_id = {item["id"]: item for item in listed["failing"]}
        self.assertEqual("0/1", by_id["lint_config"]["score"])
        self.assertEqual("0/3", by_id["unit_tests_exist"]["score"])
        self.assertNotIn("branch_protection", by_id)  # skipped is not failing
        ids = self.run_cli("ids", "--repo", REPO).stdout.split()
        self.assertEqual(["lint_config", "unit_tests_exist"], sorted(ids))

    def test_all_passing(self) -> None:
        write_report(
            self.cache,
            "run-1",
            {
                "readme": {"numerator": 1, "denominator": 1, "rationale": "ok"},
            },
        )
        listed = json.loads(self.run_cli("list", "--repo", REPO).stdout)
        self.assertEqual(0, listed["failing_count"])
        self.assertTrue(listed["all_passing"])
        self.assertEqual("", self.run_cli("ids", "--repo", REPO).stdout.strip())

    def test_latest_run_wins(self) -> None:
        write_report(self.cache, "run-1", {"readme": {"numerator": 0, "denominator": 1, "rationale": "x"}})
        write_report(self.cache, "run-2", {"readme": {"numerator": 1, "denominator": 1, "rationale": "fixed"}})
        listed = json.loads(self.run_cli("list", "--repo", REPO).stdout)
        self.assertEqual("run-2", listed["run_id"])
        self.assertTrue(listed["all_passing"])

    def test_missing_report_errors(self) -> None:
        result = self.run_cli("list", "--repo", "https://github.com/other/none.git", expected=1)
        self.assertIn("no local readiness history", result.stderr)

    def test_slug_matches_report_history(self) -> None:
        # The slug must agree with report_history.py so both skills share
        # one report directory for the same repository.
        sys_path = str(SCRIPT.parent.parent.parent / "readiness-report" / "scripts")
        probe = subprocess.run(
            [
                "python3",
                "-c",
                "import sys; sys.path.insert(0, sys.argv[1]);"
                "import report_history as rh; print(rh.slug_for_repo(sys.argv[2]))",
                sys_path,
                REPO,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        expected_slug = probe.stdout.strip()
        self.assertEqual(expected_slug, slug_of(REPO))
        write_report(self.cache, "run-1", {"readme": {"numerator": 1, "denominator": 1, "rationale": "ok"}})
        self.assertTrue((self.cache / expected_slug / "history.json").exists())

    def test_no_network_surface(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("requests", "urllib", "http.client", "socket"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
