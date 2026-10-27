import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import steward_source as source
import steward_watch as watch
from test_steward_workbook import VALID_WORKBOOK
from test_steward_ledger import FIXTURE


class GitSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / 'repo'
        self.remote = Path(self.tmp.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(self.remote)], check=True)
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('remote', 'add', 'origin', str(self.remote))
        self.workbook = self.repo / 'docs/workbook.md'
        self.workbook.parent.mkdir()
        self.workbook.write_text(VALID_WORKBOOK.replace('更新：2026-10-14', '[要求帐](ledger.md)'))
        (self.repo / 'docs/ledger.md').write_text(FIXTURE)
        self.commit('first')
        self.entry = {'repo': str(self.repo), 'ref': 'origin/main', 'path': 'docs/workbook.md', 'workbook': str(self.workbook)}

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], text=True, stderr=subprocess.DEVNULL).strip()

    def commit(self, title):
        self.git('add', '.')
        self.git('commit', '-qm', title)
        self.git('push', '-q', 'origin', 'HEAD:refs/heads/main')
        return self.git('rev-parse', 'HEAD')

    def checker(self, *args):
        result = subprocess.run([sys.executable, str(Path(watch.sw.__file__)), '--repo', str(self.repo),
                                 '--file', 'docs/workbook.md', '--mode', 'check', *args], capture_output=True, text=True)
        return result.returncode, json.loads(result.stdout)

    def test_remote_advances_and_disk_missing_or_different_do_not_change_source(self):
        first = source.pin(self.repo, 'origin/main')
        self.workbook.write_text('wrong disk')
        self.assertIn('项目介绍', watch.read_workbook(self.entry))
        self.workbook.write_text(VALID_WORKBOOK.replace('更新：2026-10-14', '[要求帐](new.md)'))
        (self.repo / 'docs/new.md').write_text(FIXTURE)
        second = self.commit('second')
        self.workbook.unlink()
        (self.repo / 'docs/new.md').unlink()
        code, result = self.checker('--ref', 'origin/main')
        self.assertEqual(code, 0, result)
        self.assertEqual(result['snapshot']['sha'], second)
        self.assertEqual(result['ledger']['path'], 'docs/new.md')
        code, result = self.checker('--revision', first)
        self.assertEqual(code, 0, result)
        self.assertEqual(result['ledger']['path'], 'docs/ledger.md')

    def test_remote_deleted_unreachable_or_timed_out_does_not_fall_back(self):
        self.git('update-ref', 'refs/remotes/origin/main', 'HEAD')
        subprocess.run(['git', '-C', str(self.remote), 'update-ref', '-d', 'refs/heads/main'], check=True)
        with self.assertRaises(watch.WatchError):
            watch.read_workbook(self.entry)
        code, result = self.checker('--ref', 'origin/main')
        self.assertEqual(code, 2)
        self.assertFalse(result['ok'])
        self.git('remote', 'set-url', 'origin', str(self.repo / 'missing'))
        with self.assertRaises(watch.WatchError):
            watch.read_workbook(self.entry)
        with patch.object(source.subprocess, 'run', side_effect=subprocess.TimeoutExpired('git', 15)):
            with self.assertRaisesRegex(source.SourceError, '超时'):
                source.pin(self.repo, 'origin/main')

    def test_history_index_and_paths_preserve_original_text_without_standard_statistics(self):
        self.workbook.write_text(VALID_WORKBOOK.replace('更新：2026-10-14', '[要求帐（历史流水账）](history/README.md)'))
        history = self.repo / 'docs/history'
        history.mkdir()
        (history / 'README.md').write_text('[旧账](../ledger.md)')
        sha = self.commit('history')
        code, result = self.checker('--ref', 'origin/main')
        self.assertEqual(code, 0, result)
        self.assertEqual(result['ledger']['kind'], 'history')
        target = source.resolve_link('docs/history/README.md', '../ledger.md', True)
        self.assertEqual(source.read(self.repo, sha, target), FIXTURE)
        for target in ('../../../etc/passwd', '/etc/passwd', 'https://example.org/a', '..%2F..%2F..%2Fetc'):
            with self.subTest(target=target), self.assertRaises(source.SourceError):
                source.resolve_link('docs/workbook.md', target, True)
        result = subprocess.run([sys.executable, str(Path(watch.sw.__file__)), '--mode', 'ledger-check',
                                 '--repo', str(self.repo), '--revision', sha, '--file', 'docs/history/README.md',
                                 '--ledger-kind', 'history'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        checked = json.loads(result.stdout)
        self.assertFalse(checked['applicable'])
        self.assertNotIn('summary', checked)


if __name__ == '__main__':
    unittest.main()
