"""Read workbooks and ledgers from a local file or a pinned Git revision."""
import posixpath
from pathlib import Path
import os
import re
import subprocess
from urllib.parse import unquote, urlsplit

import steward_vocab as vocab


class SourceError(RuntimeError):
    pass


def git(repo, *args):
    try:
        result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                                text=True, timeout=15, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SourceError('Git source cannot be verified (offline or timed out)') from exc
    if result.returncode:
        raise SourceError('Git source cannot be verified (remote unreachable, ref deleted or file missing): ' + result.stderr.strip()[:200])
    return result.stdout


def relative_path(path):
    if not path or '\\' in path or '\0' in path or path.startswith('/') or re.match(r'^[A-Za-z]:', path) or any(p in ('', '.', '..') for p in path.split('/')):
        raise SourceError('Use a normalized repository-relative path')
    return path


def pin(repo, ref):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_./-]*', ref) or '..' in ref or '//' in ref or ref.endswith('/'):
        raise SourceError('--ref must be <remote>/<branch>')
    remote, branch = ref.split('/', 1)
    branch = 'refs/heads/' + branch
    git(repo, 'check-ref-format', branch)
    lines = git(repo, 'ls-remote', '--exit-code', '--refs', remote, branch).split()
    if not lines or not re.fullmatch('[a-f0-9]{40}', lines[0]):
        raise SourceError('The remote returned no verifiable SHA')
    sha = lines[0]
    git(repo, 'fetch', '--no-tags', '--no-write-fetch-head', remote, sha)
    return sha


def read(repo, sha, path):
    if not re.fullmatch('[a-f0-9]{40}', sha):
        raise SourceError('Invalid SHA')
    return git(repo, 'show', f'{sha}:{relative_path(path)}')


def resolve_link(file, target, git_source=False):
    url = urlsplit(target.strip().strip('<>'))
    if url.scheme or url.netloc:
        raise SourceError('The requirement ledger must point to a file in the same source')
    path = unquote(url.path)
    if git_source:
        if path.startswith('/') or '\\' in path:
            raise SourceError('The requirement ledger must live inside the repository')
        return relative_path(posixpath.normpath(posixpath.join(posixpath.dirname(file), path)) if path else file)
    if not path:
        raise SourceError('The requirement ledger link has no path')
    return str((Path(file).parent / path).resolve())


def ledger_entry(text):
    header = re.split(r'^## ', text, maxsplit=1, flags=re.M)[0]
    for label, target in re.findall(r'\[([^\]]+)\]\(([^)]+)\)', header):
        if vocab.LEDGER_LABEL_RE.search(label) or vocab.LEDGER_TARGET_RE.search(target):
            return target, 'history' if label in vocab.HISTORY_LABELS else 'standard'
    raise SourceError('The workbook header has no requirement ledger entry; a passing check does not mean the entry is present')
