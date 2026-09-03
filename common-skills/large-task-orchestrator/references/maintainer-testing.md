# Maintainer black-box regression

Read this reference only when changing `large-task-orchestrator`, its ACPX lifecycle assumptions, or its route configuration. Ordinary Story execution does not run this harness.

## Contract

[`../scripts/run_black_box_e2e.py`](../scripts/run_black_box_e2e.py) sends exactly one prompt containing one plain-text block with only the explicit Skill selection and the original fixture task; a second prompt or non-text block fails. Success criteria stay outside the prompt in the fixture and runner.

The live path:

- binds the orchestrator's discovered Skill registry to this exact source directory and inherits the real `HOME`, provider profile, and provider-owned conversation state;
- resolves each selected external role to an exact adapter argv before the outer prompt: the built-in `pi` route uses the harness-pinned `npx pi-acp@^0.0.31`, and any other name must be a registered structured argv alias in `acpx config show` whose argv is a non-empty list of printable strings; command-form aliases, unknown builtins, and control characters fail closed;
- writes the logical agent name as the positional route candidate — `--agent` override sessions do not persist `agent_argv`, so only positional registered/builtin aliases satisfy the exact route check;
- creates a temporary Git repository, valid one-Story plan, and local bare remote;
- keeps the validator's `./check.sh` gate as an ACPX `execute` canary, so a validator dispatched with `--approve-reads` fails visibly instead of being mistaken for a clean direction review;
- records the route argv and the project config SHA-256 before dispatch; these expected values never come from actual session records;
- after the outer process exits and before delivery/session validation, rechecks the project orchestrator config for exact path, non-symlink type, mode, bytes, and SHA-256;
- verifies the artifact, plan `done` state, distinct sessions, an explicitly persisted non-empty string-array `agent_argv`/`agentArgv` exactly equal to the resolved route argv, provider continuity, commit, and push; command text is accepted only by best-effort cleanup of otherwise unknown records, never as route evidence;
- requires rolling-history attempt start/finish multisets to equal every prompted session discovered at the fixture cwd; an extra closed session without a prompt is still a failure;
- snapshots and cleans every session record at the fixture cwd, not only sessions that passed route/history validation, while preserving all pre-run records.
- also removes the exact session lock, legacy queue artifacts, and generation-scoped Unix queue sockets; Windows named-pipe cleanup remains platform-specific and is reported as residual risk.

The orchestrator's route preflight is the bounded ACP `sessions new` initialize/session handshake. The harness deliberately does not add `--help` or `--version` to a long-running stdio adapter: `codex-acp` and similar servers may ignore those tokens and wait for ACP stdin indefinitely. If a provider documents a separate terminating help/version command, it is optional diagnostic evidence and is outside this harness's route proof.

The parser unit suite (`tests/test_read_acpx_result.py`) feeds a refused permission stream and its non-zero ACPX exit through `scripts/read_acpx_result.py`; it requires `permission_policy_mismatch` and `acpx-exit-nonzero` to block any validator conclusion.

`--live` uses real models and gives the outer orchestrator ACPX `--approve-all`. The temporary repository and local remote are not an OS sandbox. Run it only in a trusted profile with explicit authorization, and pass `--acknowledge-broad-permissions` to confirm that boundary.

## Run

From this Skill directory:

```bash
python3 scripts/run_black_box_e2e.py --help
python3 scripts/run_black_box_e2e.py --validate-fixture
python3 scripts/run_black_box_e2e.py \
  --live \
  --acknowledge-broad-permissions \
  --worker-agent pi \
  --validator-agent pi
```

The built-in `pi` route is always available with the harness-pinned `pi-acp` spec. Any other agent name must be a registered structured argv alias in `acpx config show` whose `argv` is a non-empty list of printable strings; the harness writes the logical agent name as the positional route candidate and requires persisted session argv to equal the resolved argv exactly. Command-form aliases, unknown builtins, and control characters fail before the outer prompt; `--agent` override sessions never persist `agent_argv`, so they can never satisfy the route proof. The harness constructs no sandbox launcher: role isolation comes only from the temporary repository and local bare remote, so treat both selected roles as running with the provider's full process permissions inside the fixture. The host Skill path must resolve to this source tree; use `--skill-registry` only to name the registry the selected orchestrator actually loads, not to bypass the binding check.

Successful runs remove the temporary workspace unless `--keep-temp` is set. Failed runs retain it, while still snapshotting and cleaning this run's ACPX sessions. Use `--output-dir` to retain evidence after a successful run. Provider-owned conversation history is outside the ACPX cleanup boundary.
