import assert from "node:assert/strict";
import { test } from "node:test";
import { promisify } from "node:util";
import { execFile } from "node:child_process";
import { withAccountLimits } from "./host.js";
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

test("provider bridge passes SDK conformance with an offline ACP agent", { timeout: 25000 }, async () => {
  const { stdout } = await promisify(execFile)(process.execPath, ["--import", "./test-runtime.mjs", "--import", "tsx", "./fixtures/conformance.mjs"], { timeout: 22000, maxBuffer: 1024 * 1024 });
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
