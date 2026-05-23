---
name: first-time-setup
description: First-time setup flow for article-polish preferences
---

# First-Time Setup

## Overview

When no EXTEND.md is found, guide user through preference setup.

**BLOCKING OPERATION**: This setup MUST complete before ANY polishing. Do NOT:
- Start polishing content
- Ask about files or output paths
- Proceed to any workflow steps

ONLY ask the questions in this setup flow, save EXTEND.md, then continue.

## Setup Flow

```
No EXTEND.md found
        |
        v
+---------------------+
| AskUserQuestion     |
| (all questions)     |
+---------------------+
        |
        v
+---------------------+
| Create EXTEND.md    |
+---------------------+
        |
        v
    Continue polishing
```

## Questions

**Language**: Use user's input language or saved language preference.

Use AskUserQuestion with ALL questions in ONE call:

### Question 1: Polish Mode

```yaml
header: "Mode"
question: "Default polish mode?"
options:
  - label: "Normal (Recommended)"
    description: "Analyze content first, then polish"
  - label: "Quick"
    description: "Direct polish, no analysis"
  - label: "Refined"
    description: "Full workflow: analyze → polish → review → finalize"
```

### Question 2: Target Audience

```yaml
header: "Audience"
question: "Default target audience?"
options:
  - label: "General readers (Recommended)"
    description: "Plain language, explain specialized terms"
  - label: "Technical"
    description: "Developers/engineers, keep technical terms"
  - label: "Academic"
    description: "Formal register, precise terminology"
  - label: "Business"
    description: "Results-focused, action-oriented"
  - label: "Beginner"
    description: "Simple vocabulary, clear explanations"
  - label: "Expert"
    description: "Dense information, minimal explanation"
```

Note: User may type a custom audience description.

### Question 3: Writing Style

```yaml
header: "Style"
question: "Preferred writing style?"
options:
  - label: "Natural (Recommended)"
    description: "Smooth flow, preserve author voice"
  - label: "Concise"
    description: "Brief and to the point, remove redundancy"
  - label: "Vivid"
    description: "Lively and engaging, sensory details"
  - label: "Formal"
    description: "Professional and structured"
  - label: "Conversational"
    description: "Casual and approachable"
  - label: "Academic"
    description: "Scholarly and rigorous"
  - label: "Storytelling"
    description: "Narrative-driven, engaging pacing"
  - label: "Elegant"
    description: "Refined and polished, careful word choices"
```

Note: User may type a custom style description.

### Question 4: Polish Goal

```yaml
header: "Goal"
question: "What do you usually want when polishing?"
options:
  - label: "Improve (Recommended)"
    description: "General improvement: fix awkwardness, enhance flow"
  - label: "Simplify"
    description: "Make easier to read, reduce complexity"
  - label: "Strengthen"
    description: "More impactful, stronger verbs, clearer arguments"
  - label: "Condense"
    description: "Reduce word count, remove fluff"
  - label: "Expand"
    description: "Add depth and detail, elaborate key points"
  - label: "Rewrite"
    description: "Significant restructuring for better effect"
```

Note: User may type a custom goal description.

### Question 5: Save Location

```yaml
header: "Save"
question: "Where to save preferences?"
options:
  - label: "User (Recommended)"
    description: "$HOME/.mason-skills/ (all projects)"
  - label: "Project"
    description: ".mason-skills/ (this project only)"
```

## Save Locations

| Choice | Path | Scope |
|--------|------|-------|
| User | `$HOME/.mason-skills/article-polish/EXTEND.md` | All projects |
| Project | `.mason-skills/article-polish/EXTEND.md` | Current project |

## After Setup

1. Create directory if needed
2. Write EXTEND.md with selected values
3. Confirm: "Preferences saved to [path]"
4. Mention: "You can add custom rules to EXTEND.md anytime. See the `custom_rules` section in the file for the format."
5. Continue with polishing using saved preferences

## EXTEND.md Template

```yaml
default_mode: [quick/normal/refined]
audience: [general/technical/academic/business/beginner/expert/custom]
style: [natural/concise/vivid/formal/conversational/academic/storytelling/elegant]
goal: [improve/simplify/strengthen/condense/expand/rewrite]

# Custom rules (optional) — add your own polish instructions here
# custom_rules:
#   - "Prefer active voice"
#   - "Keep paragraphs to 3-4 sentences"
```

## Modifying Preferences Later

Users can edit EXTEND.md directly or delete it to trigger setup again.
