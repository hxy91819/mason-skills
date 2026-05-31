# Mermaid embedding security

When single-file HTML loads Mermaid via CDN, misconfiguration or diagram syntax can open **HTML injection / script execution** paths. This spec aligns with `light-harness/scripts/security/check_mermaid_insecure_config.py` (pre-commit hook `check-mermaid-insecure-config`). HTML containing Mermaid **must** pass that check after generation or modification.

## Required `mermaid.initialize` configuration

`securityLevel` and `htmlLabels` are mandatory — do not omit or weaken:

```javascript
mermaid.initialize({
  startOnLoad: true,
  securityLevel: 'sandbox', // or 'strict'; never 'loose' / 'antiscript'
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
```

| Option | Requirement | Reason |
|--------|-------------|--------|
| `securityLevel` | `'strict'` or `'sandbox'` | Restricts executable content and HTML tags in diagrams |
| `htmlLabels` | `false` (global and inside `flowchart`) | Avoids HTML rendering path for node labels |
| `secure` | Do not set `secure: []` | Empty allowlist overrides default security list |

Reference implementation: `light-harness/frontend/src/lib/mermaid-config.ts`.

## Forbidden diagram source patterns

Do **not** use in `<pre class="mermaid">` or fenced mermaid blocks:

| Forbidden | Example | Alternative |
|-----------|---------|-------------|
| `click` callbacks | `click A callback` / `click A call fn()` | Put node notes below diagram or in sidebar; use page JS for interaction |
| `javascript:` links | `click A "javascript:..."` | Plain `https://` links, or omit `click` |
| Weak security init | `%%{init: {'theme':'base'}}%%` without `securityLevel` | Set `securityLevel: 'strict'` or `'sandbox'` in init, or remove init and use page-level `initialize` only |
| Weak securityLevel | `securityLevel: 'loose'` / `'antiscript'` | Use only `strict` / `sandbox` |

If `%%{init: ...}%%` is required, the block must include recognizable `securityLevel: 'strict'` or `'sandbox'` (matching gate regex).

## Recommended practices

- Node labels: plain text or `["quoted label"]` — avoid HTML fragments.
- Architecture notes and click details: list below Mermaid diagram or sidebar — do not bind page callbacks via Mermaid `click`.
- Centralize `mermaid.initialize({...})` in one bottom `<script>` for gate scanning.
- CDN: pin major version (e.g. `mermaid@11`) consistent with other project pages.

## Pre-publish gate checks (required)

Full gate order: **security config → syntax pre-check → Playwright browser render**.

### Gate 1: Security configuration

Run the skill's check script on generated `.html` (and related files in the same directory):

```bash
python3 common-skills/tech-doc-html/scripts/security/check_mermaid_insecure_config.py path/to/output.html
```

Or from monorepo root with light-harness script:

```bash
python3 light-harness/scripts/security/check_mermaid_insecure_config.py path/to/output.html
```

Exit code `0` required; on `1`, fix each `[RULE_CODE]` in output.

### Gate 2: Syntax pre-check

After security gate, validate diagram syntax with `mermaid.parse()`:

```bash
node common-skills/tech-doc-html/scripts/security/check_mermaid_syntax.mjs <project-root> path/to/output.html
```

`<project-root>` is the directory containing `node_modules/mermaid` and `node_modules/jsdom`.

Exit code `0` means all `<pre class="mermaid">` blocks parse; on `1`, output includes `[MERMAID_SYNTAX]` line numbers and parse errors.

**Common syntax issues:**

| Symptom | Root cause | Fix |
|---------|------------|-----|
| `Parse error on line N` | Node ID with spaces or special chars | Use `["quoted label"]` |
| `Lexical error` | HTML tags like `<br/>` in plain text nodes | Remove `<br/>`; split across lines |
| `Expecting 'EOF'` | Unclosed `{}` or `[]` | Check diamond nodes `{label}` are paired |
| `&dollar;` fails in browser | HTML entity encoding | Write `$` or `${...}` directly in `<pre>`, not entities |

### Gate 3: Runtime smoke (browser render)

After syntax pre-check, the skill's runtime gate loads the HTML in headless Chromium and asserts zero `pageerror` / `console.error`:

```bash
node common-skills/tech-doc-html/scripts/qa/check_runtime.mjs <project-root> path/to/output.html
```

`<project-root>` is a directory with `node_modules/playwright` installed. The gate also waits for every `<pre class="mermaid">` to reach `data-processed=true`, so it catches "diagram parses but renders broken" cases the syntax pre-check cannot.

## Rendering pitfalls (caught by runtime gate, not syntax gate)

### Hidden Mermaid diagrams produce `translate(undefined, NaN)`

If a diagram is rendered inside a container with `display: none` (tabbed UI, swipe carousel, "switch to active lane" pattern), Mermaid's text positioning relies on `getBBox()` which returns `0/0` in hidden subtrees. The result: the SVG **is produced**, but several `<g>` elements get `transform="translate(undefined, NaN)"`, console fills with errors, and visible labels are misaligned after the container becomes visible.

**Symptom (caught by `check_runtime.mjs`):**

```
[console.error] Error: <g> attribute transform: Expected number, "translate(undefined, NaN)".
```

**Remediation pattern:** render every `.mermaid` block while it is still laid out (`display: block`), then hide non-active ones via a body class flip after `mermaid.run()` resolves:

```html
<style>
  .lane-diagram { display: block; }
  body.mermaid-ready .lane-diagram { display: none; }
  body.mermaid-ready .lane-diagram.active { display: block; }
</style>
<script>
  mermaid.initialize({ startOnLoad: false, securityLevel: 'sandbox', /* ... */ });
  (async () => {
    try { await mermaid.run({ querySelector: '.mermaid' }); }
    finally { document.body.classList.add('mermaid-ready'); }
  })();
</script>
```

Key points:

- `startOnLoad: false` — control timing manually
- Render-then-hide order: every diagram is briefly visible during measurement, then css flip hides non-active ones in a single paint
- `data-processed="true"` is still set by Mermaid on each `<pre class="mermaid">`, so `check_runtime.mjs`'s readiness wait still works

### Gate rule reference (matches pre-commit)

| Rule ID | Detects |
|---------|---------|
| `MERMAID_SECURITY_LEVEL_REQUIRED` | `mermaid.initialize` / `%%{init}` missing explicit `securityLevel: strict\|sandbox` |
| `MERMAID_HTML_LABELS_TRUE` | `htmlLabels: true` |
| `MERMAID_SECURITY_LEVEL_LOOSE` | `securityLevel: loose\|antiscript` |
| `MERMAID_CLICK_CALLBACK` | `click <id> <callback>` |
| `MERMAID_CLICK_JAVASCRIPT_URL` | `click` with `javascript:` URL |
| `MERMAID_SECURE_OVERRIDE_EMPTY` | `secure: []` |

## Relationship to QA workflow

The runtime gate only verifies "diagram renders + no JS errors" — it **cannot** replace the security/syntax config gates. Full QA order:

1. `check_mermaid_insecure_config.py` → exit 0
2. `check_mermaid_syntax.mjs` → exit 0
3. `check_runtime.mjs` → exit 0 (zero `pageerror` / `console.error`, all `pre.mermaid[data-processed=true]`)

All three must pass before publishing HTML.
