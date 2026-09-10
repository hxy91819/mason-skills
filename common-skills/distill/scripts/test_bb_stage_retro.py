"""bb-stage-retro 的纯逻辑契约测试；不调用真实 BB 或创建线程。"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).with_name("bb-stage-retro.py")
SPEC = importlib.util.spec_from_file_location("bb_stage_retro", SCRIPT)
assert SPEC and SPEC.loader
retro = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = retro
SPEC.loader.exec_module(retro)


class ContinuationCoverageTests(unittest.TestCase):
    def test_chain_collapses_to_final_worker(self) -> None:
        selected = ["thr_source", "thr_middle", "thr_final", "thr_other"]
        mapping = retro.parse_continuations(
            ["thr_source=thr_middle", "thr_middle=thr_final"], set(selected)
        )

        rows, workers = retro.coverage_rows(selected, mapping)

        self.assertEqual(
            rows,
            [
                {"threadId": "thr_source", "coveredBy": "thr_final"},
                {"threadId": "thr_middle", "coveredBy": "thr_final"},
                {"threadId": "thr_final", "coveredBy": None},
                {"threadId": "thr_other", "coveredBy": None},
            ],
        )
        self.assertEqual(workers, ["thr_final", "thr_other"])

    def test_cycle_is_rejected(self) -> None:
        with self.assertRaises(retro.RetroError):
            retro.parse_continuations(["thr_a=thr_b", "thr_b=thr_a"], {"thr_a", "thr_b"})


class PromptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = retro.ReviewPlan(
            project="proj_example",
            environment="env_example",
            scope="repo-harness",
            since="2026-09-09T07:00:00Z",
            until="2026-09-10T07:00:00Z",
            coverage=[
                {"threadId": "thr_source", "coveredBy": "thr_final"},
                {"threadId": "thr_final", "coveredBy": None},
            ],
            workers=["thr_final"],
            records={"thr_final": {"title": "final"}},
        )

    def test_worker_prompt_explicitly_invokes_distill_and_stops_before_writes(self) -> None:
        prompt = retro.worker_prompt(self.plan, "thr_final")
        self.assertTrue(prompt.startswith("$distill"))
        self.assertIn("repo-harness", prompt)
        self.assertIn("不修改文件", prompt)

    def test_aggregator_reads_only_final_worker_outputs(self) -> None:
        prompt = retro.aggregation_task(self.plan)
        self.assertTrue(prompt.startswith("$distill"))
        self.assertIn("thr_final", prompt)
        self.assertNotIn("bb thread output thr_source", prompt)
        self.assertIn("covered_by", prompt)

    def test_aggregator_is_dispatched_with_approval_gated_permission(self) -> None:
        argv = retro.dispatch_argv(self.plan, SimpleNamespace(dispatch_config=None), dry_run=True)
        position = argv.index("--permission-mode")
        self.assertEqual(argv[position + 1], "accept-edits")


class TimestampTests(unittest.TestCase):
    def test_timestamp_requires_timezone(self) -> None:
        with self.assertRaises(Exception):
            retro.parse_timestamp("2026-09-09T15:00:00")

    def test_timestamp_normalizes_to_utc(self) -> None:
        self.assertEqual(retro.iso_utc(retro.parse_timestamp("2026-09-09T15:00:00+08:00")), "2026-09-09T07:00:00Z")


if __name__ == "__main__":
    unittest.main()
