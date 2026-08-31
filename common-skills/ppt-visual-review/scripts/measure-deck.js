#!/usr/bin/env node
/* 量一份 PPT 式 HTML 每页的版面几何：块间间隔、页边距、剩余留白、并排列的对齐。
 *
 * 量的是「视觉盒」，不是布局盒，两处修正决定了结论对不对：
 *   1. 硬投影（box-shadow 的偏移与扩散）和 transform 旋转把元素的视觉边缘推到布局盒外，
 *      只量 offsetTop 会把「5px 投影 + 25px 间隔」和「无投影 + 30px 间隔」判成同一个值，
 *      而人眼看到的是 25 和 30。
 *   2. 没有背景/边框/投影/自有文本的透明容器，它的盒子不是眼睛看到的边缘；
 *      这种容器取子孙绘制并集（paintBox）。固定高度的透明包裹层最容易骗过测量。
 *
 * 剩余留白（slack）反过来必须对布局盒量：容器内容盒底边减去最后一个子块的视觉底边，
 * 这样只有被撑开或绝对定位的容器才会报留白，随内容长高的容器天然为 0。
 *
 * 用法：
 *   node measure-deck.js --file <html> [--out <目录>] [--label before]
 *        [--slide-sel .slide] [--tol 2] [--slack 24] [--shot] [--gate]
 *   浏览器模块用 NODE_PATH 或 PLAYWRIGHT_MODULE 指向装了 playwright 的 node_modules。
 *
 * 产物：
 *   <out>/<label>.json            每页几何 + flags（判定线索，不是结论）
 *   <out>/<label>-<页id>.png      每页真实渲染截图（--shot）
 *   <out>/<label>-<页id>-ruler.png 同页叠加间隔标尺与留白网格（--shot）
 *
 * 退出码：0 正常；1 脚本错误；3 选择器没命中可测的页；4 --gate 且仍有 flag。
 */
'use strict';

const fs = require('fs');
const path = require('path');

function loadPlaywright() {
  const ids = [process.env.PLAYWRIGHT_MODULE, 'playwright', 'playwright-core'].filter(Boolean);
  for (const id of ids) {
    try { return require(id); } catch { /* 继续找 */ }
  }
  let globalRoot = null;
  try {
    globalRoot = require('child_process').execSync('npm root -g', { encoding: 'utf8' }).trim();
  } catch { /* 无 npm 也继续 */ }
  for (const rel of ['playwright', 'playwright-core', '@playwright/test/node_modules/playwright-core']) {
    if (!globalRoot) break;
    const p = path.join(globalRoot, rel);
    try { if (fs.existsSync(p)) return require(p); } catch { /* 继续找 */ }
  }
  throw new Error('playwright 不可用：用 NODE_PATH 或 PLAYWRIGHT_MODULE 指向装了 playwright 的 node_modules 后重跑');
}

function parseArgs() {
  const o = {
    out: '/tmp/ppt-visual-review', label: 'before', slideSel: '.slide',
    ignoreSel: '.sr-only', tol: 2, slack: 24, near: 6, minGap: 8, minSpan: 0.3,
    viewport: '1600x900', shot: false, gate: false,
  };
  const a = process.argv.slice(2);
  for (let i = 0; i < a.length; i++) {
    const k = a[i].replace(/^--/, '');
    if (k === 'shot' || k === 'gate') { o[k] = true; continue; }
    const v = a[++i];
    if (k === 'slide-sel') o.slideSel = v;
    else if (k === 'ignore-sel') o.ignoreSel = v;
    else if (['tol', 'slack', 'near', 'minSpan', 'min-span', 'min-gap'].includes(k)) {
      o[{ 'min-span': 'minSpan', 'min-gap': 'minGap' }[k] || k] = Number(v);
    }
    else o[k] = v;
  }
  if (!o.file && !o.url) { console.error('必须提供 --file 或 --url'); process.exit(2); }
  return o;
}

/* ---------------- 页内测量 ---------------- */

