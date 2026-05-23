# Design System

Extracted design system for direct copy into HTML files.

## CSS variables

```css
:root {
  /* Colors */
  --ivory:    #FAF9F5;   /* Page background (warm ivory) */
  --slate:    #141413;   /* Primary text / emphasis */
  --clay:     #D97757;   /* Highlight / warning / CTA (warm rust orange) */
  --olive:    #788C5D;   /* Success / confirm (soft green) */
  --oat:      #E3DACC;   /* Secondary emphasis / badge (warm beige) */
  --sky:      #6A8CAF;   /* Info / links (blue-gray) */
  --rust:     #B04A3F;   /* Critical alert / delete (deep red) */

  /* Grays */
  --gray-100: #F0EEE6;
  --gray-150: #F0EEE6;
  --gray-300: #D1CFC5;
  --gray-500: #87867F;
  --gray-700: #3D3D3A;

  /* Fonts: sans-serif everywhere except code */
  --sans:  system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --mono:  ui-monospace, "SF Mono", Menlo, Monaco, Consolas, monospace;
}
```

## Color semantics

| Variable | Usage |
|----------|-------|
| `--clay` | Highlights, warnings, CTA buttons, active borders |
| `--olive` | Success state, completed markers, positive metrics |
| `--oat` | Badge background, secondary buttons, hover background |
| `--rust` | Critical alerts, failure paths, delete actions |
| `--sky` | Info markers, secondary link color |
| `--slate` | Primary text, emphasis headings, code panel background |
| `--gray-500` | Secondary text, borders, arrows |

## Typography hierarchy

```css
/* Page title */
h1 {
  font-family: var(--sans);
  font-weight: 650;
  font-size: 34px;
  line-height: 1.15;
  color: var(--slate);
  letter-spacing: -0.01em;
  margin-bottom: 16px;
}

/* Section title */
h2 {
  font-family: var(--sans);
  font-weight: 650;
  font-size: 24px;
  color: var(--slate);
  letter-spacing: -0.01em;
  margin: 40px 0 12px;
}

/* Subsection title */
h3 {
  font-family: var(--sans);
  font-weight: 650;
  font-size: 19px;
  color: var(--slate);
  margin-bottom: 6px;
}

/* Body */
body, p {
  font-family: var(--sans);
  font-size: 15px;
  line-height: 1.6;
  color: var(--gray-700);
}

/* Eyebrow label (section type) */
.eyebrow {
  font-family: var(--sans);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--gray-500);
  margin-bottom: 10px;
}

/* Mono-style label */
.label {
  font-family: var(--sans);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--gray-500);
}

/* Inline code */
code {
  font-family: var(--mono);
  font-size: 13px;
  background: var(--gray-100);
  padding: 1.5px 5px;
  border-radius: 4px;
}
```

## Spacing system

| Usage | Size |
|-------|------|
| Minimum gap | 8px |
| Inner element spacing | 12px |
| Card padding | 16–20px |
| Section spacing | 48–64px |
| Page top padding | 56px |
| Page bottom padding | 120px |
| max-width | 1100px |

## Border radius

| Element | Radius |
|---------|--------|
| Small button / chip | 6–8px |
| Panel / card | 12–14px |
| Code panel | 12px |
| Pill button | 999px |

## Borders

```css
/* Standard border */
border: 1.5px solid var(--gray-300);

/* Emphasis border (hover/active) */
border: 2px solid var(--clay);

/* Panel border */
border: 1.5px solid var(--gray-300);
border-radius: 14px;
```

## Shadows

Use sparingly, hover only:
```css
/* Card hover */
box-shadow: 0 10px 30px rgba(20, 20, 19, 0.10);
```

## Responsive breakpoints

```css
@media (max-width: 960px) {
  /* Two columns → single column */
  .page { grid-template-columns: 1fr; }
}
@media (max-width: 760px) {
  /* Two-column grid → single column */
  .grid { grid-template-columns: 1fr; }
}
```

