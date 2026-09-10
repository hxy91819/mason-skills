import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "link_project_skill.py"
SOURCE = SCRIPT.parents[1]


class LinkProjectSkillTest(unittest.TestCase):
    def run_script(self, *args):
        return subprocess.run(
            ["python3", str(SCRIPT), *args],
            capture_output=True,
            text=True,
        )

    def test_creates_and_reuses_relative_link(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "fork"
            repository.mkdir()
            subprocess.run(["git", "init", "-q", str(repository)], check=True)

            preview = self.run_script("--repo", str(repository), "--skills-dir", ".bb/skills")
            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertIn("CREATE", preview.stdout)

            created = self.run_script(
                "--repo", str(repository), "--skills-dir", ".bb/skills", "--apply"
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            link = repository / ".bb" / "skills" / SOURCE.name
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), SOURCE.resolve())

            repeated = self.run_script(
                "--repo", str(repository), "--skills-dir", ".bb/skills", "--apply"
            )
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertIn("KEEP", repeated.stdout)

    def test_rejects_skill_directory_outside_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "fork"
            repository.mkdir()
            subprocess.run(["git", "init", "-q", str(repository)], check=True)

            result = self.run_script("--repo", str(repository), "--skills-dir", "../skills", "--apply")

            self.assertEqual(result.returncode, 2)
            self.assertIn("relative path", result.stderr)

    def test_rejects_repository_root_as_a_skills_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "fork"
            repository.mkdir()
            subprocess.run(["git", "init", "-q", str(repository)], check=True)

            result = self.run_script("--repo", str(repository), "--skills-dir", "./.", "--apply")

            self.assertEqual(result.returncode, 2)
            self.assertIn("relative path", result.stderr)

    def test_rejects_a_skills_parent_linked_outside_the_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "fork"
            outside = Path(directory) / "outside"
            repository.mkdir()
            outside.mkdir()
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            (repository / ".agents").symlink_to(outside, target_is_directory=True)

            result = self.run_script(
                "--repo", str(repository), "--skills-dir", ".agents/skills", "--apply"
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("outside the repository", result.stderr)
            self.assertFalse((outside / "skills" / SOURCE.name).exists())
