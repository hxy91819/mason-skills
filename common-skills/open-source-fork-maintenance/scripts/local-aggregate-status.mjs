import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
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

const repositoryRoot = resolve(valueAfter("--repo") ?? process.cwd());
const manifestInput = valueAfter("--manifest") ?? "config/local-aggregate-features.json";
const manifestPath = resolve(repositoryRoot, manifestInput);
const outputJson = args.includes("--json");

function run(command, commandArgs) {
  try {
    return {
      ok: true,
      output: execFileSync(command, commandArgs, {
        cwd: repositoryRoot,
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
      }).trim(),
    };
  } catch (error) {
    return {
      ok: false,
      output: error.stdout?.toString().trim() ?? "",
      error: error.stderr?.toString().trim() ?? error.message,
    };
  }
}

function git(commandArgs) {
  return run("git", commandArgs);
}

function gh(commandArgs) {
  return run("gh", commandArgs);
}

function commitExists(commit) {
  return git(["cat-file", "-e", `${commit}^{commit}`]).ok;
}

function isAncestor(older, newer) {
  return git(["merge-base", "--is-ancestor", older, newer]).ok;
}

function revision(ref) {
  const result = git(["rev-parse", "--verify", `${ref}^{commit}`]);
  return result.ok ? result.output : null;
}

function commitsBetween(start, end) {
  const result = git(["log", "--format=%H%x09%s", `${start}..${end}`]);
  if (!result.ok || !result.output) {
    return [];
  }
  return result.output.split("\n").map((line) => {
    const [commit, subject] = line.split("\t", 2);
    return { commit, subject };
  });
}

function inspectRevision(recordedCommit, currentRef) {
  const currentCommit = revision(currentRef);
  if (!currentCommit) {
    return { state: "missing-ref", currentCommit: null, commits: [] };
  }
  if (!commitExists(recordedCommit)) {
    return { state: "recorded-commit-missing", currentCommit, commits: [] };
  }
  if (recordedCommit === currentCommit) {
    return { state: "packaged", currentCommit, commits: [] };
  }
  if (isAncestor(recordedCommit, currentCommit)) {
    return {
      state: "advanced",
      currentCommit,
      commits: commitsBetween(recordedCommit, currentCommit),
    };
  }
  if (isAncestor(currentCommit, recordedCommit)) {
    return { state: "behind-recorded", currentCommit, commits: [] };
  }
  return { state: "rewritten", currentCommit, commits: [] };
}

function inspectUnpackagedBranch(branch, upstreamRef) {
  const currentCommit = revision(branch);
  if (!currentCommit) {
    return { state: "missing-ref", currentCommit: null, commits: [] };
  }
  const base = git(["merge-base", upstreamRef, branch]);
  return {
    state: "unpackaged",
    currentCommit,
    commits: base.ok ? commitsBetween(base.output, branch) : [],
  };
}

function worktreesByBranch() {
  const result = git(["worktree", "list", "--porcelain"]);
  if (!result.ok) {
    return new Map();
  }
  const worktrees = new Map();
  for (const record of result.output.split("\n\n")) {
    const lines = record.split("\n");
    const worktree = lines.find((line) => line.startsWith("worktree "));
    const branch = lines.find((line) => line.startsWith("branch refs/heads/"));
    if (worktree && branch) {
      worktrees.set(
        branch.slice("branch refs/heads/".length),
        worktree.slice("worktree ".length),
      );
    }
  }
  return worktrees;
}

function localFeatureBranches() {
  const result = git(["for-each-ref", "--format=%(refname:short)", "refs/heads"]);
  if (!result.ok || !result.output) {
    return [];
  }
  return result.output
    .split("\n")
    .filter((branch) => branch.startsWith("feature/") || branch.startsWith("fix/"))
    .sort();
}

function statusEntries() {
  const result = git(["status", "--porcelain=v1", "--untracked-files=normal"]);
  if (!result.ok || !result.output) {
    return { tracked: [], untracked: [] };
  }
  const tracked = [];
  const untracked = [];
  for (const line of result.output.split("\n")) {
    if (line.startsWith("?? ")) {
      untracked.push(line.slice(3));
    } else {
      tracked.push(line);
    }
  }
  return { tracked, untracked };
}

function describeCommit(commit) {
  const result = git(["show", "-s", "--format=%s", commit]);
  return result.ok ? result.output : "unable to read commit subject";
}

