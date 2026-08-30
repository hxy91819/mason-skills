# Maintainer black-box regression

Read this reference only when changing `large-task-orchestrator`, its ACPX lifecycle assumptions, or its route configuration. Ordinary Story execution does not run this harness.

## Contract

[`../scripts/run_black_box_e2e.py`](../scripts/run_black_box_e2e.py) sends one fixed prompt containing only the explicit Skill selection and the original fixture task. Success criteria stay outside the prompt in the fixture and runner.

The live path:

- binds the orchestrator's discovered Skill registry to this exact source directory;
- inherits the actual `HOME` and provider profile;
- creates a temporary Git repository, valid one-Story plan, and local bare remote;
- applies a project-local worker/validator route;
- verifies the artifact, plan `done` state, distinct sessions, actual adapter argv, provider continuity, commit, and push;
- verifies one delivered rolling-history run whose attempt IDs, roles, agents, and provider IDs match the actual worker/validator sessions and whose real remote HEAD matches delivery, then archives that local history before workspace deletion;
- snapshots this run's ACPX record/event streams before closing and deleting only those records.

`--live` uses real models and gives the outer orchestrator ACPX `--approve-all`. The temporary repository and local remote are not an OS sandbox. Run it only in a trusted profile with explicit authorization, and pass `--acknowledge-broad-permissions` to confirm that boundary.

## Run

From this Skill directory:

```bash
python3 scripts/run_black_box_e2e.py --help
python3 scripts/run_black_box_e2e.py --validate-fixture
python3 scripts/run_black_box_e2e.py \
  --live \
  --acknowledge-broad-permissions \
  --worker-agent codexp \
  --validator-agent codexp
```

Use registered ACPX agent names. A custom alias must resolve to structured `argv` in `acpx config show`; the runner compares that exact argv with each persisted session record. The host Skill path must resolve to this source tree; use `--skill-registry` only to name the registry the selected orchestrator actually loads, not to bypass the binding check.

Successful runs remove the temporary workspace unless `--keep-temp` is set. Failed runs retain it, while still snapshotting and cleaning this run's ACPX sessions. Use `--output-dir` to retain evidence after a successful run. Provider-owned conversation history is outside the ACPX cleanup boundary.
