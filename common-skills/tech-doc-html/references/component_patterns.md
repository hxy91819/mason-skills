# 组件模板库

每个组件提供完整的 HTML + CSS + JS 代码，可直接复制组合使用。

---

## 1. Summary 指标条

展示 3-5 个关键数字，让读者一眼掌握方案概况。

```html
<div class="summary">
  <div class="cell"><div class="k">预计工时</div><div class="v accent">~2 周</div></div>
  <div class="cell"><div class="k">涉及服务</div><div class="v">3 个</div></div>
  <div class="cell"><div class="k">新增表</div><div class="v">2</div></div>
  <div class="cell"><div class="k">目标命中率</div><div class="v accent">≥95%</div></div>
</div>
```

```css
.summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 16px;
  margin-bottom: 48px;
}
.summary .cell {
  background: #fff;
  border: 1.5px solid var(--gray-300);
  border-radius: 12px;
  padding: 18px 20px;
}
.summary .k {
  font-family: var(--sans);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--gray-500);
  margin-bottom: 6px;
}
.summary .v {
  font-size: 17px;
  color: var(--slate);
  font-weight: 600;
}
.summary .v.accent { color: var(--clay); }
```

---

## 2. 对比表格

用于方案对比、技术选型，good/bad 着色让优劣一目了然。

```html
<table class="compare">
  <thead><tr><th></th><th>方案 A</th><th>方案 B</th><th>方案 C</th></tr></thead>
  <tbody>
    <tr><td>延迟</td><td class="good">&lt;1ms</td><td>~5ms</td><td class="bad">~50ms</td></tr>
    <tr><td>容量</td><td class="bad">有限</td><td class="good">弹性扩展</td><td class="good">无限</td></tr>
    <tr><td>一致性</td><td class="good">强一致</td><td>最终一致</td><td class="bad">弱一致</td></tr>
  </tbody>
</table>
```

```css
.compare {
  border-collapse: collapse;
  width: 100%;
  max-width: 720px;
  font-size: 14px;
  margin: 12px 0 24px;
}
.compare th, .compare td {
  text-align: left;
  padding: 12px 16px;
  border-bottom: 1px solid var(--gray-300);
}
.compare th {
  font-family: var(--sans);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--gray-500);
  font-weight: 500;
}
.compare tr:hover td { background: var(--gray-100); }
.compare td.good { color: var(--olive); font-weight: 600; }
.compare td.bad  { color: var(--rust); font-weight: 600; }
```

---

## 3. 风险矩阵

展示风险等级、描述和缓解措施。

```html
<div class="risks">
  <div class="risk-row risk-head">
    <div class="risk-cell">风险</div>
    <div class="risk-cell">等级</div>
    <div class="risk-cell">缓解方案</div>
  </div>
  <div class="risk-row">
    <div class="risk-cell">缓存雪崩：大量 key 同时过期</div>
    <div class="risk-cell"><span class="sev high">HIGH</span></div>
    <div class="risk-cell">TTL 加随机抖动，热点 key 永不过期</div>
  </div>
  <div class="risk-row">
    <div class="risk-cell">缓存穿透：查询不存在的 key</div>
    <div class="risk-cell"><span class="sev med">MED</span></div>
    <div class="risk-cell">布隆过滤器前置 + 空值缓存 60s</div>
  </div>
  <div class="risk-row">
    <div class="risk-cell">数据不一致窗口</div>
    <div class="risk-cell"><span class="sev low">LOW</span></div>
    <div class="risk-cell">写后删缓存 + 延迟双删兜底</div>
  </div>
</div>
```

```css
.risks {
  border: 1.5px solid var(--gray-300);
  border-radius: 12px;
  overflow: hidden;
  background: #fff;
}
.risk-row {
  display: grid;
  grid-template-columns: 1.6fr 90px 1.6fr;
  gap: 0;
}
.risk-row + .risk-row { border-top: 1.5px solid var(--gray-300); }
.risk-cell { padding: 14px 18px; font-size: 13.5px; }
.risk-cell + .risk-cell { border-left: 1.5px solid var(--gray-300); }
.risk-head { background: var(--gray-100); font-weight: 600; color: var(--slate); font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; }
.sev {
  display: inline-block;
  font-family: var(--sans);
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  font-weight: 600;
}
.sev.high { background: #F3D9CC; color: #8A3B1E; }
.sev.med  { background: var(--oat); color: var(--slate); }
.sev.low  { background: #E4E9DC; color: #4B5C39; }
```

