# Component Template Library

Each component provides complete HTML + CSS + JS code that can be copied and combined directly.

---

## 1. Summary metrics bar

Display 3–5 key numbers so readers grasp the proposal at a glance.

```html
<div class="summary">
  <div class="cell"><div class="k">Est. effort</div><div class="v accent">~2 weeks</div></div>
  <div class="cell"><div class="k">Services involved</div><div class="v">3</div></div>
  <div class="cell"><div class="k">New tables</div><div class="v">2</div></div>
  <div class="cell"><div class="k">Target hit rate</div><div class="v accent">≥95%</div></div>
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

## 2. Comparison table

For comparing proposals or technology choices; good/bad coloring makes trade-offs obvious at a glance.

```html
<table class="compare">
  <thead><tr><th></th><th>Option A</th><th>Option B</th><th>Option C</th></tr></thead>
  <tbody>
    <tr><td>Latency</td><td class="good">&lt;1ms</td><td>~5ms</td><td class="bad">~50ms</td></tr>
    <tr><td>Capacity</td><td class="bad">Limited</td><td class="good">Elastic scaling</td><td class="good">Unlimited</td></tr>
    <tr><td>Consistency</td><td class="good">Strong</td><td>Eventual</td><td class="bad">Weak</td></tr>
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

## 3. Risk matrix

Display risk level, description, and mitigation measures.

```html
<div class="risks">
  <div class="risk-row risk-head">
    <div class="risk-cell">Risk</div>
    <div class="risk-cell">Level</div>
    <div class="risk-cell">Mitigation</div>
  </div>
  <div class="risk-row">
    <div class="risk-cell">Cache avalanche: many keys expire at once</div>
    <div class="risk-cell"><span class="sev high">HIGH</span></div>
    <div class="risk-cell">Add random jitter to TTL; hot keys never expire</div>
  </div>
  <div class="risk-row">
    <div class="risk-cell">Cache penetration: queries for non-existent keys</div>
    <div class="risk-cell"><span class="sev med">MED</span></div>
    <div class="risk-cell">Bloom filter upfront + cache null values for 60s</div>
  </div>
  <div class="risk-row">
    <div class="risk-cell">Data inconsistency window</div>
    <div class="risk-cell"><span class="sev low">LOW</span></div>
    <div class="risk-cell">Delete cache after write + delayed double-delete fallback</div>
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

## 4. Timeline / milestones

Show implementation phases with support for "completed" and "in progress" states.

```html
<div class="milestones">
  <div class="milestone">
    <div class="when">Week 1</div>
    <div class="dot-col"><span class="dot done"></span><span class="line"></span></div>
    <div class="body">
      <h3>Database schema design</h3>
      <p>Complete table structure, index planning, and migration files</p>
      <div class="tags"><span class="tag">packages/db</span><span class="tag">migration</span></div>
    </div>
  </div>
  <div class="milestone">
    <div class="when">Week 2</div>
    <div class="dot-col"><span class="dot"></span><span class="line"></span></div>
    <div class="body">
      <h3>Cache layer implementation</h3>
      <p>Redis client wrapper, cache strategy, and invalidation mechanism</p>
      <div class="tags"><span class="tag">packages/cache</span></div>
    </div>
  </div>
  <!-- Hide .line on the last milestone -->
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

## 5. Code panel

Dark background with syntax highlighting for key implementation code.

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

## 6. Collapsible code block

Use details/summary for progressive disclosure; detail code is hidden by default.

```html
<details class="snippet">
  <summary>View implementation code</summary>
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

JS (optional — only one open at a time):
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

## 7. Mermaid architecture / flowchart (default first choice)

For complex system architecture, deployment topology, sequence diagrams, state machines, and multi-branch data flows — **prefer Mermaid**; do not hand-write coordinate SVG.

```html
<div class="diagram">
  <pre class="mermaid">
