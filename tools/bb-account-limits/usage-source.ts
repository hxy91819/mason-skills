import { cliproxyProviderDisplayName, cliproxyProviderId } from "./config.js";
import { aggregateCliproxyPool, normalizeCliproxyWindow, type CliproxyWindowIdentity, type PoolWindow } from "./pool.js";
import type { CliproxyAccountUsageEntry, CliproxyUsageSnapshot } from "./contract.js";
import {
  usageFetchMethod,
  usageListMethod,
  type UsageMeasurement,
  type UsageResourceList,
} from "./usage-source-contract.js";

type SnapshotProviders = CliproxyUsageSnapshot["providers"];
type SnapshotProvider = SnapshotProviders[number];
type CachedProvider = SnapshotProvider & { updatedAtMs: number };
type SourceUsage = UsageMeasurement["usage"];
type SourceWindow = Extract<SourceUsage, { status: "ok" }>["windows"][number];

export interface CliproxyUsageSourceDeps {
  readCache(hostId: string): { providers: CachedProvider[] } | null;
  updateCache(hostId: string, providers: SnapshotProviders, updatedAtMs: number): void;
  listHosts(): Promise<readonly { id: string; status: string }[]>;
  readHost(hostId: string, providerIds: readonly string[]): Promise<CliproxyUsageSnapshot>;
  enabledProviderIds(): readonly string[];
  now(): number;
}

function sourceProviderId(provider: string): string {
  // 复用官方图标：codex / claude-code 是 BB 内置 provider；其余保留 cliproxy- 前缀（默认 Bot 图标）。
  if (provider === "codex") return "codex";
  if (provider === "claude") return "claude-code";
  return cliproxyProviderId(provider);
}

function parseResourceId(resourceId: string): { kind: "pool" | "account"; provider: string; accountKey: string | null } | null {
  if (resourceId.startsWith("pool:")) {
    const provider = resourceId.slice(5);
    return provider ? { kind: "pool", provider, accountKey: null } : null;
  }
  if (!resourceId.startsWith("account:")) return null;
  const rest = resourceId.slice(8);
  const sep = rest.indexOf(":");
  if (sep <= 0 || sep === rest.length - 1) return null;
  return { kind: "account", provider: rest.slice(0, sep), accountKey: rest.slice(sep + 1) };
}

function sourceWindow(identity: CliproxyWindowIdentity, usedPercent: number, resetsAt: string | null): SourceWindow {
  return { kind: identity.kind, id: identity.id, label: identity.label, usedPercent, resetsAt, model: null, cost: null };
}

function uniqueWindows(windows: readonly SourceWindow[]): SourceWindow[] {
  const seen = new Map<string, number>();
  return windows.map(window => {
    const count = seen.get(window.id) ?? 0;
    seen.set(window.id, count + 1);
    return count === 0 ? window : { ...window, id: `${window.id}#${count + 1}` };
  });
}

function accountWindows(usage: Extract<CliproxyAccountUsageEntry["usage"], { status: "ok" }>): SourceWindow[] {
  return uniqueWindows(usage.windows.map(window => sourceWindow(normalizeCliproxyWindow(window.label), window.usedPercent, window.resetsAt)));
}

function poolWindows(windows: readonly PoolWindow[]): SourceWindow[] {
  return uniqueWindows(windows.map(window => sourceWindow(window, window.usedPercent, window.resetsAt)));
}

function accountSourceUsage(usage: CliproxyAccountUsageEntry["usage"]): SourceUsage {
  const fields = { plan: null, accountEmail: null, planLabel: null };
  switch (usage.status) {
    case "ok": return { status: "ok", ...fields, planLabel: usage.planLabel, windows: accountWindows(usage) };
    case "error": return { status: "error", ...fields, message: usage.message };
    default: return { status: usage.status, ...fields };
  }
}