function aggregateMappingValid(lastPackaged) {
  if (!lastPackaged) {
    return null;
  }
  if (!commitExists(lastPackaged.aggregateCommit)) {
    return false;
  }
  const body = git(["show", "-s", "--format=%B", lastPackaged.aggregateCommit]);
  return body.ok && body.output.includes(lastPackaged.sourceCommit);
}

function latestStableRelease(aggregate) {
  if (typeof aggregate.stableTagPattern !== "string") {
    return { state: "not-configured", tag: null, commit: null, commits: [] };
  }
  const tags = git(["tag", "--merged", aggregate.upstreamRef, "--sort=-version:refname"]);
  if (!tags.ok || !tags.output) {
    return { state: "not-found", tag: null, commit: null, commits: [] };
  }
  const pattern = new RegExp(aggregate.stableTagPattern);
  const tag = tags.output.split("\n").find((candidate) => pattern.test(candidate));
  if (!tag) {
    return { state: "not-found", tag: null, commit: null, commits: [] };
  }
  const commit = revision(tag);
  if (!commit) {
    return { state: "not-found", tag: null, commit: null, commits: [] };
  }
  if (isAncestor(commit, aggregate.lastIntegratedUpstreamCommit)) {
    return { tag, commit, state: "included-in-baseline", commits: [] };
  }
  if (isAncestor(aggregate.lastIntegratedUpstreamCommit, commit)) {
    return {
      tag,
      commit,
      state: "released-after-baseline",
      commits: commitsBetween(aggregate.lastIntegratedUpstreamCommit, tag),
    };
  }
  return { tag, commit, state: "diverged", commits: [] };
}

function summarize(value) {
  const normalized = value.replace(/\s+/gu, " ").trim();
  return normalized.length > 180 ? `${normalized.slice(0, 177)}…` : normalized;
}

function relatedPullRequestReferences(issue, comments) {
  const references = new Map();
  const pattern = /https:\/\/github\.com\/([^/\s]+\/[^/\s]+)\/pull\/(\d+)/gu;
  function addReference(repository, number) {
    if (typeof repository === "string" && Number.isInteger(number) && number > 0) {
      references.set(`${repository}#${number}`, { repository, number });
    }
  }
  for (const text of [issue.body ?? "", ...comments.map((comment) => comment.body ?? "")]) {
    for (const match of text.matchAll(pattern)) {
      addReference(match[1], Number(match[2]));
    }
  }
  for (const pullRequest of issue.closedByPullRequestsReferences ?? []) {
    const repository =
      pullRequest.repository?.nameWithOwner ??
      (typeof pullRequest.repository === "string" ? pullRequest.repository : null);
    addReference(repository, pullRequest.number);
  }
  return [...references.values()];
}

function inspectPullRequest(reference) {
  const result = gh([
    "pr",
    "view",
    String(reference.number),
    "--repo",
    reference.repository,
    "--json",
    "number,title,state,mergedAt,closedAt,updatedAt,url",
  ]);
  if (!result.ok) {
    return { ...reference, state: "unavailable" };
  }
  try {
    const pullRequest = JSON.parse(result.output);
    return {
      repository: reference.repository,
      number: pullRequest.number,
      title: pullRequest.title,
      state: pullRequest.state,
      mergedAt: pullRequest.mergedAt,
      closedAt: pullRequest.closedAt,
      updatedAt: pullRequest.updatedAt,
      url: pullRequest.url,
    };
  } catch {
    return { ...reference, state: "unavailable" };
  }
}

