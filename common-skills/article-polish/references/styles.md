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
