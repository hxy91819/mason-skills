---
name: tech-doc-html
description: Generate vivid, interactive, easy-to-understand single-file HTML visualizations from technical design documents. Use when the user asks to create technical design HTML, architecture diagram HTML, interactive technical docs, or visualize design documents as web pages.
---

# Technical Design HTML Visualization

Turn technical design content into vivid, interactive single-file HTML pages that help readers understand system design quickly.

## Core principles

1. **Interaction first** — Not static document prettification; use interaction so readers can explore technical concepts hands-on
2. **Single-file, open directly** — Inline CSS/JS; complex diagrams may use Mermaid via CDN (see chart selection and security below)
3. **Serves understanding** — Every interaction and animation must serve the goal of helping readers understand

## Workflow

### Step 1: Analyze the technical design

Read the user's technical design document and identify information types:

- System architecture / component relationships
- Algorithm or mechanism explanations
- Multi-option comparisons
- Data flows / request paths
- Implementation steps / milestones
- Risk assessment
- Key metrics / performance data
- Terminology-heavy concept explanations

### Step 2: Choose visualization + interactive components

For each content block, pick the best component and interaction:

| Information type | Recommended component | Interaction |
|------------------|----------------------|-------------|
| Architecture / deployment / sequence / state machine | **Mermaid** (preferred) | Static diagram; node details in sidebar text |
| Complex data flow / multi-branch process | **Mermaid** flowchart | Same as above |
| Few nodes + must click diagram | SVG flowchart + sidebar (§8) | Click node for details |
| Algorithm / mechanism | Interactive SVG diagram (§9) | Slider adjusts params in real time |
| Option comparison | Comparison table | good/bad coloring + hover highlight |
| Implementation steps | Timeline / milestones | Collapsible code sections |
| Simple flow animation accent | SVG lines (§11) | Dashed CSS flow animation |
| Risk assessment | Risk matrix table | Severity color codes (HIGH/MED/LOW) |
| Key metrics | Summary metric bar | Top-of-page overview |
| Terminology | Sticky glossary sidebar | Hover-linked highlight |
| Multi-perspective explanation | Tab panels | Click to switch views |
| Process demo | Step highlight | "Next step" button highlights progressively |

### Step 3: Load Mermaid security rules (required when using Mermaid)

If output includes Mermaid, **read** `references/mermaid_security.md` **first**, before writing any `mermaid.initialize` or diagram source. Must align with light-harness pre-commit gate (`check_mermaid_insecure_config.py`):

- `securityLevel: 'sandbox'` or `'strict'`
- `htmlLabels: false` (including `flowchart.htmlLabels`)
- No `click` callbacks, `javascript:` URLs, or weak `%%{init}%%` in diagrams

### Mermaid layout: default to vertical

Use `flowchart TB` (top-to-bottom) by default for any `flowchart` / `graph` diagram. The page is capped at 1100px and many readers view on laptops or split-screen, so `LR` / `RL` diagrams quickly overflow into horizontal scroll or shrink to unreadable size.

Pick `LR` only when **both** are true:

- The flow is genuinely left-to-right (e.g. pipeline stage 1 → 2 → 3, request/response timeline), AND
- It stays compact — typically ≤4 nodes in a single chain with short labels and no fan-out branches.

If a vertical diagram gets too tall, prefer `subgraph` grouping or splitting into multiple diagrams over flipping to `LR`. `sequenceDiagram`, `stateDiagram-v2`, `erDiagram`, `gantt`, and similar types have their own natural orientation — this rule applies to flowcharts only.

### Step 4: Load design system

Read `references/design_system.md` for:

- CSS variables (colors / fonts / spacing)
- Page skeleton HTML
- Typography hierarchy
- Responsive breakpoints

### Chart selection (brief)

