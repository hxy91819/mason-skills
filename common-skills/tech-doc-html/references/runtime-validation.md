# HTML runtime validation

## QA validation — headless browser (required)

After Mermaid gate passes, generated HTML **must** pass a runtime smoke check to ensure no JS / Mermaid errors at render time. The skill ships a no-MCP gate (`scripts/qa/check_runtime.mjs`) that is the recommended primary path; richer interaction tests via Playwright MCP are an optional follow-up.

### Primary gate: `check_runtime.mjs` (recommended)

A self-contained Node + Playwright script. Loads each HTML in headless Chromium, waits for all `<pre class="mermaid">` to reach `data-processed=true`, then asserts zero `pageerror` and zero `console.error`. Catches everything the security/syntax gates miss — JS SyntaxError preventing handler binding, Mermaid `translate(undefined, NaN)` positioning errors from hidden containers (see [Mermaid security](mermaid_security.md) "Rendering pitfalls"), unhandled rejections, late console errors after `networkidle`.

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
