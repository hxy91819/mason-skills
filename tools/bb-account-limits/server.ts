import { config } from "./config.js";
import type { BbPluginApi, PluginProviderDeclaration } from "@get-bb/plugin-sdk";
import { agyProvider } from "./agy-provider.js";
import {
  accountLimitsHostContract,
  accountLimitsPanelRpcContract,
  accountLimitsPanelSnapshotSchema,
  cliproxyUsageSnapshotSchema,
  type AccountLimitsPanelReadInput,
  type AccountLimitsPanelSnapshot,
  type CliproxyUsageSnapshot,
} from "./contract.js";
import { extraProviders } from "./extra-providers.js";

export const CLIPROXY_USAGE_CACHE_MAX_AGE_MS = 30 * 60 * 1000;
export const CLIPROXY_USAGE_REFRESH_SCHEDULE_NAME = "refresh-cliproxy-usage";
export const CLIPROXY_USAGE_REFRESH_CRON = "*/30 * * * *";

type PanelProvider = AccountLimitsPanelSnapshot["machines"][number]["providers"][number];
type CachedProvider = Omit<PanelProvider, "updatedAt"> & { updatedAtMs: number };

interface PanelCacheRecord {
  fullSnapshotUpdatedAtMs: number | null;
  providers: CachedProvider[];
}

interface PanelCache {
  read(hostId: string): PanelCacheRecord | null;
  replaceAll(hostId: string, providers: CliproxyUsageSnapshot["providers"], updatedAtMs: number): void;
  update(hostId: string, providers: CliproxyUsageSnapshot["providers"], updatedAtMs: number): void;
}

interface SqliteStatement {
  all(...params: unknown[]): unknown[];
  get(...params: unknown[]): unknown;
  run(...params: unknown[]): unknown;
}

