import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { relative, resolve } from "node:path";

const args = process.argv.slice(2);

function valueAfter(flag) {
  const index = args.indexOf(flag);
  if (index === -1) {
    return null;
  }
  const value = args[index + 1];
  if (!value || value.startsWith("--")) {
    throw new Error(`${flag} requires a value`);
  }
  return value;
}

function run(command, commandArgs, cwd, options = {}) {
  return execFileSync(command, commandArgs, {
    cwd,
    encoding: "utf8",
    stdio: options.capture ? ["ignore", "pipe", "pipe"] : ["ignore", "ignore", "inherit"],
  })?.trim();
}

const repository = resolve(valueAfter("--repo") ?? process.cwd());
const manifestPath = resolve(repository, valueAfter("--manifest") ?? "config/local-aggregate-features.json");
const kind = valueAfter("--kind");
const target = valueAfter("--target");
const outputRef = valueAfter("--output-ref");
let manifest = JSON.parse(readFileSync(manifestPath, "utf8"));

if (manifest.version !== 4) {
  throw new Error("composition requires a version 4 local aggregate manifest");
}
if (!kind || !target || !outputRef || !["domain", "contribution", "train"].includes(kind)) {
  throw new Error("use --kind domain|contribution|train --target <id> --output-ref <ref>");
}
if (!outputRef.startsWith("refs/heads/") && !outputRef.startsWith("refs/tags/")) {
  throw new Error("--output-ref must be a full refs/heads/* or refs/tags/* ref");
}
run("git", ["check-ref-format", outputRef], repository, { capture: true });
let existingOutput = null;
try {
  existingOutput = run("git", ["rev-parse", "--verify", outputRef], repository, { capture: true });
} catch {
}
if (existingOutput && kind !== "domain") {
  throw new Error(`output ref already exists: ${outputRef}`);
}

const features = new Map(manifest.features.map((feature) => [feature.id, feature]));
const domains = new Map(manifest.domains.map((domain) => [domain.id, domain]));

function feature(id) {
  const value = features.get(id);
  if (!value) {
    throw new Error(`unknown feature: ${id}`);
  }
  return value;
}

function domain(id) {
  const value = domains.get(id);
  if (!value) {
    throw new Error(`unknown domain: ${id}`);
  }
  return value;
}

function refIsCheckedOut(ref) {
  const worktreeList = run("git", ["worktree", "list", "--porcelain"], repository, { capture: true });
  return worktreeList.split("\n").some((line) => line === `branch ${ref}`);
}

function orderedFeatures(ids) {
  const result = [];
  const visiting = new Set();
  const visited = new Set();
  function visit(id) {
    if (visited.has(id)) {
      return;
    }
    if (visiting.has(id)) {
      throw new Error(`feature dependency cycle at ${id}`);
    }
    visiting.add(id);
    const current = feature(id);
    if (!current.source || !Array.isArray(current.dependsOn) || !current.integration) {
      throw new Error(`feature ${id} has no explicit version 4 patch selection`);
    }
    for (const dependency of current.dependsOn) {
      visit(dependency);
    }
    visiting.delete(id);
    visited.add(id);
    result.push(current);
  }
  for (const id of ids) {
    visit(id);
  }
  return result;
}

function sourcePatches(selectedFeatures) {
  return selectedFeatures.flatMap((current) => current.source.commits.map((patch) => ({
    ...patch,
    feature: current.id,
  })));
}