function inspectUpstreamIssue(reference) {
  const result = gh([
    "issue",
    "view",
    String(reference.number),
    "--repo",
    reference.repository,
    "--json",
    "number,title,state,stateReason,closedAt,updatedAt,url,body,comments,closedByPullRequestsReferences",
  ]);
  if (!result.ok) {
    return {
      ...reference,
      state: "unavailable",
      newerReplies: [],
      relatedPullRequests: [],
    };
  }
  try {
    const issue = JSON.parse(result.output);
    const comments = issue.comments ?? [];
    const hasCommentAnchor = reference.feedbackUrl.includes("#issuecomment-");
    const feedbackIndex = comments.findIndex((comment) => comment.url === reference.feedbackUrl);
    const replies = hasCommentAnchor && feedbackIndex >= 0 ? comments.slice(feedbackIndex + 1) : comments;
    return {
      repository: reference.repository,
      number: issue.number,
      feedbackUrl: reference.feedbackUrl,
      title: issue.title,
      state: issue.state,
      stateReason: issue.stateReason,
      closedAt: issue.closedAt,
      updatedAt: issue.updatedAt,
      url: issue.url,
      feedbackFound: !hasCommentAnchor || feedbackIndex >= 0,
      newerReplies: replies.map((reply) => ({
        author: reply.author?.login ?? "unknown",
        createdAt: reply.createdAt,
        url: reply.url,
        summary: summarize(reply.body ?? ""),
      })),
      relatedPullRequests: relatedPullRequestReferences(issue, comments).map(inspectPullRequest),
    };
  } catch {
    return {
      ...reference,
      state: "unavailable",
      newerReplies: [],
      relatedPullRequests: [],
    };
  }
}

function nonEmptyString(value) {
  return typeof value === "string" && value.length > 0;
}

function assertManifest(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("local aggregate manifest must be an object");
  }
  if (value.version !== 2) {
    throw new Error("local aggregate manifest version must be 2");
  }
  if (
    !value.aggregate ||
    typeof value.aggregate !== "object" ||
    !nonEmptyString(value.aggregate.branch) ||
    !nonEmptyString(value.aggregate.upstreamRef) ||
    !nonEmptyString(value.aggregate.lastIntegratedUpstreamCommit) ||
    (value.aggregate.stableTagPattern !== null && !nonEmptyString(value.aggregate.stableTagPattern))
  ) {
    throw new Error("local aggregate manifest aggregate is invalid");
  }
  if (!Array.isArray(value.features)) {
    throw new Error("local aggregate manifest features must be an array");
  }
  if (typeof value.aggregate.stableTagPattern === "string") {
    try {
      new RegExp(value.aggregate.stableTagPattern);
    } catch {
      throw new Error("local aggregate manifest stableTagPattern must be a valid regular expression");
    }
  }
  const branches = new Set();
  for (const feature of value.features) {
    const lastPackagedValid =
      feature?.lastPackaged === null ||
      (feature?.lastPackaged &&
        typeof feature.lastPackaged === "object" &&
        nonEmptyString(feature.lastPackaged.sourceCommit) &&
        nonEmptyString(feature.lastPackaged.aggregateCommit));
    const upstreamIssuesValid =
      Array.isArray(feature?.upstreamIssues) &&
      feature.upstreamIssues.length > 0 &&
      feature.upstreamIssues.every(
        (issue) =>
          issue &&
          typeof issue === "object" &&
          nonEmptyString(issue.repository) &&
          Number.isInteger(issue.number) &&
          issue.number > 0 &&
          nonEmptyString(issue.feedbackUrl),
      );
    if (
      !feature ||
      typeof feature !== "object" ||
      !nonEmptyString(feature.branch) ||
      !lastPackagedValid ||
      !upstreamIssuesValid ||
      branches.has(feature.branch)
    ) {
      throw new Error("local aggregate manifest feature is invalid");
    }
    branches.add(feature.branch);
  }
}

const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
assertManifest(manifest);

const currentBranch = git(["branch", "--show-current"]).output;
const worktrees = worktreesByBranch();
const registeredBranches = new Set(manifest.features.map((feature) => feature.branch));
const featureStatuses = manifest.features.map((feature) => ({
  ...feature,
  worktree: worktrees.get(feature.branch) ?? null,
  source: feature.lastPackaged
    ? inspectRevision(feature.lastPackaged.sourceCommit, feature.branch)
    : inspectUnpackagedBranch(feature.branch, manifest.aggregate.upstreamRef),
  aggregateCommitPresent: feature.lastPackaged ? commitExists(feature.lastPackaged.aggregateCommit) : null,
  aggregateMappingValid: aggregateMappingValid(feature.lastPackaged),
  upstreamIssues: feature.upstreamIssues.map(inspectUpstreamIssue),
}));
const upstream = inspectRevision(
  manifest.aggregate.lastIntegratedUpstreamCommit,
  manifest.aggregate.upstreamRef,
);
const stableRelease = latestStableRelease(manifest.aggregate);
const workingTree = statusEntries();
const discoveredBranches = localFeatureBranches();
const unregisteredBranches = discoveredBranches.filter((branch) => !registeredBranches.has(branch));
const report = {
  manifestPath: relative(repositoryRoot, manifestPath) || ".",
  aggregate: {
    expectedBranch: manifest.aggregate.branch,
    currentBranch,
    upstreamRef: manifest.aggregate.upstreamRef,
    lastIntegratedUpstreamCommit: manifest.aggregate.lastIntegratedUpstreamCommit,
    upstream,
    stableRelease,
  },
  workingTree,
  features: featureStatuses,
  unregisteredBranches: unregisteredBranches.map((branch) => ({
    branch,
    worktree: worktrees.get(branch) ?? null,
    head: revision(branch),
    subject: describeCommit(branch),
  })),
};

