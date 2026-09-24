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

    LAYOUT_FIXTURE = '''<!doctype html><meta charset="utf-8"><style>
      body { margin:0; font-family:Arial, sans-serif; }
      .slide { position:relative; width:1280px; height:720px; background:#fff; overflow:hidden; }
      .eyebrow { position:absolute; left:64px; top:40px; font-size:16px; color:#2563eb; margin:0; }
      .title { position:absolute; left:64px; top:70px; font-size:40px; font-weight:700; color:#111; margin:0; }
      .card { width:200px; height:120px; border-radius:12px; background:#dbeafe; border:1px solid #93c5fd; }
      .flow { position:absolute; left:64px; top:260px; display:flex; gap:40px; }
      .foot { position:absolute; left:64px; bottom:30px; font-size:14px; color:#666; margin:0; }
    </style>
    <section class="slide" id="s1">
      <p class="eyebrow">第一章</p><h1 class="title">箭头悬空</h1>
      <p style="position:absolute;left:64px;top:200px;width:300px;font-size:24px;margin:0">左侧说明</p>
      <span style="position:absolute;left:560px;top:320px;font-size:24px">→</span>
      <p style="position:absolute;left:640px;top:300px;font-size:24px;margin:0">右侧对象</p>
      <p class="foot">页脚</p>
    </section>
    <section class="slide" id="s2">
      <p class="eyebrow">第二章</p><h1 class="title">大块留白</h1>
      <div style="position:absolute;left:64px;top:170px;display:flex;gap:24px">
        <p style="margin:0;font-size:24px;width:200px">Prompt</p><p style="margin:0;font-size:24px;width:200px">Context</p>
      </div>
      <p style="position:absolute;left:1000px;top:170px;margin:0;font-size:24px">结论</p>
      <p class="foot">页脚</p>
    </section>
    <section class="slide" id="s3">
      <p class="eyebrow">第三章</p><h1 class="title">框样式不一</h1>
      <div class="flow">
        <div class="card" style="background:#f8fafc;border-color:#e2e8f0"></div>
        <div class="card"></div><div class="card"></div><div class="card"></div>
      </div>
      <p style="position:absolute;left:64px;top:420px;margin:0;font-size:25px;color:#2463ea">近似色与邻近字号</p>
      <p class="foot" style="font-family:Georgia, serif">页脚</p>
    </section>
    <section class="slide" id="s4">
      <p class="eyebrow" style="left:80px">第四章</p><h1 class="title" style="left:80px;font-size:44px">标题漂移</h1>
      <p style="position:absolute;left:64px;top:200px;margin:0;font-size:24px">正文</p>
      <p class="foot">页脚</p>
    </section>
    <section class="slide" id="s5">
      <p class="eyebrow">第五章</p><h1 class="title">排版细节</h1>
      <p style="position:absolute;left:64px;top:170px;width:330px;font-size:24px;line-height:26px;margin:0">这一段正文用于检查行距过紧呀</p>
      <p style="position:absolute;left:69px;top:260px;width:600px;font-size:24px;margin:0">为什么会卡住?交付Agent流程</p>
      <p style="position:absolute;left:64px;top:320px;width:400px;font-size:24px;margin:0">使用 AI 工具与 Agent 协作</p>
      <p style="position:absolute;left:8px;top:400px;font-size:11px;margin:0">贴边的小字说明</p>
      <div style="position:absolute;left:64px;top:460px;display:flex;gap:24px">
        <img src="sq.png" style="width:64px;height:64px"><img src="sq.png" style="width:64px;height:64px">
        <img src="sq.png" style="width:64px;height:64px"><img src="sq.png" style="width:48px;height:48px">
      </div>
      <p class="foot">页脚</p>
    </section>'''

    def test_layout_and_consistency_flags(self):
        (self.root / 'layout.html').write_text(self.LAYOUT_FIXTURE)
        Image.new('RGB', (64, 64), (60, 120, 200)).save(self.root / 'sq.png')
        result = self.run_measure('--file', str(self.root / 'layout.html'), '--out', str(self.root), '--label', 'layout')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads((self.root / 'layout.json').read_text())
        by = lambda kind: [f for f in data['flags'] if f['kind'] == kind]
        self.assertTrue(any(f['page'] == 's1' for f in by('arrow')), data['flags'])
        self.assertTrue(any(f['page'] == 's2' and f['sel'] == 'horizontal' for f in by('void')), by('void'))
        self.assertTrue(any(f['page'] == 's2' and f['sel'] == 'vertical' for f in by('void')), by('void'))
        self.assertTrue(any(f['page'] == 's3' for f in by('box-style')), by('box-style'))
        titles = by('title')
        self.assertTrue(any('s4' in f['page'] and f['sel'] == 'headline.size' for f in titles), titles)
        self.assertTrue(any('s4' in f['page'] and f['sel'] == 'eyebrow.left' for f in titles), titles)
        self.assertTrue(by('font-family') and by('color') and by('font-size'), data['flags'])
        self.assertTrue(by('role-style'), data['flags'])
        for kind in ('widow', 'leading', 'half-punct', 'cjk-spacing', 'min-size', 'edge', 'align'):
            self.assertTrue(any(f['page'] == 's5' or 's5' in f['page'].split(',') for f in by(kind)), (kind, data['flags']))
        self.assertFalse(any(f['kind'] == 'edge' and 'foot' in f['sel'] for f in data['flags']))
        self.assertTrue(any(f['page'] == 's5' and '图片/图标' in f['detail'] for f in by('box-style')), by('box-style'))
        inv = data['inventory']
        self.assertEqual(len(inv['titles']), 5)
        self.assertGreaterEqual(len(inv['fonts']), 2)


if __name__ == '__main__':
    unittest.main()