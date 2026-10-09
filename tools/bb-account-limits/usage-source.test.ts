import assert from "node:assert/strict";
import { test } from "node:test";
import { createCliproxyUsageSource, type CliproxyUsageSourceDeps } from "./usage-source.js";
import { usageMeasurementSchema, usageResourceListSchema } from "./usage-source-contract.js";
import type { CliproxyUsageSnapshot } from "./contract.js";

type SnapshotProvider = CliproxyUsageSnapshot["providers"][number];
type CachedProvider = SnapshotProvider & { updatedAtMs: number };

function provider(accounts: SnapshotProvider["accounts"]): SnapshotProvider {
  return {
    id: "cliproxy-claude",
    displayName: "Claude",
    usage: { status: "ok", planLabel: "Claude · Cliproxy · 2/2 accounts", windows: [] },
    accounts,
  };
}

const twoAccounts: SnapshotProvider["accounts"] = [
  { key: "key-work", label: "Claude 工作", weight: 2, usage: { status: "ok", planLabel: null, windows: [
    { label: "5-hour limit", usedPercent: 20, resetsAt: "2026-10-05T08:00:00Z" },
    { label: "Weekly limit", usedPercent: 40, resetsAt: null },
  ] } },
  { key: "key-personal", label: "Claude 个人", weight: 1, usage: { status: "ok", planLabel: null, windows: [
    { label: "5-hour limit", usedPercent: 80, resetsAt: "2026-10-05T06:00:00Z" },
  ] } },
];

function makeSource(options: {
  cached?: CachedProvider[];
  hosts?: Array<{ id: string; status: string }>;
  enabled?: string[];
  readHost?: CliproxyUsageSourceDeps["readHost"];
  now?: number;
}) {
  const store = new Map<string, { providers: CachedProvider[] }>();
  store.set("host-local", { providers: (options.cached ?? []).map(entry => ({ ...entry })) });
  const calls: Array<{ hostId: string; providerIds: readonly string[] }> = [];
  const deps: CliproxyUsageSourceDeps = {
    readCache: hostId => store.get(hostId) ?? null,
    updateCache: (hostId, providers, updatedAtMs) => {
      const record = store.get(hostId) ?? { providers: [] };
      const byId = new Map(record.providers.map(entry => [entry.id, entry]));
      for (const entry of providers) byId.set(entry.id, { ...entry, updatedAtMs });
      record.providers = [...byId.values()];
      store.set(hostId, record);
    },
    listHosts: async () => options.hosts ?? [{ id: "host-local", status: "connected" }],
    readHost: async (hostId, providerIds) => {
      calls.push({ hostId, providerIds });
      return options.readHost ? options.readHost(hostId, providerIds) : { providers: [] };
    },
    enabledProviderIds: () => options.enabled ?? ["cliproxy-claude"],
    now: () => options.now ?? 1_700_000_000_000,
  };
  return { source: createCliproxyUsageSource(deps), calls, store };
}

const list = (source: ReturnType<typeof createCliproxyUsageSource>) =>
  source["provider-usage.v1.listResources"]();
const get = (source: ReturnType<typeof createCliproxyUsageSource>, resourceId: string, refresh: boolean) =>
  source["provider-usage.v1.getResource"]({ resourceId, refresh });

test("listResources 只读缓存并输出池与账号资源，顺序即显示顺序", async () => {
  let hostReads = 0;
  const { source } = makeSource({
    cached: [{ ...provider(twoAccounts), updatedAtMs: 123 }],
    readHost: async () => { hostReads += 1; return { providers: [] }; },
  });
  const result = await list(source);
  const parsed = usageResourceListSchema.safeParse(result);
  assert.ok(parsed.success, JSON.stringify(parsed.error?.issues));
  assert.equal(hostReads, 0);
  assert.equal(result.label, "Cliproxy");
  assert.deepEqual(result.resources, [
    { accountKey: null, id: "pool:claude", providerId: "claude-code", label: "池 · Claude", scope: { kind: "shared" } },
    { accountKey: null, id: "account:claude:key-work", providerId: "claude-code", label: "Claude 工作", scope: { kind: "shared" } },
    { accountKey: null, id: "account:claude:key-personal", providerId: "claude-code", label: "Claude 个人", scope: { kind: "shared" } },
  ]);
});

test("providerId 映射复用 codex/claude-code，其余保留 cliproxy- 前缀", async () => {
  const { source } = makeSource({
    enabled: ["cliproxy-codex", "cliproxy-claude", "cliproxy-xai"],
    cached: [
      { ...provider(twoAccounts), id: "cliproxy-codex", displayName: "Codex", updatedAtMs: 1 },
      { ...provider(twoAccounts), updatedAtMs: 1 },
      { ...provider(twoAccounts), id: "cliproxy-xai", displayName: "Grok", updatedAtMs: 1 },
    ],
  });
  const result = await list(source);
  assert.deepEqual(result.resources.map(resource => [resource.id, resource.providerId]), [
    ["pool:codex", "codex"], ["account:codex:key-work", "codex"], ["account:codex:key-personal", "codex"],
    ["pool:claude", "claude-code"], ["account:claude:key-work", "claude-code"], ["account:claude:key-personal", "claude-code"],
    ["pool:xai", "cliproxy-xai"], ["account:xai:key-work", "cliproxy-xai"], ["account:xai:key-personal", "cliproxy-xai"],
  ]);
});

