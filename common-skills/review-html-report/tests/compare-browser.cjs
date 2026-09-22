/* 浏览器驱动：输入报告路径、截图目录；输出交互截图和尺寸 JSON。
 * 用法：node compare-browser.cjs report.html /tmp/compare-shots
 *       node compare-browser.cjs --help
 * 覆盖：默认折叠状态、工具栏全部展开、对照滑块（键盘/点击/图内拖动）、并排、
 *       resize、红框标注几何与标签。
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
    // 折叠是默认态：任何 details 都不应预先展开。
    const detailsTotal = await page.locator('details').count();
    const closedInitially = await page.locator('details:not([open])').count();
    const openInitially = detailsTotal - closedInitially;
    // 工具栏展开，而不是直接改 DOM，验证按钮接线。
    await page.click('#expand-all');
    const openAfterExpand = await page.locator('details[open]').count();
    await page.locator('img').evaluateAll(imgs => Promise.all(imgs.map(img => img.decode())));
    fs.mkdirSync(out, { recursive: true });
    const result = { errors, detailsTotal, closedInitially, openInitially, openAfterExpand, observations: [] };
    const slider = page.locator('.slider').first();
    if (await slider.count()) {
      const shot = async (name) => {
        await page.locator('.wipe').first().screenshot({ path: path.join(out, name + '.png') });
        result.observations.push({ name, box: await page.locator('.wipe').first().boundingBox(),
          value: await slider.inputValue(),
          leftLabel: await page.locator('.tag.l').first().isVisible() ? await page.locator('.tag.l').first().innerText() : null,
          rightLabel: await page.locator('.tag.r').first().isVisible() ? await page.locator('.tag.r').first().innerText() : null,
        });
      };
      await slider.focus();
      await slider.press('Home');
      await shot('zero');
      await slider.press('End');
      await shot('hundred');
      await slider.fill('50');
      await shot('middle');
      // 鼠标操作中点，验证实际控件接线，而非只修改 DOM 数值。
      const rangeBox = await slider.boundingBox();
      await page.mouse.click(rangeBox.x + rangeBox.width / 2, rangeBox.y + rangeBox.height / 2);
      await shot('pointer');
      // 图框内直接拖动竖条到 70% 处。
      const wipeBox = await page.locator('.wipe').first().boundingBox();
      const dragX = wipeBox.x + wipeBox.width * 0.7;
      await page.mouse.move(dragX, wipeBox.y + wipeBox.height / 2);
      await page.mouse.down();
      await page.mouse.move(dragX + 2, wipeBox.y + wipeBox.height / 2, { steps: 2 });
      await page.mouse.up();
      result.dragValue = Number(await slider.inputValue());
      await shot('drag');
      const side = page.locator('.side').first();
      await side.check();
      result.sideLabels = await page.locator('.sbs figcaption').allTextContents();
      const sideBox = await page.locator('.sbs').first().boundingBox();
      const sideImages = await page.locator('.sbs img').evaluateAll(imgs => imgs.map(img => {
        const r = img.getBoundingClientRect(); return { x:r.x, y:r.y, width:r.width, height:r.height };
      }));
      await page.locator('.sbs').first().screenshot({ path: path.join(out, 'side.png') });
      await side.uncheck();
      await page.setViewportSize({ width: 840, height: 760 });
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
      result.sideBox = sideBox;
      result.sideImages = sideImages;
    }
    const rbox = page.locator('.rbox').first();
    if (await rbox.count()) {
      const figure = page.locator('.annotated').first();
      const imgBox = await figure.locator('img').boundingBox();
      const box = await rbox.boundingBox();
      await figure.screenshot({ path: path.join(out, 'annotated.png') });
      result.annotation = {
        rlabel: await page.locator('.rlabel').first().innerText(),
        // 相对标注图左上角的分数坐标，供像素断言使用。
        rel: {
          x: (box.x - imgBox.x) / imgBox.width,
          y: (box.y - imgBox.y) / imgBox.height,
          w: box.width / imgBox.width,
          h: box.height / imgBox.height,
        },
        insideImage: box.x >= imgBox.x - 2 && box.y >= imgBox.y - 2
          && box.x + box.width <= imgBox.x + imgBox.width + 2
          && box.y + box.height <= imgBox.y + imgBox.height + 2,
      };
    }
    result.imagesDecoded = await page.locator('img').evaluateAll(imgs => imgs.every(img => img.complete && img.naturalWidth > 0));
    console.log(JSON.stringify(result));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });