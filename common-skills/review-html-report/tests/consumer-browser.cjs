/* 验证只读报告的文字对照、反馈复制、窄屏和输入转义。 */
const { pathToFileURL } = require('node:url');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1100, height: 800 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => {
      // 模拟无剪贴板权限，验证可复制文本框的兜底行为。
      Object.defineProperty(navigator, 'clipboard', { value: {
        writeText: async () => { throw new Error('clipboard denied'); }
      } });
    });
    await page.goto(pathToFileURL(process.argv[2]).href);
    await page.click('#expand-all');
    const original = await page.locator('.text-compare pre').first().textContent();
    const suggested = await page.locator('.text-compare pre').nth(1).textContent();
    await page.locator('.feedback-state').first().selectOption('accept');
    await page.locator('.copy-feedback').first().click();
    const single = await page.locator('#feedback-export').inputValue();
    await page.click('#copy-all');
    const all = await page.locator('#feedback-export').inputValue();
    const imageCount = await page.locator('.annotated img').count();
    await page.locator('img').evaluateAll(imgs => Promise.all(imgs.map(img => img.decode())));
    const pending = await page.locator('.res-open').count();
    const sliders = await page.locator('.slider').count();
    await page.setViewportSize({ width: 390, height: 844 });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    const injected = await page.evaluate(() => Boolean(window.INJECTED));
    await page.click('#collapse-all');
    const open = await page.locator('details[open]').count();
    console.log(JSON.stringify({errors, original, suggested, single, all, imageCount, pending, sliders, overflow, injected, open}));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