test("未启用的供应商不产生资源", async () => {
  const { source } = makeSource({ enabled: [], cached: [{ ...provider(twoAccounts), updatedAtMs: 1 }] });
  const result = await list(source);
  assert.equal(result.label, "Cliproxy");
  assert.deepEqual(result.resources, []);
});

test("getResource refresh=false 返回缓存且不触发 host 查询", async () => {
  let hostReads = 0;
  const { source } = makeSource({
    cached: [{ ...provider(twoAccounts), updatedAtMs: 999 }],
    readHost: async () => { hostReads += 1; return { providers: [] }; },
  });
  const measurement = await get(source, "account:claude:key-work", false);
  assert.equal(hostReads, 0);
  const parsed = usageMeasurementSchema.safeParse(measurement);
  assert.ok(parsed.success, JSON.stringify(parsed.error?.issues));
  assert.equal(measurement.observedAt, 999);
  assert.equal(measurement.usage.status, "ok");
  if (measurement.usage.status === "ok") {
    assert.deepEqual(measurement.usage.windows.map(window => [window.id, window.kind, window.label]), [
      ["5h", "five-hour", "5h"],
      ["7d", "weekly", "7d"],
    ]);
  }
});

test("池资源聚合同供应商账号窗口并给出可读账号数", async () => {
  const { source } = makeSource({ cached: [{ ...provider(twoAccounts), updatedAtMs: 42 }] });
  const measurement = await get(source, "pool:claude", false);
  const parsed = usageMeasurementSchema.safeParse(measurement);
  assert.ok(parsed.success, JSON.stringify(parsed.error?.issues));
  assert.equal(measurement.observedAt, 42);
  assert.equal(measurement.usage.status, "ok");
  if (measurement.usage.status !== "ok") return;
  assert.equal(measurement.usage.planLabel, "2/2 账号");
  const fiveHour = measurement.usage.windows.find(window => window.id === "5h");
  const weekly = measurement.usage.windows.find(window => window.id === "7d");
  // (2×20 + 1×80) / 3 = 40；最早重置取 06:00。
  assert.deepEqual([fiveHour?.usedPercent, fiveHour?.resetsAt, fiveHour?.kind], [40, "2026-10-05T06:00:00.000Z", "five-hour"]);
  assert.deepEqual([weekly?.usedPercent, weekly?.kind], [40, "weekly"]);
});

test("没有缓存时 getResource 只读取该资源所属供应商并回写缓存", async () => {
  const { source, calls, store } = makeSource({
    readHost: async (_hostId, providerIds) => ({
      providers: providerIds.includes("cliproxy-claude") ? [provider(twoAccounts)] : [],
    }),
  });
  const measurement = await get(source, "pool:claude", false);
  assert.deepEqual(calls, [{ hostId: "host-local", providerIds: ["cliproxy-claude"] }]);
  assert.equal(measurement.usage.status, "ok");
  assert.equal(measurement.observedAt, 1_700_000_000_000);
  assert.equal(store.get("host-local")?.providers.length, 1);

  const cached = await get(source, "account:claude:key-work", false);
  assert.equal(cached.usage.status, "ok");
  assert.equal(calls.length, 1);
});

test("refresh=true 强制重读该供应商并覆盖缓存", async () => {
  const { source, calls } = makeSource({
    cached: [{ ...provider(twoAccounts), updatedAtMs: 1 }],
    readHost: async (_hostId, providerIds) => ({
      providers: providerIds.includes("cliproxy-claude")
        ? [provider([{ key: "key-work", label: "Claude 工作", weight: 1, usage: { status: "ok", planLabel: null, windows: [{ label: "Weekly limit", usedPercent: 66, resetsAt: null }] } }])]
        : [],
    }),
  });
  const measurement = await get(source, "account:claude:key-work", true);
  assert.deepEqual(calls, [{ hostId: "host-local", providerIds: ["cliproxy-claude"] }]);
  assert.equal(measurement.observedAt, 1_700_000_000_000);
  assert.equal(measurement.usage.status, "ok");
  if (measurement.usage.status === "ok") assert.equal(measurement.usage.windows[0]?.usedPercent, 66);
});

test("资源不存在或格式非法时报错，不返回零用量", async () => {
  const { source } = makeSource({ cached: [{ ...provider(twoAccounts), updatedAtMs: 1 }] });
  await assert.rejects(() => get(source, "account:claude:missing", false), /no longer exists/);
  await assert.rejects(() => get(source, "pool:unknown", false), /no longer exists/);
  await assert.rejects(() => get(source, "garbage", false), /no longer exists/);
  await assert.rejects(() => get(source, "account:", false), /no longer exists/);
});

test("账号失败以 usage 状态表达且 observedAt 为 null", async () => {
  const { source } = makeSource({
    cached: [{ ...provider([{ key: "key-bad", label: "坏账号", weight: 1, usage: { status: "error", message: "upstream 503" } }]), updatedAtMs: 7 }],
  });
  const measurement = await get(source, "account:claude:key-bad", false);
  const parsed = usageMeasurementSchema.safeParse(measurement);
  assert.ok(parsed.success, JSON.stringify(parsed.error?.issues));
  assert.equal(measurement.observedAt, null);
  assert.equal(measurement.usage.status, "error");
});

test("池内全部账号失败时池资源返回 error 而非 0", async () => {
  const { source } = makeSource({
    cached: [{ ...provider([{ key: "k1", label: "a", weight: 1, usage: { status: "error", message: "x" } }]), updatedAtMs: 7 }],
  });
  const measurement = await get(source, "pool:claude", false);
  assert.equal(measurement.usage.status, "error");
  assert.equal(measurement.observedAt, null);
});
