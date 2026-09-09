import { useCallback, useEffect, useState } from "react";
import { definePluginApp, useRpc } from "@get-bb/plugin-sdk/app";
import { accountLimitsPanelRpcContract, type AccountLimitsPanelSnapshot, type CliproxyUsageSnapshot } from "./contract.js";

function resetLabel(value: string | null): string {
  if (!value) return "重置时间未知";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "重置时间未知";
  return `重置于 ${new Intl.DateTimeFormat("zh-CN", { dateStyle: "short", timeStyle: "short" }).format(date)}`;
}

function updatedLabel(value: string): string {
  const elapsedMs = Math.max(0, Date.now() - new Date(value).getTime());
  const minutes = Math.floor(elapsedMs / 60_000);
  if (minutes < 1) return "刚刚更新";
  if (minutes < 60) return `${minutes} 分钟前更新`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前更新`;
  return `${Math.floor(hours / 24)} 天前更新`;
}

type OkUsage = Extract<CliproxyUsageSnapshot["providers"][number]["usage"], { status: "ok" }>;
type QuotaWindow = OkUsage["windows"][number];

function displayWindowLabel(window: QuotaWindow): string {
  const prefix = window.accountLabel ? `${window.accountLabel} · ` : "";
  return prefix && window.label.startsWith(prefix) ? window.label.slice(prefix.length) : window.label;
}

function groupWindowsByAccount(windows: readonly QuotaWindow[]) {
  const groups = new Map<string, QuotaWindow[]>();
  for (const window of windows) {
    const accountLabel = window.accountLabel ?? "账户额度";
    const group = groups.get(accountLabel);
    if (group) group.push(window);
    else groups.set(accountLabel, [window]);
  }
  return [...groups.entries()];
}

function Usage({ usage }: { usage: CliproxyUsageSnapshot["providers"][number]["usage"] }) {
  if (usage.status === "ok") {
    return <>
      {usage.planLabel && <p className="mb-3 text-sm text-muted-foreground">{usage.planLabel}</p>}
      <div className="space-y-3">
        {groupWindowsByAccount(usage.windows).map(([accountLabel, windows]) => <section key={accountLabel} aria-label={`${accountLabel} 的额度`} className="rounded-md border border-border/70 bg-muted/30 p-3">
          <h3 className="mb-3 text-sm font-medium">{accountLabel}</h3>
          <ul className="space-y-3">
            {windows.map((window, index) => {
              const label = displayWindowLabel(window);
              const remaining = Math.max(0, Math.min(100, 100 - window.usedPercent));
              return <li key={`${window.label}-${index}`}>
                <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
                  <span>{label}</span>
                  <span className="shrink-0 text-muted-foreground">剩余 {remaining.toFixed(1)}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-label={`${label} 剩余额度`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={remaining}>
                  <div className="h-full rounded-full bg-primary" style={{ width: `${remaining}%` }} />
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{resetLabel(window.resetsAt)}</p>
              </li>;
            })}
          </ul>
        </section>)}
      </div>
    </>;
  }
  const messages: Record<Exclude<typeof usage.status, "ok" | "error">, string> = {
    unauthenticated: "账号尚未登录。",
    expired: "账号登录已过期。",
    not_installed: "查询组件尚未安装。",
  };
  return <p className="text-sm text-destructive">{usage.status === "error" ? usage.message : messages[usage.status]}</p>;
}

function AccountLimitsPanel() {
  const rpc = useRpc<typeof accountLimitsPanelRpcContract>();
  const [snapshot, setSnapshot] = useState<AccountLimitsPanelSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshingProviderIds, setRefreshingProviderIds] = useState<Set<string>>(new Set());
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSnapshot(await rpc.call("readCliproxyUsage", {}));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "读取账户额度失败。请稍后重试。");
    } finally {
      setLoading(false);
    }
  }, [rpc]);
  useEffect(() => { void load(); }, [load]);

  const refreshProvider = useCallback(async (providerId: string) => {
    setRefreshingProviderIds(current => new Set(current).add(providerId));
    setError(null);
    try {
      const refreshed = await rpc.call("readCliproxyUsage", { providerIds: [providerId], force: true });
      setSnapshot(current => {
        if (!current) return refreshed;
        const machines = new Map(refreshed.machines.map(machine => [machine.id, machine]));
        return {
          machines: current.machines.map(machine => {
            const update = machines.get(machine.id);
            if (!update) return machine;
            const providers = new Map(machine.providers.map(provider => [provider.id, provider]));
            for (const provider of update.providers) providers.set(provider.id, provider);
            return { ...update, providers: [...providers.values()] };
          }),
        };
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "刷新账户额度失败。请稍后重试。");
    } finally {
      setRefreshingProviderIds(current => {
        const next = new Set(current);
        next.delete(providerId);
        return next;
      });
    }
  }, [rpc]);

  const showMachineName = (snapshot?.machines.length ?? 0) > 1;
  return <main className="h-full overflow-auto p-4 md:p-5">
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">按上游供应商聚合的 Cliproxy 账户额度；数据最多缓存 30 分钟，供应商卡片可单独刷新。</p>
      </div>
      {error && <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
      {!snapshot && loading && <p className="text-sm text-muted-foreground">正在读取账户额度…</p>}
      {snapshot?.machines.map(machine => <section key={machine.id} className="space-y-3" aria-label={`${machine.displayName} 的账户额度`}>
        {showMachineName && <h2 className="text-sm font-medium text-muted-foreground">{machine.displayName}</h2>}
        {machine.status === "disconnected" && <p className="rounded-md border border-border p-3 text-sm text-muted-foreground">此机器未连接，无法读取额度。</p>}
        {machine.status === "error" && <p className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{machine.error ?? "读取此机器的额度失败。"}</p>}
        {machine.status === "connected" && machine.error && <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{machine.error}</p>}
        {machine.status === "connected" && machine.providers.length === 0 && <p className="rounded-md border border-border p-3 text-sm text-muted-foreground">没有启用的 Cliproxy 账户额度。</p>}
        {machine.status === "connected" && machine.providers.map(provider => <article key={provider.id} className="rounded-lg border border-border bg-card p-4 shadow-sm">
          <div className="mb-3 flex items-start justify-between gap-3">
            <div>
              <h2 className="font-medium">{provider.displayName}</h2>
              <p className="mt-1 text-xs text-muted-foreground">{updatedLabel(provider.updatedAt)}</p>
            </div>
            <button type="button" aria-label={`刷新 ${provider.displayName} 额度`} className="rounded-md border border-border px-2.5 py-1 text-sm hover:bg-accent disabled:cursor-not-allowed disabled:opacity-60" onClick={() => void refreshProvider(provider.id)} disabled={refreshingProviderIds.has(provider.id)}>
              {refreshingProviderIds.has(provider.id) ? "正在刷新…" : "刷新"}
            </button>
          </div>
          <Usage usage={provider.usage} />
        </article>)}
      </section>)}
    </div>
  </main>;
}

export default definePluginApp(app => {
  app.slots.navPanel({
    id: "account-limits",
    title: "账户额度",
    icon: "ChartColumn",
    path: "account-limits",
    component: AccountLimitsPanel,
  });
});