if (outputJson) {
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
} else {
  const labels = {
    source: {
      packaged: "matches the last package",
      unpackaged: "not yet packaged; default aggregate candidate",
      advanced: "has commits to package",
      rewritten: "history was rewritten; rebuild required",
      "behind-recorded": "is behind the recorded source commit",
      "missing-ref": "branch is missing",
      "recorded-commit-missing": "recorded source commit is missing",
    },
    upstream: {
      packaged: "matches the recorded aggregate baseline",
      advanced: "has commits to assess",
      rewritten: "has diverged from the recorded baseline",
      "behind-recorded": "recorded baseline is ahead of the upstream ref",
      "missing-ref": "upstream ref is unavailable",
      "recorded-commit-missing": "recorded upstream baseline is missing",
    },
  };
  console.log("# Local aggregate status\n");
  console.log(`- Registry: \`${report.manifestPath}\``);
  console.log(`- Current branch: \`${currentBranch || "detached HEAD"}\` (expected \`${manifest.aggregate.branch}\`)`);
  console.log(`- Upstream: \`${manifest.aggregate.upstreamRef}\``);
  console.log(`- Upstream baseline: \`${manifest.aggregate.lastIntegratedUpstreamCommit.slice(0, 9)}\` — ${labels.upstream[upstream.state]}`);
  for (const commit of upstream.commits) {
    console.log(`  - \`${commit.commit.slice(0, 9)}\` ${commit.subject}`);
  }
  if (stableRelease.state === "not-configured") {
    console.log("- Stable release tag: not configured");
  } else if (stableRelease.state === "not-found") {
    console.log("- Stable release tag: no matching reachable tag");
  } else {
    console.log(`- Stable release tag: \`${stableRelease.tag}\` — ${stableRelease.state}`);
  }
  console.log(`- Working tree: ${workingTree.tracked.length} tracked change(s), ${workingTree.untracked.length} untracked item(s)`);
  console.log("\n## Registered branches\n");
  if (featureStatuses.length === 0) {
    console.log("None.");
  }
  for (const feature of featureStatuses) {
    console.log(`- \`${feature.branch}\`: ${labels.source[feature.source.state]}`);
    console.log(`  - Worktree: ${feature.worktree ? `\`${feature.worktree}\`` : "not found"}`);
    if (feature.lastPackaged) {
      const aggregateMapping = !feature.aggregateCommitPresent
        ? "INVALID — aggregate commit is missing"
        : !feature.aggregateMappingValid
          ? "INVALID — aggregate commit does not retain the source SHA"
          : "valid";
      console.log(`  - Aggregate mapping: ${aggregateMapping}`);
    }
    for (const commit of feature.source.commits) {
      console.log(`  - \`${commit.commit.slice(0, 9)}\` ${commit.subject}`);
    }
    for (const issue of feature.upstreamIssues) {
      console.log(`  - Upstream \`${issue.repository}#${issue.number}\`: ${issue.state}; ${issue.newerReplies.length} newer reply/replies`);
      for (const pullRequest of issue.relatedPullRequests) {
        console.log(`    - Related PR \`${pullRequest.repository}#${pullRequest.number}\`: ${pullRequest.state}`);
      }
    }
  }
  console.log("\n## Unregistered feature/fix branches\n");
  if (report.unregisteredBranches.length === 0) {
    console.log("None.");
  }
  for (const branch of report.unregisteredBranches) {
    console.log(`- \`${branch.branch}\`: \`${branch.head?.slice(0, 9) ?? "unknown"}\` ${branch.subject}`);
  }
}
