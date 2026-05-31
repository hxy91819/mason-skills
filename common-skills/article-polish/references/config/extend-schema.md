# EXTEND.md Schema for article-polish

## Format

EXTEND.md uses YAML format:

```yaml
# Default polish mode
default_mode: normal  # quick | normal | refined

# Target audience (affects vocabulary depth and register)
audience: general  # general | technical | academic | business | beginner | expert | or custom string

# Polish style preference
style: natural  # natural | concise | vivid | formal | conversational | academic | storytelling | elegant | chinese | or custom string

# Polish goal
goal: improve  # improve | simplify | strengthen | condense | expand | rewrite | or custom string

# Word count threshold to trigger chunked polish
chunk_threshold: 4000

# Max words per chunk
chunk_max_words: 5000

# Custom rules (applied during every polish)
custom_rules:
  - "Prefer active voice"
  - "Break sentences longer than 25 words"
```

## Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `default_mode` | string | `normal` | Default polish mode (`quick` / `normal` / `refined`) |
| `audience` | string | `general` | Target reader profile (`general` / `technical` / `academic` / `business` / `beginner` / `expert` / custom) |
| `style` | string | `natural` | Writing style (`natural` / `concise` / `vivid` / `formal` / `conversational` / `academic` / `storytelling` / `elegant` / `chinese` / custom) |
| `goal` | string | `improve` | Polish goal (`improve` / `simplify` / `strengthen` / `condense` / `expand` / `rewrite` / custom) |
| `chunk_threshold` | number | `4000` | Word count threshold to trigger chunked polish |
| `chunk_max_words` | number | `5000` | Max words per chunk |
| `custom_rules` | array | `[]` | Specific rules to always apply during polishing |
