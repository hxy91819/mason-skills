#!/usr/bin/env node
/* 采集一个真实渲染面：全页截图 + 文本清单 + 需看图盘点的图像/绘制面清单。
 *
 * bbox 用文档坐标（viewport 坐标 + 滚动量），这样可以直接从 fullPage 截图上裁剪，
 * 不需要为每条 finding 再跑一次浏览器。
 *
 * 用法：
 *   node capture-surface.js --url <URL> --label <名字> [--out <目录>]
 *                           [--viewport 1440x900] [--locale zh-CN]
 *                           [--cookie name=value;domain=host] [--wait 8000]
 *
 *   node capture-surface.js --show /tmp/spec-leak-shots/page.json
 * 产物：<out>/<label>.png、<out>/<label>.json，stdout 打印采集摘要；--show 只读聚合。
 * 退出码：0 成功采集（不代表审查通过）；2 参数错误；3 页面/资源采集不完整；1 其他错误。
 */
const fs = require('fs');
const path = require('path');

function loadPlaywright() {
  const candidates = [
    process.env.PLAYWRIGHT_MODULE,
    'playwright',
    'playwright-core',
  ].filter(Boolean);
  for (const id of candidates) {
    try { return require(id); } catch { /* 继续找 */ }
  }
  // 常见的全局安装位置：npm 全局根目录下的几种打包形态。
  let globalRoot = null;
  try {
    globalRoot = require('child_process').execSync('npm root -g', { encoding: 'utf8' }).trim();
  } catch { /* 无 npm 也继续 */ }
  if (globalRoot) {
    const globs = [
      'playwright', 'playwright-core',
      '@playwright/test/node_modules/playwright-core',
      '@playwright/cli/node_modules/playwright-core',
    ];
    for (const rel of globs) {
      const p = path.join(globalRoot, rel);
      try { if (fs.existsSync(p)) return require(p); } catch { /* 继续找 */ }
    }
  }
  throw new Error(
    'playwright 不可用。安装 playwright 或用 PLAYWRIGHT_MODULE 指向模块路径后重跑；' +
    '拿不到浏览器时不要伪造截图，按 SKILL.md 记为覆盖范围限制。'
  );
}

function args() {
  if (process.argv.includes('--help') || process.argv.includes('-h')) {
    console.log(`Usage: node capture-surface.js --url <URL> --label <name> [options]
采集真实页面的截图、文本和非 DOM 文本绘制面；不执行语义审查或 OCR。
Options:
  --out <dir>           输出目录，默认 /tmp/spec-leak-shots
  --viewport <WxH>      CSS 视口，默认 1440x900
  --locale <locale>     默认 zh-CN
  --wait <ms>           导航后等待，默认 8000，允许 0
  --cookie <spec>       可重复，格式 'name=value;domain=host;path=/'
  --show <capture.json> 只读输出现有采集的覆盖线索，不启动浏览器
  -h, --help           显示帮助
Outputs: <out>/<label>.png/json；stdout JSON 摘要。0 成功；2 参数错误；3 采集不完整；1 其他错误。
Examples:
  node capture-surface.js --url http://localhost:8000 --label home --wait 0
  node capture-surface.js --show /tmp/spec-leak-shots/home.json`);
    process.exit(0);
  }
  const out = { out: '/tmp/spec-leak-shots', viewport: '1440x900', locale: 'zh-CN', wait: 8000, cookie: [] };
  const fail = (message) => { console.error(message); process.exit(2); };
  const a = process.argv.slice(2);
  for (let i = 0; i < a.length; i += 2) {
    const k = a[i].replace(/^--/, '');
    const v = a[i + 1];
    if (!['url', 'label', 'out', 'viewport', 'locale', 'wait', 'cookie', 'show'].includes(k) || v === undefined || v.startsWith('--')) {
      fail(`未知参数或缺少值：${a[i]}；使用 --help 查看用法`);
    }
    if (k === 'cookie') out.cookie.push(v);
    else if (k === 'wait') out.wait = Number(v);
    else out[k] = v;
  }
  if (out.show) return out;
  if (!out.url || !out.label) fail('必须提供 --url 和 --label');
  if (!/^[\w.-]+$/.test(out.label) || ['.', '..'].includes(out.label)) fail('--label 只能是文件名，不含路径');
  if (!/^\d+x\d+$/.test(out.viewport) || out.viewport.split('x').some(v => Number(v) < 1)) fail('--viewport 应为正整数 WxH');
  if (!Number.isFinite(out.wait) || out.wait < 0) fail('--wait 必须是非负毫秒数');
  if (out.cookie.some(v => !/^[^=;]+=[^;]*;.*\bdomain=[^;]+/.test(v))) fail('--cookie 需要 name=value;domain=host');
  return out;
}

