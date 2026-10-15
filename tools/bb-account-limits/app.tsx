import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { definePluginApp, useRpc } from "@get-bb/plugin-sdk/app";
import { accountLimitsPanelRpcContract, type AccountLimitsPanelSnapshot, type CliproxyUsageSnapshot } from "./contract.js";
import { aggregateCliproxyPool, groupAccountPools, normalizeCliproxyWindow, orderQuotaWindows, type PoolWindow } from "./pool.js";
import { AntigravityIcon, GrokIcon } from "./provider-icons.js";
import { panelStyles } from "./panel-styles.js";
import { buildPoolRecovery, type PoolRecovery } from "./pool-recovery.js";

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
    .replace(/\b7d\b/gu, "周")
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

type MeterWindow = QuotaWindow & { detail?: string; displayLabel?: string; recovery?: PoolRecovery | null };

function recoveryNumber(value: number): string {
  return value > 0 && value < 0.1 ? "<0.1" : new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 1 }).format(value);
}

function recoveryStrength(index: number, count: number): number {
  return 100 - 60 * index / Math.max(1, count - 1);
}

function RecoverySegments({ recovery, mode, now }: { recovery: PoolRecovery; mode: DisplayMode; now: number }) {
  const segments = [
    ...(mode === "remaining" ? [{ key: "remaining", percent: recovery.remainingPercent, kind: "current", strength: 100, title: `当前剩余 ${recoveryNumber(recovery.remainingPercent)}%` }] : []),
    { key: "overdue", percent: recovery.overduePercent, kind: "unresolved", strength: 40, title: `已到重置时间，待刷新 · ${recoveryNumber(recovery.overduePercent)} 个百分点` },
    ...recovery.steps.map((step, index) => ({ key: step.resetsAt, percent: step.gainPercent, kind: "future",
      strength: recoveryStrength(index, recovery.steps.length) * (mode === "remaining" ? 0.45 : 1),
      title: `${compactReset(step.resetsAt, now)} · 预计恢复 ${recoveryNumber(step.gainPercent)} 个百分点 · 预计剩余 ${recoveryNumber(step.remainingPercent)}%`,
    })),
    { key: "unknown", percent: recovery.unknownPercent, kind: "unresolved", strength: 40, title: `重置时间未知 · ${recoveryNumber(recovery.unknownPercent)} 个百分点，未计入定时预测` },
  ];
  return <>{segments.filter(segment => segment.percent > 0).map(segment => <span key={segment.key}
    className={`limits-recovery-segment limits-recovery-segment--${segment.kind}`} aria-hidden="true" title={segment.title}
    style={{ width: `${segment.percent}%`, "--recovery-strength": `${segment.strength}%` } as CSSProperties} />)}</>;
}

