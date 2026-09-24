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
 * 布局与一致性线索：
 *   arrow       箭头一端没有对象或离对象过远（悬空箭头读不出起止关系）
 *   void        占位元素投影后页内出现大块纵向空带，或同一横带内的横向空缺
 *   box-style   同父级同尺寸兄弟盒子样式不一；同 class 盒子跨页样式不一
 *   role-style  同 class 文字跨页字号/字重/颜色/字体不一
 *   title       页标题、眉题跨页的字号/字重/颜色/字体/起点漂移
 *   font-family / font-size / color  全局字体栈、相邻字号档位、近似色（inventory 另存全量清单）
 *
 * 排版细节线索（逐字符矩形切出真实折行）：
 *   align 近似对齐；widow 末行孤字；kinsoku 避头尾；half-punct 中文后半角标点；cjk-spacing 中英空格混用；
 *   line-length 单行过长；leading 行距过紧；density 单页字数过多；min-size 字号过小；edge 文字贴边
 *
 * 用法：
 *   node measure-deck.js --file <html> [--out <目录>] [--label before]
 *        [--slide-sel .slide] [--tol 2] [--slack 24] [--void 0.12] [--arrow-gap 48] [--shot] [--gate]
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
  --connector-tol <px> 连接符（→/←等文本箭头）与相邻文字中心容差，默认 6
  --void <ratio>      页内空带阈值（占页高；横向按页宽 ×1.2），默认 0.12
  --arrow-gap <px>    箭头端点到最近对象的距离上限，默认 48
  --size-near <px>    视为同档位的字号差上限，默认 2
  --color-near <d>    视为近似色的 RGB 欧氏距离上限，默认 12
  --max-sizes <n>     全 deck 常用字号档位上限，默认 8
  --min-font <px>     投影字号下限（按 1280 宽画布折算），默认 14
  --max-chars <n>     单页可见字数上限，默认 320
  --max-line <n>      单行字宽上限（中文按字宽，西文按 2 字符 1 字），默认 40
  --min-leading <r>   多行正文行距/字号下限，默认 1.2
  --safe <px>         文字距页面边缘的安全距离（按 1280 宽折算），默认 24
  --shot              逐页生成 plain 与 ruler PNG
  --gate              有 flag 时退出 4；不能据此声明 clean
  -h, --help          显示帮助
