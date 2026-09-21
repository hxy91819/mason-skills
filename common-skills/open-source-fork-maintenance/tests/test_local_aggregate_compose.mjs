import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const script = resolve(
  fileURLToPath(new URL(".", import.meta.url)),
  "..",
  "scripts",
  "local-aggregate-compose.mjs",
);
const repository = mkdtempSync(join(tmpdir(), "fork-aggregate-compose-"));

function git(args, options = {}) {
  return execFileSync("git", args, {
    cwd: repository,
    encoding: "utf8",
    stdio: options.capture ? ["ignore", "pipe", "pipe"] : "pipe",
  })?.trim();
}

function commit(branch, file, content, subject, start) {
  git(["switch", "-qC", branch, start]);
  writeFileSync(join(repository, file), content);
  git(["add", file]);
  git(["commit", "-qm", subject]);
  return git(["rev-parse", "HEAD"], { capture: true });
}

function compose(kind, target, outputRef, manifest = "manifest.json") {
  return JSON.parse(execFileSync(
    "node",
    [script, "--repo", repository, "--manifest", manifest, "--kind", kind, "--target", target, "--output-ref", outputRef],
    { encoding: "utf8" },
  ));
}

try {
  git(["init", "-q", "--initial-branch=main"]);
  git(["config", "user.name", "Test User"]);
  git(["config", "user.email", "test@example.com"]);
  writeFileSync(join(repository, "README.md"), "base\n");
  git(["add", "README.md"]);
  git(["commit", "-qm", "base"]);
  const base = git(["rev-parse", "HEAD"], { capture: true });
  git(["tag", "stable-v1", base]);

  const shared = commit("feature/shared", "shared.txt", "shared\n", "shared dependency", base);
  const featureA = commit("feature/a", "a.txt", "feature a\n", "feature a", shared);
  const featureB = commit("feature/b", "b.txt", "feature b\n", "feature b", shared);
  const direct = commit("fix/direct", "direct.txt", "direct\n", "direct patch", base);
  git(["switch", "-q", "main"]);

  const feedback = {
    lastPackaged: null,
    specIssue: null,
    upstreamFeedback: [],
    relatedIssues: [],
    disposition: "internal",
    reason: "Test fixture.",
  };
  const feature = (id, branch, versionCommit, commits, dependsOn, domain) => ({
    id,
    branch,
    ...feedback,
    source: { baseCommit: base, versionCommit, commits },
    dependsOn,
    integration: { domain },
  });
  const manifest = {
    version: 4,
    aggregate: {
      branch: "local/aggregate",
      upstreamRef: "main",
      upstreamRepository: "example/upstream",
      stableTagPattern: null,
      lastIntegratedUpstreamCommit: base,
    },
    features: [
      feature("shared", "feature/shared", shared, [{ commit: shared, logicalPatch: "shared-v1" }], [], "provider"),
      feature("a", "feature/a", featureA, [{ commit: featureA, logicalPatch: "a-v1" }], ["shared"], "provider"),
      feature("b", "feature/b", featureB, [{ commit: featureB, logicalPatch: "b-v1" }], ["shared"], "runtime"),
      feature("direct", "fix/direct", direct, [{ commit: direct, logicalPatch: "direct-v1" }], [], null),
    ],
    domains: [
      { id: "provider", branch: "integration/provider", baseline: { ref: "stable-v1", commit: base }, members: ["a"], integrated: null },
      { id: "runtime", branch: "integration/runtime", baseline: { ref: "stable-v1", commit: base }, members: ["b"], integrated: null },
    ],
    trains: [{ id: "train-all", manifest: "train-all.json" }, { id: "train-partial", manifest: "train-partial.json" }],
  };
  writeFileSync(join(repository, "manifest.json"), JSON.stringify(manifest, null, 2));

  const provider = compose("domain", "provider", "refs/heads/integration/provider");
  const runtime = compose("domain", "runtime", "refs/heads/integration/runtime");
  assert.deepEqual(provider.features, ["shared", "a"]);
  assert.deepEqual(runtime.features, ["shared", "b"]);
  assert.equal(git(["rev-parse", "feature/a"], { capture: true }), featureA);
  assert.equal(git(["rev-parse", "feature/b"], { capture: true }), featureB);

  const adaptation = commit("integration/adaptation", "adaptation.txt", "provider/runtime\n", "shared adaptation", provider.commit);
  git(["switch", "-q", "main"]);
  manifest.domains[0].integrated = {
    commit: adaptation,
    sourceLogicalPatches: provider.patches.map((patch) => patch.logicalPatch),
    patches: [
      ...provider.patches,
      { commit: adaptation, sourceCommit: adaptation, logicalPatch: "provider-runtime-adaptation-v1", features: ["a", "b"] },
    ],
  };
  manifest.domains[0].adaptations = [
    { commit: adaptation, sourceCommit: adaptation, logicalPatch: "provider-runtime-adaptation-v1", features: ["a", "b"] },
  ];
  manifest.domains[1].integrated = {
    commit: runtime.commit,
    sourceLogicalPatches: runtime.patches.map((patch) => patch.logicalPatch),
    patches: runtime.patches,
  };
  git(["branch", "-f", "integration/provider", adaptation]);
  writeFileSync(join(repository, "manifest.json"), JSON.stringify(manifest, null, 2));
  const directPatch = {
    commit: direct,
    sourceCommit: direct,
    logicalPatch: "direct-v1",
    features: ["direct"],
  };
  writeFileSync(join(repository, "train-all.json"), JSON.stringify({
    baseline: { ref: "stable-v1", commit: base },
    features: ["shared", "a", "b", "direct"],
    dependencies: { shared: [], a: ["shared"], b: ["shared"], direct: [] },
    featureSources: {
      shared: [{ logicalPatch: "shared-v1", commit: shared }],
      a: [{ logicalPatch: "a-v1", commit: featureA }],
      b: [{ logicalPatch: "b-v1", commit: featureB }],
      direct: [{ logicalPatch: "direct-v1", commit: direct }],
    },
    featurePatches: {
      shared: ["shared-v1"],
      a: ["a-v1", "provider-runtime-adaptation-v1"],
      b: ["b-v1", "provider-runtime-adaptation-v1"],
      direct: ["direct-v1"],
    },
    domains: ["provider", "runtime"],
    directFeatures: ["direct"],
    patches: [
      ...manifest.domains[0].integrated.patches,
      ...manifest.domains[1].integrated.patches.filter((patch) => patch.logicalPatch !== "shared-v1"),
      directPatch,
    ],
  }));
  writeFileSync(join(repository, "train-partial.json"), JSON.stringify({
    baseline: { ref: "stable-v1", commit: base },
    features: ["shared", "b", "direct"],
    dependencies: { shared: [], b: ["shared"], direct: [] },
    featureSources: {
      shared: [{ logicalPatch: "shared-v1", commit: shared }],
      b: [{ logicalPatch: "b-v1", commit: featureB }],
      direct: [{ logicalPatch: "direct-v1", commit: direct }],
    },
    featurePatches: {
      shared: ["shared-v1"],
      b: ["b-v1"],
      direct: ["direct-v1"],
    },
    domains: ["provider", "runtime"],
    domainFeatures: { provider: [], runtime: ["b"] },
    directFeatures: ["direct"],
    patches: [
      ...manifest.domains[1].integrated.patches,
      directPatch,
    ],
  }));

  const contribution = compose("contribution", "a", "refs/heads/contribution/a");
  assert.deepEqual(contribution.features, ["shared", "a"]);
  assert.deepEqual(contribution.patches.map((patch) => patch.logicalPatch), [
    "shared-v1",
    "a-v1",
    "provider-runtime-adaptation-v1",
  ]);
  assert.equal(git(["show", "refs/heads/contribution/a:a.txt"], { capture: true }), "feature a");
  assert.throws(() => git(["show", "refs/heads/contribution/a:b.txt"], { capture: true }));

  const runtimeContribution = compose("contribution", "b", "refs/heads/contribution/b");
  assert.deepEqual(runtimeContribution.patches.map((patch) => patch.logicalPatch), [
    "shared-v1",
    "b-v1",
    "provider-runtime-adaptation-v1",
  ]);
  assert.equal(git(["show", "refs/heads/contribution/b:b.txt"], { capture: true }), "feature b");
  assert.equal(git(["show", "refs/heads/contribution/b:adaptation.txt"], { capture: true }), "provider/runtime");

  const staleContributionManifest = structuredClone(manifest);
  staleContributionManifest.domains[1].integrated.patches = [];
  writeFileSync(join(repository, "stale-contribution.json"), JSON.stringify(staleContributionManifest));
  const staleContribution = spawnSync(
    "node",
    [script, "--repo", repository, "--manifest", "stale-contribution.json", "--kind", "contribution", "--target", "b", "--output-ref", "refs/heads/contribution/stale-b"],
    { encoding: "utf8" },
  );
  assert.notEqual(staleContribution.status, 0);
  assert.match(staleContribution.stderr, /contribution feature b has no current domain mapping/);

  const rebuiltProvider = compose("domain", "provider", "refs/heads/integration/provider");
  assert.deepEqual(rebuiltProvider.patches.map((patch) => patch.logicalPatch), [
    "shared-v1",
    "a-v1",
    "provider-runtime-adaptation-v1",
  ]);
  assert.equal(git(["show", "refs/heads/integration/provider:adaptation.txt"], { capture: true }), "provider/runtime");

  manifest.domains[0].integrated.patches = [{
    commit: direct,
    sourceCommit: direct,
    logicalPatch: "mutable-registry-patch",
    features: ["a"],
  }];
  manifest.domains[0].members = [];
  manifest.features.find((entry) => entry.id === "a").dependsOn = [];
  writeFileSync(join(repository, "manifest.json"), JSON.stringify(manifest, null, 2));
  git(["add", "manifest.json", "train-all.json", "train-partial.json"]);
  git(["commit", "-qm", "freeze train fixtures"]);

  const train = compose("train", "train-all", "refs/tags/local-aggregate/train-all");
  assert.equal(train.patches.filter((patch) => patch.logicalPatch === "shared-v1").length, 1);
  assert.deepEqual(new Set(train.features), new Set(["shared", "a", "b", "direct"]));
  assert.equal(git(["show", "refs/tags/local-aggregate/train-all:a.txt"], { capture: true }), "feature a");
  assert.equal(git(["show", "refs/tags/local-aggregate/train-all:b.txt"], { capture: true }), "feature b");
  assert.equal(git(["show", "refs/tags/local-aggregate/train-all:direct.txt"], { capture: true }), "direct");

  const partial = compose("train", "train-partial", "refs/tags/local-aggregate/train-partial");
  assert.deepEqual(new Set(partial.features), new Set(["shared", "b", "direct"]));
  assert.throws(() => git(["show", "refs/tags/local-aggregate/train-partial:a.txt"], { capture: true }));
  assert.equal(git(["show", "refs/tags/local-aggregate/train-partial:b.txt"], { capture: true }), "feature b");

  const unsafePartialTrain = JSON.parse(readFileSync(join(repository, "train-partial.json"), "utf8"));
  unsafePartialTrain.featurePatches.b.push("provider-runtime-adaptation-v1");
  unsafePartialTrain.patches.push(manifest.domains[0].adaptations[0]);
  writeFileSync(join(repository, "train-unsafe-partial.json"), JSON.stringify(unsafePartialTrain));
  const unsafePartialManifest = structuredClone(manifest);
  unsafePartialManifest.trains.push({ id: "train-unsafe-partial", manifest: "train-unsafe-partial.json" });
  writeFileSync(join(repository, "unsafe-partial.json"), JSON.stringify(unsafePartialManifest));
  git(["add", "unsafe-partial.json", "train-unsafe-partial.json"]);
  git(["commit", "-qm", "add unsafe partial train fixture"]);
  const unsafePartial = spawnSync(
    "node",
    [script, "--repo", repository, "--manifest", "unsafe-partial.json", "--kind", "train", "--target", "train-unsafe-partial", "--output-ref", "refs/tags/local-aggregate/train-unsafe-partial"],
    { encoding: "utf8" },
  );
  assert.notEqual(unsafePartial.status, 0);
  assert.match(unsafePartial.stderr, /affects an unselected feature/);

  const publishedTree = git(["rev-parse", "refs/tags/local-aggregate/train-all^{tree}"], { capture: true });
  commit("feature/a", "a.txt", "rewritten\n", "replace feature a", base);
  git(["branch", "-f", "integration/provider", base]);
  assert.equal(git(["rev-parse", "refs/tags/local-aggregate/train-all^{tree}"], { capture: true }), publishedTree);
  git(["switch", "-q", "main"]);

  const retry = spawnSync(
    "node",
    [script, "--repo", repository, "--manifest", "manifest.json", "--kind", "train", "--target", "train-all", "--output-ref", "refs/tags/local-aggregate/train-all"],
    { encoding: "utf8" },
  );
  assert.notEqual(retry.status, 0);
  assert.match(retry.stderr, /output ref already exists/);

  writeFileSync(join(repository, "train-all.json"), `${readFileSync(join(repository, "train-all.json"), "utf8")}\n`);
  const dirtyTrain = spawnSync(
    "node",
    [script, "--repo", repository, "--manifest", "manifest.json", "--kind", "train", "--target", "train-all", "--output-ref", "refs/tags/local-aggregate/train-dirty"],
    { encoding: "utf8" },
  );
  assert.notEqual(dirtyTrain.status, 0);
  assert.throws(() => git(["show-ref", "--verify", "refs/tags/local-aggregate/train-dirty"], { capture: true }));
  git(["checkout", "--", "train-all.json"]);

  const incompleteTrain = JSON.parse(readFileSync(join(repository, "train-all.json"), "utf8"));
  incompleteTrain.patches = incompleteTrain.patches.filter((patch) => !patch.features.includes("direct"));
  writeFileSync(join(repository, "train-incomplete.json"), JSON.stringify(incompleteTrain));
  const incompleteManifest = structuredClone(manifest);
  incompleteManifest.trains.push({ id: "train-incomplete", manifest: "train-incomplete.json" });
  writeFileSync(join(repository, "incomplete.json"), JSON.stringify(incompleteManifest));
  git(["add", "incomplete.json", "train-incomplete.json"]);
  git(["commit", "-qm", "add incomplete train fixture"]);
  const incomplete = spawnSync(
    "node",
    [script, "--repo", repository, "--manifest", "incomplete.json", "--kind", "train", "--target", "train-incomplete", "--output-ref", "refs/tags/local-aggregate/train-incomplete"],
    { encoding: "utf8" },
  );
  assert.notEqual(incomplete.status, 0);
  assert.match(incomplete.stderr, /train feature direct does not match its frozen patch selection/);
  assert.throws(() => git(["show-ref", "--verify", "refs/tags/local-aggregate/train-incomplete"], { capture: true }));

  const duplicateTrain = JSON.parse(readFileSync(join(repository, "train-all.json"), "utf8"));
  duplicateTrain.patches.push({ ...directPatch, commit: shared });
  writeFileSync(join(repository, "train-duplicate.json"), JSON.stringify(duplicateTrain));
  const duplicateManifest = structuredClone(manifest);
  duplicateManifest.trains.push({ id: "train-duplicate", manifest: "train-duplicate.json" });
  writeFileSync(join(repository, "duplicate.json"), JSON.stringify(duplicateManifest));
  git(["add", "duplicate.json", "train-duplicate.json"]);
  git(["commit", "-qm", "add duplicate train fixture"]);
  const duplicate = spawnSync(
    "node",
    [script, "--repo", repository, "--manifest", "duplicate.json", "--kind", "train", "--target", "train-duplicate", "--output-ref", "refs/tags/local-aggregate/train-duplicate"],
    { encoding: "utf8" },
  );
  assert.notEqual(duplicate.status, 0);
  assert.match(duplicate.stderr, /duplicate logical patch requires one frozen canonical mapping/);
  assert.throws(() => git(["show-ref", "--verify", "refs/tags/local-aggregate/train-duplicate"], { capture: true }));

  const unownedTrain = JSON.parse(readFileSync(join(repository, "train-all.json"), "utf8"));
  unownedTrain.features = unownedTrain.features.map((id) => id === "direct" ? "legacy" : id);
  unownedTrain.dependencies.legacy = unownedTrain.dependencies.direct;
  delete unownedTrain.dependencies.direct;
  unownedTrain.featurePatches.legacy = unownedTrain.featurePatches.direct;
  delete unownedTrain.featurePatches.direct;
  unownedTrain.patches = unownedTrain.patches.map((patch) => patch.logicalPatch === "direct-v1"
    ? { ...patch, features: ["legacy"] }
    : patch);
  writeFileSync(join(repository, "train-unowned.json"), JSON.stringify(unownedTrain));
  const unownedManifest = structuredClone(manifest);
  unownedManifest.features.push({ id: "legacy", branch: "fix/legacy", ...feedback });
  unownedManifest.trains.push({ id: "train-unowned", manifest: "train-unowned.json" });
  writeFileSync(join(repository, "unowned.json"), JSON.stringify(unownedManifest));
  git(["add", "unowned.json", "train-unowned.json"]);
  git(["commit", "-qm", "add unowned train fixture"]);
  const unowned = spawnSync(
    "node",
    [script, "--repo", repository, "--manifest", "unowned.json", "--kind", "train", "--target", "train-unowned", "--output-ref", "refs/tags/local-aggregate/train-unowned"],
    { encoding: "utf8" },
  );
  assert.notEqual(unowned.status, 0);
  assert.match(unowned.stderr, /train feature legacy has no complete frozen selection/);

  const mutableRevisionTrain = JSON.parse(readFileSync(join(repository, "train-all.json"), "utf8"));
  mutableRevisionTrain.patches[0].commit = "feature/shared";
  writeFileSync(join(repository, "train-mutable-revision.json"), JSON.stringify(mutableRevisionTrain));
  const mutableRevisionManifest = structuredClone(manifest);
  mutableRevisionManifest.trains.push({ id: "train-mutable-revision", manifest: "train-mutable-revision.json" });
  writeFileSync(join(repository, "mutable-revision.json"), JSON.stringify(mutableRevisionManifest));
  git(["add", "mutable-revision.json", "train-mutable-revision.json"]);
  git(["commit", "-qm", "add mutable revision train fixture"]);
  const mutableRevision = spawnSync(
    "node",
    [script, "--repo", repository, "--manifest", "mutable-revision.json", "--kind", "train", "--target", "train-mutable-revision", "--output-ref", "refs/tags/local-aggregate/train-mutable-revision"],
    { encoding: "utf8" },
  );
  assert.notEqual(mutableRevision.status, 0);
  assert.match(mutableRevision.stderr, /must be a full immutable commit ID/);

  const missingDependencyManifest = structuredClone(manifest);
  missingDependencyManifest.features.find((entry) => entry.id === "a").dependsOn = ["missing"];
  writeFileSync(join(repository, "missing.json"), JSON.stringify(missingDependencyManifest));
  const failure = spawnSync(
    "node",
    [script, "--repo", repository, "--manifest", "missing.json", "--kind", "contribution", "--target", "a", "--output-ref", "refs/heads/contribution/failure"],
    { encoding: "utf8" },
  );
  assert.notEqual(failure.status, 0);
  assert.throws(() => git(["show-ref", "--verify", "refs/heads/contribution/failure"], { capture: true }));

  const legacyManifest = structuredClone(manifest);
  legacyManifest.features.push({ id: "legacy", branch: "fix/legacy", ...feedback });
  writeFileSync(join(repository, "legacy.json"), JSON.stringify(legacyManifest));
  const legacyFailure = spawnSync(
    "node",
    [script, "--repo", repository, "--manifest", "legacy.json", "--kind", "contribution", "--target", "legacy", "--output-ref", "refs/heads/contribution/legacy"],
    { encoding: "utf8" },
  );
  assert.notEqual(legacyFailure.status, 0);
  assert.match(legacyFailure.stderr, /has no explicit version 4 patch selection/);
  assert.throws(() => git(["show-ref", "--verify", "refs/heads/contribution/legacy"], { capture: true }));

  const rewrittenA = git(["rev-parse", "feature/a"], { capture: true });
  const conflictingSourceManifest = structuredClone(manifest);
  conflictingSourceManifest.features.find((entry) => entry.id === "a").source.commits = [
    { commit: rewrittenA, logicalPatch: "shared-v1" },
  ];
  conflictingSourceManifest.features.find((entry) => entry.id === "a").dependsOn = ["shared"];
  conflictingSourceManifest.domains[0].members = ["a"];
  conflictingSourceManifest.domains[0].integrated = {
    commit: git(["rev-parse", "refs/heads/integration/provider"], { capture: true }),
    sourceLogicalPatches: [],
    patches: [],
  };
  writeFileSync(join(repository, "source-conflict.json"), JSON.stringify(conflictingSourceManifest));
  const sourceConflict = spawnSync(
    "node",
    [script, "--repo", repository, "--manifest", "source-conflict.json", "--kind", "domain", "--target", "provider", "--output-ref", "refs/heads/integration/provider"],
    { encoding: "utf8" },
  );
  assert.notEqual(sourceConflict.status, 0);
  assert.match(sourceConflict.stderr, /duplicate logical patch requires one frozen canonical mapping/);

  const wrongDomainRef = spawnSync(
    "node",
    [script, "--repo", repository, "--manifest", "manifest.json", "--kind", "domain", "--target", "provider", "--output-ref", "refs/tags/local-aggregate/train-all"],
    { encoding: "utf8" },
  );
  assert.notEqual(wrongDomainRef.status, 0);
  assert.match(wrongDomainRef.stderr, /domain provider output must be refs\/heads\/integration\/provider/);

  const domainUpdateManifest = structuredClone(manifest);
  domainUpdateManifest.features.find((entry) => entry.id === "a").source = {
    baseCommit: base,
    versionCommit: rewrittenA,
    commits: [{ commit: rewrittenA, logicalPatch: "a-v2" }],
  };
  domainUpdateManifest.features.find((entry) => entry.id === "a").dependsOn = ["shared"];
  domainUpdateManifest.domains[0].members = ["a"];
  const oldDomain = git(["rev-parse", "refs/heads/integration/provider"], { capture: true });
  domainUpdateManifest.domains[0].integrated = {
    commit: oldDomain,
    sourceLogicalPatches: [],
    patches: [],
  };
  writeFileSync(join(repository, "domain-update.json"), JSON.stringify(domainUpdateManifest));
  const checkedOutDomain = mkdtempSync(join(tmpdir(), "fork-domain-checkout-"));
  git(["worktree", "add", "-q", checkedOutDomain, "integration/provider"]);
  const checkedOutFailure = spawnSync(
    "node",
    [script, "--repo", repository, "--manifest", "domain-update.json", "--kind", "domain", "--target", "provider", "--output-ref", "refs/heads/integration/provider"],
    { encoding: "utf8" },
  );
  assert.notEqual(checkedOutFailure.status, 0);
  assert.match(checkedOutFailure.stderr, /domain output ref is checked out/);
  git(["worktree", "remove", "--force", checkedOutDomain]);
  rmSync(checkedOutDomain, { force: true, recursive: true });
  const updatedDomain = compose("domain", "provider", "refs/heads/integration/provider", "domain-update.json");
  assert.notEqual(updatedDomain.commit, oldDomain);
  assert.equal(git(["rev-parse", "feature/a"], { capture: true }), rewrittenA);
  assert.equal(git(["show", "refs/heads/integration/provider:adaptation.txt"], { capture: true }), "provider/runtime");
} finally {
  rmSync(repository, { force: true, recursive: true });
}