---

## 4. 时间线 / 里程碑

展示实现阶段，支持"已完成"和"进行中"状态。

```html
<div class="milestones">
  <div class="milestone">
    <div class="when">Week 1</div>
    <div class="dot-col"><span class="dot done"></span><span class="line"></span></div>
    <div class="body">
      <h3>数据库 Schema 设计</h3>
      <p>完成表结构设计、索引规划和 migration 文件</p>
      <div class="tags"><span class="tag">packages/db</span><span class="tag">migration</span></div>
    </div>
  </div>
  <div class="milestone">
    <div class="when">Week 2</div>
    <div class="dot-col"><span class="dot"></span><span class="line"></span></div>
    <div class="body">
      <h3>缓存层实现</h3>
      <p>Redis 客户端封装、缓存策略实现、失效机制</p>
      <div class="tags"><span class="tag">packages/cache</span></div>
    </div>
  </div>
  <!-- 最后一个 milestone 的 .line 隐藏 -->
</div>
```

```css
.milestones { display: flex; flex-direction: column; }
.milestone {
  display: grid;
  grid-template-columns: 100px 28px 1fr;
  gap: 0 18px;
}
.milestone .when {
  text-align: right;
  font-family: var(--sans);
  font-size: 12px;
  color: var(--gray-500);
  padding-top: 4px;
}
.milestone .dot-col {
  display: flex;
  flex-direction: column;
  align-items: center;
}
.milestone .dot {
  width: 14px; height: 14px;
  border-radius: 50%;
  background: #fff;
  border: 3px solid var(--clay);
  flex-shrink: 0;
  margin-top: 4px;
}
.milestone .dot.done { background: var(--olive); border-color: var(--olive); }
.milestone .line {
  width: 2px;
  flex: 1;
  background: var(--gray-300);
  margin: 4px 0;
}
.milestone:last-child .line { display: none; }
.milestone .body { padding-bottom: 36px; }
.milestone .body h3 {
  font-family: var(--sans);
  font-weight: 650;
  font-size: 19px;
  color: var(--slate);
  margin-bottom: 4px;
}
.milestone .body p { font-size: 14px; color: var(--gray-500); margin-bottom: 10px; }
.milestone .tags { display: flex; gap: 8px; flex-wrap: wrap; }
.milestone .tag {
  font-family: var(--sans);
  font-size: 11.5px;
  background: var(--gray-100);
  border: 1px solid var(--gray-300);
  border-radius: 6px;
  padding: 3px 8px;
  color: var(--gray-700);
}
```

---

## 5. 代码面板

暗底 + 语法高亮，展示关键实现代码。

```html
<div class="code-block">
  <div class="file-label">src/cache/redis-client.ts</div>
  <div class="code"><pre><span class="kw">export class</span> <span class="fn">CacheClient</span> {
  <span class="kw">async</span> <span class="fn">get</span>&lt;T&gt;(key: string): Promise&lt;T | <span class="kw">null</span>&gt; {
    <span class="kw">const</span> raw = <span class="kw">await</span> <span class="kw">this</span>.redis.<span class="fn">get</span>(key);
    <span class="kw">return</span> raw ? JSON.<span class="fn">parse</span>(raw) : <span class="kw">null</span>;
  }
}</pre></div>
</div>
```

```css
.code-block .file-label {
  font-family: var(--sans);
  font-size: 12px;
  color: var(--gray-500);
  margin-bottom: 8px;
}
.code {
  background: var(--slate);
  border-radius: 12px;
  padding: 18px 20px;
  overflow-x: auto;
}
.code pre {
  font-family: var(--mono);
  font-size: 12.5px;
  line-height: 1.65;
  color: #E8E6DE;
  white-space: pre;
}
.code .kw  { color: #D97757; }
.code .str { color: #788C5D; }
.code .cm  { color: #87867F; }
.code .fn  { color: #C9B98A; }
```

---

## 6. 折叠代码段

用 details/summary 实现渐进式披露，默认隐藏细节代码。

```html
<details class="snippet">
  <summary>查看实现代码</summary>
  <div class="code"><pre>...</pre></div>
</details>
```

```css
details.snippet { margin-top: 8px; }
details.snippet summary {
  list-style: none;
  cursor: pointer;
  font-size: 12.5px;
  color: var(--gray-500);
  font-family: var(--sans);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  user-select: none;
}
details.snippet summary::-webkit-details-marker { display: none; }
details.snippet summary::before {
  content: "▸";
  font-size: 10px;
  transition: transform 0.15s ease;
}
details.snippet[open] summary::before { transform: rotate(90deg); }
```

