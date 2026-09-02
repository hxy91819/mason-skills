#!/usr/bin/env node
/* 采集一个真实渲染面：全页截图 + 带文档坐标 bbox 的可见文本清单。
 *
 * bbox 用文档坐标（viewport 坐标 + 滚动量），这样可以直接从 fullPage 截图上裁剪，
 * 不需要为每条 finding 再跑一次浏览器。
 *
 * 用法：
 *   node capture-surface.js --url <URL> --label <名字> [--out <目录>]
 *                           [--viewport 1440x900] [--locale zh-CN]
 *                           [--cookie name=value;domain=host] [--wait 8000]
 *
 * 产物：<out>/<label>.png（全页截图）、<out>/<label>.json（元素清单）
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
  const out = { out: '/tmp/spec-leak-shots', viewport: '1440x900', locale: 'zh-CN', wait: 8000, cookie: [] };
  const a = process.argv.slice(2);
  for (let i = 0; i < a.length; i += 2) {
    const k = a[i].replace(/^--/, '');
    const v = a[i + 1];
    if (k === 'cookie') out.cookie.push(v);
    else if (k === 'wait') out.wait = Number(v);
    else out[k] = v;
  }
  if (!out.url || !out.label) {
    console.error('必须提供 --url 和 --label');
    process.exit(2);
  }
  return out;
}

// 只取节点自身的直接文本，避免父子层层重复；坐标转成文档坐标供裁剪使用。
const DUMP = () => {
  const out = [];
  let seq = 0;
  const walk = (el) => {
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return;
    const own = Array.from(el.childNodes)
      .filter((n) => n.nodeType === 3)
      .map((n) => n.textContent.replace(/\s+/g, ' ').trim())
      .filter(Boolean)
      .join(' ');
    if (own) {
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
      if (!text) continue;
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

  return {
    url: location.href,
    title: document.title,
    scrollHeight: document.documentElement.scrollHeight,
    dpr: window.devicePixelRatio,
    elements: out,
  };
};

(async () => {
  const opt = args();
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

  const png = path.join(opt.out, `${opt.label}.png`);
  await page.screenshot({ path: png, fullPage: true });
  const dump = await page.evaluate(DUMP);
  const meta = { label: opt.label, requested: opt.url, status, navError, failures, viewport: { width, height }, ...dump };
  fs.writeFileSync(path.join(opt.out, `${opt.label}.json`), JSON.stringify(meta, null, 1));

  // 导航失败时页面停在浏览器错误页，此时截图和清单都不能当作被审界面的证据。
  const landedOnError = /^chrome-error:/.test(dump.url);
  console.log(JSON.stringify({
    label: opt.label, status, navError, landedOnError,
    finalUrl: dump.url, title: dump.title,
    elements: dump.elements.length, png,
    json: path.join(opt.out, `${opt.label}.json`),
    failures: failures.slice(0, 5),
  }, null, 1));

  await browser.close();
  if (landedOnError || navError) process.exit(3);
})().catch((e) => { console.error('FAIL', e.message); process.exit(1); });
