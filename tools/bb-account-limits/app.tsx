import { useCallback, useEffect, useState } from "react";
import { definePluginApp, useRpc } from "@get-bb/plugin-sdk/app";
import { accountLimitsPanelRpcContract, type AccountLimitsPanelSnapshot, type CliproxyUsageSnapshot } from "./contract.js";

function resetLabel(value: string | null): string {
  if (!value) return "重置时间未知";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "重置时间未知";
  return `重置于 ${new Intl.DateTimeFormat("zh-CN", { dateStyle: "short", timeStyle: "short" }).format(date)}`;
}

function Usage({ usage }: { usage: CliproxyUsageSnapshot["providers"][number]["usage"] }) {
  if (usage.status === "ok") {
    return <>
      {usage.planLabel && <p className="mb-3 text-sm text-muted-foreground">{usage.planLabel}</p>}
      <ul className="space-y-3">
        {usage.windows.map((window, index) => {
          const remaining = Math.max(0, Math.min(100, 100 - window.usedPercent));
          return <li key={`${window.label}-${index}`}>
            <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
              <span>{window.label}</span>
              <span className="shrink-0 text-muted-foreground">剩余 {remaining.toFixed(1)}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-label={`${window.label} 剩余额度`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={remaining}>
              <div className="h-full rounded-full bg-primary" style={{ width: `${remaining}%` }} />
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{resetLabel(window.resetsAt)}</p>
          </li>;
        })}
      </ul>
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
  const refresh = useCallback(async () => {
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
  useEffect(() => { void refresh(); }, [refresh]);

  const showMachineName = (snapshot?.machines.length ?? 0) > 1;
  return <main className="h-full overflow-auto p-4 md:p-5">
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">按上游供应商聚合的 Cliproxy 账户额度；它们不会加入模型 Provider 选择器。</p>
        <button type="button" className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-accent disabled:cursor-not-allowed disabled:opacity-60" onClick={() => void refresh()} disabled={loading}>
          {loading ? "正在刷新…" : "刷新"}
        </button>
      </div>
      {error && <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
      {!snapshot && loading && <p className="text-sm text-muted-foreground">正在读取账户额度…</p>}
      {snapshot?.machines.map(machine => <section key={machine.id} className="space-y-3" aria-label={`${machine.displayName} 的账户额度`}>
        {showMachineName && <h2 className="text-sm font-medium text-muted-foreground">{machine.displayName}</h2>}
        {machine.status === "disconnected" && <p className="rounded-md border border-border p-3 text-sm text-muted-foreground">此机器未连接，无法读取额度。</p>}
        {machine.status === "error" && <p className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{machine.error ?? "读取此机器的额度失败。"}</p>}
        {machine.status === "connected" && machine.providers.length === 0 && <p className="rounded-md border border-border p-3 text-sm text-muted-foreground">没有启用的 Cliproxy 账户额度。</p>}
        {machine.status === "connected" && machine.providers.map(provider => <article key={provider.id} className="rounded-lg border border-border bg-card p-4 shadow-sm">
          <h2 className="mb-3 font-medium">{provider.displayName}</h2>
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