flowchart TB
  Client["Client"] --> API["API Gateway"]
  API --> Cache["Redis Cache"]
  Cache --> DB[("MySQL")]
  </pre>
</div>
```

For sequence diagrams, replace `flowchart` with `sequenceDiagram` syntax.

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

See `references/mermaid_security.md` for security configuration and gate rules. Put node descriptions in a list below the diagram or in sidebar text; **do not** bind page callbacks with `click` inside the diagram.

---

## 8. Clickable flowchart (interactive SVG)

Use SVG when there are ≤5 nodes and you need "click node in diagram → sidebar details". For complex diagrams, use Mermaid from the previous section.

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
      <!-- Nodes -->
      <g class="node" data-k="client">
        <rect x="20" y="60" width="160" height="54" rx="10"
              fill="#fff" stroke="#D1CFC5" stroke-width="1.5"/>
        <text x="100" y="83" text-anchor="middle" font-size="12">Client</text>
        <text x="100" y="100" text-anchor="middle" font-size="10" fill="#87867F">Browser / App</text>
      </g>
      <g class="node" data-k="cache">
        <rect x="240" y="60" width="160" height="54" rx="10"
              fill="rgba(217,119,87,0.10)" stroke="#D97757" stroke-width="1.5"/>
        <text x="320" y="83" text-anchor="middle" font-size="12">Cache</text>
        <text x="320" y="100" text-anchor="middle" font-size="10" fill="#87867F">Redis Cluster</text>
      </g>
      <!-- Arrows -->
      <line x1="180" y1="87" x2="240" y2="87"
            stroke="#87867F" stroke-width="1.5" marker-end="url(#arrow)"/>
    </svg>
  </div>
  <aside class="flow-panel" id="flowPanel">
    <div class="hint">Click a node in the diagram to view details</div>
    <h3 id="fp-title">Client</h3>
    <div class="fp-meta" id="fp-meta">Frontend app</div>
    <p id="fp-body">Issues data requests; checks cache first...</p>
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
    meta: "Frontend app · Browser / App",
    body: "Issues data requests. Checks local cache first (if any), then calls the API layer."
  },
  cache: {
    title: "Cache Layer",
    meta: "Redis Cluster · 3 primary, 3 replica",
    body: "Receives query requests; returns on hit. On miss, falls through to the database, backfills cache, then returns."
  }
  // ... more nodes
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

## 9. Interactive parameter chart (slider tuning)

Use sliders to change parameters and update the SVG chart in real time. Good for demonstrating algorithm behavior or performance changes.

```html
<div class="demo">
  <div class="demo-grid">
    <svg class="chart" id="chart" viewBox="0 0 300 200">
      <!-- Dynamically generated bar chart / curve -->
    </svg>
    <div class="controls">
      <div class="ctrl-row">
        <label>Cache size</label>
        <input id="sizeSlider" type="range" min="100" max="10000" value="1000" step="100">
        <span class="val" id="sizeVal">1000</span>
      </div>
      <div class="ctrl-row">
        <label>TTL (sec)</label>
        <input id="ttlSlider" type="range" min="10" max="3600" value="300" step="10">
        <span class="val" id="ttlVal">300</span>
      </div>
      <div class="readout" id="readout">
        Hit rate: <b>92%</b> · Avg latency: <b>2.3ms</b>
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

  // Simulated hit-rate calculation (example formula)
  const hitRate = Math.min(99, 50 + 30 * Math.log10(size / 100) + 10 * Math.log10(ttl / 10));
  const latency = (1 - hitRate / 100) * 20 + 0.5;

  readout.innerHTML = `Hit rate: <b>${hitRate.toFixed(1)}%</b> · Avg latency: <b>${latency.toFixed(1)}ms</b>`;

  // Update SVG bar chart
  const barH = hitRate / 100 * 160;
  chart.innerHTML = `
    <rect x="0" y="0" width="300" height="200" fill="var(--gray-100)" rx="8"/>
    <rect x="50" y="${180 - barH}" width="60" height="${barH}" fill="var(--olive)" rx="4"/>
    <text x="80" y="195" text-anchor="middle" font-size="10" fill="var(--gray-500)">Hit rate</text>
    <rect x="180" y="${180 - latency * 8}" width="60" height="${latency * 8}" fill="var(--clay)" rx="4"/>
    <text x="210" y="195" text-anchor="middle" font-size="10" fill="var(--gray-500)">Latency</text>
  `;
}

