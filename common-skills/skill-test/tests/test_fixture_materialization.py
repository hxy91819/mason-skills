from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "materialize_fixture.py"
FIXTURES = Path(__file__).with_name("fixtures")
MARKER_NAME = ".skill-test-fixture.json"


class FixtureMaterializationTests(unittest.TestCase):
    def run_cli(self, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["python3", str(SCRIPT), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(expected, result.returncode, result.stderr)
        return result

    def materialize(self, *arguments: str) -> dict[str, object]:
        return json.loads(self.run_cli("materialize", *arguments).stdout)

    def test_fixture_source_exposes_no_agent_facing_files(self) -> None:
        files = [
            path.relative_to(FIXTURES)
            for path in sorted(FIXTURES.rglob("*"))
            if path.is_file()
        ]
        self.assertTrue(files)
        for relative in files:
            self.assertNotEqual("SKILL.md", relative.name, relative)
            self.assertTrue(relative.name.endswith(".fixture"), relative)

    def test_materialize_restores_a_usable_skill_in_a_temp_dir(self) -> None:
        payload = self.materialize()
        materialized = Path(str(payload["dir"]))
        try:
            self.assertEqual("echo-skill", payload["fixture"])
            skill_md = materialized / "SKILL.md"
            self.assertTrue(skill_md.is_file())
            text = skill_md.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n"), text)
            self.assertIn("name: echo-skill", text)
            self.assertTrue((materialized / "agents" / "openai.yaml").is_file())
            self.assertFalse(
                list(materialized.rglob("*.fixture")),
                "materialized copy must contain no template files",
            )
            self.assertTrue((materialized / MARKER_NAME).is_file())
            self.assertEqual(
                str(skill_md),
                payload["skill_md"],
                "reported path must point at the materialized SKILL.md",
            )
        finally:
            self.run_cli("clean", "--dir", str(materialized))

    def test_materialize_honors_dest_and_copies_template_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "echo-skill"
            self.materialize("--fixture", "echo-skill", "--dest", str(destination))
            try:
                self.assertEqual(
                    (FIXTURES / "echo-skill" / "SKILL.md.fixture").read_text(
                        encoding="utf-8"
                    ),
                    (destination / "SKILL.md").read_text(encoding="utf-8"),
                )
                self.assertEqual(
                    (
                        FIXTURES
                        / "echo-skill"
                        / "agents"
                        / "openai.yaml.fixture"
                    ).read_text(encoding="utf-8"),
                    (destination / "agents" / "openai.yaml").read_text(
                        encoding="utf-8"
                    ),
                )
                self.run_cli("materialize", "--dest", str(destination), expected=1)
            finally:
                self.run_cli("clean", "--dir", str(destination))

    def test_clean_rejects_directories_without_fixture_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.run_cli("clean", "--dir", temporary, expected=1)
            self.assertTrue(Path(temporary).exists())

    def test_materialize_rejects_unknown_fixture(self) -> None:
        self.run_cli("materialize", "--fixture", "missing-skill", expected=2)


if __name__ == "__main__":
    unittest.main()