- **Default to Mermaid** for architecture, deployment, sequence, state, ER, and large flowcharts — do not hand-write complex SVG
- **Only when** you need "click diagram node → sidebar switches details" and nodes ≤5, use hand-written SVG template (`component_patterns.md` §8)
- **Slider tuning, dynamic bar charts** still use §9 JS + SVG

### Step 5: Load component templates

Read `references/component_patterns.md` for full HTML + CSS + JS templates for chosen components (§7 Mermaid includes safe `initialize` template).

### Step 6: Assemble output

Combine components into a complete single-file HTML:

- All styles in one `<style>` block
- All scripts in one `<script>` block (at end of body)
- Complex relationship diagrams via Mermaid (CDN + safe `mermaid.initialize`); simple interactive diagrams inline SVG
- Responsive layout for mobile

## Page structure template

Recommended sections for a standard technical design HTML:

```
1. Header    — Title + eyebrow type label + one-line summary
2. Summary   — 4-cell key metric bar (e.g. est. effort, services involved...)
3. Architecture / overview — Mermaid system diagram (core, largest visual)
4. Mechanism diagram — Interactive concept explanation (sliders/buttons to explore)
5. Option comparison — Table with good/bad coloring
6. Implementation plan — Timeline + milestones + collapsible code
7. Risk matrix — HIGH/MED/LOW color codes
8. Open questions — Pending decisions (optional)
```

Not every design needs all sections — pick based on content.

## Interaction design guide

### When to use interaction

- **Concept has tunable parameters** → Slider (e.g. cache size, node count, timeout)
- **System has multiple components** → Mermaid architecture; SVG clickable flowchart (§8) only when few nodes need click details
- **Steps / sequence** → "Next step" button to highlight progressively
- **Long code blocks** → Collapse; show only key lines by default
- **Multiple options** → Tab switch

### When not to use interaction

- Little information, one paragraph suffices → Plain text
- Only 2–3 comparison items → Simple table, no extra JS
- Flow has ≤3 steps → Static diagram is enough

## Output quality checklist

Generated HTML must satisfy:

1. Opens directly in browser (Mermaid CDN allowed; note offline needs network)
2. All interactive elements have hover feedback (cursor: pointer, border changes, etc.)
3. Unified typography: use `--sans` everywhere except `code` / `pre` / code panel content
4. Mobile usable (at least single-column fallback)
5. Mermaid container scrolls horizontally; hand-written SVG uses viewBox for scaling
6. Code panels dark background + syntax highlighting
7. Page max-width ≤ 1100px
8. **Mermaid security gate passes** (see below)

### Mermaid security gate (required when using Mermaid)

After assembly, before Playwright:

```bash
python3 common-skills/tech-doc-html/scripts/security/check_mermaid_insecure_config.py path/to/output.html
```

Exit code must be `0`. Rule details in `references/mermaid_security.md` (same as light-harness `.pre-commit-config.yaml` → `check-mermaid-insecure-config`).

## QA validation — headless browser (required)

After Mermaid gate passes, generated HTML **must** pass a runtime smoke check to ensure no JS / Mermaid errors at render time. The skill ships a no-MCP gate (`scripts/qa/check_runtime.mjs`) that is the recommended primary path; richer interaction tests via Playwright MCP are an optional follow-up.

### Primary gate: `check_runtime.mjs` (recommended)

A self-contained Node + Playwright script. Loads each HTML in headless Chromium, waits for all `<pre class="mermaid">` to reach `data-processed=true`, then asserts zero `pageerror` and zero `console.error`. Catches everything the security/syntax gates miss — JS SyntaxError preventing handler binding, Mermaid `translate(undefined, NaN)` positioning errors from hidden containers (see `references/mermaid_security.md` "Rendering pitfalls"), unhandled rejections, late console errors after `networkidle`.

```bash
# In any project that has `npm i playwright` installed:
node <skill-path>/scripts/qa/check_runtime.mjs <project-root> path/to/output.html [more.html ...]
```

