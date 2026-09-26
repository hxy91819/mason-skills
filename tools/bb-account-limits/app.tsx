import { useCallback, useEffect, useState } from "react";
import { definePluginApp, useRpc } from "@get-bb/plugin-sdk/app";
import { accountLimitsPanelRpcContract, type AccountLimitsPanelSnapshot, type CliproxyUsageSnapshot } from "./contract.js";

function compactReset(value: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return null;
  return new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}

function updatedLabel(value: string): string {
  const elapsedMs = Math.max(0, Date.now() - new Date(value).getTime());
  const minutes = Math.floor(elapsedMs / 60_000);
  if (minutes < 1) return "刚刚更新";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  return `${Math.floor(hours / 24)} 天前`;
}

type OkUsage = Extract<CliproxyUsageSnapshot["providers"][number]["usage"], { status: "ok" }>;
type QuotaWindow = OkUsage["windows"][number];

function displayWindowLabel(window: QuotaWindow): string {
  const prefix = window.accountLabel ? `${window.accountLabel} · ` : "";
  return prefix && window.label.startsWith(prefix) ? window.label.slice(prefix.length) : window.label;
}

function shortWindowLabel(label: string): string {
  const exact: Record<string, string> = {
    "5-hour limit": "5h",
    "Weekly limit": "周",
    "Weekly scoped limit": "scoped",
    "Current limit": "当前",
    "Secondary limit": "次级",
  };
  if (exact[label]) return exact[label];
  return label
    .replaceAll("Gemini Models: ", "Gemini ")
    .replaceAll("Claude and GPT models: ", "C/GPT ")
    .replaceAll("5-hour limit", "5h")
    .replaceAll("Weekly limit", "周")
    .replace(/(\d+)-minute limit/u, "$1m");
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

function remainingPercent(usedPercent: number): number {
  return Math.max(0, Math.min(100, 100 - usedPercent));
}

function WindowMeter({ window }: { window: QuotaWindow }) {
  const label = displayWindowLabel(window);
  const remaining = remainingPercent(window.usedPercent);
  const reset = compactReset(window.resetsAt);
  const depleted = remaining <= 10;
  return <li className="min-w-0">
    <div className="flex items-baseline justify-between gap-2 text-xs">
      <span className="truncate text-muted-foreground">{shortWindowLabel(label)}</span>
      <span className={`shrink-0 tabular-nums ${depleted ? "text-destructive" : ""}`}>{`${Math.round(remaining)}%`}</span>
    </div>
    <div className="mt-0.5 h-1 overflow-hidden rounded-full bg-muted" role="progressbar" aria-label={`${label} 剩余额度`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={remaining} title={reset ? `${label} · ${reset}` : label}>
      <div className={`h-full rounded-full ${depleted ? "bg-destructive" : "bg-primary"}`} style={{ width: `${remaining}%` }} />
    </div>
  </li>;
}

function Usage({ usage }: { usage: CliproxyUsageSnapshot["providers"][number]["usage"] }) {
  if (usage.status === "ok") {
    const columns = Math.max(...groupWindowsByAccount(usage.windows).map(([, windows]) => windows.length), 1);
    return <div className="space-y-1.5">
      {groupWindowsByAccount(usage.windows).map(([accountLabel, windows]) => <section key={accountLabel} aria-label={`${accountLabel} 的额度`} className="grid items-center gap-x-3 gap-y-1 sm:grid-cols-[minmax(8rem,14rem)_1fr]">
        <h3 className="truncate text-xs font-medium" title={accountLabel}>{accountLabel}</h3>
        <ul className="grid min-w-0 gap-x-3 gap-y-1" style={{ gridTemplateColumns: `repeat(${Math.min(columns, 4)}, minmax(4.5rem, 1fr))` }}>
          {windows.map((window, index) => <WindowMeter key={`${window.label}-${index}`} window={window} />)}
        </ul>
      </section>)}
    </div>;
  }
  const messages: Record<Exclude<typeof usage.status, "ok" | "error">, string> = {
    unauthenticated: "账号尚未登录。",
    expired: "账号登录已过期。",
    not_installed: "查询组件尚未安装。",
  };
  return <p className="text-xs text-destructive">{usage.status === "error" ? usage.message : messages[usage.status]}</p>;
}

function accountCountLabel(planLabel: string | null): string | null {
  const match = planLabel?.match(/(\d+\/\d+)\s+accounts$/u);
  return match?.[1] ?? planLabel;
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
  return <main className="h-full overflow-auto p-3">
    <div className="mx-auto max-w-6xl space-y-2">
      {error && <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1.5 text-xs text-destructive">{error}</p>}
      {!snapshot && loading && <p className="text-xs text-muted-foreground">正在读取账户额度…</p>}
      {snapshot?.machines.map(machine => <section key={machine.id} className="space-y-2" aria-label={`${machine.displayName} 的账户额度`}>
        {showMachineName && <h2 className="text-xs font-medium text-muted-foreground">{machine.displayName}</h2>}
        {machine.status === "disconnected" && <p className="rounded-md border border-border px-2 py-1.5 text-xs text-muted-foreground">此机器未连接，无法读取额度。</p>}
        {machine.status === "error" && <p className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1.5 text-xs text-destructive">{machine.error ?? "读取此机器的额度失败。"}</p>}
        {machine.status === "connected" && machine.error && <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1.5 text-xs text-destructive">{machine.error}</p>}
        {machine.status === "connected" && machine.providers.length === 0 && <p className="rounded-md border border-border px-2 py-1.5 text-xs text-muted-foreground">没有启用的 Cliproxy 账户额度。</p>}
        {machine.status === "connected" && machine.providers.map(provider => <article key={provider.id} className="rounded-md border border-border bg-card px-3 py-2">
          <div className="mb-1.5 flex items-center gap-2">
            <h2 className="text-sm font-medium">{provider.displayName}</h2>
            {provider.usage.status === "ok" && accountCountLabel(provider.usage.planLabel) && <span className="text-xs text-muted-foreground">{accountCountLabel(provider.usage.planLabel)}</span>}
            <span className="ml-auto text-xs text-muted-foreground">{updatedLabel(provider.updatedAt)}</span>
            <button type="button" aria-label={`刷新 ${provider.displayName} 额度`} className="rounded border border-border px-1.5 py-0.5 text-xs hover:bg-accent disabled:cursor-not-allowed disabled:opacity-60" onClick={() => void refreshProvider(provider.id)} disabled={refreshingProviderIds.has(provider.id)}>
              {refreshingProviderIds.has(provider.id) ? "刷新中" : "刷新"}
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