JS（可选，同时只展开一个）：
```javascript
document.querySelectorAll('details.snippet').forEach(d => {
  d.addEventListener('toggle', () => {
    if (!d.open) return;
    document.querySelectorAll('details.snippet').forEach(other => {
      if (other !== d) other.open = false;
    });
  });
});
```

---

## 7. Mermaid 架构/流程图（默认首选）

复杂系统架构、部署拓扑、时序、状态机、多分支数据流——**优先用 Mermaid**，不要手写坐标 SVG。

```html
<div class="diagram">
  <pre class="mermaid">
flowchart LR
  Client["Client"] --> API["API Gateway"]
  API --> Cache["Redis Cache"]
  Cache --> DB[("MySQL")]
  </pre>
</div>
```

时序图将 `flowchart` 换成 `sequenceDiagram` 语法即可。

```html
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>
  mermaid.initialize({
    startOnLoad: true,
    securityLevel: 'sandbox',
    htmlLabels: false,
    theme: 'base',
    themeVariables: {
      fontFamily: 'system-ui, -apple-system, sans-serif',
      fontSize: '14px',
      primaryColor: '#FAF9F5',
      primaryTextColor: '#141413',
      primaryBorderColor: '#D1CFC5',
      lineColor: '#87867F',
      secondaryColor: '#E3DACC',
      tertiaryColor: '#fff'
    },
    flowchart: { useMaxWidth: true, htmlLabels: false, curve: 'basis' }
  });
</script>
```

安全配置与 gate 规则见 `references/mermaid_security.md`。节点说明放在图下方列表或侧栏文字即可；**不要**在 diagram 里用 `click` 绑页面回调。

---

## 8. 可点击流程图（交互式 SVG）

节点 ≤5 且需要「点击图中节点 → 侧栏详情」时用 SVG。复杂图请用上一节 Mermaid。

```html
<div class="flow-layout">
  <div class="flow-canvas">
    <svg class="flow" viewBox="0 0 620 400">
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"
                markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="#87867F"/>
        </marker>
      </defs>
      <!-- 节点 -->
      <g class="node" data-k="client">
        <rect x="20" y="60" width="160" height="54" rx="10"
              fill="#fff" stroke="#D1CFC5" stroke-width="1.5"/>
        <text x="100" y="83" text-anchor="middle" font-size="12">Client</text>
        <text x="100" y="100" text-anchor="middle" font-size="10" fill="#87867F">浏览器/App</text>
      </g>
      <g class="node" data-k="cache">
        <rect x="240" y="60" width="160" height="54" rx="10"
              fill="rgba(217,119,87,0.10)" stroke="#D97757" stroke-width="1.5"/>
        <text x="320" y="83" text-anchor="middle" font-size="12">Cache</text>
        <text x="320" y="100" text-anchor="middle" font-size="10" fill="#87867F">Redis Cluster</text>
      </g>
      <!-- 箭头 -->
      <line x1="180" y1="87" x2="240" y2="87"
            stroke="#87867F" stroke-width="1.5" marker-end="url(#arrow)"/>
    </svg>
  </div>
  <aside class="flow-panel" id="flowPanel">
    <div class="hint">点击图中节点查看详情</div>
    <h3 id="fp-title">Client</h3>
    <div class="fp-meta" id="fp-meta">前端应用</div>
    <p id="fp-body">发起数据请求，优先查询缓存...</p>
  </aside>
</div>
```

```css
.flow-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 24px;
  align-items: start;
}
@media (max-width: 960px) { .flow-layout { grid-template-columns: 1fr; } }

.flow-canvas {
  border: 1.5px solid var(--gray-300);
  border-radius: 14px;
  background: #fff;
  padding: 24px;
  overflow-x: auto;
}
.flow { display: block; width: 100%; height: auto; }
.flow text { font-family: var(--sans); }

.node { cursor: pointer; transition: transform 120ms ease; }
.node:hover { transform: translateY(-1px); }
.node.active rect { stroke: var(--clay); stroke-width: 2; }

.flow-panel {
  position: sticky;
  top: 24px;
  border: 1.5px solid var(--gray-300);
  border-radius: 14px;
  background: #fff;
  padding: 20px;
}
.flow-panel .hint { font-size: 12px; color: var(--gray-500); margin-bottom: 12px; }
.flow-panel h3 { font-family: var(--sans); font-size: 19px; font-weight: 650; margin-bottom: 4px; }
.flow-panel .fp-meta { font-family: var(--sans); font-size: 11px; color: var(--gray-500); margin-bottom: 12px; }
.flow-panel p { font-size: 13.5px; color: var(--gray-700); line-height: 1.6; }
```

