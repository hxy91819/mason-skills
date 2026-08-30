# Fixture repository rules

- Keep every repository change inside this temporary repository.
- The accepted plan is under `docs/plan/`; use its planning script contract for plan state.
- Do not create branches or worktrees. Preserve the current `main` branch.
- Workers and validators must not commit. The orchestrator may commit validated Story and plan changes, then push only to the configured local `origin`.
- Do not use network resources other than the configured coding-agent provider. The repository test is `./check.sh`.
