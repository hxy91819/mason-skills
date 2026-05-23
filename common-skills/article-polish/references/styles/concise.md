# Concise Style Guide

Brief and to the point. Removes redundancy, tightens sentences, eliminates fluff.

## Characteristics

- **Length**: Shorter, denser prose
- **Words**: Strong verbs, minimal adverbs
- **Sentences**: Direct, no circumlocution
- **Paragraphs**: Focused, single idea

## When to Use

- Executive summaries
- Technical documentation
- When word count matters
- Content that feels bloated

## Polish Approach

### Do
- Remove redundant words and phrases
- Replace weak verbs + adverbs with strong verbs
- Delete filler words (very, really, actually, basically)
- Combine short, related sentences
- Cut unnecessary qualifiers

### Don't
- Remove essential context
- Make it cryptic or unclear
- Lose nuance or important details
- Create choppy, staccato rhythm

## Target Metrics

- Reduce word count by 10-30%
- Average sentence length: 15-20 words
- One main idea per paragraph
- Eliminate 90%+ of adverbs

## Example Transformations

### Redundancy Removal
**Before**: "In order to improve performance, we need to make changes to the current implementation that exists right now."

**After**: "To improve performance, change the current implementation."

**Reduction**: 19 words → 7 words (63% reduction)

### Strong Verbs
**Before**: "The system is able to handle a large number of requests very quickly."

**After**: "The system processes thousands of requests per second."

**Reduction**: 15 words → 8 words (47% reduction)

### Filler Elimination
**Before**: "Basically, what I'm trying to say is that we should actually consider using a different approach."

**After**: "Consider a different approach."

**Reduction**: 17 words → 4 words (76% reduction)

### Sentence Combining
**Before**: "The API returns JSON. The JSON contains user data. The data includes name and email."

**After**: "The API returns JSON containing user data (name and email)."

**Reduction**: 3 sentences → 1 sentence

## Common Redundancies to Cut

| Instead of | Use |
|------------|-----|
| at this point in time | now |
| due to the fact that | because |
| in order to | to |
| for the purpose of | for |
| in the event that | if |
| a large number of | many |
| is able to | can |
| it is important to note | (delete) |
| needless to say | (delete) |

## Prompt Additions

When using concise style, add to polish prompt:

```
Style: Concise - Brief and to the point
- Remove redundant words and phrases
- Replace weak verbs + adverbs with strong verbs
- Eliminate filler words (very, really, actually, basically, just)
- Combine short, related sentences
- Target 10-30% word count reduction
- Maintain clarity while being brief
- One main idea per paragraph
```
