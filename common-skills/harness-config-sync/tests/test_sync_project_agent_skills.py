from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync_project_agent_skills.py"


class SyncProjectAgentSkillsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.repo = self.root / "repo"
        (self.repo / ".agents" / "skills").mkdir(parents=True)

    def make_skill(self, relative_path: str, name: str) -> Path:
        skill = self.repo / relative_path
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: test\n---\n\n# {name}\n",
            encoding="utf-8",
        )
        return skill

    def write_catalog(self, entries: list[tuple[str, str]]) -> None:
        catalog = {"skills": [{"name": name, "path": path} for name, path in entries]}
        (self.repo / ".agents" / "skill-catalog.json").write_text(
            json.dumps(catalog), encoding="utf-8"
        )

    def run_script(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), *arguments],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_apply_creates_relative_canonical_link_and_is_idempotent(self) -> None:
        self.make_skill(".agents/skills/demo", "demo")
        self.write_catalog([("demo", ".agents/skills/demo")])

        applied = self.run_script("--target", ".kiro/skills", "--apply")

        self.assertEqual(applied.returncode, 0, applied.stderr)
        target = self.repo / ".kiro" / "skills" / "demo"
        self.assertTrue(target.is_symlink())
        self.assertEqual(os.readlink(target), "../../.agents/skills/demo")
        self.assertEqual(target.resolve(), (self.repo / ".agents" / "skills" / "demo").resolve())

        repeated = self.run_script("--target", ".kiro/skills", "--apply")
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertIn("KEEP", repeated.stdout)
        self.assertIn("Applied: 0 created, 1 already correct.", repeated.stdout)

    def test_repository_internal_symlink_source_keeps_agents_entry_as_link_target(self) -> None:
        tool_skill = self.make_skill("tools/tool-skill", "tool-skill")
        canonical = self.repo / ".agents" / "skills" / "tool-skill"
        canonical.symlink_to("../../tools/tool-skill", target_is_directory=True)
        self.write_catalog([("tool-skill", ".agents/skills/tool-skill")])

        result = self.run_script("--target", ".claude/skills", "--apply")

        self.assertEqual(result.returncode, 0, result.stderr)
        target = self.repo / ".claude" / "skills" / "tool-skill"
        self.assertEqual(os.readlink(target), "../../.agents/skills/tool-skill")
        self.assertEqual(target.resolve(), tool_skill.resolve())

    def test_symlink_source_outside_repository_is_rejected(self) -> None:
        external = self.root / "external-skill"
        external.mkdir()
        (external / "SKILL.md").write_text("not empty", encoding="utf-8")
        canonical = self.repo / ".agents" / "skills" / "external-skill"
        canonical.symlink_to(external, target_is_directory=True)
        self.write_catalog([("external-skill", ".agents/skills/external-skill")])

        result = self.run_script("--apply")

        self.assertEqual(result.returncode, 2)
        self.assertIn("escapes the repository", result.stderr)
        self.assertFalse((self.repo / ".kiro" / "skills").exists())

    def test_conflict_prevents_every_planned_write(self) -> None:
        self.make_skill(".agents/skills/alpha", "alpha")
        self.make_skill(".agents/skills/beta", "beta")
        self.write_catalog(
            [("alpha", ".agents/skills/alpha"), ("beta", ".agents/skills/beta")]
        )
        target_root = self.repo / ".codebuddy" / "skills"
        target_root.mkdir(parents=True)
        (target_root / "alpha").write_text("conflict", encoding="utf-8")

        result = self.run_script("--target", ".codebuddy/skills", "--apply")

        self.assertEqual(result.returncode, 2)
        self.assertIn("CONFLICT alpha", result.stderr)
        self.assertFalse((target_root / "beta").exists())

    def test_target_path_cannot_escape_repository(self) -> None:
        self.make_skill(".agents/skills/demo", "demo")
        self.write_catalog([("demo", ".agents/skills/demo")])

        result = self.run_script("--target", "../outside", "--apply")

        self.assertEqual(result.returncode, 2)
        self.assertIn("unsafe path", result.stderr)


if __name__ == "__main__":
    unittest.main()