Outputs: <out>/<label>.json（含 inventory：字体栈/字号/调色板/逐页标题），--shot 时生成逐页 PNG；stdout 摘要。
flags 覆盖：箭头悬空(arrow)、空带(void)、同组/同类盒子样式(box-style)、同类文字样式(role-style)、
页标题/眉题跨页漂移(title)、全局字体栈(font-family)、字号档位(font-size)、近似色(color)；
排版细节：近似对齐(align)、末行孤字(widow)、避头尾(kinsoku)、半角标点(half-punct)、中英空格(cjk-spacing)、
行长(line-length)、行距(leading)、字数(density)、字号下限(min-size)、贴边(edge)；
以及节奏/对称/档位/留白/跨页边距、连接符对齐、溢出、图片、遮挡、对比度、字体加载。
全部是看图线索，不是验收结论。
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
    voidRatio: 0.12, arrowGap: 48, sizeNear: 2, colorNear: 12, maxSizes: 8,
    minFont: 14, maxChars: 320, maxLine: 40, minLeading: 1.2, safe: 24,
  };
  const numeric = {
    tol: 'tol', slack: 'slack', near: 'near', minSpan: 'minSpan', 'min-span': 'minSpan', 'min-gap': 'minGap',
    connectorTol: 'connectorTol', 'connector-tol': 'connectorTol', void: 'voidRatio', 'arrow-gap': 'arrowGap',
    'size-near': 'sizeNear', 'color-near': 'colorNear', 'max-sizes': 'maxSizes',
    'min-font': 'minFont', 'max-chars': 'maxChars', 'max-line': 'maxLine', 'min-leading': 'minLeading', safe: 'safe',
  };
  const a = process.argv.slice(2);
  for (let i = 0; i < a.length; i++) {
    const k = a[i].replace(/^--/, '');
    if (k === 'shot' || k === 'gate') { o[k] = true; continue; }
    const v = a[++i];
    if (!['file', 'url', 'out', 'label', 'slide-sel', 'ignore-sel', 'viewport', ...Object.keys(numeric)].includes(k)
      || v === undefined || v.startsWith('--')) {
      fail(`未知参数或缺少值：--${k}；使用 --help 查看用法`);
    }
    if (k === 'slide-sel') o.slideSel = v;
    else if (k === 'ignore-sel') o.ignoreSel = v;
    else if (numeric[k]) o[numeric[k]] = Number(v);
    else o[k] = v;
  }
  if (!o.file && !o.url) { console.error('必须提供 --file 或 --url'); process.exit(2); }
  if (!/^[\w.-]+$/.test(o.label) || ['.', '..'].includes(o.label)) fail('--label 只能是文件名，不含路径');
  if (!/^\d+x\d+$/.test(o.viewport) || o.viewport.split('x').some(v => Number(v) < 1)) fail('--viewport 应为正整数 WxH');
  if ([...new Set(Object.values(numeric))].some(k => !Number.isFinite(o[k]) || o[k] < 0) || o.minSpan > 1 || o.voidRatio > 1) {
    fail('阈值必须非负，--min-span 与 --void 必须在 0 到 1 之间');
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

  /* ---- 布局与样式一致性的原始线索（判定在 buildFlags）---- */
  const area = W * H;
  const opaque = (c) => { const p = parseColor(c); return p && p[3] > 0.05 ? `rgb(${p[0]},${p[1]},${p[2]})` : null; };
  const classKey = (el) => (typeof el.className === 'string' && el.className.trim())
    ? el.tagName.toLowerCase() + '.' + el.className.trim().split(/\s+/).sort().join('.') : '';
  const inSlide = [...slide.querySelectorAll('*')].filter(visible);
  const bigBackdrop = (b) => (b.right - b.left) * (b.bottom - b.top) > area * 0.6;

  // svg 常被当整块叠层铺满一片区域，占位和邻接都按其实际绘制的图元并集算。
  const SHAPES = 'path,line,polyline,polygon,rect,circle,ellipse,text,image,use';
  const drawn = (el) => [...el.querySelectorAll(SHAPES)].filter((s) => !s.closest('defs,marker,clipPath,mask,symbol'));
  const svgBox = (el) => {
    const bs = drawn(el).map(vbox).filter((b) => b.right > b.left || b.bottom > b.top);
    if (!bs.length) return vbox(el);
    return {
      left: R(Math.min(...bs.map((b) => b.left))), right: R(Math.max(...bs.map((b) => b.right))),
      top: R(Math.min(...bs.map((b) => b.top))), bottom: R(Math.max(...bs.map((b) => b.bottom))),
    };
  };
  const boxOf = (el) => (el.tagName.toLowerCase() === 'svg' ? svgBox(el) : vbox(el));

  // 占位元素：文字、图片/矢量、无子元素的自绘块（分隔线、色块），以及画了背景面板的容器；
  // 只画边框/投影的外层容器不算占位，否则整行都被它"填满"。整页背景板同样不算。
  const panel = (el) => {
    const cs = getComputedStyle(el);
    return cs.backgroundImage !== 'none' || !!opaque(cs.backgroundColor);
  };
  const occupants = [];
  const targets = [];   // 箭头邻接候选：svg 拆成各图元，避免整块叠层把端点"包住"
  for (const el of inSlide) {
    const isSvg = el.tagName.toLowerCase() === 'svg';
    const media = /^(img|svg|canvas|video|picture)$/i.test(el.tagName);
    if (el.closest('svg') && !isSvg) continue;
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    const leafShape = painted(el) && !el.children.length;
    if (!media && !own && !leafShape && !(painted(el) && panel(el))) continue;
    const b = boxOf(el);
    if (bigBackdrop(b)) continue;
    occupants.push({ sel: pathOf(el), ...b });
    if (isSvg) {
      for (const s of drawn(el)) {
        const sb = vbox(s);
        if (sb.right - sb.left > 0 || sb.bottom - sb.top > 0) targets.push({ el: s, box: sb });
      }
    } else targets.push({ el, box: b });
  }

  // 箭头：文本箭头字形、class 含 arrow/connector 的细长元素、svg 里带 marker 的连线。
  const arrows = [];
  const seenArrow = new Set();
  const markerLines = [...slide.querySelectorAll('[marker-end],[marker-start]')]
    .filter((s) => !s.closest('defs,marker') && visible(s.closest('svg') || s));
  for (const el of [...inSlide, ...markerLines]) {
    const txt = el.children.length ? '' : el.textContent.trim();
    const cls = typeof el.className === 'string' ? el.className : (el.getAttribute('class') || '');
    const isSvg = el.tagName.toLowerCase() === 'svg';
    const b = vbox(el);
    const w = b.right - b.left, h = b.bottom - b.top;
    const thin = Math.min(w, h) <= 24 && Math.max(w, h) >= 16;
    const hit = ARROW.test(txt)
      || markerLines.includes(el)
      || (/arrow|connector/i.test(cls) && thin && !(isSvg && el.querySelector('[marker-end],[marker-start]')));
    if (!hit || seenArrow.has(el) || [...seenArrow].some((a) => a.contains(el))) continue;
    seenArrow.add(el);
    const glyphAxis = /[↑↓↕]/.test(txt) ? 'y' : (ARROW.test(txt) ? 'x' : null);
    arrows.push({ el, sel: pathOf(el), box: b, axis: glyphAxis || (w >= h ? 'x' : 'y') });
  }
  const others = (el) => targets.filter((t) => t.el !== el && !t.el.contains(el) && !el.contains(t.el)
    && !arrows.some((a) => a.el === t.el));
  // svg 连线按真实起点/终点量到最近对象的距离（折线、回路的外接盒方向没有意义）；
  // 其余箭头沿指向轴在同一横/纵带内找两侧最近对象。
  const endpoints = (el) => {
    if (typeof el.getTotalLength !== 'function' || !el.getScreenCTM()) return null;
    const len = el.getTotalLength();
    const ctm = el.getScreenCTM();
    return [0, len].map((at) => {
      const p = el.getPointAtLength(at);
      const q = new DOMPoint(p.x, p.y).matrixTransform(ctm);
      return { x: Lx(q.x), y: Ly(q.y) };
    });
  };
  const rectDist = (pt, b) => Math.hypot(Math.max(b.left - pt.x, 0, pt.x - b.right), Math.max(b.top - pt.y, 0, pt.y - b.bottom));
  const arrowInfo = arrows.map(({ el, sel, box, axis }) => {
    const cands = others(el);
    const ends = endpoints(el);
    if (ends) {
      const near = (pt) => {
        if (!cands.length) return { d: null };
        const best = cands.reduce((m, t) => { const d = rectDist(pt, t.box); return d < m.d ? { d, t } : m; }, { d: Infinity });
        const b = best.t.box;
        // 端点落在对象的斜角外：连线没对准对象任何一条边，观众读不出它从哪里来/指向谁。
        const corner = Math.max(b.left - pt.x, pt.x - b.right) > 2 && Math.max(b.top - pt.y, pt.y - b.bottom) > 2;
        return { d: R(best.d), sel: pathOf(best.t.el), box: b, corner };
      };
      const [s, e] = ends.map(near);
      return { sel, axis: 'path', box, before: s.d, after: e.d, beforeTo: s.sel, afterTo: e.sel,
        beforeCorner: !!s.corner, afterCorner: !!e.corner,
        beforeBox: s.box, afterBox: e.box, ends: ends.map((p) => ({ x: R(p.x), y: R(p.y) })) };
    }
    const perp = axis === 'x' ? ['top', 'bottom'] : ['left', 'right'];
    const [lo, hi] = axis === 'x' ? ['left', 'right'] : ['top', 'bottom'];
    let before = null, after = null;
    for (const { box: b } of cands) {
      if (b[perp[1]] < box[perp[0]] - 12 || b[perp[0]] > box[perp[1]] + 12) continue;
      if (b[hi] <= box[lo] + 2) { const d = R(box[lo] - b[hi]); if (before === null || d < before) before = d; }
      if (b[lo] >= box[hi] - 2) { const d = R(b[lo] - box[hi]); if (after === null || d < after) after = d; }
    }
    return { sel, axis, box, before, after };
  });

  // 文本样式：字体栈、字号、字重、颜色，按完整 class 组合归类，跨页比较同类元素。
  const texts = textLeaves.slice(0, 400).map((el) => {
    const cs = getComputedStyle(el);
    return {
      sel: pathOf(el), role: classKey(el), stack: cs.fontFamily.replace(/["']/g, '').replace(/\s*,\s*/g, ', '),
      size: R(num(cs.fontSize)), weight: parseInt(cs.fontWeight, 10) || 400, color: opaque(cs.color),
      chars: el.textContent.trim().length, box: vbox(el),
    };
  });

  // 自绘盒子：背景、边框、圆角、投影；同父级的同尺寸兄弟应是同一视觉角色。
  const decorated = (el) => {
    const cs = getComputedStyle(el);
    return cs.backgroundImage !== 'none' || !!opaque(cs.backgroundColor) || (cs.boxShadow && cs.boxShadow !== 'none')
      || ['borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth'].filter((k) => num(cs[k]) > 0).length >= 3;
  };
  const boxes = inSlide.filter((el) => el !== slide && !/^(img|svg|canvas|video)$/i.test(el.tagName) && decorated(el))
    .map((el) => {
      const cs = getComputedStyle(el), b = vbox(el);
      const bw = num(cs.borderTopWidth) || num(cs.borderLeftWidth);
      return {
        sel: pathOf(el), parent: el.parentElement ? pathOf(el.parentElement) : '', role: classKey(el), box: b,
        w: R(b.right - b.left), h: R(b.bottom - b.top),
        style: [
          `bg ${opaque(cs.backgroundColor) || (cs.backgroundImage !== 'none' ? 'gradient' : 'none')}`,
          `border ${bw ? `${R(bw)}px ${opaque(cs.borderTopColor) || opaque(cs.borderLeftColor)}` : 'none'}`,
          `radius ${R(num(cs.borderTopLeftRadius))}`,
          `shadow ${cs.boxShadow === 'none' ? 'none' : 'yes'}`,
        ].join(' · '),
        colors: [opaque(cs.backgroundColor), bw ? opaque(cs.borderTopColor) : null].filter(Boolean),
      };
    })
    .concat([...slide.querySelectorAll('svg rect')]
      .filter((el) => !el.closest('defs,marker,clipPath,mask,symbol,pattern') && visible(el.closest('svg')))
      .map((el) => {
        const cs = getComputedStyle(el), b = vbox(el);
        const fill = cs.fill && cs.fill !== 'none' ? (opaque(cs.fill) || cs.fill) : 'none';
        const stroke = cs.stroke && cs.stroke !== 'none' && num(cs.strokeWidth) > 0
          ? `${R(num(cs.strokeWidth))}px ${opaque(cs.stroke) || cs.stroke}` : 'none';
        return {
          sel: pathOf(el), parent: el.parentElement ? pathOf(el.parentElement) : '', role: classKey(el) ? 'svg:' + classKey(el) : '',
          box: b, w: R(b.right - b.left), h: R(b.bottom - b.top),
          style: `fill ${fill} · stroke ${stroke} · rx ${R(num(cs.rx) || num(el.getAttribute('rx')))}`,
          colors: [opaque(cs.fill), stroke !== 'none' ? opaque(cs.stroke) : null].filter(Boolean),
        };
      }))
    // 图片与图标只比尺寸：同组插图/图标大小不一是最常见的"看起来不整齐"。
    .concat(inSlide.filter((el) => /^(img|svg|canvas|video)$/i.test(el.tagName) && !el.parentElement.closest('svg'))
      .map((el) => {
        const b = boxOf(el);
        return {
          sel: pathOf(el), parent: el.parentElement ? pathOf(el.parentElement) : '', role: classKey(el) ? 'media:' + classKey(el) : '',
          box: b, w: R(b.right - b.left), h: R(b.bottom - b.top), style: 'media', colors: [], media: true,
        };
      }))
    .filter((b) => b.w * b.h < area * 0.6 && b.w >= 16 && b.h >= 16);

  // 页标题：页上部的 h1–h3，缺省取最大字号文字所在的块；眉题是紧贴其上方、字号更小的块。
  // 按块取样式与首行文字起点，标题里高亮的 span 不代表整条标题的颜色和位置。
  const blockOf = (el) => {
    let e = el;
    while (e && e !== slide && getComputedStyle(e).display.startsWith('inline')) e = e.parentElement;
    return e && e !== slide ? e : el;
  };
  const blockInfo = (el) => {
    const cs = getComputedStyle(el), b = vbox(el);
    const range = document.createRange();
    range.selectNodeContents(el);
    const first = [...range.getClientRects()].find((r) => r.width > 1);
    return {
      el, sel: pathOf(el), stack: cs.fontFamily.replace(/["']/g, '').replace(/\s*,\s*/g, ', '),
      size: R(num(cs.fontSize)), weight: parseInt(cs.fontWeight, 10) || 400, color: opaque(cs.color),
      left: first ? R(Lx(first.left)) : b.left, top: first ? R(Ly(first.top)) : b.top, bottom: b.bottom,
    };
  };
  const heads = [...slide.querySelectorAll('h1,h2,h3')].filter(visible).map(blockInfo).filter((t) => t.top < H * 0.35);
  const upperLeaves = textLeaves.filter((el) => vbox(el).top < H * 0.35 && el.textContent.trim().length >= 2);
  const pool = heads.length ? heads : [...new Set(upperLeaves.map(blockOf))].map(blockInfo);
  const headline = pool.length ? pool.reduce((m, t) => (t.size > m.size || (t.size === m.size && t.top < m.top) ? t : m)) : null;
  const eyebrow = headline ? [...new Set(textLeaves.map(blockOf))]
    .filter((el) => el !== headline.el && !el.contains(headline.el) && !headline.el.contains(el)).map(blockInfo)
    .filter((t) => t.bottom <= headline.top + 2 && headline.top - t.bottom <= 60 && t.size < headline.size)
    .sort((a, b) => b.bottom - a.bottom)[0] || null : null;
  const pick = (t) => t && { sel: t.sel, stack: t.stack, size: t.size, weight: t.weight, color: t.color, left: t.left, top: t.top };

  // 逐行排版：按字符矩形切出真实折行，供孤字、避头尾、行长、行距、标点与中英混排判断。
  const typo = [];
  const med = (xs) => { const s = [...xs].sort((a, b) => a - b); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
  const blocks = [...new Set(textLeaves.map(blockOf))].slice(0, 150);
  for (const el of blocks) {
    const cs = getComputedStyle(el);
    const fs = num(cs.fontSize);
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const chars = [];
    const narrow = [];
    const range = document.createRange();
    let raw = '';
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (!visible(n.parentElement)) continue;
      const t = n.textContent;
      raw += t;
      const cfs = num(getComputedStyle(n.parentElement).fontSize);
      for (let i = 0; i < t.length && chars.length < 600; i++) {
        if (!t[i].trim()) { chars.push({ ch: ' ' }); continue; }
        range.setStart(n, i); range.setEnd(n, i + 1);
        const r = [...range.getClientRects()].find((x) => x.width > 0);
        if (!r) continue;
        chars.push({ ch: t[i], top: Ly(r.top), h: r.height / scale, left: Lx(r.left), right: Lx(r.right) });
        // 字宽偏窄只是线索；引号可以天然较窄，具体字体和碰撞仍需看图确认。
        if (/[，。、；：？！（）《》「」『』“”‘’]/.test(t[i]) && r.width / scale < cfs * 0.7) {
          narrow.push({ ch: t[i], ctx: t.slice(Math.max(0, i - 4), i + 2), w: R(r.width / scale), fs: R(cfs) });
        }
      }
    }
    const lines = [];
    for (const c of chars) {
      if (c.top === undefined) { if (lines.length) lines[lines.length - 1].text += ' '; continue; }
      const cur = lines[lines.length - 1];
      if (!cur || c.top > cur.top + cur.h * 0.6) lines.push({ text: c.ch, top: c.top, h: c.h, left: c.left, right: c.right });
      else { cur.text += c.ch; cur.right = Math.max(cur.right, c.right); cur.left = Math.min(cur.left, c.left); }
    }
    lines.forEach((l) => { l.text = l.text.replace(/\s+/g, ' ').trim(); });
    const text = lines.map((l) => l.text).join('');
    if (!text) continue;
    const steps = lines.slice(1).map((l, i) => l.top - lines[i].top).filter((d) => d > 0);
    typo.push({
      sel: pathOf(el), size: R(fs), box: vbox(el), lines: lines.map((l) => ({ text: l.text, top: R(l.top), left: R(l.left), right: R(l.right) })),
      leading: steps.length ? R(med(steps) / fs * 100) / 100 : null,
      heading: /^h[1-3]$/i.test(el.tagName) || fs >= 28,
      raw: raw.replace(/\s+/g, ' ').trim(), narrow: narrow.slice(0, 12),
    });
  }

  // 近似对齐：同页两个不相互包含的块，左边缘只差 tol–8px，且纵向相距不远，肉眼会读成"没对齐"。
  // 文字块按首行文字起点比，盒子与图片按视觉边比。
  const alignBox = (el) => {
    if (el.tagName.toLowerCase() === 'svg') return svgBox(el);
    const b = vbox(el);
    return blocks.includes(el) ? { ...b, left: blockInfo(el).left } : b;
  };
  const alignItems = [...new Set([...blocks, ...inSlide.filter((el) => decorated(el) || /^(img|svg)$/i.test(el.tagName))])]
    .filter((el) => el !== slide && !el.parentElement.closest('svg'))
    .map((el) => ({ el, sel: pathOf(el), b: alignBox(el) }))
    .filter((x) => x.b.right - x.b.left >= 40 && !bigBackdrop(x.b));
  const nearAligns = [];
  for (let i = 0; i < alignItems.length; i++) {
    for (let j = i + 1; j < alignItems.length; j++) {
      const a = alignItems[i], c = alignItems[j];
      if (a.el.contains(c.el) || c.el.contains(a.el)) continue;
      const d = Math.abs(a.b.left - c.b.left);
      if (d <= overlapTol || d > 8) continue;
      const vgap = Math.max(a.b.top, c.b.top) - Math.min(a.b.bottom, c.b.bottom);
      if (vgap > 160) continue;
      nearAligns.push({ a: a.sel, b: c.sel, aLeft: a.b.left, bLeft: c.b.left, delta: R(d),
        y0: Math.min(a.b.top, c.b.top), y1: Math.max(a.b.bottom, c.b.bottom) });
    }
  }

  const all = inSlide.map(vbox);
  const frame = all.length ? {
    left: R(Math.min(...all.map((b) => b.left))),
    right: R(W - Math.max(...all.map((b) => b.right))),
    top: R(Math.min(...all.map((b) => b.top))),
    bottom: R(H - Math.max(...all.map((b) => b.bottom))),
  } : null;

  return {
    id: slide.id || `slide-${idx + 1}`, index: idx, width: W, height: H, scale: R(scale), frame,
    stacks, rows, connectors, overflows, images, occlusions, contrasts,
    occupants, arrows: arrowInfo, texts, boxes, title: { headline: pick(headline), eyebrow: pick(eyebrow) },
    typo, nearAligns,
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

  // 空带：页内占位元素投影到纵轴后，内部出现高于阈值的空隙（页边距不算）；
  // 同一横带内再投影到横轴，找出行内被撑开的空缺。
  const intervals = (list, lo, hi) => {
    const s = list.map((b) => [b[lo], b[hi]]).filter(([a, b]) => b > a).sort((a, b) => a[0] - b[0]);
    const out = [];
    for (const [a, b] of s) {
      if (out.length && a <= out[out.length - 1][1]) out[out.length - 1][1] = Math.max(out[out.length - 1][1], b);
      else out.push([a, b]);
    }
    return out;
  };
  for (const p of pages) {
    const occ = p.occupants || [];
    const bands = intervals(occ, 'top', 'bottom');
    for (let i = 1; i < bands.length; i++) {
      const gap = r1(bands[i][0] - bands[i - 1][1]);
      if (gap <= p.height * o.voidRatio) continue;
      push({
        kind: 'void', page: p.id, sel: 'vertical', spread: gap,
        detail: `纵向空带 ${gap}px（y ${r1(bands[i - 1][1])}–${r1(bands[i][0])}，占页高 ${Math.round(gap / p.height * 100)}%），看图判断是否承担停顿/构图用途`,
        values: [gap],
        draws: [{ type: 'slack', x0: 0, x1: p.width, y0: bands[i - 1][1], y1: bands[i][0], label: `空带 ${gap}px` }],
      });
    }
    for (const [y0, y1] of bands) {
      if (y1 - y0 < 24) continue;
      const inBand = occ.filter((b) => b.top >= y0 - 1 && b.bottom <= y1 + 1);
      const cols = intervals(inBand, 'left', 'right');
      for (let i = 1; i < cols.length; i++) {
        const gap = r1(cols[i][0] - cols[i - 1][1]);
        if (gap <= p.width * o.voidRatio * 1.2) continue;
        push({
          kind: 'void', page: p.id, sel: 'horizontal', spread: gap,
          detail: `同一横带内横向空缺 ${gap}px（x ${r1(cols[i - 1][1])}–${r1(cols[i][0])}，y ${r1(y0)}–${r1(y1)}），看图判断是否为有意分栏`,
          values: [gap],
          draws: [{ type: 'slack', x0: cols[i - 1][1], x1: cols[i][0], y0, y1, label: `空缺 ${gap}px` }],
        });
      }
    }
  }

  // 箭头：两端都要有能读出的起点和终点；一端悬空或离对象太远时关系读不出来。
  for (const p of pages) {
    for (const a of p.arrows || []) {
      const [s0, s1] = { x: ['左', '右'], y: ['上', '下'], path: ['起点', '终点'] }[a.axis];
      const miss = [];
      if (a.before === null) miss.push(`${s0}侧无对象`);
      else if (a.before > o.arrowGap) miss.push(`${s0}侧对象距 ${a.before}px`);
      if (a.after === null) miss.push(`${s1}侧无对象`);
      else if (a.after > o.arrowGap) miss.push(`${s1}侧对象距 ${a.after}px`);
      if (a.beforeCorner && a.before !== null && a.before <= o.arrowGap) miss.push(`${s0}落在最近对象 ${a.beforeTo} 的斜角外，未对准任何一边`);
      if (a.afterCorner && a.after !== null && a.after <= o.arrowGap) miss.push(`${s1}落在最近对象 ${a.afterTo} 的斜角外，未对准任何一边`);
      if (!miss.length) continue;
      push({
        kind: 'arrow', page: p.id, sel: a.sel, spread: Math.max(a.before || 0, a.after || 0),
        detail: `箭头 ${a.sel}：${miss.join('；')}（距离阈值 ${o.arrowGap}px），看图确认起止对象和指向是否可读`,
        values: [a.before, a.after],
        draws: [{ type: 'box', x0: a.box.left, x1: a.box.right, y0: a.box.top, y1: a.box.bottom, label: '箭头' }],
      });
    }
  }

  // 同组盒子：同父级（或同页同 class、分散在不同父级里）的尺寸相近的 ≥3 个元素，
  // 应共用一种框样式和尺寸；少数派多半是漏改。图片/图标单独成组，只比尺寸。
  const draw = (b, label) => ({ type: 'box', x0: b.box.left, x1: b.box.right, y0: b.box.top, y1: b.box.bottom, label });
  for (const p of pages) {
    const groups = new Map();
    const add = (key, b) => { if (!groups.has(key)) groups.set(key, []); groups.get(key).push(b); };
    for (const b of p.boxes || []) {
      add(`parent|${b.parent}|${b.media ? 'm' : 'b'}`, b);
      if (b.role) add(`role|${b.role}`, b);
    }
    for (const [key, list] of groups) {
      if (list.length < 3) continue;
      if (key.startsWith('role|') && new Set(list.map((b) => b.parent)).size < 2) continue;
      const noun = list[0].media ? '图片/图标' : '盒子';
      const mw = median(list.map((b) => b.w)), mh = median(list.map((b) => b.h));
      const peers = list.filter((b) => Math.abs(b.w - mw) <= mw * 0.3 && Math.abs(b.h - mh) <= mh * 0.3);
      if (peers.length < 3) continue;
      for (const [dim, name] of [['h', '高'], ['w', '宽']]) {
        const vals = peers.map((b) => b[dim]);
        const mode = [...vals.reduce((m, v) => m.set(Math.round(v), (m.get(Math.round(v)) || 0) + 1), new Map()).entries()]
          .sort((a, b) => b[1] - a[1])[0];
        const odd = peers.filter((b) => Math.abs(b[dim] - mode[0]) > Math.max(o.tol * 2, 4));
        // 只在多数同尺寸、少数偏离时报；本来就按内容自适应的一组（无主流值）交给看图。
        if (!odd.length || mode[1] < 2 || odd.length >= peers.length / 2) continue;
        push({
          kind: 'box-style', page: p.id, sel: peers[0].parent, spread: r1(Math.max(...odd.map((b) => Math.abs(b[dim] - mode[0])))),
          detail: `同组${noun}${name}度不一：多数 ${mode[0]}px，偏离 ${odd.map((b) => `${b.sel.split('>').pop()} ${b[dim]}px`).join('，')}`,
          values: vals, draws: odd.map((b) => draw(b, `${name} ${b[dim]}`)),
        });
      }
      const counts = new Map();
      for (const b of peers) counts.set(b.style, (counts.get(b.style) || 0) + 1);
      if (counts.size < 2) continue;
      const [major, n] = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
      const odd = n > peers.length / 2 ? peers.filter((b) => b.style !== major) : peers;
      push({
        kind: 'box-style', page: p.id, sel: peers[0].parent, spread: counts.size,
        detail: `同组 ${peers.length} 个同尺寸盒子有 ${counts.size} 种样式：${[...counts.entries()].map(([s, c]) => `${c}×「${s}」`).join('；')}，看图确认是有意强调还是漏改`,
        values: [...counts.values()],
        draws: odd.map((b) => draw(b, n > peers.length / 2 ? '样式不同' : '样式分歧')),
      });
    }
  }

  // 跨页同类元素：完整 class 组合相同的文字/盒子，各页应同一样式；只列偏离多数的页。
  const crossRole = (kind, items, keyOf, describe) => {
    const byRole = new Map();
    for (const it of items) {
      if (!it.role) continue;
      if (!byRole.has(it.role)) byRole.set(it.role, []);
      byRole.get(it.role).push(it);
    }
    for (const [role, list] of byRole) {
      const pagesUsed = new Set(list.map((x) => x.page));
      if (pagesUsed.size < 2) continue;
      const counts = new Map();
      for (const it of list) counts.set(keyOf(it), (counts.get(keyOf(it)) || 0) + 1);
      if (counts.size < 2) continue;
      const major = [...counts.entries()].sort((a, b) => b[1] - a[1])[0][0];
      const odd = list.filter((x) => keyOf(x) !== major);
      push({
        kind, page: [...new Set(odd.map((x) => x.page))].join(','), sel: role, spread: counts.size,
        detail: `${role} 跨页有 ${counts.size} 种样式；多数为「${describe(major)}」，偏离：${odd.slice(0, 6).map((x) => `${x.page}「${describe(keyOf(x))}」`).join('，')}${odd.length > 6 ? ` 等 ${odd.length} 处` : ''}`,
        values: [...counts.values()],
        draws: odd.map((x) => ({ ...draw(x, '同类不同'), page: x.page })),
      });
    }
  };
  const allTexts = pages.flatMap((p) => (p.texts || []).map((t) => ({ ...t, page: p.id })));
  const allBoxes = pages.flatMap((p) => (p.boxes || []).map((b) => ({ ...b, page: p.id })));
  crossRole('role-style', allTexts, (t) => `${t.size}px ${t.weight} ${t.color} ${t.stack}`, (k) => k);
  crossRole('box-style', allBoxes, (b) => b.style, (k) => k);

  // 页标题与眉题：跨页同一角色的字号、字重、颜色、字体、起点应一致；封面/章节页看图裁决。
  for (const role of ['headline', 'eyebrow']) {
    const list = pages.map((p) => ({ page: p.id, t: p.title && p.title[role] })).filter((x) => x.t);
    if (list.length < 3) continue;
    const name = role === 'headline' ? '页标题' : '眉题';
    for (const [attr, fmt, tolerant] of [['size', (v) => `${v}px`, false], ['weight', String, false], ['color', String, false],
      ['stack', String, false], ['left', (v) => `x=${v}`, true], ['top', (v) => `y=${v}`, true]]) {
      const vals = list.map((x) => x.t[attr]);
      const mode = [...vals.reduce((m, v) => m.set(v, (m.get(v) || 0) + 1), new Map()).entries()].sort((a, b) => b[1] - a[1])[0][0];
      const odd = list.filter((x) => (tolerant ? Math.abs(x.t[attr] - mode) > o.tol : x.t[attr] !== mode));
      if (!odd.length) continue;
      push({
        kind: 'title', page: odd.map((x) => x.page).join(','), sel: `${role}.${attr}`, spread: odd.length,
        detail: `${name}${{ size: '字号', weight: '字重', color: '颜色', stack: '字体', left: '左起点', top: '顶端位置' }[attr]}不一致：多数 ${fmt(mode)}，偏离 ${odd.map((x) => `${x.page} ${fmt(x.t[attr])}`).join('，')}`,
        values: odd.map((x) => x.t[attr]),
        draws: odd.map((x) => ({ type: 'box', page: x.page, x0: x.t.left, x1: x.t.left + 240, y0: x.t.top, y1: x.t.top + x.t.size * 1.2, label: `${name}偏离` })),
      });
    }
  }

  // 全局字体：按字符数统计字体栈；非主字体栈逐个列出，代码/数字字体是否有意看图裁决。
  const famChars = new Map();
  for (const t of allTexts) {
    if (!famChars.has(t.stack)) famChars.set(t.stack, { chars: 0, pages: new Set() });
    famChars.get(t.stack).chars += t.chars;
    famChars.get(t.stack).pages.add(t.page);
  }
  const fams = [...famChars.entries()].sort((a, b) => b[1].chars - a[1].chars);
  const totalChars = fams.reduce((s, [, v]) => s + v.chars, 0) || 1;
  for (const [stack, v] of fams.slice(1)) {
    push({
      kind: 'font-family', page: [...v.pages].join(','), sel: stack, spread: r1(v.chars / totalChars * 100),
      detail: `非主字体栈「${stack}」占 ${r1(v.chars / totalChars * 100)}% 字符（主字体「${fams[0][0]}」），看图确认是否有意`,
      values: [v.chars], draws: [],
    });
  }

  // 全局字号档位：少量使用、又与主流档位只差 sizeNear 的字号，通常是同一层级写成了两个值；
  // 常用档位本身过多时只报一条汇总，不逐对报邻近档位。
  const sizeCount = new Map();
  for (const t of allTexts) sizeCount.set(t.size, (sizeCount.get(t.size) || 0) + 1);
  const sizes = [...sizeCount.entries()].sort((a, b) => b[1] - a[1] || a[0] - b[0]);
  const common = sizes.filter(([, c]) => c >= 3).map(([s]) => s).sort((a, b) => a - b);
  if (common.length > o.maxSizes) {
    push({
      kind: 'font-size', page: pages.map((p) => p.id).join(','), sel: 'tiers', spread: common.length,
      detail: `全 deck 常用字号 ${common.length} 档（≥3 处）：${common.join(' / ')}px，超过 ${o.maxSizes} 档，检查是否需要收敛字号层级`,
      values: common, draws: [],
    });
  }
  for (const [s, c] of sizes) {
    const stronger = sizes.find(([s2, c2]) => c2 > c && c <= c2 / 3 && s2 !== s && Math.abs(s2 - s) <= o.sizeNear);
    if (!stronger) continue;
    const where = allTexts.filter((t) => t.size === s);
    push({
      kind: 'font-size', page: [...new Set(where.map((t) => t.page))].join(','), sel: `${s}px`, spread: r1(Math.abs(stronger[0] - s)),
      detail: `字号 ${s}px 用了 ${c} 处，相邻档位 ${stronger[0]}px 用了 ${stronger[1]} 处，疑似同层级不同值`,
      values: [s, stronger[0]],
      draws: where.map((t) => ({ ...draw(t, `${s}px`), page: t.page })),
    });
  }

  // 全局颜色：文字色、盒子背景与边框色中，肉眼难分的近似色是调色板漂移。
  const colorUse = new Map();
  const addColor = (c, page) => {
    if (!c) return;
    if (!colorUse.has(c)) colorUse.set(c, { n: 0, pages: new Set() });
    colorUse.get(c).n += 1; colorUse.get(c).pages.add(page);
  };
  for (const t of allTexts) addColor(t.color, t.page);
  for (const b of allBoxes) for (const c of b.colors || []) addColor(c, b.page);
  const rgb = (c) => c.match(/\d+/g).map(Number);
  const dist = (a, b) => Math.hypot(...rgb(a).map((v, i) => v - rgb(b)[i]));
  const palette = [...colorUse.entries()].sort((a, b) => b[1].n - a[1].n);
  for (const [c, v] of palette) {
    const stronger = palette.find(([c2, v2]) => v2.n > v.n && c2 !== c && dist(c, c2) <= o.colorNear);
    if (!stronger) continue;
    push({
      kind: 'color', page: [...v.pages].join(','), sel: c, spread: r1(dist(c, stronger[0])),
      detail: `颜色 ${c} 用了 ${v.n} 处，与主色 ${stronger[0]}（${stronger[1].n} 处）仅差 ${r1(dist(c, stronger[0]))}，疑似同一颜色写成两个值`,
      values: [v.n, stronger[1].n], draws: [],
    });
  }

  /* ---- 排版细节：孤字、避头尾、标点、中英混排、行长、行距、字数、字号下限、贴边、近似对齐 ---- */
  const CJK = /[\u3400-\u9fff\uf900-\ufaff]/;
  const HEAD_BAN = /^[，。、；：？！）》」』”’…,.;:?!)\]%]/;
  const TAIL_BAN = /[（《「『“‘(\[]$/;
  const tbox = (t, label, page) => ({ type: 'box', page, x0: t.box.left, x1: t.box.right, y0: t.box.top, y1: t.box.bottom, label });
  const spacing = { tight: [], spaced: [] };
  // 页脚、页码等每页同位置重复的元素是版式契约，贴边判断不算它们。
  const chromeKey = (t) => `${norm(t.sel)}@${Math.round(t.box.top / 8)}`;
  const chromeCount = new Map();
  for (const p of pages) {
    for (const k of new Set([...(p.typo || []), ...(p.texts || [])].map(chromeKey))) chromeCount.set(k, (chromeCount.get(k) || 0) + 1);
  }
  const isChrome = (t) => pages.length >= 3 && chromeCount.get(chromeKey(t)) >= pages.length / 2;
  const ctx = (text, re) => {
    const out = [];
    for (const m of text.matchAll(re)) out.push(text.slice(Math.max(0, m.index - 3), m.index + m[0].length + 3));
    return out;
  };
  for (const p of pages) {
    const typo = p.typo || [];
    const scaleRef = p.width / 1280;
    const widows = [], kinsoku = [], longLines = [], tight = [], halfPunct = [], narrowPunct = [];
    for (const t of typo) {
      const ls = t.lines;
      const text = ls.map((l) => l.text).join('');
      if (ls.length >= 2) {
        const last = ls[ls.length - 1].text.replace(/\s/g, '');
        if (last.length <= 2 && CJK.test(text)) widows.push({ t, last });
        ls.slice(1).forEach((l, i) => {
          if (HEAD_BAN.test(l.text)) kinsoku.push({ t, what: `行首「${l.text[0]}」` });
          if (TAIL_BAN.test(ls[i].text)) kinsoku.push({ t, what: `行尾「${ls[i].text.slice(-1)}」` });
        });
        if (t.leading !== null && t.leading < o.minLeading && !t.heading) tight.push({ t });
      }
      for (const l of ls) {
        const cjk = CJK.test(l.text);
        const units = cjk ? (l.right - l.left) / t.size : l.text.length / 2;
        if (units > o.maxLine) { longLines.push({ t, units: Math.round(units) }); break; }
      }
      const raw = t.raw || text;
      const m = ctx(raw, /[\u3400-\u9fff][,?!:;](?=[\u3400-\u9fff\s]|$)/g);
      if (m.length) halfPunct.push({ t, samples: m });
      if (t.narrow && t.narrow.length) narrowPunct.push({ t, samples: t.narrow.map((x) => `${x.ctx}（${x.ch} 宽 ${x.w}/${x.fs}px）`) });
      // 只比较真实同一行的相邻文字；raw 会把 br、块级分隔和自动换行两侧拼接。
      // 行内 span 等强调标签仍属于同一行，不能靠加包装标签消掉真正的混排线索。
      for (const line of ls) {
        for (const s of ctx(line.text, /[\u3400-\u9fff][A-Za-z0-9]|[A-Za-z0-9][\u3400-\u9fff]/g)) spacing.tight.push({ page: p.id, s, t });
        for (const s of ctx(line.text, /[\u3400-\u9fff] [A-Za-z0-9]|[A-Za-z0-9] [\u3400-\u9fff]/g)) spacing.spaced.push({ page: p.id, s, t });
      }
    }
    const emit = (kind, list, detail, label) => {
      if (!list.length) return;
      push({ kind, page: p.id, sel: list.map((x) => x.t.sel).join(' | '), spread: list.length, detail: detail(list),
        values: [], draws: list.map((x) => tbox(x.t, label(x))) });
    };
    emit('widow', widows, (l) => `末行孤字 ${l.length} 处：${l.map((x) => `「…${x.last}」`).join('，')}，标题/短段落末行只剩 1–2 字`, (x) => `孤字 ${x.last}`);
    emit('kinsoku', kinsoku, (l) => `避头尾违规 ${l.length} 处：${l.map((x) => x.what).join('，')}`, (x) => x.what);
    emit('half-punct', halfPunct, (l) => `中文后使用半角标点：${l.flatMap((x) => x.samples).slice(0, 6).map((s) => `「${s}」`).join('，')}`, () => '半角标点');
    emit('half-punct', narrowPunct, (l) => `标点字宽偏窄，需看图确认字形或碰撞，宽度本身不证明字体错误：${l.flatMap((x) => x.samples).slice(0, 4).join('；')}`, () => '字宽待核');
    emit('line-length', longLines, (l) => `单行过长 ${l.length} 处：约 ${l.map((x) => x.units).join(' / ')} 字宽（上限 ${o.maxLine}），投影阅读换行困难`, (x) => `${x.units} 字`);
    emit('leading', tight, (l) => `多行正文行距过紧：${l.map((x) => `${x.t.size}px × ${x.t.leading}`).join('，')}（下限 ${o.minLeading}）`, (x) => `行距 ${x.t.leading}`);

    const chars = typo.reduce((s, t) => s + t.lines.map((l) => l.text).join('').replace(/\s/g, '').length, 0);
    if (chars > o.maxChars) {
      push({ kind: 'density', page: p.id, sel: p.id, spread: chars,
        detail: `本页可见文字约 ${chars} 字（上限 ${o.maxChars}），投影下难以读完，考虑拆页或压缩成要点`, values: [chars], draws: [] });
    }
    const edgeHits = typo.filter((t) => !isChrome(t)
      && Math.min(t.box.left, t.box.top, p.width - t.box.right, p.height - t.box.bottom) < o.safe * scaleRef);
    emit('edge', edgeHits.map((t) => ({ t })), (l) => `文字距页面边缘不足 ${o.safe}px：${l.length} 处，投影裁边或观感拥挤`, () => '贴边');

    const na = p.nearAligns || [];
    if (na.length) {
      push({ kind: 'align', page: p.id, sel: na.slice(0, 4).map((x) => `${x.a} ~ ${x.b}`).join(' | '), spread: Math.max(...na.map((x) => x.delta)),
        detail: `近似对齐 ${na.length} 对：左边缘只差 ${[...new Set(na.map((x) => x.delta))].slice(0, 6).join('/')}px，肉眼读作"没对齐"，应统一到同一条参考线`,
        values: na.map((x) => x.delta),
        draws: na.slice(0, 8).map((x) => ({ type: 'line', x0: Math.min(x.aLeft, x.bLeft), x1: Math.max(x.aLeft, x.bLeft) + 2, y0: x.y0, y1: x.y0 + 2, label: `差 ${x.delta}` })) });
    }
  }
  // 字号下限按 1280 宽画布折算，跨 deck 按字号合并成一条，页脚/页码等元信息看图裁决。
  const small = new Map();
  for (const p of pages) {
    for (const t of p.texts || []) {
      if (t.size >= o.minFont * (p.width / 1280) || isChrome(t)) continue;
      if (!small.has(t.size)) small.set(t.size, []);
      small.get(t.size).push({ ...t, page: p.id });
    }
  }
  for (const [size, list] of small) {
    push({ kind: 'min-size', page: [...new Set(list.map((x) => x.page))].join(','), sel: `${size}px`, spread: r1(o.minFont - size),
      detail: `字号 ${size}px 低于投影下限 ${o.minFont}px，共 ${list.length} 处（如「${list[0].sel.split('>').pop()}」），页脚/页码等元信息可保留，承载论点的文字需放大`,
      values: [size], draws: list.map((x) => ({ ...tbox(x, `${size}px`, x.page) })) });
  }
  // 中英文之间是否加空格：两种写法并存时报少数派。
  if (spacing.tight.length && spacing.spaced.length) {
    const minor = spacing.tight.length <= spacing.spaced.length ? ['不加空格', spacing.tight, '加空格'] : ['加空格', spacing.spaced, '不加空格'];
    push({ kind: 'cjk-spacing', page: [...new Set(minor[1].map((x) => x.page))].join(','), sel: 'cjk-latin', spread: minor[1].length,
      detail: `中英文/数字之间空格写法不统一：多数${minor[2]}（${Math.max(spacing.tight.length, spacing.spaced.length)} 处），${minor[0]} ${minor[1].length} 处，如 ${minor[1].slice(0, 5).map((x) => `「${x.s}」`).join('')}`,
      values: [spacing.tight.length, spacing.spaced.length], draws: minor[1].slice(0, 30).map((x) => tbox(x.t, '空格', x.page)) });
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

  const inventory = {
    fonts: fams.map(([stack, v]) => ({ stack, chars: v.chars, pages: [...v.pages] })),
    sizes: sizes.map(([size, count]) => ({ size, count })),
    colors: palette.map(([color, v]) => ({ color, count: v.n, pages: [...v.pages] })),
    titles: pages.map((p) => ({ page: p.id, ...(p.title || {}) })),
  };
  return { flags: deduped, histogram: counts.map((c) => ({ gap: c.v, count: c.n })), inventory };
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

  const { flags, histogram, inventory } = buildFlags(pages, o, fontInfo);

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
    thresholds: {
      tol: o.tol, slack: o.slack, near: o.near, minGap: o.minGap, minSpan: o.minSpan, connectorTol: o.connectorTol,
      voidRatio: o.voidRatio, arrowGap: o.arrowGap, sizeNear: o.sizeNear, colorNear: o.colorNear, maxSizes: o.maxSizes,
      minFont: o.minFont, maxChars: o.maxChars, maxLine: o.maxLine, minLeading: o.minLeading, safe: o.safe,
    },
    pageCount: count, pages, histogram, inventory, flags, shots, fonts: fontInfo,
  };
  const json = path.join(o.out, `${o.label}.json`);
  fs.writeFileSync(json, JSON.stringify(result, null, 1));

  const byKind = flags.reduce((a, f) => ({ ...a, [f.kind]: (a[f.kind] || 0) + 1 }), {});
  console.log(JSON.stringify({ json, pageCount: count, flags: flags.length, byKind, shots }, null, 1));
  for (const f of flags) console.log(`[${f.kind}] ${f.id} ${f.page} ${f.detail}`);

  await browser.close();
  process.exit(o.gate && flags.length ? 4 : 0);
})().catch((e) => { console.error('FAIL', e && e.stack || e); process.exit(1); });