// 只取节点自身的直接文本，避免父子层层重复；坐标转成文档坐标供裁剪使用。
const DUMP = () => {
  const out = [];
  const surfaces = [];
  let seq = 0;
  const visible = el => el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true }) &&
    el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0;
  const box = el => {
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x + scrollX), y: Math.round(r.y + scrollY), w: Math.round(r.width), h: Math.round(r.height) };
  };
  const walk = (el) => {
    const st = getComputedStyle(el);
    const own = Array.from(el.childNodes)
      .filter((n) => n.nodeType === 3)
      .map((n) => n.textContent.replace(/\s+/g, ' ').trim())
      .filter(Boolean)
      .join(' ');
    if (own && visible(el)) {
      const r = el.getBoundingClientRect();
      out.push({
        id: `t${++seq}`,
        kind: 'visible',
        tag: el.tagName.toLowerCase(),
        text: own,
        x: Math.round(r.x + window.scrollX),
        y: Math.round(r.y + window.scrollY),
        w: Math.round(r.width),
        h: Math.round(r.height),
        fontSize: st.fontSize,
        inDetails: el.closest('details') !== null,
      });
    }
    for (const c of el.children) walk(c);
  };
  walk(document.body);

  // 不在文本节点里但同样对用户可见的文案。
  const extra = (sel, attr, kind) => {
    for (const el of document.querySelectorAll(sel)) {
      const text = el.getAttribute(attr);
      if (!text || !visible(el)) continue;
      const r = el.getBoundingClientRect();
      out.push({
        id: `t${++seq}`, kind, tag: el.tagName.toLowerCase(), text,
        x: Math.round(r.x + window.scrollX), y: Math.round(r.y + window.scrollY),
        w: Math.round(r.width), h: Math.round(r.height),
        fontSize: getComputedStyle(el).fontSize, inDetails: el.closest('details') !== null,
      });
    }
  };
  extra('[placeholder]', 'placeholder', 'placeholder');
  extra('[title]', 'title', 'tooltip');
  extra('[aria-label]', 'aria-label', 'a11y');

  // 这里只登记绘制面，不把 alt/DOM 文字当作位图内文；审查者仍须打开截图逐区域读取。
  for (const el of [document.body, ...document.body.querySelectorAll('*')]) {
    if (!visible(el)) continue;
    const tag = el.tagName.toLowerCase();
    const addSurface = (kind, source = '') => surfaces.push({
      id: `s${surfaces.length + 1}`, kind, tag, ...box(el),
      source: source.startsWith('data:') ? 'embedded data URI' : source,
    });
    if (['img', 'canvas', 'svg', 'iframe', 'object', 'embed', 'video'].includes(tag)) {
      addSurface(tag, el.currentSrc || el.getAttribute('src') || el.getAttribute('data') || '');
    }
    if (getComputedStyle(el).backgroundImage !== 'none') addSurface('background');
    for (const pseudo of ['::before', '::after']) {
      const style = getComputedStyle(el, pseudo);
      if ((style.content && !['none', 'normal', '""'].includes(style.content)) || style.backgroundImage !== 'none') {
        addSurface('generated', pseudo);
      }
    }
  }

  return {
    url: location.href,
    title: document.title,
    scrollHeight: document.documentElement.scrollHeight,
    dpr: window.devicePixelRatio,
    elements: out,
    surfaces,
  };
};

