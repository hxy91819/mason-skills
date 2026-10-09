import assert from "node:assert/strict";
import { test } from "node:test";
import { promisify } from "node:util";
import { execFile } from "node:child_process";
import { readCliproxyUsageSnapshot, withAccountLimits } from "./host.js";
import { usageError } from "./usage.js";

test("usage replies use BB's protocol; concurrent queries share work, other methods pass through", async () => {
  const forwarded: string[] = [];
  const output: any[] = [];
  let count = 0;
  const bridge = withAccountLimits({ experimental_apiVersion: 1, handleLine: line => { forwarded.push(line); } }, async () => {
    count++;
    return usageError("fixture");
  }, line => output.push(JSON.parse(line)));
  const send = (id: number, method: string, params: unknown) => bridge.handleLine(JSON.stringify({ jsonrpc: "2.0", id, method, params }));
  send(1, "provider/usage", { providerId: "acp-kiro" });
  send(2, "provider/usage", { providerId: "acp-kiro" });
  send(3, "provider/usage", {});
  send(4, "provider/usage", { providerId: "unknown" });
  send(5, "thread/resume", { providerThreadId: "preserved" });
  send(6, "provider/usage", { providerId: "acp-agy" });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(count, 2);
  assert.equal(output.find(m => m.id === 3).error.code, -32602);
  assert.deepEqual(output.find(m => m.id === 4).result, { supported: false });
  for (const id of [1, 2, 6]) assert.deepEqual(output.find(m => m.id === id).result, usageError("fixture"));
  assert.equal(JSON.parse(forwarded[0]).params.providerThreadId, "preserved");
});

test("model discovery remains delegated after Cliproxy moves to the panel", () => {
  const forwarded: string[] = [];
  const bridge = withAccountLimits({ experimental_apiVersion: 1, handleLine: line => forwarded.push(line) }, async () => usageError("unused"));
  bridge.handleLine(JSON.stringify({
    jsonrpc: "2.0",
    id: 1,
    method: "model/list",
    params: { providerId: "acp-codexl" },
  }));
  assert.deepEqual(forwarded, [JSON.stringify({
    jsonrpc: "2.0",
    id: 1,
    method: "model/list",
    params: { providerId: "acp-codexl" },
  })]);
});

test("Cliproxy snapshot accepts an empty enabled group set", async () => {
  const snapshot = await readCliproxyUsageSnapshot(new Map(), { managementKey: "test" });
  assert.deepEqual(snapshot, { providers: [] });
});

test("Cliproxy snapshot keeps failed accounts alongside healthy ones", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    if (url.endsWith("/auth-files")) return new Response(JSON.stringify({ files: [
      { provider: "claude", auth_index: "auth-1" },
      { provider: "claude", auth_index: "auth-2" },
    ] }), { status: 200 });
    const body = JSON.parse(String(init?.body));
    if (body.auth_index === "auth-2") return new Response(JSON.stringify({ status_code: 503, body: "{}" }), { status: 200 });
    return new Response(JSON.stringify({ status_code: 200, body: JSON.stringify({ limits: [
      { kind: "weekly_all", percent: 25, resets_at: "2026-09-12T10:00:00Z" },
    ] }) }), { status: 200 });
  };
  try {
    const groups = new Map([["claude", [
      { provider: "claude", authIndex: "auth-1", label: "账号 1" },
      { provider: "claude", authIndex: "auth-2", label: "账号 2" },
    ]]]);
    const snapshot = await readCliproxyUsageSnapshot(groups, { managementKey: "test" });
    assert.equal(snapshot.providers.length, 1);
    const provider = snapshot.providers[0]!;
    assert.equal(provider.accounts.length, 2);
    assert.equal(provider.accounts[0]?.usage.status, "ok");
    assert.equal(provider.accounts[1]?.usage.status, "error");
    assert.notEqual(provider.accounts[0]?.key, provider.accounts[1]?.key);
    assert.equal(provider.accounts[0]?.weight, 1);
    // 供应商级压平窗口只保留成功账号，失败账号不丢。
    assert.equal(provider.usage.status, "ok");
    if (provider.usage.status === "ok") {
      assert.equal(provider.usage.windows.length, 1);
      assert.equal(provider.usage.windows[0]?.accountLabel, "账号 1");
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("provider bridge passes SDK conformance with an offline ACP agent", { timeout: 25000 }, async () => {
  const { stdout } = await promisify(execFile)(process.execPath, ["--import", "tsx", "./fixtures/conformance.mjs"], { timeout: 22000, maxBuffer: 1024 * 1024 });
  const report = JSON.parse(stdout);
  assert.equal(report.passed, true, JSON.stringify(report.results.filter((r: any) => r.status !== "pass")));
});

test("bridge shutdown waits for quota subprocess cleanup before exiting", async () => {
  const events: string[] = [];
  const bridge = withAccountLimits({ experimental_apiVersion: 1, handleLine() {}, onClose() { events.push("closed"); } }, async (_id, signal) => {
    await new Promise<void>(resolve => signal.addEventListener("abort", () => {
      setImmediate(() => { events.push("cleaned"); resolve(); });
    }, { once: true }));
    return usageError("cancelled");
  }, () => {});
  bridge.handleLine(JSON.stringify({ jsonrpc: "2.0", id: 1, method: "provider/usage", params: { providerId: "acp-codexl" } }));
  await new Promise(resolve => setImmediate(resolve));
  bridge.onClose?.();
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(events, ["cleaned", "closed"]);
});
