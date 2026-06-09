---
name: article-workflow-skill-maker
description: Meta skill for turning a manually executed article workflow phase into a reusable `article-workflow-*` skill. Use when the user says they manually followed the article optimization workflow overview, adjusted through conversation, checked the result, and now wants to summarize the current session into a workflow skill.
priority: P2
---

# Article Workflow Skill Maker

This is a meta skill for the `article-workflow-*` series. It does not directly optimize articles; instead, it distills a manually executed, conversation-adjusted, and result-verified article workflow phase into a reusable skill.

Applicable pattern:

1. The user first follows the article optimization workflow overview to manually execute a phase.
2. During execution, the user supplements author decisions, corrects deliverables, and checks results through conversation.
3. The user confirms this workflow is reusable.
4. This skill summarizes the current session and crystallizes it into a new `article-workflow-*` skill.

## Core Principles

- Distill from real sessions; do not design workflows from scratch.
- Prioritize recording actual inputs, outputs, author decision points, and verification methods that have occurred.
- Turn "requires author judgment" parts into dialog questions; do not embed them in the final deliverable document.
- If the phase contains ambiguities that would block progress or affect the deliverable's direction, scope, facts, style, or downstream inputs, the new skill must require the agent to proactively ask the user for confirmation rather than guessing, silently recording, or waiting for the user to correct.
- If the phase has no ambiguities requiring author confirmation, do not force dialog questions or interrupt the user just for formality.
- Every generated workflow skill must include a sub-agent review step; the sub-agent only raises goal-alignment and deliverable-quality review opinions, and the main agent decides whether to adopt them.
- The new skill should serve the next execution, not recapitulate the current article's content.
- Maintain the same prefix as the article optimization workflow: `article-workflow-`.

## Input

Needs to read or leverage:

- The article optimization workflow overview
- Phase goals, supplementary requirements, and correction feedback raised by the user in the current session
- Deliverables actually created or modified in the current session
- If sibling skills already exist, read adjacent skills for style reference, e.g.:
  - `../brief/SKILL.md`

If the current session context is insufficient, confirm with the user:

- Which Phase to crystallize
- The new skill's name
- What the input files are
- What the output files are
- Which decisions, if they exist, must be collected via dialog
- Which ambiguities, if they exist, must be proactively confirmed with the user
- Which content must not be written into the final deliverable

## Output

Create or update:

```text
../<phase-name>/SKILL.md
```

The new skill must include:

- frontmatter: `name`, `description`, optional `priority`
- Trigger scenarios
- Input and output
- Core principles
- Workflow
- Author decision dialog (only when the phase genuinely involves author judgment)
- Rules for proactively confirming ambiguities (only when ambiguities exist that would affect progress or deliverable quality)
- Final deliverable structure
- Sub-agent review step
- Verification checklist
- Relationship to the `article-workflow-*` series

## Execution Flow

### Step 1: Identify the Phase

First confirm which phase of the article optimization workflow overview the current session is crystallizing.

Record:

- Phase number and name
- Original goal
- Recommended input
- Recommended output
- Requirements the user added or revised during actual execution

### Step 2: Review the Current Session

Distill from the current session:

- How the user initially described the task
- Which files the agent actually read
- Which files the agent actually wrote
- What author decisions arose mid-process
- Which decisions were filled in through conversation
- Which workflow design choices the user corrected
- Why the final result was considered acceptable

Focus on finding reusable patterns, not on recording the article content itself.

### Step 3: Define the New Skill's Boundaries

Clarify for the new skill:

- Which phase problem it solves
- What problems it does not solve
- Whether it is allowed to edit the main text
- Whether it is allowed to generate intermediate documents
- Whether it must ask the author
- Which ambiguities, when encountered, require proactively asking the author; if no such points exist, do not force questions
- What file it ultimately writes
- Which goal-alignment questions the sub-agent should review after deliverable completion

For the article optimization workflow, defaults are:

- AI does diagnosis, organization, and execution
- The author makes judgments
- Unconfirmed author decisions that would affect progress are collected via dialog
- Ambiguities are proactively confirmed with the user, not advanced by guessing; but do not force questions for phases that are already clear
- Unless the user explicitly requests, do not write unresolved questions into the final deliverable
- The sub-agent only raises deliverable review opinions; the main agent decides which suggestions to adopt

### Step 4: Design Dialog Questions

If the phase involves author judgment that would affect the deliverable's direction, scope, facts, style, or downstream phase inputs, you must design `AskQuestion` questions.

If no such ambiguities exist, explicitly state: "This phase does not require mandatory author confirmation; the agent may execute directly and explain assumptions in the final response." Do not fabricate questions just to satisfy the template.

Dialog questions should:

- Collect the 3-8 most critical decisions at once
- Offer clear options per question, not requiring the author to write long prose
- Include an "Other / need to add more" escape option
- Derive from the real session, not from generic writing templates
- Cover all ambiguities that would affect the deliverable's direction, scope, facts, style, or downstream phase inputs
- Not re-ask information already provided by the brief, author decision files, or the user's current request
- Not ask about low-risk details that do not affect this phase's progress; such content can be recorded in intermediate notes or the final response

