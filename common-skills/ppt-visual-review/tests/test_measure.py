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

    TRAP_FIXTURE = '''<!doctype html><meta charset="utf-8"><style>
      .slide { position:relative; width:1280px; height:720px; background:#fff; overflow:hidden; }
      .chain { display:grid; grid-template-columns:1fr 40px 1fr 40px 1fr; align-items:center;
               height:140px; margin:60px 80px 0; }
      .chain > div { font-size:24px; line-height:31.2px; border-top:2px solid #888; padding-top:16px; }
      .chain b { font-size:24px; }
    </style>
    <section class="slide active" id="s1">
      <div class="chain">
        <div>步骤一</div><b>→</b>
        <div>步骤二<small style="display:block;font-size:15px;color:#999">注释行撑高容器</small></div><b>→</b>
        <div>步骤三</div>
      </div>
      <p style="width:200px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;margin:30px 80px 0;font-size:18px;color:#000">这一段说明文字非常长一定会被水平截断掉尾巴内容全部都在</p>
      <img src="missing.png" alt="broken" style="width:300px;height:120px;margin:30px 80px 0">
      <img src="sq.png" alt="distorted" style="width:200px;height:50px;display:block;margin:20px 80px 0">
      <div style="position:relative;width:260px;height:36px;margin:20px 80px 0">
        <span style="font-size:18px">被覆盖的文字示例内容展示</span>
        <div style="position:absolute;inset:0;background:#eee"></div>
      </div>
      <p style="color:#bbbbbb;font-size:14px;margin:20px 80px 0">低对比度小字样本示例内容用于触发对比度线索判断逻辑</p>
    </section>'''

    def test_common_pitfall_flags(self):
        (self.root / 'pitfall.html').write_text(self.TRAP_FIXTURE)
        sq = Image.new('RGB', (100, 100), (200, 60, 60))
        sq.save(self.root / 'sq.png')   # 正方形位图被拉成 200x50 → 变形
        result = self.run_measure('--file', str(self.root / 'pitfall.html'), '--out', str(self.root), '--label', 'trap')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads((self.root / 'trap.json').read_text())
        kinds = {f['kind'] for f in data['flags']}
        for kind in ('connector', 'overflow', 'image', 'occlusion', 'contrast'):
            self.assertIn(kind, kinds, data['flags'])
        conn = [f for f in data['flags'] if f['kind'] == 'connector']
        self.assertTrue(all('文字带' in f['detail'] for f in conn))
        self.assertEqual(len([f for f in data['flags'] if f['kind'] == 'image' and '失败' in f['detail']]), 1)


if __name__ == '__main__':
    unittest.main()