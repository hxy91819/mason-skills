import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const script = resolve(
  fileURLToPath(new URL(".", import.meta.url)),
  "..",
  "scripts",
  "local-aggregate-status.mjs",
);
const repository = mkdtempSync(join(tmpdir(), "fork-aggregate-status-"));

function git(args) {
  execFileSync("git", args, { cwd: repository, stdio: "pipe" });
}

try {
  git(["init", "-q", "--initial-branch=main"]);
  git(["config", "user.name", "Test User"]);
  git(["config", "user.email", "test@example.com"]);
  writeFileSync(join(repository, "README.md"), "base\n");
  git(["add", "README.md"]);
  git(["commit", "-qm", "base"]);
  const baseline = execFileSync("git", ["rev-parse", "HEAD"], { cwd: repository, encoding: "utf8" }).trim();
  git(["branch", "local/aggregate"]);
  git(["switch", "-qc", "feature/example"]);
  writeFileSync(join(repository, "README.md"), "feature\n");
  git(["add", "README.md"]);
  git(["commit", "-qm", "feature"]);
  git(["switch", "-q", "local/aggregate"]);
  writeFileSync(
    join(repository, "manifest.json"),
    `${JSON.stringify(
      {
        version: 2,
        aggregate: {
          branch: "local/aggregate",
          upstreamRef: "main",
          lastIntegratedUpstreamCommit: baseline,
          stableTagPattern: null,
        },
        features: [],
      },
      null,
      2,
    )}\n`,
  );

  const output = execFileSync(
    "node",
    [script, "--repo", repository, "--manifest", "manifest.json", "--json"],
    { encoding: "utf8" },
  );
  const report = JSON.parse(output);
  assert.equal(report.aggregate.currentBranch, "local/aggregate");
  assert.equal(report.aggregate.upstream.state, "packaged");
  assert.equal(report.aggregate.stableRelease.state, "not-configured");
  assert.deepEqual(report.unregisteredBranches.map((branch) => branch.branch), ["feature/example"]);

  const fakeBin = join(repository, "fake-bin");
  mkdirSync(fakeBin);
  const fakeGh = join(fakeBin, "gh");
  writeFileSync(
    fakeGh,
    `#!/bin/sh
if [ "$1" = "issue" ]; then
  printf '%s\\n' '{"number":1,"title":"Closed by PR","state":"CLOSED","stateReason":"COMPLETED","closedAt":null,"updatedAt":"2026-01-01T00:00:00Z","url":"https://github.com/example/upstream/issues/1","body":"","comments":[],"closedByPullRequestsReferences":[{"number":42,"repository":{"nameWithOwner":"example/upstream"}}]}'
else
  printf '%s\\n' '{"number":42,"title":"Upstream implementation","state":"MERGED","mergedAt":"2026-01-01T00:00:00Z","closedAt":null,"updatedAt":"2026-01-01T00:00:00Z","url":"https://github.com/example/upstream/pull/42"}'
fi
`,
  );
  chmodSync(fakeGh, 0o755);
  writeFileSync(
    join(repository, "registered-manifest.json"),
    `${JSON.stringify(
      {
        version: 2,
        aggregate: {
          branch: "local/aggregate",
          upstreamRef: "main",
          lastIntegratedUpstreamCommit: baseline,
          stableTagPattern: null,
        },
        features: [
          {
            branch: "feature/example",
            lastPackaged: { sourceCommit: baseline, aggregateCommit: baseline },
            upstreamIssues: [
              {
                repository: "example/upstream",
                number: 1,
                feedbackUrl: "https://github.com/example/upstream/issues/1",
              },
            ],
          },
        ],
      },
      null,
      2,
    )}\n`,
  );
  const environment = { ...process.env, PATH: `${fakeBin}:${process.env.PATH}` };
  const registeredOutput = execFileSync(
    "node",
    [script, "--repo", repository, "--manifest", "registered-manifest.json", "--json"],
    { encoding: "utf8", env: environment },
  );
  const registeredReport = JSON.parse(registeredOutput);
  assert.deepEqual(
    registeredReport.features[0].upstreamIssues[0].relatedPullRequests.map((pullRequest) => ({
      repository: pullRequest.repository,
      number: pullRequest.number,
      state: pullRequest.state,
    })),
    [{ repository: "example/upstream", number: 42, state: "MERGED" }],
  );
  const textReport = execFileSync(
    "node",
    [script, "--repo", repository, "--manifest", "registered-manifest.json"],
    { encoding: "utf8", env: environment },
  );
  assert.match(textReport, /Aggregate mapping: INVALID — aggregate commit does not retain the source SHA/);

  writeFileSync(
    join(repository, "invalid-manifest.json"),
    `${JSON.stringify(
      {
        version: 2,
        aggregate: {
          branch: "local/aggregate",
          upstreamRef: "main",
          lastIntegratedUpstreamCommit: baseline,
          stableTagPattern: "[",
        },
        features: [],
      },
      null,
      2,
    )}\n`,
  );
  const invalid = spawnSync(
    "node",
    [script, "--repo", repository, "--manifest", "invalid-manifest.json", "--json"],
    { encoding: "utf8" },
  );
  assert.notEqual(invalid.status, 0);
  assert.match(invalid.stderr, /stableTagPattern must be a valid regular expression/);
} finally {
  rmSync(repository, { force: true, recursive: true });
}
