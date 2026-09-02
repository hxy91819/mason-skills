#!/usr/bin/env python3
"""解析 large-task-orchestrator 的 user/project 两层配置。

脚本定义：这是编排器读取配置的唯一入口。它固定读取 user 配置与 repository-local
project override，严格验证 version 1 schema 后确定性合并；它不探测 Agent，也不创建会话。
参数定义：必须传 --repository，且该路径必须是编排目标仓库根目录。
输出定义：成功时 stdout 输出 JSON，包含两层的固定 path/status 与 merged config；project
文件不存在时 status=absent。错误写 stderr，退出码 1；参数错误退出码 2。任何已存在但
不可读、JSON 损坏或 schema 非法的文件都会 fail closed，且错误点名文件路径。
关键设计：project route 按 routing.<role>.<name> 整键替换；profiles 按 name 合并，project
profile 优先并排在 user profile 前，以保持同等 specificity 时的 project 优先级。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, NoReturn, Sequence


SCRIPT_PATH = Path(__file__).resolve()
CONFIG_RELATIVE = Path("mason-skills/large-task-orchestrator/orchestrator.json")
PROJECT_RELATIVE = Path(".local/large-task-orchestrator/orchestrator.json")
SCHEMA_VERSION = 1
ROUTES = {"worker": {"default", "frontend"}, "validator": {"default"}}
REQUIRED_ROUTES = (("worker", "default"), ("validator", "default"))
CANDIDATE_FIELDS = {
    "agent",
    "acpx_command",
    "native_args",
    "model_contains",
    "model_preference",
    "max_difficulty",
    "reason",
}
PROFILE_FIELDS = {"name", "match", "effort_by_difficulty"}
MATCH_FIELDS = {"agent", "role", "model_contains"}
DIFFICULTIES = {"routine", "standard", "complex", "critical"}
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")


class ConfigError(RuntimeError):
    """配置路径、JSON 或 schema 不满足 fail-closed 契约。"""


class DuplicateKeyError(ValueError):
    """JSON object 包含重复 key。"""


def usage() -> str:
    return f"""用法:
  python3 {SCRIPT_PATH.name} --repository <repo>

说明:
  固定读取并合并：
  1. ${{XDG_CONFIG_HOME:-$HOME/.config}}/{CONFIG_RELATIVE.as_posix()}
  2. <repo>/{PROJECT_RELATIVE.as_posix()}
  user 配置必须存在；project 配置可不存在。存在的文件必须完整通过 version 1 schema
  校验。脚本不接受配置路径 override，避免不同宿主读取不同来源。

参数:
  --repository <repo>  编排目标仓库根目录（必填）。
  -h, --help           显示帮助。

输出:
  成功时 stdout 输出 UTF-8 JSON：ok=true、repository、sources.user、
  sources.project 和合并后的 config。每个 source 都报告固定 path 与 loaded/absent status；
  user 成功时只能是 loaded。错误写 stderr 并点名失败路径，不输出可供 dispatch 使用的配置。
  退出码：0=成功，1=配置/文件错误，2=参数错误。

示例:
  python3 {SCRIPT_PATH.name} --repository .
  XDG_CONFIG_HOME="$HOME/.config" python3 {SCRIPT_PATH.name} \\
    --repository /path/to/repository
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="确定性解析 large-task-orchestrator 的两层配置。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=usage(),
    )
    parser.add_argument(
        "--repository",
        required=True,
        type=Path,
        help="编排目标仓库根目录",
    )
    return parser


def _error(path: Path, field: str, message: str) -> NoReturn:
    raise ConfigError(f"{path}: {field}: {message}")


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate key {key!r}")
        result[key] = value
    return result


def _parse_json(path: Path, text: str) -> dict[str, Any]:
    try:
        value = json.loads(text, object_pairs_hook=_object_without_duplicates)
    except (json.JSONDecodeError, DuplicateKeyError) as error:
        raise ConfigError(f"{path}: malformed JSON: {error}") from error
    if not isinstance(value, dict):
        _error(path, "$", "must be an object")
    return value


def _read_open_file(fd: int, path: Path) -> dict[str, Any]:
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise ConfigError(f"{path}: configuration path is not a regular file")
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            fd = -1
            text = stream.read()
    except (OSError, UnicodeError) as error:
        raise ConfigError(f"{path}: cannot read UTF-8 configuration: {error}") from error
    finally:
        if fd >= 0:
            os.close(fd)
    return _parse_json(path, text)