const MEASURE = ({ slideSel, idx, ignoreSel, minSpan, overlapTol }) => {
  const R = (v) => Math.round(v * 10) / 10;
  const num = (v) => (parseFloat(v) || 0);
  const slide = document.querySelectorAll(slideSel)[idx];
  const sr = slide.getBoundingClientRect();
  const scale = slide.offsetWidth ? sr.width / slide.offsetWidth : 1;
  const W = slide.offsetWidth || Math.round(sr.width);
  const H = slide.offsetHeight || Math.round(sr.height);
  const Lx = (v) => (v - sr.left) / scale;
  const Ly = (v) => (v - sr.top) / scale;

  const visible = (el) => {
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden' || num(st.opacity) === 0) return false;
    if (ignoreSel && el.matches(ignoreSel)) return false;
    const r = el.getBoundingClientRect();
    return r.width * r.height > 16;
  };

  // 硬投影推出的视觉外扩；模糊投影按半径一半折算（模糊边缘的观感中点）。
  const grow = (el) => {
    const out = { t: 0, r: 0, b: 0, l: 0 };
    const bs = getComputedStyle(el).boxShadow;
    if (!bs || bs === 'none') return out;
    for (const layer of bs.split(/,(?![^(]*\))/)) {
      if (/inset/.test(layer)) continue;
      const nums = (layer.replace(/\([^)]*\)/g, '()').match(/-?[\d.]+px/g) || []).map(parseFloat);
      const ox = nums[0] || 0, oy = nums[1] || 0, blur = nums[2] || 0, spread = nums[3] || 0;
      const pad = spread + blur / 2;
      out.r = Math.max(out.r, ox + pad); out.l = Math.max(out.l, pad - ox);
      out.b = Math.max(out.b, oy + pad); out.t = Math.max(out.t, pad - oy);
    }
    return out;
  };

  const vbox = (el) => {
    const r = el.getBoundingClientRect();
    const g = grow(el);
    return {
      left: R(Lx(r.left) - g.l), right: R(Lx(r.right) + g.r),
      top: R(Ly(r.top) - g.t), bottom: R(Ly(r.bottom) + g.b),
    };
  };

  // 元素自己画了东西才算视觉边缘：背景、边框、投影，或直接挂着文本。
  const painted = (el) => {
    const cs = getComputedStyle(el);
    if (cs.backgroundImage !== 'none') return true;
    if (cs.backgroundColor && !/^rgba\(0, 0, 0, 0\)$|^transparent$/.test(cs.backgroundColor)) return true;
    if (['borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth'].some((k) => num(cs[k]) > 0)) return true;
    if (cs.boxShadow && cs.boxShadow !== 'none') return true;
    return [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
  };

  const paintBox = (el) => {
    if (painted(el)) return vbox(el);
    const kids = [...el.children].filter(visible);
    if (!kids.length) return vbox(el);
    const bs = kids.map(paintBox);
    return {
      left: R(Math.min(...bs.map((b) => b.left))), right: R(Math.max(...bs.map((b) => b.right))),
      top: R(Math.min(...bs.map((b) => b.top))), bottom: R(Math.max(...bs.map((b) => b.bottom))),
    };
  };

  const contentBox = (el) => {
    const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    return {
      top: R(Ly(r.top) + num(cs.borderTopWidth) + num(cs.paddingTop)),
      bottom: R(Ly(r.bottom) - num(cs.borderBottomWidth) - num(cs.paddingBottom)),
      left: R(Lx(r.left) + num(cs.borderLeftWidth) + num(cs.paddingLeft)),
      right: R(Lx(r.right) - num(cs.borderRightWidth) - num(cs.paddingRight)),
      pad: [num(cs.paddingTop), num(cs.paddingRight), num(cs.paddingBottom), num(cs.paddingLeft)].map(R),
    };
  };

  const sig = (el) => {
    const cls = (typeof el.className === 'string' && el.className.trim()) ? '.' + el.className.trim().split(/\s+/)[0] : '';
    return el.tagName.toLowerCase() + cls;
  };
  const pathOf = (el) => {
    const parts = [];
    let e = el;
    while (e && e !== document.body) {
      if (e.id) { parts.unshift('#' + e.id); break; }
      let s = sig(e);
      const sibs = e.parentElement ? [...e.parentElement.children].filter((c) => sig(c) === s) : [e];
      if (sibs.length > 1) s += `:n${sibs.indexOf(e) + 1}`;
      parts.unshift(s);
      e = e.parentElement;
    }
    return parts.join('>');
  };

  const stacks = [], rows = [];
  const walk = (el) => {
    const kids = [...el.children].filter(visible);
    if (kids.length >= 2) {
      const items = kids.map((k) => ({ sel: pathOf(k), ...paintBox(k) })).sort((a, b) => a.top - b.top);
      const own = paintBox(el);
      if (own.right - own.left >= W * minSpan) {
        const stacked = items.every((cur, i) => i === 0 || cur.top >= items[i - 1].bottom - overlapTol);
        const inner = contentBox(el);
        if (stacked) {
          stacks.push({
            sel: pathOf(el), box: own, inner, items,
            paintedSelf: painted(el), isRoot: el === slide,
            gaps: items.slice(1).map((b, i) => ({
              from: items[i].sel, to: b.sel, gap: R(b.top - items[i].bottom),
              y0: items[i].bottom, y1: b.top,
              x0: Math.max(items[i].left, b.left), x1: Math.min(items[i].right, b.right),
            })),
            slackTop: R(items[0].top - inner.top),
            slackBottom: R(inner.bottom - items[items.length - 1].bottom),
          });
        } else {
          const cols = [...items].sort((a, b) => a.left - b.left);
          const bottoms = cols.map((c) => c.bottom), tops = cols.map((c) => c.top);
          rows.push({
            sel: pathOf(el), box: own, inner, cols,
            align: getComputedStyle(el).alignItems,
            heightRatio: R((own.bottom - own.top) / H),
            topSpread: R(Math.max(...tops) - Math.min(...tops)),
            bottomSpread: R(Math.max(...bottoms) - Math.min(...bottoms)),
            hgaps: cols.slice(1).map((c, i) => R(c.left - cols[i].right)),
          });
        }
      }
    }
    for (const k of kids) walk(k);
  };
  walk(slide);

  const all = [...slide.querySelectorAll('*')].filter(visible).map(vbox);
  const frame = all.length ? {
    left: R(Math.min(...all.map((b) => b.left))),
    right: R(W - Math.max(...all.map((b) => b.right))),
    top: R(Math.min(...all.map((b) => b.top))),
    bottom: R(H - Math.max(...all.map((b) => b.bottom))),
  } : null;

  return { id: slide.id || `slide-${idx + 1}`, index: idx, width: W, height: H, scale: R(scale), frame, stacks, rows };
};

