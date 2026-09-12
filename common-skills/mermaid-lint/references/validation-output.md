# Validator output and troubleshooting

### Output structure

```json
{
  "status": "error",
  "summary": {
    "files": 2,
    "total_blocks": 7,
    "valid_blocks": 6,
    "error_blocks": 1,
    "warnings": 1,
    "unmatched_patterns": []
  },
  "files": [
    {
      "file": "/abs/path/architecture.md",
      "total_blocks": 5,
      "valid_blocks": 4,
      "errors": [
        {
          "block_index": 2,
          "line_start": 45,
          "line_end": 58,
          "diagram_type": "graph TD",
          "mermaid_source": "graph TD\n    A[Start --> B[End]",
          "error_message": "Parse error on line 2: ...",
          "error_line_in_block": 2,
          "error_line_in_file": 46,
          "timed_out": false
        }
      ],
      "warnings": [
        { "line": 88, "message": "Mermaid code block opened at line 88 is never closed before end of file; skipped." }
      ],
      "blocks": [
        { "index": 1, "line_start": 20, "line_end": 35, "diagram_type": "graph TD", "valid": true }
      ]
    }
  ]
}
```

`error_line_in_file` is already an absolute line number in the source file. Use it directly instead of recomputing from `line_start`.

`warnings` do not change the exit code to 1, but still handle them and report them — an unterminated code block is a document defect in its own right.

`timed_out` set to `true` means rendering timed out or the render process crashed. That is not necessarily a syntax error and is usually an oversized diagram. Flag these for the user to confirm manually rather than trying to "fix" them.


### Common error patterns

| Error message contains | Usual cause | Fix direction |
|---|---|---|
| `Expecting 'SQE'` | unclosed `[` | add the missing `]` |
| `Expecting 'PE'` | unclosed `(` | add the missing `)` |
| `Expecting 'DIAMOND_STOP'` | unclosed `{` | add the missing `}` |
| `Unexpected token` | illegal character or reserved word | quote the text that needs escaping |
| `Lexer error` / `Lexical error` | illegal character | remove or escape it |
| `Parse error on line N` | syntax error on block-relative line N | use `error_line_in_file` to locate it in the source |
| `Invalid date:...` | gantt date does not match `dateFormat` | rewrite the date in the declared format |
| `Trying to inactivate an inactive participant` | unbalanced activate/deactivate in sequenceDiagram | add the missing `activate` or drop the extra `deactivate` |
| `Negative values are not allowed` | negative value in a pie chart | use non-negative values |
| `Edge limit exceeded` | diagram exceeds mermaid's edge cap | split it into several diagrams |

## Environment variables

Not needed in normal use; these exist for troubleshooting.

- `MERMAID_LINT_BLOCK_TIMEOUT_MS`: render timeout for a single diagram. Default `20000`.
- `MERMAID_LINT_SESSION_OVERHEAD_MS`: budget for fixed per-session cost such as browser startup. Default `15000`. Raise it on machines with slow cold starts.
