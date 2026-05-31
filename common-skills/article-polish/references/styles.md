# Style Gallery for article-polish

Complete guide to polish styles.

## Core Styles

| Style | Best For | Effect |
|-------|----------|--------|
| `natural` | General use | Smooth flow, preserves voice |
| `concise` | Word count limits | Removes redundancy, tightens |
| `vivid` | Dry content | Adds imagery, strong verbs |
| `formal` | Professional docs | Elevates register |

## Extended Styles

| Style | Best For | Effect |
|-------|----------|--------|
| `conversational` | Casual blogs | Friendly, approachable |
| `academic` | Papers, research | Scholarly, rigorous |
| `storytelling` | Narratives | Engaging pacing |
| `elegant` | Premium content | Refined, polished |

## Language-Specific Styles

| Style | Best For | Effect |
|-------|----------|--------|
| `chinese` | Chinese prose | Strips four-layer AI fingerprints; auto-picks 直接型/分析型 benchmark |

## Style Details

### Natural
Smooth, effortless flow. Fixes awkward phrasing while preserving the author's unique voice.

**When to use**: Default choice, general blog posts, when author has distinct voice

[Full guide: styles/natural.md](styles/natural.md)

### Concise
Brief and to the point. Removes redundancy, tightens sentences, eliminates fluff.

**When to use**: Executive summaries, documentation, when word count matters

**Target**: 10-30% word count reduction

[Full guide: styles/concise.md](styles/concise.md)

### Vivid
Lively and engaging. Adds sensory details, strong verbs, vivid imagery.

**When to use**: Storytelling, product descriptions, dry content that needs life

[Full guide: styles/vivid.md](styles/vivid.md)

### Formal
Professional and structured. Elevates register, removes colloquialisms.

**When to use**: Academic papers, business reports, official documentation

[Full guide: styles/formal.md](styles/formal.md)

### Conversational
Casual and approachable. Friendly tone, as if speaking to reader.

**When to use**: Casual blogs, newsletters, community content

**Characteristics**:
- Use "you" and "we" naturally
- Contractions OK
- Friendly, approachable
- Explain without talking down

### Academic
Scholarly and rigorous. Formal register, precise terminology.

**When to use**: Research papers, academic articles, technical reports

**Characteristics**:
- Formal register
- Precise terminology
- Objective tone
- Citation-aware
- Complex clauses acceptable

### Storytelling
Narrative-driven. Smooth transitions, engaging pacing.

**When to use**: Case studies, journey posts, narrative content

**Characteristics**:
- Smooth transitions
- Engaging pacing
- Clear narrative arc
- Scene-setting
- Emotional resonance

### Elegant
Refined and polished. Careful word choices, rhythmic prose.

**When to use**: Premium content, thought leadership, literary pieces

**Characteristics**:
- Careful word choices
- Rhythmic prose
- Aesthetic refinement
- Sophisticated without being pretentious

### Chinese (反 AI 中文)
Removes the stable fingerprints of AI-generated Chinese across four layers — 思维模式 (assumed-balance, escalation formulas, conclusion-first), 句式, 词汇, and 结构 — and rewrites toward a human, direct voice.

**When to use**: Any Chinese article, essay, opinion piece, or analysis — **opt-in only** (explicitly select `--style chinese`; the default style preserves the author's voice even for Chinese)

**Characteristics**:
- Auto-selects a benchmark per genre: **直接型** (narrative/opinion) or **分析型** (analytical/data-driven)
- 具体胜过抽象, 断言需要支撑, 信任读者 (no redundant restatement)
- Natural paragraphs over bullet lists; detail follows information, not symmetry
- 中英文之间加空格, terms use 中英双语 on first mention, zero emoji

[Full rules: zh/anti-ai.md](zh/anti-ai.md)

## Custom Styles

You can also provide custom style descriptions:

```bash
/polish article.md --style "poetic and contemplative"
/polish article.md --style "punchy and direct"
/polish article.md --style "warm and encouraging"
```

## Style Selection Guide

### By Content Type

| Content Type | Recommended Style |
|--------------|-------------------|
| Technical tutorial | natural, concise |
| API documentation | concise, formal |
| Product announcement | vivid, storytelling |
| Research summary | academic, formal |
| Opinion piece | natural, vivid |
| Case study | storytelling, vivid |
| Newsletter | conversational, natural |
| Executive summary | concise, formal |

### By Goal

| Goal | Recommended Style |
|------|-------------------|
| Fix awkwardness | natural |
| Reduce length | concise |
| Add engagement | vivid, storytelling |
| Professionalize | formal, academic |
| Simplify | natural, conversational |
