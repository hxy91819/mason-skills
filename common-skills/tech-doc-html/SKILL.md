---
name: tech-doc-html
description: "Use when the user invokes $tech-doc-html to turn a technical design document into an interactive HTML page."
disable-model-invocation: true
triggers:
  - user
---

# Technical Design HTML Visualization

Turn technical design content into vivid, interactive single-file HTML pages that help readers understand system design quickly.

仅在用户显式调用 `$tech-doc-html` 时运行。

## Core principles

1. **Interaction first** — Not static document prettification; use interaction so readers can explore technical concepts hands-on
2. **Single-file, open directly** — Inline CSS/JS; complex diagrams may use Mermaid via CDN (see chart selection and security below)
3. **Serves understanding** — Every interaction and animation must serve the goal of helping readers understand
4. **Fixed identity, free layout** — Color and font tokens are the shared visual identity (use them consistently); page structure, section composition, and layout are designed fresh for each document's content

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

The table below is a menu of proven options, not an assignment — combine entries, adapt them, or invent components not listed here. The deciding criterion is always "does this help the reader understand", not table coverage.

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

Use `flowchart TB` (top-to-bottom) by default for any `flowchart` / `graph` diagram. The default page width is ~1100px and many readers view on laptops or split-screen, so `LR` / `RL` diagrams quickly overflow into horizontal scroll or shrink to unreadable size.

Pick `LR` only when **both** are true:

- The flow is genuinely left-to-right (e.g. pipeline stage 1 → 2 → 3, request/response timeline), AND
- It stays compact — typically ≤4 nodes in a single chain with short labels and no fan-out branches.

If a vertical diagram gets too tall, prefer `subgraph` grouping or splitting into multiple diagrams over flipping to `LR`. `sequenceDiagram`, `stateDiagram-v2`, `erDiagram`, `gantt`, and similar types have their own natural orientation — this rule applies to flowcharts only.

### Step 4: Load design system

Read `references/design_system.md`. It has two layers:

- **Fixed identity** — CSS color variables and font roles. Always use these tokens; they keep every generated page visually consistent.
- **Adjustable defaults** — spacing scale, radii, max-width, page skeleton, breakpoints. Starting points only: restructure the layout (sidebar layouts, full-width sections, multi-column grids, etc.) whenever the content calls for it.

### Chart selection (brief)

- **Default to Mermaid** for architecture, deployment, sequence, state, ER, and large flowcharts — do not hand-write complex SVG
- **Only when** you need "click diagram node → sidebar switches details" and nodes ≤5, use hand-written SVG template (`component_patterns.md` §8)
- **Slider tuning, dynamic bar charts** still use §9 JS + SVG

### Step 5: Load component templates

Read only the sections of `references/component_patterns.md` that implement the chosen components. Treat them as adaptable starting points — restyle, recombine, or replace them as the layout demands. When using Mermaid, read §7 for its required safe `initialize` template.

### Step 6: Assemble output

Combine components into a complete single-file HTML:

- All styles in one `<style>` block
- All scripts in one `<script>` block (at end of body)
- Complex relationship diagrams via Mermaid (CDN + safe `mermaid.initialize`); simple interactive diagrams inline SVG
- Responsive layout for mobile

## Page composition

There is no fixed page skeleton. Compose sections from the information types found in Step 1: each block becomes a section sized and ordered by its importance to understanding, not by a template. A comparison-only doc might be one interactive table; a deep algorithm doc might lead with the parameter explorer and skip the architecture diagram entirely.

One common shape, for full design docs only: open with a summary metric bar, then the core architecture diagram, then mechanism/comparison/plan/risks as present. Treat this as a frequent outcome of content analysis, not a required structure.

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
7. Page width fits the content — ~1100px is the default for readability on laptops/split-screen; wider or narrower layouts are fine as long as they stay responsive with no unintended horizontal overflow
8. **Mermaid security gate passes** (see below)

### Mermaid security gate (required when using Mermaid)

After assembly, before Playwright:

```bash
python3 common-skills/tech-doc-html/scripts/security/check_mermaid_insecure_config.py path/to/output.html
```

Exit code must be `0`. Rule details in `references/mermaid_security.md` (same as light-harness `.pre-commit-config.yaml` → `check-mermaid-insecure-config`).

## Runtime proof and completion

After assembly, run the applicable Mermaid security gate and the bundled browser smoke check:

```bash
node <skill-path>/scripts/qa/check_runtime.mjs <project-root> path/to/output.html
```

This is required even if source inspection looks correct. Read [runtime validation](references/runtime-validation.md) when setting up the browser, diagnosing a failure, taking screenshots, or testing bespoke interactions.

Verify the generated page opens, its requested interactions work, and relevant security/runtime gates pass. Fix failures and rerun affected checks before delivery; once evidence is current, deliver the HTML instead of repeating the same checks. A runtime pass does not replace checking the user's requested interaction.

Report the artifact and any demonstrated limitations. Failed required gates block publication; missing browser infrastructure is reported as unverified, without claiming success. Publishing a browser link uses the applicable preview workflow only when requested or already authorized.

## Reference example

`assets/example_output.html` is a complete cache system design HTML output with interactive architecture diagram, slider demo, option comparison, etc. Use it as the quality bar for output — its specific layout is one instance of the design system, not the required shape.
