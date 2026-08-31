from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "resolve_orchestration_config.py"
)
PROJECT = Path(".local/large-task-orchestrator/orchestrator.json")
USER = Path("mason-skills/large-task-orchestrator/orchestrator.json")


def candidate(agent: str) -> dict[str, str]:
    return {"agent": agent}


def profile(name: str, agent: str, effort: str, role: str | None = None) -> dict[str, Any]:
    match = {"agent": agent}
    if role is not None:
        match["role"] = role
    return {
        "name": name,
        "match": match,
        "effort_by_difficulty": {"standard": effort},
    }


class ResolveOrchestrationConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.config_home = self.root / "config"
        self.user_path = self.config_home / USER
        self.project_path = self.repository / PROJECT
        self.environment = os.environ.copy()
        self.environment["XDG_CONFIG_HOME"] = str(self.config_home)
        self.environment["HOME"] = str(self.root / "home")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_json(self, path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def base_config(self, validator: str = "pi") -> dict[str, Any]:
        return {
            "version": 1,
            "routing": {
                "worker": {
                    "default": [candidate("codex")],
                    "frontend": [candidate("kimi"), candidate("codex")],
                },
                "validator": {"default": [candidate(validator)]},
            },
            "profiles": [
                profile("shared", "codex", "medium", "worker"),
                profile("user-only", validator, "high", "validator"),
            ],
        }

    def run_cli(
        self, *, expected: int = 0
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--repository",
                str(self.repository),
            ],
            capture_output=True,
            text=True,
            check=False,
            env=self.environment,
            timeout=5,
        )
        self.assertEqual(result.returncode, expected, result.stderr or result.stdout)
        payload: dict[str, Any] = {}
        if result.stdout:
            parsed = json.loads(result.stdout)
            if not isinstance(parsed, dict):
                self.fail(f"CLI JSON must be an object: {parsed!r}")
            payload = parsed
        return result, payload

    def test_project_validator_route_overrides_user_route(self) -> None:
        self.write_json(self.user_path, self.base_config(validator="pi"))
        project = {
            "version": 1,
            "routing": {
                "validator": {"default": [candidate("codexp")]},
            },
            "profiles": [],
        }
        self.write_json(self.project_path, project)

        _, result = self.run_cli()

        self.assertEqual(
            result["config"]["routing"]["validator"]["default"],
            [candidate("codexp")],
        )
        self.assertEqual(result["sources"]["user"]["status"], "loaded")
        self.assertEqual(result["sources"]["project"]["status"], "loaded")
        self.assertEqual(result["sources"]["user"]["path"], str(self.user_path))
        self.assertEqual(result["sources"]["project"]["path"], str(self.project_path))

    def test_absent_project_is_reported_and_user_config_is_used(self) -> None:
        self.write_json(self.user_path, self.base_config(validator="pi"))

        _, result = self.run_cli()

        self.assertEqual(result["sources"]["project"]["status"], "absent")
        self.assertEqual(
            result["config"]["routing"]["validator"]["default"],
            [candidate("pi")],
        )

    def test_malformed_project_fails_closed_and_names_path(self) -> None:
        self.write_json(self.user_path, self.base_config())
        self.project_path.parent.mkdir(parents=True)
        self.project_path.write_text('{"version": 1,\n', encoding="utf-8")

        result, payload = self.run_cli(expected=1)

        self.assertEqual(payload, {})
        self.assertIn(str(self.project_path), result.stderr)
        self.assertIn("malformed JSON", result.stderr)

    def test_dangling_project_source_fails_closed_and_names_path(self) -> None:
        self.write_json(self.user_path, self.base_config())
        self.project_path.parent.mkdir(parents=True)
        try:
            self.project_path.symlink_to(self.root / "missing-project-config.json")
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlink unavailable: {error}")

        result, payload = self.run_cli(expected=1)

        self.assertEqual(payload, {})
        self.assertEqual(result.stdout, "")
        self.assertIn(str(self.project_path), result.stderr)
        self.assertIn("symlink", result.stderr.lower())

    def test_project_parent_symlink_fails_closed(self) -> None:
        self.write_json(self.user_path, self.base_config())
        outside = self.root / "outside"
        self.write_json(outside / "orchestrator.json", self.base_config("codexp"))
        (self.repository / ".local").mkdir()
        try:
            (self.repository / ".local" / "large-task-orchestrator").symlink_to(
                outside,
                target_is_directory=True,
            )
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlink unavailable: {error}")

        result, payload = self.run_cli(expected=1)

        self.assertEqual(payload, {})
        self.assertEqual(result.stdout, "")
        self.assertIn(str(self.project_path), result.stderr)
        self.assertIn("symlink", result.stderr.lower())

    def test_fifo_project_source_fails_closed_without_blocking(self) -> None:
        self.write_json(self.user_path, self.base_config())
        self.project_path.parent.mkdir(parents=True)
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFO unavailable")
        try:
            os.mkfifo(self.project_path)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"FIFO unavailable: {error}")

        result, payload = self.run_cli(expected=1)

        self.assertEqual(payload, {})
        self.assertIn(str(self.project_path), result.stderr)
        self.assertIn("regular file", result.stderr)

    def test_boolean_version_is_rejected(self) -> None:
        config = self.base_config()
        config["version"] = True
        self.write_json(self.user_path, config)

        result, payload = self.run_cli(expected=1)

        self.assertEqual(payload, {})
        self.assertEqual(result.stdout, "")
        self.assertIn(str(self.user_path), result.stderr)
        self.assertIn("version", result.stderr)
        self.assertIn("integer 1", result.stderr)

    def test_routes_replace_whole_key_and_profiles_merge_by_name(self) -> None:
        self.write_json(self.user_path, self.base_config())
        project = {
            "version": 1,
            "routing": {
                "worker": {"frontend": [candidate("codexp")]},
                "validator": {
                    "default": [
                        {
                            "agent": "codexp",
                            "model_contains": "gpt-5.6",
                        }
                    ]
                },
            },
            "profiles": [
                profile("shared", "codexp", "max", "worker"),
                profile("project-only", "codexp", "low", "validator"),
            ],
        }
        self.write_json(self.project_path, project)

        _, result = self.run_cli()
        config = result["config"]

        self.assertEqual(
            config["routing"]["worker"]["default"], [candidate("codex")]
        )
        self.assertEqual(
            config["routing"]["worker"]["frontend"], [candidate("codexp")]
        )
        self.assertEqual(
            config["routing"]["validator"]["default"],
            [{"agent": "codexp", "model_contains": "gpt-5.6"}],
        )
        self.assertEqual(
            [item["name"] for item in config["profiles"]],
            ["shared", "project-only", "user-only"],
        )
        self.assertEqual(
            config["profiles"][0]["effort_by_difficulty"]["standard"], "max"
        )

    def test_unknown_candidate_field_is_rejected_with_field_path(self) -> None:
        config = self.base_config()
        config["routing"]["validator"]["default"][0]["unexpected"] = True
        self.write_json(self.user_path, config)

        result, _ = self.run_cli(expected=1)

        self.assertIn(str(self.user_path), result.stderr)
        self.assertIn("routing.validator.default[0]", result.stderr)
        self.assertIn("unknown fields", result.stderr)

    def test_non_string_profile_role_is_rejected_cleanly(self) -> None:
        config = self.base_config()
        config["profiles"][0]["match"]["role"] = []
        self.write_json(self.user_path, config)

        result, payload = self.run_cli(expected=1)

        self.assertEqual(payload, {})
        self.assertIn("profiles[0].match.role", result.stderr)
        self.assertIn("must be worker or validator", result.stderr)


if __name__ == "__main__":
    unittest.main()
