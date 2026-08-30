from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "run_black_box_e2e.py"
SPEC = importlib.util.spec_from_file_location("run_black_box_e2e", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


class RunBlackBoxE2ETest(unittest.TestCase):
    def test_prompt_is_exactly_skill_selection_and_original_task(self) -> None:
        RUNNER.validate_static_inputs()

        self.assertEqual(RUNNER.PROMPT_FILE.read_text(encoding="utf-8"), RUNNER.EXPECTED_PROMPT)
        self.assertNotIn("provider", RUNNER.EXPECTED_PROMPT)
        self.assertNotIn("session", RUNNER.EXPECTED_PROMPT)
        self.assertNotIn("成功标准", RUNNER.EXPECTED_PROMPT)

    def test_project_config_has_one_candidate_per_external_role(self) -> None:
        args = argparse.Namespace(
            worker_agent="codexp",
            validator_agent="kiro",
            worker_effort="high",
            validator_effort="low",
        )

        config = RUNNER.build_project_config(args)

        self.assertEqual(config["routing"]["worker"]["default"], [{"agent": "codexp"}])
        self.assertEqual(config["routing"]["validator"]["default"], [{"agent": "kiro"}])
        self.assertEqual(config["profiles"][0]["match"]["role"], "worker")
        self.assertEqual(config["profiles"][1]["match"]["role"], "validator")

    def test_session_inspection_accepts_one_creation_before_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events = root / "session.stream.ndjson"
            events.write_text(
                "\n".join(
                    [
                        json.dumps({"method": "session/new", "params": {"cwd": str(root)}}),
                        json.dumps(
                            {
                                "method": "session/prompt",
                                "params": {"sessionId": "provider-1"},
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            record = root / "record.json"
            record.write_text(
                json.dumps(
                    {
                        "acpx_record_id": "record-1",
                        "acp_session_id": "provider-1",
                        "cwd": str(root),
                        "name": "run-story-01-worker-1",
                        "event_log": {"active_path": str(events)},
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(worker_agent="codexp", validator_agent="codexp")

            inspected = RUNNER.inspect_session(record, args)

        self.assertEqual(inspected.prompt_count, 1)
        self.assertEqual(inspected.new_after_prompt, 0)
        self.assertEqual(inspected.resume_count, 0)
        self.assertEqual(inspected.provider_id, "provider-1")

    def test_session_inspection_rejects_reconnect_after_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events = root / "session.stream.ndjson"
            events.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "method": "session/prompt",
                                "params": {"sessionId": "provider-1"},
                            }
                        ),
                        json.dumps(
                            {
                                "method": "session/resume",
                                "params": {"sessionId": "provider-1"},
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            record = root / "record.json"
            record.write_text(
                json.dumps(
                    {
                        "acpx_record_id": "record-1",
                        "acp_session_id": "provider-1",
                        "cwd": str(root),
                        "name": "run-story-01-validator-1",
                        "event_log": {"active_path": str(events)},
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(worker_agent="codexp", validator_agent="codexp")

            with self.assertRaisesRegex(RUNNER.HarnessError, "continuity"):
                RUNNER.inspect_session(record, args)

    def test_outer_prompt_must_match_fixed_prompt(self) -> None:
        ndjson = json.dumps(
            {
                "method": "session/prompt",
                "params": {
                    "prompt": [
                        {"type": "text", "text": RUNNER.EXPECTED_PROMPT.rstrip("\n")}
                    ]
                },
            }
        )

        RUNNER.verify_outer_prompt(ndjson)

        with self.assertRaisesRegex(RUNNER.HarnessError, "prompt"):
            RUNNER.verify_outer_prompt(
                json.dumps(
                    {
                        "method": "session/prompt",
                        "params": {"prompt": [{"type": "text", "text": "leaked"}]},
                    }
                )
            )

    def test_route_identity_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = root / "record.json"
            record.write_text(
                json.dumps(
                    {
                        "acpx_record_id": "record-1",
                        "acp_session_id": "provider-1",
                        "cwd": str(root),
                        "name": "run-story-01-worker-1",
                        "agent_command": "wrong-agent acp",
                        "agent_argv": ["wrong-agent", "acp"],
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                worker_agent="codexp",
                validator_agent="codexp",
                expected_agents={
                    "worker": RUNNER.ExpectedAgent("codexp", ("expected-agent", "acp"))
                },
            )

            with self.assertRaisesRegex(RUNNER.HarnessError, "route mismatch"):
                RUNNER.basic_session(record, args)

    def test_live_requires_broad_permission_acknowledgement(self) -> None:
        args = argparse.Namespace(
            timeout=10,
            orchestrator_agent="kiro",
            worker_agent="codex",
            validator_agent=None,
            worker_effort="high",
            validator_effort="low",
            live=True,
            acknowledge_broad_permissions=False,
        )

        with self.assertRaisesRegex(
            RUNNER.HarnessEnvironmentError, "acknowledge-broad-permissions"
        ):
            RUNNER.validate_arguments(args)

    def test_skill_binding_rejects_a_stale_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stale = Path(directory) / "large-task-orchestrator"
            stale.mkdir()
            args = argparse.Namespace(orchestrator_agent="kiro", skill_registry=stale)

            with self.assertRaisesRegex(RUNNER.HarnessEnvironmentError, "未绑定当前源码"):
                RUNNER.validate_skill_binding(args)

    def test_run_history_must_link_to_actual_session_names(self) -> None:
        from unittest import mock

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            evidence = root / "evidence"
            repository.mkdir()
            evidence.mkdir()
            local_history = repository / RUNNER.RUN_HISTORY_RELATIVE
            local_history.parent.mkdir(parents=True)
            local_history.write_text("{}\n", encoding="utf-8")
            workspace = RUNNER.Workspace(
                root=root,
                repository=repository,
                remote=root / "remote.git",
                evidence=evidence,
                initial_commit="initial",
            )
            sessions = [
                RUNNER.SessionEvidence(
                    record_path=root / f"{role}.json",
                    record_id=f"record-{role}",
                    provider_id=f"provider-{role}",
                    name=f"actual-{role}-session",
                    role=role,
                    agent="codexp",
                    agent_command="codexp",
                    agent_argv=("codexp",),
                    prompt_count=1,
                    new_after_prompt=0,
                    resume_count=0,
                    event_paths=(),
                )
                for role in ("worker", "validator")
            ]
            summary = {
                "runs": [
                    {
                        "run_id": "run-1",
                        "outcome": "delivered",
                        "metrics": {
                            "attempts": 3,
                            "by_role": {"worker": 2, "validator": 1},
                            "by_outcome": {"worker-done": 2, "continue": 1},
                        },
                        "delivery": {"head": "head", "remote_head": "head"},
                    }
                ]
            }
            detail_events = []
            for attempt_id, role, provider in (
                ("actual-worker-session", "worker", "provider-worker"),
                ("actual-validator-session", "validator", "provider-validator"),
                ("invented-worker-session", "worker", "provider-invented"),
            ):
                for event_type in ("attempt-start", "attempt-finish"):
                    detail_events.append(
                        {
                            "event": event_type,
                            "attempt_id": attempt_id,
                            "role": role,
                            "agent": "codexp",
                            "session": provider,
                        }
                    )
            detail = {"run": {"recent_events": detail_events}}
            results = [
                subprocess.CompletedProcess([], 0, json.dumps({"active_run": None}), ""),
                subprocess.CompletedProcess([], 0, json.dumps(summary), ""),
                subprocess.CompletedProcess([], 0, json.dumps(detail), ""),
            ]
            with mock.patch.object(RUNNER, "run_command", side_effect=results):
                with self.assertRaisesRegex(RUNNER.HarnessError, "多重集不完全一致"):
                    RUNNER.verify_run_history(workspace, "head", "head", sessions)

    def test_run_history_rejects_duplicate_actual_session_names(self) -> None:
        from unittest import mock

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            evidence = root / "evidence"
            repository.mkdir()
            evidence.mkdir()
            workspace = RUNNER.Workspace(
                root=root,
                repository=repository,
                remote=root / "remote.git",
                evidence=evidence,
                initial_commit="initial",
            )
            sessions = [
                RUNNER.SessionEvidence(
                    record_path=root / f"record-{index}.json",
                    record_id=f"record-{index}",
                    provider_id=provider,
                    name=name,
                    role=role,
                    agent="codexp",
                    agent_command="codexp",
                    agent_argv=("codexp",),
                    prompt_count=1,
                    new_after_prompt=0,
                    resume_count=0,
                    event_paths=(),
                )
                for index, (name, role, provider) in enumerate(
                    (
                        ("same-worker", "worker", "provider-worker-1"),
                        ("same-worker", "worker", "provider-worker-2"),
                        ("only-validator", "validator", "provider-validator"),
                    )
                )
            ]
            summary = {
                "runs": [
                    {
                        "run_id": "run-1",
                        "outcome": "delivered",
                        "metrics": {
                            "attempts": 3,
                            "by_role": {"worker": 2, "validator": 1},
                            "by_outcome": {"worker-done": 2, "continue": 1},
                        },
                        "delivery": {"head": "head", "remote_head": "head"},
                    }
                ]
            }
            detail_events = [
                {"event": event_type, "attempt_id": attempt_id}
                for attempt_id in ("same-worker", "only-validator")
                for event_type in ("attempt-start", "attempt-finish")
            ]
            results = [
                subprocess.CompletedProcess([], 0, json.dumps({"active_run": None}), ""),
                subprocess.CompletedProcess([], 0, json.dumps(summary), ""),
                subprocess.CompletedProcess(
                    [], 0, json.dumps({"run": {"recent_events": detail_events}}), ""
                ),
            ]
            with mock.patch.object(RUNNER, "run_command", side_effect=results):
                with self.assertRaisesRegex(RUNNER.HarnessError, "session name 不唯一"):
                    RUNNER.verify_run_history(workspace, "head", "head", sessions)

    def test_cleanup_exceptions_preserve_primary_failure_and_archive(self) -> None:
        from unittest import mock

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "run"
            repository = root / "repository"
            evidence = root / "evidence"
            repository.mkdir(parents=True)
            evidence.mkdir()
            workspace = RUNNER.Workspace(
                root=root,
                repository=repository,
                remote=root / "remote.git",
                evidence=evidence,
                initial_commit="initial",
            )
            output = base / "archive"
            args = RUNNER.build_parser().parse_args(
                [
                    "--live",
                    "--acknowledge-broad-permissions",
                    "--output-dir",
                    str(output),
                ]
            )

            with (
                mock.patch.object(RUNNER, "validate_static_inputs"),
                mock.patch.object(RUNNER, "require_command", return_value="/fake"),
                mock.patch.object(
                    RUNNER, "validate_skill_binding", return_value=RUNNER.SKILL_DIR
                ),
                mock.patch.object(
                    RUNNER.tempfile, "mkdtemp", return_value=str(root)
                ),
                mock.patch.object(
                    RUNNER, "prepare_workspace", return_value=workspace
                ),
                mock.patch.object(
                    RUNNER,
                    "resolve_expected_agents",
                    side_effect=RUNNER.HarnessError("PRIMARY"),
                ),
                mock.patch.object(
                    RUNNER, "matching_test_record_paths", return_value=[]
                ),
                mock.patch.object(
                    RUNNER,
                    "snapshot_session_evidence",
                    side_effect=RuntimeError("SNAPSHOT-BOOM"),
                ),
                mock.patch.object(
                    RUNNER,
                    "cleanup_test_sessions",
                    side_effect=RuntimeError("CLEANUP-BOOM"),
                ),
            ):
                with self.assertRaisesRegex(RUNNER.HarnessError, "PRIMARY.*诊断目录"):
                    RUNNER.live_run(args)

            archives = list(output.iterdir())
            self.assertEqual(len(archives), 1)
            summary = json.loads(
                (archives[0] / "summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(summary["result"], "failed")
            self.assertEqual(summary["error"], "PRIMARY")
            self.assertEqual(
                summary["cleanup_errors"],
                [
                    "snapshot sessions: SNAPSHOT-BOOM",
                    "cleanup sessions: CLEANUP-BOOM",
                ],
            )
            self.assertIn("SNAPSHOT-BOOM", summary["cleanup_failure"])
            self.assertIn("CLEANUP-BOOM", summary["cleanup_failure"])
            self.assertEqual(summary["workspace"], str(root))
            self.assertTrue(root.is_dir())

    def test_cleanup_exception_turns_a_pass_into_an_archived_failure(self) -> None:
        from unittest import mock

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "run"
            repository = root / "repository"
            evidence = root / "evidence"
            repository.mkdir(parents=True)
            evidence.mkdir()
            workspace = RUNNER.Workspace(
                root=root,
                repository=repository,
                remote=root / "remote.git",
                evidence=evidence,
                initial_commit="initial",
            )
            output = base / "archive"
            args = RUNNER.build_parser().parse_args(
                [
                    "--live",
                    "--acknowledge-broad-permissions",
                    "--output-dir",
                    str(output),
                ]
            )
            expected = {
                "worker": RUNNER.ExpectedAgent("codex", ("codex-acp",)),
                "validator": RUNNER.ExpectedAgent("codex", ("codex-acp",)),
            }
            outer_event = (
                json.dumps(
                    {
                        "method": "session/prompt",
                        "params": {
                            "prompt": [
                                {
                                    "type": "text",
                                    "text": RUNNER.EXPECTED_PROMPT.rstrip("\n"),
                                }
                            ]
                        },
                    }
                )
                + "\n"
            )
            completed = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=outer_event, stderr=""
            )

            with (
                mock.patch.object(RUNNER, "validate_static_inputs"),
                mock.patch.object(RUNNER, "require_command", return_value="/fake"),
                mock.patch.object(
                    RUNNER, "validate_skill_binding", return_value=RUNNER.SKILL_DIR
                ),
                mock.patch.object(
                    RUNNER.tempfile, "mkdtemp", return_value=str(root)
                ),
                mock.patch.object(
                    RUNNER, "prepare_workspace", return_value=workspace
                ),
                mock.patch.object(
                    RUNNER, "resolve_expected_agents", return_value=expected
                ),
                mock.patch.object(RUNNER, "snapshot_session_records", return_value=set()),
                mock.patch.object(RUNNER, "run_command", return_value=completed),
                mock.patch.object(
                    RUNNER,
                    "verify_delivery",
                    return_value={"head": "commit", "remote_head": "commit"},
                ),
                mock.patch.object(RUNNER, "discover_test_sessions", return_value=[]),
                mock.patch.object(RUNNER, "verify_run_history", return_value={}),
                mock.patch.object(
                    RUNNER, "matching_test_record_paths", return_value=[]
                ),
                mock.patch.object(
                    RUNNER, "snapshot_session_evidence", return_value=[]
                ),
                mock.patch.object(
                    RUNNER,
                    "cleanup_test_sessions",
                    side_effect=RuntimeError("CLEANUP-BOOM"),
                ),
            ):
                with self.assertRaisesRegex(RUNNER.HarnessError, "清理失败.*CLEANUP-BOOM"):
                    RUNNER.live_run(args)

            archives = list(output.iterdir())
            self.assertEqual(len(archives), 1)
            summary = json.loads(
                (archives[0] / "summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(summary["result"], "failed")
            self.assertIn("CLEANUP-BOOM", summary["error"])
            self.assertEqual(
                summary["cleanup_errors"], ["cleanup sessions: CLEANUP-BOOM"]
            )
            self.assertEqual(summary["workspace"], str(root))
            self.assertTrue(root.is_dir())

    def test_cli_requires_an_explicit_mode(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)], capture_output=True, text=True, check=False
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("required", result.stderr)

    def test_validate_fixture_mode_never_calls_an_agent(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--validate-fixture", "--json"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "validate-fixture")
        self.assertTrue(payload["fixture_check_fails_before_story"])
        self.assertEqual(payload["plan_check"], "passed")


if __name__ == "__main__":
    unittest.main()
