import posixpath
from pathlib import Path
import os
import re
import subprocess
from urllib.parse import unquote, urlsplit


class SourceError(RuntimeError):
    pass


def git(repo, *args):
    try:
        result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                                text=True, timeout=15, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SourceError('Git 来源无法核实（离线或超时）') from exc
    if result.returncode:
        raise SourceError('Git 来源无法核实（远端不可达、ref 已删除或文件不存在）：' + result.stderr.strip()[:200])
    return result.stdout


def relative_path(path):
    if not path or '\\' in path or '\0' in path or path.startswith('/') or re.match(r'^[A-Za-z]:', path) or any(p in ('', '.', '..') for p in path.split('/')):
        raise SourceError('请使用仓库内规范相对路径')
    return path


def pin(repo, ref):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_./-]*', ref) or '..' in ref or '//' in ref or ref.endswith('/'):
        raise SourceError('--ref 必须为远端/分支')
    remote, branch = ref.split('/', 1)
    branch = 'refs/heads/' + branch
    git(repo, 'check-ref-format', branch)
    lines = git(repo, 'ls-remote', '--exit-code', '--refs', remote, branch).split()
    if not lines or not re.fullmatch('[a-f0-9]{40}', lines[0]):
        raise SourceError('远端未返回可核实 SHA')
    sha = lines[0]
    git(repo, 'fetch', '--no-tags', '--no-write-fetch-head', remote, sha)
    return sha


def read(repo, sha, path):
    if not re.fullmatch('[a-f0-9]{40}', sha):
        raise SourceError('无效 SHA')
    return git(repo, 'show', f'{sha}:{relative_path(path)}')


def resolve_link(file, target, git_source=False):
    url = urlsplit(target.strip().strip('<>'))
    if url.scheme or url.netloc:
        raise SourceError('要求帐必须指向同来源文件')
    path = unquote(url.path)
    if git_source:
        if path.startswith('/') or '\\' in path:
            raise SourceError('要求帐必须位于仓库内')
        return relative_path(posixpath.normpath(posixpath.join(posixpath.dirname(file), path)) if path else file)
    if not path:
        raise SourceError('要求帐链接缺少路径')
    return str((Path(file).parent / path).resolve())


def ledger_entry(text):
    header = re.split(r'^## ', text, maxsplit=1, flags=re.M)[0]
    for label, target in re.findall(r'\[([^\]]+)\]\(([^)]+)\)', header):
        if re.search(r'要求[帳帐]', label) or re.search(r'-要求[帳帐]\.md(?:[#?]|$)', target):
            return target, 'history' if label == '要求帐（历史流水账）' else 'standard'
    raise SourceError('工作簿标头缺少要求帐入口；check 通过不代表入口齐全')
