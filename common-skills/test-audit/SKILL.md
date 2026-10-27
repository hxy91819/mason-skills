---
name: test-audit
description: Gate new or changed tests and audit existing ones; reject duplicate or implementation-coupled proof and remove test-only production seams.
disable-model-invocation: true
triggers:
  - user
---

# Test Audit

Adapted from OpenClaw's `test-audit` skill (MIT, see `LICENSE`); toolchain specifics replaced with the project's own commands.

- The authoring gate applies to every new or changed test.
- Audits remove low-value proof in coherent owner batches; deletion counts are never the goal.
- Whole-subsystem campaign: read [CAMPAIGN.md](CAMPAIGN.md) first.
- Discovery is read-only; report candidates before editing.

## Authoring gate

Before adding a test, answer:

1. Which observable behavior, invariant, or independent contract does it protect?
2. Which credible regression makes it fail?
3. Why does existing proof miss it? Each contract has one primary owner at the strongest boundary. Another layer needs a distinct transport or lifecycle risk. Extend tables and shared fixtures; consolidate repeated setup.
4. Does it need an export, flag, wrapper, or injection hook with no production caller? Move the proof to the real boundary instead.

- Prove a caller-visible contract through its production owner, with fixed external I/O fixtures and independently derived expected values. Prefer focused integration tests and independent unit contracts over mocked internal decisions or whole-product boots.
- Regressions fail on the original defect for the intended reason (not on fixture setup) and pass after the repair; report when baseline proof is unavailable.
- One owner regression covers a bug; never replay it at every crossed layer.
- Behavior-preserving refactors should not break tests.

## Boundary and cost

- Inject clocks. A fake clock must drive the timers the owner actually creates; advancing a clock that no timer observes proves nothing. Avoid real sleeps and polling.
- Async waits target produced state, never action return.
- Seconds-long tests must prove a contract no cheaper layer can; long end-to-end compositions belong in a slower tier.
- Isolate each file's state; fix shared-state leaks instead of serializing tests.
- Many private controls suggest fragmented ownership, not a need for test-only exports.

## Junk patterns

- Reject self-comparisons, copied inventories, source greps, implementation or call-shape assertions, duplicate contracts, test-only seams, subject-generated expected values, and mocks supplying the asserted behavior.
- Fixtures must not fabricate owner receipts or ordering, or claim a persistence path the owner never writes.
- Negative controls must fail at the intended guard; names must match the exercised behavior.
- Auditing candidates: use the [full checklist](references/audit.md#junk-patterns).

## Retention bar

- Keep independent API, SDK, protocol, config, migration, storage, security, platform, default, generated-language, package, release, architecture, and observable-ordering contracts. Static or slow does not mean disposable.
- Source inspection must survive identifier-only refactors and guard an independent user-facing contract.
- Baseline failures may be bugs to repair, not tests to delete.

## Audit and validation

- Before an audit edit, read the [candidate evidence and workflow](references/audit.md#candidate-evidence); inspect full owners, callers, and history; record the remaining proof before deletion.
- Delete obsolete production seams together with their tests.
- Run the owner and sibling tests plus the project's changed-file checks and dead-code tooling; then run `$autoreview` when available.
- Report causes, retained contracts, proof and cost, production versus test LOC, and follow-ups. Commit, push, or land only with task authority.
