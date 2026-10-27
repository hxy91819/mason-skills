import unittest
from pathlib import Path
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).parent))
import check_codex_quota_fast as checker


class TestCheckCodexQuotaFast(unittest.TestCase):
    def test_parse_remaining(self):
        data = {
            "codex": {
                "status": "ok",
                "windows": [{"label": "Weekly limit", "usedPercent": 25, "resetsAt": "2026-11-01T00:00:00Z"}]
            }
        }
        stat, err = checker.parse_remaining(data, "codex")
        self.assertEqual(err, "ok")
        self.assertEqual(stat["used_percent"], 25.0)
        self.assertEqual(stat["remaining_percent"], 75.0)

    def test_fuse_triggers_when_remaining_below_threshold(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "config.yaml"
            cfg.write_text("version: 2\nfast: true\ndefaults: {}\n", encoding="utf-8")

            # Mock get_usage returning codex at 65% used (35% remaining <= 40%)
            orig_get_usage = checker.get_usage
            try:
                checker.get_usage = lambda: {
                    "codex": {
                        "status": "ok",
                        "windows": [{"label": "Weekly limit", "usedPercent": 65, "resetsAt": "2026-11-01"}]
                    },
                    "codex-l": {
                        "status": "ok",
                        "windows": [{"label": "Weekly limit", "usedPercent": 10, "resetsAt": "2026-11-01"}]
                    }
                }
                res = checker.check_and_fuse(config_path=cfg, dry_run=False)
                self.assertTrue(res["fuse_triggered"])
                self.assertEqual(res["action"], "fused_closed_fast")
                self.assertIn("fast: false", cfg.read_text(encoding="utf-8"))
            finally:
                checker.get_usage = orig_get_usage

    def test_no_fuse_when_quota_healthy(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "config.yaml"
            cfg.write_text("version: 2\nfast: true\ndefaults: {}\n", encoding="utf-8")

            orig_get_usage = checker.get_usage
            try:
                checker.get_usage = lambda: {
                    "codex": {
                        "status": "ok",
                        "windows": [{"label": "Weekly limit", "usedPercent": 10, "resetsAt": "2026-11-01"}]
                    },
                    "codex-l": {
                        "status": "ok",
                        "windows": [{"label": "Weekly limit", "usedPercent": 20, "resetsAt": "2026-11-01"}]
                    }
                }
                res = checker.check_and_fuse(config_path=cfg, dry_run=False)
                self.assertFalse(res["fuse_triggered"])
                self.assertEqual(res["action"], "kept_current")
                self.assertIn("fast: true", cfg.read_text(encoding="utf-8"))
            finally:
                checker.get_usage = orig_get_usage

    def test_notify_thread(self):
        orig_run = checker.subprocess.run
        calls = []

        class FakeRes:
            returncode = 0

        def fake_run(cmd, *args, **kwargs):
            calls.append(cmd)
            return FakeRes()

        try:
            checker.subprocess.run = fake_run
            res = checker.notify_thread("thr_test123", "熔断测试")
            self.assertTrue(res)
            self.assertEqual(calls, [["bb", "thread", "tell", "thr_test123", "熔断测试"]])
        finally:
            checker.subprocess.run = orig_run


if __name__ == "__main__":
    unittest.main()