/* ---------------- 标尺叠加 ---------------- */

const OVERLAY = ({ slideSel, idx, draws }) => {
  const slide = document.querySelectorAll(slideSel)[idx];
  const layer = document.createElement('div');
  layer.id = '__pvr_ruler';
  layer.setAttribute('style', 'position:absolute;inset:0;z-index:9999;pointer-events:none;font:800 13px/1 ui-monospace,SFMono-Regular,Menlo,monospace;');
  const add = (css, text) => {
    const d = document.createElement('div');
    d.setAttribute('style', 'position:absolute;' + css);
    if (text) d.textContent = text;
    layer.appendChild(d);
  };
  for (const it of draws) {
    const w = Math.max(1, it.x1 - it.x0), h = Math.max(1, it.y1 - it.y0);
    if (it.type === 'gap') {
      add(`left:${it.x0}px;top:${it.y0}px;width:${w}px;height:${h}px;background:rgba(214,31,105,.34);outline:1px solid #d61f69;`);
      add(`left:${it.x0 + w / 2 - 28}px;top:${it.y0 + h / 2 - 9}px;width:56px;height:18px;background:#d61f69;color:#fff;text-align:center;line-height:18px;`, it.label);
    } else if (it.type === 'slack') {
      add(`left:${it.x0}px;top:${it.y0}px;width:${w}px;height:${h}px;background:repeating-linear-gradient(45deg,rgba(29,78,216,.30) 0 8px,rgba(29,78,216,.10) 8px 16px);outline:2px dashed #1d4ed8;`);
      add(`left:${it.x0 + 6}px;top:${it.y0 + 6}px;height:18px;padding:0 6px;background:#1d4ed8;color:#fff;line-height:18px;`, it.label);
    } else if (it.type === 'line') {
      add(`left:${it.x0}px;top:${it.y0}px;width:${w}px;height:2px;background:#047857;`);
      add(`left:${it.x0}px;top:${it.y0 + 4}px;height:18px;padding:0 6px;background:#047857;color:#fff;line-height:18px;`, it.label);
    } else if (it.type === 'box') {
      add(`left:${it.x0}px;top:${it.y0}px;width:${w}px;height:${h}px;outline:2px dashed rgba(4,120,87,.75);`);
      if (it.label) add(`left:${it.x0}px;top:${it.y0 - 22}px;height:18px;padding:0 6px;background:#047857;color:#fff;line-height:18px;`, it.label);
    }
  }
  slide.appendChild(layer);
};

