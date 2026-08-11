---
name: ask-oracle
description: Prepare a concise decision brief to seek an oracle's technical guidance.
disable-model-invocation: true
---

# Ask Oracle

Act only as a seeker: frame the problem, supply the decision context, and ask the oracle to provide the technical judgment. The brief must contain no agent-authored solution, recommendation, preference, or ranked options.

## Process

1. State the user's original goal faithfully and concisely. Keep the requested outcome and acceptance criteria here; move supporting facts to Decision context even when the user supplied them in the same message. Preserve exact wording only when its interpretation could affect the answer.
2. Gather the context already available from the conversation, repository, documents, and tool results. Include every known fact, constraint, prior decision, dependency, and piece of evidence that could change the oracle's advice. Include only the few unknowns most likely to change that advice.
3. Attribute any existing proposal to its source. Present it as context without endorsing, extending, or comparing it.
4. Return only the following concise Markdown brief:

```markdown
# Ask the Oracle

## Original request
<the user's request>

## Decision context
- <decision-relevant context>

## Request to the oracle
<the technical judgment or help being requested>
```

Give each fact one home. Prune background, implementation trivia, secondary unknowns, and anything that cannot affect the decision. State retained unknowns as unknowns instead of filling them with assumptions.

The brief is complete only when the original request is faithful, every known decision-changing context item is represented once, the requested help is explicit, and no technical proposal originates from the agent.
