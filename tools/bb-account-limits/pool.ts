import type { CliproxyAccountUsageEntry } from "./contract.js";

/**
 * Cliproxy 池级聚合：把同一供应商下全部账号的额度窗口合成一个池。
 * server（Provider Usage 来源）和 app（“账户额度”池视图）共用，保持纯函数、不引 Node API。
 */

export type CliproxyWindowKind = "five-hour" | "daily" | "weekly" | "custom";

export interface CliproxyWindowIdentity {
  /** 归一化后的窗口身份（去掉账号/分组前缀后的窗口种类），池聚合按它分组。 */
  id: string;
  kind: CliproxyWindowKind;
  /** 短标签；官方 Usage 卡片标签列很窄，非标准窗口必须自带短名。 */
  label: string;
}

/** 账号窗口里 "<分组>: <窗口>" 的分组名缩写，例如 Antigravity 的 Gemini/Claude+GPT 桶。 */
const shortGroupPrefixes: Record<string, string> = {
  "gemini models": "Gem",
  "claude and gpt models": "C/G",
};

function normalizeBaseWindow(label: string): CliproxyWindowIdentity {
  const text = label.trim().toLowerCase();
  if (text === "5-hour limit" || text === "five-hour limit" || text === "5h" || text === "session") return { id: "5h", kind: "five-hour", label: "5h" };
  if (text === "weekly limit" || text === "7d") return { id: "7d", kind: "weekly", label: "7d" };
  if (text === "daily limit") return { id: "1d", kind: "daily", label: "1d" };
  if (text === "weekly scoped limit") return { id: "scoped", kind: "custom", label: "scoped" };
  if (text === "weekly opus limit") return { id: "opus-7d", kind: "custom", label: "Opus 7d" };
  if (text === "monthly limit") return { id: "30d", kind: "custom", label: "30d" };
  if (text === "current limit") return { id: "current", kind: "custom", label: "cur" };
  if (text === "secondary limit") return { id: "secondary", kind: "custom", label: "sec" };
  if (text === "current period") return { id: "period", kind: "custom", label: "period" };
  const minutes = /^(\d+(?:\.\d+)?)[- ]minute limit$/u.exec(text);
  if (minutes) return { id: `${minutes[1]}m`, kind: "custom", label: `${minutes[1]}m` };
  return { id: `custom:${text}`, kind: "custom", label: label.trim() };
}

/**
 * 归一化窗口身份："<分组>: <窗口>" 拆出分组前缀并缩写；无前缀的标准窗口保留真实 kind
 * （官方卡片会把 Five-hour/Weekly limit 缩写回 5h/7d），其余一律 custom + 短标签。
 */
export function normalizeCliproxyWindow(label: string): CliproxyWindowIdentity {
  const sep = label.indexOf(": ");
  if (sep < 0) return normalizeBaseWindow(label);
  const prefix = label.slice(0, sep).trim();
  const base = normalizeBaseWindow(label.slice(sep + 2));
  const short = shortGroupPrefixes[prefix.toLowerCase()] ?? prefix;
  return { id: `${short} ${base.id}`, kind: "custom", label: `${short} ${base.label}` };
}

export interface PoolWindow {
  id: string;
  kind: CliproxyWindowKind;
  label: string;
  /** Σ(weight × usedPercent) / Σ weight，只在报出该窗口的 ok 账号上加权。 */
  usedPercent: number;
  /** 该窗口内所有账号中最早的重置时间；都没有则为 null。 */
  resetsAt: string | null;
  /** 覆盖率分子：报出该窗口的账号数（分母是结果上的 totalAccounts）。 */
  accounts: number;
  /** 该窗口已用 ≥100% 的账号数。 */
  exhausted: number;
}

export type CliproxyPoolUsage =
  | { status: "ok"; okAccounts: number; totalAccounts: number; windows: PoolWindow[] }
  | { status: "error"; message: string };

/** 只统计 status=ok 的账号；没有任何 ok 账号时返回 error，绝不显示 0 用量。 */
export function aggregateCliproxyPool(accounts: readonly CliproxyAccountUsageEntry[]): CliproxyPoolUsage {
  if (accounts.length === 0) return { status: "error", message: "该供应商没有可用的账号。" };
  const okAccounts = accounts.filter(account => account.usage.status === "ok");
  if (okAccounts.length === 0) return { status: "error", message: "该供应商的全部账号额度查询均失败。" };
  const groups = new Map<string, { identity: CliproxyWindowIdentity; weight: number; weighted: number; resetsAtMs: number | null; accounts: number; exhausted: number }>();
  for (const account of okAccounts) {
    if (account.usage.status !== "ok") continue;
    const weight = Number.isFinite(account.weight) && account.weight > 0 ? account.weight : 1;
    const seen = new Set<string>();
    for (const window of account.usage.windows) {
      const normalized = normalizeCliproxyWindow(window.label);
      const identity = { ...normalized, id: window.id ?? normalized.id };
      if (seen.has(identity.id)) continue;
      seen.add(identity.id);
      let group = groups.get(identity.id);
      if (!group) {
        group = { identity, weight: 0, weighted: 0, resetsAtMs: null, accounts: 0, exhausted: 0 };
        groups.set(identity.id, group);
      }
      group.weight += weight;
      group.weighted += weight * window.usedPercent;
      group.accounts += 1;
      if (window.usedPercent >= 100) group.exhausted += 1;
      if (window.resetsAt !== null) {
        const time = Date.parse(window.resetsAt);
        if (Number.isFinite(time) && (group.resetsAtMs === null || time < group.resetsAtMs)) group.resetsAtMs = time;
      }
    }
  }
  return {
    status: "ok",
    okAccounts: okAccounts.length,
    totalAccounts: accounts.length,
    windows: [...groups.values()].map(group => ({
      id: group.identity.id,
      kind: group.identity.kind,
      label: group.identity.label,
      usedPercent: group.weighted / group.weight,
      resetsAt: group.resetsAtMs === null ? null : new Date(group.resetsAtMs).toISOString(),
      accounts: group.accounts,
      exhausted: group.exhausted,
    })),
  };
}
