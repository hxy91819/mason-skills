#!/usr/bin/env python3
"""生成供独立行为评估使用的两份合成幻灯片，全部文字、记录和位图在此定义。

参数：--out 必填，指定临时产物目录。依赖 Pillow；不读取用户项目、不联网。
输出：case-a.html、case-b.html、sample-audit.png；stdout 输出目录。成功 0，参数错误 2。
示例：
  python3 make-review-fixtures.py --out /tmp/review-cases
  python3 make-review-fixtures.py --out /tmp/review-cases-second-run
生成物不是测试断言，也不代表新版技能已通过独立行为评估。
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

STYLE = '''
* {box-sizing:border-box} body {margin:0;background:#e6e9ef;font-family:Arial,sans-serif}
.slide {position:relative;width:1280px;height:720px;overflow:hidden;background:#fafcfb;color:#12332d}
h1,p {margin:0} .eyebrow {font-size:20px;letter-spacing:3px;color:#47716b}
'''


def generate(out):
    out.mkdir(parents=True, exist_ok=True)
    img = Image.new('RGB', (1000, 420), '#f4f8ff')
    draw = ImageDraw.Draw(img)
    title = ImageFont.truetype('DejaVuSans.ttf', 38)
    text = ImageFont.truetype('DejaVuSans.ttf', 28)
    draw.text((36, 28), 'Sample release A-17 / approval record', fill='#133247', font=title)
    draw.line((36, 100, 964, 100), fill='#adc4d6', width=2)
    for y, line in [(126, 'Build checks: passed'), (178, 'Decision: HOLD - owner approval is still required'),
                    (230, 'Accessibility verification: pending'),
                    (318, 'Production note: choose a shorter row for the demo')]:
        draw.text((36, y), line, fill='#173347', font=text)
    img.save(out / 'sample-audit.png')
    cases = {
        'case-a': '''<section class="slide active" id="slide-1">
          <p class="eyebrow" style="position:absolute;left:60px;top:28px">RELEASE UPDATE</p>
          <h1 style="position:absolute;left:60px;top:66px;font-size:44px">Ready for publication</h1>
          <p style="position:absolute;left:60px;top:128px;font-size:24px">The review is complete. The record confirms approval.</p>
          <figure style="position:absolute;left:930px;top:25px;margin:0;width:230px">
            <img src="sample-audit.png" alt="Release approval record" style="width:200px;display:block">
            <figcaption style="font-size:16px;margin-top:8px">Approval completed</figcaption>
          </figure>
          <p style="position:absolute;left:60px;top:174px;font-size:19px;color:#536b70">制作安排：演示前换成更短的结论，补齐本页截图。</p>
          <span style="position:absolute;left:60px;bottom:30px;font-size:20px">Sample product team</span>
        </section>''',
        'case-b': '''<section class="slide active" id="slide-1">
          <p class="eyebrow" style="position:absolute;left:84px;top:92px">WORKSPACE PREVIEW</p>
          <h1 style="position:absolute;left:84px;top:224px;font-size:64px;line-height:1.12;width:840px">Preview first.<br>Publish with approval.</h1>
          <p style="position:absolute;left:88px;top:458px;font-size:28px;line-height:1.45;width:840px">Previewing does not change shared records.<br>Only a workspace owner can approve publication.</p>
          <div aria-hidden="true" style="position:absolute;right:-210px;top:90px;width:560px;height:560px;border:60px solid #d6ebe4;border-radius:50%"></div>
          <span style="position:absolute;left:88px;bottom:44px;font-size:20px;color:#47716b">Sample product onboarding</span>
        </section>''',
    }
    for name, body in cases.items():
        (out / (name + '.html')).write_text(
            '<!doctype html><html lang="en"><meta charset="utf-8"><title>Sample deck</title>'
            '<style>' + STYLE + '</style><body>' + body + '</body></html>', encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', type=Path, required=True, help='生成 HTML 与 PNG 的临时目录')
    args = ap.parse_args()
    try:
        generate(args.out)
    except OSError as error:
        ap.error(str(error))
    print(args.out.resolve())


if __name__ == '__main__':
    main()
