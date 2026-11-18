/* 验证只读报告的文字对照、折叠、窄屏和输入转义。 */
const { pathToFileURL } = require('node:url');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1100, height: 800 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pathToFileURL(process.argv[2]).href);
    await page.click('#expand-all');
    const cardsOpen = await page.locator('details.finding[open]').count();
    const detailsOpen = await page.locator('details.detail[open]').count();
    const original = await page.locator('.text-compare pre').first().textContent();
    const suggested = await page.locator('.text-compare pre').nth(1).textContent();
    const feedbackControls = await page.locator('select, textarea, .copy-feedback').count() > 0;
    const pending = await page.locator('.res-open').count();
    const sliders = await page.locator('.slider').count();
    await page.setViewportSize({ width: 390, height: 844 });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    const injected = await page.evaluate(() => Boolean(window.INJECTED));
    await page.click('#collapse-all');
    const open = await page.locator('details[open]').count();
    console.log(JSON.stringify({errors, cardsOpen, detailsOpen, original, suggested, feedbackControls,
                                pending, sliders, overflow, injected, open}));
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
