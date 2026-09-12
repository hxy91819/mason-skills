# Writing preferences

**Style presets** — control the voice and tone of the polished output:

| Value | Description | Effect |
|-------|-------------|--------|
| `natural` | Smooth, natural flow (default) | Fixes awkward phrasing while preserving author's voice |
| `concise` | Brief and to the point | Removes redundancy, tightens sentences |
| `vivid` | Lively and engaging | Adds sensory details, strong verbs, vivid imagery |
| `formal` | Professional and structured | Elevates register, removes colloquialisms |
| `conversational` | Casual and approachable | Friendly tone, as if speaking to reader |
| `academic` | Scholarly and rigorous | Formal register, precise terminology |
| `storytelling` | Narrative-driven | Smooth transitions, engaging pacing |
| `elegant` | Refined and polished | Careful word choices, rhythmic prose |
| `chinese` | Anti-AI Chinese prose (opt-in) | Strips AI fingerprints from Chinese writing; auto-picks a 直接型/分析型 benchmark by genre. Only when explicitly selected |

Custom style descriptions are also accepted, e.g., `--style "poetic and contemplative"`.

**Chinese module (`style: chinese`)**: A dedicated rule set for Chinese prose that removes the four-layer AI fingerprints (思维模式 / 句式 / 词汇 / 结构). Read [Chinese style integration](chinese-style.md) only when explicitly selected.

**Polish goals** — what aspect to focus on during polishing:

| Value | Description | Effect |
|-------|-------------|--------|
| `improve` | General improvement (default) | Fix awkward phrasing, improve clarity, enhance flow |
| `simplify` | Make it easier to read | Reduce complexity, shorter sentences, clearer structure |
| `strengthen` | Make it more impactful | Stronger verbs, clearer arguments, better pacing |
| `condense` | Reduce word count | Remove fluff, tighten expression, keep only essentials |
| `expand` | Add depth and detail | Elaborate on key points, add examples, enrich content |
| `rewrite` | Significant reworking | Restructure sentences and paragraphs for better effect |

Custom goal descriptions are also accepted, e.g., `--goal "more persuasive and energetic"`.

**Audience presets**:

| Value | Description | Effect |
|-------|-------------|--------|
| `general` | General readers (default) | Plain language, explain specialized terms |
| `technical` | Developers / engineers | Keep technical terms, explain only domain-specific jargon |
| `academic` | Researchers / scholars | Formal register, assume domain knowledge |
| `business` | Business professionals | Results-focused, action-oriented language |
| `beginner` | Novice readers | Simple vocabulary, clear explanations, patient tone |
| `expert` | Domain experts | Dense information, minimal explanation, precise terms |

Custom audience descriptions are also accepted, e.g., `--audience "startup founders interested in AI"`.
