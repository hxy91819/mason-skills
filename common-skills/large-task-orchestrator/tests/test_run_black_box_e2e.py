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
            worker_agent="codexp",
            validator_agent="codexp",
            worker_effort="high",
            validator_effort="low",
        )
        witness = RUNNER.FileWitness(Path("/tmp/launcher"), 0o500, "hash", b"content")
        expected = {
            "worker": RUNNER.ExpectedAgent(
                "codexp", ("base", "worker"), ("final", "worker"), witness
            ),
            "validator": RUNNER.ExpectedAgent(
                "codexp", ("base", "validator"), ("final", "validator"), witness
            ),
        }

        config = RUNNER.build_project_config(args, expected)

        self.assertEqual(
            config["routing"]["worker"]["default"],
            [{"agent": "codexp", "acpx_command": "final worker"}],
        )
        self.assertEqual(
            config["routing"]["validator"]["default"],
            [{"agent": "codexp", "acpx_command": "final validator"}],
        )
        self.assertEqual(
            config["profiles"][0]["match"], {"role": "worker", "agent": "codexp"}
        )
        self.assertEqual(
            config["profiles"][1]["match"], {"role": "validator", "agent": "codexp"}
        )

    def test_safe_role_launchers_preserve_base_tokens_and_feed_full_commands(
        self,
    ) -> None:
        from unittest import mock

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            evidence = root / "evidence"
            repository.mkdir()
            evidence.mkdir()
            executable = root / "codex"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o700)
            trusted_npx = root / "npx"
            trusted_npx.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            trusted_npx.chmod(0o700)
            workspace = RUNNER.Workspace(
                root, repository, root / "origin.git", evidence, "initial"
            )
            args = argparse.Namespace(
                worker_agent="codexp",
                validator_agent="codexv",
                worker_effort="high",
                validator_effort="low",
            )
            worker_base = [
                "/usr/bin/env",
                "CODEX_HOME=/real/profile",
                f"CODEX_PATH={executable}",
                "npx",
                "-y",
                "@agentclientprotocol/codex-acp@^1.1.5",
            ]
            validator_base = [
                "/usr/bin/env",
                "CODEX_HOME=/real/profile",
                f"CODEX_PATH={executable}",
                "npx",
                "-y",
                "@agentclientprotocol/codex-acp@^1.1.5",
            ]
            completed = subprocess.CompletedProcess(
                [],
                0,
                json.dumps(
                    {
                        "agents": {
                            "codexp": {"argv": worker_base},
                            "codexv": {"argv": validator_base},
                        }
                    }
                ),
                "",
            )
            with (
                mock.patch.object(RUNNER, "run_command", return_value=completed),
                mock.patch.object(
                    RUNNER.shutil, "which", return_value=str(trusted_npx)
                ),
            ):
                expected = RUNNER.resolve_expected_agents(
                    args, workspace, "/usr/bin/acpx"
                )
            integrity = RUNNER.install_project_config(workspace, args, expected)

            self.assertNotEqual(
                expected["worker"].launcher.path, expected["validator"].launcher.path
            )
            for role, base in (("worker", worker_base), ("validator", validator_base)):
                item = expected[role]
                self.assertEqual(item.base_argv, tuple(base))
                changed = [
                    index
                    for index, pair in enumerate(zip(item.base_argv, item.argv))
                    if pair[0] != pair[1]
                ]
                self.assertEqual(changed, [2, 3])
                self.assertEqual(item.argv[3], str(trusted_npx))
                self.assertEqual(
                    item.launcher.path.parent, root / "capability-launchers"
                )
                self.assertNotIn(repository, item.launcher.path.parents)
                self.assertFalse(item.launcher.path.is_symlink())
                self.assertEqual(item.launcher.path.stat().st_mode & 0o777, 0o500)
            self.assertFalse((root / "capability-launchers").is_symlink())
            self.assertEqual(
                (root / "capability-launchers").stat().st_mode & 0o777, 0o700
            )
            worker_text = expected["worker"].launcher.path.read_text(encoding="utf-8")
            validator_text = expected["validator"].launcher.path.read_text(
                encoding="utf-8"
            )
            self.assertIn("--sandbox workspace-write", worker_text)
            self.assertIn("sandbox_workspace_write.network_access=false", worker_text)
            self.assertIn("--sandbox read-only", validator_text)
            config = json.loads(integrity.project_config.content)
            self.assertEqual(
                config["routing"]["worker"]["default"][0]["acpx_command"],
                RUNNER.command_text(expected["worker"].argv),
            )
            self.assertEqual(
                config["routing"]["validator"]["default"][0]["acpx_command"],
                RUNNER.command_text(expected["validator"].argv),
            )
            self.assertEqual(config["profiles"][0]["match"]["agent"], "codexp")
            self.assertEqual(config["profiles"][1]["match"]["agent"], "codexv")
            RUNNER.verify_harness_integrity(workspace, expected, integrity)

    def test_registered_codex_alias_rejects_unsafe_base_argv(self) -> None:
        from unittest import mock

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "codex"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o700)
            trusted_npx = root / "npx"
            trusted_npx.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            trusted_npx.chmod(0o700)
            untrusted_npx = root / "other" / "npx"
            untrusted_npx.parent.mkdir()
            untrusted_npx.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            untrusted_npx.chmod(0o700)
            non_executable = root / "not-executable"
            non_executable.write_text("x", encoding="utf-8")
            non_executable.chmod(0o600)
            directory_path = root / "directory"
            directory_path.mkdir()
            adapter = "@agentclientprotocol/codex-acp@1.2.3"
            cases = {
                "missing": (
                    ["/usr/bin/env", str(trusted_npx), adapter],
                    "恰好包含一个 CODEX_PATH",
                ),
                "duplicate": (
                    [
                        "/usr/bin/env",
                        f"CODEX_PATH={executable}",
                        f"CODEX_PATH={executable}",
                        str(trusted_npx),
                        adapter,
                    ],
                    "恰好包含一个 CODEX_PATH",
                ),
                "relative": (
                    [
                        "/usr/bin/env",
                        "CODEX_PATH=bin/codex",
                        str(trusted_npx),
                        adapter,
                    ],
                    "绝对路径",
                ),
                "non-regular": (
                    [
                        "/usr/bin/env",
                        f"CODEX_PATH={directory_path}",
                        str(trusted_npx),
                        adapter,
                    ],
                    "指向普通文件",
                ),
                "non-executable": (
                    [
                        "/usr/bin/env",
                        f"CODEX_PATH={non_executable}",
                        str(trusted_npx),
                        adapter,
                    ],
                    "不可执行",
                ),
                "non-codex-adapter": (
                    [
                        "/usr/bin/env",
                        f"CODEX_PATH={executable}",
                        str(trusted_npx),
                        "@agentclientprotocol/claude-agent-acp@1",
                    ],
                    "codex-acp adapter",
                ),
                "npm-package-redirection": (
                    [
                        "/usr/bin/env",
                        f"CODEX_PATH={executable}",
                        str(trusted_npx),
                        "@agentclientprotocol/codex-acp@npm:arbitrary-wrapper",
                    ],
                    "codex-acp adapter",
                ),
                "duplicate-codex-adapter": (
                    [
                        "/usr/bin/env",
                        f"CODEX_PATH={executable}",
                        str(trusted_npx),
                        adapter,
                        adapter,
                    ],
                    "恰好包含一个 codex-acp adapter",
                ),
                "decorated-arbitrary-executable": (
                    ["/bin/true", f"CODEX_PATH={executable}", adapter],
                    "受支持命令形状",
                ),
                "shell-command": (
                    [
                        "/usr/bin/env",
                        f"CODEX_PATH={executable}",
                        "/bin/sh",
                        "-c",
                        "exec arbitrary-wrapper",
                        adapter,
                    ],
                    "当前可信 npx 路径",
                ),
                "dynamic-wrapper": (
                    [
                        "/usr/bin/env",
                        f"CODEX_PATH={executable}",
                        str(untrusted_npx),
                        adapter,
                    ],
                    "当前可信 npx 路径",
                ),
                "codex-path-not-an-env-assignment": (
                    [
                        "/usr/bin/env",
                        str(trusted_npx),
                        f"CODEX_PATH={executable}",
                        adapter,
                    ],
                    "env 启动环境赋值",
                ),
                "adapter-not-first-positional": (
                    [
                        "/usr/bin/env",
                        f"CODEX_PATH={executable}",
                        str(trusted_npx),
                        "arbitrary-wrapper",
                        adapter,
                    ],
                    "首个位置参数",
                ),
                "path-hijack": (
                    [
                        "/usr/bin/env",
                        f"PATH={untrusted_npx.parent}",
                        f"CODEX_PATH={executable}",
                        "npx",
                        "-y",
                        adapter,
                    ],
                    "不安全 env 赋值.*PATH",
                ),
                "node-options-injection": (
                    [
                        "/usr/bin/env",
                        "NODE_OPTIONS=--require=/tmp/hostile.js",
                        f"CODEX_PATH={executable}",
                        str(trusted_npx),
                        adapter,
                    ],
                    "不安全 env 赋值.*NODE_OPTIONS",
                ),
                "npm-environment-injection": (
                    [
                        "/usr/bin/env",
                        "npm_config_registry=https://hostile.invalid",
                        f"CODEX_PATH={executable}",
                        str(trusted_npx),
                        adapter,
                    ],
                    "不安全 env 赋值.*npm_config_registry",
                ),
                "loader-environment-injection": (
                    [
                        "/usr/bin/env",
                        "LD_PRELOAD=/tmp/hostile.so",
                        f"CODEX_PATH={executable}",
                        str(trusted_npx),
                        adapter,
                    ],
                    "不安全 env 赋值.*LD_PRELOAD",
                ),
                "node-runner": (
                    [
                        "/usr/bin/env",
                        f"CODEX_PATH={executable}",
                        "/usr/bin/node",
                        adapter,
                    ],
                    "当前可信 npx 路径",
                ),
                "npm-runner": (
                    [
                        "/usr/bin/env",
                        f"CODEX_PATH={executable}",
                        "npm",
                        adapter,
                    ],
                    "只允许字面 npx",
                ),
                "other-relative-runner": (
                    [
                        "/usr/bin/env",
                        f"CODEX_PATH={executable}",
                        "bin/npx",
                        adapter,
                    ],
                    "只允许字面 npx",
                ),
                "untrusted-absolute-runner": (
                    [
                        "/usr/bin/env",
                        f"CODEX_PATH={executable}",
                        str(untrusted_npx),
                        adapter,
                    ],
                    "当前可信 npx 路径",
                ),
                "assignment-after-runner": (
                    [
                        "/usr/bin/env",
                        f"CODEX_PATH={executable}",
                        "npx",
                        adapter,
                        "CODEX_HOME=/late",
                    ],
                    "runner 后不得包含 env 赋值",
                ),
                "adapter-capability-override": (
                    [
                        "/usr/bin/env",
                        f"CODEX_PATH={executable}",
                        "npx",
                        adapter,
                        "--sandbox",
                        "danger-full-access",
                    ],
                    "adapter 必须是 runner 的最后一个参数",
                ),
                "assignment-order": (
                    [
                        "/usr/bin/env",
                        f"CODEX_PATH={executable}",
                        "CODEX_HOME=/late",
                        "npx",
                        adapter,
                    ],
                    "连续的可选 CODEX_HOME 后接必需 CODEX_PATH",
                ),
                "newline-token": (
                    [
                        "/usr/bin/env",
                        f"CODEX_PATH={executable}",
                        "npx",
                        adapter + "\n",
                    ],
                    "含控制字符",
                ),
                "nul-token": (
                    [
                        "/usr/bin/env",
                        f"CODEX_PATH={executable}",
                        "npx",
                        adapter + "\x00",
                    ],
                    "含控制字符",
                ),
            }
            with mock.patch.object(
                RUNNER.shutil, "which", return_value=str(trusted_npx)
            ):
                for name, (argv, message) in cases.items():
                    with self.subTest(name=name):
                        with self.assertRaisesRegex(
                            RUNNER.HarnessEnvironmentError, message
                        ):
                            RUNNER.registered_codex_base_argv({"argv": argv}, "alias")
                accepted = [
                    "/usr/bin/env",
                    "CODEX_HOME=/real/profile",
                    f"CODEX_PATH={executable}",
                    str(trusted_npx),
                    "-y",
                    adapter,
                ]
                self.assertEqual(
                    RUNNER.registered_codex_base_argv({"argv": accepted}, "alias"),
                    tuple(accepted),
                )
                real_shape = [
                    "/usr/bin/env",
                    "CODEX_HOME=/real/profile",
                    f"CODEX_PATH={executable}",
                    "npx",
                    "-y",
                    adapter,
                ]
                self.assertEqual(
                    RUNNER.registered_codex_base_argv({"argv": real_shape}, "alias"),
                    tuple(real_shape),
                )
            with self.assertRaisesRegex(
                RUNNER.HarnessEnvironmentError, "structured argv"
            ):
                RUNNER.registered_codex_base_argv({"command": "codex-acp"}, "alias")

    def test_trusted_npx_resolution_fails_closed(self) -> None:
        from unittest import mock

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "npx"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o700)
            non_executable = root / "not-executable"
            non_executable.write_text("x", encoding="utf-8")
            non_executable.chmod(0o600)
            folder = root / "folder"
            folder.mkdir()

            with mock.patch.object(
                RUNNER.shutil, "which", return_value=str(executable)
            ):
                self.assertEqual(RUNNER.trusted_npx_path(), executable)
            cases = {
                "missing": (None, "找不到 npx"),
                "relative": ("npx", "不是绝对路径"),
                "non-string": (Path(executable), "不是非空字符串"),
                "non-executable": (str(non_executable), "必须是可执行普通文件"),
                "directory": (str(folder), "必须是可执行普通文件"),
            }
            for name, (resolved, message) in cases.items():
                with self.subTest(name=name):
                    with mock.patch.object(
                        RUNNER.shutil, "which", return_value=resolved
                    ):
                        with self.assertRaisesRegex(
                            RUNNER.HarnessEnvironmentError, message
                        ):
                            RUNNER.trusted_npx_path()

    def test_harness_integrity_rejects_launcher_and_config_drift(self) -> None:
        from unittest import mock

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            evidence = root / "evidence"
            repository.mkdir()
            evidence.mkdir()
            executable = root / "codex"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o700)
            trusted_npx = root / "npx"
            trusted_npx.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            trusted_npx.chmod(0o700)
            workspace = RUNNER.Workspace(
                root, repository, root / "origin.git", evidence, "initial"
            )
            args = argparse.Namespace(
                worker_agent="codexp",
                validator_agent="codexp",
                worker_effort="high",
                validator_effort="low",
            )
            base = [
                "/usr/bin/env",
                f"CODEX_PATH={executable}",
                str(trusted_npx),
                "@agentclientprotocol/codex-acp@1",
            ]
            completed = subprocess.CompletedProcess(
                [], 0, json.dumps({"agents": {"codexp": {"argv": base}}}), ""
            )
            with (
                mock.patch.object(RUNNER, "run_command", return_value=completed),
                mock.patch.object(
                    RUNNER.shutil, "which", return_value=str(trusted_npx)
                ),
            ):
                expected = RUNNER.resolve_expected_agents(args, workspace, "acpx")
            integrity = RUNNER.install_project_config(workspace, args, expected)

            worker = expected["worker"].launcher
            worker.path.chmod(0o700)
            with self.assertRaisesRegex(RUNNER.HarnessError, "mode 漂移"):
                RUNNER.verify_harness_integrity(workspace, expected, integrity)
            worker.path.chmod(0o500)

            worker.path.chmod(0o700)
            worker.path.write_bytes(worker.content + b"# drift\n")
            worker.path.chmod(0o500)
            with self.assertRaisesRegex(RUNNER.HarnessError, "content/hash 漂移"):
                RUNNER.verify_harness_integrity(workspace, expected, integrity)
            worker.path.chmod(0o700)
            worker.path.write_bytes(worker.content)
            worker.path.chmod(0o500)

            try:
                worker.path.unlink()
                worker.path.symlink_to(expected["validator"].launcher.path)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"symlink unavailable: {error}")
            with self.assertRaisesRegex(RUNNER.HarnessError, "普通非 symlink"):
                RUNNER.verify_harness_integrity(workspace, expected, integrity)
            worker.path.unlink()
            worker.path.write_bytes(worker.content)
            worker.path.chmod(0o500)

            config = integrity.project_config
            config.path.write_bytes(config.content + b" ")
            with self.assertRaisesRegex(RUNNER.HarnessError, "content/hash 漂移"):
                RUNNER.verify_harness_integrity(workspace, expected, integrity)
            config.path.write_bytes(config.content)
            config.path.chmod(0o644)
            with self.assertRaisesRegex(RUNNER.HarnessError, "mode 漂移"):
                RUNNER.verify_harness_integrity(workspace, expected, integrity)

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
            witness = RUNNER.FileWitness(root / "worker", 0o500, "hash", b"worker")
            expected = RUNNER.ExpectedAgent(
                "codexp",
                ("env", "CODEX_PATH=/real/codex", "codex-acp"),
                ("env", "CODEX_PATH=/tmp/worker", "codex-acp"),
                witness,
            )
            args = argparse.Namespace(
                worker_agent="codexp",
                validator_agent="codexp",
                expected_agents={"worker": expected},
            )
            variants = {
                "base-fallback": expected.base_argv,
                "wrapper-interchange": (
                    "env",
                    "CODEX_PATH=/tmp/validator",
                    "codex-acp",
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
            witness = RUNNER.FileWitness(root / "worker", 0o500, "hash", b"worker")
            expected_argv = (
                "/usr/bin/env",
                "CODEX_PATH=/tmp/worker",
                "/usr/bin/npx",
            )
            expected = RUNNER.ExpectedAgent(
                "codexp", expected_argv, expected_argv, witness
            )
            args = argparse.Namespace(
                worker_agent="codexp",
                validator_agent="codexp",
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
                        "agent_argv": ["codexp"],
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(worker_agent="codexp", validator_agent="codexp")

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
                        "agent_argv": ["codexp"],
                        "event_log": {"active_path": str(foreign_stream)},
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(worker_agent="codexp", validator_agent="codexp")

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
                "codexp",
                "codexp",
                ("codexp",),
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
            args = argparse.Namespace(worker_agent="codexp", validator_agent="codexp")

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
                        "agent_argv": ["codexp"],
                        "closed": True,
                        "event_log": {"active_path": str(events)},
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(worker_agent="codexp", validator_agent="codexp")
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
                        "agent_argv": ["codexp"],
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
                        "agent_argv": ["codexp"],
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
            witness = RUNNER.FileWitness(root / "launcher", 0o500, "hash", b"content")
            args = argparse.Namespace(
                worker_agent="codexp",
                validator_agent="codexp",
                expected_agents={
                    "worker": RUNNER.ExpectedAgent(
                        "codexp",
                        ("base-agent", "acp"),
                        ("expected-agent", "acp"),
                        witness,
                    )
                },
            )

            with self.assertRaisesRegex(RUNNER.HarnessError, "route mismatch"):
                RUNNER.basic_session(record, args)

    def test_route_validation_compares_command_text_with_persisted_argv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = root / "record.json"
            argv = ["codexp", "--safe"]
            record.write_text(
                json.dumps(
                    {
                        "acpx_record_id": "record-command",
                        "acp_session_id": "provider-command",
                        "cwd": str(root),
                        "name": "run-story-01-worker-command",
                        "agent_command": "codexp --different",
                        "agent_argv": argv,
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(worker_agent="codexp", validator_agent="codexp")

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
                        "agent_argv": ["codexp"],
                        "agentArgv": ["other"],
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(worker_agent="codexp", validator_agent="codexp")

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
            witness = RUNNER.FileWitness(root / "launcher", 0o500, "hash", b"content")
            expected = {
                "worker": RUNNER.ExpectedAgent(
                    "codex", ("base-codex-acp",), ("codex-acp",), witness
                ),
                "validator": RUNNER.ExpectedAgent(
                    "codex", ("base-codex-acp",), ("codex-acp",), witness
                ),
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
            preflight["accepted_registered_runner_tokens"],
            ["npx", "<shutil.which('npx') absolute path>"],
        )
        self.assertEqual(
            preflight["final_runner_token"],
            "<shutil.which('npx') absolute path>",
        )
        self.assertTrue(preflight["requires_persisted_nonempty_string_agent_argv"])
        self.assertEqual(
            preflight["allowed_alias_environment"], ["CODEX_HOME", "CODEX_PATH"]
        )
        self.assertTrue(preflight["alias_assignments_contiguous"])
        self.assertEqual(
            preflight["alias_assignment_order"], ["CODEX_HOME?", "CODEX_PATH"]
        )
        self.assertTrue(preflight["reject_trailing_env_assignments"])
        self.assertTrue(preflight["reject_trailing_adapter_arguments"])
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
