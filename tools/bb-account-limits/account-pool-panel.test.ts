import assert from "node:assert/strict";
import { test } from "node:test";
import { createAccountLimitsReader, createAccountPoolPanelReader } from "./account-pool-panel.js";
import { aggregateCliproxyPool } from "./pool.js";
import type { UsageMeasurement, UsageResourceList } from "./usage-source-contract.js";

const observedAt = Date.parse("2026-10-05T10:00:00Z");
const resource = (id: string, providerId = "codex"): UsageResourceList["resources"][number] => ({
  id, providerId, label: id, scope: { kind: "shared" }, accountKey: null,
});
function measurement(percent: number, at: number | null = observedAt): UsageMeasurement {
  return { observedAt: at, accountKey: null, usage: {
    status: "ok", plan: null, accountEmail: null, planLabel: "Pro",
    windows: [{ id: "primary", kind: "five-hour", label: "Five-hour limit", usedPercent: percent,
      resetsAt: "2026-10-06T10:00:00Z", model: null, cost: null }],
  } };
}

test("Account Pooler 账号进入独立来源，按相同窗口聚合并保留真实测量时间", async () => {
  const reader = createAccountPoolPanelReader({
    listResources: async () => ({ resources: [resource("a"), resource("b")] }),
    getResource: async id => measurement(id === "a" ? 20 : 60, id === "a" ? observedAt : observedAt + 60_000),
  });
  const { machines } = await reader({});
  assert.equal(machines[0]?.source, "account-pool");
  const provider = machines[0]!.providers[0]!;
  assert.equal(provider.id, "account-pool:codex");
  assert.equal(provider.displayName, "Codex");
  assert.equal(provider.updatedAt, new Date(observedAt).toISOString());
  assert.equal(provider.accounts[1]?.updatedAt, new Date(observedAt + 60_000).toISOString());
  const pool = aggregateCliproxyPool(provider.accounts);
  assert.equal(pool.status, "ok");
  if (pool.status !== "ok") return;
  assert.equal(pool.windows[0]?.usedPercent, 40);
  assert.equal(pool.windows[0]?.label, "5h");
  assert.equal(pool.windows[0]?.accounts, 2);
});

test("账号失败保留错误行，健康账号仍显示且失败账号不进入池均值", async () => {
  const reader = createAccountPoolPanelReader({
    listResources: async () => ({ resources: [resource("good"), resource("bad"), resource("expired")] }),
    getResource: async id => {
      if (id === "bad") throw new Error("sensitive upstream diagnostics");
      if (id === "expired") return { observedAt: null, accountKey: null,
        usage: { status: "expired", plan: null, accountEmail: null, planLabel: null } };
      return measurement(25);
    },
  });
  const provider = (await reader({})).machines[0]!.providers[0]!;
  assert.equal(provider.accounts.length, 3);
  assert.equal(provider.accounts[1]?.usage.status, "error");
  assert.equal(provider.accounts[2]?.usage.status, "expired");
  assert.ok(!JSON.stringify(provider).includes("sensitive"));
  const pool = aggregateCliproxyPool(provider.accounts);
  assert.equal(pool.status, "ok");
  if (pool.status !== "ok") return;
  assert.equal(pool.windows[0]?.usedPercent, 25);
  assert.equal(pool.totalAccounts, 3);
  assert.equal(pool.windows[0]?.accounts, 1);
});

test("单供应商强制刷新不查询其他供应商，重新列举后移除消失的账号与供应商", async () => {
  let resources = [resource("codex"), resource("claude", "claude-code")];
  const calls: unknown[] = [];
  const reader = createAccountPoolPanelReader({
    listResources: async () => ({ resources }),
    getResource: async (id, refresh) => { calls.push([id, refresh]); return measurement(refresh ? 80 : 20); },
  });
  await reader({});
  calls.length = 0;
  const refreshed = await reader({ providerIds: ["account-pool:codex"], force: true });
  assert.deepEqual(calls, [["codex", true]]);
  assert.equal(refreshed.machines[0]!.providers[1]!.accounts[0]!.usage.status, "ok");
  resources = [resource("codex")];
  const removed = await reader({ providerIds: ["account-pool:codex"], force: true });
  assert.equal(removed.machines[0]!.providers.length, 1);
  assert.equal(removed.machines[0]!.providers[0]!.accounts.length, 1);
});

test("相同显示名的不同窗口或模型不在池视图混算，百分比超额仍显示耗尽", async () => {
  const m = measurement(120);
  if (m.usage.status !== "ok") throw new Error("fixture");
  m.usage.windows.push({ ...m.usage.windows[0]!, id: "family", model: "opus", usedPercent: 10 });
  const reader = createAccountPoolPanelReader({
    listResources: async () => ({ resources: [resource("a")] }), getResource: async () => m,
  });
  const pool = aggregateCliproxyPool((await reader({})).machines[0]!.providers[0]!.accounts);
  assert.equal(pool.status, "ok");
  if (pool.status !== "ok") return;
  assert.equal(pool.windows.length, 2);
  assert.equal(pool.windows[0]?.exhausted, 1);
  assert.equal(pool.windows[1]?.usedPercent, 10);
  assert.match(pool.windows[1]!.label, /opus/);
});

test("缺测量时间不伪造刚刚更新，空来源与全失败池都有明确状态", async () => {
  let resources = [resource("a")];
  let fail = false;
  const reader = createAccountPoolPanelReader({
    listResources: async () => ({ resources }),
    getResource: async () => fail
      ? { observedAt: null, accountKey: null, usage: { status: "error", plan: null, accountEmail: null, planLabel: null, message: "No quota" } }
      : measurement(25, null),
  });
  assert.equal((await reader({})).machines[0]!.providers[0]!.updatedAt, null);
  fail = true;
  const failed = (await reader({})).machines[0]!.providers[0]!;
  assert.equal(failed.usage.status, "error");
  assert.equal(aggregateCliproxyPool(failed.accounts).status, "error");
  resources = [];
  assert.deepEqual((await reader({})).machines[0]!.providers, []);
});

test("来源不可用时保留有提示的旧测量，首次不可用时返回来源错误", async () => {
  let available = false;
  const reader = createAccountPoolPanelReader({
    listResources: async () => {
      if (!available) throw new Error("unavailable");
      return { resources: [resource("a")] };
    },
    getResource: async () => measurement(25),
  });
  assert.equal((await reader({})).machines[0]?.status, "error");
  available = true;
  await reader({});
  available = false;
  const stale = (await reader({})).machines[0]!;
  assert.equal(stale.status, "connected");
  assert.match(stale.error!, /上次/);
  assert.equal(stale.providers[0]!.updatedAt, new Date(observedAt).toISOString());
});

test("统一读取隔离来源故障，定向刷新只调用指定来源", async () => {
  const calls: string[] = [];
  const reader = createAccountLimitsReader(
    async () => { calls.push("cliproxy"); throw new Error("unavailable"); },
    async () => { calls.push("pool"); return { machines: [{ id: "source:account-pool", source: "account-pool", displayName: "Account Pooler", status: "connected", providers: [], error: null }] }; },
  );
  const initial = await reader({});
  assert.equal(initial.machines[0]?.status, "error");
  assert.equal(initial.machines[1]?.status, "connected");
  calls.length = 0;
  const refreshed = await reader({ source: "account-pool", force: true, providerIds: ["account-pool:codex"] });
  assert.deepEqual(calls, ["pool"]);
  assert.equal(refreshed.machines.length, 1);
});
