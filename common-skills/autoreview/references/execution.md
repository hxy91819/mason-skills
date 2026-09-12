# Review execution details

## Skill Path (set once)

Set the skill script paths once, then use `"$AUTOREVIEW"` and `"$AUTOREVIEW_HARNESS"` in the examples below.

Choose one:

```bash
# Project-local skill in the current repo for Codex and other agents:
export AUTOREVIEW=".agents/skills/autoreview/scripts/autoreview"
export AUTOREVIEW_HARNESS=".agents/skills/autoreview/scripts/test-review-harness"
```

```bash
# Claude Code project-local skill in the current repo:
export AUTOREVIEW=".claude/skills/autoreview/scripts/autoreview"
export AUTOREVIEW_HARNESS=".claude/skills/autoreview/scripts/test-review-harness"
```

```bash
# Source checkout of openclaw/agent-skills:
export AUTOREVIEW="skills/autoreview/scripts/autoreview"
export AUTOREVIEW_HARNESS="skills/autoreview/scripts/test-review-harness"
```

```bash
# Global skill:
export AGENTS_HOME="${AGENTS_HOME:-$HOME/.agents}"
export AUTOREVIEW="$AGENTS_HOME/skills/autoreview/scripts/autoreview"
export AUTOREVIEW_HARNESS="$AGENTS_HOME/skills/autoreview/scripts/test-review-harness"
```

When using Claude Code, set `AGENTS_HOME="$HOME/.claude"` for global skills.

## Optional Credential Preflight

Credential scanning is not an implicit autoreview gate. Run it explicitly when the
change is about to be committed, pushed, or sent to an external reviewer:

```bash
common-skills/autoreview/scripts/trufflehog-preflight --mode local
common-skills/autoreview/scripts/trufflehog-preflight --mode branch --base origin/main
common-skills/autoreview/scripts/trufflehog-preflight --mode commit --commit HEAD
```

On native Windows, choose the matching pair:

```powershell
# Project-local skill in the current repo for Codex and other agents:
$AUTOREVIEW = ".agents\skills\autoreview\scripts\autoreview"
$AUTOREVIEW_HARNESS = ".agents\skills\autoreview\scripts\test-review-harness.ps1"
```

```powershell
# Claude Code project-local skill in the current repo:
$AUTOREVIEW = ".claude\skills\autoreview\scripts\autoreview"
$AUTOREVIEW_HARNESS = ".claude\skills\autoreview\scripts\test-review-harness.ps1"
```

```powershell
# Source checkout of openclaw/agent-skills:
$AUTOREVIEW = "skills\autoreview\scripts\autoreview"
$AUTOREVIEW_HARNESS = "skills\autoreview\scripts\test-review-harness.ps1"
```

```powershell
# Global skill:
$AgentsHome = if ($env:AGENTS_HOME) { $env:AGENTS_HOME } else { Join-Path $HOME ".agents" }
$AUTOREVIEW = Join-Path $AgentsHome "skills\autoreview\scripts\autoreview"
$AUTOREVIEW_HARNESS = Join-Path $AgentsHome "skills\autoreview\scripts\test-review-harness.ps1"
```

## Oversized Bundles

The helper scans the full patch before partitioning it. A safe bundle that fits
the aggregate prompt limit remains one integrated review pass. Larger bundles
are split at bundle sections and file boundaries where possible; an oversized
single-file block is split at line boundaries with repeated file/hunk context
and an absolute new- or old-file line offset. Untracked snapshots use
injection-safe source-line records so continuation passes retain reportable
locations. A single physical diff line split across passes also retains its
original addition, deletion, or context marker.
Every original bundle byte appears exactly once across the pass sequence, and
all validated reports are merged before required-finding and exit-status checks.
The helper caps one run at eight bounded passes so an unexpectedly huge branch
cannot create unbounded model calls; split still-larger work into coherent review
targets.

Chunking makes large-diff review usable, but it cannot give one model call every
cross-file implementation detail. For architecture-heavy changes, still prefer
a coherent branch or PR shape whose semantic decision surface fits one pass.
Removing verified non-authoritative generated noise remains useful, but never
drop lockfiles, generated clients, policies, manifests, schemas, or other
independently semantic artifacts merely to shrink the review.

## Parallel Closeout

Format first if formatting can change line locations. Then it is OK to run tests and review in parallel:

```bash
"$AUTOREVIEW" --parallel-tests "<focused test command>"
```

On Windows, the default `--parallel-tests` shell preserves the platform `cmd.exe`
semantics used by Python `shell=True`. Use `--parallel-tests-shell powershell`
or `--parallel-tests-shell pwsh` when the focused test command is PowerShell-specific.
Parallel tests inherit only a small allowlist of ordinary OS, CI, and toolchain
variables. Put additional non-secret project controls directly in the test command.
Home and standard config directories point to a temporary isolated root that is
removed after the command exits. Do not put secrets in the command because it is
printed before execution. Set `OPENCLAW_TESTBOX=1` on the autoreview process, not
inside the test command, because the environment snapshot and credential staging
happen before the test shell starts:

```bash
OPENCLAW_TESTBOX=1 "$AUTOREVIEW" --parallel-tests "pnpm check:changed"
```

On POSIX, the helper puts this isolated Testbox home under the short, sticky
system `/tmp`; Blacksmith creates an SSH control socket below that home, and a
long macOS `TMPDIR` can exceed the Unix-socket path limit. With an older helper,
prefix the outer autoreview process with `TMPDIR=/tmp`. Setting `TMPDIR` inside
the quoted test command is too late because the isolated home already exists.

This is the narrow trusted-maintainer-code exception: it stages only the Blacksmith
credential file into the temporary home so the command can delegate remotely. Never
use this credential-hydrated path for untrusted contributor or fork code. Run other
secret-bearing or credentialed tests separately in an appropriately isolated remote
runner.

Tradeoff: tests may force code changes that stale the review. If tests or review lead to code edits, rerun the affected tests and rerun review until no accepted/actionable findings remain. Once that rerun exits cleanly, stop; do not spend another long review cycle on redundant confirmation.

## Credential scanner contract

- TruffleHog is intentionally outside autoreview's default engine path. Run the standalone `scripts/trufflehog-preflight` command for an explicit pre-commit, push, CI, or external-review credential gate; it scans temporary snapshots of the exact added, modified, or deleted content and uses TruffleHog's low-false-positive `verified,unknown` policy. One-to-one renames whose blobs are byte-identical are omitted because they introduce or remove no bytes; copies, ambiguous many-path moves, and renamed files with content changes remain scanned. The standalone preflight does not classify arbitrary password-like strings or rescan unchanged history. Autoreview still redacts locally recognized secret-like values when building its review bundle, and repositories should run TruffleHog in pull-request CI as a backup. Install TruffleHog using its official platform-neutral instructions; the standalone command fails with that link when the binary is unavailable and never auto-installs it. Review bundles still omit security-sensitive paths or files, and explicit prompt and dataset inputs remain checked before engine invocation. Safe large diffs are sent as one pass while they fit the aggregate prompt limit, then partitioned into complete bounded passes without truncation.
