# tech-doc-html

Turn technical design documents into interactive, single-file HTML pages that help readers understand system architecture, data flows, and implementation plans at a glance.

## What it does

Given a technical spec or design doc (markdown, notes, or inline text), the agent produces a **self-contained HTML file** with:

- Architecture and flow diagrams (Mermaid-first)
- Interactive SVG demos (sliders, step-by-step highlights, tab panels)
- Comparison tables, timelines, risk matrices, and summary metric bars
- A consistent visual design system (warm palette, responsive layout)

The goal is not pretty static docs — it is **interaction that helps people grasp the design**.

## When to use

Trigger this skill when you want to:

- Generate an HTML visualization from a technical design document
- Turn architecture diagrams into an interactive web page
- Create a shareable single-file explainer for a system or RFC
- Visualize implementation plans, trade-offs, or risk assessments

Example prompts: *"Turn this design doc into interactive HTML"*, *"Create an architecture diagram page"*, *"Visualize this RFC as a web page"*.

## Workflow overview

| Step | Action |
|------|--------|
| 1. Analyze | Identify content types: architecture, algorithms, comparisons, data flows, milestones, risks, metrics |
| 2. Pick components | Map each section to Mermaid, SVG, tables, tabs, or timelines |
| 3. Security | Load Mermaid sandbox rules before writing any diagram config |
| 4. Design | Apply tokens and layout from `references/design_system.md` |
| 5. Templates | Pull HTML/CSS/JS patterns from `references/component_patterns.md` |
| 6. Assemble | Combine into one file with inline styles and scripts |
| 7. Validate | Run Mermaid security gate + Playwright QA (zero console errors) |

## Directory layout

```
tech-doc-html/
├── SKILL.md                              # Agent instructions
├── assets/example_output.html            # Reference output (cache system design)
├── references/
│   ├── design_system.md                  # CSS variables, typography, page skeleton
│   ├── component_patterns.md             # Reusable HTML/CSS/JS templates
│   └── mermaid_security.md               # Sandbox config and diagram rules
└── scripts/security/
    ├── check_mermaid_insecure_config.py  # Pre-publish security gate
    └── check_mermaid_syntax.mjs          # Mermaid syntax helper
```

## Quality gates

Before shipping an HTML file, the skill enforces:

1. **Mermaid security** — `securityLevel: 'sandbox'` or `'strict'`, no unsafe `click` handlers or `javascript:` URLs
2. **Playwright QA** — zero console errors; interactive elements must actually work

See `assets/example_output.html` for the expected output quality bar.

## Requirements

- **Browser**: file opens directly; Mermaid diagrams need network access for CDN
- **Validation**: Python 3 for the security script; Playwright MCP for QA (when available)

## License

Part of [mason-skills](../../README.md). Skill design and instructions: [MIT License](../../LICENSE).

**Style inspiration:** Visual style inspired by [html-effectiveness](https://github.com/ThariqS/html-effectiveness) (Apache-2.0, Copyright Anthropic PBC). Original skill workflow — not affiliated with the upstream project. Apache-2.0 full text: [licenses/APACHE-2.0.txt](../../licenses/APACHE-2.0.txt).
