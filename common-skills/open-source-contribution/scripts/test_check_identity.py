import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("check_identity.py")

APPROVED_NAME = "@hxy91819"
APPROVED_EMAIL = "masonxhuang@proton.me"


class IdentityCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        subprocess.run(["git", "-C", self.repo, "config", "--local",
                        "user.name", APPROVED_NAME], check=True)
        subprocess.run(["git", "-C", self.repo, "config", "--local",
                        "user.email", APPROVED_EMAIL], check=True)
        subprocess.run(["git", "-C", self.repo, "config", "--local",
                        "user.useConfigOnly", "true"], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self, name, email, committer_name=None, committer_email=None, message="c"):
        path = Path(self.repo) / f"f{len(list(Path(self.repo).iterdir()))}.txt"
        path.write_text("x")
        env = dict(os.environ)
        env["GIT_AUTHOR_NAME"] = name
        env["GIT_AUTHOR_EMAIL"] = email
        env["GIT_COMMITTER_NAME"] = committer_name or name
        env["GIT_COMMITTER_EMAIL"] = committer_email or email
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True)
        subprocess.run(["git", "-C", self.repo, "commit", "-q", "-m", message],
                       check=True, env=env)

    def run_script(self, *args, env=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "-C", self.repo, "--no-github", *args],
            capture_output=True, text=True, env=env)

    def test_clean_repo_passes(self):
        self.commit(APPROVED_NAME, APPROVED_EMAIL)
        proc = self.run_script()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("CLEAN", proc.stdout)

    def test_company_email_is_must_fix(self):
        self.commit(APPROVED_NAME, "masonxhuang@tencent.com")
        proc = self.run_script()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("must-fix", proc.stdout)
        self.assertIn("tencent.com", proc.stdout)

    def test_corporate_id_name_is_must_fix(self):
        self.commit("masonxhuang", APPROVED_EMAIL)
        proc = self.run_script()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("corporate ID", proc.stdout)

    def test_noreply_committer_accepted(self):
        self.commit(APPROVED_NAME, APPROVED_EMAIL,
                    committer_name="GitHub", committer_email="noreply@github.com")
        proc = self.run_script()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_unknown_identity_is_mismatch(self):
        self.commit("Someone Else", "someone@example.com")
        proc = self.run_script()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("mismatch", proc.stdout)

    def test_local_config_company_email_is_must_fix(self):
        subprocess.run(["git", "-C", self.repo, "config", "--local",
                        "user.email", "masonxhuang@tencent.com"], check=True)
        proc = self.run_script()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("must-fix", proc.stdout)

    def test_missing_local_config_falls_back_to_global(self):
        subprocess.run(["git", "-C", self.repo, "config", "--local",
                        "--unset", "user.name"], check=True)
        subprocess.run(["git", "-C", self.repo, "config", "--local",
                        "--unset", "user.email"], check=True)
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        (Path(home.name) / ".gitconfig").write_text(
            "[user]\n\tname = masonxhuang\n\temail = masonxhuang@tencent.com\n")
        proc = self.run_script(env=dict(os.environ, HOME=home.name))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("must-fix", proc.stdout)
        self.assertIn("not set locally", proc.stdout)

    def test_json_output(self):
        self.commit("masonxhuang", "masonxhuang@tencent.com")
        proc = self.run_script("--json")
        self.assertEqual(proc.returncode, 1)
        data = json.loads(proc.stdout)
        self.assertFalse(data["summary"]["clean"])
        self.assertGreaterEqual(data["summary"]["must_fix"], 1)
        self.assertTrue(any(f["section"] == "history" for f in data["findings"]))

    def test_usage_error_exits_2(self):
        proc = self.run_script("--no-such-flag")
        self.assertEqual(proc.returncode, 2)

    def test_not_a_repo_exits_2(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "-C", self.tmp.name + "/nope", "--no-github"],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
