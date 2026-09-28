import { useCallback, useEffect, useState } from "react";
import { definePluginApp, useRpc } from "@get-bb/plugin-sdk/app";
import { accountLimitsPanelRpcContract, type AccountLimitsPanelSnapshot, type CliproxyUsageSnapshot } from "./contract.js";

function compactReset(value: string | null, now: number): string {
  const resetAt = value ? Date.parse(value) : NaN;
  if (!Number.isFinite(resetAt)) return "重置时间未知";
  const remainingMs = resetAt - now;
  if (remainingMs <= 0) return "已到重置时间，待刷新";
  const minutes = Math.floor(remainingMs / 60_000);
  if (minutes < 1) return "不到 1 分钟重置";
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);
  const duration = days > 0 ? `${days} 天 ${hours % 24} 小时`
    : hours > 0 ? `${hours} 小时 ${minutes % 60} 分钟` : `${minutes} 分钟`;
  return `还剩 ${duration}重置`;
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
type DisplayMode = "remaining" | "used";
const displayModeStorageKey = "account-limits.display-mode";

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

function WindowMeter({ window, now, mode }: { window: QuotaWindow; now: number; mode: DisplayMode }) {
  const label = displayWindowLabel(window);
  const remaining = remainingPercent(window.usedPercent);
  const percent = mode === "used" ? 100 - remaining : remaining;
  const reset = compactReset(window.resetsAt, now);
  const depleted = remaining <= 10;
  return <li className="min-w-0">
    <div className="flex items-baseline justify-between gap-2 text-xs">
      <span className="truncate text-muted-foreground">{shortWindowLabel(label)}</span>
      <span className={`shrink-0 tabular-nums ${depleted ? "text-destructive" : ""}`}>{`${Math.round(percent)}%`}</span>
    </div>
    <div className="mt-0.5 h-1 overflow-hidden rounded-full bg-muted" role="progressbar" aria-label={`${label} ${mode === "used" ? "已用" : "剩余"}额度`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} title={reset ? `${label} · ${reset}` : label}>
      <div className={`h-full rounded-full ${depleted ? "bg-destructive" : "bg-primary"}`} style={{ width: `${percent}%` }} />
    </div>
    <p className="mt-1 text-xs text-muted-foreground tabular-nums">{reset}</p>
  </li>;
}

function Usage({ usage, now, mode }: { usage: CliproxyUsageSnapshot["providers"][number]["usage"]; now: number; mode: DisplayMode }) {
  if (usage.status === "ok") {
    const columns = Math.max(...groupWindowsByAccount(usage.windows).map(([, windows]) => windows.length), 1);
    return <div className="space-y-1.5">
      {groupWindowsByAccount(usage.windows).map(([accountLabel, windows]) => <section key={accountLabel} aria-label={`${accountLabel} 的额度`} className="grid items-center gap-x-3 gap-y-1 sm:grid-cols-[minmax(8rem,14rem)_1fr]">
        <h3 className="truncate text-xs font-medium" title={accountLabel}>{accountLabel}</h3>
        <ul className="grid min-w-0 gap-x-3 gap-y-1" style={{ gridTemplateColumns: `repeat(${Math.min(columns, 4)}, minmax(4.5rem, 1fr))` }}>
          {windows.map((window, index) => <WindowMeter key={`${window.label}-${index}`} window={window} now={now} mode={mode} />)}
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
  const [mode, setMode] = useState<DisplayMode>(() => {
    try { return window.localStorage.getItem(displayModeStorageKey) === "used" ? "used" : "remaining"; }
    catch { return "remaining"; }
  });
  const changeMode = (next: DisplayMode) => {
    setMode(next);
    try { window.localStorage.setItem(displayModeStorageKey, next); }
    catch { /* 禁用浏览器存储时仍允许本次切换。 */ }
  };
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(timer);
  }, []);
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
      <div className="flex justify-end gap-1" role="group" aria-label="额度显示模式">
        {(["remaining", "used"] as const).map(value => <button key={value} type="button" aria-pressed={mode === value}
          className={`rounded border border-border px-2 py-1 text-xs ${mode === value ? "bg-accent font-medium" : "text-muted-foreground hover:bg-accent"}`}
          onClick={() => changeMode(value)}>{value === "used" ? "已用（Used）" : "剩余"}</button>)}
      </div>
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
          <Usage usage={provider.usage} now={now} mode={mode} />
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
