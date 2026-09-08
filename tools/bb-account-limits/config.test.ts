import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { loadLocalAccountLimitsConfig, localAccountLimitsConfigCandidates } from "./config.js";

async function withLocalConfig(body: string | null) {
  const dir = await mkdtemp(join(tmpdir(), "account-limits-config-"));
  const file = join(dir, "local.json");
  if (body !== null) await writeFile(file, body);
  const warnings: string[] = [];
  try {
    const overrides = loadLocalAccountLimitsConfig([pathToFileURL(file)], message => warnings.push(message));
    return { overrides, warnings };
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

test("missing local config yields no overrides and no warnings", async () => {
  const { overrides, warnings } = await withLocalConfig(null);
  assert.deepEqual(overrides, {});
  assert.deepEqual(warnings, []);
});

test("valid local config overrides only the fields it provides", async () => {
  const { overrides, warnings } = await withLocalConfig(JSON.stringify({
    enabledProviders: ["acp-codex-saiens"],
    codexAcp: "/opt/codex-acp/bin/codex-acp",
    codexAccounts: [{ id: "acp-codex-saiens", displayName: "Codex · saiens", command: "codex-saiens-bb", icon: "Terminal" }],
  }));
  assert.deepEqual(warnings, []);
  assert.deepEqual(overrides, {
    enabledProviders: ["acp-codex-saiens"],
    codexAcp: "/opt/codex-acp/bin/codex-acp",
    codexAccounts: [{ id: "acp-codex-saiens", displayName: "Codex · saiens", command: "codex-saiens-bb", icon: "Terminal" }],
  });
});

test("invalid JSON, schema violations and wrong types fall back to defaults with a warning", async () => {
  for (const body of ["not json", "[]", JSON.stringify({ enabledProviders: "acp-codexl" }), JSON.stringify({ codexAccounts: [{ id: "x" }] })]) {
    const { overrides, warnings } = await withLocalConfig(body);
    assert.deepEqual(overrides, {}, `expected fallback for: ${body}`);
    assert.equal(warnings.length, 1, `expected one warning for: ${body}`);
  }
});

test("unknown keys are ignored; a valid empty config applies cleanly", async () => {
  const ignored = await withLocalConfig(JSON.stringify({ unknownKey: "x" }));
  assert.deepEqual(ignored.overrides, {});
  assert.deepEqual(ignored.warnings, []);
  const empty = await withLocalConfig("{}");
  assert.deepEqual(empty.overrides, {});
  assert.deepEqual(empty.warnings, []);
});

test("candidates resolve in order; the first existing file wins and later bad files are ignored", async () => {
  const dir = await mkdtemp(join(tmpdir(), "account-limits-candidates-"));
  const warnings: string[] = [];
  try {
    const missing = pathToFileURL(join(dir, "missing.json"));
    const good = pathToFileURL(join(dir, "good.json"));
    await writeFile(good, JSON.stringify({ codex: "good-codex" }));
    const bad = pathToFileURL(join(dir, "bad.json"));
    await writeFile(bad, "not json");
    // 好文件在前：后面的坏文件不会被碰。
    const overrides = loadLocalAccountLimitsConfig([missing, good, bad], message => warnings.push(message));
    assert.deepEqual(overrides, { codex: "good-codex" });
    assert.equal(warnings.length, 0);
    // 坏文件在前：警告后落到下一个候选。
    const fallback = loadLocalAccountLimitsConfig([bad, good], message => warnings.push(message));
    assert.deepEqual(fallback, { codex: "good-codex" });
    assert.equal(warnings.length, 1);
    // 全部缺失：静默回退默认。
    const none = loadLocalAccountLimitsConfig([missing, pathToFileURL(join(dir, "also-missing.json"))], message => warnings.push(message));
    assert.deepEqual(none, {});
    assert.equal(warnings.length, 1);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("built-in candidate list is env → XDG → plugin root", () => {
  const previousEnv = process.env.ACCOUNT_LIMITS_LOCAL_CONFIG;
  const previousXdg = process.env.XDG_CONFIG_HOME;
  try {
    process.env.ACCOUNT_LIMITS_LOCAL_CONFIG = "/tmp/from-env.json";
    process.env.XDG_CONFIG_HOME = "/tmp/xdg";
    const [env, xdg, root] = localAccountLimitsConfigCandidates();
    assert.equal(env.protocol, "file:");
    assert.ok(env.pathname.endsWith("/from-env.json"));
    assert.ok(xdg.pathname.endsWith("/tmp/xdg/bb/account-limits/local.json"));
    assert.ok(root.pathname.endsWith("account-limits.local.json"));
  } finally {
    if (previousEnv === undefined) delete process.env.ACCOUNT_LIMITS_LOCAL_CONFIG;
    else process.env.ACCOUNT_LIMITS_LOCAL_CONFIG = previousEnv;
    if (previousXdg === undefined) delete process.env.XDG_CONFIG_HOME;
    else process.env.XDG_CONFIG_HOME = previousXdg;
  }
});
