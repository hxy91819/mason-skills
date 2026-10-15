import { useCallback, useEffect, useState } from "react";
import { definePluginApp, useRpc } from "@get-bb/plugin-sdk/app";
import { accountLimitsPanelRpcContract, type AccountLimitsPanelSnapshot, type CliproxyUsageSnapshot } from "./contract.js";
import { aggregateCliproxyPool, groupAccountPools, normalizeCliproxyWindow, orderQuotaWindows, type PoolWindow } from "./pool.js";
import { AntigravityIcon, GrokIcon } from "./provider-icons.js";

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

function updatedLabel(value: string | null): string {
  if (value === null) return "尚无成功测量";
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
type PanelProvider = AccountLimitsPanelSnapshot["machines"][number]["providers"][number];
type DisplayMode = "remaining" | "used";
type PanelView = "accounts" | "pool";
const displayModeStorageKey = "account-limits.display-mode";
const panelViewStorageKey = "account-limits.view";

function displayWindowLabel(window: QuotaWindow): string {
  const prefix = window.accountLabel ? `${window.accountLabel} · ` : "";
  return prefix && window.label.startsWith(prefix) ? window.label.slice(prefix.length) : window.label;
}

function shortWindowLabel(label: string): string {
  const exact: Record<string, string> = {
    "5-hour limit": "5h",
    "Five-hour limit": "5h",
    "Weekly limit": "周",
    "Weekly scoped limit": "Fable",
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

type MeterWindow = QuotaWindow & { detail?: string; displayLabel?: string };

function WindowMeter({ window, now, mode }: { window: MeterWindow; now: number; mode: DisplayMode }) {
  const label = displayWindowLabel(window);
  const remaining = remainingPercent(window.usedPercent);
  const percent = mode === "used" ? 100 - remaining : remaining;
  const reset = compactReset(window.resetsAt, now);
  const depleted = remaining <= 10;
  return <li className="min-w-0">
    <div className="flex items-baseline justify-between gap-2 text-xs">
      <span className="truncate text-muted-foreground">{window.displayLabel ?? shortWindowLabel(label)}</span>
      <span className={`shrink-0 tabular-nums ${depleted ? "text-destructive" : ""}`}>{`${Math.round(percent)}%`}</span>
    </div>
    <div className="mt-0.5 h-1 overflow-hidden rounded-full bg-muted" role="progressbar" aria-label={`${label} ${mode === "used" ? "已用" : "剩余"}额度`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} title={reset ? `${label} · ${reset}` : label}>
      <div className={`h-full rounded-full ${depleted ? "bg-destructive" : "bg-primary"}`} style={{ width: `${percent}%` }} />
    </div>
    <p className="mt-1 text-xs text-muted-foreground tabular-nums">{window.detail ? `${reset} · ${window.detail}` : reset}</p>
  </li>;
}

function modelWeeklyName(label: string): string | null {
  if (/^(weekly scoped limit|scoped)$/iu.test(label)) return "Fable";
  const model = /\b(fable|opus|sonnet|haiku)\b/iu.exec(label)?.[1];
  return model && /\b(weekly|7d)\b/iu.test(label) ? model[0].toUpperCase() + model.slice(1).toLowerCase() : null;
}

function MeterList({ windows, now, mode }: { windows: readonly MeterWindow[]; now: number; mode: DisplayMode }) {
  return <ul className="grid min-w-0 gap-x-3 gap-y-1" style={{ gridTemplateColumns: `repeat(${Math.min(Math.max(windows.length, 1), 4)}, minmax(0, 1fr))` }}>
    {windows.map((window, index) => <WindowMeter key={`${window.label}-${index}`} window={window} now={now} mode={mode} />)}
  </ul>;
}

/** Model limits constrain the same weekly usage; their percentages have separate denominators. */
function QuotaWindows({ providerId, windows, now, mode }: {
  providerId: string; windows: readonly MeterWindow[]; now: number; mode: DisplayMode;
}) {
  const ordered = orderQuotaWindows(windows).map(window => ({ ...window, label: displayWindowLabel(window), accountLabel: null }));
  const claude = ["claude", "cliproxy-claude", "account-pool:claude-code"].includes(providerId);
  const modelWindows = claude ? ordered.filter(window => modelWeeklyName(window.label) !== null) : [];
  if (modelWindows.length === 0) return <MeterList windows={ordered} now={now} mode={mode} />;
  const totalWindows = ordered.filter(window => normalizeCliproxyWindow(window.label).id === "7d");
  const otherWindows = ordered.filter(window => !totalWindows.includes(window) && !modelWindows.includes(window));
  const exhausted = totalWindows.some(window => window.usedPercent >= 100);
  return <div className={`grid min-w-0 gap-3 ${otherWindows.length ? "sm:grid-cols-[minmax(6rem,1fr)_minmax(0,2fr)]" : ""}`}>
    {otherWindows.length > 0 && <MeterList windows={otherWindows} now={now} mode={mode} />}
    <div role="group" aria-label="周额度" className="min-w-0 space-y-2 rounded border border-border px-2 py-1.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-2 text-xs">
        <span className="font-medium">周额度</span>
        {exhausted && <span className="text-destructive">总周额度已用尽</span>}
        {totalWindows.length === 0 && <span className="text-muted-foreground">总周额度未返回</span>}
      </div>
      {totalWindows.length > 0 && <MeterList windows={totalWindows.map(window => ({ ...window, displayLabel: "全部模型" }))} now={now} mode={mode} />}
      <div role="group" aria-label="模型周上限" className="min-w-0 border-l-2 border-border pl-3">
        <MeterList windows={modelWindows.map(window => ({ ...window, displayLabel: `${modelWeeklyName(window.label)} 周上限` }))} now={now} mode={mode} />
      </div>
      <p className="text-xs text-muted-foreground">{totalWindows.length > 0
        ? "模型使用同时计入总周额度；百分比分别计算，不可相加。"
        : "仅显示模型自身上限，无法据此判断总周余量。"}</p>
    </div>
  </div>;
}

function poolWindowDetail(window: PoolWindow, totalAccounts: number): string {
  const exhausted = window.exhausted > 0 ? ` · ${window.exhausted} 账号已耗尽` : "";
  return `覆盖 ${window.accounts}/${totalAccounts}${exhausted}`;
}

function PoolUsage({ provider, now, mode }: { provider: PanelProvider; now: number; mode: DisplayMode }) {
  return <div className="space-y-2">
    {groupAccountPools(provider.id, provider.accounts).map(group => <section key={group.id}
      aria-label={group.label ? `${group.label} 的池额度` : undefined}>
      {group.label && <h3 className="mb-1 text-xs font-medium">{group.label}</h3>}
      <PoolGroupUsage providerId={provider.id} accounts={group.accounts} providerUsage={provider.usage} now={now} mode={mode} />
    </section>)}
  </div>;
}

function PoolGroupUsage({ providerId, accounts, providerUsage, now, mode }: {
  providerId: string;
  accounts: readonly PanelProvider["accounts"][number][];
  providerUsage: PanelProvider["usage"]; now: number; mode: DisplayMode;
}) {
  const pool = aggregateCliproxyPool(accounts);
  if (pool.status !== "ok") {
    const message = accounts.length === 0 && providerUsage.status === "error" ? providerUsage.message : pool.message;
    return <p className="text-xs text-destructive">{message}</p>;
  }
  if (pool.windows.length === 0) return <p className="text-xs text-muted-foreground">未报告额度窗口。</p>;
  return <QuotaWindows providerId={providerId} windows={pool.windows.map(window => ({
    accountLabel: null, label: window.label, usedPercent: window.usedPercent, resetsAt: window.resetsAt,
    detail: poolWindowDetail(window, pool.totalAccounts),
  }))} now={now} mode={mode} />;
}

function Usage({ providerId, usage, now, mode }: { providerId: string; usage: CliproxyUsageSnapshot["providers"][number]["usage"]; now: number; mode: DisplayMode }) {
  if (usage.status === "ok") {
    return <div className="space-y-1.5">
      {groupWindowsByAccount(usage.windows).map(([accountLabel, windows]) => <section key={accountLabel} aria-label={`${accountLabel} 的额度`} className="grid items-center gap-x-3 gap-y-1 sm:grid-cols-[minmax(8rem,14rem)_1fr]">
        <h3 className="truncate text-xs font-medium" title={accountLabel}>{accountLabel}</h3>
        <QuotaWindows providerId={providerId} windows={windows} now={now} mode={mode} />
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

function AccountUsage({ provider, now, mode }: { provider: PanelProvider; now: number; mode: DisplayMode }) {
  if (provider.accounts.length === 0) return <Usage providerId={provider.id} usage={provider.usage} now={now} mode={mode} />;
  return <div className="space-y-1.5">
    {provider.accounts.map(account => <section key={account.key} aria-label={`${account.label} 的额度`}
      className="grid items-center gap-x-3 gap-y-1 sm:grid-cols-[minmax(8rem,14rem)_1fr]">
      <div className="min-w-0">
        <h3 className="truncate text-xs font-medium" title={account.label}>{account.label}</h3>
        {account.usage.status === "ok" && account.usage.planLabel && <p className="text-xs text-muted-foreground">{account.usage.planLabel}</p>}
        {account.updatedAt !== undefined && <p className="text-xs text-muted-foreground">{updatedLabel(account.updatedAt)}</p>}
      </div>
      {account.usage.status === "ok"
        ? account.usage.windows.length === 0
          ? <p className="text-xs text-muted-foreground">未报告额度窗口。</p>
          : <QuotaWindows providerId={provider.id} windows={account.usage.windows.map(window => ({ ...window, accountLabel: null }))} now={now} mode={mode} />
        : <Usage providerId={provider.id} usage={account.usage} now={now} mode={mode} />}
    </section>)}
  </div>;
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
  const [view, setView] = useState<PanelView>(() => {
    try { return window.localStorage.getItem(panelViewStorageKey) === "pool" ? "pool" : "accounts"; }
    catch { return "accounts"; }
  });
  const changeView = (next: PanelView) => {
    setView(next);
    try { window.localStorage.setItem(panelViewStorageKey, next); }
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
  const load = useCallback(async (force = false) => {
    setLoading(true);
    setError(null);
    try {
      setSnapshot(await rpc.call("readAccountLimits", force ? { force: true } : {}));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "读取账户额度失败。请稍后重试。");
    } finally {
      setLoading(false);
    }
  }, [rpc]);
  useEffect(() => { void load(); }, [load]);

  const refreshProvider = useCallback(async (providerId: string, source: "cliproxy" | "account-pool") => {
    setRefreshingProviderIds(current => new Set(current).add(providerId));
    setError(null);
    try {
      const refreshed = await rpc.call("readAccountLimits", { source, providerIds: [providerId], force: true });
      setSnapshot(current => {
        if (!current) return refreshed;
        const refreshedSources = new Set(refreshed.machines.map(machine => machine.source ?? "cliproxy"));
        return {
          machines: (["cliproxy", "account-pool"] as const).flatMap(source =>
            (refreshedSources.has(source) ? refreshed.machines : current.machines)
              .filter(machine => (machine.source ?? "cliproxy") === source)),
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
      <div className="flex justify-end gap-3">
        <button type="button" className="rounded border border-border px-2 py-1 text-xs hover:bg-accent disabled:opacity-60"
          disabled={loading || refreshingProviderIds.size > 0} onClick={() => void load(true)}>{loading && snapshot ? "刷新中" : "刷新全部"}</button>
        <div className="flex gap-1" role="group" aria-label="额度视图">
          {(["accounts", "pool"] as const).map(value => <button key={value} type="button" aria-pressed={view === value}
            className={`rounded border border-border px-2 py-1 text-xs ${view === value ? "bg-accent font-medium" : "text-muted-foreground hover:bg-accent"}`}
            onClick={() => changeView(value)}>{value === "pool" ? "池" : "账号"}</button>)}
        </div>
        <div className="flex gap-1" role="group" aria-label="额度显示模式">
          {(["remaining", "used"] as const).map(value => <button key={value} type="button" aria-pressed={mode === value}
            className={`rounded border border-border px-2 py-1 text-xs ${mode === value ? "bg-accent font-medium" : "text-muted-foreground hover:bg-accent"}`}
            onClick={() => changeMode(value)}>{value === "used" ? "已用（Used）" : "剩余"}</button>)}
        </div>
      </div>
      {error && <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1.5 text-xs text-destructive">{error}</p>}
      {!snapshot && loading && <p className="text-xs text-muted-foreground">正在读取账户额度…</p>}
      {snapshot?.machines.map(machine => <section key={machine.id} className="space-y-2" aria-label={`${machine.displayName} 的账户额度`}>
        {showMachineName && <h2 className="text-xs font-medium text-muted-foreground">{machine.displayName}</h2>}
        {machine.status === "disconnected" && <p className="rounded-md border border-border px-2 py-1.5 text-xs text-muted-foreground">此机器未连接，无法读取额度。</p>}
        {machine.status === "error" && <p className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1.5 text-xs text-destructive">{machine.error ?? "读取此机器的额度失败。"}</p>}
        {machine.status === "connected" && machine.error && <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1.5 text-xs text-destructive">{machine.error}</p>}
        {machine.status === "connected" && machine.providers.length === 0 && <p className="rounded-md border border-border px-2 py-1.5 text-xs text-muted-foreground">{machine.source === "account-pool" ? "Account Pooler 尚未添加账号。" : "没有启用的 Cliproxy 账户额度。"}</p>}
        {machine.status === "connected" && machine.providers.map(provider => <article key={provider.id} className="rounded-md border border-border bg-card px-3 py-2">
          <div className="mb-1.5 flex items-center gap-2">
            <h2 className="text-sm font-medium">{provider.displayName}</h2>
            <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">{machine.source === "account-pool" ? "Account Pooler" : "Cliproxy"}</span>
            {provider.usage.status === "ok" && accountCountLabel(provider.usage.planLabel) && <span className="text-xs text-muted-foreground">{accountCountLabel(provider.usage.planLabel)}</span>}
            <span className="ml-auto text-xs text-muted-foreground">{updatedLabel(provider.updatedAt)}</span>
            <button type="button" aria-label={`刷新 ${machine.source === "account-pool" ? "Account Pooler " : ""}${provider.displayName} 额度`} className="rounded border border-border px-1.5 py-0.5 text-xs hover:bg-accent disabled:cursor-not-allowed disabled:opacity-60" onClick={() => void refreshProvider(provider.id, machine.source ?? "cliproxy")} disabled={loading || refreshingProviderIds.has(provider.id)}>
              {refreshingProviderIds.has(provider.id) ? "刷新中" : "刷新"}
            </button>
          </div>
          {view === "pool" ? <PoolUsage provider={provider} now={now} mode={mode} /> : <AccountUsage provider={provider} now={now} mode={mode} />}
        </article>)}
      </section>)}
    </div>
  </main>;
}

export default definePluginApp(app => {
  // Provider Usage resolves these marks by resource providerId, including IDs
  // without an executable agent provider. Keep them scoped to Cliproxy.
  app.slots.experimental_providerIcon({ providerKind: "agent", providerId: "cliproxy-xai", icon: GrokIcon });
  app.slots.experimental_providerIcon({ providerKind: "agent", providerId: "cliproxy-antigravity", icon: AntigravityIcon });
  app.slots.navPanel({
    id: "account-limits",
    title: "账户额度",
    // 导航图标优先于插件品牌图标，与 package.json 的 bb.branding.icon 保持一致。
    icon: "CircleDollarSign",
    path: "account-limits",
    component: AccountLimitsPanel,
  });
});