```javascript
const FLOW_DETAIL = {
  client: {
    title: "Client",
    meta: "前端应用 · 浏览器/App",
    body: "发起数据请求。首先检查本地缓存（如有），然后请求 API 层。"
  },
  cache: {
    title: "Cache Layer",
    meta: "Redis Cluster · 3 主 3 从",
    body: "接收查询请求，命中则直接返回；未命中则穿透到数据库，回写缓存后返回。"
  }
  // ... 更多节点
};

const nodes = document.querySelectorAll('.node');
nodes.forEach(n => {
  n.addEventListener('click', () => {
    nodes.forEach(x => x.classList.remove('active'));
    n.classList.add('active');
    const d = FLOW_DETAIL[n.dataset.k];
    if (!d) return;
    document.getElementById('fp-title').textContent = d.title;
    document.getElementById('fp-meta').textContent = d.meta;
    document.getElementById('fp-body').innerHTML = d.body;
  });
});
```

---

## 9. 交互式参数图（滑块调参）

用滑块改变参数，SVG 图表实时更新。适合演示算法原理或性能变化。

```html
<div class="demo">
  <div class="demo-grid">
    <svg class="chart" id="chart" viewBox="0 0 300 200">
      <!-- 动态生成的柱状图/曲线 -->
    </svg>
    <div class="controls">
      <div class="ctrl-row">
        <label>缓存大小</label>
        <input id="sizeSlider" type="range" min="100" max="10000" value="1000" step="100">
        <span class="val" id="sizeVal">1000</span>
      </div>
      <div class="ctrl-row">
        <label>TTL (秒)</label>
        <input id="ttlSlider" type="range" min="10" max="3600" value="300" step="10">
        <span class="val" id="ttlVal">300</span>
      </div>
      <div class="readout" id="readout">
        命中率: <b>92%</b> · 平均延迟: <b>2.3ms</b>
      </div>
    </div>
  </div>
</div>
```

```css
.demo {
  border: 1.5px solid var(--gray-300);
  border-radius: 14px;
  background: #fff;
  padding: 24px;
  margin: 16px 0;
}
.demo-grid {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 28px;
  align-items: center;
}
@media (max-width: 760px) { .demo-grid { grid-template-columns: 1fr; } }

.controls { font-size: 13px; }
.ctrl-row { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.ctrl-row label {
  width: 80px;
  color: var(--gray-500);
  font-family: var(--sans);
  font-size: 11px;
}
.ctrl-row input[type=range] { flex: 1; accent-color: var(--clay); }
.ctrl-row .val { font-family: var(--sans); font-size: 12px; color: var(--slate); width: 48px; }

.readout {
  border-top: 1px solid var(--gray-300);
  margin-top: 16px;
  padding-top: 14px;
  font-size: 13px;
  color: var(--gray-700);
}
.readout b { color: var(--slate); }
```

```javascript
const sizeSlider = document.getElementById('sizeSlider');
const ttlSlider = document.getElementById('ttlSlider');
const sizeVal = document.getElementById('sizeVal');
const ttlVal = document.getElementById('ttlVal');
const readout = document.getElementById('readout');
const chart = document.getElementById('chart');

function updateChart() {
  const size = +sizeSlider.value;
  const ttl = +ttlSlider.value;
  sizeVal.textContent = size;
  ttlVal.textContent = ttl;

  // 模拟命中率计算（示例公式）
  const hitRate = Math.min(99, 50 + 30 * Math.log10(size / 100) + 10 * Math.log10(ttl / 10));
  const latency = (1 - hitRate / 100) * 20 + 0.5;

  readout.innerHTML = `命中率: <b>${hitRate.toFixed(1)}%</b> · 平均延迟: <b>${latency.toFixed(1)}ms</b>`;

  // 更新 SVG 柱状图
  const barH = hitRate / 100 * 160;
  chart.innerHTML = `
    <rect x="0" y="0" width="300" height="200" fill="var(--gray-100)" rx="8"/>
    <rect x="50" y="${180 - barH}" width="60" height="${barH}" fill="var(--olive)" rx="4"/>
    <text x="80" y="195" text-anchor="middle" font-size="10" fill="var(--gray-500)">命中率</text>
    <rect x="180" y="${180 - latency * 8}" width="60" height="${latency * 8}" fill="var(--clay)" rx="4"/>
    <text x="210" y="195" text-anchor="middle" font-size="10" fill="var(--gray-500)">延迟</text>
  `;
}

sizeSlider.oninput = updateChart;
ttlSlider.oninput = updateChart;
updateChart();
```

