import {
  activeCliproxyAccountsByProvider,
  cliproxyProviderId,
  config,
} from "./config.js";
import { experimental_acpProviderBridge } from "@get-bb/plugin-sdk/provider-bridge/acp";
import { bridgeRequestEnvelopeSchema, createBridgeIo, experimental_defineProviderBridge, modelListParamsSchema, providerMaintenanceParamsSchema, type ProviderBridgeEntry, type ProviderUsageResult } from "@get-bb/plugin-sdk/provider-bridge";
import { readAgyUsage, readCliproxyManagementKey, readCliproxyProviderUsage, readCodexUsage, readKiroUsage, usageError } from "./usage.js";

// usage 查询支持的本插件 provider ID：三个原生入口 + config.codexAccounts 里的额外 Codex 账号。
const usageProviderIds = new Set([
  "acp-codexl", "acp-kiro", "acp-agy",
  ...config.codexAccounts.map(account => account.id),
  ...[...activeCliproxyAccountsByProvider(config.cliproxy.accounts).keys()].map(cliproxyProviderId),
]);
const usageOnlyProviderIds = new Set(
  [...activeCliproxyAccountsByProvider(config.cliproxy.accounts).keys()].map(cliproxyProviderId),
);

function modelRequestIsUsageOnly(params: unknown, usageOnlyIds: ReadonlySet<string>): boolean {
  const parsed = modelListParamsSchema.safeParse(params);
  if (!parsed.success) return false;
  const values = parsed.data as Record<string, unknown>;
  const providerOptions = values.providerOptions;
  const usageOnly = providerOptions !== null && typeof providerOptions === "object"
    && (providerOptions as Record<string, unknown>).usageOnly === true;
  return usageOnly || (typeof values.providerId === "string" && usageOnlyIds.has(values.providerId));
}

export async function resolveUsageReader(id: string, signal: AbortSignal): Promise<ProviderUsageResult> {
  const account = config.codexAccounts.find(entry => entry.id === id);
  if (account) return readCodexUsage(account.command, { signal });
  if (id.startsWith("cliproxy-")) {
    const provider = id.slice("cliproxy-".length).toLowerCase();
    const cliproxyAccounts = activeCliproxyAccountsByProvider(config.cliproxy.accounts).get(provider);
    if (!cliproxyAccounts?.length) return usageError("Cliproxy provider is not configured.");
    const managementKey = await readCliproxyManagementKey(config.cliproxy);
    return readCliproxyProviderUsage(cliproxyAccounts, {
      managementBaseUrl: config.cliproxy.managementBaseUrl,
      managementKey,
      signal,
    });
  }
  return id === "acp-codexl" ? readCodexUsage(undefined, { signal })
    : id === "acp-agy" ? readAgyUsage(undefined, { signal })
    : readKiroUsage(undefined, { signal });
}

export function withAccountLimits(
  delegate: ProviderBridgeEntry,
  read: (id: string, signal: AbortSignal) => Promise<ProviderUsageResult>,
  write?: (line: string) => void,
  usageOnlyIds: ReadonlySet<string> = usageOnlyProviderIds,
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
      if (raw?.method !== "provider/usage" && raw?.method !== "model/list") { delegate.handleLine(line); return; }
      const request = bridgeRequestEnvelopeSchema.safeParse(raw);
      if (!request.success) { delegate.handleLine(line); return; }
      if (raw.method === "model/list") {
        if (modelRequestIsUsageOnly(request.data.params, usageOnlyIds)) io.sendResult(request.data.id, { models: [], selectedOnlyModels: [] });
        else delegate.handleLine(line);
        return;
      }
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
