"""报告行为回归；用合成 PNG，不读取用户项目。

用法：python3 -m unittest discover -s common-skills/review-html-report/tests -v
      PLAYWRIGHT_MODULE=/path/to/playwright python3 -m unittest discover -s common-skills/review-html-report/tests -v
输出 unittest 结果；浏览器失败也使测试失败。需 Pillow、Playwright/Chromium。
"""
import json
from html.parser import HTMLParser
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'build-report.py'
RED = (217, 45, 32)  # 报告里红框标注用的 --red #d92d20


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

    def browser(self):
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
        return observations, shots

    def test_before_only_is_not_modified_or_comparison(self):
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        html = (self.root / 'report.html').read_text()
        self.assertNotIn('已修改', html)
        self.assertNotIn('class="slider"', html)
        self.assertIn('未完成验收', html)
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

    def test_unembedded_corrupt_screenshots_fail_without_replacing_report(self):
        self.covered()
        broken = self.root / 'broken.png'
        broken.write_bytes(b'not an image')
        report = self.root / 'report.html'
        report.write_text('previous report')
        for key in ('before', 'after'):
            with self.subTest(key=key):
                self.data['pages'][0][key] = str(broken)
                for args in ((), ('--check',)):
                    result = self.run_report(*args)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('图片读取失败', result.stderr)
                    self.assertEqual(report.read_text(), 'previous report')
                self.data['pages'][0][key] = str(self.root / (key + '.png'))

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
        self.data['findings'] = [{'id':'V1', 'page':'p1', 'severity':'should', 'fix':'Enlarge evidence (proposal)'}]
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
        self.data['findings'] = [{'id': 'V1', 'page': 'p1', 'severity': 'should', 'resolution': 'fixed', 'fix': 'spacing'}]
        source = self.root / 'input.json'
        source.write_text(json.dumps(self.data))
        result = subprocess.run([sys.executable, '-S', str(SCRIPT), '--data', str(source),
                                 '--out', str(self.root / 'report.html')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('data:image/png;base64,', (self.root / 'report.html').read_text())

    def test_invalid_box_degrades_with_limits_note(self):
        self.covered()
        for bad in ([64, 430, 0, 160], [64, 430], ['x', 430, 100, 100]):
            with self.subTest(bad=bad):
                self.data['findings'] = [{'id': 'V1', 'severity': 'should', 'page': 'p1',
                                          'title': 'Gap', 'resolution': 'fixed', 'box': bad, 'fix': 'proposal'}]
                result = self.run_report()
                self.assertEqual(result.returncode, 0, result.stderr)
                html = (self.root / 'report.html').read_text()
                self.assertNotIn('class="rbox"', html)
                self.assertIn('红框', html)
                self.assertNotIn('src=""', html)

    def test_box_pixel_coordinates_and_short_line(self):
        self.covered()
        self.data['findings'] = [{
            'id': 'V1', 'severity': 'should', 'kind': 'slack', 'page': 'p1',
            'title': 'Bottom band is empty',
            'short': 'A wide empty band sits between the cards and the takeaway.',
            'label': '空带 160px', 'resolution': 'fixed', 'box': [64, 100, 512, 128],
            'why': 'The band pushes the takeaway to the page edge.',
            'fix': 'Tighten spacing (proposal only).', 'where': 'deck.html:1',
        }]
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        html = (self.root / 'report.html').read_text()
        # before 截图是 640x360：64/640=10%，100/360≈27.78%，512/640=80%，128/360≈35.6%。
        self.assertIn('left:10.00%', html)
        self.assertIn('top:27.78%', html)
        self.assertIn('空带 160px', html)
        self.assertIn('class="mk"', html)
        self.assertIn('A wide empty band sits between', html)
        self.assertNotIn('class="slider"', html)
        self.assertNotIn('src=""', html)

    def test_box_out_of_range_is_clamped(self):
        self.covered()
        # y=430 超出 360 高的截图：top 钳到 100%，高被压到 0 → 视为无效，红框省略并记 limits。
        self.data['findings'] = [{'id': 'V1', 'severity': 'should', 'page': 'p1',
                                  'title': 'Gap', 'resolution': 'fixed', 'box': [64, 430, 512, 128], 'fix': 'proposal'}]
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        html = (self.root / 'report.html').read_text()
        self.assertNotIn('class="rbox"', html)
        self.assertIn('红框', html)

    def test_finding_level_comparison_without_page_after(self):
        self.covered()
        self.data['findings'] = [{'id': 'V1', 'severity': 'should', 'page': 'p1', 'title': 'Gap',
                                  'resolution': 'fixed', 'box': [64, 100, 300, 120], 'fix': 'tighten',
                                  'beforeImg': str(self.root / 'before.png'),
                                  'afterImg': str(self.root / 'after.png')}]
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        html = (self.root / 'report.html').read_text()
        self.assertEqual(html.count('class="cmp"'), 1)   # 仅已修项有对照，检查摘要没有图片
        self.assertIn('class="slider"', html)
        self.assertIn('已修复', html)

    def test_each_repair_comparison_stays_in_its_own_finding_card(self):
        self.covered()
        self.data['findings'] = [
            {'id': fid, 'severity': 'should', 'page': 'p1', 'title': fid,
             'resolution': resolution, 'resolutionReason': 'Keep intentional spacing',
             'fix': 'Adjust spacing', 'beforeImg': str(self.root / 'before.png'),
             'afterImg': str(self.root / 'after.png')}
            for fid, resolution in [('V1', 'fixed'), ('V2', 'fixed'), ('V3', 'open'), ('V4', 'kept')]]
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)

        class Cards(HTMLParser):
            def __init__(self):
                super().__init__()
                self.depth = 0
                self.card = None
                self.cards = []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'details':
                    self.depth += 1
                    if 'finding' in attrs.get('class', '').split():
                        self.card = {'depth': self.depth, 'text': '', 'sliders': []}
                        self.cards.append(self.card)
                if self.card and tag == 'input' and attrs.get('type') == 'range':
                    self.card['sliders'].append(attrs.get('aria-label'))

            def handle_endtag(self, tag):
                if tag == 'details':
                    if self.card and self.depth == self.card['depth']:
                        self.card = None
                    self.depth -= 1

            def handle_data(self, text):
                if self.card:
                    self.card['text'] += text

        cards = Cards()
        cards.feed((self.root / 'report.html').read_text())
        self.assertEqual(len(cards.cards), 4)
        for card, fid in zip(cards.cards, ('V1', 'V2', 'V3', 'V4')):
            self.assertIn(fid, card['text'])
            self.assertIn('Adjust spacing', card['text'])
            self.assertEqual(card['sliders'], [fid + ' 改前改后分界'] if fid in ('V1', 'V2') else [])

    def test_finding_compare_needs_both_images(self):
        self.covered()
        # 页 id 未命中时 finding 无页级回落，beforeImg 缺失 → 不渲染对照并记降级说明。
        self.data['findings'] = [{'id': 'V1', 'severity': 'should', 'page': 'ghost', 'title': 'Gap',
                                  'afterImg': str(self.root / 'after.png'), 'fix': 'x', 'resolution': 'fixed'}]
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        html = (self.root / 'report.html').read_text()
        self.assertNotIn('class="slider"', html)
        self.assertIn('缺少其一', html)

    def test_unchanged_pages_do_not_add_report_content(self):
        self.covered()
        self.data['pages'][0]['after'] = str(self.root / 'after.png')
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        small = (self.root / 'report.html').read_text()
        for n in range(2, 29):
            pg = dict(self.data['pages'][0], id=f'p{n}', title=f'Unchanged page {n}')
            self.data['pages'].append(pg)
        self.data['pageCount'] = 28
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        large = (self.root / 'report.html').read_text()
        self.assertNotIn('data:image/', large)
        self.assertNotIn('class="slider"', large)
        self.assertNotIn('class="fold page"', large)
        self.assertNotIn('Unchanged page 28', large)
        self.assertLess(len(large) - len(small), 10000)

    def test_page_compare_shows_changed_pages_and_metrics(self):
        self.covered()
        self.data['mode'] = 'fix'
        self.data['pages'][0].update(title='Changed page', after=str(self.root / 'after.png'))
        self.data['pages'][0]['review']['after'] = 'Gap closed after moving the conclusion.'
        self.data['pages'].append(dict(self.data['pages'][0], id='p2', title='Same page',
                                       after=str(self.root / 'before.png')))
        self.data['pageCount'] = 2
        self.data['pageCompare'] = True
        self.data['metrics'] = [{'name': 'void flags', 'before': 9, 'after': 2}]
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        html = (self.root / 'report.html').read_text()
        self.assertIn('整体前后对照', html)
        self.assertEqual(html.count('class="fold pagecmp"'), 1)
        self.assertIn('data-page-id="p1"', html)
        self.assertIn('1 页无像素变化：p2', html)
        self.assertIn('void flags', html)
        self.assertIn('Gap closed after moving the conclusion.', html)

    def test_page_compare_requires_fix_mode(self):
        self.covered()
        self.data['pageCompare'] = True
        result = self.run_report()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('pageCompare', result.stderr)

    def test_open_and_kept_findings_do_not_embed_images(self):
        self.covered()
        self.data['findings'] = [
            {'id': resolution, 'page': 'p1', 'severity': 'should', 'resolution': resolution,
             'title': 'Text explanation', 'fix': 'Proposal', 'resolutionReason': 'Intentional',
             'afterImg': str(self.root / 'after.png')}
            for resolution in ('open', 'kept')]
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        html = (self.root / 'report.html').read_text()
        self.assertNotIn('data:image/', html)
        self.assertNotIn('class="slider"', html)
        self.assertIn('Text explanation', html)

    def test_identical_repair_images_do_not_get_slider(self):
        self.covered()
        self.data['findings'] = [{'id': 'V1', 'page': 'p1', 'severity': 'should',
                                  'resolution': 'fixed', 'fix': 'Style adjustment',
                                  'afterImg': str(self.root / 'before.png')}]
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('class="slider"', (self.root / 'report.html').read_text())

    def test_visual_repairs_and_content_advice_have_separate_results(self):
        self.covered()
        self.data['mode'] = 'fix'
        self.data['pages'][0]['after'] = str(self.root / 'after.png')
        self.data['pages'][0]['review']['after'] = 'Text now fits and is legible.'
        self.data['findings'] = [
            {'id': 'V1', 'category': 'visual', 'kind': 'evidence', 'page': 'p1',
             'severity': 'should', 'title': 'Evidence text too small',
             'resolution': 'fixed', 'fix': 'Increase font size'},
            {'id': 'C1', 'category': 'content', 'kind': 'evidence', 'page': 'p1',
             'severity': 'should', 'title': 'Survey lacks sample size',
             'resolution': 'open', 'fix': 'Ask author to supply survey scope'}]
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        groups = json.loads(result.stdout)['groups']
        self.assertEqual(groups['visual']['status'], 'fixed')
        self.assertEqual(groups['visual']['unresolved'], 0)
        self.assertEqual(groups['content']['status'], 'reviewed')
        self.assertEqual(groups['content']['unresolved'], 1)

        class Sections(HTMLParser):
            def __init__(self):
                super().__init__()
                self.current = None
                self.sections = {}
            def handle_starttag(self, tag, attrs):
                if tag == 'section':
                    self.current = dict(attrs)['id']
                    self.sections[self.current] = {'text': '', 'sliders': 0}
                if self.current and tag == 'input' and dict(attrs).get('type') == 'range':
                    self.sections[self.current]['sliders'] += 1
            def handle_endtag(self, tag):
                if tag == 'section':
                    self.current = None
            def handle_data(self, text):
                if self.current:
                    self.sections[self.current]['text'] += text
        parser = Sections()
        parser.feed((self.root / 'report.html').read_text())
        visual, content = (parser.sections[name] for name in ('visual-findings', 'content-findings'))
        self.assertIn('V1', visual['text'])
        self.assertNotIn('C1', visual['text'])
        self.assertIn('C1', content['text'])
        self.assertNotIn('V1', content['text'])
        self.assertEqual(visual['sliders'], 1)
        self.assertEqual(content['sliders'], 0)

    def test_unknown_finding_category_is_rejected(self):
        self.covered()
        self.data['findings'] = [{'id': 'V1', 'severity': 'should', 'category': 'other'}]
        self.assertNotEqual(self.run_report().returncode, 0)

    def test_process_appendices_stay_local_but_limits_remain_visible(self):
        self.covered()
        self.data['pages'][0]['review']['summary'] = 'INTERNAL_PAGE_OBSERVATION'
        self.data['kept'] = [{'what': 'INTERNAL_KEPT_ITEM', 'why': 'Intentional spacing'}]
        self.data['pending'] = ['INTERNAL_DUPLICATE_PENDING']
        self.data['commands'] = [{'cmd': 'INTERNAL_COMMAND', 'result': 'PASS'}]
        self.data['limits'] = ['A missing slide prevents full visual review.']
        self.data['findings'] = [{'id': 'C1', 'category': 'content', 'page': 'p1',
                                 'severity': 'should', 'title': 'Survey scope needed',
                                 'fix': 'AUTHOR_ACTION: supply sample size', 'resolution': 'open'}]
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        html = (self.root / 'report.html').read_text()
        for marker in ('INTERNAL_PAGE_OBSERVATION', 'INTERNAL_KEPT_ITEM',
                       'INTERNAL_DUPLICATE_PENDING', 'INTERNAL_COMMAND'):
            self.assertNotIn(marker, html)
        self.assertIn('AUTHOR_ACTION: supply sample size', html)
        self.assertIn('A missing slide prevents full visual review.', html)
        self.assertEqual(json.loads(result.stdout)['pending'], 1)
        source = json.loads((self.root / 'input.json').read_text())
        self.assertEqual(source['commands'][0]['cmd'], 'INTERNAL_COMMAND')

    def test_browser_comparison_pixels(self):
        self.data['findings'] = [{'id': 'V1', 'page': 'p1', 'severity': 'should', 'resolution': 'fixed', 'fix': 'spacing'}]
        pg = self.data['pages'][0]
        pg.update(after=str(self.root / 'after.png'), beforeRuler=pg['before'],
                  afterRuler=str(self.root / 'after.png'))
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        observations, shots = self.browser()
        self.assertEqual(observations['errors'], [])
        self.assertGreater(observations['detailsTotal'], 0)
        self.assertEqual(observations['closedInitially'], observations['detailsTotal'])
        self.assertEqual(observations['openInitially'], 0)
        self.assertEqual(observations['openAfterExpand'], observations['detailsTotal'])
        self.assertNotIn('rulersVisible', observations)
        self.assertTrue(observations['imagesDecoded'])
        self.assertEqual(observations['sideLabels'], ['改前', '改后'])
        self.assertAlmostEqual(observations['dragValue'], 70, delta=3)
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

    def test_browser_finding_annotation(self):
        self.covered()
        self.data['findings'] = [{
            'id': 'V1', 'severity': 'should', 'kind': 'slack', 'page': 'p1',
            'title': 'Bottom band is empty', 'label': '空带 160px',
            'resolution': 'fixed', 'box': [320, 90, 256, 144], 'why': 'gap', 'fix': 'proposal', 'where': 'deck.html:1',
        }]
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        observations, shots = self.browser()
        self.assertEqual(observations['errors'], [])
        self.assertEqual(observations['closedInitially'], observations['detailsTotal'])
        self.assertEqual(observations['openAfterExpand'], observations['detailsTotal'])
        self.assertTrue(observations['imagesDecoded'])
        annotation = observations['annotation']
        self.assertEqual(annotation['rlabel'], '空带 160px')
        self.assertTrue(annotation['insideImage'], annotation)
        # 框选区域左缘中点应是红框描边色。
        annotated = Image.open(shots / 'annotated.png').convert('RGB')
        img_w = annotated.width - 2  # figure 1px 边框
        img_h = img_w * 360 / 640
        rel = annotation['rel']
        # figcaption 在 img 下方，标注图高 = 1 + img_h + caption；img 从 y=1 开始。
        px = annotated.getpixel((int(1 + rel['x'] * img_w) + 1, int(1 + (rel['y'] + rel['h'] / 2) * img_h)))
        self.assertLess(max(abs(a - b) for a, b in zip(px, RED)), 30, (px, RED))


if __name__ == '__main__':
    unittest.main()
