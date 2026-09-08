import { config } from "./config.js";
import { experimental_acpProviderBridge } from "@get-bb/plugin-sdk/provider-bridge/acp";
import { bridgeRequestEnvelopeSchema, createBridgeIo, experimental_defineProviderBridge, providerMaintenanceParamsSchema, type ProviderBridgeEntry, type ProviderUsageResult } from "@get-bb/plugin-sdk/provider-bridge";
import { readAgyUsage, readCodexUsage, readKiroUsage, usageError } from "./usage.js";

// usage 查询支持的本插件 provider ID：三个原生入口 + config.codexAccounts 里的额外 Codex 账号。
const usageProviderIds = new Set([
  "acp-codexl", "acp-kiro", "acp-agy",
  ...config.codexAccounts.map(account => account.id),
]);

export function resolveUsageReader(id: string, signal: AbortSignal): Promise<ProviderUsageResult> {
  const account = config.codexAccounts.find(entry => entry.id === id);
  if (account) return readCodexUsage(account.command, { signal });
  return id === "acp-codexl" ? readCodexUsage(undefined, { signal })
    : id === "acp-agy" ? readAgyUsage(undefined, { signal })
    : readKiroUsage(undefined, { signal });
}

export function withAccountLimits(delegate: ProviderBridgeEntry, read: (id: string, signal: AbortSignal) => Promise<ProviderUsageResult>, write?: (line: string) => void): ProviderBridgeEntry {
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