function integratedPatches(selectedFeatures, domainIds, preferredDomainId) {
  const patches = [];
  const availableDomains = [...domainIds];
  for (const current of selectedFeatures) {
    if (!current.integration.domain) {
      patches.push(...current.source.commits.map((patch) => ({
        ...patch,
        features: [current.id],
      })));
      continue;
    }
    const orderedDomains = [...new Set([
      preferredDomainId,
      current.integration.domain,
      ...availableDomains.filter((id) => id !== current.integration.domain),
    ].filter(Boolean))];
    for (const sourcePatch of current.source.commits) {
      const mapping = orderedDomains
        .map((domainId) => domain(domainId))
        .filter((currentDomain) => currentDomain.integrated)
        .flatMap((currentDomain) => currentDomain.integrated.patches)
        .find((patch) => (
          patch.logicalPatch === sourcePatch.logicalPatch
          && patch.sourceCommit === sourcePatch.commit
          && patch.features.includes(current.id)
        ));
      if (mapping) {
        patches.push({ ...mapping, features: [...mapping.features] });
      }
    }
  }
  const selectedIds = new Set(selectedFeatures.map((current) => current.id));
  const orderedDomains = [...new Set([preferredDomainId, ...availableDomains].filter(Boolean))];
  for (const domainId of orderedDomains) {
    const currentDomain = domain(domainId);
    if (!currentDomain.integrated) {
      continue;
    }
    const sourceLogicalPatches = new Set(currentDomain.integrated.sourceLogicalPatches ?? []);
    for (const patch of currentDomain.integrated.patches) {
      if (!sourceLogicalPatches.has(patch.logicalPatch) && patch.features.some((id) => selectedIds.has(id))) {
        patches.push({ ...patch, features: [...patch.features] });
      }
    }
  }
  return patches;
}

function committedPath(path) {
  const repositoryPath = relative(repository, path);
  if (repositoryPath.startsWith("..")) {
    throw new Error(`path is outside repository: ${path}`);
  }
  run("git", ["ls-files", "--error-unmatch", repositoryPath], repository, { capture: true });
  run("git", ["diff", "--quiet", "HEAD", "--", repositoryPath], repository, { capture: true });
  return repositoryPath;
}

