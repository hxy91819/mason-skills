import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const script = join(dirname(fileURLToPath(import.meta.url)), "..", "assets", "fork-aggregate");

function git(cwd, ...args) {
  return execFileSync("git", args, {
    cwd,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, GIT_CONFIG_GLOBAL: "/dev/null", GIT_CONFIG_NOSYSTEM: "1" },
  }).trim();
}

function commitFile(cwd, file, content, message) {
  writeFileSync(join(cwd, file), content);
  git(cwd, "add", file);
  git(cwd, "commit", "-q", "-m", message);
}

function runAggregate(cwd, ...args) {
  const result = spawnSync("bash", [script, ...args], {
    cwd,
    encoding: "utf8",
    env: { ...process.env, GIT_CONFIG_GLOBAL: "/dev/null", GIT_CONFIG_NOSYSTEM: "1" },
  });
  return { status: result.status, output: result.stdout + result.stderr };
}

function withFork(run) {
  const dir = mkdtempSync(join(tmpdir(), "fork-aggregate-"));
  const upstream = join(dir, "upstream");
  const originRemote = join(dir, "origin.git");
  const root = join(dir, "root");
  try {
    git(dir, "init", "-q", "-b", "main", upstream);
    git(upstream, "config", "user.email", "t@example.com");
    git(upstream, "config", "user.name", "T");
    commitFile(upstream, "app.txt", "line1\nline2\nline3\n", "v1");
    git(upstream, "tag", "v1");
    git(dir, "init", "-q", "--bare", "-b", "main", originRemote);
    git(dir, "clone", "-q", upstream, root);
    git(root, "config", "user.email", "t@example.com");
    git(root, "config", "user.name", "T");
    git(root, "remote", "rename", "origin", "upstream");
    git(root, "remote", "add", "origin", originRemote);
    git(root, "checkout", "-q", "main");
    git(root, "push", "-q", "origin", "main");
    run({ dir, upstream, originRemote, root });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

function addBranch(root, name, file, content, base = "main") {
  const wt = join(root, "..", name.replaceAll("/", "-"));
  git(root, "worktree", "add", "-q", "-b", name, wt, base);
  commitFile(wt, file, content, name);
  git(root, "push", "-q", "origin", name);
}

function addSecurityBaseline(root) {
  const wt = join(root, "..", "security-baseline");
  git(root, "worktree", "add", "-q", "-b", "security/baseline", wt, "main");
  commitFile(wt, "security.txt", "patched\n", "security baseline");
  git(root, "push", "-q", "origin", "security/baseline");
}

function mergeBaselineIntoMain(root) {
  git(root, "merge", "-q", "--no-ff", "-m", "Merge security/baseline", "security/baseline");
  git(root, "push", "-q", "origin", "main");
}

function securityWorktree(root) {
  return join(root, "..", "security-baseline");
}

function writeList(root, base, branches) {
  const wt = join(root, "..", "tooling");
  git(root, "worktree", "add", "-q", "-B", "fork-tooling", wt, "main");
  mkdirSync(join(wt, ".fork"), { recursive: true });
  const lines = [`base ${base}`, "fork-tooling internal", ...branches.map((b) => `${b} needs-feedback # ${b}`)];
  commitFile(wt, ".fork/branches", `# list\n${lines.join("\n")}\n`, "list");
}

test("merges every listed branch onto main without moving root main", () => {
  withFork(({ root }) => {
    addBranch(root, "feature/a", "a.txt", "a\n");
    addBranch(root, "feature/b", "b.txt", "b\n");
    writeList(root, "v1", ["feature/a", "feature/b"]);
    const before = git(root, "rev-parse", "main");
    const { status, output } = runAggregate(root);
    assert.equal(status, 0, output);
    assert.equal(git(root, "rev-parse", "main"), before);
    assert.equal(git(root, "rev-parse", "HEAD"), before);
    const tree = git(root, "ls-tree", "--name-only", "aggregate-next");
    assert.match(tree, /a\.txt/);
    assert.match(tree, /b\.txt/);
    assert.match(tree, /\.fork/);
  });
});

test("requires security/baseline in main and includes it in the aggregate", () => {
  withFork(({ root }) => {
    addSecurityBaseline(root);
    writeList(root, "v1", ["feature/a"]);
    const blocked = runAggregate(root);
    assert.equal(blocked.status, 1, blocked.output);
    assert.match(blocked.output, /security\/baseline 尚未合入 main/);
    mergeBaselineIntoMain(root);
    addBranch(root, "feature/a", "a.txt", "a\n");
    const { status, output } = runAggregate(root);
    assert.equal(status, 0, output);
    assert.equal(git(root, "show", "aggregate-next:security.txt"), "patched");
  });
});

test("a conflict between branches stops, and its recorded resolution replays", () => {
  withFork(({ root }) => {
    addBranch(root, "fix/x", "app.txt", "line1\nX\nline3\n");
    addBranch(root, "fix/y", "app.txt", "line1\nY\nline3\n");
    writeList(root, "v1", ["fix/x", "fix/y"]);
    const first = runAggregate(root);
    assert.equal(first.status, 1);
    assert.match(first.output, /CONFLICT fix\/y/);
    assert.match(first.output, /两个分支之间的冲突/);
    const wt = join(root, ".worktrees", "aggregate-next");
    writeFileSync(join(wt, "app.txt"), "line1\nX\nY\nline3\n");
    git(wt, "add", "app.txt");
    git(wt, "commit", "-q", "--no-edit");
    const second = runAggregate(root);
    assert.equal(second.status, 0, second.output);
    assert.match(second.output, /rerere +fix\/y/);
    assert.equal(git(root, "show", "aggregate-next:app.txt"), "line1\nX\nY\nline3");
  });
});

test("a branch that conflicts with a new upstream tag is sent back to its own rebase", () => {
  withFork(({ upstream, root }) => {
    addBranch(root, "fix/z", "app.txt", "line1\nZ\nline3\n");
    commitFile(upstream, "app.txt", "line1\nUPSTREAM\nline3\n", "v2");
    git(upstream, "tag", "v2");
    writeList(root, "v2", ["fix/z"]);
    const stale = runAggregate(root);
    assert.equal(stale.status, 1);
    assert.match(stale.output, /main 尚未包含基线 tag v2/);
    git(root, "merge", "-q", "--no-ff", "-m", "v2", "v2");
    git(root, "push", "-q", "origin", "main");
    const { status, output } = runAggregate(root);
    assert.equal(status, 1);
    assert.match(output, /单独合入 main（v2 基线）就冲突/);
  });
});

test("--promote publishes aggregate without moving root main", () => {
  withFork(({ dir, root }) => {
    addBranch(root, "feature/a", "a.txt", "a\n");
    writeList(root, "v1", ["feature/a"]);
    const mainBefore = git(root, "rev-parse", "main");
    git(root, "checkout", "-q", "-b", "scratch", "main");
    const scratchBefore = git(root, "rev-parse", "HEAD");
    const { status, output } = runAggregate(root, "--promote");
    assert.equal(status, 0, output);
    assert.equal(git(root, "branch", "--show-current"), "scratch");
    assert.equal(git(root, "rev-parse", "HEAD"), scratchBefore);
    assert.equal(git(root, "rev-parse", "main"), mainBefore);
    const aggregate = git(root, "rev-parse", "aggregate-next");
    const aggregateTree = git(root, "rev-parse", "aggregate-next^{tree}");
    assert.equal(git(root, "ls-remote", "origin", "refs/heads/aggregate").split("\t")[0], aggregate);
    assert.equal(git(root, "ls-remote", "origin", "refs/heads/main").split("\t")[0], mainBefore);
    const clone = join(dir, "clone");
    git(root, "clone", "-q", git(root, "remote", "get-url", "origin"), clone);
    assert.equal(git(clone, "branch", "--show-current"), "main");
    assert.equal(git(clone, "rev-parse", "HEAD"), mainBefore);
    const second = runAggregate(root, "--promote");
    assert.equal(second.status, 0, second.output);
    assert.equal(git(root, "rev-parse", "main"), mainBefore);
    assert.equal(git(root, "rev-parse", "aggregate-next^{tree}"), aggregateTree);
    const after = git(root, "ls-remote", "origin", "refs/heads/aggregate").split("\t")[0];
    assert.equal(git(root, "merge-base", "--is-ancestor", aggregate, after), "");
  });
});

test("origin security/baseline ahead of local is adopted and must be in main", () => {
  withFork(({ root }) => {
    addSecurityBaseline(root);
    mergeBaselineIntoMain(root);
    writeList(root, "v1", []);
    const wt = securityWorktree(root);
    commitFile(wt, "security.txt", "patched\nremote-extra\n", "remote baseline");
    const remoteTip = git(wt, "rev-parse", "HEAD");
    git(root, "push", "-q", "origin", "security/baseline");
    git(wt, "reset", "-q", "--hard", "HEAD~1");
    const blocked = runAggregate(root);
    assert.equal(blocked.status, 1, blocked.output);
    assert.match(blocked.output, /security\/baseline 尚未合入 main/);
    assert.ok(blocked.output.includes(remoteTip), blocked.output);
    git(root, "merge", "-q", "--no-ff", "-m", "Merge newer security baseline", remoteTip);
    git(root, "push", "-q", "origin", "main");
    const { status, output } = runAggregate(root);
    assert.equal(status, 0, output);
    assert.equal(git(root, "show", "aggregate-next:security.txt"), "patched\nremote-extra");
  });
});

test("local security/baseline ahead of origin is adopted and must be in main", () => {
  withFork(({ root }) => {
    addSecurityBaseline(root);
    mergeBaselineIntoMain(root);
    writeList(root, "v1", []);
    const wt = securityWorktree(root);
    commitFile(wt, "security.txt", "patched\nlocal-extra\n", "local baseline");
    const localTip = git(wt, "rev-parse", "HEAD");
    const blocked = runAggregate(root);
    assert.equal(blocked.status, 1, blocked.output);
    assert.match(blocked.output, /security\/baseline 尚未合入 main/);
    assert.ok(blocked.output.includes(localTip), blocked.output);
    git(root, "merge", "-q", "--no-ff", "-m", "Merge local security baseline", "security/baseline");
    git(root, "push", "-q", "origin", "main");
    const { status, output } = runAggregate(root);
    assert.equal(status, 0, output);
    assert.equal(git(root, "show", "aggregate-next:security.txt"), "patched\nlocal-extra");
  });
});

test("diverged local and origin security/baseline tips are rejected", () => {
  withFork(({ root }) => {
    addSecurityBaseline(root);
    mergeBaselineIntoMain(root);
    writeList(root, "v1", []);
    const wt = securityWorktree(root);
    commitFile(wt, "security.txt", "patched\nlocal\n", "local baseline");
    const other = join(root, "..", "baseline-other");
    git(root, "worktree", "add", "-q", "--detach", other, "security/baseline~1");
    commitFile(other, "security.txt", "patched\norigin\n", "origin baseline");
    git(other, "push", "-q", "origin", "HEAD:refs/heads/security/baseline");
    const mainBefore = git(root, "rev-parse", "main");
    const { status, output } = runAggregate(root);
    assert.equal(status, 1, output);
    assert.match(output, /security\/baseline.*分叉/);
    assert.equal(git(root, "rev-parse", "main"), mainBefore);
    assert.equal(git(root, "ls-remote", "origin", "refs/heads/aggregate"), "");
  });
});

test("--promote-only publishes the verified SHA without rebuilding", () => {
  withFork(({ root }) => {
    addBranch(root, "feature/a", "a.txt", "a\n");
    writeList(root, "v1", ["feature/a"]);
    const built = runAggregate(root);
    assert.equal(built.status, 0, built.output);
    const verified = git(root, "rev-parse", "aggregate-next");
    const verifiedTree = git(root, "rev-parse", "aggregate-next^{tree}");
    const mainBefore = git(root, "rev-parse", "main");
    const promoted = runAggregate(root, "--promote-only", "--result", verified);
    assert.equal(promoted.status, 0, promoted.output);
    assert.equal(git(root, "rev-parse", "aggregate-next"), verified);
    assert.equal(git(root, "rev-parse", "aggregate-next^{tree}"), verifiedTree);
    assert.equal(git(root, "rev-parse", "main"), mainBefore);
    assert.equal(git(root, "ls-remote", "origin", "refs/heads/aggregate").split("\t")[0], verified);
  });
});
