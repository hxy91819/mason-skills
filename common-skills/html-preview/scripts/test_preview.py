#!/usr/bin/env python3
"""验证 HTML 发布的可观察生命周期和删除边界。
用法：python3 -m unittest discover -s common-skills/html-preview/scripts -p 'test_*.py'
输出：unittest 结果；所有产物位于自动清理的临时目录，不操作真实网关。
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from preview import Store


class PreviewTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'published'
        self.state = self.base / 'state'
        self.root.mkdir()
        self.state.mkdir()
        self.source = self.base / 'report.html'
        self.source.write_text('<html>report</html>')
        self.config = self.base / 'config.json'
        self.cfg = dict(publish_root=str(self.root), state_root=str(self.state),
                        base_url='https://html.preview.test/previews',
                        login_url='https://html.preview.test/oauth2/sign_in')
        self.config.write_text(json.dumps(self.cfg))
        self.store = Store(self.config)

    def test_publish_links_and_delete_preserve_source(self):
        info = self.store.publish(self.source, 24)
        self.assertTrue(info['published_copy_exists'])
        self.assertFalse(info['access_verified'])
        self.assertEqual(info['url'], self.cfg['base_url'] + '/' + info['id'] + '/')
        self.assertIn('?rd=%2Fpreviews%2F', info['login_url'])
        self.store.delete(info['id'])
        self.assertFalse((self.root / info['id']).exists())
        self.assertEqual(self.source.read_text(), '<html>report</html>')

    def test_gc_expiry_and_unknown_directory_preserved(self):
        with patch('preview.time.time', return_value=1000):
            old = self.store.publish(self.source, 1)
            keep = self.store.publish(self.source, 24)
        unknown = self.root / 'p-0123456789abcdef'
        unknown.mkdir()
        (unknown / 'index.html').write_text('unknown')
        with patch('preview.time.time', return_value=4601):
            result = self.store.scan(cleanup=True)
        self.assertEqual(result['items'], [{'deleted': old['id']}])
        self.assertTrue((self.root / keep['id']).exists())
        self.assertTrue(unknown.exists())
        self.assertTrue(self.source.exists())

    def test_renew_keeps_copy_but_deleted_cannot_renew(self):
        with patch('preview.time.time', return_value=1000):
            info = self.store.publish(self.source, 1)
        with patch('preview.time.time', return_value=5000):
            self.store.renew(info['id'], 24)
            self.assertEqual(self.store.scan(cleanup=True)['items'], [])
        self.store.delete(info['id'])
        with self.assertRaises(OSError):
            self.store.renew(info['id'], 24)

    def test_gc_errors_do_not_block_other_expired_copies(self):
        with patch('preview.time.time', return_value=1000):
            bad = self.store.publish(self.source, 1)
            good = self.store.publish(self.source, 1)
        extra = self.root / bad['id'] / 'keep.txt'
        extra.write_text('preserve')
        with patch('preview.time.time', return_value=5000):
            result = self.store.scan(cleanup=True)
        self.assertEqual(result['items'], [{'deleted': good['id']}])
        self.assertEqual(result['errors'][0]['id'], bad['id'])
        self.assertTrue(extra.exists())
        self.assertTrue((self.root / bad['id'] / 'index.html').exists())

    def test_symlinks_and_path_traversal_rejected(self):
        link = self.base / 'link.html'
        link.symlink_to(self.source)
        with self.assertRaises(ValueError):
            self.store.publish(link, 1)
        with self.assertRaises(ValueError):
            self.store.delete('../report.html')
        info = self.store.publish(self.source, 1)
        index = self.root / info['id'] / 'index.html'
        index.unlink()
        index.symlink_to(self.source)
        with self.assertRaises(ValueError):
            self.store.delete(info['id'])
        self.assertTrue(self.source.exists())

    def test_foreign_or_legacy_record_not_deleted(self):
        info = self.store.publish(self.source, 1)
        record_path = self.state / (info['id'] + '.json')
        record_path.write_text(json.dumps({'expires_at': 0}))
        result = self.store.scan(cleanup=True)
        self.assertEqual(len(result['errors']), 1)
        self.assertTrue((self.root / info['id'] / 'index.html').exists())

    def test_config_state_cannot_be_served(self):
        self.cfg['state_root'] = str(self.root / 'state')
        self.config.write_text(json.dumps(self.cfg))
        with self.assertRaises(ValueError):
            Store(self.config)

    def test_malformed_record_does_not_abort_scan(self):
        info = self.store.publish(self.source, 1)
        (self.state / (info['id'] + '.json')).write_text('[]')
        self.assertEqual(len(self.store.scan(cleanup=True)['errors']), 1)
        self.assertTrue((self.root / info['id'] / 'index.html').exists())

    def test_cli_rejects_invalid_ttl_and_returns_json(self):
        cmd = [sys.executable, str(Path(__file__).with_name('preview.py')),
               '--config', str(self.config)]
        for ttl in ['0', 'nan', 'inf', '169']:
            result = subprocess.run(cmd + ['publish', str(self.source), '--hours', ttl], capture_output=True)
            self.assertEqual(result.returncode, 2)
        result = subprocess.run(cmd + ['publish', str(self.source)], capture_output=True, text=True, check=True)
        info = json.loads(result.stdout)
        result = subprocess.run(cmd + ['show', info['id']], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)['url'], info['url'])


if __name__ == '__main__':
    unittest.main()
