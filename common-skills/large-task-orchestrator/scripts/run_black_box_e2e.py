#!/usr/bin/env python3
"""黑盒验证 large-task-orchestrator 的真实 Kiro→ACPX→worker/validator 工作流。

脚本定义：复制固定单 Story 夹具到系统临时目录，用本地 bare remote 隔离交付，
并让一次性外部 orchestrator Agent 仅凭 Skill 与原始任务完成实现和独立验证。
参数定义：默认 orchestrator=kiro、worker=pi、validator 跟随 worker；只有 --live
会调用真实 Agent，--validate-fixture 只校验本地夹具，--dry-run 只展示输入和命令。
输出定义：stdout 返回人读摘要或 JSON；--output-dir 可归档事件和检查结果；成功时
默认删除临时仓库，失败时保留并打印路径。退出码 0=通过，1=行为/清理失败，2=参数或环境错误。
关键设计：继承调用者真实 HOME，不伪造 provider profile；只清理本轮新建且 cwd
等于临时仓库的 ACPX session，provider 自身的历史由 provider 保留。
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import quote


SCRIPT_PATH = Path(__file__).resolve()
SKILL_DIR = SCRIPT_PATH.parent.parent
FIXTURE_ROOT = SKILL_DIR / "tests" / "fixtures" / "black-box-e2e"
FIXTURE_REPOSITORY = FIXTURE_ROOT / "repository"
PROMPT_FILE = FIXTURE_ROOT / "prompt.txt"
PLANNING_SCRIPT = SKILL_DIR.parent / "large-task-planning" / "scripts" / "epic_story.py"
HISTORY_SCRIPT = SKILL_DIR / "scripts" / "orchestration_history.py"
RUN_HISTORY_RELATIVE = Path(".local/large-task-orchestrator/run-history.json")
EXPECTED_PROMPT = (
    "使用 $large-task-orchestrator 完成下面的用户任务：\n\n"
    "执行这个仓库现有大型任务计划中的下一项 Story，完成实现、独立验证和计划更新。\n"
)
EXPECTED_GREETING = b"hello from orchestrated worker\n"
AGENT_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
EFFORT_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
# 内置 pi 路由锁定 pi-acp 版本：harness 拥有精确 argv，persisted agent_argv 才能做
# 精确相等校验；acpx 升级其内置 range 时这里刻意同步 bump，而不是隐式跟随。
PI_ACP_ADAPTER_SPEC = "pi-acp@^0.0.31"
BUILTIN_AGENT_ARGVS = {"pi": ("npx", PI_ACP_ADAPTER_SPEC)}
PROJECT_CONFIG_MODE = 0o600
DEFAULT_COMMAND_TIMEOUT = 120.0
OUTER_COMMAND_GRACE_SECONDS = 60.0
REQUIRED_FIXTURE_PATHS = (
    "AGENTS.md",
    "README.md",
    "check.sh",
    "docs/plan/README.md",
    "docs/plan/epics/EPIC-FORWARD.md",
    "docs/plan/stories/Story-01-创建并验证问候文件.md",
    "docs/plan/agent/STORY-01-创建并验证问候文件.json",
    "docs/plan/agent/黄金验收.json",
    "docs/plan/agent/风险与阻塞.json",
    "docs/plan/agent/门禁.json",
)


class HarnessError(RuntimeError):
    """可复核的 E2E 行为或清理失败。"""


class HarnessEnvironmentError(HarnessError):
    """参数、依赖或本地环境不满足运行条件。"""


@dataclass(frozen=True)
class Workspace:
    root: Path
    repository: Path
    remote: Path
    evidence: Path
    initial_commit: str


@dataclass(frozen=True)
class FileWitness:
    path: Path
    mode: int
    sha256: str
    content: bytes


@dataclass(frozen=True)
class ExpectedAgent:
    logical_name: str
    argv: tuple[str, ...]


@dataclass(frozen=True)
class HarnessIntegrity:
    project_config: FileWitness


@dataclass(frozen=True)
class SessionEvidence:
    record_path: Path
    record_id: str
    provider_id: str
    name: str
    role: str
    agent: str
    agent_command: str
    agent_argv: tuple[str, ...]
    prompt_count: int
    new_after_prompt: int
    resume_count: int
    event_paths: tuple[Path, ...]


def usage() -> str:
    return f"""用法:
  python3 {SCRIPT_PATH.name} --dry-run [options]
  python3 {SCRIPT_PATH.name} --validate-fixture [options]
  python3 {SCRIPT_PATH.name} --live [options]

说明:
  用固定纯净提示词黑盒调用 $large-task-orchestrator。live 模式会使用真实 HOME、
  真实 ACPX Agent 和模型额度，但所有预期仓库写入与 push 都指向临时仓库和本地 bare remote。
  live 会给外层 orchestrator 使用 --approve-all；临时目录不是 OS 沙箱，只能在信任当前
  Agent/profile 且已授权这次测试时运行。

模式（必须且只能选择一个）:
  --dry-run              打印固定提示词、路由配置和将执行的 ACPX 命令，不创建临时仓库。
  --validate-fixture     创建临时仓库并运行计划 render/check 与失败基线，不调用 Agent。
  --live                 执行完整黑盒 E2E；这是唯一会调用真实 Agent 的模式。

选项:
  --orchestrator-agent <name>  外层 ACPX Agent，默认 kiro。
  --worker-agent <name>        ACPX worker Agent，默认 pi。非 pi 名称必须是
                               acpx config show 注册的 structured argv alias。
  --validator-agent <name>     validator Agent，规则同 worker；默认与 worker 相同。
  --worker-effort <value>      worker difficulty profile 的 effort，默认 high。
  --validator-effort <value>   validator difficulty profile 的 effort，默认 low。
  --timeout <seconds>          外层 Agent 总超时，默认 1800。
  --skill-registry <path>      宿主实际加载的 large-task-orchestrator 路径；默认按 Agent 推导。
  --acknowledge-broad-permissions
                               live 必填；确认 outer --approve-all 且没有 OS 沙箱。
  --output-dir <path>          归档 prompt、NDJSON、检查和 summary；默认不归档。
  --keep-temp                  成功后也保留临时仓库；失败总会保留以便诊断。
  --json                       stdout 只输出最终 JSON；进度写 stderr。
  -h, --help                   显示帮助。

输出:
  live 成功必须同时证明：固定 prompt 未被扩写、Story/Epic done、fixture 检查通过、
  本地提交已 push、worker/validator 为不同 session、provider ID 连续、session 没有
  prompt 后 new/resume、实际 persisted argv 精确匹配预先解析的 route argv，并且
  project config 的路径、模式和 SHA-256 在 outer 返回后未漂移。harness 不构造沙箱
  launcher；角色隔离只来自临时仓库和本地 bare remote。

退出码:
  0  所选模式通过。
  1  Agent、行为断言、计划门禁或精确清理失败。
  2  参数非法，或缺少 acpx/git/fixture/HOME 等运行环境。