/* ---------------- flags ---------------- */

const median = (xs) => {
  if (!xs.length) return 0;
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const norm = (sel) => sel.replace(/^#[^>]*>?/, '') || 'slide-root';
const r1 = (v) => Math.round(v * 10) / 10;

function buildFlags(pages, o) {
  const flags = [];
  let n = 0;
  const push = (f) => { flags.push({ id: `V${++n}`, ...f }); };

  // 同一区块内的节奏：一组兄弟块之间的间隔不该有肉眼可见的极差。
  // 只看真正当分隔用的间隔（≥12px）；行内文字的行距差异不是版式问题。
  for (const p of pages) {
    for (const st of p.stacks) {
      const gs = st.gaps.filter((g) => g.gap > 0.5);
      if (gs.length < 2) continue;
      const vals = gs.map((g) => g.gap);
      if (Math.max(...vals) < 12) continue;
      const spread = r1(Math.max(...vals) - Math.min(...vals));
      if (spread > o.tol) {
        push({
          kind: 'rhythm', page: p.id, sel: st.sel, spread,
          detail: `同一容器内块间隔 ${vals.join(' / ')}px，极差 ${spread}px`,
          values: vals,
          draws: gs.map((g) => ({ type: 'gap', x0: g.x0, x1: g.x1, y0: g.y0, y1: g.y1, label: String(g.gap) })),
        });
      }
    }
  }

  // 跨页节奏：同一角色的容器（去掉页 id 的路径）在每页要给出同一个间隔。
  const byRole = new Map();
  for (const p of pages) {
    for (const st of p.stacks) {
      const key = norm(st.sel);
      if (!byRole.has(key)) byRole.set(key, []);
      byRole.get(key).push({ page: p.id, st });
    }
  }
  for (const [role, list] of byRole) {
    if (list.length < 2) continue;
    const per = list.map(({ page, st }) => ({ page, med: r1(median(st.gaps.map((g) => g.gap).filter((v) => v > 0.5))), st }));
    const meds = per.map((x) => x.med).filter((v) => v > 0);
    if (meds.length < 2) continue;
    const spread = r1(Math.max(...meds) - Math.min(...meds));
    if (spread > o.tol) {
      push({
        kind: 'cross-page', page: per.map((x) => x.page).join(','), sel: role, spread,
        detail: `同角色容器 ${role} 的间隔各页不同：${per.map((x) => `${x.page} ${x.med}px`).join('，')}`,
        values: meds,
        draws: [],
      });
    }
  }

  // 剩余留白：容器被撑开却没填满，底部（或顶部）空出一块。
  // 只对透明布局容器判定——卡片自己画了边界，内部空隙由边界兜住，不破坏页面节奏。
  for (const p of pages) {
    for (const st of p.stacks) {
      if (st.paintedSelf || st.isRoot) continue;
      for (const side of ['slackBottom', 'slackTop']) {
        const v = st[side];
        if (v <= o.slack) continue;
        const y0 = side === 'slackBottom' ? st.items[st.items.length - 1].bottom : st.inner.top;
        const y1 = side === 'slackBottom' ? st.inner.bottom : st.items[0].top;
        push({
          kind: 'slack', page: p.id, sel: st.sel, spread: v,
          detail: `${st.sel} ${side === 'slackBottom' ? '底部' : '顶部'}空出 ${v}px（阈值 ${o.slack}px）`,
          values: [v],
          draws: [{ type: 'slack', x0: st.inner.left, x1: st.inner.right, y0, y1, label: `留白 ${v}px` }],
        });
      }
    }
  }

  // 并排列：列底/列顶不齐，观感就是左右两边不一致。
  // 只判「等高面板」这种列：容器交给默认拉伸对齐、且这一排占到页面高度的两成以上。
  // 声明了 center/baseline 的单行排，错位是设计意图；旋转装饰带来的几像素也不算。
  for (const p of pages) {
    for (const rw of p.rows) {
      if (!/^(stretch|normal)$/.test(rw.align || '')) continue;
      if (rw.heightRatio < 0.22) continue;
      for (const [side, v] of [['底', rw.bottomSpread], ['顶', rw.topSpread]]) {
        if (v <= Math.max(o.tol * 3, 6)) continue;
        push({
          kind: 'symmetry', page: p.id, sel: rw.sel, spread: v,
          detail: `${rw.sel} 各列${side}边错位 ${v}px`,
          values: rw.cols.map((c) => (side === '底' ? c.bottom : c.top)),
          draws: rw.cols.map((c) => ({
            type: 'line', x0: c.left, x1: c.right,
            y0: side === '底' ? c.bottom : c.top, y1: (side === '底' ? c.bottom : c.top) + 2,
            label: `${side} ${side === '底' ? c.bottom : c.top}`,
          })),
        });
      }
    }
  }

  // 页边距：同页左右不对称，或各页边距不统一。
  for (const p of pages) {
    if (!p.frame) continue;
    const d = r1(Math.abs(p.frame.left - p.frame.right));
    if (d > o.tol) {
      push({
        kind: 'symmetry', page: p.id, sel: p.id, spread: d,
        detail: `页内容左右边距不对称：左 ${p.frame.left}px / 右 ${p.frame.right}px`,
        values: [p.frame.left, p.frame.right],
        draws: [],
      });
    }
  }
  for (const side of ['left', 'right', 'top', 'bottom']) {
    const vals = pages.filter((p) => p.frame).map((p) => ({ page: p.id, v: p.frame[side] }));
    if (vals.length < 2) continue;
    const spread = r1(Math.max(...vals.map((x) => x.v)) - Math.min(...vals.map((x) => x.v)));
    if (spread > o.tol) {
      push({
        kind: 'cross-page', page: vals.map((x) => x.page).join(','), sel: `frame.${side}`, spread,
        detail: `各页${side}边距不统一：${vals.map((x) => `${x.page} ${x.v}px`).join('，')}`,
        values: vals.map((x) => x.v),
        draws: [],
      });
    }
  }

  // 间隔档位：数值接近但不相等的间隔，就是「这里和别处不一样」的来源。
  // 只统计当分隔用的间隔（≥minGap），行距级别的小数值不参与档位。
  const hist = new Map();
  for (const p of pages) {
    for (const st of p.stacks) {
      for (const g of st.gaps) {
        if (g.gap < o.minGap) continue;
        const k = Math.round(g.gap * 2) / 2;
        if (!hist.has(k)) hist.set(k, []);
        hist.get(k).push({ page: p.id, sel: st.sel, g });
      }
    }
  }
  const counts = [...hist.entries()].map(([v, list]) => ({ v, n: list.length, list })).sort((a, b) => b.n - a.n || a.v - b.v);
  for (const c of counts) {
    const stronger = counts.find((x) => x.n > c.n && Math.abs(x.v - c.v) <= o.near && Math.abs(x.v - c.v) > o.tol);
    if (!stronger) continue;
    push({
      kind: 'scale', page: [...new Set(c.list.map((x) => x.page))].join(','), sel: c.list.map((x) => x.sel).join(' | '),
      spread: r1(Math.abs(stronger.v - c.v)),
      detail: `${c.v}px 只用了 ${c.n} 处，同档位主流值是 ${stronger.v}px（${stronger.n} 处），差 ${r1(Math.abs(stronger.v - c.v))}px`,
      values: [c.v, stronger.v],
      draws: c.list.map((x) => ({ type: 'gap', page: x.page, x0: x.g.x0, x1: x.g.x1, y0: x.g.y0, y1: x.g.y1, label: String(x.g.gap) })),
    });
  }

  return { flags, histogram: counts.map((c) => ({ gap: c.v, count: c.n })) };
}

/* ---------------- 主流程 ---------------- */

(async () => {
  const o = parseArgs();
  const { chromium } = loadPlaywright();
  fs.mkdirSync(o.out, { recursive: true });
  const target = o.url || 'file://' + path.resolve(o.file);
  const [vw, vh] = o.viewport.split('x').map(Number);

  const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  const page = await browser.newPage({ viewport: { width: vw, height: vh } });
  page.setDefaultTimeout(60000);
  await page.goto(target, { waitUntil: 'networkidle' });

  const count = await page.evaluate((sel) => document.querySelectorAll(sel).length, o.slideSel);
  if (!count) {
    console.error(`选择器 ${o.slideSel} 没命中任何页；确认页容器选择器后重跑，不要拿空结果当验收依据`);
    await browser.close();
    process.exit(3);
  }

  // 缩放自适应的舞台要先撑到 1:1，截图才是原始像素；测量另有 scale 归一，不依赖这一步。
  const activate = async (idx) => {
    const how = await page.evaluate(({ sel, i }) => {
      const all = [...document.querySelectorAll(sel)];
      all.forEach((s, k) => s.classList.toggle('active', k === i));
      const shown = () => getComputedStyle(all[i]).visibility !== 'hidden' && getComputedStyle(all[i]).display !== 'none';
      if (shown()) return 'class';
      if (all[i].id) { location.hash = '#' + all[i].id; window.dispatchEvent(new HashChangeEvent('hashchange')); }
      if (shown()) return 'hash';
      all.forEach((s, k) => { s.style.visibility = k === i ? 'visible' : 'hidden'; });
      return 'inline';
    }, { sel: o.slideSel, i: idx });
    await page.waitForTimeout(60);
    return how;
  };

  await activate(0);
  for (let i = 0; i < 3; i++) {
    const m = await page.evaluate((sel) => {
      const el = document.querySelector(sel);
      const r = el.getBoundingClientRect();
      return { s: el.offsetWidth ? r.width / el.offsetWidth : 1 };
    }, o.slideSel);
    if (Math.abs(m.s - 1) < 0.005) break;
    const vp = page.viewportSize();
    const w = Math.min(4000, Math.round(vp.width / m.s) + 8);
    const h = Math.min(4000, Math.round(vp.height / m.s) + 8);
    await page.setViewportSize({ width: w, height: h });
    await page.waitForTimeout(80);
  }

  const pages = [];
  for (let i = 0; i < count; i++) {
    const how = await activate(i);
    const m = await page.evaluate(MEASURE, {
      slideSel: o.slideSel, idx: i, ignoreSel: o.ignoreSel, minSpan: o.minSpan, overlapTol: o.tol,
    });
    pages.push({ ...m, activatedBy: how });
  }

  const { flags, histogram } = buildFlags(pages, o);

  const shots = {};
  if (o.shot) {
    for (let i = 0; i < count; i++) {
      const p = pages[i];
      await activate(i);
      const plain = path.join(o.out, `${o.label}-${p.id}.png`);
      await page.locator(o.slideSel).nth(i).screenshot({ path: plain });
      const draws = flags.flatMap((f) => (f.draws || [])
        .filter((d) => (d.page ? d.page === p.id : f.page.split(',').includes(p.id)))
        .map((d) => ({ ...d })));
      const framed = p.frame ? [{
        type: 'box', x0: p.frame.left, x1: p.width - p.frame.right, y0: p.frame.top, y1: p.height - p.frame.bottom,
        label: `边距 上${p.frame.top} 右${p.frame.right} 下${p.frame.bottom} 左${p.frame.left}`,
      }] : [];
      await page.evaluate(OVERLAY, { slideSel: o.slideSel, idx: i, draws: [...framed, ...draws] });
      const ruler = path.join(o.out, `${o.label}-${p.id}-ruler.png`);
      await page.locator(o.slideSel).nth(i).screenshot({ path: ruler });
      await page.evaluate(() => document.getElementById('__pvr_ruler')?.remove());
      shots[p.id] = { plain, ruler };
    }
  }

  const result = {
    target, label: o.label, generated: new Date().toISOString(),
    thresholds: { tol: o.tol, slack: o.slack, near: o.near, minGap: o.minGap, minSpan: o.minSpan },
    pageCount: count, pages, histogram, flags, shots,
  };
  const json = path.join(o.out, `${o.label}.json`);
  fs.writeFileSync(json, JSON.stringify(result, null, 1));

  const byKind = flags.reduce((a, f) => ({ ...a, [f.kind]: (a[f.kind] || 0) + 1 }), {});
  console.log(JSON.stringify({ json, pageCount: count, flags: flags.length, byKind, shots }, null, 1));
  for (const f of flags) console.log(`[${f.kind}] ${f.id} ${f.page} ${f.detail}`);

  await browser.close();
  process.exit(o.gate && flags.length ? 4 : 0);
})().catch((e) => { console.error('FAIL', e && e.stack || e); process.exit(1); });
