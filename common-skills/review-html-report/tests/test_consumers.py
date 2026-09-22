"""两个审查调用方的共享输出行为；在临时目录运行，不修改用户项目。"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


class ConsumerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='shared-review-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        # 独立安装位置：renderer 不依赖旧技能目录或调用方工作目录。
        self.installed = self.root / 'unrelated-install'
        shutil.copytree(ROOT / 'scripts', self.installed)
        self.script = self.installed / 'build-report.py'
        self.data = {
            'target': 'rules.md', 'title': '内容审查', 'mode': 'review',
            'evidenceMode': 'text', 'pageCount': 1, 'showCoverage': True,
            'context': {'受众': '维护者', '决策': '执行长期规范'},
            'pages': [{'id': 'f1', 'where': 'rules.md:1-20', 'review': {'before': '已读 1–20 行'}}],
            'findings': [{'id': 'F1', 'page': 'f1', 'severity': 'should', 'category': 'content',
                          'title': '移除制作说明', 'changeSummary': '[删除] 内部待办',
                          'textComparison': {'before': '<script>window.INJECTED=true</script>',
                                             'suggested': '删除，不替换。'},
                          'fix': '建议删除，尚未执行', 'resolution': 'open'}],
            'suggestedCopy': '完整建议稿\n尚未执行'}

    def run_report(self, *args, no_site=False):
        data = self.root / 'findings.json'
        data.write_text(json.dumps(self.data), encoding='utf-8')
        return subprocess.run([sys.executable, *(['-S'] if no_site else []), str(self.script),
                               '--data', str(data), '--out', str(self.root / 'report.html'), *args],
                              cwd=self.root, capture_output=True, text=True)

    def test_text_has_no_screenshot_requirement_or_pillow_dependency(self):
        result = self.run_report(no_site=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'reviewed')
        html = (self.root / 'report.html').read_text()
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('data:image/', html)
        self.assertNotIn('class="slider"', html)
        self.assertIn('建议 · 尚未执行', html)
        self.assertIn('完整建议稿', html)
        self.assertIn('rules.md:1-20', html)
        self.assertNotIn('已修改 · 已复验', html)

    def test_fixed_text_displays_actual_after_and_fixed_copy(self):
        self.data.update(mode='fix', fixedCopy='实际改后正文')
        self.data.pop('suggestedCopy')
        self.data['pages'][0]['review']['after'] = '已重读，制作说明已删除'
        finding = self.data['findings'][0]
        finding.update(resolution='fixed', fix='已删除制作说明')
        finding['textComparison']['after'] = '实际结果文案'
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'fixed')
        html = (self.root / 'report.html').read_text()
        self.assertIn('改后 · 已执行', html)
        self.assertIn('实际结果文案', html)
        self.assertIn('实际改后正文', html)
        self.assertNotIn('建议 · 尚未执行', html)
        self.assertNotIn('class="slider"', html)
        # 删除也是真实修改，空 after 不得回落为未执行建议。
        finding['textComparison']['after'] = ''
        self.assertEqual(self.run_report().returncode, 0)
        del finding['textComparison']['after']
        self.assertNotEqual(self.run_report().returncode, 0)

    def test_clean_text_and_incomplete_text_have_distinct_status(self):
        self.data['findings'] = []
        self.assertEqual(json.loads(self.run_report('--check').stdout)['status'], 'clean')
        self.assertFalse((self.root / 'report.html').exists())
        self.data['pages'][0]['review'] = {}
        self.assertEqual(json.loads(self.run_report('--check').stdout)['status'], 'incomplete')

    def test_readonly_annotated_evidence_is_not_a_repair(self):
        Image.new('RGB', (320, 180), 'white').save(self.root / 'shot.png')
        self.data['evidenceMode'] = 'visual'
        self.data['pages'][0].update(before=str(self.root / 'shot.png'))
        self.data['pages'][0]['review']['interaction'] = '静态画面，无交互'
        self.data['findings'][0]['annotatedImg'] = str(self.root / 'shot.png')
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'reviewed')
        html = (self.root / 'report.html').read_text()
        self.assertIn('data:image/', html)
        self.assertNotIn('class="slider"', html)
        self.assertIn('待处理', html)
        self.assertNotIn('已修改 · 已复验', html)
        original = html
        self.data['findings'][0]['annotatedImg'] = str(self.root / 'missing.png')
        self.assertNotEqual(self.run_report().returncode, 0)
        self.assertEqual((self.root / 'report.html').read_text(), original)

    def test_spec_annotation_output_renders_without_html_injection_step(self):
        # 仅仓库维护测试定位另一个被测组件；运行时由宿主分别解析技能。
        annotator = ROOT.parent / 'spec-leak-review' / 'scripts' / 'annotate-shot.py'
        Image.new('RGB', (320, 180), 'white').save(self.root / 'shot.png')
        boxes = self.root / 'boxes.json'
        boxes.write_text(json.dumps([{'id': 'F1', 'png': str(self.root / 'shot.png'),
                                      'x': 20, 'y': 30, 'w': 120, 'h': 40, 'scale': 1}]))
        result = subprocess.run([sys.executable, str(annotator), '--boxes', str(boxes),
                                 '--out', str(self.root / 'marked')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        annotations = json.loads((self.root / 'marked' / 'annotations.json').read_text())
        self.data['evidenceMode'] = 'visual'
        self.data['pages'][0].update(before=str(self.root / 'shot.png'))
        self.data['pages'][0]['review']['interaction'] = '静态画面，无交互'
        self.data['findings'][0]['annotatedImg'] = annotations['F1']
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'reviewed')
        html = (self.root / 'report.html').read_text()
        self.assertIn('data:image/', html)
        self.assertNotIn('class="slider"', html)
        self.assertNotIn('__EMBED_', html)

    def test_mixed_text_and_visual_coverage(self):
        Image.new('RGB', (320, 180), 'white').save(self.root / 'shot.png')
        self.data['pageCount'] = 2
        self.data['pages'].append({'id': 'p1', 'evidenceMode': 'visual',
                                   'before': str(self.root / 'shot.png'),
                                   'review': {'before': '可读', 'interaction': '静态无交互'}})
        self.assertEqual(json.loads(self.run_report('--check').stdout)['examinedPages'], 2)
        del self.data['pages'][1]['review']['interaction']
        self.assertEqual(json.loads(self.run_report('--check').stdout)['status'], 'incomplete')

    def test_browser_feedback_text_safety_and_responsive_layout(self):
        second = dict(self.data['findings'][0], id='F2', title='第二项')
        self.data['findings'].append(second)
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        env = dict(os.environ)
        if not env.get('PLAYWRIGHT_MODULE') and not env.get('NODE_PATH'):
            env['NODE_PATH'] = subprocess.check_output(['npm', 'root', '-g'], text=True).strip()
        result = subprocess.run(['node', str(ROOT / 'tests' / 'consumer-browser.cjs'),
                                 str(self.root / 'report.html')], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = json.loads(result.stdout)
        self.assertEqual(seen['errors'], [])
        self.assertEqual(seen['original'], self.data['findings'][0]['textComparison']['before'])
        self.assertEqual(seen['suggested'], '删除，不替换。')
        self.assertIn('[F1 采纳]', seen['single'])
        self.assertNotIn('F2', seen['single'])
        self.assertIn('[F1 采纳]', seen['all'])
        self.assertIn('[F2 待定]', seen['all'])
        self.assertEqual(seen['pending'], 2)  # 采纳意见不等于已经修复。
        self.assertEqual(seen['sliders'], 0)
        self.assertFalse(seen['overflow'])
        self.assertFalse(seen['injected'])
        self.assertEqual(seen['open'], 0)


if __name__ == '__main__':
    unittest.main()
