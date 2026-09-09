import {
  activeCliproxyAccountsByProvider,
  cliproxyProviderDisplayName,
  cliproxyProviderId,
  config,
} from "./config.js";
import { experimental_acpProviderBridge } from "@get-bb/plugin-sdk/provider-bridge/acp";
import { experimental_defineHostEntry } from "@get-bb/plugin-sdk/host";
import { bridgeRequestEnvelopeSchema, createBridgeIo, experimental_defineProviderBridge, providerMaintenanceParamsSchema, type ProviderBridgeEntry, type ProviderUsageResult } from "@get-bb/plugin-sdk/provider-bridge";
import { accountLimitsHostContract, cliproxyUsageSnapshotSchema, type CliproxyUsageSnapshot } from "./contract.js";
import { readAgyUsage, readCliproxyManagementKey, readCliproxyProviderUsage, readCodexUsage, readKiroUsage, usageError, type CliproxyUsageAccount, type CliproxyUsageOptions } from "./usage.js";

// usage 查询支持的本插件 provider ID：三个原生入口 + config.codexAccounts 里的额外 Codex 账号。
const usageProviderIds = new Set([
  "acp-codexl", "acp-kiro", "acp-agy",
  ...config.codexAccounts.map(account => account.id),
]);

export async function resolveUsageReader(id: string, signal: AbortSignal): Promise<ProviderUsageResult> {
  const account = config.codexAccounts.find(entry => entry.id === id);
  if (account) return readCodexUsage(account.command, { signal });
  return id === "acp-codexl" ? readCodexUsage(undefined, { signal })
    : id === "acp-agy" ? readAgyUsage(undefined, { signal })
    : readKiroUsage(undefined, { signal });
}

export function withAccountLimits(
  delegate: ProviderBridgeEntry,
  read: (id: string, signal: AbortSignal) => Promise<ProviderUsageResult>,
  write?: (line: string) => void,
): ProviderBridgeEntry {
  const io = createBridgeIo({ write });
  const controller = new AbortController();
  const pending = new Map<string, Promise<ProviderUsageResult>>();
  let closing = false;
  const close = (handler = delegate.onClose) => {
    if (closing) return;
    closing = true;
    controller.abort();
    // ACP bridge 关闭时会退出进程，先等待额度查询清理其子进程。
    void Promise.allSettled([...pending.values()]).then(() => handler?.());
  };
  return experimental_defineProviderBridge({
    ...delegate,
    handleLine(line) {
      let raw;
      try { raw = JSON.parse(line); } catch { delegate.handleLine(line); return; }
      if (raw?.method !== "provider/usage") { delegate.handleLine(line); return; }
      const request = bridgeRequestEnvelopeSchema.safeParse(raw);
      if (!request.success) { delegate.handleLine(line); return; }
      const params = providerMaintenanceParamsSchema.safeParse(request.data.params);
      if (!params.success) { io.sendError(request.data.id, -32602, "Invalid provider usage parameters."); return; }
      const id = params.data.providerId;
      if (!usageProviderIds.has(id)) { io.sendResult(request.data.id, { supported: false }); return; }
      let query = pending.get(id);
      if (!query) {
        query = Promise.resolve().then(() => read(id, controller.signal)).catch(() => usageError("Account limits query failed."));
        pending.set(id, query);
        void query.finally(() => pending.delete(id));
      }
      void query.then(result => io.sendResult(request.data.id, result));
    },
    onClose() { close(); },
    onSigterm() { close(delegate.onSigterm ?? delegate.onClose); },
    onSigint() { close(delegate.onSigint ?? delegate.onClose); },
  });
}

export const experimental_providerBridge = withAccountLimits(experimental_acpProviderBridge, (id, signal) =>
  resolveUsageReader(id, signal));

function enabledCliproxyGroups(): Map<string, CliproxyUsageAccount[]> {
  return new Map([...activeCliproxyAccountsByProvider(config.cliproxy.accounts)]
    .filter(([provider]) => config.enabledProviders.includes(cliproxyProviderId(provider))));
}

function compactCliproxyUsage(result: ProviderUsageResult): CliproxyUsageSnapshot["providers"][number]["usage"] {
  if (!result.supported) return { status: "error", message: "Cliproxy quota querying is not supported on this machine." };
  switch (result.usage.status) {
    case "ok":
      return {
        status: "ok",
        planLabel: result.usage.planLabel,
        windows: result.usage.windows.map(window => ({
          label: window.label,
          usedPercent: Math.min(100, Math.max(0, window.usedPercent)),
          resetsAt: window.resetsAt,
        })),
      };
    case "error": return { status: "error", message: result.usage.message };
    default: return { status: result.usage.status };
  }
}

export async function readCliproxyUsageSnapshot(
  groups: ReadonlyMap<string, readonly CliproxyUsageAccount[]> = enabledCliproxyGroups(),
  options: Partial<CliproxyUsageOptions> = {},
): Promise<CliproxyUsageSnapshot> {
  const managementKey = options.managementKey ?? await readCliproxyManagementKey(config.cliproxy);
  const query: CliproxyUsageOptions = {
    managementBaseUrl: options.managementBaseUrl ?? config.cliproxy.managementBaseUrl,
    managementKey,
    timeoutMs: options.timeoutMs,
    signal: options.signal,
  };
  const providers = await Promise.all([...groups].map(async ([provider, accounts]) => ({
    id: cliproxyProviderId(provider),
    displayName: cliproxyProviderDisplayName(provider),
    usage: compactCliproxyUsage(await readCliproxyProviderUsage(accounts, query)),
  })));
  return cliproxyUsageSnapshotSchema.parse({ providers });
}

export default experimental_defineHostEntry({
  contract: accountLimitsHostContract,
  handlers: {
    readCliproxyUsage: (_input, context) => readCliproxyUsageSnapshot(undefined, { signal: context.signal }),
  },
});
