"""报告行为回归；用合成 PNG，不读取用户项目。

用法：python3 -m unittest discover -s common-skills/ppt-visual-review/tests -v
      PLAYWRIGHT_MODULE=/path/to/playwright python3 -m unittest discover -s common-skills/ppt-visual-review/tests -v
输出 unittest 结果；浏览器失败也使测试失败。需 Pillow、Playwright/Chromium。
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'build-report.py'


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ppt-report-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name, colors in [('before', ((20, 50, 210), (20, 150, 210))),
                             ('after', ((230, 90, 20), (220, 170, 20)))]:
            img = Image.new('RGB', (640, 360), colors[0])
            ImageDraw.Draw(img).rectangle((320, 0, 639, 359), fill=colors[1])
            for x in (96, 448):
                ImageDraw.Draw(img).rectangle((x, 120, x + 24, 280), fill=(150, 60, 170))
            img.save(self.root / (name + '.png'))
        self.data = {'target': 'synthetic.html', 'pages': [
            {'id': 'p1', 'before': str(self.root / 'before.png')}]}

    def run_report(self, *extra):
        source = self.root / 'input.json'
        source.write_text(json.dumps(self.data))
        return subprocess.run([sys.executable, str(SCRIPT), '--data', str(source),
                               '--out', str(self.root / 'report.html'), *extra], capture_output=True, text=True)

    def test_before_only_is_not_modified_or_comparison(self):
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        html = (self.root / 'report.html').read_text()
        self.assertNotIn('已修改', html)
        self.assertNotIn('class="slider"', html)
        self.assertIn('现状', html)
        self.assertNotIn('src=""', html)

    def test_required_image_failure_does_not_replace_existing_report(self):
        report = self.root / 'report.html'
        for missing in [None, str(self.root / 'missing.png')]:
            with self.subTest(missing=missing):
                report.write_text('previous report')
                self.data['pages'][0]['before'] = missing
                result = self.run_report()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(report.read_text(), 'previous report')

    def test_empty_coverage_cannot_be_clean(self):
        self.data['status'] = 'clean'
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('clean ·', (self.root / 'report.html').read_text())

    def covered(self):
        self.data['pageCount'] = 1
        self.data['pages'][0]['review'] = {'before': 'The result and chart are legible at the presentation viewport.',
                                         'interaction': 'No controls on this static page.'}

    def test_truthful_states_and_read_only_check(self):
        self.covered()
        result = self.run_report('--check')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'clean')
        self.assertFalse((self.root / 'report.html').exists())
        self.data['pending'] = ['Audience cannot yet confirm the intended comparison scope.']
        self.assertEqual(json.loads(self.run_report('--check').stdout)['status'], 'reviewed')
        self.data.pop('pending')
        for alteration in ({'limits': ['A key bitmap region is unreadable']}, {'pageCount': 2}):
            with self.subTest(alteration=alteration):
                data = dict(self.data)
                self.data.update(alteration)
                self.assertEqual(json.loads(self.run_report('--check').stdout)['status'], 'incomplete')
                self.data = data
        self.data['status'] = 'clean'
        self.data['findings'] = [{'id':'V1', 'severity':'should', 'fix':'Enlarge evidence (proposal)'}]
        self.assertEqual(json.loads(self.run_report('--check').stdout)['status'], 'reviewed')
        self.data.update(mode='fix', status='fixed')
        self.data['findings'][0]['resolution'] = 'fixed'
        self.assertEqual(json.loads(self.run_report('--check').stdout)['status'], 'incomplete')
        self.data['pages'][0].update(after=str(self.root / 'after.png'))
        self.data['pages'][0]['review']['after'] = 'Evidence is now large enough in the slide.'
        self.assertEqual(json.loads(self.run_report('--check').stdout)['status'], 'fixed')

    def test_invalid_status_duplicate_pages_and_missing_after_image(self):
        for status in ('unknown', 'fixed'):
            with self.subTest(status=status):
                self.data.update(status=status, mode='review')
                self.assertNotEqual(self.run_report().returncode, 0)
        self.data.pop('status')
        self.data['pages'].append(dict(self.data['pages'][0]))
        self.assertNotEqual(self.run_report().returncode, 0)
        self.data['pages'].pop()
        self.data['pages'][0]['after'] = str(self.root / 'missing.png')
        self.assertNotEqual(self.run_report().returncode, 0)

    def test_legacy_shape_and_independent_rulers(self):
        self.data['status'] = 'fixed'
        self.data['pages'][0].update(after=str(self.root / 'after.png'), beforeRuler=str(self.root / 'before.png'))
        self.data['findings'] = [{'id':'V1', 'severity':'should', 'kind':'slack', 'page':'p1',
                                 'before':'40px', 'after':'20px', 'fix':'container gap', 'where':'synthetic.html:1'}]
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'incomplete')
        html = (self.root / 'report.html').read_text()
        self.assertNotIn('改后标尺', html)
        self.assertNotIn('src=""', html)
        self.assertIn('40px', html)

    def test_help_and_invalid_max_width(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('--check', result.stdout)
        self.assertEqual(self.run_report('--max-width', '0').returncode, 2)

    def test_png_fallback_without_pillow(self):
        source = self.root / 'input.json'
        source.write_text(json.dumps(self.data))
        result = subprocess.run([sys.executable, '-S', str(SCRIPT), '--data', str(source),
                                 '--out', str(self.root / 'report.html')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('data:image/png;base64,', (self.root / 'report.html').read_text())

    def test_browser_comparison_pixels(self):
        pg = self.data['pages'][0]
        pg.update(after=str(self.root / 'after.png'), beforeRuler=pg['before'],
                  afterRuler=str(self.root / 'after.png'))
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        env = dict(os.environ)
        if not env.get('PLAYWRIGHT_MODULE') and not env.get('NODE_PATH'):
            global_root = subprocess.check_output(['npm', 'root', '-g'], text=True).strip()
            env['NODE_PATH'] = global_root
        shots = self.root / 'shots'
        result = subprocess.run(['node', str(Path(__file__).with_name('compare-browser.cjs')),
                                 str(self.root / 'report.html'), str(shots)],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        observations = json.loads(result.stdout)
        if os.environ.get('PPT_REVIEW_TEST_ARTIFACTS'):
            dest = Path(os.environ['PPT_REVIEW_TEST_ARTIFACTS'])
            shutil.copytree(self.root, dest, dirs_exist_ok=True)
            (dest / 'browser-results.json').write_text(result.stdout)
        self.assertEqual(observations['errors'], [])
        self.assertTrue(observations['rulersVisible'])
        self.assertTrue(observations['rulersHidden'])
        self.assertTrue(observations['imagesDecoded'])
        self.assertEqual(observations['sideLabels'], ['改前', '改后'])
        source = {name: Image.open(self.root / (name + '.png')).convert('RGB') for name in ('before', 'after')}
        for observation in observations['observations']:
            name = observation['name']
            with self.subTest(state=name):
                split = float(observation['value']) / 100
                self.assertEqual(observation['leftLabel'], '改前' if split else None)
                self.assertEqual(observation['rightLabel'], '改后' if split < 1 else None)
                img = Image.open(shots / (name + '.png')).convert('RGB')
                for x in (0.1, 0.17, 0.25, 0.45, 0.55, 0.72, 0.9):
                    color = source['before' if x < split else 'after'].getpixel((int(640*x), 216))
                    actual = img.getpixel((1 + int((img.width - 2) * x), 1 + int((img.height - 2) * 0.6)))
                    self.assertLess(max(abs(a - b) for a, b in zip(actual, color)), 12, (name, x, actual, color))
        side = Image.open(shots / 'side.png').convert('RGB')
        for name, box in zip(('before', 'after'), observations['sideImages']):
            for x in (0.25, 0.75):
                color = source[name].getpixel((int(640*x), 216))
                actual = side.getpixel((int(box['x'] - observations['sideBox']['x'] + box['width']*x),
                                        int(box['y'] - observations['sideBox']['y'] + box['height']*0.6)))
                self.assertLess(max(abs(a - b) for a, b in zip(actual, color)), 12)


if __name__ == '__main__':
    unittest.main()