/**
 * 官方 Provider Usage 卡片的 Cliproxy 来源：每供应商一个池资源 + 各账号资源。
 * listResources 只读本地 SQLite 缓存（面板/定时刷新写入），不触发 host 查询；
 * getResource 只刷新该资源所属供应商并回写同一份缓存。
 */
export function createCliproxyUsageSource(deps: CliproxyUsageSourceDeps) {
  async function cachedProviders(): Promise<CachedProvider[]> {
    const enabled = new Set(deps.enabledProviderIds());
    const seen = new Set<string>();
    const providers: CachedProvider[] = [];
    for (const host of await deps.listHosts()) {
      for (const provider of deps.readCache(host.id)?.providers ?? []) {
        if (!enabled.has(provider.id) || seen.has(provider.id)) continue;
        seen.add(provider.id);
        providers.push(provider);
      }
    }
    return providers;
  }

  function findCached(hosts: readonly { id: string; status: string }[], providerId: string): { hostId: string; provider: CachedProvider } | null {
    for (const host of hosts) {
      const provider = deps.readCache(host.id)?.providers.find(entry => entry.id === providerId);
      if (provider) return { hostId: host.id, provider };
    }
    return null;
  }

  return {
    async [usageListMethod](): Promise<UsageResourceList> {
      const resources: UsageResourceList["resources"] = [];
      for (const provider of await cachedProviders()) {
        const raw = provider.id.replace(/^cliproxy-/u, "");
        const providerId = sourceProviderId(raw);
        resources.push({
          accountKey: null, id: `pool:${raw}`, providerId,
          label: `池 · ${cliproxyProviderDisplayName(raw)}`,
          scope: { kind: "shared" },
        });
        for (const account of provider.accounts) {
          resources.push({
            accountKey: null, id: `account:${raw}:${account.key}`, providerId,
            label: account.label,
            scope: { kind: "shared" },
          });
        }
      }
      return { label: "Cliproxy", resources };
    },

    async [usageFetchMethod]({ resourceId, refresh }: { resourceId: string; refresh: boolean }): Promise<UsageMeasurement> {
      const parsed = parseResourceId(resourceId);
      if (!parsed) throw new Error("Usage resource no longer exists.");
      const providerId = cliproxyProviderId(parsed.provider);
      const hosts = await deps.listHosts();
      const cached = findCached(hosts, providerId);
      let provider: SnapshotProvider | null = cached?.provider ?? null;
      let observedAtMs = cached?.provider.updatedAtMs ?? null;
      if (refresh || provider === null) {
        const hostId = cached && hosts.some(host => host.id === cached.hostId && host.status === "connected")
          ? cached.hostId
          : hosts.find(host => host.status === "connected")?.id;
        if (!hostId) throw new Error("No connected host can refresh this Cliproxy resource.");
        const snapshot = await deps.readHost(hostId, [providerId]);
        const updatedAtMs = deps.now();
        deps.updateCache(hostId, snapshot.providers, updatedAtMs);
        const refreshed = snapshot.providers.find(entry => entry.id === providerId);
        if (!refreshed) throw new Error("Usage resource no longer exists.");
        provider = refreshed;
        observedAtMs = updatedAtMs;
      }
      const accountFields = { plan: null, accountEmail: null, planLabel: null };
      if (parsed.kind === "pool") {
        const pool = aggregateCliproxyPool(provider.accounts);
        if (pool.status !== "ok") {
          return { accountKey: null, observedAt: null, usage: { status: "error", ...accountFields, message: pool.message } };
        }
        return {
          accountKey: null,
          observedAt: observedAtMs,
          usage: {
            status: "ok",
            ...accountFields,
            planLabel: `${pool.okAccounts}/${pool.totalAccounts} 账号`,
            windows: poolWindows(pool.windows),
          },
        };
      }
      const account = provider.accounts.find(entry => entry.key === parsed.accountKey);
      if (!account) throw new Error("Usage resource no longer exists.");
      const usage = accountSourceUsage(account.usage);
      return { accountKey: null, observedAt: usage.status === "ok" ? observedAtMs : null, usage };
    },
  };
}
