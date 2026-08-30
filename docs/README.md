# Docs

This directory holds maintained repository design notes and generated snapshots. Skill source remains under `common-skills/`.

| Path | What it is |
| --- | --- |
| [large-task-system-design.md](large-task-system-design.md) | Shared design principles and boundaries for planning and orchestrating large tasks |
| [largeplan-example/](largeplan-example/) | Latest `large-task-planning` portal for the token-login prompt |

Re-run the example from the repository root:

```bash
python3 common-skills/large-task-planning/examples/token-login/run_example.py
```

Each run also archives a copy under `common-skills/large-task-planning/examples/token-login/runs/`.
