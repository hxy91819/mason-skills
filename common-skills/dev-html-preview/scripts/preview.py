#!/usr/bin/env python3
"""发布可信单文件 HTML 副本并管理 TTL；不安装网关，不修改源文件。

参数：--config 本机 JSON；publish SOURCE [--hours 24]、show [ID]、
renew ID [--hours 24]、delete ID、gc。TTL 为 1 到 168 小时。
输出：stdout JSON（地址、到期时间或清理结果）；错误写 stderr，退出码 2。
示例：preview.py --config /etc/html-preview/publish.json publish /tmp/report.html
      preview.py --config /etc/html-preview/publish.json gc
配置与状态均应位于 Git 外。只删除有效登记目录中的 index.html，不递归清目录。
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import sys
import time
from urllib.parse import quote, urlsplit

ID = re.compile(r"p-[0-9a-f]{16}")


def plain_path(value):
    path = Path(value).absolute()
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f"不接受符号链接: {part}")
    return path.resolve()


def hours(value):
    value = float(value)
    if not math.isfinite(value) or not 1 <= value <= 168:
        raise argparse.ArgumentTypeError("hours 必须在 1 到 168 之间")
    return value


class Store:
    def __init__(self, config):
        cfg = json.loads(plain_path(config).read_text())
        keys = ('publish_root', 'state_root', 'base_url', 'login_url')
        if not isinstance(cfg, dict) or any(not isinstance(cfg.get(key), str) for key in keys):
            raise ValueError('配置需包含 publish_root、state_root、base_url、login_url 字符串')
        if any(not Path(cfg[key]).is_absolute() for key in ('publish_root', 'state_root')):
            raise ValueError('发布和状态目录必须为绝对路径')
        self.root = plain_path(cfg['publish_root'])
        self.state = plain_path(cfg['state_root'])
        if (self.root == self.state or self.root in self.state.parents
                or self.state in self.root.parents):
            raise ValueError('发布目录和状态目录必须独立、互不包含')
        for path in (self.root, self.state):
            if not path.is_dir() or path.stat().st_mode & 0o022:
                raise ValueError(f'目录必须存在且不可被组或其他用户写入: {path}')
        self.base = cfg['base_url'].rstrip('/')
        self.login = cfg['login_url']
        for url in (self.base, self.login):
            parsed = urlsplit(url)
            parsed.port
            if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
                    or parsed.password or parsed.query or parsed.fragment
                    or any(c.isspace() or c in '<>\\' for c in url)):
                raise ValueError('base_url/login_url 需要不含凭据、查询或片段的 HTTPS 地址')
        if urlsplit(self.base).netloc != urlsplit(self.login).netloc:
            raise ValueError('base_url 与 login_url 必须同一 origin')
        self.binding = hashlib.sha256(str(self.root).encode()).hexdigest()

    @contextmanager
    def locked(self):
        fd = os.open(self.state / '.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def path(self, ident):
        if not ID.fullmatch(ident):
            raise ValueError('无效预览 ID')
        return plain_path(self.state / f'{ident}.json')

    def read(self, ident):
        record = json.loads(self.path(ident).read_text())
        if (not isinstance(record, dict) or record.get('version') != 1 or record.get('id') != ident
                or record.get('binding') != self.binding):
            raise ValueError('记录不属于当前发布目录或格式未知')
        for key in ('created_at', 'expires_at'):
            val = record[key]
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
                raise ValueError('无效时间记录')
        return record

    def write(self, record):
        dest = self.path(record['id'])
        temp = self.state / ('.record-' + secrets.token_hex(8))
        try:
            with temp.open('x') as f:
                os.chmod(temp, 0o600)
                json.dump(record, f)
            os.replace(temp, dest)
        finally:
            temp.unlink(missing_ok=True)

    def describe(self, record):
        ident = record['id']
        url = f'{self.base}/{ident}/'
        target = plain_path(self.root / ident / 'index.html')
        return {
            'id': ident, 'url': url,
            'login_url': self.login + '?rd=' + quote(urlsplit(url).path, safe=''),
            'expires_at': datetime.fromtimestamp(record['expires_at'], timezone.utc).isoformat(),
            'expired': record['expires_at'] <= time.time(),
            'published_copy_exists': target.is_file(),
            'access_verified': False,
        }

    def publish(self, source, ttl):
        source = plain_path(source)
        if source.suffix.lower() not in ('.html', '.htm') or not source.is_file():
            raise ValueError('需要可信的单文件 HTML，不能是目录或符号链接')
        payload = source.read_bytes()
        ident = 'p-' + secrets.token_hex(8)
        target = self.root / ident
        if target.exists() or target.is_symlink() or self.path(ident).exists():
            raise ValueError('ID 冲突，请重试发布')
        now = time.time()
        record = dict(version=1, id=ident, binding=self.binding,
                      created_at=now, expires_at=now + ttl * 3600)
        # 先登记，文件复制中断后仍有明确的回收依据。
        self.write(record)
        target.mkdir(mode=0o755)
        index = target / 'index.html'
        with index.open('xb') as f:
            f.write(payload)
        index.chmod(0o644)
        return self.describe(record)

    def renew(self, ident, ttl):
        record = self.read(ident)
        if not plain_path(self.root / ident / 'index.html').is_file():
            raise ValueError('发布副本已不存在，请重新发布源文件')
        record['expires_at'] = time.time() + ttl * 3600
        self.write(record)
        return self.describe(record)

    def delete(self, ident):
        self.read(ident)
        target = plain_path(self.root / ident)
        if target.exists():
            entries = list(target.iterdir())
            if any(p.name != 'index.html' or p.is_symlink() or not p.is_file() for p in entries):
                raise ValueError('目录含未知文件或符号链接，保留并报告')
            for entry in entries:
                entry.unlink()
            target.rmdir()
        self.path(ident).unlink()
        return {'deleted': ident}

    def scan(self, cleanup=False):
        result = {'items': [], 'errors': []}
        for path in sorted(self.state.glob('p-*.json')):
            ident = path.stem
            try:
                record = self.read(ident)
                if cleanup:
                    if record['expires_at'] <= time.time():
                        result['items'].append(self.delete(ident))
                else:
                    result['items'].append(self.describe(record))
            except (OSError, ValueError, KeyError, TypeError, OverflowError) as e:
                result['errors'].append({'id': ident, 'error': str(e)})
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--config', required=True, help='Git 外的本机 JSON 配置')
    commands = parser.add_subparsers(dest='command', required=True)
    pub = commands.add_parser('publish', help='发布单文件 HTML 的副本')
    pub.add_argument('source')
    pub.add_argument('--hours', type=hours, default=24)
    show = commands.add_parser('show', help='只读展示登记、URL 和到期时间；省略 ID 列出全部')
    show.add_argument('id', nargs='?')
    renew = commands.add_parser('renew', help='从现在起续期，已删除副本不可续期')
    renew.add_argument('id')
    renew.add_argument('--hours', type=hours, default=24)
    commands.add_parser('delete', help='只删除指定 ID 的发布副本').add_argument('id')
    commands.add_parser('gc', help='删除到期的已登记副本，不扫描或递归清理源文件')
    args = parser.parse_args()
    try:
        store = Store(args.config)
        with store.locked():
            if args.command == 'publish':
                result = store.publish(args.source, args.hours)
            elif args.command == 'renew':
                result = store.renew(args.id, args.hours)
            elif args.command == 'delete':
                result = store.delete(args.id)
            elif args.command == 'show' and args.id:
                result = store.describe(store.read(args.id))
            else:
                result = store.scan(cleanup=args.command == 'gc')
        print(json.dumps(result, ensure_ascii=False))
        return 2 if result.get('errors') else 0
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