function committedFile(commit, repositoryPath) {
  return execFileSync("git", ["show", `${commit}:${repositoryPath}`], {
    cwd: repository,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
}

function trainDefinition(id, commit = null) {
  const matches = manifest.trains.filter((entry) => entry.id === id);
  if (matches.length === 0) {
    throw new Error(`unknown train: ${id}`);
  }
  if (matches.length > 1) {
    throw new Error(`duplicate train id: ${id}`);
  }
  const trainPath = matches[0].manifest;
  if (!commit) {
    return JSON.parse(readFileSync(resolve(repository, trainPath), "utf8"));
  }
  const repositoryTrainPath = committedPath(resolve(repository, trainPath));
  return JSON.parse(committedFile(commit, repositoryTrainPath));
}

let baseline;
let selectedFeatures;
let patches;
let compositionManifestCommit = null;
if (kind === "domain") {
  const selectedDomain = domain(target);
  const registeredOutputRef = `refs/heads/${selectedDomain.branch}`;
  if (outputRef !== registeredOutputRef) {
    throw new Error(`domain ${target} output must be ${registeredOutputRef}`);
  }
  if (refIsCheckedOut(outputRef)) {
    throw new Error(`domain output ref is checked out: ${outputRef}`);
  }
  if (existingOutput && selectedDomain.integrated?.commit !== existingOutput) {
    throw new Error(`domain ${target} ref tip is not the registered integrated commit`);
  }
  baseline = selectedDomain.baseline.commit;
  selectedFeatures = orderedFeatures(selectedDomain.members);
  patches = sourcePatches(selectedFeatures).map((patch) => {
    const mapping = selectedDomain.integrated?.patches.find(
      (candidate) => candidate.logicalPatch === patch.logicalPatch && candidate.sourceCommit === patch.commit,
    );
    return mapping
      ? { ...mapping, features: [...mapping.features] }
      : { ...patch, sourceCommit: patch.commit, features: [patch.feature] };
  });
  const adaptations = selectedDomain.adaptations ?? [];
  const adaptationLogicalPatches = new Set(adaptations.map((patch) => patch.logicalPatch));
  const recordedSourceLogicalPatches = new Set(selectedDomain.integrated?.sourceLogicalPatches ?? []);
  const unclassifiedMappings = selectedDomain.integrated?.patches.filter(
    (patch) => !recordedSourceLogicalPatches.has(patch.logicalPatch) && !adaptationLogicalPatches.has(patch.logicalPatch),
  ) ?? [];
  if (unclassifiedMappings.length > 0) {
    throw new Error(`domain ${target} has unclassified adaptation mappings`);
  }
  patches.push(...adaptations.map((patch) => ({ ...patch, features: [...patch.features] })));
} else if (kind === "contribution") {
  selectedFeatures = orderedFeatures([target]);
  const selectedDomain = feature(target).integration.domain
    ? domain(feature(target).integration.domain)
    : null;
  baseline = selectedDomain?.baseline.commit ?? manifest.aggregate.lastIntegratedUpstreamCommit;
  patches = integratedPatches(selectedFeatures, domains.keys(), selectedDomain?.id);
} else {
  const manifestCommit = run("git", ["rev-parse", "HEAD"], repository, { capture: true });
  compositionManifestCommit = manifestCommit;
  const repositoryManifestPath = committedPath(manifestPath);
  manifest = JSON.parse(committedFile(manifestCommit, repositoryManifestPath));
  const train = trainDefinition(target, manifestCommit);
  baseline = train.baseline.commit;
  const baselineRefCommit = run("git", ["rev-parse", "--verify", `${train.baseline.ref}^{commit}`], repository, { capture: true });
  if (baselineRefCommit !== baseline) {
    throw new Error(`train ${target} baseline ref does not match its recorded commit`);
  }
  if (!Array.isArray(train.features) || train.features.length === 0) {
    throw new Error(`train ${target} has no frozen features`);
  }
  selectedFeatures = train.features.map((id) => ({ id }));
  if (!Array.isArray(train.patches) || train.patches.length === 0) {
    throw new Error(`train ${target} has no frozen patches`);
  }
  const selectedIds = new Set(selectedFeatures.map((current) => current.id));
  patches = train.patches;
  for (const patch of patches) {
    if (patch.features.length === 0 || patch.features.some((id) => !selectedIds.has(id))) {
      throw new Error(`train patch ${patch.logicalPatch} affects an unselected feature`);
    }
  }
  for (const id of selectedIds) {
    const dependencies = train.dependencies?.[id];
    const expectedPatches = train.featurePatches?.[id];
    const sourcePatches = train.featureSources?.[id];
    if (
      !Array.isArray(dependencies)
      || !Array.isArray(expectedPatches)
      || expectedPatches.length === 0
      || !Array.isArray(sourcePatches)
      || sourcePatches.length === 0
    ) {
      throw new Error(`train feature ${id} has no complete frozen selection`);
    }
    for (const dependency of dependencies) {
      if (!selectedIds.has(dependency)) {
        throw new Error(`train feature ${id} is missing dependency ${dependency}`);
      }
    }
    const actualPatches = new Set(
      patches.filter((patch) => patch.features.includes(id)).map((patch) => patch.logicalPatch),
    );
    const expectedPatchSet = new Set(expectedPatches);
    if (
      actualPatches.size !== expectedPatchSet.size
      || [...expectedPatchSet].some((logicalPatch) => !actualPatches.has(logicalPatch))
    ) {
      throw new Error(`train feature ${id} does not match its frozen patch selection`);
    }
    for (const sourcePatch of sourcePatches) {
      const mapping = patches.find((patch) => (
        patch.logicalPatch === sourcePatch.logicalPatch
        && patch.sourceCommit === sourcePatch.commit
        && patch.features.includes(id)
      ));
      if (!mapping) {
        throw new Error(`train feature ${id} does not match its frozen source selection`);
      }
    }
  }
}

const logicalPatches = new Set();
const uniquePatches = [];
for (const patch of patches) {
  if (logicalPatches.has(patch.logicalPatch)) {
    const canonical = uniquePatches.find((candidate) => candidate.logicalPatch === patch.logicalPatch);
    const canonicalSource = canonical.sourceCommit ?? canonical.commit;
    const patchSource = patch.sourceCommit ?? patch.commit;
    if (kind === "train" || canonicalSource !== patchSource) {
      throw new Error(`duplicate logical patch requires one frozen canonical mapping: ${patch.logicalPatch}`);
    }
    canonical.features = [...new Set([...canonical.features, ...patch.features])];
    continue;
  }
  logicalPatches.add(patch.logicalPatch);
  uniquePatches.push(patch);
}

if (kind === "contribution") {
  for (const current of selectedFeatures) {
    for (const sourcePatch of current.source.commits) {
      const mapping = uniquePatches.find((patch) => patch.logicalPatch === sourcePatch.logicalPatch);
      if (
        !mapping
        || (mapping.sourceCommit ?? mapping.commit) !== sourcePatch.commit
        || !mapping.features.includes(current.id)
      ) {
        throw new Error(`contribution feature ${current.id} has no current domain mapping for ${sourcePatch.logicalPatch}`);
      }
    }
  }
}

function requireCommitId(value, label) {
  if (!/^[0-9a-f]{40}$/.test(value)) {
    throw new Error(`${label} must be a full immutable commit ID`);
  }
  const resolved = run("git", ["rev-parse", "--verify", `${value}^{commit}`], repository, { capture: true });
  if (resolved !== value) {
    throw new Error(`${label} does not resolve to its recorded commit ID`);
  }
}

requireCommitId(baseline, "baseline");
for (const patch of uniquePatches) {
  requireCommitId(patch.commit, `patch ${patch.logicalPatch}`);
  if (patch.sourceCommit) {
    requireCommitId(patch.sourceCommit, `source patch ${patch.logicalPatch}`);
  }
}

const applications = [];
const applicationsByCommit = new Map();
for (const patch of uniquePatches) {
  let application = applicationsByCommit.get(patch.commit);
  if (!application) {
    application = { commit: patch.commit, patches: [] };
    applicationsByCommit.set(patch.commit, application);
    applications.push(application);
  }
  application.patches.push(patch);
}

const temporary = mkdtempSync(resolve(tmpdir(), "local-aggregate-compose-"));
let worktreeAdded = false;
let trainProvenance = null;
try {
  run("git", ["cat-file", "-e", `${baseline}^{commit}`], repository, { capture: true });
  for (const patch of uniquePatches) {
    run("git", ["cat-file", "-e", `${patch.commit}^{commit}`], repository, { capture: true });
  }
  run("git", ["worktree", "add", "--detach", temporary, baseline], repository);
  worktreeAdded = true;
  const applied = [];
  for (const application of applications) {
    run("git", ["cherry-pick", "-x", application.commit], temporary);
    const appliedCommit = run("git", ["rev-parse", "HEAD"], temporary, { capture: true });
    for (const patch of application.patches) {
      applied.push({
        logicalPatch: patch.logicalPatch,
        sourceCommit: patch.sourceCommit ?? patch.commit,
        commit: appliedCommit,
        features: patch.features,
      });
    }
  }
  if (kind === "train") {
    const manifestCommit = compositionManifestCommit;
    const repositoryManifestPath = committedPath(manifestPath);
    const trainPath = manifest.trains.find((entry) => entry.id === target).manifest;
    const repositoryTrainPath = committedPath(resolve(repository, trainPath));
    const trainBytes = committedFile(manifestCommit, repositoryTrainPath);
    run("git", ["checkout", manifestCommit, "--", repositoryManifestPath, repositoryTrainPath], temporary);
    run("git", ["add", repositoryManifestPath, repositoryTrainPath], temporary);
    run("git", ["commit", "-m", `chore(maintenance): bind ${target} train manifest`], temporary);
    trainProvenance = {
      manifestCommit,
      trainSha256: createHash("sha256").update(trainBytes).digest("hex"),
    };
  }
  const commit = run("git", ["rev-parse", "HEAD"], temporary, { capture: true });
  run("git", ["update-ref", outputRef, commit, kind === "domain" ? existingOutput ?? "" : ""], repository);
  process.stdout.write(`${JSON.stringify({
    kind,
    target,
    outputRef,
    baseline,
    commit,
    ...trainProvenance,
    features: selectedFeatures.map((current) => current.id),
    patches: applied,
  }, null, 2)}\n`);
} finally {
  if (worktreeAdded) {
    try {
      run("git", ["worktree", "remove", "--force", temporary], repository, { capture: true });
    } catch {
    }
  }
  rmSync(temporary, { recursive: true, force: true });
}
