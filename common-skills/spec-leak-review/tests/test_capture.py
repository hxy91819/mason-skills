"""合成渲染面的清单与报告注入回归，不读取外部项目。

用法：python3 -m unittest discover -s common-skills/spec-leak-review/tests -v
      PLAYWRIGHT_MODULE=/path/to/playwright python3 -m unittest discover -s common-skills/spec-leak-review/tests -v
输出 unittest 结果；失败非零。依赖 Pillow、Playwright/Chromium。
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from PIL import Image, ImageDraw

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='spec-capture-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = dict(os.environ)
        if not self.env.get('PLAYWRIGHT_MODULE') and not self.env.get('NODE_PATH'):
            self.env['NODE_PATH'] = subprocess.check_output(['npm', 'root', '-g'], text=True).strip()
        img = Image.new('RGB', (320, 100), 'white')
        ImageDraw.Draw(img).text((12, 20), 'Production note: replace chart before release', fill='black')
        img.save(self.root / 'bitmap.png')

    def capture(self, html):
        surface = self.root / 'surface.html'
        surface.write_text(html)
        result = subprocess.run(['node', str(SCRIPTS / 'capture-surface.js'), '--url', surface.as_uri(),
                                 '--label', 'surface', '--out', str(self.root), '--wait', '0'],
                                env=self.env, capture_output=True, text=True)
        return result, json.loads((self.root / 'surface.json').read_text())

    def test_bitmap_canvas_background_and_hidden_text(self):
        result, data = self.capture('''<!doctype html><style>
          .back { width:320px;height:100px;background:url(bitmap.png) }
          .generated::before {content:'Production-only label'}
          </style><h1>Audience result</h1><img src="bitmap.png">
          <canvas width="320" height="100"></canvas><div class="back"></div>
          <div class="generated"></div><details><summary>More</summary><p>Hidden draft</p></details>
          <div hidden title="Invisible hint">Invisible</div>
          <script>const c=document.querySelector('canvas').getContext('2d');
          c.fillText('Another production instruction',10,30)</script>''')
        self.assertEqual(result.returncode, 0, result.stderr)
        texts = [item['text'] for item in data['elements']]
        self.assertIn('Audience result', texts)
        self.assertNotIn('Hidden draft', texts)
        self.assertNotIn('Invisible hint', texts)
        kinds = {item['kind'] for item in data.get('surfaces', [])}
        self.assertTrue({'img', 'canvas', 'background', 'generated'} <= kinds, kinds)
        self.assertTrue(all(item['w'] > 0 and item['h'] > 0 for item in data['surfaces']))
        self.assertEqual(data['captureState'], 'captured')
        summary = subprocess.run(['node', str(SCRIPTS / 'capture-surface.js'), '--show',
                                  str(self.root / 'surface.json')], env=self.env, capture_output=True, text=True)
        self.assertEqual(summary.returncode, 0, summary.stderr)
        self.assertGreaterEqual(json.loads(summary.stdout)['surfaces'], 4)

    def test_broken_image_is_incomplete(self):
        result, data = self.capture('<h1>Chart</h1><img src="missing.png" width="320" height="100">')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(data['captureState'], 'incomplete')
        self.assertEqual(len(data['brokenImages']), 1)

    def test_missing_embed_does_not_mutate_report(self):
        report = self.root / 'report.html'
        original = '<img src="__EMBED_F1__"><img src="__EMBED_F2__">'
        report.write_text(original)
        boxes = self.root / 'boxes.json'
        boxes.write_text(json.dumps([{'id':'F1','png':str(self.root / 'bitmap.png'), 'x':10,'y':10,'w':200,'h':40}]))
        result = subprocess.run([sys.executable, str(SCRIPTS / 'annotate-shot.py'), '--boxes', str(boxes),
                                 '--out', str(self.root / 'marked'), '--inject', str(report)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report.read_text(), original)

    def test_annotation_scaling_and_successful_injection(self):
        (self.root / 'bitmap.json').write_text(json.dumps({'viewport': {'width': 160}}))
        report = self.root / 'report.html'
        report.write_text('<img src="__EMBED_F1__"><img src="__EMBED_overview:bitmap__">')
        boxes = self.root / 'boxes.json'
        boxes.write_text(json.dumps([{'id':'F1', 'png':str(self.root / 'bitmap.png'),
                                      'x':5, 'y':10, 'w':80, 'h':20}]))
        result = subprocess.run([sys.executable, str(SCRIPTS / 'annotate-shot.py'), '--boxes', str(boxes),
                                 '--out', str(self.root / 'marked'), '--pad', '0',
                                 '--overview', str(self.root / 'bitmap.png'), '--inject', str(report)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('__EMBED_', report.read_text())
        self.assertEqual(report.read_text().count('data:image/png;base64,'), 2)
        with Image.open(self.root / 'marked' / 'F1.png') as marked:
            self.assertEqual(marked.size, (160, 40))
            self.assertEqual(marked.getpixel((0, 0)), (217, 45, 32))

    def test_http_error_is_not_target_evidence(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'<h1>Missing sample</h1>')

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run(['node', str(SCRIPTS / 'capture-surface.js'), '--url',
                                     f'http://127.0.0.1:{server.server_port}', '--label', 'error',
                                     '--out', str(self.root), '--wait', '0'],
                                    env=self.env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 3, result.stderr)
            data = json.loads((self.root / 'error.json').read_text())
            self.assertEqual(data['status'], 404)
            self.assertEqual(data['captureState'], 'incomplete')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_help_and_invalid_arguments(self):
        for script, runtime in [('capture-surface.js', 'node'), ('annotate-shot.py', sys.executable)]:
            for flag in ('--help', '-h'):
                result = subprocess.run([runtime, str(SCRIPTS / script), flag], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(['node', str(SCRIPTS / 'capture-surface.js'), '--url', 'file:///missing',
                                 '--label', 'sample', '--wait', 'NaN'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