def _read_json(path: Path, *, required: bool) -> dict[str, Any] | None:
    # Non-blocking open makes a repository-controlled FIFO fail closed instead
    # of hanging before fstat can reject the non-regular file.
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        fd = os.open(path, flags)
    except FileNotFoundError as error:
        if required:
            raise ConfigError(f"{path}: required user configuration is absent") from error
        return None
    except OSError as error:
        raise ConfigError(f"{path}: cannot open configuration: {error}") from error
    return _read_open_file(fd, path)


def _read_project_json(repository: Path, path: Path) -> dict[str, Any] | None:
    """Read the fixed repository-local source without following path symlinks."""
    if os.open not in os.supports_dir_fd or not hasattr(os, "O_DIRECTORY"):
        current = repository
        for component in PROJECT_RELATIVE.parts:
            current = current / component
            try:
                metadata = current.lstat()
            except FileNotFoundError:
                return None
            except OSError as error:
                raise ConfigError(
                    f"{path}: cannot inspect project configuration path: {error}"
                ) from error
            if stat.S_ISLNK(metadata.st_mode):
                raise ConfigError(
                    f"{path}: project configuration path must not contain symlinks"
                )
        return _read_json(path, required=False)

    directory_flags = (
        os.O_RDONLY
        | os.O_DIRECTORY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    file_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    directory_fds: list[int] = []
    try:
        directory_fds.append(os.open(repository, directory_flags))
        for component in PROJECT_RELATIVE.parts[:-1]:
            try:
                child_fd = os.open(
                    component,
                    directory_flags,
                    dir_fd=directory_fds[-1],
                )
            except FileNotFoundError:
                return None
            except OSError as error:
                raise ConfigError(
                    f"{path}: cannot open project configuration directory "
                    f"{component!r} without following symlinks: {error}"
                ) from error
            directory_fds.append(child_fd)
        try:
            config_fd = os.open(
                PROJECT_RELATIVE.name,
                file_flags,
                dir_fd=directory_fds[-1],
            )
        except FileNotFoundError:
            return None
        except OSError as error:
            raise ConfigError(
                f"{path}: cannot open project configuration without following "
                f"symlinks: {error}"
            ) from error
        return _read_open_file(config_fd, path)
    except OSError as error:
        raise ConfigError(
            f"{path}: cannot open repository for project configuration: {error}"
        ) from error
    finally:
        for directory_fd in reversed(directory_fds):
            os.close(directory_fd)


def _exact_fields(
    value: dict[str, Any],
    expected: set[str],
    path: Path,
    field: str,
    *,
    required: set[str] | None = None,
) -> None:
    required_fields = expected if required is None else required
    missing = sorted(required_fields - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        _error(path, field, f"missing fields {missing}")
    if unknown:
        _error(path, field, f"unknown fields {unknown}")


def _string(
    value: Any,
    path: Path,
    field: str,
    *,
    token: bool = False,
) -> str:
    if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
        _error(path, field, "must be a non-empty single-line string")
    if token and not TOKEN_RE.fullmatch(value):
        _error(path, field, f"contains invalid token {value!r}")
    return value


def _validate_candidate(value: Any, path: Path, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _error(path, field, "must be an object")
    _exact_fields(value, CANDIDATE_FIELDS, path, field, required={"agent"})
    _string(value["agent"], path, f"{field}.agent", token=True)
    for name in ("acpx_command", "model_contains", "model_preference", "reason"):
        if name in value:
            _string(value[name], path, f"{field}.{name}")
    if "native_args" in value:
        native_args = value["native_args"]
        if not isinstance(native_args, list):
            _error(path, f"{field}.native_args", "must be an array")
        for index, argument in enumerate(native_args):
            _string(argument, path, f"{field}.native_args[{index}]")
    if "max_difficulty" in value:
        ceiling_field = f"{field}.max_difficulty"
        ceiling = _string(value["max_difficulty"], path, ceiling_field)
        if ceiling not in DIFFICULTIES:
            _error(path, ceiling_field, f"must be one of {sorted(DIFFICULTIES)}")
    return value


def _validate_routing(value: Any, path: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        _error(path, "routing", "must be an object")
    unknown_roles = sorted(set(value) - set(ROUTES))
    if unknown_roles:
        _error(path, "routing", f"unknown roles {unknown_roles}")
    for role, routes in value.items():
        field = f"routing.{role}"
        if not isinstance(routes, dict):
            _error(path, field, "must be an object")
        unknown_routes = sorted(set(routes) - ROUTES[role])
        if unknown_routes:
            _error(path, field, f"unknown routes {unknown_routes}")
        for route, candidates in routes.items():
            route_field = f"{field}.{route}"
            if not isinstance(candidates, list) or not candidates:
                _error(path, route_field, "must be a non-empty candidate array")
            for index, candidate in enumerate(candidates):
                _validate_candidate(candidate, path, f"{route_field}[{index}]")
    return value


def _validate_profile(value: Any, path: Path, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _error(path, field, "must be an object")
    _exact_fields(value, PROFILE_FIELDS, path, field, required={"name", "match"})
    _string(value["name"], path, f"{field}.name", token=True)

    match = value["match"]
    if not isinstance(match, dict):
        _error(path, f"{field}.match", "must be an object")
    _exact_fields(match, MATCH_FIELDS, path, f"{field}.match", required={"agent"})
    _string(match["agent"], path, f"{field}.match.agent", token=True)
    if "role" in match:
        role = match["role"]
        if not isinstance(role, str) or role not in ROUTES:
            _error(path, f"{field}.match.role", "must be worker or validator")
    if "model_contains" in match:
        _string(match["model_contains"], path, f"{field}.match.model_contains")

    if "effort_by_difficulty" in value:
        efforts = value["effort_by_difficulty"]
        if not isinstance(efforts, dict):
            _error(path, f"{field}.effort_by_difficulty", "must be an object")
        unknown = sorted(set(efforts) - DIFFICULTIES)
        if unknown:
            _error(
                path,
                f"{field}.effort_by_difficulty",
                f"unknown difficulties {unknown}",
            )
        for difficulty, effort in efforts.items():
            _string(
                effort,
                path,
                f"{field}.effort_by_difficulty.{difficulty}",
                token=True,
            )
    return value


def validate_config(value: dict[str, Any], path: Path) -> dict[str, Any]:
    _exact_fields(value, {"version", "routing", "profiles"}, path, "$")
    if type(value["version"]) is not int or value["version"] != SCHEMA_VERSION:
        _error(
            path,
            "version",
            f"must equal integer {SCHEMA_VERSION}; got {value['version']!r}",
        )
    _validate_routing(value["routing"], path)
    profiles = value["profiles"]
    if not isinstance(profiles, list):
        _error(path, "profiles", "must be an array")
    names: set[str] = set()
    for index, profile in enumerate(profiles):
        validated = _validate_profile(profile, path, f"profiles[{index}]")
        name = validated["name"]
        if name in names:
            _error(path, f"profiles[{index}].name", f"duplicate profile name {name!r}")
        names.add(name)
    return value


def _merge_configs(
    user: dict[str, Any],
    project: dict[str, Any] | None,
    *,
    user_path: Path,
    project_path: Path,
) -> dict[str, Any]:
    routing = deepcopy(user["routing"])
    project_profiles: list[dict[str, Any]] = []
    if project is not None:
        for role, routes in project["routing"].items():
            target = routing.setdefault(role, {})
            for route, candidates in routes.items():
                target[route] = deepcopy(candidates)
        project_profiles = deepcopy(project["profiles"])

    for role, route in REQUIRED_ROUTES:
        if role not in routing or route not in routing[role]:
            raise ConfigError(
                f"{user_path} + {project_path}: merged routing.{role}.{route}: "
                "required route is absent"
            )

    project_names = {profile["name"] for profile in project_profiles}
    profiles = project_profiles + [
        deepcopy(profile)
        for profile in user["profiles"]
        if profile["name"] not in project_names
    ]
    return {"version": SCHEMA_VERSION, "routing": routing, "profiles": profiles}


def _repository(path: Path) -> Path:
    repository = path.expanduser().resolve()
    if not repository.is_dir():
        raise ConfigError(f"{repository}: --repository must be an existing directory")
    return repository


def _user_config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        base = Path(xdg).expanduser()
        if not base.is_absolute():
            raise ConfigError(
                f"{base}: XDG_CONFIG_HOME must be absolute to resolve user configuration"
            )
    else:
        base = Path.home() / ".config"
    return base / CONFIG_RELATIVE


def resolve(repository_arg: Path) -> dict[str, Any]:
    repository = _repository(repository_arg)
    user_path = _user_config_path()
    project_path = repository / PROJECT_RELATIVE
    user = _read_json(user_path, required=True)
    assert user is not None
    validate_config(user, user_path)
    project = _read_project_json(repository, project_path)
    if project is not None:
        validate_config(project, project_path)
    merged = _merge_configs(
        user,
        project,
        user_path=user_path,
        project_path=project_path,
    )
    return {
        "ok": True,
        "repository": str(repository),
        "sources": {
            "user": {"path": str(user_path), "status": "loaded"},
            "project": {
                "path": str(project_path),
                "status": "loaded" if project is not None else "absent",
            },
        },
        "config": merged,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = resolve(args.repository)
    except ConfigError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
