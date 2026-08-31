# Maintainer black-box regression

Read this reference only when changing `large-task-orchestrator`, its ACPX lifecycle assumptions, or its route configuration. Ordinary Story execution does not run this harness.

## Contract

[`../scripts/run_black_box_e2e.py`](../scripts/run_black_box_e2e.py) sends exactly one prompt containing one plain-text block with only the explicit Skill selection and the original fixture task; a second prompt or non-text block fails. Success criteria stay outside the prompt in the fixture and runner.

The live path:

- binds the orchestrator's discovered Skill registry to this exact source directory and inherits the real `HOME`, `CODEX_HOME`, and provider profile;
- reads each selected registered ACPX alias before the outer prompt and accepts only the statically provable `/usr/bin/env <CODEX_HOME assignment?> <CODEX_PATH assignment> <npx|absolute trusted npx> [-y|--yes] @agentclientprotocol/codex-acp...` structured `argv` shape: the assignments must be one contiguous prefix in that order (`CODEX_HOME` is optional and `CODEX_PATH` is required), `CODEX_PATH` must name an absolute executable regular file, the runner token must be the literal `npx` used by real aliases or exactly the absolute `npx` selected by `shutil.which("npx")` in the inherited environment, and the adapter must be the first and last positional runner argument; no `NAME=value` token may occur after the runner, and argv tokens containing control characters (including newline or NUL) fail closed. Alias-level `PATH`, Node/npm/loader variables, arbitrary assignments, other relative or absolute runners, arbitrary executables, shells, dynamic wrappers, adapter tail arguments, builtin/command-form routes, and non-Codex adapters fail closed because decorative tokens do not prove an enforceable capability boundary;
- creates `<workspace>/capability-launchers/` outside the fixture repository as a non-symlink `0700` directory, with separate non-symlink `0500` launchers: worker forces `workspace-write` plus `sandbox_workspace_write.network_access=false`, validator forces `read-only`;
- preserves the registered base argv verbatim as provenance, then derives each final role argv with exactly two controlled substitutions for the normal literal-`npx` alias: `CODEX_PATH` becomes the role launcher and `npx` becomes the trusted absolute runner; it writes that complete final command as the candidate's `acpx_command`, while profiles continue to match the logical alias;
- creates a temporary Git repository, valid one-Story plan, and local bare remote;
- keeps the validator's `./check.sh` gate as an ACPX `execute` canary, so a validator dispatched with `--approve-reads` fails visibly instead of being mistaken for a clean direction review;
- records base/final argv, launcher paths and SHA-256 values, and the project config SHA-256 before dispatch; these expected values never come from actual session records;
- after the outer process exits and before delivery/session validation, rechecks both launchers and the project orchestrator config for exact path, non-symlink type, mode, bytes, and SHA-256;
- verifies the artifact, plan `done` state, distinct sessions, an explicitly persisted non-empty string-array `agent_argv`/`agentArgv` exactly equal to the final adapter argv, provider continuity, commit, and push; command text is accepted only by best-effort cleanup of otherwise unknown records, never as route evidence;
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
  --worker-agent codexp \
  --validator-agent codexp
```

Use registered ACPX agent names whose `acpx config show` entry has the real supported `/usr/bin/env <CODEX_HOME assignment?> <CODEX_PATH assignment> npx [-y|--yes] @agentclientprotocol/codex-acp...` structure; users do not need to rewrite that alias. `CODEX_HOME` may be omitted, but when present it precedes `CODEX_PATH`; after the runner, only the adapter package itself is accepted—no adapter tail argument, `NAME=value` token, or control character. An already-absolute runner is also accepted only when it exactly equals `shutil.which("npx")` from the inherited live environment. The alias may set only `CODEX_HOME` and `CODEX_PATH`, so `PATH`, Node/npm/loader variables, other assignments, and every other relative or absolute runner fail closed instead of creating a dynamic wrapper surface. The runner preserves the registered base argv verbatim as provenance, replaces `CODEX_PATH` with the role launcher, canonicalizes the runner token to the trusted absolute `npx`, writes that final command into the project route, and requires persisted session argv to equal it exactly. A route that merely carries decorative `CODEX_PATH` or adapter tokens, or otherwise lacks this independently enforceable Codex launcher shape, fails before the outer prompt; there is no shell, wrapper, builtin, command-text route-evidence, or non-Codex fallback. The host Skill path must resolve to this source tree; use `--skill-registry` only to name the registry the selected orchestrator actually loads, not to bypass the binding check.

Successful runs remove the temporary workspace unless `--keep-temp` is set. Failed runs retain it, while still snapshotting and cleaning this run's ACPX sessions. Use `--output-dir` to retain evidence after a successful run. Provider-owned conversation history is outside the ACPX cleanup boundary.
