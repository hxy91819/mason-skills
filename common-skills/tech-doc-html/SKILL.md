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

After Mermaid gate passes, generated HTML **must** pass Playwright MCP validation to ensure no JS errors in interaction logic.

### Validation steps

**Step 1: Initialize Playwright MCP**
```bash
node <skill-path>/setup.js
```

**Step 2: Navigate to page**
```bash
mcporter call playwright.browser_navigate url=file:///path/to/output.html
```

**Step 3: Console error check**
```bash
mcporter call playwright.browser_console_messages
```
- Must be **0 errors**. Any SyntaxError / ReferenceError means JS did not run and all interactions are broken.
- Mermaid syntax errors appear in console — fix diagram source and re-run.
- Common cause: unescaped quotes in HTML strings (e.g. `"review this MR"` truncating the string).

**Step 4: Key variable existence check**
```bash
mcporter call playwright.browser_evaluate function="()=>({
  FLOW_DETAIL: typeof FLOW_DETAIL !== 'undefined',
  hasNodes: document.querySelectorAll('.node').length > 0,
  hasSteps: document.querySelectorAll('.step-node').length > 0
})"
```
- If key variables are `false`, the browser abandoned the JS block → return to Step 3 to fix syntax errors.

**Step 5: Interaction tests**

| Interaction type | Test command | Pass criteria |
|------------------|--------------|---------------|
| SVG node click | `browser_evaluate` with `dispatchEvent('click')` | Panel title shows corresponding node name |
| Step button | `browser_evaluate` with `btn.click()` | `stepInfo` changes from "Step 1/N" to "Step 2/N" |
| Tab switch | `browser_evaluate` with `tab.click()` | `activeTab` shows target tab text |
| Mermaid render | `browser_evaluate` check `.mermaid svg` exists | At least 1 SVG child; no mermaid parse error |
| Glossary hover | `browser_evaluate` with `mouseenter` / `mouseleave` | `dt.hl` class added/removed correctly |

### Common failure modes

| Symptom | Root cause | Fix |
|---------|------------|-----|
| Console `SyntaxError` | Unescaped `"` in JS strings | Use `'` inside or escape as `\"` |
| Variables `undefined` | HTML syntax error before `<script>` aborts parsing | Check HTML entity encoding (e.g. `=&gt;` should be `=>`) |
| Button click no response | `addEventListener` not bound (JS did not run) | Fix SyntaxError first |
| Tab switch no change | CSS `.active` not toggled | Check JS classList logic |

### Hard rules

- **Mermaid gate failed = do not publish**, even if the diagram looks fine in browser.
- **Console has errors = page unusable**, regardless of visual appearance.
- **Fix all JS errors before publishing** — no exceptions.

## Reference example

`assets/example_output.html` is a complete cache system design HTML output with interactive architecture diagram, slider demo, option comparison, etc. Use it as the quality bar for output.