## Page skeleton

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Technical Design Title</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<style>
  :root { /* Paste CSS variables above */ }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--ivory);
    color: var(--gray-700);
    font-family: var(--sans);
    font-size: 15px;
    line-height: 1.6;
    padding: 56px 24px 120px;
    -webkit-font-smoothing: antialiased;
  }
  .page {
    max-width: 1100px;
    margin: 0 auto;
  }
</style>
</head>
<body>
<div class="page">
  <!-- Header -->
  <header>
    <div class="eyebrow">Technical Design · Type Label</div>
    <h1>Design Title</h1>
    <p class="lead">One-line summary...</p>
  </header>

  <!-- Content sections -->
</div>

<script>
  mermaid.initialize({
    startOnLoad: true,
    securityLevel: 'sandbox',
    htmlLabels: false,
    theme: 'base',
    themeVariables: {
      fontFamily: 'system-ui, sans-serif',
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
  // Other interaction logic
</script>
</body>
</html>
```

## Mermaid

Security: `references/mermaid_security.md`. **Layout — vertical by default:** use `flowchart TB` (top-to-bottom). The page max-width is 1100px and many readers are on laptops/split-screen, so `LR` diagrams quickly overflow into horizontal scroll or shrink to unreadable. Choose `LR` only when the flow is genuinely left-to-right (pipeline stages, request/response timeline) **and** stays compact (typically ≤4 nodes in one chain, short labels, no fan-out). When a vertical diagram grows too tall, prefer `subgraph` grouping or splitting into multiple diagrams over flipping to `LR`. Call chains → `sequenceDiagram`.

```css
.diagram {
  background: #fff;
  border: 1.5px solid var(--gray-300);
  border-radius: 14px;
  padding: 24px;
  overflow-x: auto;
}
.mermaid {
  display: flex;
  justify-content: center;
  min-height: 120px;
}
.mermaid svg {
  max-width: 100%;
  height: auto;
}
```

Common diagram types: `flowchart TB` (default — vertical fits 1100px page width), `flowchart LR` (only for short ≤4-node L→R chains that won't overflow on laptop screens), `sequenceDiagram`, `stateDiagram-v2`, `erDiagram`.

## SVG diagram guidelines

For **few-node** clickable diagrams, slider tuning, simple flow animation — use Mermaid for complex relationships.

```css
/* Diagram container */
.diagram {
  background: #fff;
  border: 1.5px solid var(--gray-300);
  border-radius: 14px;
  padding: 24px;
  overflow-x: auto;
}

/* SVG base */
svg { display: block; width: 100%; height: auto; }
svg text { font-family: var(--sans); font-size: 12px; fill: var(--slate); }
svg .sub  { font-size: 10px; fill: var(--gray-500); }
```

SVG arrow markers:
```html
<defs>
  <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"
          markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 z" fill="#87867F"/>
  </marker>
  <marker id="arrow-clay" viewBox="0 0 10 10" refX="9" refY="5"
          markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 z" fill="#D97757"/>
  </marker>
</defs>
```

## Code panel guidelines

```css
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
/* Syntax highlighting */
.code .kw  { color: var(--clay); }      /* Keywords */
.code .str { color: var(--olive); }     /* Strings */
.code .cm  { color: var(--gray-500); }  /* Comments */
.code .fn  { color: #C9B98A; }          /* Function names */
```

## Interaction base styles

```css
/* Generic hover for interactive elements */
.interactive {
  cursor: pointer;
  transition: transform 150ms ease, border-color 150ms ease;
}
.interactive:hover {
  transform: translateY(-1px);
  border-color: var(--slate);
}

/* Active state (selected node) */
.active {
  border-color: var(--clay);
  border-width: 2px;
}

/* Unified slider style */
input[type=range] {
  accent-color: var(--clay);
}

/* Generic button style */
button {
  appearance: none;
  border: 1.5px solid var(--gray-300);
  background: var(--gray-100);
  border-radius: 6px;
  font-family: var(--sans);
  font-size: 11px;
  padding: 6px 10px;
  cursor: pointer;
}
button:hover {
  background: var(--oat);
}
```
