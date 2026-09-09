import assert from "node:assert/strict";
import { test } from "node:test";
import { CLIPROXY_USAGE_CACHE_MAX_AGE_MS, createInMemoryPanelCache, createPanelSnapshotReader, providers } from "./server.js";
import type { CliproxyUsageSnapshot } from "./contract.js";

function acpLaunchEnv(provider: typeof providers[number]) {
  const options = provider.experimental_bridgeOptions as {
    acpLaunchSpec?: { env?: Record<string, string> };
  } | null;
  return options?.acpLaunchSpec?.env;
}

test("plugin ACP providers expose full access only", () => {
  for (const provider of providers) {
    assert.deepEqual(provider.capabilities.permissionModes, ["full"]);
  }
});

test("Cliproxy quota sources do not register as executable providers", () => {
  assert.ok(providers.every(provider => !provider.id.startsWith("cliproxy-")));
});

test("Codex ACP providers start with Codex full access", () => {
  const codexProviders = providers.filter(provider => provider.id.startsWith("acp-codex"));
  assert.ok(codexProviders.length > 0);

  for (const provider of codexProviders) {
    assert.equal(acpLaunchEnv(provider)?.INITIAL_AGENT_MODE, "agent-full-access");
  }
});

function cliproxySnapshot(claudeUsedPercent: number, grokUsedPercent: number): CliproxyUsageSnapshot {
  return {
    providers: [
      { id: "cliproxy-claude", displayName: "Claude", usage: { status: "ok", planLabel: null, windows: [{ accountLabel: "Claude", label: "Weekly limit", usedPercent: claudeUsedPercent, resetsAt: null }] } },
      { id: "cliproxy-xai", displayName: "Grok", usage: { status: "ok", planLabel: null, windows: [{ accountLabel: "Grok", label: "Weekly limit", usedPercent: grokUsedPercent, resetsAt: null }] } },
    ],
  };
}

function usedPercent(provider: CliproxyUsageSnapshot["providers"][number] | undefined): number | undefined {
  return provider?.usage.status === "ok" ? provider.usage.windows[0]?.usedPercent : undefined;
}

test("额度面板在 30 分钟内复用缓存，过期才重新读取完整快照", async () => {
  let now = 1_700_000_000_000;
  const calls: Array<readonly string[] | undefined> = [];
  const reader = createPanelSnapshotReader({
    cache: createInMemoryPanelCache(),
    listHosts: async () => [{ id: "host-local", name: "本机", status: "connected" }],
    readHost: async (_hostId, providerIds) => {
      calls.push(providerIds);
      return cliproxySnapshot(calls.length, calls.length);
    },
    now: () => now,
  });

  const initial = await reader({});
  const cached = await reader({});
  now += CLIPROXY_USAGE_CACHE_MAX_AGE_MS;
  const refreshed = await reader({});

  assert.deepEqual(calls, [undefined, undefined]);
  assert.equal(usedPercent(initial.machines[0]?.providers[0]), 1);
  assert.equal(usedPercent(cached.machines[0]?.providers[0]), 1);
  assert.equal(usedPercent(refreshed.machines[0]?.providers[0]), 2);
});

test("单供应商刷新只请求该供应商，并保留其余缓存数据", async () => {
  let now = 1_700_000_000_000;
  const calls: Array<readonly string[] | undefined> = [];
  const reader = createPanelSnapshotReader({
    cache: createInMemoryPanelCache(),
    listHosts: async () => [{ id: "host-local", name: "本机", status: "connected" }],
    readHost: async (_hostId, providerIds) => {
      calls.push(providerIds);
      const snapshot = cliproxySnapshot(10, 20);
      return providerIds ? { providers: snapshot.providers.filter(provider => providerIds.includes(provider.id)).map(provider => ({
        ...provider,
        usage: provider.id === "cliproxy-claude" && provider.usage.status === "ok"
          ? { ...provider.usage, windows: [{ ...provider.usage.windows[0]!, usedPercent: 30 }] }
          : provider.usage,
      })) } : snapshot;
    },
    now: () => now,
  });

  await reader({});
  now += 60_000;
  const refreshed = await reader({ providerIds: ["cliproxy-claude"], force: true });
  const providers = new Map(refreshed.machines[0]?.providers.map(provider => [provider.id, provider]));

  assert.deepEqual(calls, [undefined, ["cliproxy-claude"]]);
  assert.equal(providers.size, 2);
  assert.equal(usedPercent(providers.get("cliproxy-claude")), 30);
  assert.equal(usedPercent(providers.get("cliproxy-xai")), 20);
  assert.equal(providers.get("cliproxy-claude")?.updatedAt, new Date(now).toISOString());
  assert.equal(providers.get("cliproxy-xai")?.updatedAt, new Date(now - 60_000).toISOString());
});
