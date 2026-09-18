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
 * 除几何外，另收常见 HTML PPT 陷阱的原始线索（判定在 buildFlags，全部是看图线索）：
 *   connector  文本箭头与相邻文字带中心的偏差（布局盒居中≠视觉对齐，注释行撑高行时箭头下沉）
 *   overflow   裁切容器内内容溢出（页根溢出 = 演示出现滚动条或被静默裁切）
 *   image      图片加载失败、渲染比偏离原始比（拉伸变形）、位图过度放大（投影发虚）
 *   occlusion  文本叶子中心点命中其他元素（疑似被覆盖，看图裁决）
 *   contrast   纯色背景可解析时的 WCAG 对比度；渐变/半透明背景交给看图
 *   font       自定义字体未加载（回退字体改变字宽与观感）
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
 *   <out>/<label>.json            每页几何 + 原始线索 + flags（判定线索，不是结论）
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
  if (process.argv.includes('--help') || process.argv.includes('-h')) {
    console.log(`Usage: node measure-deck.js (--file <html> | --url <URL>) [options]
测量 PPT HTML 的版面几何；flags 是看图线索，不是视觉验收结论。
Options:
  --out <dir>          输出目录，默认 /tmp/ppt-visual-review
  --label <name>       产物前缀，默认 before
  --slide-sel <css>    页选择器，默认 .slide
  --ignore-sel <css>   测量忽略项，默认 .sr-only
  --viewport <WxH>    初始视口，默认 1600x900；测量会尝试归一到原画布
  --tol <px>          几何容差，默认 2
  --slack <px>        留白线索阈值，默认 24
  --near <px>         间隔档位邻近阈值，默认 6
  --min-gap <px>      档位统计下限，默认 8
  --min-span <ratio>  测量容器宽度下限占比，默认 0.3
  --connector-tol <px> 连接符（→/←等文本箭头）与相邻文字中心容差，默认 8
  --shot              逐页生成 plain 与 ruler PNG
  --gate              有 flag 时退出 4；不能据此声明 clean
  -h, --help          显示帮助
Outputs: <out>/<label>.json，--shot 时生成逐页 PNG；stdout 摘要。
flags 覆盖：节奏/对称/档位/留白/跨页一致；连接符对齐、截断溢出、图片质量、
遮挡、对比度、字体加载。全部是看图线索，不是验收结论。
Exit: 0 成功；1 脚本错误；2 参数错误；3 未命中页；4 几何线索未清零。
Examples:
  node measure-deck.js --file deck.html --label before --shot
  node measure-deck.js --url http://localhost:8000 --label after --shot --gate`);
    process.exit(0);
  }
  const fail = message => { console.error(message); process.exit(2); };
  const o = {
    out: '/tmp/ppt-visual-review', label: 'before', slideSel: '.slide',
    ignoreSel: '.sr-only', tol: 2, slack: 24, near: 6, minGap: 8, minSpan: 0.3,
    connectorTol: 6, viewport: '1600x900', shot: false, gate: false,
  };
  const a = process.argv.slice(2);
  for (let i = 0; i < a.length; i++) {
    const k = a[i].replace(/^--/, '');
    if (k === 'shot' || k === 'gate') { o[k] = true; continue; }
    const v = a[++i];
    if (!['file', 'url', 'out', 'label', 'slide-sel', 'ignore-sel', 'viewport', 'tol', 'slack', 'near',
      'minSpan', 'min-span', 'min-gap', 'connectorTol', 'connector-tol'].includes(k) || v === undefined || v.startsWith('--')) {
      fail(`未知参数或缺少值：--${k}；使用 --help 查看用法`);
    }
    if (k === 'slide-sel') o.slideSel = v;
    else if (k === 'ignore-sel') o.ignoreSel = v;
    else if (['tol', 'slack', 'near', 'minSpan', 'min-span', 'min-gap', 'connectorTol', 'connector-tol'].includes(k)) {
      o[{ 'min-span': 'minSpan', 'min-gap': 'minGap', 'connector-tol': 'connectorTol' }[k] || k] = Number(v);
    }
    else o[k] = v;
  }
  if (!o.file && !o.url) { console.error('必须提供 --file 或 --url'); process.exit(2); }
  if (!/^[\w.-]+$/.test(o.label) || ['.', '..'].includes(o.label)) fail('--label 只能是文件名，不含路径');
  if (!/^\d+x\d+$/.test(o.viewport) || o.viewport.split('x').some(v => Number(v) < 1)) fail('--viewport 应为正整数 WxH');
  if (['tol', 'slack', 'near', 'minGap', 'minSpan'].some(k => !Number.isFinite(o[k]) || o[k] < 0) || o.minSpan > 1) {
    fail('阈值必须非负，--min-span 必须在 0 到 1 之间');
  }
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

  /* ---- 常见 HTML PPT 陷阱的原始线索（判定在 buildFlags）---- */

  // 连接符对齐：grid/flex 容器里的纯文本箭头子项，与相邻文字块首行带中心比对。
  // s2 型问题：注释行撑高 grid 行，align-items:center 把单行箭头居中到整行，而文字贴顶。
  const ARROW = /^[→←↑↓↔↕⇒⇐⇔➜➔➤»«›‹]{1,2}$/;
  const connectors = [];
  const scanConnectors = (el) => {
    const kids = [...el.children].filter(visible);
    const disp = getComputedStyle(el).display;
    if (/(grid|flex)/.test(disp) && kids.length >= 2) {
      const arrows = kids.filter((k) => ARROW.test(k.textContent.trim()));
      if (arrows.length) {
        for (const a of arrows) {
          const idx = kids.indexOf(a);
          const nb = [kids[idx - 1], kids[idx + 1]].find(
            (k) => k && k !== a && [...k.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()));
          if (!nb) continue;
          const cs = getComputedStyle(nb);
          // computed line-height 已是 px 或 normal，不能当无单位系数再乘字号。
          const lhVal = parseFloat(cs.lineHeight);
          const firstLine = Number.isFinite(lhVal) ? lhVal : num(cs.fontSize) * 1.2;
          const textCenter = contentBox(nb).top + firstLine / 2;   // 文字贴顶布局的首行带中心
          const ar = vbox(a);
          const arrowCenter = (ar.top + ar.bottom) / 2;
          connectors.push({
            container: pathOf(el), sel: pathOf(a), near: pathOf(nb),
            delta: R(arrowCenter - textCenter), firstLine: R(firstLine),
            arrowCenter: R(arrowCenter), textCenter: R(textCenter),
            x0: ar.left, x1: ar.right,
            y0: R(Math.min(arrowCenter, textCenter) - 6), y1: R(Math.max(arrowCenter, textCenter) + 6),
          });
        }
      }
    }
    for (const k of kids) scanConnectors(k);
  };
  scanConnectors(slide);

  // 截断与溢出：裁切容器（hidden/clip/auto/scroll）里内容超出可视区；
  // 页根溢出意味着演示时会出现滚动条，overflow:hidden 则静默裁切，都算线索。
  const overflows = [];
  for (const el of [slide, ...slide.querySelectorAll('*')].filter(visible)) {
    const cs = getComputedStyle(el);
    const clipped = (axis) => !/visible/.test(axis === 'x' ? cs.overflowX : cs.overflowY);
    if (el.scrollWidth > el.clientWidth + 2 && clipped('x') && el.textContent.trim()) {
      overflows.push({ axis: 'x', sel: pathOf(el), client: el.clientWidth, scroll: el.scrollWidth, isSlide: el === slide });
    }
    if (el.scrollHeight > el.clientHeight + 2 && clipped('y') && el.textContent.trim()) {
      overflows.push({ axis: 'y', sel: pathOf(el), client: el.clientHeight, scroll: el.scrollHeight, isSlide: el === slide });
    }
  }

  // 图片质量：加载失败、渲染宽高比偏离原始比（拉伸变形）、位图过度放大（投影发虚）。
  const images = [...slide.querySelectorAll('img')].filter(visible).map((im) => {
    const r = im.getBoundingClientRect();
    return {
      sel: pathOf(im), src: (im.currentSrc || im.src || '').split('/').pop(),
      broken: im.complete && im.naturalWidth === 0,
      natW: im.naturalWidth, natH: im.naturalHeight,
      renderW: R(r.width / scale), renderH: R(r.height / scale),
      box: vbox(im),
    };
  });

  // 遮挡：文本叶子中心点命中的是别的元素 → 疑似被覆盖；透明热区和隐身控件不算（不挡视线）。
  const occlusions = [];
  const faint = (el) => {
    for (let n = el; n && n !== document.body; n = n.parentElement) {
      if (num(getComputedStyle(n).opacity) < 0.05) return true;
    }
    return false;
  };
  const textLeaves = [...slide.querySelectorAll('*')].filter(visible)
    .filter((el) => [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()));
  for (const el of textLeaves.slice(0, 80)) {
    const r = el.getBoundingClientRect();
    const stack = document.elementsFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    if (!stack.length) continue;
    const top = stack[0];
    if (top === el || top.contains(el) || el.contains(top)) continue;
    if (!slide.contains(top)) continue;   // slide 外的全局控件（导航/备注按钮）浮在页面上是 chrome 常态
    if (faint(top) || !painted(top)) continue;   // 透明热区/隐层不挡视线
    occlusions.push({ sel: pathOf(el), coveredBy: pathOf(top), text: el.textContent.trim().slice(0, 24), box: vbox(el) });
  }

  // 对比度：文本叶子的 color 与纯色有效背景的 WCAG 对比度；渐变/半透明背景算不出就跳过。
  const parseColor = (c) => {
    const m = (c || '').match(/rgba?\(([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+))?\)/);
    return m ? [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4]] : null;
  };
  const lum = ([r, g, b]) => {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const contrasts = [];
  for (const el of textLeaves) {
    const cs = getComputedStyle(el);
    const fg = parseColor(cs.color);
    if (!fg || fg[3] === 0) continue;
    let bg = null;
    for (let node = el; node && node !== document.documentElement; node = node.parentElement) {
      const s = getComputedStyle(node);
      if (s.backgroundImage !== 'none') { bg = null; break; }
      const c = parseColor(s.backgroundColor);
      if (c && c[3] >= 1) { bg = c; break; }
      if (c && c[3] > 0) { bg = null; break; }   // 半透明背景需与下层合成，交给看图
    }
    if (!bg) continue;
    const mixed = fg[3] < 1 ? fg.slice(0, 3).map((v, i) => v * fg[3] + bg[i] * (1 - fg[3])) : fg.slice(0, 3);
    const ratio = (Math.max(lum(mixed), lum(bg)) + 0.05) / (Math.min(lum(mixed), lum(bg)) + 0.05);
    const size = num(cs.fontSize), weight = parseInt(cs.fontWeight, 10) || 400;
    contrasts.push({
      sel: pathOf(el), ratio: Math.round(ratio * 100) / 100,
      need: size >= 24 || (size >= 18.66 && weight >= 700) ? 3 : 4.5,
      fontSize: size, text: el.textContent.trim().slice(0, 24), box: vbox(el),
    });
  }

  const all = [...slide.querySelectorAll('*')].filter(visible).map(vbox);
  const frame = all.length ? {
    left: R(Math.min(...all.map((b) => b.left))),
    right: R(W - Math.max(...all.map((b) => b.right))),
    top: R(Math.min(...all.map((b) => b.top))),
    bottom: R(H - Math.max(...all.map((b) => b.bottom))),
  } : null;

  return {
    id: slide.id || `slide-${idx + 1}`, index: idx, width: W, height: H, scale: R(scale), frame,
    stacks, rows, connectors, overflows, images, occlusions, contrasts,
  };
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

function buildFlags(pages, o, fontInfo) {
  const flags = [];
  let n = 0;
  const push = (f) => { flags.push({ id: `V${++n}`, ...f }); };

  // 字体加载：回退字体会改变字宽与观感，截图里看到的就是投影效果，先给线索。
  if (fontInfo && fontInfo.unloaded && fontInfo.unloaded.length) {
    push({
      kind: 'font', page: pages.map((p) => p.id).join(','), sel: 'document.fonts', spread: 0,
      detail: `自定义字体未加载：${fontInfo.unloaded.join('，')}；页面可能以回退字体渲染，看图裁决`,
      values: [], draws: [],
    });
  }

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

  // 连接符对齐：文本箭头与相邻文字块首行带中心的偏差。
  // 布局盒完全居中也可能错位（注释行撑高行），所以比对的是文字带，不是盒子对齐。
  // 判据相对首行高：|delta| > max(容差， 首行高的两成)——大字号允许多几像素，小字号更严。
  for (const p of pages) {
    const byContainer = new Map();
    for (const c of p.connectors || []) {
      if (Math.abs(c.delta) <= Math.max(o.connectorTol, (c.firstLine || 24) * 0.2)) continue;
      const key = c.container + '|' + c.delta;
      if (!byContainer.has(key)) byContainer.set(key, { c, list: [] });
      byContainer.get(key).list.push(c);
    }
    for (const { c, list } of byContainer.values()) {
      push({
        kind: 'connector', page: p.id, sel: c.sel, spread: r1(Math.abs(c.delta)),
        detail: `连接符中心距相邻文字带中心偏 ${r1(Math.abs(c.delta))}px（${c.delta > 0 ? '低' : '高'}于文字带，首行高 ${c.firstLine}px，共 ${list.length} 处，${c.container}）`,
        values: list.map((x) => x.delta),
        draws: list.flatMap((x) => [
          { type: 'line', x0: x.x0, x1: x.x1, y0: x.arrowCenter - 1, y1: x.arrowCenter + 1, label: `箭头中心 ${x.arrowCenter}` },
          { type: 'line', x0: x.x0, x1: x.x1, y0: x.textCenter - 1, y1: x.textCenter + 1, label: `文字带中心 ${x.textCenter}` },
        ]),
      });
    }
  }

  // 截断与溢出：裁切容器里的内容超出可视区，演示时读者看到的是残缺或滚动条。
  for (const p of pages) {
    for (const ov of p.overflows || []) {
      push({
        kind: 'overflow', page: p.id, sel: ov.sel, spread: ov.scroll - ov.client,
        detail: `${ov.isSlide ? '页面' : ov.sel} 内容${ov.axis === 'x' ? '横向' : '纵向'}溢出：可视 ${ov.client}px / 实际 ${ov.scroll}px（${ov.isSlide && ov.axis === 'y' ? '演示会出现滚动条或被静默裁切' : '内容被裁切/截断'}），看图确认`,
        values: [ov.client, ov.scroll],
        draws: ov.isSlide ? [] : [],
      });
    }
  }

  // 图片质量：加载失败是断证；比例偏差是拉伸变形；位图放大发虚在投影上更明显。
  for (const p of pages) {
    for (const im of p.images || []) {
      if (im.broken) {
        push({
          kind: 'image', page: p.id, sel: im.sel, spread: 0,
          detail: `图片加载失败：${im.src}（断证，直接阻断级线索）`, values: [], draws: [],
        });
        continue;
      }
      if (!im.natW || !im.natH) continue;
      const natRatio = im.natW / im.natH, renRatio = im.renderW / im.renderH;
      if (Math.abs(renRatio - natRatio) / natRatio > 0.02) {
        push({
          kind: 'image', page: p.id, sel: im.sel, spread: r1(Math.abs(renRatio - natRatio) * 100),
          detail: `图片渲染比 ${renRatio.toFixed(2)} 偏离原始比 ${natRatio.toFixed(2)}（拉伸变形），看图确认`,
          values: [im.natW, im.natH, im.renderW, im.renderH],
          draws: [{ type: 'box', x0: im.box.left, x1: im.box.right, y0: im.box.top, y1: im.box.bottom, label: '变形' }],
        });
      }
      if (im.renderW > im.natW * 1.5 && im.renderW > 120) {
        push({
          kind: 'image', page: p.id, sel: im.sel, spread: r1(im.renderW / im.natW),
          detail: `位图放大 ${Math.round((im.renderW / im.natW) * 10) / 10}×（原始 ${im.natW}px → 渲染 ${im.renderW}px），投影可能发虚，看图裁决`,
          values: [im.natW, im.renderW],
          draws: [{ type: 'box', x0: im.box.left, x1: im.box.right, y0: im.box.top, y1: im.box.bottom, label: `放大 ${Math.round(im.renderW / im.natW * 10) / 10}x` }],
        });
      }
    }
  }

  // 遮挡：文本中心点命中的是别的元素，看图确认是设计叠层还是事故遮盖。
  for (const p of pages) {
    for (const oc of p.occlusions || []) {
      push({
        kind: 'occlusion', page: p.id, sel: oc.sel, spread: 0,
        detail: `文本「${oc.text}」疑似被 ${oc.coveredBy} 覆盖，看图确认是否影响阅读`,
        values: [],
        draws: [{ type: 'box', x0: oc.box.left, x1: oc.box.right, y0: oc.box.top, y1: oc.box.bottom, label: '疑似遮挡' }],
      });
    }
  }

  // 对比度：纯色背景可解析时按 WCAG 判；渐变/半透明背景算不出，只能看图。
  for (const p of pages) {
    for (const ct of p.contrasts || []) {
      if (ct.ratio >= ct.need) continue;
      push({
        kind: 'contrast', page: p.id, sel: ct.sel, spread: r1(ct.need - ct.ratio),
        detail: `文本「${ct.text}」对比度 ${ct.ratio}:1，低于${ct.need >= 4.5 ? '正文 4.5' : '大字 3'}:1（${ct.fontSize}px），看图裁决`,
        values: [ct.ratio, ct.need],
        draws: [{ type: 'box', x0: ct.box.left, x1: ct.box.right, y0: ct.box.top, y1: ct.box.bottom, label: `对比 ${ct.ratio}` }],
      });
    }
  }

  // 同页同文案的同类线索（如一排相同箭头各自低对比）合并为一条，减噪不丢证据。
  const merged = new Map();
  for (const f of flags) {
    const key = `${f.kind}|${f.page}|${f.detail}`;
    if (merged.has(key)) {
      const m = merged.get(key);
      m.draws = [...(m.draws || []), ...(f.draws || [])];
      m.values = [...(m.values || []), ...(f.values || [])];
      continue;
    }
    merged.set(key, f);
  }
  const deduped = [...merged.values()].map((f, i) => ({ ...f, id: `V${i + 1}` }));

  return { flags: deduped, histogram: counts.map((c) => ({ gap: c.v, count: c.n })) };
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

  const fontInfo = await page.evaluate(async () => {
    await document.fonts.ready;
    const unloaded = [...document.fonts]
      .filter((f) => f.status !== 'loaded')
      .map((f) => `${f.family}(${f.status})`);
    return { status: document.fonts.status, unloaded };
  });

  const { flags, histogram } = buildFlags(pages, o, fontInfo);

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
    thresholds: { tol: o.tol, slack: o.slack, near: o.near, minGap: o.minGap, minSpan: o.minSpan, connectorTol: o.connectorTol },
    pageCount: count, pages, histogram, flags, shots, fonts: fontInfo,
  };
  const json = path.join(o.out, `${o.label}.json`);
  fs.writeFileSync(json, JSON.stringify(result, null, 1));

  const byKind = flags.reduce((a, f) => ({ ...a, [f.kind]: (a[f.kind] || 0) + 1 }), {});
  console.log(JSON.stringify({ json, pageCount: count, flags: flags.length, byKind, shots }, null, 1));
  for (const f of flags) console.log(`[${f.kind}] ${f.id} ${f.page} ${f.detail}`);

  await browser.close();
  process.exit(o.gate && flags.length ? 4 : 0);
})().catch((e) => { console.error('FAIL', e && e.stack || e); process.exit(1); });