---

## 10. 术语表联动（Hover 高亮）

正文中的术语 hover 时高亮侧栏对应定义。适合概念密集的方案。

```html
<div class="page-with-glossary">
  <main>
    <p>当 <span class="term" data-term="cache-miss">缓存未命中</span> 时，请求会
    <span class="term" data-term="penetration">穿透</span> 到数据库...</p>
  </main>
  <aside class="glossary">
    <div class="label">术语表</div>
    <dl id="gloss">
      <dt data-g="cache-miss">缓存未命中 (Cache Miss)</dt>
      <dd>查询的 key 不在缓存中，需要回源到数据库获取</dd>
      <dt data-g="penetration">穿透 (Penetration)</dt>
      <dd>请求绕过缓存直接到达数据库，可能造成数据库压力</dd>
    </dl>
  </aside>
</div>
```

```css
.page-with-glossary {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 240px;
  gap: 40px;
}
@media (max-width: 960px) { .page-with-glossary { grid-template-columns: 1fr; } }

.term {
  border-bottom: 1.5px dotted var(--clay);
  cursor: help;
  color: var(--slate);
}

.glossary {
  position: sticky;
  top: 32px;
  align-self: start;
  border: 1.5px solid var(--gray-300);
  border-radius: 12px;
  background: #fff;
  padding: 18px;
}
.glossary .label {
  font-family: var(--sans);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--gray-500);
  margin-bottom: 12px;
}
.glossary dl dt {
  font-family: var(--sans);
  font-size: 15px;
  color: var(--slate);
}
.glossary dl dd {
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--gray-700);
  margin: 2px 0 14px;
}
.glossary dl dt.hl,
.glossary dl dt.hl + dd {
  background: rgba(217,119,87,0.10);
  margin-left: -8px; margin-right: -8px;
  padding-left: 8px; padding-right: 8px;
  border-radius: 4px;
}
```

```javascript
document.querySelectorAll('.term').forEach(el => {
  const g = el.dataset.term;
  el.addEventListener('mouseenter', () => {
    document.querySelector(`dt[data-g="${g}"]`)?.classList.add('hl');
  });
  el.addEventListener('mouseleave', () => {
    document.querySelector(`dt[data-g="${g}"]`)?.classList.remove('hl');
  });
});
```

---

## 11. 数据流动画

SVG 路径上的虚线流动效果，表示数据或请求在组件间传递。

```html
<svg viewBox="0 0 600 100">
  <line class="flow-line animated" x1="50" y1="50" x2="550" y2="50"
        stroke="#D97757" stroke-width="2" stroke-dasharray="8 6"/>
</svg>
```

```css
.flow-line.animated {
  animation: dash-flow 1.5s linear infinite;
}
@keyframes dash-flow {
  to { stroke-dashoffset: -28; }
}
```

可用于区分同步（实线 + 箭头）和异步（虚线 + 流动动画）路径：
```css
.edge-sync  { stroke: var(--gray-500); stroke-width: 1.5; fill: none; }
.edge-async { stroke: var(--clay); stroke-width: 1.5; stroke-dasharray: 6 4; fill: none;
              animation: dash-flow 1.2s linear infinite; }
```

---

## 12. Tab 切换面板

多方案/多视角切换，同一空间展示不同内容。

```html
<div class="tabs">
  <div class="tab-bar">
    <button class="tab active" data-tab="redis">Redis</button>
    <button class="tab" data-tab="memcached">Memcached</button>
    <button class="tab" data-tab="local">本地缓存</button>
  </div>
  <div class="tab-content active" id="tab-redis">
    <p>Redis 集群模式，支持丰富数据结构...</p>
  </div>
  <div class="tab-content" id="tab-memcached">
    <p>Memcached 纯 KV 模式，极致简单...</p>
  </div>
  <div class="tab-content" id="tab-local">
    <p>进程内 LRU 缓存，零网络开销...</p>
  </div>
</div>
```