示例:
  python3 {SCRIPT_PATH.name} --dry-run
  python3 {SCRIPT_PATH.name} --validate-fixture
  python3 {SCRIPT_PATH.name} --live --acknowledge-broad-permissions --worker-agent pi --validator-agent pi --timeout 1800
  python3 {SCRIPT_PATH.name} --live --acknowledge-broad-permissions --output-dir /tmp/lto-e2e-runs --keep-temp
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="黑盒验证 large-task-orchestrator 的真实多 Agent 工作流。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=usage(),
    )
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true", help="只展示输入和命令")
    modes.add_argument("--validate-fixture", action="store_true", help="只校验本地夹具")
    modes.add_argument("--live", action="store_true", help="调用真实 Agent 完整运行")
    parser.add_argument("--orchestrator-agent", default="kiro")
    parser.add_argument("--worker-agent", default="pi")
    parser.add_argument("--validator-agent")
    parser.add_argument("--worker-effort", default="high")
    parser.add_argument("--validator-effort", default="low")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--skill-registry", type=Path)
    parser.add_argument("--acknowledge-broad-permissions", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--keep-temp", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def log(message: str, *, json_mode: bool) -> None:
    print(f"INFO: {message}", file=sys.stderr if json_mode else sys.stdout)


def command_text(command: Sequence[str]) -> str:
    return shlex.join(str(part) for part in command)


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
    env: dict[str, str] | None = None,
    timeout: float = DEFAULT_COMMAND_TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            [str(part) for part in command],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise HarnessError(
            f"命令超时 timeout={timeout}s: {command_text(command)}"
        ) from error
    if check and result.returncode != 0:
        raise HarnessError(
            f"命令失败 exit={result.returncode}: {command_text(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def require_command(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None:
        raise HarnessEnvironmentError(f"找不到必需命令 `{name}`；请先安装并加入 PATH")
    return resolved


def validate_token(value: str, label: str, pattern: re.Pattern[str]) -> str:
    if not pattern.fullmatch(value):
        raise HarnessEnvironmentError(
            f"{label}={value!r} 非法；仅允许字母、数字、下划线和连字符"
        )
    return value


def validate_arguments(args: argparse.Namespace) -> None:
    if args.timeout <= 0:
        raise HarnessEnvironmentError("--timeout 必须是正整数")
    validate_token(args.orchestrator_agent, "--orchestrator-agent", AGENT_TOKEN)
    validate_token(args.worker_agent, "--worker-agent", AGENT_TOKEN)
    if args.validator_agent is None:
        args.validator_agent = args.worker_agent
    validate_token(args.validator_agent, "--validator-agent", AGENT_TOKEN)
    validate_token(args.worker_effort, "--worker-effort", EFFORT_TOKEN)
    validate_token(args.validator_effort, "--validator-effort", EFFORT_TOKEN)
    if args.live and not args.acknowledge_broad_permissions:
        raise HarnessEnvironmentError(
            "--live 必须同时传 --acknowledge-broad-permissions；"
            "outer Agent 使用 --approve-all 且临时目录不是 OS 沙箱"
        )


def validate_static_inputs() -> None:
    if not PLANNING_SCRIPT.is_file():
        raise HarnessEnvironmentError(f"找不到计划脚本: {PLANNING_SCRIPT}")
    if not HISTORY_SCRIPT.is_file():
        raise HarnessEnvironmentError(f"找不到运行历史脚本: {HISTORY_SCRIPT}")
    if not PROMPT_FILE.is_file():
        raise HarnessEnvironmentError(f"找不到固定提示词: {PROMPT_FILE}")
    prompt = PROMPT_FILE.read_text(encoding="utf-8")
    if prompt != EXPECTED_PROMPT:
        raise HarnessEnvironmentError(
            "固定提示词已漂移；它只能包含 Skill 选择和原始用户任务"
        )
    missing = [
        relative
        for relative in REQUIRED_FIXTURE_PATHS
        if not (FIXTURE_REPOSITORY / relative).is_file()
    ]
    if missing:
        raise HarnessEnvironmentError(f"夹具缺少文件: {', '.join(missing)}")


def inferred_skill_registry(orchestrator_agent: str) -> Path:
    if orchestrator_agent == "kiro":
        return Path.home() / ".kiro" / "skills" / "large-task-orchestrator"
    return Path.home() / ".agents" / "skills" / "large-task-orchestrator"


def validate_skill_binding(args: argparse.Namespace) -> Path:
    registry = args.skill_registry or inferred_skill_registry(args.orchestrator_agent)
    registry = registry.expanduser()
    if not registry.is_dir():
        raise HarnessEnvironmentError(
            f"宿主找不到待测 Skill registry: {registry}；"
            "请用 --skill-registry 指向宿主实际加载路径"
        )
    if registry.resolve() != SKILL_DIR.resolve():
        raise HarnessEnvironmentError(
            f"宿主 Skill 未绑定当前源码: {registry.resolve()} != {SKILL_DIR.resolve()}；"
            "请先用 symlink/宿主配置暴露当前 SKILL_DIR"
        )
    return registry.resolve()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validated_registered_argv(entry_argv: Any, logical_name: str) -> tuple[str, ...]:
    if (
        not isinstance(entry_argv, list)
        or not entry_argv
        or not all(isinstance(item, str) and item for item in entry_argv)
    ):
        raise HarnessEnvironmentError(
            f"ACPX agent {logical_name!r} 必须提供非空 structured argv；"
            "command 形态的 alias 无法做精确 argv 校验，live route fail closed"
        )
    for index, token in enumerate(entry_argv):
        if not token.isprintable():
            raise HarnessEnvironmentError(
                f"ACPX agent {logical_name!r} 的 argv[{index}] 含控制字符；"
                "拒绝换行、NUL 等不可打印字符"
            )
    return tuple(entry_argv)


def agent_argv_matches(expected: ExpectedAgent, actual: tuple[str, ...]) -> bool:
    return actual == expected.argv


def resolve_expected_agents(
    args: argparse.Namespace, workspace: Workspace, acpx: str
) -> dict[str, ExpectedAgent]:
    result = run_command(
        [
            acpx,
            "--cwd",
            str(workspace.repository),
            "--format",
            "json",
            "--json-strict",
            "config",
            "show",
        ],
        cwd=workspace.repository,
    )
    (workspace.evidence / "acpx-config.json").write_text(
        result.stdout, encoding="utf-8"
    )
    try:
        config = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise HarnessEnvironmentError(
            f"acpx config show 不是合法 JSON: {error}"
        ) from error
    configured = config.get("agents", {}) if isinstance(config, dict) else {}
    if not isinstance(configured, dict):
        raise HarnessEnvironmentError("acpx config show 的 agents 必须是对象")
    expected: dict[str, ExpectedAgent] = {}
    for role, logical_name in (
        ("worker", args.worker_agent),
        ("validator", args.validator_agent),
    ):
        entry = configured.get(logical_name)
        if entry is None and logical_name in BUILTIN_AGENT_ARGVS:
            # 内置 alias 不会出现在 acpx config show；使用 harness 锁定的适配器 argv。
            argv = BUILTIN_AGENT_ARGVS[logical_name]
        elif entry is not None:
            argv = validated_registered_argv(entry.get("argv"), logical_name)
        else:
            raise HarnessEnvironmentError(
                f"ACPX agent {logical_name!r} 既不是 harness 支持的内置路由，"
                "也不是 acpx config show 注册的 structured argv alias；"
                "live route fail closed"
            )
        expected[role] = ExpectedAgent(logical_name, argv)
    return expected
def profile(name: str, role: str, agent: str, effort: str) -> dict[str, Any]:
    return {
        "name": name,
        "match": {"role": role, "agent": agent},
        "effort_by_difficulty": {
            "routine": effort,
            "standard": effort,
            "complex": effort,
            "critical": effort,
        },
    }


def build_project_config(
    args: argparse.Namespace, expected_agents: dict[str, ExpectedAgent]
) -> dict[str, Any]:
    # 路由必须用位置式 agent 名：--agent 覆盖形式创建的 session 不持久化 agent_argv，
    # harness 的 persisted-argv 精确等值校验只有位置式注册/内置 alias 才能满足。
    return {
        "version": 1,
        "routing": {
            "worker": {
                "default": [{"agent": args.worker_agent}]
            },
            "validator": {
                "default": [{"agent": args.validator_agent}]
            },
        },
        "profiles": [
            profile("e2e-worker", "worker", args.worker_agent, args.worker_effort),
            profile(
                "e2e-validator",
                "validator",
                args.validator_agent,
                args.validator_effort,
            ),
        ],
    }


def planning_paths(repository: Path) -> dict[str, Path]:
    plan = repository / "docs" / "plan"
    return {
        "plan": plan,
        "epic": plan / "epics" / "EPIC-FORWARD.md",
        "stories": plan / "stories",
        "overview": plan / "README.md",
        "dashboard": plan / "项目进展.md",
        "card": plan / "agent" / "STORY-01-创建并验证问候文件.json",
    }


def planning_command(repository: Path, action: str, *extra: str) -> list[str]:
    paths = planning_paths(repository)
    command = [
        sys.executable,
        str(PLANNING_SCRIPT),
        action,
        "--epic",
        str(paths["epic"]),
        "--stories-dir",
        str(paths["stories"]),
    ]
    command.extend(extra)
    return command


def prepare_workspace(root: Path, args: argparse.Namespace) -> Workspace:
    repository = root / "repository"
    remote = root / "origin.git"
    evidence = root / "evidence"
    shutil.copytree(FIXTURE_REPOSITORY, repository)
    evidence.mkdir(parents=True)
    (repository / "check.sh").chmod(0o755)

    git = require_command("git")
    run_command([git, "init", "-b", "main"], cwd=repository)
    run_command([git, "config", "user.name", "LTO Black Box E2E"], cwd=repository)
    run_command(
        [git, "config", "user.email", "lto-black-box@example.invalid"],
        cwd=repository,
    )
    exclude = repository / ".git" / "info" / "exclude"
    with exclude.open("a", encoding="utf-8") as handle:
        handle.write(".local/\n")

    paths = planning_paths(repository)
    run_command(
        planning_command(repository, "render", "--dashboard", str(paths["dashboard"])),
        cwd=repository,
    )
    run_command(
        planning_command(
            repository,
            "check",
            "--overview",
            str(paths["overview"]),
            "--dashboard",
            str(paths["dashboard"]),
        ),
        cwd=repository,
    )
    baseline = run_command(["./check.sh"], cwd=repository, check=False)
    if baseline.returncode == 0:
        raise HarnessEnvironmentError("夹具失败基线意外通过；greeting.txt 不应预先存在")

    run_command(
        [git, "add", "AGENTS.md", "README.md", "check.sh", "docs"], cwd=repository
    )
    run_command(
        [git, "commit", "-m", "test: initialize black-box fixture"], cwd=repository
    )
    initial_commit = run_command(
        [git, "rev-parse", "HEAD"], cwd=repository
    ).stdout.strip()
    run_command([git, "init", "--bare", str(remote)], cwd=root)
    run_command([git, "remote", "add", "origin", str(remote)], cwd=repository)
    run_command([git, "push", "-u", "origin", "main"], cwd=repository)
    if run_command([git, "status", "--porcelain"], cwd=repository).stdout:
        raise HarnessEnvironmentError("夹具初始化后工作区不干净")
    return Workspace(root, repository, remote, evidence, initial_commit)


def install_project_config(
    workspace: Workspace,
    args: argparse.Namespace,
    expected_agents: dict[str, ExpectedAgent],
) -> HarnessIntegrity:
    config = build_project_config(args, expected_agents)
    content = (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path = (
        workspace.repository
        / ".local"
        / "large-task-orchestrator"
        / "orchestrator.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, PROJECT_CONFIG_MODE)
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise HarnessEnvironmentError(
            f"无法创建 project orchestrator config {path}: {error}"
        ) from error
    path.chmod(PROJECT_CONFIG_MODE)
    witness = FileWitness(path, PROJECT_CONFIG_MODE, sha256_bytes(content), content)
    route_evidence = {
        role: {
            "logical_name": expected.logical_name,
            "argv": list(expected.argv),
        }
        for role, expected in expected_agents.items()
    }
    route_evidence["project_config"] = {
        "path": str(path),
        "mode": f"{witness.mode:04o}",
        "sha256": witness.sha256,
    }
    (workspace.evidence / "safe-routes.json").write_text(
        json.dumps(route_evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return HarnessIntegrity(witness)


def verify_file_witness(witness: FileWitness, label: str) -> None:
    try:
        metadata = witness.path.lstat()
    except OSError as error:
        raise HarnessError(
            f"{label} 路径漂移或缺失: {witness.path}: {error}"
        ) from error
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise HarnessError(f"{label} 必须仍为普通非 symlink 文件: {witness.path}")
    actual_mode = stat.S_IMODE(metadata.st_mode)
    if actual_mode != witness.mode:
        raise HarnessError(
            f"{label} mode 漂移: expected={witness.mode:04o} actual={actual_mode:04o}"
        )
    try:
        content = witness.path.read_bytes()
    except OSError as error:
        raise HarnessError(f"{label} 内容无法复核: {witness.path}: {error}") from error
    actual_hash = sha256_bytes(content)
    if content != witness.content or actual_hash != witness.sha256:
        raise HarnessError(
            f"{label} content/hash 漂移: expected={witness.sha256} actual={actual_hash}"
        )


def verify_no_symlink_components(base: Path, path: Path, label: str) -> None:
    try:
        relative = path.relative_to(base)
    except ValueError as error:
        raise HarnessError(f"{label} 不在固定 base 下: {path}") from error
    current = base
    for component in relative.parts[:-1]:
        current = current / component
        try:
            metadata = current.lstat()
        except OSError as error:
            raise HarnessError(f"{label} 父路径缺失: {current}: {error}") from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise HarnessError(f"{label} 父路径发生 symlink/type 漂移: {current}")


def verify_harness_integrity(workspace: Workspace, integrity: HarnessIntegrity) -> None:
    expected_config_path = (
        workspace.repository
        / ".local"
        / "large-task-orchestrator"
        / "orchestrator.json"
    )
    if integrity.project_config.path != expected_config_path:
        raise HarnessError("project orchestrator config path 漂移")
    verify_no_symlink_components(
        workspace.repository,
        integrity.project_config.path,
        "project orchestrator config",
    )
    verify_file_witness(integrity.project_config, "project orchestrator config")


def sessions_directory() -> Path:
    """Return the host ACPX session directory without accepting a caller path."""
    return Path.home() / ".acpx" / "sessions"


def confined_path_under(
    base_raw: Path, path: Path, *, allow_missing: bool = False
) -> Path | None:
    """Resolve an artifact only when every path component stays under ``base``."""
    try:
        base_metadata = base_raw.lstat()
    except OSError:
        return None
    if stat.S_ISLNK(base_metadata.st_mode) or not stat.S_ISDIR(base_metadata.st_mode):
        return None
    base = base_raw.resolve()
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        resolved = candidate.resolve(strict=False)
        relative = resolved.relative_to(base)
    except (OSError, ValueError):
        return None
    if not relative.parts:
        return None

    current = base
    for component in relative.parts[:-1]:
        current = current / component
        try:
            metadata = current.lstat()
        except OSError:
            return None
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            return None

    try:
        metadata = resolved.lstat()
    except FileNotFoundError:
        return resolved if allow_missing else None
    except OSError:
        return None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        return None
    return resolved


def confined_session_path(path: Path, *, allow_missing: bool = False) -> Path | None:
    """Resolve a host ACPX artifact only when it stays in sessions/."""
    return confined_path_under(sessions_directory(), path, allow_missing=allow_missing)


def encoded_session_id(record_id: str) -> str:
    # Match JavaScript encodeURIComponent while keeping the result a single
    # filename component.  In particular, never leave '/' available to a glob.
    return quote(record_id, safe="-_.!~*'()")


def is_host_sessions_directory(path: Path) -> bool:
    try:
        return path.expanduser().resolve(strict=False) == sessions_directory().resolve(
            strict=False
        )
    except OSError:
        return False


def is_host_session_record(path: Path) -> bool:
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    try:
        return candidate.parent.resolve(strict=False) == sessions_directory().resolve(
            strict=False
        )
    except OSError:
        return False


def is_session_stream_name(record_id: str, name: str) -> bool:
    prefix = encoded_session_id(record_id)
    return re.fullmatch(
        rf"{re.escape(prefix)}\.stream(?:\.\d+)?\.ndjson", name
    ) is not None


def session_stream_paths(record_id: str, base: Path | None = None) -> set[Path]:
    """Enumerate only ACPX stream filenames for one exact encoded record ID."""
    stream_base = (base or sessions_directory()).expanduser()
    if not stream_base.is_dir() or stream_base.is_symlink():
        return set()
    paths: set[Path] = set()
    try:
        entries = tuple(stream_base.iterdir())
    except OSError:
        return set()
    for entry in entries:
        if not is_session_stream_name(record_id, entry.name):
            continue
        confined = confined_path_under(stream_base, entry)
        if confined is not None:
            paths.add(confined)
    return paths


def session_artifact_paths(record: SessionEvidence, session_dir: Path) -> set[Path]:
    """Build a fixed, confined set of record/stream files for cleanup."""
    paths: set[Path] = set()
    safe_record = confined_session_path(record.record_path)
    expected_record = f"{encoded_session_id(record.record_id)}.json"
    if safe_record is not None and (
        not is_host_session_record(record.record_path)
        or safe_record.name == expected_record
    ):
        paths.add(safe_record)
    paths.update(session_stream_paths(record.record_id))
    encoded = encoded_session_id(record.record_id)
    stream_lock = confined_session_path(session_dir / f"{encoded}.stream.lock")
    if stream_lock is not None:
        paths.add(stream_lock)
    for event_path in record.event_paths:
        safe_event = confined_session_path(event_path)
        if safe_event is not None and (
            not is_host_sessions_directory(session_dir)
            or is_session_stream_name(record.record_id, safe_event.name)
        ):
            paths.add(safe_event)
    return paths


def queue_artifact_paths(queue_dir: Path, queue_key: str) -> set[Path]:
    """Enumerate only fixed-key queue artifacts, including safe tombstones."""
    if not queue_dir.is_dir() or queue_dir.is_symlink():
        return set()
    pattern = re.compile(
        rf"^{re.escape(queue_key)}\.(?:lock|sock)(?:\.[A-Za-z0-9._-]+)*$"
    )
    paths: set[Path] = set()
    try:
        entries = tuple(queue_dir.iterdir())
    except OSError:
        return set()
    for entry in entries:
        if not pattern.fullmatch(entry.name):
            continue
        try:
            metadata = entry.lstat()
        except OSError:
            continue
        if stat.S_ISLNK(metadata.st_mode) or not (
            stat.S_ISREG(metadata.st_mode) or stat.S_ISSOCK(metadata.st_mode)
        ):
            continue
        # Keep the lexical directory entry. Resolving here adds another
        # filesystem lookup and widens a rename/symlink race window; cleanup
        # lstat/unlinks this exact entry instead.
        paths.add(entry)
    return paths


def queue_socket_base_directory() -> Path | None:
    if os.name == "nt":
        return None
    home_hash = hashlib.sha256(str(Path.home()).encode()).hexdigest()[:10]
    return Path("/tmp") / f"acpx-{home_hash}"


def queue_socket_artifact_paths(socket_dir: Path, queue_key: str) -> set[Path]:
    """Enumerate this session's generation-scoped Unix queue sockets."""
    if not socket_dir.is_dir() or socket_dir.is_symlink():
        return set()
    pattern = re.compile(rf"^{re.escape(queue_key)}(?:-[A-Za-z0-9]+)?\.sock$")
    paths: set[Path] = set()
    try:
        entries = tuple(socket_dir.iterdir())
    except OSError:
        return set()
    for entry in entries:
        if not pattern.fullmatch(entry.name):
            continue
        try:
            metadata = entry.lstat()
        except OSError:
            continue
        if stat.S_ISLNK(metadata.st_mode) or not (
            stat.S_ISREG(metadata.st_mode) or stat.S_ISSOCK(metadata.st_mode)
        ):
            continue
        paths.add(entry)
    return paths


def snapshot_session_records() -> set[Path]:
    sessions = sessions_directory()
    if not sessions.is_dir() or sessions.is_symlink():
        return set()
    records: set[Path] = set()
    try:
        entries = tuple(sessions.iterdir())
    except OSError:
        return set()
    for path in entries:
        if not path.name.endswith(".json"):
            continue
        confined = confined_session_path(path)
        if confined is not None:
            records.add(confined)
    return records


def first_string(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def load_record(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HarnessError(f"无法读取 ACPX session record {path}: {error}") from error
    if not isinstance(payload, dict):
        raise HarnessError(f"ACPX session record 不是对象: {path}")
    return payload


def record_identity(record: dict[str, Any]) -> tuple[str, str]:
    return (
        first_string(record, "acpx_record_id", "acpxRecordId"),
        first_string(record, "acp_session_id", "acpSessionId"),
    )


def record_event_paths(
    record: dict[str, Any], record_id: str, base: Path | None = None
) -> tuple[Path, ...]:
    """Return event files confined to the record's directory.

    ``base`` is the directory containing the record being inspected.  Live
    records come from the host ACPX sessions directory; using the record's
    parent here also keeps synthetic/unit-test records readable without
    weakening cleanup, which applies the stricter host-sessions boundary.
    """
    stream_base = base or sessions_directory()
    paths: set[Path] = set()
    event_log = record.get("event_log")
    if isinstance(event_log, dict):
        active = event_log.get("active_path")
        if isinstance(active, str) and active:
            confined = confined_path_under(stream_base, Path(active))
            if confined is not None:
                if is_host_sessions_directory(stream_base) and not is_session_stream_name(
                    record_id, confined.name
                ):
                    raise HarnessError(
                        f"session {record_id} event_log.active_path 不匹配其 stream 文件名: "
                        f"{confined}"
                    )
                paths.add(confined)
    paths.update(session_stream_paths(record_id, stream_base))
    return tuple(sorted(paths))


def collect_protocol_events(
    value: Any, output: list[tuple[str, dict[str, Any]]]
) -> None:
    if isinstance(value, dict):
        method = value.get("method")
        if isinstance(method, str):
            params = value.get("params")
            output.append((method, params if isinstance(params, dict) else {}))
        for child in value.values():
            collect_protocol_events(child, output)
    elif isinstance(value, list):
        for child in value:
            collect_protocol_events(child, output)


def read_protocol_events(
    paths: Sequence[Path], base: Path | None = None
) -> list[tuple[str, dict[str, Any]]]:
    stream_base = base or sessions_directory()
    events: list[tuple[str, dict[str, Any]]] = []
    for path in paths:
        confined = confined_path_under(stream_base, path)
        if confined is None:
            raise HarnessError(f"event stream 不在受信任的 session 目录: {path}")
        for line_number, line in enumerate(
            confined.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as error:
                raise HarnessError(
                    f"{confined}:{line_number} 不是合法 NDJSON: {error}"
                ) from error
            collect_protocol_events(payload, events)
    return events


def infer_role(name: str) -> str:
    lowered = name.lower()
    if "validator" in lowered:
        return "validator"
    if "worker" in lowered:
        return "worker"
    return "unknown"


def basic_session(
    path: Path, args: argparse.Namespace, *, validate_route: bool = True
) -> SessionEvidence:
    record = load_record(path)
    record_id, provider_id = record_identity(record)
    name = first_string(record, "name")
    cwd = first_string(record, "cwd")
    if not record_id or not provider_id or not name or not cwd:
        raise HarnessError(f"session record 缺少身份字段: {path}")
    if is_host_session_record(path):
        expected_name = f"{encoded_session_id(record_id)}.json"
        if path.name != expected_name:
            raise HarnessError(
                f"session record filename 与 acpx_record_id 不匹配: "
                f"expected={expected_name} actual={path.name}"
            )
    role = infer_role(name)
    if role == "unknown" and validate_route:
        raise HarnessError(f"无法从 session name 判定 worker/validator: {name}")
    expected_agents: dict[str, ExpectedAgent] = getattr(args, "expected_agents", {})
    expected = expected_agents.get(role)
    if expected is not None:
        agent = expected.logical_name
    elif role == "worker":
        agent = args.worker_agent
    elif role == "validator":
        agent = args.validator_agent
    else:
        agent = first_string(record, "agent") or "unknown"
    agent_command = first_string(record, "agent_command", "agentCommand")
    snake_argv = record.get("agent_argv")
    camel_argv = record.get("agentArgv")
    if "agent_argv" in record and "agentArgv" in record and snake_argv != camel_argv:
        raise HarnessError(f"session {name} 的 agent_argv/agentArgv 字段冲突")
    raw_argv = snake_argv if "agent_argv" in record else camel_argv
    valid_persisted_argv = (
        isinstance(raw_argv, list)
        and bool(raw_argv)
        and all(isinstance(item, str) and item for item in raw_argv)
    )
    if validate_route and not valid_persisted_argv:
        raise HarnessError(
            f"session {name} route validation 要求 persisted agent_argv/agentArgv "
            "为非空字符串数组"
        )
    if valid_persisted_argv:
        agent_argv = tuple(raw_argv)
    elif not validate_route and agent_command:
        agent_argv = tuple(shlex.split(agent_command))
    else:
        agent_argv = ()
    if (
        validate_route
        and expected is not None
        and not agent_argv_matches(expected, agent_argv)
    ):
        raise HarnessError(
            f"session {name} route mismatch: expected={expected.logical_name} "
            f"actual={list(agent_argv)}"
        )
    if validate_route and agent_command and valid_persisted_argv:
        try:
            command_argv = tuple(shlex.split(agent_command))
        except ValueError as error:
            raise HarnessError(
                f"session {name} 的 agent_command 不是可解析的 argv: {error}"
            ) from error
        if command_argv != agent_argv:
            raise HarnessError(
                f"session {name} 的 agent_command 与 persisted agent_argv 不一致"
            )
    return SessionEvidence(
        path,
        record_id,
        provider_id,
        name,
        role,
        agent,
        agent_command,
        agent_argv,
        0,
        0,
        0,
        record_event_paths(record, record_id, path.parent),
    )


def matching_test_record_paths(before: set[Path], workspace: Workspace) -> list[Path]:
    expected_cwd = str(workspace.repository.resolve())
    matching: list[Path] = []
    for path in sorted(snapshot_session_records() - before):
        record = load_record(path)
        cwd = first_string(record, "cwd")
        if cwd and str(Path(cwd).resolve()) == expected_cwd:
            matching.append(path)
    return matching


def inspect_session(path: Path, args: argparse.Namespace) -> SessionEvidence:
    session = basic_session(path, args)
    if not session.event_paths:
        raise HarnessError(f"session {session.name} 没有 event stream")
    events = read_protocol_events(session.event_paths, session.record_path.parent)
    prompt_indexes = [
        index for index, event in enumerate(events) if event[0] == "session/prompt"
    ]
    if not prompt_indexes:
        raise HarnessError(f"session {session.name} 没有 session/prompt 证据")
    for index in prompt_indexes:
        prompt_provider = first_string(events[index][1], "sessionId", "session_id")
        if prompt_provider != session.provider_id:
            raise HarnessError(
                f"session {session.name} prompt provider 漂移: "
                f"{prompt_provider} != {session.provider_id}"
            )
    first_prompt = min(prompt_indexes)
    new_after_prompt = sum(
        1
        for index, event in enumerate(events)
        if event[0] == "session/new" and index > first_prompt
    )
    resume_count = sum(1 for event in events if event[0] == "session/resume")
    if new_after_prompt or resume_count:
        raise HarnessError(
            f"session {session.name} continuity 失败: new_after_prompt={new_after_prompt}, "
            f"resume={resume_count}"
        )
    return replace(
        session,
        prompt_count=len(prompt_indexes),
        new_after_prompt=new_after_prompt,
        resume_count=resume_count,
    )


def discover_test_sessions(
    before: set[Path], workspace: Workspace, args: argparse.Namespace
) -> list[SessionEvidence]:
    evidence = [
        inspect_session(path, args)
        for path in matching_test_record_paths(before, workspace)
    ]
    workers = [item for item in evidence if item.role == "worker"]
    validators = [item for item in evidence if item.role == "validator"]
    if not workers or not validators:
        raise HarnessError(
            f"需要独立 worker 和 validator session；实际 worker={len(workers)}, "
            f"validator={len(validators)}"
        )
    if {item.provider_id for item in workers} & {
        item.provider_id for item in validators
    }:
        raise HarnessError("worker 与 validator 复用了 provider session")
    return evidence


def verify_run_history(
    workspace: Workspace,
    head: str,
    remote_head: str,
    sessions: Sequence[SessionEvidence],
) -> dict[str, Any]:
    repository = workspace.repository
    check = run_command(
        [sys.executable, str(HISTORY_SCRIPT), "--repository", str(repository), "check"],
        cwd=repository,
    )
    check_payload = json.loads(check.stdout)
    if check_payload.get("active_run") is not None:
        raise HarnessError("运行历史仍有 active run")
    show = run_command(
        [sys.executable, str(HISTORY_SCRIPT), "--repository", str(repository), "show"],
        cwd=repository,
    )
    show_payload = json.loads(show.stdout)
    delivered = [
        run for run in show_payload.get("runs", []) if run.get("outcome") == "delivered"
    ]
    if len(delivered) != 1:
        raise HarnessError(
            f"运行历史必须有且仅有一个 delivered run；实际={len(delivered)}"
        )
    run = delivered[0]
    metrics = run.get("metrics", {})
    if metrics.get("by_role", {}).get("worker", 0) < 1:
        raise HarnessError("运行历史缺少 worker attempt")
    if metrics.get("by_role", {}).get("validator", 0) < 1:
        raise HarnessError("运行历史缺少 validator attempt")
    if metrics.get("by_outcome", {}).get("worker-done", 0) < 1:
        raise HarnessError("运行历史缺少 worker-done outcome")
    if metrics.get("by_outcome", {}).get("continue", 0) < 1:
        raise HarnessError("运行历史缺少 validator continue outcome")
    delivery = run.get("delivery", {})
    if delivery.get("head") != head or delivery.get("remote_head") != remote_head:
        raise HarnessError("运行历史的 Git 交付证明与 fixture 实际 HEAD 不一致")

    detail = run_command(
        [
            sys.executable,
            str(HISTORY_SCRIPT),
            "--repository",
            str(repository),
            "show",
            "--run-id",
            str(run.get("run_id")),
        ],
        cwd=repository,
    )
    detail_payload = json.loads(detail.stdout)
    events = detail_payload.get("run", {}).get("recent_events", [])
    start_events = [event for event in events if event.get("event") == "attempt-start"]
    finish_events = [
        event for event in events if event.get("event") == "attempt-finish"
    ]
    actual_name_counts = Counter(session.name for session in sessions)
    if any(count != 1 for count in actual_name_counts.values()):
        raise HarnessError("实际 session name 不唯一，无法建立 history 关联")
    start_name_counts = Counter(event.get("attempt_id") for event in start_events)
    finish_name_counts = Counter(event.get("attempt_id") for event in finish_events)
    if (
        start_name_counts != actual_name_counts
        or finish_name_counts != actual_name_counts
    ):
        raise HarnessError("运行历史 attempt 多重集与实际 session 多重集不完全一致")
    expected_roles = {
        role: sum(session.role == role for session in sessions)
        for role in ("worker", "validator")
    }
    if (
        metrics.get("attempts") != len(sessions)
        or metrics.get("by_role") != expected_roles
    ):
        raise HarnessError("运行历史 attempt 汇总分母与实际 sessions 不一致")
    if sum(metrics.get("by_outcome", {}).values()) != len(sessions):
        raise HarnessError("运行历史 outcome 汇总分母与实际 sessions 不一致")
    for session in sessions:
        starts = [
            event for event in start_events if event.get("attempt_id") == session.name
        ]
        finishes = [
            event for event in finish_events if event.get("attempt_id") == session.name
        ]
        for event in (starts[0], finishes[0]):
            if event.get("role") != session.role or event.get("agent") != session.agent:
                raise HarnessError(f"运行历史 session role/agent 漂移: {session.name}")
            if event.get("session") != session.provider_id:
                raise HarnessError(f"运行历史 provider ID 漂移: {session.name}")

    shutil.copy2(
        repository / RUN_HISTORY_RELATIVE,
        workspace.evidence / "orchestration-history.json",
    )
    return {
        "run_id": run.get("run_id"),
        "outcome": run.get("outcome"),
        "attempts": metrics.get("attempts"),
        "attempt_ids": sorted(session.name for session in sessions),
        "by_role": metrics.get("by_role"),
        "by_outcome": metrics.get("by_outcome"),
        "delivery": delivery,
    }


def verify_fixture_path(
    path: Path, repository: Path, label: str, *, directory: bool = False
) -> None:
    """Require fixture inputs to be local, non-symlink paths before reading/running."""
    try:
        relative = path.relative_to(repository)
    except ValueError as error:
        raise HarnessError(f"{label} 不在 fixture repository 内: {path}") from error
    current = repository
    for component in relative.parts[:-1]:
        current = current / component
        try:
            metadata = current.lstat()
        except OSError as error:
            raise HarnessError(f"{label} 父路径缺失: {current}: {error}") from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise HarnessError(f"{label} 父路径发生 symlink/type 漂移: {current}")
    try:
        metadata = path.lstat()
    except OSError as error:
        raise HarnessError(f"{label} 缺失或无法检查: {path}: {error}") from error
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if stat.S_ISLNK(metadata.st_mode) or not expected(metadata.st_mode):
        kind = "目录" if directory else "普通非 symlink 文件"
        raise HarnessError(f"{label} 必须是本地{kind}: {path}")


def verify_delivery(workspace: Workspace) -> dict[str, Any]:
    repository = workspace.repository
    paths = planning_paths(repository)
    verify_fixture_path(repository / "greeting.txt", repository, "greeting.txt")
    verify_fixture_path(repository / "check.sh", repository, "check.sh")
    verify_fixture_path(paths["epic"], repository, "epic plan")
    verify_fixture_path(paths["stories"], repository, "stories directory", directory=True)
    verify_fixture_path(
        paths["stories"] / "Story-01-创建并验证问候文件.md",
        repository,
        "Story-01 plan",
    )
    verify_fixture_path(paths["overview"], repository, "plan overview")
    verify_fixture_path(paths["dashboard"], repository, "plan dashboard")
    verify_fixture_path(paths["card"], repository, "execution card")
    if (repository / "greeting.txt").read_bytes() != EXPECTED_GREETING:
        raise HarnessError("greeting.txt 内容或结尾换行不符合 fixture oracle")
    check = run_command(["./check.sh"], cwd=repository)
    if "greeting check passed" not in check.stdout:
        raise HarnessError("fixture check 未输出固定通过标记")
    run_command(
        planning_command(
            repository,
            "check",
            "--overview",
            str(paths["overview"]),
            "--dashboard",
            str(paths["dashboard"]),
        ),
        cwd=repository,
    )
    status = run_command(
        planning_command(repository, "status", "--json"), cwd=repository
    )
    status_payload = json.loads(status.stdout)
    stories = status_payload.get("stories", [])
    if status_payload.get("epic", {}).get("status") != "done":
        raise HarnessError("Epic 未变为 done")
    if len(stories) != 1 or stories[0].get("status") != "done":
        raise HarnessError("STORY-01 未变为 done")

    card = json.loads(paths["card"].read_text(encoding="utf-8"))
    if card.get("status") != "done" or not all(
        item.get("done") is True for item in card.get("checklist", [])
    ):
        raise HarnessError("执行卡状态或 checklist 未完成")
    card_evidence = f"{card.get('verification', '')}\n{card.get('handoff', '')}"
    if "CONTINUE" not in card_evidence:
        raise HarnessError("执行卡没有记录独立 validator 的 CONTINUE 结论")

    git = require_command("git")
    if run_command([git, "status", "--porcelain"], cwd=repository).stdout:
        raise HarnessError("Agent 完成后 fixture 工作区不干净")
    head = run_command([git, "rev-parse", "HEAD"], cwd=repository).stdout.strip()
    if head == workspace.initial_commit:
        raise HarnessError("Agent 没有创建交付 commit")
    remote_head = run_command(
        [git, f"--git-dir={workspace.remote}", "rev-parse", "refs/heads/main"],
        cwd=workspace.root,
    ).stdout.strip()
    if head != remote_head:
        raise HarnessError(f"本地 HEAD 未 push 到 origin/main: {head} != {remote_head}")
    changed = set(
        run_command(
            [
                git,
                "-c",
                "core.quotepath=false",
                "diff",
                "--name-only",
                f"{workspace.initial_commit}..{head}",
            ],
            cwd=repository,
        ).stdout.splitlines()
    )
    required = {
        "greeting.txt",
        "docs/plan/agent/STORY-01-创建并验证问候文件.json",
        "docs/plan/项目进展.md",
    }
    allowed = required | {
        path for path in changed if path.startswith("docs/plan/agent/evidence/")
    }
    if not required.issubset(changed) or changed - allowed:
        raise HarnessError(f"交付文件范围异常: {sorted(changed)}")
    subjects = run_command(
        [git, "log", "--format=%s", f"{workspace.initial_commit}..{head}"],
        cwd=repository,
    ).stdout.splitlines()
    if not any("STORY-01" in subject for subject in subjects):
        raise HarnessError("交付 commit message 未包含 STORY-01")
    return {
        "head": head,
        "remote_head": remote_head,
        "changed_files": sorted(changed),
        "check_stdout": check.stdout.strip(),
        "story_status": stories[0].get("status"),
        "epic_status": status_payload.get("epic", {}).get("status"),
    }


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_for_exit(pids: set[int], timeout: float = 8.0) -> set[int]:
    deadline = time.monotonic() + timeout
    remaining = {pid for pid in pids if pid > 0}
    while remaining and time.monotonic() < deadline:
        remaining = {pid for pid in remaining if process_alive(pid)}
        if remaining:
            time.sleep(0.1)
    return {pid for pid in remaining if process_alive(pid)}


def json_pid(path: Path) -> int | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    pid = payload.get("pid") if isinstance(payload, dict) else None
    return pid if isinstance(pid, int) and pid > 0 else None


def snapshot_session_evidence(
    sessions: Sequence[SessionEvidence], workspace: Workspace
) -> list[str]:
    errors: list[str] = []
    destination = workspace.evidence / "sessions"
    destination.mkdir(exist_ok=True)
    for session in sessions:
        target = destination / f"{session.role}-{quote(session.record_id, safe='')}"
        target.mkdir(exist_ok=True)
        try:
            safe_record = confined_session_path(session.record_path)
            if safe_record is not None:
                shutil.copy2(safe_record, target / "record.json")
            for index, path in enumerate(session.event_paths, 1):
                safe_event = confined_session_path(path)
                if safe_event is not None:
                    shutil.copy2(safe_event, target / f"event-{index}.ndjson")
            (target / "identity.json").write_text(
                json.dumps(
                    {
                        "name": session.name,
                        "role": session.role,
                        "expected_agent": session.agent,
                        "actual_command": session.agent_command,
                        "actual_argv": list(session.agent_argv),
                        "record_id": session.record_id,
                        "provider_id": session.provider_id,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        except OSError as error:
            errors.append(f"snapshot {session.name}: {error}")
    return errors


def cleanup_test_sessions(
    sessions: Sequence[SessionEvidence],
    workspace: Workspace,
    acpx: str,
    before: set[Path],
) -> list[str]:
    errors: list[str] = []
    session_dir = sessions_directory()
    queue_dir = Path.home() / ".acpx" / "queues"
    socket_dir = queue_socket_base_directory()
    for session in sessions:
        session_errors: list[str] = []
        safe_record_path = confined_session_path(session.record_path)
        try:
            record = (
                load_record(safe_record_path)
                if safe_record_path is not None
                else {}
            )
        except HarnessError as error:
            record = {}
            session_errors.append(str(error))
        if safe_record_path is None:
            session_errors.append(
                f"record path 不在受信任的 ACPX sessions 目录: {session.record_path}"
            )
        pids: set[int] = set()
        record_pid = record.get("pid")
        if isinstance(record_pid, int) and record_pid > 0:
            pids.add(record_pid)
        queue_key = hashlib.sha256(session.record_id.encode()).hexdigest()[:24]
        lock = queue_dir / f"{queue_key}.lock"
        owner_pid = json_pid(lock)
        if owner_pid is not None:
            pids.add(owner_pid)
        if record.get("closed") is not True:
            selector = (
                ["--agent", session.agent_command]
                if session.agent_command
                else [session.agent]
            )
            try:
                close = run_command(
                    [
                        acpx,
                        "--cwd",
                        str(workspace.repository),
                        "--format",
                        "json",
                        "--json-strict",
                        "--timeout",
                        "120",
                        *selector,
                        "sessions",
                        "close",
                        session.name,
                    ],
                    cwd=workspace.repository,
                    check=False,
                    timeout=150.0,
                )
                if close.returncode != 0:
                    session_errors.append(
                        f"close exit={close.returncode}: "
                        f"{close.stderr.strip() or close.stdout.strip()}"
                    )
            except (OSError, HarnessError) as error:
                session_errors.append(f"close: {error}")
        remaining = wait_for_exit(pids)
        if remaining:
            session_errors.append(f"进程未退出: {sorted(remaining)}")
        if not session_errors:
            paths = session_artifact_paths(session, session_dir)
            paths.update(queue_artifact_paths(queue_dir, queue_key))
            if socket_dir is not None:
                paths.update(queue_socket_artifact_paths(socket_dir, queue_key))
            for path in paths:
                try:
                    metadata = path.lstat()
                    if stat.S_ISREG(metadata.st_mode) or stat.S_ISSOCK(metadata.st_mode):
                        path.unlink(missing_ok=True)
                    elif stat.S_ISLNK(metadata.st_mode):
                        session_errors.append(f"拒绝删除 symlink artifact: {path}")
                except OSError as error:
                    session_errors.append(f"unlink {path}: {error}")
        if session_errors:
            errors.append(f"session {session.name}: " + "; ".join(session_errors))
    missing_preexisting = sorted(str(path) for path in before if not path.exists())
    if missing_preexisting:
        errors.append(
            "pre-run session records disappeared: " + ", ".join(missing_preexisting)
        )
    try:
        remaining_records = matching_test_record_paths(before, workspace)
    except Exception as error:
        errors.append(f"verify cleanup records: {error}")
    else:
        if remaining_records:
            errors.append(
                "test session records remain: "
                + ", ".join(str(path) for path in remaining_records)
            )
    return errors


def archive_evidence(
    workspace: Workspace, output_dir: Path, summary: dict[str, Any]
) -> Path:
    run_id = summary["run_id"]
    destination = output_dir.expanduser().resolve() / run_id
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise HarnessError(f"归档目录已存在: {destination}")
    destination.mkdir(mode=0o700)
    shutil.copytree(workspace.evidence, destination, dirs_exist_ok=True)
    (destination / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for path in sorted(destination.rglob("*"), key=lambda item: len(item.parts)):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise HarnessError(f"归档中拒绝 symlink: {path}")
        if stat.S_ISDIR(metadata.st_mode):
            path.chmod(0o700)
        elif stat.S_ISREG(metadata.st_mode):
            path.chmod(0o600)
        else:
            raise HarnessError(f"归档包含不支持的文件类型: {path}")
    destination.chmod(0o700)
    return destination


def build_outer_command(
    args: argparse.Namespace, repository: Path, prompt_path: Path, acpx: str
) -> list[str]:
    return [
        acpx,
        "--cwd",
        str(repository),
        "--format",
        "json",
        "--json-strict",
        "--timeout",
        str(args.timeout),
        "--ttl",
        "120",
        "--approve-all",
        "--non-interactive-permissions",
        "fail",
        args.orchestrator_agent,
        "exec",
        "--file",
        str(prompt_path),
    ]


def verify_outer_prompt(ndjson: str) -> None:
    prompts: list[list[Any]] = []
    for line_number, line in enumerate(ndjson.splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise HarnessError(
                f"outer NDJSON 第 {line_number} 行非法: {error}"
            ) from error
        if event.get("method") != "session/prompt":
            continue
        params = event.get("params")
        prompt = params.get("prompt") if isinstance(params, dict) else None
        if not isinstance(prompt, list):
            prompts.append([])
        else:
            prompts.append(prompt)
    if len(prompts) != 1:
        raise HarnessError(
            f"outer ACPX 必须恰好发送一次 session/prompt；实际={len(prompts)}"
        )
    prompt = prompts[0]
    if len(prompt) != 1 or not isinstance(prompt[0], dict):
        raise HarnessError("outer session/prompt 只允许一个纯 text 内容块")
    item = prompt[0]
    if set(item) != {"type", "text"} or item.get("type") != "text":
        raise HarnessError("outer session/prompt 只允许一个纯 text 内容块")
    actual = item.get("text")
    if not isinstance(actual, str):
        raise HarnessError("outer session/prompt 的 text 必须是字符串")
    if actual.rstrip("\n") != EXPECTED_PROMPT.rstrip("\n"):
        raise HarnessError("实际下发给 orchestrator 的 prompt 与固定纯净 prompt 不一致")


def dry_run(args: argparse.Namespace) -> dict[str, Any]:
    validate_static_inputs()
    command = build_outer_command(
        args, Path("<temp-repository>"), Path("<prompt.sent.txt>"), "acpx"
    )
    return {
        "mode": "dry-run",
        "prompt": EXPECTED_PROMPT,
        "route_preflight": {
            "uses_bounded_acp_session_handshake": True,
            "rejects_raw_adapter_help_preflight": True,
            "builtin_routes": {"pi": list(BUILTIN_AGENT_ARGVS["pi"])},
            "accepts_registered_structured_argv_aliases": True,
            "rejects_command_form_and_unknown_builtin": True,
            "reject_control_characters": True,
            "requires_persisted_nonempty_string_agent_argv": True,
            "requires_persisted_argv_equal_expected_argv": True,
            "constructs_no_sandbox_launcher": True,
            "project_config": "<repository>/.local/large-task-orchestrator/orchestrator.json",
        },
        "command": command,
        "inherits_home": True,
        "calls_real_agents": False,
    }


def validate_fixture_mode(args: argparse.Namespace) -> dict[str, Any]:
    validate_static_inputs()
    require_command("git")
    root = Path(tempfile.mkdtemp(prefix="large-task-orchestrator-fixture-"))
    try:
        workspace = prepare_workspace(root, args)
        return {
            "mode": "validate-fixture",
            "initial_commit": workspace.initial_commit,
            "fixture_check_fails_before_story": True,
            "plan_check": "passed",
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def live_run(args: argparse.Namespace) -> dict[str, Any]:
    validate_static_inputs()
    acpx = require_command("acpx")
    require_command("git")
    if not os.environ.get("HOME"):
        raise HarnessEnvironmentError("live 模式必须继承真实 HOME")
    skill_registry = validate_skill_binding(args)
    root = Path(tempfile.mkdtemp(prefix="large-task-orchestrator-e2e-"))
    workspace: Workspace | None = None
    sessions: list[SessionEvidence] = []
    before: set[Path] = set()
    failure: Exception | None = None
    cleanup_errors: list[str] = []
    summary: dict[str, Any] = {
        "mode": "live",
        "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "orchestrator_agent": args.orchestrator_agent,
        "worker_agent": args.worker_agent,
        "validator_agent": args.validator_agent,
        "home": str(Path.home()),
        "skill_registry": str(skill_registry),
        "workspace": str(root),
        "prompt_sha256": hashlib.sha256(EXPECTED_PROMPT.encode()).hexdigest(),
    }
    try:
        workspace = prepare_workspace(root, args)
        args.expected_agents = resolve_expected_agents(args, workspace, acpx)
        integrity = install_project_config(workspace, args, args.expected_agents)
        summary["expected_agents"] = {
            role: {
                "logical_name": expected.logical_name,
                "argv": list(expected.argv),
            }
            for role, expected in args.expected_agents.items()
        }
        summary["project_config"] = {
            "path": str(integrity.project_config.path),
            "mode": f"{integrity.project_config.mode:04o}",
            "sha256": integrity.project_config.sha256,
        }
        prompt_path = workspace.evidence / "prompt.sent.txt"
        prompt_path.write_text(EXPECTED_PROMPT, encoding="utf-8")
        before = snapshot_session_records()
        command = build_outer_command(args, workspace.repository, prompt_path, acpx)
        summary["command"] = command
        (workspace.evidence / "command.txt").write_text(
            command_text(command) + "\n", encoding="utf-8"
        )
        result = run_command(
            command,
            cwd=workspace.repository,
            check=False,
            env=os.environ.copy(),
            timeout=float(args.timeout) + OUTER_COMMAND_GRACE_SECONDS,
        )
        (workspace.evidence / "orchestrator.ndjson").write_text(
            result.stdout, encoding="utf-8"
        )
        (workspace.evidence / "orchestrator.stderr").write_text(
            result.stderr, encoding="utf-8"
        )
        summary["orchestrator_exit"] = result.returncode
        verify_harness_integrity(workspace, integrity)
        summary["harness_integrity_rechecked"] = True
        if result.returncode != 0:
            raise HarnessError(
                f"orchestrator ACPX exit={result.returncode}; "
                f"stderr={result.stderr.strip()!r}"
            )
        verify_outer_prompt(result.stdout)
        summary["prompt_exact"] = True
        delivery = verify_delivery(workspace)
        sessions = discover_test_sessions(before, workspace, args)
        delivery["run_history"] = verify_run_history(
            workspace,
            str(delivery["head"]),
            str(delivery["remote_head"]),
            sessions,
        )
        summary["delivery"] = delivery
        summary["sessions"] = [
            {
                "name": item.name,
                "role": item.role,
                "agent": item.agent,
                "actual_command": item.agent_command,
                "actual_argv": list(item.agent_argv),
                "record_id": item.record_id,
                "provider_id": item.provider_id,
                "prompt_count": item.prompt_count,
                "new_after_prompt": item.new_after_prompt,
                "resume_count": item.resume_count,
            }
            for item in sessions
        ]
        summary["result"] = "passed"
    except (
        Exception
    ) as error:  # cleanup and evidence preservation are shared by every failure
        failure = error
        summary["result"] = "failed"
        summary["error"] = str(error)
    finally:
        if workspace is not None:
            cleanup_sessions = list(sessions)
            known_ids = {session.record_id for session in cleanup_sessions}
            try:
                for path in matching_test_record_paths(before, workspace):
                    session = basic_session(path, args, validate_route=False)
                    if session.record_id not in known_ids:
                        cleanup_sessions.append(session)
                        known_ids.add(session.record_id)
            except Exception as error:
                cleanup_errors.append(f"discover during cleanup: {error}")
            try:
                cleanup_errors.extend(
                    snapshot_session_evidence(cleanup_sessions, workspace)
                )
            except Exception as error:
                cleanup_errors.append(f"snapshot sessions: {error}")
            try:
                cleanup_errors.extend(
                    cleanup_test_sessions(cleanup_sessions, workspace, acpx, before)
                )
            except Exception as error:
                cleanup_errors.append(f"cleanup sessions: {error}")
        if cleanup_errors:
            cleanup_failure = HarnessError("清理失败: " + "; ".join(cleanup_errors))
            if failure is None:
                failure = cleanup_failure
            else:
                summary["cleanup_failure"] = str(cleanup_failure)
        summary["cleanup_errors"] = cleanup_errors
        if failure is not None:
            summary["result"] = "failed"
            summary["error"] = str(failure)
        preserve = args.keep_temp or failure is not None
        summary["workspace"] = str(root) if preserve else None
        if args.output_dir is not None and workspace is not None:
            destination = args.output_dir.expanduser().resolve() / summary["run_id"]
            summary["archive"] = str(destination)
            try:
                archive_evidence(workspace, args.output_dir, summary)
            except Exception as error:
                failure = failure or HarnessError(f"归档失败: {error}")
                summary["result"] = "failed"
                summary["error"] = str(failure)
                summary["workspace"] = str(root)
                summary.pop("archive", None)
                preserve = True
        if not preserve:
            shutil.rmtree(root, ignore_errors=True)
    if failure is not None:
        location = summary.get("workspace")
        suffix = f"；诊断目录={location}" if location else ""
        raise HarnessError(f"{failure}{suffix}") from failure
    return summary


def emit_result(result: dict[str, Any], *, json_mode: bool) -> None:
    if json_mode:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print("RESULT:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        validate_arguments(args)
        if args.dry_run:
            result = dry_run(args)
        elif args.validate_fixture:
            result = validate_fixture_mode(args)
        else:
            log(
                "live 使用真实 HOME 和 --approve-all；临时仓库/local remote 不是 OS 沙箱，"
                "已收到 --acknowledge-broad-permissions",
                json_mode=args.json,
            )
            result = live_run(args)
        emit_result(result, json_mode=args.json)
        return 0
    except HarnessEnvironmentError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    except HarnessError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
