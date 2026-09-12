/* 浏览器驱动：输入报告路径、截图目录；输出交互截图和尺寸 JSON。
 * 用法：node compare-browser.cjs report.html /tmp/compare-shots
 *       node compare-browser.cjs --help
 * 依赖 PLAYWRIGHT_MODULE 或 NODE_PATH；失败退出 1，不修改报告。
 */
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
if (process.argv.includes('--help') || process.argv.includes('-h')) {
  console.log('Usage: node compare-browser.cjs <report.html> <output-dir>\nOutputs: interaction PNGs and JSON on stdout; failure exits 1.');
  process.exit(0);
}
(async () => {
  const [report, out] = process.argv.slice(2);
  if (!report || !out) throw new Error('Expected report path and screenshot directory');
  const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
  const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pathToFileURL(path.resolve(report)).href);
    await page.locator('.wipe img').evaluateAll(imgs => Promise.all(imgs.map(img => img.decode())));
    fs.mkdirSync(out, { recursive: true });
    const observations = [];
    const shot = async (name) => {
      await page.locator('.wipe').screenshot({ path: path.join(out, name + '.png') });
      observations.push({ name, box: await page.locator('.wipe').boundingBox(),
        value: await slider.inputValue(),
        leftLabel: await page.locator('.tag.l').isVisible() ? await page.locator('.tag.l').innerText() : null,
        rightLabel: await page.locator('.tag.r').isVisible() ? await page.locator('.tag.r').innerText() : null,
      });
    };
    const slider = page.locator('.slider');
    await slider.focus();
    await slider.press('Home');
    await shot('zero');
    await slider.press('End');
    await shot('hundred');
    await slider.fill('50');
    await shot('middle');
    // 鼠标操作中点，验证实际控件接线，而非只修改 DOM 数值。
    const box = await slider.boundingBox();
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    await shot('pointer');
    await page.locator('.side').check();
    const sideLabels = await page.locator('.sbs figcaption').allTextContents();
    const sideBox = await page.locator('.sbs').boundingBox();
    const sideImages = await page.locator('.sbs img').evaluateAll(imgs => imgs.map(img => {
      const r = img.getBoundingClientRect(); return { x:r.x, y:r.y, width:r.width, height:r.height };
    }));
    await page.locator('.sbs').screenshot({ path: path.join(out, 'side.png') });
    await page.setViewportSize({ width: 840, height: 760 });
    await page.locator('.side').uncheck();
    await shot('hidden-resize');
    await slider.focus();
    await slider.press('Home');
    await shot('hidden-resize-zero');
    await slider.press('End');
    await shot('hidden-resize-hundred');
    await slider.fill('50');
    await shot('hidden-resize-middle');
    await page.setViewportSize({ width: 1000, height: 800 });
    await shot('resize');
    await page.locator('.ruler').check();
    const rulersVisible = await page.locator('.rulers').isVisible();
    await page.locator('.rulers').screenshot({ path: path.join(out, 'rulers.png') });
    await page.locator('.ruler').uncheck();
    await shot('ruler-off');
    console.log(JSON.stringify({ observations, errors, rulersVisible, sideLabels, sideBox, sideImages,
      rulersHidden: !(await page.locator('.rulers').isVisible()),
      imagesDecoded: await page.locator('img').evaluateAll(imgs => imgs.every(img => img.complete && img.naturalWidth > 0)),
    }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