function summary(meta) {
  return { label: meta.label, captureState: meta.captureState || 'unknown',
    elements: (meta.elements || []).length, surfaces: (meta.surfaces || []).length,
    brokenImages: (meta.brokenImages || []).length, failures: (meta.failures || []).length,
    visualReview: '未由采集工具判断；请查单轮逐页看图记录' };
}

(async () => {
  const opt = args();
  if (opt.show) {
    console.log(JSON.stringify(summary(JSON.parse(fs.readFileSync(opt.show, 'utf8'))), null, 1));
    return;
  }
  const { chromium } = loadPlaywright();
  const [width, height] = opt.viewport.split('x').map(Number);
  fs.mkdirSync(opt.out, { recursive: true });

  const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  const ctx = await browser.newContext({ viewport: { width, height }, locale: opt.locale });

  for (const spec of opt.cookie) {
    const [pair, ...rest] = spec.split(';');
    const eq = pair.indexOf('=');
    const meta = Object.fromEntries(rest.map((s) => {
      const i = s.indexOf('=');
      return [s.slice(0, i).trim(), s.slice(i + 1).trim()];
    }));
    await ctx.addCookies([{
      name: pair.slice(0, eq).trim(),
      value: pair.slice(eq + 1).trim(),
      domain: meta.domain,
      path: meta.path || '/',
      httpOnly: true,
      secure: false,
    }]);
  }

  const page = await ctx.newPage();
  page.setDefaultTimeout(90000);
  const failures = [];
  page.on('requestfailed', (r) => {
    const t = r.failure() && r.failure().errorText;
    if (!/ERR_ABORTED/.test(t || '')) failures.push({ url: r.url(), error: t });
  });

  let status = null;
  let navError = null;
  try {
    const resp = await page.goto(opt.url, { waitUntil: 'domcontentloaded', timeout: 90000 });
    status = resp && resp.status();
  } catch (e) {
    navError = e.message.split('\n')[0];
  }
  await page.waitForTimeout(opt.wait);
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all([...document.images].map(img => img.decode().catch(() => {})));
  });
  const brokenImages = await page.evaluate(() => [...document.images]
    .filter(img => !img.complete || img.naturalWidth === 0)
    .map(img => ({ src: img.currentSrc || img.getAttribute('src'), alt: img.alt })));

  const png = path.join(opt.out, `${opt.label}.png`);
  await page.screenshot({ path: png, fullPage: true });
  const dump = await page.evaluate(DUMP);
  const landedOnError = /^chrome-error:/.test(dump.url);
  const incomplete = landedOnError || navError || status >= 400 || brokenImages.length || failures.length;
  const meta = { label: opt.label, requested: opt.url, status, navError, failures, brokenImages,
    captureState: incomplete ? 'incomplete' : 'captured', viewport: { width, height }, ...dump };
  fs.writeFileSync(path.join(opt.out, `${opt.label}.json`), JSON.stringify(meta, null, 1));

  // 导航失败时页面停在浏览器错误页，此时截图和清单都不能当作被审界面的证据。
  console.log(JSON.stringify({
    ...summary(meta),
    label: opt.label, status, navError, landedOnError,
    finalUrl: dump.url, title: dump.title,
    elements: dump.elements.length, png,
    json: path.join(opt.out, `${opt.label}.json`),
    failures: failures.slice(0, 5),
  }, null, 1));

  await browser.close();
  if (incomplete) process.exit(3);
})().catch((e) => { console.error('FAIL', e.message); process.exit(1); });
