"""测量命令的兼容性与失败边界；视觉质量由独立评估判断。

用法：python3 -m unittest discover -s common-skills/ppt-visual-review/tests -v
      python3 -m unittest discover -s common-skills/ppt-visual-review/tests -p test_measure.py -v
输出测试结果，失败非零；合成产物仅存临时目录。需 Playwright/Chromium、Pillow。
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from PIL import Image

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'measure-deck.js'


class MeasureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ppt-measure-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = dict(os.environ)
        if not self.env.get('PLAYWRIGHT_MODULE') and not self.env.get('NODE_PATH'):
            self.env['NODE_PATH'] = subprocess.check_output(['npm', 'root', '-g'], text=True).strip()

    def run_measure(self, *args):
        return subprocess.run(['node', str(SCRIPT), *args], env=self.env, capture_output=True, text=True)

    def test_existing_capture_geometry_and_gate(self):
        generated = subprocess.run([sys.executable, str(Path(__file__).with_name('make-review-fixtures.py')),
                                    '--out', str(self.root)], capture_output=True, text=True)
        self.assertEqual(generated.returncode, 0, generated.stderr)
        for index, args in enumerate((['--file', str(self.root / 'case-a.html')],
                                      ['--url', (self.root / 'case-b.html').as_uri()])):
            with self.subTest(index=index):
                result = self.run_measure(*args, '--out', str(self.root), '--label', f'page{index}', '--shot', '--gate')
                self.assertIn(result.returncode, (0, 4), result.stderr)
                data = json.loads((self.root / f'page{index}.json').read_text())
                self.assertEqual(data['pageCount'], 1)
                self.assertEqual((data['pages'][0]['width'], data['pages'][0]['height']), (1280, 720))
                self.assertEqual(result.returncode, 4 if data['flags'] else 0)
                for shot in data['shots']['slide-1'].values():
                    with Image.open(shot) as image:
                        self.assertEqual(image.size, (1280, 720))

    def test_help_invalid_input_and_no_matching_slides(self):
        self.assertEqual(self.run_measure('--help').returncode, 0)
        self.assertEqual(self.run_measure('-h').returncode, 0)
        self.assertEqual(self.run_measure('--file', 'absent.html', '--tol', 'NaN').returncode, 2)
        self.assertEqual(self.run_measure('--file', 'absent.html', '--viewport', '0x20').returncode, 2)
        empty = self.root / 'empty.html'
        empty.write_text('<!doctype html><h1>Not a deck</h1>')
        self.assertEqual(self.run_measure('--file', str(empty), '--out', str(self.root)).returncode, 3)


if __name__ == '__main__':
    unittest.main()