interface SqliteDatabase {
  prepare(sql: string): SqliteStatement;
  transaction(action: () => void): () => void;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function asTimestamp(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

function cachedProviders(providers: CliproxyUsageSnapshot["providers"], updatedAtMs: number): CachedProvider[] {
  return providers.map(provider => ({ ...provider, updatedAtMs }));
}

export function createInMemoryPanelCache(): PanelCache {
  const records = new Map<string, PanelCacheRecord>();
  return {
    read(hostId) {
      const record = records.get(hostId);
      if (!record) return null;
      return { fullSnapshotUpdatedAtMs: record.fullSnapshotUpdatedAtMs, providers: record.providers.map(provider => ({ ...provider })) };
    },
    replaceAll(hostId, providers, updatedAtMs) {
      records.set(hostId, { fullSnapshotUpdatedAtMs: updatedAtMs, providers: cachedProviders(providers, updatedAtMs) });
    },
    update(hostId, providers, updatedAtMs) {
      const record = records.get(hostId) ?? { fullSnapshotUpdatedAtMs: null, providers: [] };
      const byId = new Map(record.providers.map(provider => [provider.id, provider]));
      for (const provider of cachedProviders(providers, updatedAtMs)) byId.set(provider.id, provider);
      records.set(hostId, { ...record, providers: [...byId.values()] });
    },
  };
}

export function createSqlitePanelCache(database: SqliteDatabase): PanelCache {
  const readMeta = database.prepare("SELECT full_snapshot_updated_at_ms FROM cliproxy_usage_cache_hosts WHERE host_id = ?");
  const readProviders = database.prepare("SELECT provider_json, updated_at_ms FROM cliproxy_usage_cache_providers WHERE host_id = ? ORDER BY rowid");
  const deleteProviders = database.prepare("DELETE FROM cliproxy_usage_cache_providers WHERE host_id = ?");
  const writeProvider = database.prepare("INSERT INTO cliproxy_usage_cache_providers (host_id, provider_id, provider_json, updated_at_ms) VALUES (?, ?, ?, ?) ON CONFLICT(host_id, provider_id) DO UPDATE SET provider_json = excluded.provider_json, updated_at_ms = excluded.updated_at_ms");
  const writeMeta = database.prepare("INSERT INTO cliproxy_usage_cache_hosts (host_id, full_snapshot_updated_at_ms) VALUES (?, ?) ON CONFLICT(host_id) DO UPDATE SET full_snapshot_updated_at_ms = excluded.full_snapshot_updated_at_ms");

  return {
    read(hostId) {
      const meta = asRecord(readMeta.get(hostId));
      const providers = readProviders.all(hostId).flatMap(row => {
        const record = asRecord(row);
        const updatedAtMs = asTimestamp(record?.updated_at_ms);
        if (updatedAtMs === null || typeof record?.provider_json !== "string") return [];
        try {
          const parsed = cliproxyUsageSnapshotSchema.safeParse({ providers: [JSON.parse(record.provider_json)] });
          return parsed.success ? cachedProviders(parsed.data.providers, updatedAtMs) : [];
        } catch { return []; }
      });
      if (!meta && providers.length === 0) return null;
      return { fullSnapshotUpdatedAtMs: asTimestamp(meta?.full_snapshot_updated_at_ms), providers };
    },
    replaceAll(hostId, providers, updatedAtMs) {
      database.transaction(() => {
        deleteProviders.run(hostId);
        for (const provider of providers) writeProvider.run(hostId, provider.id, JSON.stringify(provider), updatedAtMs);
        writeMeta.run(hostId, updatedAtMs);
      })();
    },
    update(hostId, providers, updatedAtMs) {
      database.transaction(() => {
        for (const provider of providers) writeProvider.run(hostId, provider.id, JSON.stringify(provider), updatedAtMs);
      })();
    },
  };
}

interface PanelHost {
  id: string;
  name: string;
  status: string;
}

interface PanelSnapshotReaderDependencies {
  cache: PanelCache;
  listHosts(): Promise<readonly PanelHost[]>;
  readHost(hostId: string, providerIds?: readonly string[]): Promise<CliproxyUsageSnapshot>;
  now(): number;
}

function panelProviders(record: PanelCacheRecord): PanelProvider[] {
  return record.providers.map(({ updatedAtMs, ...provider }) => ({ ...provider, updatedAt: new Date(updatedAtMs).toISOString() }));
}

function cachedMachine(host: PanelHost, record: PanelCacheRecord, error: string | null = null) {
  return { id: host.id, displayName: host.name, status: "connected" as const, providers: panelProviders(record), error };
}

export function createPanelSnapshotReader(deps: PanelSnapshotReaderDependencies) {
  return async (input: AccountLimitsPanelReadInput): Promise<AccountLimitsPanelSnapshot> => {
    const now = deps.now();
    const machines = await Promise.all((await deps.listHosts()).map(async host => {
      if (host.status === "disconnected") {
        return { id: host.id, displayName: host.name, status: "disconnected" as const, providers: [], error: null };
      }
      const record = deps.cache.read(host.id);
      const requestedProviderIds = input.force && input.providerIds ? input.providerIds : undefined;
      const shouldReadAll = !requestedProviderIds && (input.force === true
        || !record
        || record.fullSnapshotUpdatedAtMs === null
        || now - record.fullSnapshotUpdatedAtMs >= CLIPROXY_USAGE_CACHE_MAX_AGE_MS);
      if (!shouldReadAll && !requestedProviderIds && record) return cachedMachine(host, record);
      try {
        const snapshot = await deps.readHost(host.id, requestedProviderIds);
        const updatedAtMs = deps.now();
        if (shouldReadAll) deps.cache.replaceAll(host.id, snapshot.providers, updatedAtMs);
        else deps.cache.update(host.id, snapshot.providers, updatedAtMs);
        return cachedMachine(host, deps.cache.read(host.id)!);
      } catch (error) {
        const message = error instanceof Error ? error.message : "读取此机器的 Cliproxy 额度失败。";
        return record
          ? cachedMachine(host, record, `刷新失败，正在显示缓存：${message}`)
          : { id: host.id, displayName: host.name, status: "error" as const, providers: [], error: message };
      }
    }));
    return accountLimitsPanelSnapshotSchema.parse({ machines });
  };
}

export function registerCliproxyUsageRefreshSchedule(
  background: Pick<BbPluginApi["background"], "schedule">,
  refresh: (input: AccountLimitsPanelReadInput) => unknown,
) {
  background.schedule(CLIPROXY_USAGE_REFRESH_SCHEDULE_NAME, CLIPROXY_USAGE_REFRESH_CRON, async () => {
    await refresh({ force: true });
  });
}

const agents: Array<{ id: string; displayName: string; command: string; args: string[]; env: Record<string, string>; login: string; icon: string }> = [
  { id: "acp-codexl", displayName: "CodexL", command: config.codexAcp, args: [], env: { CODEX_PATH: config.codex, INITIAL_AGENT_MODE: "agent-full-access" }, login: "codexl-bb login", icon: "Terminal" },
  // 额外 Codex 账号与 acp-codexl 同构：codex-acp 通过 CODEX_PATH 拿到账号隔离的 codex 包装 CLI。
  ...config.codexAccounts.map(account => ({
    id: account.id, displayName: account.displayName, command: config.codexAcp, args: [] as string[],
    env: { CODEX_PATH: account.command, INITIAL_AGENT_MODE: "agent-full-access" }, login: `${account.command} login`, icon: account.icon,
  })),
  { id: "acp-kiro", displayName: "Kiro", command: config.kiro, args: ["acp"], env: {}, login: "kiro-cli login", icon: "Bug" },
];

export const providers = agents.map((agent): PluginProviderDeclaration => ({
  id: agent.id,
  displayName: agent.displayName,
  family: "acp",
  icon: agent.icon,
  strings: {
    installUrl: agent.id === "acp-kiro" ? "https://kiro.dev/docs/cli/" : "https://github.com/agentclientprotocol/codex-acp",
    signInHint: `Run \`${agent.login}\` on the machine, then reload usage.`,
    expiredHint: `Session expired. Run \`${agent.login}\`, then reload usage.`,
  },
  experimental_bridgeOptions: {
    acpDialect: "generic",
    acpLaunchSpec: { displayName: agent.displayName, command: agent.command, args: agent.args, env: agent.env },
  },
  maintenance: { health: true, usage: true, installation: false },
  models: { scope: "host" },
  capabilities: {
    supportsServiceTier: true,
    supportsNativeUserQuestion: false,
    supportsManualCompaction: false,
    fork: "none",
    supportsThreadArchive: false,
    supportsThreadRename: false,
    permissionModes: ["full"],
    reasoningLevels: ["low", "medium", "high", "xhigh", "max"],
  },
  serviceTiers: [{ id: "default", label: "Default" }, { id: "fast", label: "Fast" }],
  composerActions: [],
}));

export default function accountLimitsPlugin(bb: BbPluginApi) {
  const enabled = [...providers, agyProvider, ...extraProviders].filter(p => config.enabledProviders.includes(p.id));
  for (const provider of enabled) bb.providers.register(provider);
  const host = bb.hosts.experimental_client({ contract: accountLimitsHostContract });
  const rawDatabase = bb.storage.database();
  bb.storage.migrate(rawDatabase, [
    "CREATE TABLE IF NOT EXISTS cliproxy_usage_cache_hosts (host_id TEXT PRIMARY KEY, full_snapshot_updated_at_ms INTEGER NOT NULL)",
    "CREATE TABLE IF NOT EXISTS cliproxy_usage_cache_providers (host_id TEXT NOT NULL, provider_id TEXT NOT NULL, provider_json TEXT NOT NULL, updated_at_ms INTEGER NOT NULL, PRIMARY KEY (host_id, provider_id))",
  ]);
  const database = rawDatabase as unknown as SqliteDatabase;
  const readPanelSnapshot = createPanelSnapshotReader({
    cache: createSqlitePanelCache(database),
    listHosts: () => bb.sdk.hosts.list(),
    readHost: (hostId, providerIds) => host.call("readCliproxyUsage", providerIds ? { providerIds: [...providerIds] } : {}, { hostId }),
    now: () => Date.now(),
  });
  bb.rpc.register(accountLimitsPanelRpcContract, { readCliproxyUsage: readPanelSnapshot });
  registerCliproxyUsageRefreshSchedule(bb.background, readPanelSnapshot);
  bb.cli.register({
    name: "account-limits",
    summary: "Query native provider limits and the Cliproxy account-limits panel data",
    commands: [{ name: "show", summary: "Read account limits", usage: "bb account-limits [--host <id>]" }],
    async run(argv) {
      if (argv.includes("--help")) return { exitCode: 0, stdout: "Usage: bb account-limits [--host <id>]\n" };
      if (argv.length !== 0 && !(argv.length === 2 && argv[0] === "--host")) {
        return { exitCode: 2, stderr: "Usage: bb account-limits [--host <id>]\n" };
      }
      const [usage, panel] = await Promise.all([
        bb.sdk.system.usageLimits(argv.length ? { hostId: argv[1] } : {}),
        readPanelSnapshot({}),
      ]);
      const cliproxy = argv.length === 0 ? panel : { machines: panel.machines.filter(machine => machine.id === argv[1]) };
      const native = Object.fromEntries(enabled.filter(p => p.maintenance?.usage).map(p => [p.id, usage[p.id] ?? null]));
      return { exitCode: 0, stdout: JSON.stringify({ providers: native, cliproxy }, null, 2) + "\n" };
    },
  });
}
