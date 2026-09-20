import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
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
  assert.equal(report.aggregate.recommendedIntegration.kind, "upstream-ref");
  assert.equal(report.aggregate.recommendedIntegration.ref, "main");
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
  assert.match(textReport, /Unclassified legacy issue `example\/upstream#1`/);
  assert.equal(registeredReport.warnings.length, 1);
  const legacyManifest = JSON.parse(readFileSync(join(repository, "registered-manifest.json"), "utf8"));
  legacyManifest.features[0].upstreamIssues[0].feedbackUrl += "/";
  writeFileSync(join(repository, "legacy-manifest.json"), JSON.stringify(legacyManifest));
  const legacy = spawnSync(
    "node",
    [script, "--repo", repository, "--manifest", "legacy-manifest.json", "--json"],
    { encoding: "utf8", env: environment },
  );
  assert.equal(legacy.status, 0, legacy.stderr);
  assert.equal(JSON.parse(legacy.stdout).warnings.length, 1);

  const reference = (repository) => ({
    repository,
    number: 1,
    feedbackUrl: `https://github.com/${repository}/issues/1`,
  });
  const classifiedManifest = {
    version: 3,
    aggregate: {
      branch: "local/aggregate",
      upstreamRef: "main",
      upstreamRepository: "example/upstream",
      lastIntegratedUpstreamCommit: baseline,
      stableTagPattern: null,
    },
    features: [{
      branch: "feature/example",
      lastPackaged: null,
      specIssue: reference("example/fork"),
      upstreamFeedback: [],
      relatedIssues: [reference("example/upstream")],
      disposition: "needs-feedback",
      reason: "The fork specification has related upstream work but no submitted feedback.",
    }],
  };
  function runClassified(manifest, json = true) {
    writeFileSync(join(repository, "classified-manifest.json"), JSON.stringify(manifest));
    return spawnSync(
      "node",
      [script, "--repo", repository, "--manifest", "classified-manifest.json", ...(json ? ["--json"] : [])],
      { encoding: "utf8", env: environment },
    );
  }
  const classified = runClassified(classifiedManifest);
  assert.equal(classified.status, 0, classified.stderr);
  const classifiedReport = JSON.parse(classified.stdout);
  assert.equal(classifiedReport.features[0].specIssue.repository, "example/fork");
  assert.deepEqual(classifiedReport.features[0].upstreamFeedback, []);
  assert.equal(classifiedReport.features[0].relatedIssues[0].repository, "example/upstream");
  assert.equal(classifiedReport.features[0].disposition, "needs-feedback");
  const classifiedText = runClassified(classifiedManifest, false);
  assert.equal(classifiedText.status, 0, classifiedText.stderr);
  assert.match(classifiedText.stdout, /Specification `example\/fork#1`/);
  assert.match(classifiedText.stdout, /Related context `example\/upstream#1`/);
  assert.doesNotMatch(classifiedText.stdout, /Upstream feedback `/);

  const reportedManifest = structuredClone(classifiedManifest);
  reportedManifest.features[0].upstreamFeedback = [reference("example/upstream")];
  reportedManifest.features[0].relatedIssues = [];
  reportedManifest.features[0].disposition = "reported";
  const reportedText = runClassified(reportedManifest, false);
  assert.equal(reportedText.status, 0, reportedText.stderr);
  assert.match(reportedText.stdout, /Upstream feedback `example\/upstream#1`/);

  const internalManifest = structuredClone(classifiedManifest);
  internalManifest.features[0].specIssue = null;
  internalManifest.features[0].relatedIssues = [];
  internalManifest.features[0].disposition = "internal";
  internalManifest.features[0].reason = "Repairs local migration history; no upstream issue is required.";
  const internal = runClassified(internalManifest);
  assert.equal(internal.status, 0, internal.stderr);
  assert.equal(JSON.parse(internal.stdout).features[0].specIssue, null);

  const wrongRepository = structuredClone(reportedManifest);
  wrongRepository.features[0].upstreamFeedback = [reference("example/fork")];
  assert.notEqual(runClassified(wrongRepository).status, 0);
  const wrongUrl = structuredClone(reportedManifest);
  wrongUrl.features[0].upstreamFeedback[0].feedbackUrl = "https://github.com/example/fork/issues/1";
  assert.notEqual(runClassified(wrongUrl).status, 0);
  const missingFeedback = structuredClone(reportedManifest);
  missingFeedback.features[0].upstreamFeedback = [];
  assert.notEqual(runClassified(missingFeedback).status, 0);

  git(["switch", "-q", "main"]);
  writeFileSync(join(repository, "STABLE.md"), "stable\n");
  git(["add", "STABLE.md"]);
  git(["commit", "-qm", "stable"]);
  const stableCommit = execFileSync("git", ["rev-parse", "HEAD"], {
    cwd: repository,
    encoding: "utf8",
  }).trim();
  git(["tag", "desktop-v1.0.0"]);
  git(["switch", "-q", "local/aggregate"]);
  writeFileSync(
    join(repository, "stable-manifest.json"),
    `${JSON.stringify(
      {
        version: 2,
        aggregate: {
          branch: "local/aggregate",
          upstreamRef: "main",
          lastIntegratedUpstreamCommit: baseline,
          stableTagPattern: "^desktop-v\\d+\\.\\d+\\.\\d+$",
        },
        features: [],
      },
      null,
      2,
    )}\n`,
  );
  const stableReport = JSON.parse(
    execFileSync(
      "node",
      [script, "--repo", repository, "--manifest", "stable-manifest.json", "--json"],
      { encoding: "utf8" },
    ),
  );
  assert.equal(stableReport.aggregate.stableRelease.state, "released-after-baseline");
  assert.equal(stableReport.aggregate.stableRelease.tag, "desktop-v1.0.0");
  assert.equal(stableReport.aggregate.recommendedIntegration.kind, "stable-tag");
  assert.equal(stableReport.aggregate.recommendedIntegration.ref, "desktop-v1.0.0");
  assert.equal(stableReport.aggregate.recommendedIntegration.commit, stableCommit);
  const stableText = execFileSync(
    "node",
    [script, "--repo", repository, "--manifest", "stable-manifest.json"],
    { encoding: "utf8" },
  );
  assert.match(stableText, /Recommended integration: `desktop-v1\.0\.0` \(latest stable tag\)/);

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

  git(["switch", "-qC", "feature/tiered", stableCommit]);
  writeFileSync(join(repository, "TIERED.md"), "v1\n");
  git(["add", "TIERED.md"]);
  git(["commit", "-qm", "tiered v1"]);
  const tieredV1 = execFileSync("git", ["rev-parse", "HEAD"], { cwd: repository, encoding: "utf8" }).trim();
  git(["branch", "integration/provider", tieredV1]);
  const tieredManifest = {
    version: 4,
    aggregate: {
      branch: "local/aggregate",
      upstreamRef: "main",
      upstreamRepository: "example/upstream",
      lastIntegratedUpstreamCommit: stableCommit,
      stableTagPattern: "^desktop-v\\d+\\.\\d+\\.\\d+$",
    },
    features: [{
      id: "tiered",
      branch: "feature/tiered",
      lastPackaged: null,
      specIssue: null,
      upstreamFeedback: [],
      relatedIssues: [],
      disposition: "internal",
      reason: "Test fixture.",
      source: {
        baseCommit: stableCommit,
        versionCommit: tieredV1,
        commits: [{ commit: tieredV1, logicalPatch: "tiered-v1" }],
      },
      dependsOn: [],
      integration: { domain: "provider" },
    }],
    domains: [{
      id: "provider",
      branch: "integration/provider",
      baseline: { ref: "desktop-v1.0.0", commit: stableCommit },
      members: ["tiered"],
      adaptations: [],
      integrated: {
        commit: tieredV1,
        sourceLogicalPatches: ["tiered-v1"],
        patches: [{
          commit: tieredV1,
          sourceCommit: tieredV1,
          logicalPatch: "tiered-v1",
          features: ["tiered"],
        }],
      },
    }],
    trains: [{ id: "train-v1", manifest: "train-v1.json" }],
  };
  writeFileSync(join(repository, "tiered-manifest.json"), JSON.stringify(tieredManifest));
  writeFileSync(join(repository, "train-v1.json"), "{}");
  const tieredCurrent = JSON.parse(execFileSync(
    "node",
    [script, "--repo", repository, "--manifest", "tiered-manifest.json", "--json"],
    { encoding: "utf8", env: environment },
  ));
  assert.equal(tieredCurrent.features[0].selection.state, "packaged");
  assert.equal(tieredCurrent.domains[0].baselinePresent, true);
  assert.equal(tieredCurrent.domains[0].patchCommitsPresent, true);
  assert.equal(tieredCurrent.domains[0].sourceMappingCurrent, true);
  assert.equal(tieredCurrent.trains[0].id, "train-v1");

  tieredManifest.domains[0].adaptations = [{
    commit: tieredV1,
    sourceCommit: tieredV1,
    logicalPatch: "tiered-adaptation-v1",
    features: ["tiered"],
  }];
  writeFileSync(join(repository, "tiered-manifest.json"), JSON.stringify(tieredManifest));
  const adaptationStale = JSON.parse(execFileSync(
    "node",
    [script, "--repo", repository, "--manifest", "tiered-manifest.json", "--json"],
    { encoding: "utf8", env: environment },
  ));
  assert.equal(adaptationStale.domains[0].sourceMappingCurrent, false);
  tieredManifest.domains[0].adaptations = [];

  writeFileSync(join(repository, "TIERED.md"), "v2\n");
  git(["add", "TIERED.md"]);
  git(["commit", "-qm", "tiered v2"]);
  const tieredAdvanced = JSON.parse(execFileSync(
    "node",
    [script, "--repo", repository, "--manifest", "tiered-manifest.json", "--json"],
    { encoding: "utf8", env: environment },
  ));
  assert.equal(tieredAdvanced.features[0].selection.state, "advanced");

  tieredManifest.features[0].source.versionCommit = execFileSync(
    "git",
    ["rev-parse", "feature/tiered"],
    { cwd: repository, encoding: "utf8" },
  ).trim();
  tieredManifest.features[0].source.commits = [{
    commit: tieredManifest.features[0].source.versionCommit,
    logicalPatch: "tiered-v2",
  }];
  writeFileSync(join(repository, "tiered-manifest.json"), JSON.stringify(tieredManifest));
  const tieredStale = JSON.parse(execFileSync(
    "node",
    [script, "--repo", repository, "--manifest", "tiered-manifest.json", "--json"],
    { encoding: "utf8", env: environment },
  ));
  assert.equal(tieredStale.domains[0].sourceMappingCurrent, false);

  git(["switch", "-qC", "replacement", stableCommit]);
  writeFileSync(join(repository, "TIERED.md"), "replacement\n");
  git(["add", "TIERED.md"]);
  git(["commit", "-qm", "replacement history"]);
  git(["branch", "-f", "feature/tiered", "replacement"]);
  const tieredRewritten = JSON.parse(execFileSync(
    "node",
    [script, "--repo", repository, "--manifest", "tiered-manifest.json", "--json"],
    { encoding: "utf8", env: environment },
  ));
  assert.equal(tieredRewritten.features[0].selection.state, "rewritten");
} finally {
  rmSync(repository, { force: true, recursive: true });
}