sizeSlider.oninput = updateChart;
ttlSlider.oninput = updateChart;
updateChart();
```

---

## 10. Glossary linking (hover highlight)

Hovering terms in the body highlights the matching definition in the sidebar. Good for concept-heavy proposals.

```html
<div class="page-with-glossary">
  <main>
    <p>When a <span class="term" data-term="cache-miss">cache miss</span> occurs, the request
    <span class="term" data-term="penetration">penetrates</span> to the database...</p>
  </main>
  <aside class="glossary">
    <div class="label">Glossary</div>
    <dl id="gloss">
      <dt data-g="cache-miss">Cache miss</dt>
      <dd>The queried key is not in cache; data must be fetched from the database</dd>
      <dt data-g="penetration">Penetration</dt>
      <dd>Request bypasses cache and hits the database directly, which can overload the database</dd>
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

## 11. Data flow animation

Animated dashed lines on SVG paths to show data or requests moving between components.

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

Use to distinguish synchronous (solid line + arrow) and asynchronous (dashed line + flow animation) paths:
```css
.edge-sync  { stroke: var(--gray-500); stroke-width: 1.5; fill: none; }
.edge-async { stroke: var(--clay); stroke-width: 1.5; stroke-dasharray: 6 4; fill: none;
              animation: dash-flow 1.2s linear infinite; }
```

---

## 12. Tab panel

Switch between multiple options or perspectives in the same space.

```html
<div class="tabs">
  <div class="tab-bar">
    <button class="tab active" data-tab="redis">Redis</button>
    <button class="tab" data-tab="memcached">Memcached</button>
    <button class="tab" data-tab="local">Local cache</button>
  </div>
  <div class="tab-content active" id="tab-redis">
    <p>Redis cluster mode with rich data structures...</p>
  </div>
  <div class="tab-content" id="tab-memcached">
    <p>Memcached pure KV mode, maximally simple...</p>
  </div>
  <div class="tab-content" id="tab-local">
    <p>In-process LRU cache with zero network overhead...</p>
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

## 13. Step highlight animation

Click "Next" to highlight flowchart nodes step by step, simulating the request path.

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
    <!-- Arrows -->
    <line x1="110" y1="40" x2="160" y2="40" stroke="#D1CFC5" stroke-width="1.5" marker-end="url(#arrow)"/>
    <line x1="260" y1="40" x2="310" y2="40" stroke="#D1CFC5" stroke-width="1.5" marker-end="url(#arrow)"/>
    <line x1="410" y1="40" x2="460" y2="40" stroke="#D1CFC5" stroke-width="1.5" marker-end="url(#arrow)"/>
  </svg>
  <div class="step-controls">
    <button id="stepPrev">← Previous</button>
    <span class="step-info" id="stepInfo">Step 1/4</span>
    <button id="stepNext">Next →</button>
  </div>
  <p class="step-desc" id="stepDesc">Client sends request...</p>
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
  "Client sends data request",
  "Query cache first (Redis)",
  "On cache miss, fall through to database",
  "Return data and backfill cache"
];
let currentStep = 0;
const stepNodes = document.querySelectorAll('.step-node');

function updateStep() {
  stepNodes.forEach((n, i) => {
    n.classList.toggle('active', i <= currentStep);
  });
  document.getElementById('stepInfo').textContent = `Step ${currentStep + 1}/${STEP_DESCS.length}`;
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
