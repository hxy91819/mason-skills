import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
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
  const forkRemote = join(dir, "fork.git");
  const root = join(dir, "root");
  try {
    git(dir, "init", "-q", "-b", "main", upstream);
    git(upstream, "config", "user.email", "t@example.com");
    git(upstream, "config", "user.name", "T");
    commitFile(upstream, "app.txt", "line1\nline2\nline3\n", "v1");
    git(upstream, "tag", "v1");
    git(dir, "init", "-q", "--bare", forkRemote);
    git(dir, "clone", "-q", upstream, root);
    git(root, "config", "user.email", "t@example.com");
    git(root, "config", "user.name", "T");
    git(root, "remote", "add", "fork", forkRemote);
    git(root, "checkout", "-q", "-b", "local/aggregate", "v1");
    git(root, "push", "-q", "fork", "local/aggregate");
    run({ upstream, root });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

function addBranch(root, name, file, content) {
  git(root, "branch", name, "v1");
  const wt = join(root, "..", name.replaceAll("/", "-"));
  git(root, "worktree", "add", "-q", wt, name);
  commitFile(wt, file, content, name);
  git(root, "push", "-q", "fork", name);
}

function writeList(root, base, branches) {
  const wt = join(root, "..", "tooling");
  git(root, "worktree", "add", "-q", "-B", "fork-tooling", wt, "v1");
  execFileSync("mkdir", ["-p", join(wt, ".fork")]);
  const lines = [`base ${base}`, "fork-tooling internal", ...branches.map((b) => `${b} needs-feedback # ${b}`)];
  commitFile(wt, ".fork/branches", `# list\n${lines.join("\n")}\n`, "list");
}

test("merges every listed branch onto the base tag", () => {
  withFork(({ root }) => {
    addBranch(root, "feature/a", "a.txt", "a\n");
    addBranch(root, "feature/b", "b.txt", "b\n");
    writeList(root, "v1", ["feature/a", "feature/b"]);
    const { status, output } = runAggregate(root);
    assert.equal(status, 0, output);
    const tree = git(root, "ls-tree", "--name-only", "aggregate/next");
    assert.match(tree, /a\.txt/);
    assert.match(tree, /b\.txt/);
    assert.match(tree, /\.fork/);
  });
});

test("a conflict between fork branches stops, and its recorded resolution replays", () => {
  withFork(({ root }) => {
    addBranch(root, "fix/x", "app.txt", "line1\nX\nline3\n");
    addBranch(root, "fix/y", "app.txt", "line1\nY\nline3\n");
    writeList(root, "v1", ["fix/x", "fix/y"]);
    const first = runAggregate(root);
    assert.equal(first.status, 1);
    assert.match(first.output, /CONFLICT fix\/y/);
    assert.match(first.output, /fork 分支之间的冲突/);
    const wt = join(root, ".worktrees", "aggregate-next");
    writeFileSync(join(wt, "app.txt"), "line1\nX\nY\nline3\n");
    git(wt, "add", "app.txt");
    git(wt, "commit", "-q", "--no-edit");
    const second = runAggregate(root);
    assert.equal(second.status, 0, second.output);
    assert.match(second.output, /rerere +fix\/y/);
    assert.equal(git(root, "show", "aggregate/next:app.txt"), "line1\nX\nY\nline3");
  });
});

test("a branch that conflicts with a new upstream tag is sent back to its own rebase", () => {
  withFork(({ upstream, root }) => {
    addBranch(root, "fix/z", "app.txt", "line1\nZ\nline3\n");
    commitFile(upstream, "app.txt", "line1\nUPSTREAM\nline3\n", "v2");
    git(upstream, "tag", "v2");
    writeList(root, "v1", ["fix/z"]);
    const { status, output } = runAggregate(root, "--base", "v2");
    assert.equal(status, 1);
    assert.match(output, /该分支单独合入 v2 就冲突/);
  });
});

test("--promote moves local/aggregate and publishes it to the fork", () => {
  withFork(({ root }) => {
    addBranch(root, "feature/a", "a.txt", "a\n");
    writeList(root, "v1", ["feature/a"]);
    const { status, output } = runAggregate(root, "--promote");
    assert.equal(status, 0, output);
    const head = git(root, "rev-parse", "HEAD");
    assert.equal(head, git(root, "rev-parse", "aggregate/next"));
    assert.equal(git(root, "ls-remote", "fork", "refs/heads/local/aggregate").split("\t")[0], head);
  });
});