Example question types:

- Final direction
- Target audience
- Technical detail ratio
- Whether to acknowledge risks
- Evidence presentation style
- Which material enters the main text
- Which content is only a footnote, personal wrap-up, or source material

### Step 5: Write the Skill

Create `../<phase-name>/SKILL.md`.

Naming rules:

- Must use the `article-workflow-` prefix.
- Name uses lowercase English and hyphens.
- Name should express the phase, not the specific article topic.

Writing rules:

- Keep SKILL.md concise, typically no more than 500 lines.
- Description must include trigger scenarios.
- Do not write article-specific conclusions unless as examples.
- Keep file references to one level; do not design deep reference chains.
- The workflow must include a "launch sub-agent for review" step.
- The review step must state: the sub-agent only reviews goal alignment and deliverable quality; the main agent decides whether to adopt suggestions.
- The workflow must state: when encountering ambiguities that would affect progress or deliverable quality, the agent must proactively use a dialog to ask the user for confirmation before writing the final deliverable; if no such ambiguities exist, do not force questions.

### Step 6: Launch Sub-Agent Review of the New Skill

After writing the new skill, the main agent must launch a read-only sub-agent review. The sub-agent only raises review opinions, checking whether the new skill is reusable, aligned with the current workflow phase, and correctly preserves necessary author-decision confirmation rules and review steps.

Sub-agent review focus:

- Whether the new skill comes from a real session rather than being designed from scratch
- Whether there are clear inputs, outputs, and prohibitions
- Whether necessary author decisions are turned into dialog flows
- Whether it requires the agent to proactively confirm ambiguities that would affect progress, and does not force unnecessary questions
- Whether it explicitly prohibits writing critical uncertainties only into notes or waiting for the user to correct
- Whether it includes a sub-agent review step
- Whether it avoids hard-coding the current article's specific conclusions as general rules
- Whether it is consistent with the `article-workflow-*` series naming and structure

After the main agent receives the review:

- Judge for itself which opinions are valid
- Only adopt suggestions that improve the skill's reusability
- Do not introduce article-specific content due to review opinions
- If adopting, update the new skill
- If not adopting, briefly explain why in the final response

### Step 7: Verify

After completion, check:

- Whether the skill name conforms to `article-workflow-*`
- Whether the description explains when to trigger
- Whether there are clear inputs, outputs, and prohibitions
- Whether necessary author decisions are turned into dialog flows
- Whether it includes a sub-agent review step
- Whether it avoids hard-coding the current article's specific conclusions as general rules
- Whether the sub-agent review has been completed and the main agent has judged adoption
- Whether recently edited files have been read and lints checked

## Recommended Skill Template

```markdown
---
name: article-workflow-<phase-name>
description: <Phase N: what it does. Use when...>
priority: P2
---

# Article Workflow <Phase Name>

This is Phase N of the `article-workflow-*` series.

## Trigger Scenarios

## Input and Output

## Core Principles

- When encountering ambiguities that would affect this phase's deliverable direction, scope, facts, style, or downstream phase inputs, proactively use a dialog to ask the user for confirmation; do not guess.
- If no such ambiguities exist, do not force questions for formality; execute directly and explain key assumptions in the final response.

## Workflow

### Step 1: Read Source Materials

### Step 2: Form Diagnosis

### Step 3: Collect Author Decisions via Dialog (if needed)

If ambiguities exist that would affect progress or deliverable quality, first compress them into a few multiple-choice questions and ask the user for confirmation; only write the final deliverable after confirmation. If no such ambiguities exist, skip this step.

### Step 4: Write Final Deliverable

### Step 5: Launch Sub-Agent for Review

After the deliverable is written, the main agent must launch a read-only sub-agent for goal-alignment review.

The sub-agent only raises review opinions, focusing on:

- Whether the deliverable aligns with this phase's goals
- Whether input, output, and prohibition rules are followed
- Whether author decisions confirmed via dialog are preserved (if any)
- Whether ambiguities that should be proactively confirmed with the user are missing, or unnecessary confirmations are forced
- Whether key materials, judgments, or evidence lines are missing

After the main agent receives the review:

- Judge for itself which opinions are valid
- Only adopt suggestions consistent with this phase's goals
- If adopting, update the deliverable
- If not adopting, briefly explain why in the final response

### Step 6: Verify

## Output Style

Use English unless the user specifies otherwise.

## Relationship to the Workflow
```

## Existing Series Naming

- `article-workflow-brief`: Phase 0, Edit Brief

It is recommended to continue using:

- `article-workflow-clean-sources`
- `article-workflow-section-review`
- `article-workflow-evidence-pool`
- Phase 3 (author self-read and direct editing) is not recommended as a standalone skill; the author directly edits `.article-workflow/00-cleaned-sources/`
- `article-workflow-ai-edit-pass`
- `article-workflow-global-review`
- `article-workflow-main-draft`
- `article-workflow-visual-plan`
- `article-workflow-style-bible`
- `article-workflow-polish`
- `article-workflow-final-review`