function PanelIcon({ name, spinning = false }: { name: "refresh" | "accounts" | "pool" | "info" | "layers"; spinning?: boolean }) {
  const paths = {
    refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M6.1 7a7 7 0 0 1 11.6-2L20 8M4 16l2.3 3A7 7 0 0 0 17.9 17" /></>,
    accounts: <><circle cx="9" cy="8" r="3" /><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 5a3 3 0 0 1 0 6M18 15a5 5 0 0 1 3 4v2" /></>,
    pool: <><path d="m12 3 9 5-9 5-9-5 9-5ZM3 12l9 5 9-5M3 16l9 5 9-5" /></>,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7h.01" /></>,
    layers: <><rect x="3" y="3" width="7" height="7" rx="2" /><rect x="14" y="3" width="7" height="7" rx="2" /><rect x="3" y="14" width="7" height="7" rx="2" /><path d="M14 17.5h7M17.5 14v7" /></>,
  };
  return <svg className={`limits-icon${spinning ? " limits-icon--spin" : ""}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function ProviderMark({ id, name }: { id: string; name: string }) {
  if (id.includes("antigravity")) return <AntigravityIcon className="limits-mark-icon" />;
  if (id.includes("xai")) return <GrokIcon className="limits-mark-icon" />;
  if (id.includes("claude")) return <svg className="limits-mark-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="M12 2v20M2 12h20M5 5l14 14M5 19 19 5M3 8l18 8M8 3l8 18M3 16l18-8M8 21 16 3" /></svg>;
  return <span className="limits-mark-letter" aria-hidden="true">{id.includes("codex") ? "⌘" : name.slice(0, 1).toUpperCase()}</span>;
}

function WindowMeter({ window, now, mode }: { window: MeterWindow; now: number; mode: DisplayMode }) {
  const label = displayWindowLabel(window);
  const remaining = remainingPercent(window.usedPercent);
  const percent = mode === "used" ? 100 - remaining : remaining;
  const reset = compactReset(window.resetsAt, now);
  const depleted = remaining <= 10;
  return <li className="limits-meter" data-depleted={depleted || undefined}>
    <div className="limits-meter-heading">
      <span className="limits-meter-label" title={window.displayLabel ?? shortWindowLabel(label)}>{window.displayLabel ?? shortWindowLabel(label)}</span>
      <span className="limits-meter-number">{`${Math.round(percent)}%`}</span>
    </div>
    <div className={`limits-meter-track${window.recovery && window.recovery.usedPercent > 0 ? " limits-meter-track--recovery" : ""}`} role="progressbar" aria-label={`${label} ${mode === "used" ? "已用" : "剩余"}额度`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} title={`${label} · ${reset}`}>
      {window.recovery && window.recovery.usedPercent > 0 ? <RecoverySegments recovery={window.recovery} mode={mode} now={now} /> : <div className="limits-meter-fill" style={{ width: `${percent}%` }} />}
    </div>
    <p className="limits-reset">{window.detail ? `${reset} · ${window.detail}` : reset}</p>
  </li>;
}

function modelWeeklyName(label: string): string | null {
  if (/^(weekly scoped limit|scoped)$/iu.test(label)) return "Fable";
  const model = /\b(fable|opus|sonnet|haiku)\b/iu.exec(label)?.[1];
  return model && /\b(weekly|7d)\b/iu.test(label) ? model[0].toUpperCase() + model.slice(1).toLowerCase() : null;
}

function MeterList({ windows, now, mode }: { windows: readonly MeterWindow[]; now: number; mode: DisplayMode }) {
  const columns = Math.min(Math.max(windows.length, 1), 4);
  return <ul className="limits-meters" data-columns={columns} style={{ "--quota-columns": columns } as CSSProperties}>
    {windows.map((window, index) => <WindowMeter key={`${window.label}-${index}`} window={window} now={now} mode={mode} />)}
  </ul>;
}

function ModelCap({ window, now, mode }: { window: MeterWindow; now: number; mode: DisplayMode }) {
  const remaining = remainingPercent(window.usedPercent);
  const percent = mode === "used" ? 100 - remaining : remaining;
  const reset = compactReset(window.resetsAt, now);
  return <li className="limits-cap">
    <div className="limits-cap-heading">
      <span className="limits-cap-label">{modelWeeklyName(window.label)} 周上限</span>
      <span className="limits-cap-value" data-depleted={remaining <= 10 || undefined} role="progressbar"
        aria-label={`${window.label} ${mode === "used" ? "已用" : "剩余"}额度`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}
        aria-valuetext={`${mode === "used" ? "已用" : "剩余"} ${Math.round(percent)}%，以 ${modelWeeklyName(window.label)} 自身周上限计算`}>
        <span className="limits-cap-mode">{mode === "used" ? "已用" : "剩余"}</span> {Math.round(percent)}%
      </span>
    </div>
    <p className="limits-reset">{window.detail ? `${reset} · ${window.detail}` : reset}</p>
  </li>;
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
  return <div className={`limits-quotas${otherWindows.length ? " limits-quotas--weekly" : ""}`}>
    {otherWindows.length > 0 && <MeterList windows={otherWindows} now={now} mode={mode} />}
    <div role="group" aria-label="周额度" className="limits-weekly">
      {totalWindows.length > 0
        ? <MeterList windows={totalWindows.map(window => ({ ...window, displayLabel: "总周额度" }))} now={now} mode={mode} />
        : <div className="limits-weekly-unknown"><span>总周额度</span><span className="limits-unknown-value">—</span><span className="limits-reset">总周额度未返回</span></div>}
      {exhausted && <p className="limits-exhausted">总周额度已用尽</p>}
      <div role="group" aria-label="模型周上限" className="limits-caps">
        <ul>{modelWindows.map((window, index) => <ModelCap key={`${window.label}-${index}`} window={window} now={now} mode={mode} />)}</ul>
      </div>
    </div>
  </div>;
}

function poolWindowDetail(window: PoolWindow, totalAccounts: number): string {
  const exhausted = window.exhausted > 0 ? ` · ${window.exhausted} 账号已耗尽` : "";
  return `覆盖 ${window.accounts}/${totalAccounts}${exhausted}`;
}

function PoolUsage({ provider, now, mode }: { provider: PanelProvider; now: number; mode: DisplayMode }) {
  return <div className="limits-pools">
    {groupAccountPools(provider.id, provider.accounts).map(group => <section key={group.id}
      className="limits-pool"
      aria-label={group.label ? `${group.label} 的池额度` : undefined}>
      {group.label && <h3 className="limits-pool-label"><PanelIcon name="pool" />{group.label}</h3>}
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
    return <p className="limits-message limits-message--error">{message}</p>;
  }
  if (pool.windows.length === 0) return <p className="limits-message">未报告额度窗口。</p>;
  return <QuotaWindows providerId={providerId} windows={pool.windows.map(window => ({
    accountLabel: null, label: window.label, usedPercent: window.usedPercent, resetsAt: window.resetsAt,
    detail: poolWindowDetail(window, pool.totalAccounts),
    recovery: buildPoolRecovery(accounts, window.id, now),
  }))} now={now} mode={mode} />;
}

function Usage({ providerId, usage, now, mode }: { providerId: string; usage: CliproxyUsageSnapshot["providers"][number]["usage"]; now: number; mode: DisplayMode }) {
  if (usage.status === "ok") {
    if (usage.windows.length === 0) return <p className="limits-message">未报告额度窗口。</p>;
    return <div className="limits-accounts">
      {groupWindowsByAccount(usage.windows).map(([accountLabel, windows]) => <section key={accountLabel} aria-label={`${accountLabel} 的额度`} className="limits-account">
        <h3 className="limits-account-name" title={accountLabel}>{accountLabel}</h3>
        <QuotaWindows providerId={providerId} windows={windows} now={now} mode={mode} />
      </section>)}
    </div>;
  }
  const messages: Record<Exclude<typeof usage.status, "ok" | "error">, string> = {
    unauthenticated: "账号尚未登录。",
    expired: "账号登录已过期。",
    not_installed: "查询组件尚未安装。",
  };
  return <p className="limits-message limits-message--error">{usage.status === "error" ? usage.message : messages[usage.status]}</p>;
}

function AccountUsage({ provider, now, mode }: { provider: PanelProvider; now: number; mode: DisplayMode }) {
  if (provider.accounts.length === 0) return <Usage providerId={provider.id} usage={provider.usage} now={now} mode={mode} />;
  return <div className="limits-accounts">
    {provider.accounts.map((account, index) => <section key={account.key} aria-label={`${account.label} 的额度`}
      className="limits-account">
      <div className="limits-identity">
        <span className="limits-account-index" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
        <div className="limits-identity-text">
          <h3 className="limits-account-name" title={account.label}>{account.label}</h3>
          <div className="limits-account-meta">
            {account.usage.status === "ok" && account.usage.planLabel && account.usage.planLabel.trim() !== account.label.trim() && <span className="limits-plan">{account.usage.planLabel}</span>}
            {account.updatedAt !== undefined && <span>{updatedLabel(account.updatedAt)}</span>}
          </div>
        </div>
      </div>
      {account.usage.status === "ok"
        ? account.usage.windows.length === 0
          ? <p className="limits-message">未报告额度窗口。</p>
          : <QuotaWindows providerId={provider.id} windows={account.usage.windows.map(window => ({ ...window, accountLabel: null }))} now={now} mode={mode} />
        : <Usage providerId={provider.id} usage={account.usage} now={now} mode={mode} />}
    </section>)}
  </div>;
}

function accountCountLabel(planLabel: string | null): string | null {
  const match = planLabel?.match(/(\d+\/\d+)\s+accounts$/u);
  return match?.[1] ?? planLabel;
}

function ModelLimitNote({ provider }: { provider: PanelProvider }) {
  if (!["claude", "cliproxy-claude", "account-pool:claude-code"].includes(provider.id)) return null;
  const windows = provider.accounts.length > 0
    ? provider.accounts.flatMap(account => account.usage.status === "ok" ? account.usage.windows.map(window => ({ ...window, accountLabel: null })) : [])
    : provider.usage.status === "ok" ? provider.usage.windows : [];
  if (!windows.some(window => modelWeeklyName(displayWindowLabel(window)) !== null)) return null;
  return <p className="limits-footnote"><PanelIcon name="info" /><span>模型上限不是额外额度：订阅内使用同时计入总周，百分比分别计算，不可相加。总周缺失时，总余量未知。</span></p>;
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
  const providers = snapshot?.machines.flatMap(machine => machine.providers) ?? [];
  const accountCount = providers.reduce((count, provider) => count + (provider.accounts.length ||
    (provider.usage.status === "ok" ? groupWindowsByAccount(provider.usage.windows).length : 0)), 0);
  return <main className="limits-panel">
    <style>{panelStyles}</style>
    <div className="limits-shell">
      <header className="limits-hero">
        <div className="limits-title-wrap">
          <div className="limits-emblem"><PanelIcon name="layers" /></div>
          <div><h1 className="limits-title">账户额度</h1><p className="limits-subtitle">订阅窗口与模型上限，一处查看。</p></div>
        </div>
        <div className="limits-overview" aria-label="额度记录概览">
          <div className="limits-stat"><span className="limits-stat-number">{snapshot ? providers.length : "—"}</span><span className="limits-stat-label">接入服务</span></div>
          <div className="limits-stat" title="按展示的账号行计数，不代表独立订阅或额度池。"><span className="limits-stat-number">{snapshot ? accountCount : "—"}</span><span className="limits-stat-label">账号记录</span></div>
        </div>
      </header>
      <div className="limits-toolbar">
        <div className="limits-segments" role="group" aria-label="额度视图">
          {(["accounts", "pool"] as const).map(value => <button key={value} type="button" aria-pressed={view === value}
            className="limits-segment"
            onClick={() => changeView(value)}><PanelIcon name={value === "pool" ? "pool" : "accounts"} />{value === "pool" ? "池" : "账号"}</button>)}
        </div>
        <div className="limits-toolbar-end">
          <div className="limits-segments" role="group" aria-label="额度显示模式">
            {(["remaining", "used"] as const).map(value => <button key={value} type="button" aria-pressed={mode === value}
              className="limits-segment" aria-label={value === "used" ? "已用（Used）" : "剩余"}
              onClick={() => changeMode(value)}>{value === "used" ? "已用" : "剩余"}</button>)}
          </div>
          <button type="button" className="limits-button"
            disabled={loading || refreshingProviderIds.size > 0} onClick={() => void load(true)}><PanelIcon name="refresh" spinning={loading} />{loading && snapshot ? "刷新中" : "刷新全部"}</button>
        </div>
      </div>
      {view === "pool" && providers.length > 0 && <p className="limits-recovery-legend"><span className="limits-recovery-key" aria-hidden="true" />{mode === "used"
        ? "已用部分按预计恢复批次分段，深色较近、浅色较远；斜纹为时间未知或待刷新。"
        : "实色为当前剩余，浅色分段为预计恢复（由近到远）；斜纹为时间未知或待刷新。"}</p>}
      {error && <p role="alert" className="limits-alert">{error}</p>}
      {!snapshot && loading && <p className="limits-loading" role="status"><PanelIcon name="refresh" spinning />正在读取账户额度…</p>}
      {snapshot && snapshot.machines.length === 0 && <p className="limits-empty">暂无可显示的账户额度。</p>}
      {snapshot?.machines.map(machine => <section key={machine.id} className="limits-source-section" aria-label={`${machine.displayName} 的账户额度`}>
        {showMachineName && <h2 className="limits-source-label">{machine.displayName}</h2>}
        {machine.status === "disconnected" && <p className="limits-empty">此机器未连接，无法读取额度。</p>}
        {machine.status === "error" && <p className="limits-alert">{machine.error ?? "读取此机器的额度失败。"}</p>}
        {machine.status === "connected" && machine.error && <p role="alert" className="limits-alert">{machine.error}</p>}
        {machine.status === "connected" && machine.providers.length === 0 && <p className="limits-empty">{machine.source === "account-pool" ? "Account Pooler 尚未添加账号。" : "没有启用的 Cliproxy 账户额度。"}</p>}
        {machine.status === "connected" && machine.providers.map(provider => <article key={provider.id} className="limits-provider" aria-label={`${provider.displayName} · ${machine.source === "account-pool" ? "Account Pooler" : "Cliproxy"}`}>
          <header className="limits-provider-head">
            <div className={`limits-provider-mark${provider.id.includes("claude") ? " limits-provider-mark--claude" : provider.id.includes("codex") ? " limits-provider-mark--codex" : ""}`}><ProviderMark id={provider.id} name={provider.displayName} /></div>
            <div className="limits-provider-title">
              <h2 className="limits-provider-name">{provider.displayName}</h2>
              <span className="limits-source-badge">{machine.source === "account-pool" ? "Account Pooler" : "Cliproxy"}</span>
              {provider.usage.status === "ok" && accountCountLabel(provider.usage.planLabel) && <span className="limits-provider-count">{accountCountLabel(provider.usage.planLabel)}</span>}
            </div>
            <div className="limits-provider-actions">
              <span className="limits-updated">{updatedLabel(provider.updatedAt)}</span>
              <button type="button" aria-label={`刷新 ${machine.source === "account-pool" ? "Account Pooler " : ""}${provider.displayName} 额度`} title="刷新此服务" className="limits-button limits-refresh" onClick={() => void refreshProvider(provider.id, machine.source ?? "cliproxy")} disabled={loading || refreshingProviderIds.has(provider.id)}>
                <PanelIcon name="refresh" spinning={refreshingProviderIds.has(provider.id)} />
              </button>
            </div>
          </header>
          <div className="limits-provider-body">{view === "pool" ? <PoolUsage provider={provider} now={now} mode={mode} /> : <AccountUsage provider={provider} now={now} mode={mode} />}</div>
          <ModelLimitNote provider={provider} />
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
