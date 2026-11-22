import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(os.name == "posix", "POSIX command installation")
class DispatchInstallTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.bin_dir = self.home / ".local" / "bin"
        self.link = self.bin_dir / "bb-dispatch"
        self.env = {**os.environ, "HOME": str(self.home)}

    def sync(self, mode):
        return subprocess.run(
            [sys.executable, str(Path(__file__).with_name("sync_skill_symlinks.py")),
             "--mode", mode, "--bb-dispatch-only"],
            env=self.env, capture_output=True, text=True, timeout=10,
        )

    def test_install_is_idempotent_and_command_resolves_in_fresh_shell(self):
        self.assertEqual(self.sync("check").returncode, 1)
        self.assertFalse(self.bin_dir.exists())
        for mode in ("apply", "apply", "check"):
            result = self.sync(mode)
            self.assertEqual(result.returncode, 0, result.stderr)
        shell = subprocess.run(
            ["sh", "-c", 'PATH="$HOME/.local/bin:$PATH"; command -v bb-dispatch && bb-dispatch --help'],
            env={**self.env, "PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin"},
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(shell.returncode, 0, shell.stderr)
        self.assertEqual(shell.stdout.splitlines()[0], str(self.link))
        self.assertFalse((self.home / ".agents").exists())

    def test_existing_command_is_preserved(self):
        self.bin_dir.mkdir(parents=True)
        self.link.write_text("existing command")
        self.assertEqual(self.sync("apply").returncode, 1)
        self.assertEqual(self.link.read_text(), "existing command")
