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

        self.assertEqual(
            RUNNER.PROMPT_FILE.read_text(encoding="utf-8"), RUNNER.EXPECTED_PROMPT
        )
        self.assertNotIn("provider", RUNNER.EXPECTED_PROMPT)
        self.assertNotIn("session", RUNNER.EXPECTED_PROMPT)
        self.assertNotIn("成功标准", RUNNER.EXPECTED_PROMPT)
        for forbidden in ("route", "sandbox", "oracle", "路由", "沙箱"):
            self.assertNotIn(forbidden, RUNNER.EXPECTED_PROMPT.lower())

    def test_project_config_has_one_candidate_per_external_role(self) -> None:
        args = argparse.Namespace(
            worker_agent="pi",
            validator_agent="pi",
            worker_effort="high",
            validator_effort="low",
        )
        expected = {
            "worker": RUNNER.ExpectedAgent(
                "pi", ("npx", "pi-acp@^0.0.31")
            ),
            "validator": RUNNER.ExpectedAgent(
                "pi", ("npx", "pi-acp@^0.0.31")
            ),
        }

        config = RUNNER.build_project_config(args, expected)

        self.assertEqual(
            config["routing"]["worker"]["default"],
            [{"agent": "pi"}],
        )
        self.assertEqual(
            config["routing"]["validator"]["default"],
            [{"agent": "pi"}],
        )
        self.assertEqual(
            config["profiles"][0]["match"], {"role": "worker", "agent": "pi"}
        )
        self.assertEqual(
            config["profiles"][1]["match"], {"role": "validator", "agent": "pi"}
        )

    def test_registered_argv_passes_through_verbatim_without_launchers(
        self,
    ) -> None:
        from unittest import mock

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            evidence = root / "evidence"
            repository.mkdir()
            evidence.mkdir()
            workspace = RUNNER.Workspace(
                root, repository, root / "origin.git", evidence, "initial"
            )
            args = argparse.Namespace(
                worker_agent="codexl",
                validator_agent="pi",
                worker_effort="high",
                validator_effort="low",
            )
            registered_argv = [
                "/usr/bin/env",
                "CODEXL_HOME=/root/.codexl",
                "npx",
                "-y",
                "@agentclientprotocol/codex-acp@^1.1.5",
            ]
            completed = subprocess.CompletedProcess(
                [],
                0,
                json.dumps(
                    {"agents": {"codexl": {"argv": registered_argv}}}
                ),
                "",
            )
            with mock.patch.object(RUNNER, "run_command", return_value=completed):
                expected = RUNNER.resolve_expected_agents(
                    args, workspace, "/usr/bin/acpx"
                )
            integrity = RUNNER.install_project_config(workspace, args, expected)

            self.assertEqual(
                expected["worker"].argv, tuple(registered_argv)
            )
            # 内置 pi 不在 acpx config show 中，使用 harness 锁定的适配器 argv。
            self.assertEqual(
                expected["validator"].argv, RUNNER.BUILTIN_AGENT_ARGVS["pi"]
            )
            self.assertFalse((root / "capability-launchers").exists())
            config = json.loads(integrity.project_config.content)
            # 位置式 agent 名才会持久化 agent_argv；路由不写 acpx_command。
            self.assertEqual(
                config["routing"]["worker"]["default"],
                [{"agent": "codexl"}],
            )
            self.assertEqual(
                config["routing"]["validator"]["default"],
                [{"agent": "pi"}],
            )
            self.assertEqual(config["profiles"][0]["match"]["agent"], "codexl")
            self.assertEqual(config["profiles"][1]["match"]["agent"], "pi")
            RUNNER.verify_harness_integrity(workspace, integrity)

    def test_validated_registered_argv_rejects_unsafe_shapes(self) -> None:
        cases = {
            "command-form": ({"command": "codex-acp"}, "structured argv"),
            "argv-missing": ({}, "structured argv"),
            "argv-empty": ({"argv": []}, "structured argv"),
            "argv-non-string": (
                {"argv": ["npx", 1]},
                "structured argv",
            ),
            "newline-token": (
                {"argv": ["npx", "pi-acp\n"]},
                "含控制字符",
            ),
            "nul-token": (
                {"argv": ["npx", "pi-acp\x00"]},
                "含控制字符",
            ),
        }
        for name, (entry, message) in cases.items():
            with self.subTest(name=name):
                with self.assertRaisesRegex(
                    RUNNER.HarnessEnvironmentError, message
                ):
                    RUNNER.validated_registered_argv(
                        entry.get("argv"), "alias"
                    ) if "argv" in entry else RUNNER.validated_registered_argv(
                        None, "alias"
                    )

    def test_resolve_expected_agents_fail_closed_on_unknown_and_builtin_pinned(
        self,
    ) -> None:
        from unittest import mock

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            evidence = root / "evidence"
            repository.mkdir()
            evidence.mkdir()
            workspace = RUNNER.Workspace(
                root, repository, root / "origin.git", evidence, "initial"
            )
            args = argparse.Namespace(
                worker_agent="pi",
                validator_agent="unknown-agent",
                worker_effort="high",
                validator_effort="low",
            )
            completed = subprocess.CompletedProcess(
                [], 0, json.dumps({"agents": {}}), ""
            )
            with mock.patch.object(RUNNER, "run_command", return_value=completed):
                with self.assertRaisesRegex(
                    RUNNER.HarnessEnvironmentError, "unknown-agent"
                ):
                    RUNNER.resolve_expected_agents(args, workspace, "acpx")

            args.validator_agent = "pi"
            with mock.patch.object(RUNNER, "run_command", return_value=completed):
                expected = RUNNER.resolve_expected_agents(args, workspace, "acpx")
            self.assertEqual(
                expected["worker"].argv,
                ("npx", RUNNER.PI_ACP_ADAPTER_SPEC),
            )
            self.assertEqual(
                expected["validator"].argv,
                ("npx", RUNNER.PI_ACP_ADAPTER_SPEC),
            )

    def test_harness_integrity_rejects_config_drift(self) -> None:
        from unittest import mock

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            evidence = root / "evidence"
            repository.mkdir()
            evidence.mkdir()
            workspace = RUNNER.Workspace(
                root, repository, root / "origin.git", evidence, "initial"
            )
            args = argparse.Namespace(
                worker_agent="pi",
                validator_agent="pi",
                worker_effort="high",
                validator_effort="low",
            )
            completed = subprocess.CompletedProcess(
                [], 0, json.dumps({"agents": {}}), ""
            )
            with mock.patch.object(RUNNER, "run_command", return_value=completed):
                expected = RUNNER.resolve_expected_agents(args, workspace, "acpx")
            integrity = RUNNER.install_project_config(workspace, args, expected)

            RUNNER.verify_harness_integrity(workspace, integrity)

            config = integrity.project_config
            config.path.write_bytes(config.content + b" ")
            with self.assertRaisesRegex(RUNNER.HarnessError, "content/hash 漂移"):
                RUNNER.verify_harness_integrity(workspace, integrity)
            config.path.write_bytes(config.content)
            config.path.chmod(0o644)
            with self.assertRaisesRegex(RUNNER.HarnessError, "mode 漂移"):
                RUNNER.verify_harness_integrity(workspace, integrity)
            config.path.chmod(RUNNER.PROJECT_CONFIG_MODE)
            try:
                config.path.unlink()
                config.path.symlink_to(config.path.with_name("elsewhere.json"))
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"symlink unavailable: {error}")
            with self.assertRaisesRegex(RUNNER.HarnessError, "普通非 symlink"):
                RUNNER.verify_harness_integrity(workspace, integrity)

    def test_verify_fixture_path_rejects_symlink_or_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            repository.mkdir()
            target = root / "outside.txt"
            target.write_text("hello\n", encoding="utf-8")
            link = repository / "greeting.txt"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"symlink unavailable: {error}")

            with self.assertRaisesRegex(RUNNER.HarnessError, "普通非 symlink"):
                RUNNER.verify_fixture_path(link, repository, "greeting.txt")

            with self.assertRaisesRegex(RUNNER.HarnessError, "不在 fixture repository"):
                RUNNER.verify_fixture_path(target, repository, "outside")

    def test_queue_artifacts_keep_lexical_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            queue = Path(directory) / "queues"
            queue.mkdir()
            artifact = queue / "queue-key.lock"
            artifact.write_text("{}", encoding="utf-8")

            self.assertEqual(
                RUNNER.queue_artifact_paths(queue, "queue-key"), {artifact}
            )

    def test_generation_scoped_queue_sockets_are_confined_to_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            socket_dir = Path(directory) / "acpx-home"
            socket_dir.mkdir()
            own = socket_dir / "queue-key-1z.sock"
            own.write_text("", encoding="utf-8")
            legacy = socket_dir / "queue-key.sock"
            legacy.write_text("", encoding="utf-8")
            foreign = socket_dir / "other-key-1z.sock"
            foreign.write_text("", encoding="utf-8")
            symlink = socket_dir / "queue-key-2.sock"
            try:
                symlink.symlink_to(own)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"symlink unavailable: {error}")

            self.assertEqual(
                RUNNER.queue_socket_artifact_paths(socket_dir, "queue-key"),
                {own, legacy},
            )

    def test_exact_route_rejects_wrapper_interchange_and_base_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected_argv = ("npx", "pi-acp@^0.0.31")
            expected = RUNNER.ExpectedAgent("pi", expected_argv)
            args = argparse.Namespace(
                worker_agent="pi",
                validator_agent="pi",
                expected_agents={"worker": expected},
            )
            variants = {
                "base-fallback": ("npx", "pi-acp"),
                "wrapper-interchange": (
                    "/usr/bin/env",
                    "npx",
                    "pi-acp@^0.0.31",
                ),
            }
            for name, actual in variants.items():
                with self.subTest(name=name):
                    record = root / f"{name}.json"
                    record.write_text(
                        json.dumps(
                            {
                                "acpx_record_id": f"record-{name}",
                                "acp_session_id": f"provider-{name}",
                                "cwd": str(root),
                                "name": f"run-story-01-worker-{name}",
                                "agent_argv": list(actual),
                            }
                        ),
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(RUNNER.HarnessError, "route mismatch"):
                        RUNNER.basic_session(record, args)
            self.assertTrue(RUNNER.agent_argv_matches(expected, expected.argv))

    def test_route_validation_rejects_missing_empty_or_typed_persisted_argv(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected_argv = ("npx", "pi-acp@^0.0.31")
            expected = RUNNER.ExpectedAgent("pi", expected_argv)
            args = argparse.Namespace(
                worker_agent="pi",
                validator_agent="pi",
                expected_agents={"worker": expected},
            )
            cases = {
                "missing": {},
                "empty": {"agent_argv": []},
                "wrong-type": {"agentArgv": RUNNER.command_text(expected_argv)},
            }
            for name, persisted in cases.items():
                with self.subTest(name=name):
                    record = root / f"invalid-{name}.json"
                    record.write_text(
                        json.dumps(
                            {
                                "acpx_record_id": f"record-{name}",
                                "acp_session_id": f"provider-{name}",
                                "cwd": str(root),
                                "name": f"run-story-01-worker-{name}",
                                "agent_command": RUNNER.command_text(expected_argv),
                                **persisted,
                            }
                        ),
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(
                        RUNNER.HarnessError,
                        "persisted agent_argv/agentArgv.*非空字符串数组",
                    ):
                        RUNNER.basic_session(record, args)

    def test_host_record_filename_must_match_persisted_record_id(self) -> None:
        from unittest import mock

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sessions = root / "sessions"
            sessions.mkdir()
            record = sessions / "evil.json"
            record.write_text(
                json.dumps(
                    {
                        "acpx_record_id": "record-target",
                        "acp_session_id": "provider-target",
                        "cwd": str(root),
                        "name": "run-story-01-worker-target",
                        "agent_argv": ["pi"],
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(worker_agent="pi", validator_agent="pi")

            with mock.patch.object(RUNNER, "sessions_directory", return_value=sessions):
                with self.assertRaisesRegex(
                    RUNNER.HarnessError, "filename 与 acpx_record_id 不匹配"
                ):
                    RUNNER.basic_session(record, args)

    def test_host_active_stream_must_match_record_id(self) -> None:
        from unittest import mock

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sessions = root / "sessions"
            sessions.mkdir()
            foreign_stream = sessions / (
                f"{RUNNER.encoded_session_id('record-foreign')}.stream.ndjson"
            )
            foreign_stream.write_text(
                json.dumps(
                    {
                        "method": "session/prompt",
                        "params": {"sessionId": "provider-source"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            record_id = "record-source"
            record = sessions / f"{RUNNER.encoded_session_id(record_id)}.json"
            record.write_text(
                json.dumps(
                    {
                        "acpx_record_id": record_id,
                        "acp_session_id": "provider-source",
                        "cwd": str(root),
                        "name": "run-story-01-worker-source",
                        "agent_argv": ["pi"],
                        "event_log": {"active_path": str(foreign_stream)},
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(worker_agent="pi", validator_agent="pi")

            with mock.patch.object(RUNNER, "sessions_directory", return_value=sessions):
                with self.assertRaisesRegex(
                    RUNNER.HarnessError, "active_path 不匹配其 stream 文件名"
                ):
                    RUNNER.basic_session(record, args)

    def test_cleanup_artifacts_ignore_foreign_host_streams(self) -> None:
        from unittest import mock

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sessions = root / "sessions"
            sessions.mkdir()
            own_record_id = "record-own"
            own_record = sessions / f"{RUNNER.encoded_session_id(own_record_id)}.json"
            own_record.write_text("{}", encoding="utf-8")
            foreign_stream = sessions / (
                f"{RUNNER.encoded_session_id('record-foreign')}.stream.ndjson"
            )
            foreign_stream.write_text("", encoding="utf-8")
            own_stream = sessions / (
                f"{RUNNER.encoded_session_id(own_record_id)}.stream.ndjson"
            )
            own_stream.write_text("", encoding="utf-8")
            evidence = RUNNER.SessionEvidence(
                own_record,
                own_record_id,
                "provider-own",
                "run-worker-own",
                "worker",
                "pi",
                "pi",
                ("pi",),
                1,
                0,
                0,
                (foreign_stream, own_stream),
            )

            with mock.patch.object(RUNNER, "sessions_directory", return_value=sessions):
                paths = RUNNER.session_artifact_paths(evidence, sessions)

            self.assertIn(own_record, paths)
            self.assertIn(own_stream, paths)
            self.assertNotIn(foreign_stream, paths)

    def test_unknown_cleanup_record_can_fall_back_to_agent_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = root / "unknown.json"
            record.write_text(
                json.dumps(
                    {
                        "acpx_record_id": "record-unknown",
                        "acp_session_id": "provider-unknown",
                        "cwd": str(root),
                        "name": "run-story-01-unclassified",
                        "agent": "legacy-alias",
                        "agent_command": "legacy-runner --cleanup",
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(worker_agent="pi", validator_agent="pi")

            session = RUNNER.basic_session(record, args, validate_route=False)

            self.assertEqual(session.role, "unknown")
            self.assertEqual(session.agent, "legacy-alias")
            self.assertEqual(session.agent_argv, ("legacy-runner", "--cleanup"))

    def test_closed_unprompted_session_still_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events = root / "events.ndjson"
            events.write_text(
                json.dumps({"method": "session/new", "params": {"cwd": str(root)}})
                + "\n",
                encoding="utf-8",
            )
            record = root / "record.json"
            record.write_text(
                json.dumps(
                    {
                        "acpx_record_id": "record-closed",
                        "acp_session_id": "provider-closed",
                        "cwd": str(root),
                        "name": "run-story-01-worker-extra",
                        "agent_argv": ["pi"],
                        "closed": True,
                        "event_log": {"active_path": str(events)},
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(worker_agent="pi", validator_agent="pi")
            with self.assertRaisesRegex(RUNNER.HarnessError, "没有 session/prompt"):
                RUNNER.inspect_session(record, args)

    def test_session_inspection_accepts_one_creation_before_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events = root / "session.stream.ndjson"
            events.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {"method": "session/new", "params": {"cwd": str(root)}}
                        ),
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
                        "agent_argv": ["pi"],
                        "event_log": {"active_path": str(events)},
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(worker_agent="pi", validator_agent="pi")

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
                        "agent_argv": ["pi"],
                        "event_log": {"active_path": str(events)},
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(worker_agent="pi", validator_agent="pi")

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

        with self.assertRaisesRegex(RUNNER.HarnessError, "恰好发送一次"):
            RUNNER.verify_outer_prompt(ndjson + "\n" + ndjson)

        with self.assertRaisesRegex(RUNNER.HarnessError, "只允许一个纯 text"):
            RUNNER.verify_outer_prompt(
                json.dumps(
                    {
                        "method": "session/prompt",
                        "params": {
                            "prompt": [
                                {"type": "text", "text": RUNNER.EXPECTED_PROMPT},
                                {"type": "image", "data": "sensitive"},
                            ]
                        },
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
                worker_agent="pi",
                validator_agent="pi",
                expected_agents={
                    "worker": RUNNER.ExpectedAgent("pi", ("npx", "pi-acp@^0.0.31"))
                },
            )

            with self.assertRaisesRegex(RUNNER.HarnessError, "route mismatch"):
                RUNNER.basic_session(record, args)

    def test_route_validation_compares_command_text_with_persisted_argv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = root / "record.json"
            argv = ["pi", "--safe"]
            record.write_text(
                json.dumps(
                    {
                        "acpx_record_id": "record-command",
                        "acp_session_id": "provider-command",
                        "cwd": str(root),
                        "name": "run-story-01-worker-command",
                        "agent_command": "pi --different",
                        "agent_argv": argv,
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(worker_agent="pi", validator_agent="pi")

            with self.assertRaisesRegex(
                RUNNER.HarnessError, "agent_command 与 persisted agent_argv 不一致"
            ):
                RUNNER.basic_session(record, args)

    def test_conflicting_argv_field_spellings_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = root / "record.json"
            record.write_text(
                json.dumps(
                    {
                        "acpx_record_id": "record-fields",
                        "acp_session_id": "provider-fields",
                        "cwd": str(root),
                        "name": "run-story-01-worker-fields",
                        "agent_argv": ["pi"],
                        "agentArgv": ["other"],
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(worker_agent="pi", validator_agent="pi")

            with self.assertRaisesRegex(RUNNER.HarnessError, "字段冲突"):
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

            with self.assertRaisesRegex(
                RUNNER.HarnessEnvironmentError, "未绑定当前源码"
            ):
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
                    agent="pi",
                    agent_command="pi",
                    agent_argv=("pi",),
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
                            "agent": "pi",
                            "session": provider,
                        }
                    )
            detail = {"run": {"recent_events": detail_events}}
            results = [
                subprocess.CompletedProcess(
                    [], 0, json.dumps({"active_run": None}), ""
                ),
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
                    agent="pi",
                    agent_command="pi",
                    agent_argv=("pi",),
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
                subprocess.CompletedProcess(
                    [], 0, json.dumps({"active_run": None}), ""
                ),
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
                mock.patch.object(RUNNER.tempfile, "mkdtemp", return_value=str(root)),
                mock.patch.object(RUNNER, "prepare_workspace", return_value=workspace),
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

    def test_archive_evidence_is_private(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            evidence = base / "evidence"
            evidence.mkdir()
            nested = evidence / "sessions"
            nested.mkdir()
            (evidence / "summary-source.txt").write_text("sensitive", encoding="utf-8")
            (nested / "record.json").write_text("{}", encoding="utf-8")
            workspace = RUNNER.Workspace(
                root=base / "workspace",
                repository=base / "repository",
                remote=base / "remote.git",
                evidence=evidence,
                initial_commit="initial",
            )
            destination = RUNNER.archive_evidence(
                workspace, base / "archive", {"run_id": "run-private"}
            )

            self.assertEqual(destination.stat().st_mode & 0o777, 0o700)
            self.assertEqual(
                (destination / "sessions").stat().st_mode & 0o777, 0o700
            )
            self.assertEqual(
                (destination / "summary-source.txt").stat().st_mode & 0o777, 0o600
            )
            self.assertEqual(
                (destination / "sessions" / "record.json").stat().st_mode & 0o777,
                0o600,
            )

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
                "worker": RUNNER.ExpectedAgent("pi", ("npx", "pi-acp@^0.0.31")),
                "validator": RUNNER.ExpectedAgent("pi", ("npx", "pi-acp@^0.0.31")),
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
                mock.patch.object(RUNNER.tempfile, "mkdtemp", return_value=str(root)),
                mock.patch.object(RUNNER, "prepare_workspace", return_value=workspace),
                mock.patch.object(
                    RUNNER, "resolve_expected_agents", return_value=expected
                ),
                mock.patch.object(
                    RUNNER, "snapshot_session_records", return_value=set()
                ),
                mock.patch.object(RUNNER, "run_command", return_value=completed),
                mock.patch.object(RUNNER, "verify_harness_integrity"),
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
                mock.patch.object(RUNNER, "snapshot_session_evidence", return_value=[]),
                mock.patch.object(
                    RUNNER,
                    "cleanup_test_sessions",
                    side_effect=RuntimeError("CLEANUP-BOOM"),
                ),
            ):
                with self.assertRaisesRegex(
                    RUNNER.HarnessError, "清理失败.*CLEANUP-BOOM"
                ):
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

    def test_run_command_converts_subprocess_timeout_to_harness_error(self) -> None:
        from unittest import mock

        with mock.patch.object(
            RUNNER.subprocess,
            "run",
            side_effect=RUNNER.subprocess.TimeoutExpired(["hang"], 1),
        ):
            with self.assertRaisesRegex(RUNNER.HarnessError, "命令超时"):
                RUNNER.run_command(["hang"], cwd=Path("/tmp"), timeout=1.0)

    def test_dry_run_discloses_safe_route_boundaries(self) -> None:
        args = RUNNER.build_parser().parse_args(["--dry-run"])

        payload = RUNNER.dry_run(args)

        preflight = payload["route_preflight"]
        self.assertTrue(preflight["uses_bounded_acp_session_handshake"])
        self.assertTrue(preflight["rejects_raw_adapter_help_preflight"])
        self.assertEqual(
            preflight["builtin_routes"], {"pi": ["npx", RUNNER.PI_ACP_ADAPTER_SPEC]}
        )
        self.assertTrue(preflight["accepts_registered_structured_argv_aliases"])
        self.assertTrue(preflight["rejects_command_form_and_unknown_builtin"])
        self.assertTrue(preflight["requires_persisted_nonempty_string_agent_argv"])
        self.assertTrue(preflight["requires_persisted_argv_equal_expected_argv"])
        self.assertTrue(preflight["constructs_no_sandbox_launcher"])
        self.assertTrue(preflight["reject_control_characters"])

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
