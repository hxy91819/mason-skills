import type { CliproxyAccountUsageEntry } from "./contract.js";
import { normalizeCliproxyWindow } from "./pool.js";

const HOUR = 3_600_000;
const WEEK = 168 * HOUR;

export interface WeeklyPace {
  level: "generous" | "normal" | "conserve" | "exhausted" | "blocked" | "unknown";
  label: string;
  reason: string;
  /** 当前余量和均匀使用基准，均以该周窗口的完整容量为分母。 */
  remainingPercent?: number;
  expectedPercent?: number;
  /** 临期宽裕账号只构成优先使用提示，不提升整个池的评级。 */
  expiringAccounts: string[];
  expiringRemainingPercent: number;
}

/** 只评估完整周窗口；Fable、Opus 等自身上限不当作总周容量。 */
export function isWeeklyBudget(label: string): boolean {
  const id = normalizeCliproxyWindow(label).id;
  return id === "7d" || /^(Gem|C\/G) 7d$/u.test(id)
    || /^(Gem|C\/G) 7d$/u.test(label);
}

const number = (value: number) => value > 0 && value < 0.1 ? "<0.1"
  : new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 1 }).format(value);
const unknown = (reason: string): WeeklyPace => ({ level: "unknown", label: "暂不判断", reason,
  expiringAccounts: [], expiringRemainingPercent: 0 });

/**
 * 以周均匀分配为参照的建议，不是对真实消耗速度的预测。
 * 池先分别计算每个账号的剩余时间，再按原有容量权重加总；不取最早重置时间代表全池。
 * 不跨来源/分池/模型窗口，不发请求、不把未来重置当作已恢复。
 */
export function buildWeeklyPace(
  accounts: readonly CliproxyAccountUsageEntry[], windowId: string, now: number,
  fallbackUpdatedAt: string | null = null,
): WeeklyPace {
  const entries: { label: string; weight: number; remaining: number; expected: number; hours: number; blocked: boolean }[] = [];
  for (const account of accounts) {
    if (account.usage.status !== "ok") return unknown("部分账号额度查询失败，无法判断整池使用节奏。");
    const window = account.usage.windows.find(window => (window.id ?? normalizeCliproxyWindow(window.label).id) === windowId);
    if (!window) return unknown("部分账号未报告该周窗口，无法判断整池使用节奏。");
    if (!isWeeklyBudget(window.label)) return unknown("该窗口不是完整周额度，无法据此判断周使用节奏。");
    const resetsAt = window.resetsAt ? Date.parse(window.resetsAt) : NaN;
    if (!Number.isFinite(resetsAt)) return unknown("周额度的重置时间未知。");
    if (resetsAt <= now) return unknown("已到重置时间，待刷新确认周余量。");
    if (resetsAt - now > WEEK) return unknown("重置时间超过一周，无法按七天周期判断。");
    const updatedAt = account.updatedAt === undefined ? fallbackUpdatedAt : account.updatedAt;
    const observed = updatedAt ? Date.parse(updatedAt) : NaN;
    if (!Number.isFinite(observed)) return unknown("测量时间未知，刷新后再判断周使用节奏。");
    if (now - observed > HOUR || observed - now > 5 * 60_000) return unknown("额度测量已过时或时间异常，刷新后再判断。");
    const shortId = normalizeCliproxyWindow(window.label).id.replace(/7d$/u, "5h");
    const shortWindow = account.usage.windows.find(candidate => normalizeCliproxyWindow(candidate.label).id === shortId);
    entries.push({ label: account.label, weight: Number.isFinite(account.weight) && account.weight > 0 ? account.weight : 1,
      remaining: Math.max(0, Math.min(100, 100 - window.usedPercent)),
      expected: 100 * (resetsAt - now) / WEEK, hours: (resetsAt - now) / HOUR,
      blocked: shortWindow !== undefined && shortWindow.usedPercent >= 100 });
  }
  if (entries.length === 0) return unknown("没有可判断的周额度。");
  const totalWeight = entries.reduce((sum, entry) => sum + entry.weight, 0);
  const mean = (read: (entry: typeof entries[number]) => number) => entries.reduce((sum, entry) => sum + entry.weight * read(entry), 0) / totalWeight;
  const remainingPercent = mean(entry => entry.remaining);
  const expectedPercent = mean(entry => entry.expected);
  // 最后六小时不放大为无限倍率；百分点差另设门槛，避免少量余量也被判定为宽裕。
  const ratio = remainingPercent / Math.max(expectedPercent, 100 * 6 * HOUR / WEEK);
  const surplus = remainingPercent - expectedPercent;
  const expiring = entries.filter(entry => !entry.blocked && entry.hours <= 24 && entry.remaining >= 20
    && entry.remaining - entry.expected >= 15
    && entry.remaining / Math.max(entry.expected, 100 * 6 * HOUR / WEEK) >= 1.5);
  const common = { remainingPercent, expectedPercent, expiringAccounts: expiring.map(entry => entry.label),
    expiringRemainingPercent: expiring.reduce((sum, entry) => sum + entry.weight * entry.remaining, 0) / totalWeight };
  let level: WeeklyPace["level"] = "normal";
  let label = "正常用";
  let reason = `周余量 ${number(remainingPercent)}%，均匀使用基准约 ${number(expectedPercent)}%，可按正常节奏使用。`;
  if (remainingPercent <= 0) {
    level = "exhausted"; label = "周额已用尽"; reason = "当前周额度已用尽，等待实际重置。";
  } else if ((ratio <= 0.7 && surplus <= -10) || (remainingPercent <= 10 && mean(entry => entry.hours) >= 24)) {
    level = "conserve"; label = "节约用";
    reason = `周余量 ${number(remainingPercent)}%，低于均匀使用基准约 ${number(expectedPercent)}%，建议放慢消耗。`;
  } else if (ratio >= 1.5 && surplus >= 15) {
    level = "generous"; label = "可多用";
    reason = `周余量 ${number(remainingPercent)}%，高于均匀使用基准约 ${number(expectedPercent)}%，可增加使用。`;
  }
  if (entries.length > 1 && expiring.length > 0) reason += ` 优先使用 ${expiring.map(entry => entry.label).join("、")}：24 小时内重置，其当前余量合计占池 ${number(common.expiringRemainingPercent)} 个百分点。`;
  if (remainingPercent > 0 && entries.every(entry => entry.remaining <= 0 || entry.blocked)) {
    reason = `周额度判断为“${label}”，但有周余量的账号目前都已耗尽对应的 5h 窗口，短期恢复前无法按此节奏使用。 ${reason}`;
    level = "blocked"; label = "短期受限";
  }
  reason += " 按一周均匀分配估算；短期窗口和模型自身上限仍单独约束。";
  return { ...common, level, label, reason };
}