Exit code `0` means all files clean; `1` means at least one file reported `pageerror` / `console.error` / mermaid-ready timeout.

Useful env vars:

| Var | Default | Purpose |
|-----|---------|---------|
| `QA_ALLOW_CONSOLE` | unset | Regex; matching `console.error` lines are suppressed (e.g. expected `Failed to load resource` for offline-only assets) |
| `QA_TIMEOUT_MS` | `30000` | Page load + mermaid-ready timeout |
| `QA_WAIT_MS` | `1500` | Extra wait after `networkidle` for late-binding handlers |
| `QA_VIEWPORT` | `1280x900` | Viewport size `WxH` |

### Visual self-review: `screenshot.mjs`

For iterative editing, the agent can screenshot a page (or one CSS selector) to inspect layout / spacing / mermaid render visually:

```bash
node <skill-path>/scripts/qa/screenshot.mjs <project-root> path/to/output.html out.png
# Crop to one section:
QA_SELECTOR="#some-section" node ...screenshot.mjs ...
# Full scrollable page:
QA_FULL_PAGE=1 node ...screenshot.mjs ...
```

This is **not a go/no-go gate** — it is the cheap way to verify visual changes without leaving the agent loop.

### Optional richer tests via Playwright MCP

If the project's HTML has bespoke interactions (slider → bar widths, tab switch → content swap, etc.) and you want per-interaction assertions, write a project-specific Node + Playwright test file based on the same `<project-root>` convention. The skill intentionally **does not** ship per-page DOM assertion scripts; those live with the project, not the skill.

If Playwright MCP is available, alternative manual probes:

```bash
mcporter call playwright.browser_navigate url=file:///path/to/output.html
mcporter call playwright.browser_console_messages   # expect 0 errors
mcporter call playwright.browser_evaluate function="() => ({...})"
```

### Common runtime failure modes

| Symptom | Root cause | Fix |
|---------|------------|-----|
| `[pageerror] SyntaxError: Unexpected ...` | Unescaped `"` inside JS string literal | Use `'` inside or escape as `\"` |
| `[console.error] translate(undefined, NaN)` | Mermaid rendered inside `display: none` container (bbox unmeasurable) | See "Rendering pitfalls" in `mermaid_security.md`; defer hide until `mermaid.run()` resolves |
| `[mermaid-ready-timeout]` | `mermaid.initialize({ startOnLoad: true })` with diagrams produced after init | Switch to `startOnLoad: false` + explicit `await mermaid.run()` |
| `[console.error] Failed to load resource` for CDN | Page run offline | Set `QA_ALLOW_CONSOLE='^Failed to load resource'` only if intentional |
| Variables `undefined` in browser | HTML syntax error aborts `<script>` parse | Check HTML entity encoding (`=&gt;` should be `=>`) |

### Common failure modes

| Symptom | Root cause | Fix |
|---------|------------|-----|
| Console `SyntaxError` | Unescaped `"` in JS strings | Use `'` inside or escape as `\"` |
| Variables `undefined` | HTML syntax error before `<script>` aborts parsing | Check HTML entity encoding (e.g. `=&gt;` should be `=>`) |
| Button click no response | `addEventListener` not bound (JS did not run) | Fix SyntaxError first |
| Tab switch no change | CSS `.active` not toggled | Check JS classList logic |

### Hard rules

- **Mermaid security gate failed = do not publish**, even if the diagram looks fine in browser.
- **Mermaid syntax gate failed = do not publish**, even if `mermaid.parse()` fails on only one block.
- **Runtime gate (`check_runtime.mjs`) failed = do not publish** — `pageerror` / `console.error` means interactions are broken regardless of visual appearance.
- **Fix all JS / Mermaid runtime errors before publishing** — no exceptions.

## Reference example

`assets/example_output.html` is a complete cache system design HTML output with interactive architecture diagram, slider demo, option comparison, etc. Use it as the quality bar for output.
