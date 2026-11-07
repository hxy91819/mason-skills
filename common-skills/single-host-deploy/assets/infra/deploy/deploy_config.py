#!/usr/bin/env python3
"""部署配置辅助：读取 Ansible 清单、生成/校验密钥、渲染 0600 运行环境文件。

只使用标准库；清单由 `ansible-inventory --list` 输出为 JSON，避免在本机再引入
一份 YAML 解析依赖。所有密钥值只写入本机未跟踪文件，不打印到终端。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets as token_module
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

KEY_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
KEY_LINE = re.compile(r'^(\s*(?:export\s+)?)([A-Za-z_][A-Za-z0-9_]*)(\s*)=')
BUILTIN_SECRETS = ('APP_SECRET_KEY', 'DATABASE_PASSWORD', 'DATABASE_ADMIN_PASSWORD')


class ConfigError(RuntimeError):
    """配置或密钥不满足发布条件。"""


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding='utf-8') as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ConfigError(f'{path} 不是 JSON 对象')
    return data


def dig(data: Any, path: str) -> Any:
    """按点路径读取 Ansible inventory JSON 中的值。"""
    current = data
    for part in path.split('.'):
        if isinstance(current, dict):
            if part not in current:
                raise ConfigError(f'清单缺少字段 {path}')
            current = current[part]
        elif isinstance(current, list):
            current = current[int(part)]
        else:
            raise ConfigError(f'清单字段 {path} 不是可继续索引的结构')
    return current


def parse_value(raw: str) -> str:
    """解析 dotenv 值，兼容本工具写入的双引号转义与已有单引号值。"""
    raw = raw.strip()
    if not raw:
        return ''
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        return re.sub(r'\\(["\\$])', lambda match: match.group(1), raw[1:-1])
    if len(raw) >= 2 and raw[0] == "'" and raw[-1] == "'":
        return raw[1:-1]
    return raw


def read_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        raise ConfigError(
            f'密钥文件 {path} 不存在。请从 infra/deploy/environments/example.secrets.env 复制后填写。'
        )
    values: dict[str, str] = {}
    for lineno, raw in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].lstrip()
        if '=' not in line:
            raise ConfigError(f'{path}:{lineno} 不是 KEY=VALUE 形式')
        key, rest = line.split('=', 1)
        key = key.strip()
        if not KEY_NAME.fullmatch(key):
            raise ConfigError(f'{path}:{lineno} 的键名不合法：{key}')
        values[key] = parse_value(rest)
    return values


def quote_value(value: str) -> str:
    """生成 Docker Compose env_file 可读的双引号值。

    双引号内转义反斜杠、双引号和美元符号，Compose 读取后会还原为原值；
    这样含空格、#、引号的凭据不会被截断，也不会触发变量插值。
    """
    if '\n' in value or '\r' in value:
        raise ConfigError('密钥值不能包含换行')
    escaped = value.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$')
    return f'"{escaped}"'


def write_atomic(path: Path, content: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def write_dotenv(path: Path, values: dict[str, str]) -> None:
    """写回密钥文件，保留原注释和键顺序；只替换已有键、追加缺失键。"""
    original = path.read_text(encoding='utf-8').splitlines() if path.exists() else []
    seen: set[str] = set()
    lines: list[str] = []
    for raw in original:
        match = KEY_LINE.match(raw)
        if match and match.group(2) in values:
            key = match.group(2)
            lines.append(f'{match.group(1)}{key}={quote_value(values[key])}')
            seen.add(key)
        else:
            lines.append(raw)
    for key, value in values.items():
        if key not in seen:
            lines.append(f'{key}={quote_value(value)}')
    write_atomic(path, '\n'.join(lines).rstrip('\n') + '\n', 0o600)
    os.chmod(path, 0o600)


def list_value(manifest: dict[str, Any], path: str) -> list[str]:
    """读取清单里的字符串列表；缺省或 null 返回空列表。"""
    current: Any = manifest
    for part in path.split('.'):
        if not isinstance(current, dict) or part not in current:
            return []
        current = current[part]
    if current is None:
        return []
    if not isinstance(current, list) or any(not isinstance(item, str) for item in current):
        raise ConfigError(f'清单 {path} 必须是字符串列表')
    return current


def mapping_value(manifest: dict[str, Any], path: str) -> dict[str, str]:
    """读取清单里的字符串映射；缺省或 null 返回空映射。"""
    current: Any = manifest
    for part in path.split('.'):
        if not isinstance(current, dict) or part not in current:
            return {}
        current = current[part]
    if current is None:
        return {}
    if not isinstance(current, dict):
        raise ConfigError(f'清单 {path} 必须是字符串映射')
    result: dict[str, str] = {}
    for key, value in current.items():
        if not isinstance(key, str) or not KEY_NAME.fullmatch(key):
            raise ConfigError(f'清单 {path} 的键 {key!r} 不是合法环境变量名')
        result[key] = env_text(value)
    return result


def secret_keys(manifest: dict[str, Any]) -> list[str]:
    """所有允许出现在密钥文件里的键：内置键 + required + generated + app.secrets 的值。"""
    keys = list(BUILTIN_SECRETS)
    for key in list_value(manifest, 'secrets.required') + list_value(manifest, 'secrets.generated'):
        if not KEY_NAME.fullmatch(key):
            raise ConfigError(f'密钥键 {key!r} 不是合法环境变量名')
        if key not in keys:
            keys.append(key)
    for key in mapping_value(manifest, 'app.secrets').values():
        if not KEY_NAME.fullmatch(key):
            raise ConfigError(f'app.secrets 引用的密钥键 {key!r} 不是合法环境变量名')
        if key not in keys:
            keys.append(key)
    return keys


def ensure_secret(values: dict[str, str], key: str, length: int, generated: list[str]) -> None:
    if not values.get(key):
        values[key] = token_module.token_urlsafe(length)
        generated.append(key)


def require_secret(values: dict[str, str], key: str, hint: str) -> None:
    if not values.get(key):
        raise ConfigError(f'缺少必需密钥 {key}：{hint}')


def validate_modes(manifest: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    database = manifest.get('database') or {}
    gateway = manifest.get('gateway') or {}
    if database.get('mode') not in ('bundled', 'external'):
        raise ConfigError('database.mode 必须是 bundled 或 external')
    if gateway.get('mode') not in ('bundled', 'external'):
        raise ConfigError('gateway.mode 必须是 bundled 或 external')
    return database, gateway


def validate_and_generate(manifest: dict[str, Any], values: dict[str, str], action: str) -> list[str]:
    """按环境模式校验必须由人提供的密钥，再补全可生成密钥。"""
    generated: list[str] = []
    database, _ = validate_modes(manifest)
    db_mode = database['mode']
    required = list_value(manifest, 'secrets.required')
    generated_keys = list_value(manifest, 'secrets.generated')
    app_secrets = mapping_value(manifest, 'app.secrets')

    overlap = set(required) & set(generated_keys)
    if overlap:
        raise ConfigError(f'secrets.required 与 secrets.generated 重复：{", ".join(sorted(overlap))}')

    if action == 'db-init':
        if db_mode != 'external':
            raise ConfigError('db-init 只适用于 database.mode=external；bundled 模式由首次启动自动初始化。')
        require_secret(values, 'DATABASE_ADMIN_PASSWORD', '外部 PostgreSQL 管理员密码，仅用于本次初始化。')
        ensure_secret(values, 'DATABASE_PASSWORD', 32, generated)
        return generated

    # 先校验人工输入，避免发布失败时密钥文件已经被改写。
    if action == 'rollback':
        require_secret(values, 'APP_SECRET_KEY', '回滚必须沿用原环境密钥，不能重新生成。')
        require_secret(values, 'DATABASE_PASSWORD', '回滚必须沿用原数据库密码。')
        if db_mode == 'bundled':
            require_secret(values, 'DATABASE_ADMIN_PASSWORD', '回滚必须沿用 bundled 数据库管理员密码。')
    if db_mode == 'external':
        require_secret(
            values,
            'DATABASE_PASSWORD',
            '外部数据库应用角色密码。新库先运行 deploy.sh <env> db-init，或填入已有角色密码。',
        )
    for key in required:
        require_secret(values, key, '清单 secrets.required 声明为必需。')
    for key in app_secrets.values():
        require_secret(values, key, '清单 app.secrets 引用的密钥。')

    # 校验通过后再生成可自动创建的值。
    if action != 'rollback':
        ensure_secret(values, 'APP_SECRET_KEY', 48, generated)
        for key in generated_keys:
            ensure_secret(values, key, 32, generated)
    if db_mode == 'bundled':
        ensure_secret(values, 'DATABASE_PASSWORD', 32, generated)
        ensure_secret(values, 'DATABASE_ADMIN_PASSWORD', 32, generated)

    return generated


def env_text(value: Any) -> str:
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return '' if value is None else str(value)


def build_private_env(
    manifest: dict[str, Any],
    values: dict[str, str],
    api_image: str,
    web_image: str,
) -> dict[str, str]:
    database, gateway = validate_modes(manifest)
    db_mode = database['mode']
    db_user = database['user']
    db_name = database['name']
    db_password = values['DATABASE_PASSWORD']
    db_host = 'postgres' if db_mode == 'bundled' else database['host']
    db_port = 5432 if db_mode == 'bundled' else int(database.get('port', 5432))
    driver = database.get('driver', 'postgresql+asyncpg')
    database_url = (
        f'{driver}://{quote(db_user, safe="")}:{quote(db_password, safe="")}'
        f'@{db_host}:{db_port}/{quote(db_name, safe="")}'
    )

    env: dict[str, str] = {
        'COMPOSE_PROJECT_NAME': manifest['project_name'],
        'DEPLOY_API_IMAGE': api_image,
        'DEPLOY_WEB_IMAGE': web_image,
        'DATABASE_URL': database_url,
        'APP_SECRET_KEY': values['APP_SECRET_KEY'],
    }
    for key, value in mapping_value(manifest, 'app.env').items():
        env[key] = value
    for env_key, secret_key in mapping_value(manifest, 'app.secrets').items():
        env[env_key] = values[secret_key]

    if db_mode == 'bundled':
        env.update({
            'POSTGRES_ADMIN_PASSWORD': values['DATABASE_ADMIN_PASSWORD'],
            'POSTGRES_APP_USER': db_user,
            'POSTGRES_APP_PASSWORD': db_password,
            'POSTGRES_APP_DB': db_name,
            'POSTGRES_APP_SCHEMA': database['schema'],
            'POSTGRES_APP_CONNECTION_LIMIT': str(database.get('connection_limit', 10)),
        })
    else:
        env['SHARED_POSTGRES_NETWORK'] = database['network']

    if gateway['mode'] == 'bundled':
        env['GATEWAY_HTTP_PORT'] = str(gateway.get('http_port', 80))
        env['GATEWAY_HTTPS_PORT'] = str(gateway.get('https_port', 443))
    else:
        env['GATEWAY_UPSTREAM_PORT'] = str(gateway.get('upstream_port', 18080))

    return env


def prepare(args: argparse.Namespace) -> None:
    inventory = load_json(Path(args.inventory_json))
    hostvars = dig(inventory, '_meta.hostvars')
    if not isinstance(hostvars, dict) or 'target' not in hostvars:
        raise ConfigError('环境清单必须且只能定义 target 主机（Ansible inventory 的 hosts.target）。')
    manifest = hostvars['target']
    if not isinstance(manifest, dict):
        raise ConfigError('清单 target hostvars 不是对象')

    allowed = secret_keys(manifest)
    secrets_path = Path(args.secrets_file)

    if args.action == 'bootstrap':
        values: dict[str, str] = {}
        generated: list[str] = []
    else:
        values = read_dotenv(secrets_path)
        generated = validate_and_generate(manifest, values, args.action)
        # 只回写模板认识的键；手工加入的其他键保留在文件里，但不参与校验。
        for key in allowed:
            values.setdefault(key, '')

    if generated or (args.action != 'bootstrap' and not secrets_path.exists()):
        write_dotenv(secrets_path, values)
    elif args.action != 'bootstrap':
        current = read_dotenv(secrets_path)
        merged = {**current, **values}
        if merged != current:
            write_dotenv(secrets_path, merged)
        else:
            os.chmod(secrets_path, 0o600)

    deploy_secrets = {key: values.get(key, '') for key in allowed}
    Path(args.vars_output).write_text(
        json.dumps({'deploy_secrets': deploy_secrets}, ensure_ascii=False),
        encoding='utf-8',
    )
    os.chmod(args.vars_output, 0o600)

    if args.private_env_output:
        if args.action not in ('release', 'rollback'):
            raise ConfigError('只有 release/rollback 需要渲染 private.env')
        if not args.api_image or not args.web_image:
            raise ConfigError('release/rollback 需要 --api-image 与 --web-image')
        env = build_private_env(manifest, values, args.api_image, args.web_image)
        content = ''.join(f'{key}={quote_value(value)}\n' for key, value in env.items())
        write_atomic(Path(args.private_env_output), content, 0o600)

    if generated:
        print('已生成密钥：' + ', '.join(generated))
    if args.action != 'bootstrap':
        print(f'密钥文件已校验：{secrets_path}（值不输出）')


def get_value(args: argparse.Namespace) -> None:
    inventory = load_json(Path(args.inventory_json))
    try:
        value = dig(inventory, args.path)
    except ConfigError:
        if args.default is not None:
            print(args.default)
            return
        raise
    if isinstance(value, bool):
        print('true' if value else 'false')
    elif isinstance(value, (dict, list)):
        print(json.dumps(value, ensure_ascii=False))
    else:
        print('' if value is None else value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)

    prepare_parser = sub.add_parser('prepare', help='生成密钥并渲染部署运行配置')
    prepare_parser.add_argument('--inventory-json', required=True)
    prepare_parser.add_argument('--secrets-file', required=True)
    prepare_parser.add_argument('--action', required=True, choices=('release', 'rollback', 'db-init', 'bootstrap'))
    prepare_parser.add_argument('--api-image', default='')
    prepare_parser.add_argument('--web-image', default='')
    prepare_parser.add_argument('--private-env-output', default='')
    prepare_parser.add_argument('--vars-output', required=True)

    get_parser = sub.add_parser('get', help='读取清单字段')
    get_parser.add_argument('--inventory-json', required=True)
    get_parser.add_argument('--path', required=True)
    get_parser.add_argument('--default', default=None)

    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            prepare(args)
        else:
            get_value(args)
    except ConfigError as exc:
        print(f'部署配置错误：{exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
