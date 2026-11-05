"""Integration coverage for offline workbook initialization."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import steward_workbook as sw


class InitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / 'project'
        self.repo.mkdir()
        self.git('init')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def test_init_and_repeat(self):
        first = sw.init_workbook(self.repo)
        path = Path(first['path'])
        self.assertTrue(first['created'])
        self.assertTrue((path / '.git').is_dir())
        self.assertEqual(self.git('check-ignore', '.local/steward/'), '.local/steward/')
        exclude = self.repo / '.git/info/exclude'
        before = exclude.read_bytes()
        again = sw.init_workbook(self.repo)
        self.assertFalse(again['created'])
        self.assertEqual(again['imported'], [])
        self.assertEqual(exclude.read_bytes(), before)
        self.assertEqual(subprocess.check_output(['git', '-C', str(path), 'remote']), b'')
        workbook = path / 'topic.md'
        workbook.write_text('local baseline')
        local_git = ['git', '-C', str(path)]
        subprocess.run(local_git + ['add', 'topic.md'], check=True, capture_output=True)
        subprocess.run(local_git + ['-c', 'user.name=Test', '-c', 'user.email=test@example.org',
                                   'commit', '-m', 'baseline'], check=True, capture_output=True)
        self.assertEqual(sw.head_content_for(workbook), 'local baseline')
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_existing_ignore_is_preserved(self):
        (self.repo / '.gitignore').write_text('/.local/\n')
        exclude = self.repo / '.git/info/exclude'
        before = exclude.read_bytes()
        result = sw.init_workbook(self.repo)
        self.assertIn('.gitignore', result['ignored_by'])
        self.assertEqual(before, exclude.read_bytes())

    def test_worktree_and_read_only_path(self):
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.org',
                 'commit', '--allow-empty', '-m', 'init')
        wt = Path(self.tmp.name) / 'linked'
        self.git('worktree', 'add', '-b', 'linked', str(wt))
        expected = self.repo / '.local/steward'
        script = Path(sw.__file__).resolve()
        result = subprocess.check_output(['python3', str(script), '--mode', 'path'], cwd=wt, text=True)
        self.assertEqual(result.strip(), str(expected))
        self.assertFalse(expected.exists())
        result = json.loads(subprocess.check_output(
            ['python3', str(script), '--mode', 'init', '--repo', str(wt)], text=True))
        self.assertEqual(result['path'], str(expected))

    def test_import_only_into_empty_target(self):
        legacy = self.repo / 'docs/steward'
        legacy.mkdir(parents=True)
        (legacy / 'topic.md').write_text('workbook')
        (legacy / 'topic-要求帳.md').write_text('ledger')
        result = sw.init_workbook(self.repo)
        self.assertEqual(result['imported'], ['topic-要求帳.md', 'topic.md'])
        target = Path(result['path']) / 'topic.md'
        self.assertEqual(target.read_text(), 'workbook')
        target.write_text('local changes')
        self.assertEqual(sw.init_workbook(self.repo)['imported'], [])
        self.assertEqual(target.read_text(), 'local changes')
        self.assertEqual((legacy / 'topic.md').read_text(), 'workbook')