```css
.tabs { margin: 16px 0; }
.tab-bar {
  display: flex;
  gap: 0;
  border-bottom: 1.5px solid var(--gray-300);
  margin-bottom: 16px;
}
.tab {
  appearance: none;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  font-family: var(--sans);
  font-size: 12px;
  padding: 10px 16px;
  color: var(--gray-500);
  cursor: pointer;
  transition: color 150ms, border-color 150ms;
}
.tab:hover { color: var(--slate); }
.tab.active {
  color: var(--slate);
  border-bottom-color: var(--clay);
  font-weight: 600;
}
.tab-content { display: none; }
.tab-content.active { display: block; }
```

```javascript
document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  });
});
```

---

## 13. 步骤高亮动画

点击"下一步"按钮，逐步高亮流程图中的节点，模拟请求路径。

```html
<div class="step-through">
  <svg class="flow" id="stepFlow" viewBox="0 0 600 80">
    <g class="step-node" data-step="0">
      <rect x="10" y="15" width="100" height="50" rx="8" fill="#fff" stroke="#D1CFC5" stroke-width="1.5"/>
      <text x="60" y="45" text-anchor="middle" font-size="11">Request</text>
    </g>
    <g class="step-node" data-step="1">
      <rect x="160" y="15" width="100" height="50" rx="8" fill="#fff" stroke="#D1CFC5" stroke-width="1.5"/>
      <text x="210" y="45" text-anchor="middle" font-size="11">Cache</text>
    </g>
    <g class="step-node" data-step="2">
      <rect x="310" y="15" width="100" height="50" rx="8" fill="#fff" stroke="#D1CFC5" stroke-width="1.5"/>
      <text x="360" y="45" text-anchor="middle" font-size="11">Database</text>
    </g>
    <g class="step-node" data-step="3">
      <rect x="460" y="15" width="100" height="50" rx="8" fill="#fff" stroke="#D1CFC5" stroke-width="1.5"/>
      <text x="510" y="45" text-anchor="middle" font-size="11">Response</text>
    </g>
    <!-- 箭头 -->
    <line x1="110" y1="40" x2="160" y2="40" stroke="#D1CFC5" stroke-width="1.5" marker-end="url(#arrow)"/>
    <line x1="260" y1="40" x2="310" y2="40" stroke="#D1CFC5" stroke-width="1.5" marker-end="url(#arrow)"/>
    <line x1="410" y1="40" x2="460" y2="40" stroke="#D1CFC5" stroke-width="1.5" marker-end="url(#arrow)"/>
  </svg>
  <div class="step-controls">
    <button id="stepPrev">← 上一步</button>
    <span class="step-info" id="stepInfo">步骤 1/4</span>
    <button id="stepNext">下一步 →</button>
  </div>
  <p class="step-desc" id="stepDesc">客户端发起请求...</p>
</div>
```

```css
.step-through {
  border: 1.5px solid var(--gray-300);
  border-radius: 14px;
  background: #fff;
  padding: 24px;
  margin: 16px 0;
}
.step-node rect { transition: fill 200ms ease, stroke 200ms ease; }
.step-node.active rect {
  fill: rgba(217,119,87,0.12);
  stroke: var(--clay);
  stroke-width: 2;
}
.step-controls {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-top: 16px;
}
.step-info {
  font-family: var(--sans);
  font-size: 12px;
  color: var(--gray-500);
}
.step-desc {
  text-align: center;
  font-size: 14px;
  color: var(--gray-700);
  margin-top: 12px;
}
```

```javascript
const STEP_DESCS = [
  "客户端发起数据请求",
  "先查询缓存（Redis）",
  "缓存未命中时穿透到数据库",
  "数据返回并回写缓存"
];
let currentStep = 0;
const stepNodes = document.querySelectorAll('.step-node');

function updateStep() {
  stepNodes.forEach((n, i) => {
    n.classList.toggle('active', i <= currentStep);
  });
  document.getElementById('stepInfo').textContent = `步骤 ${currentStep + 1}/${STEP_DESCS.length}`;
  document.getElementById('stepDesc').textContent = STEP_DESCS[currentStep];
}

document.getElementById('stepNext').addEventListener('click', () => {
  if (currentStep < STEP_DESCS.length - 1) { currentStep++; updateStep(); }
});
document.getElementById('stepPrev').addEventListener('click', () => {
  if (currentStep > 0) { currentStep--; updateStep(); }
});
updateStep();
```
