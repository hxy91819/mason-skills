import type { CliproxyAccountUsageEntry } from "./contract.js";
import { normalizeCliproxyWindow } from "./pool.js";

export interface PoolRecoveryStep {
  resetsAt: string;
  /** 对整个窗口池的增量，单位是百分点，不是当前余量的百分比。 */
  gainPercent: number;
  remainingPercent: number;
  accounts: number;
}

export interface PoolRecovery {
  usedPercent: number;
  remainingPercent: number;
  steps: PoolRecoveryStep[];
  unknownPercent: number;
  overduePercent: number;
}

/**
 * 当前测量在各账号下一次重置时归零的投影，不预测后续消耗或下一轮重置。
 * 与池均值保持同一窗口身份、首条去重、健康账号及权重分母；不修改池或 RPC。
 */
export function buildPoolRecovery(
  accounts: readonly CliproxyAccountUsageEntry[], windowId: string, now: number,
): PoolRecovery | null {
  const entries = accounts.flatMap(account => {
    if (account.usage.status !== "ok") return [];
    const window = account.usage.windows.find(window => (window.id ?? normalizeCliproxyWindow(window.label).id) === windowId);
    if (!window) return [];
    return [{ window, weight: Number.isFinite(account.weight) && account.weight > 0 ? account.weight : 1 }];
  });
  if (entries.length === 0) return null;
  const totalWeight = entries.reduce((sum, entry) => sum + entry.weight, 0);
  const usedPercent = entries.reduce((sum, entry) => sum + entry.weight * entry.window.usedPercent, 0) / totalWeight;
  const remainingPercent = Math.max(0, Math.min(100, 100 - usedPercent));
  let unknownPercent = 0;
  let overduePercent = 0;
  const groups = new Map<number, { gainPercent: number; accounts: number }>();
  for (const { window, weight } of entries) {
    const gainPercent = weight * window.usedPercent / totalWeight;
    if (gainPercent <= 0) continue;
    const resetsAt = window.resetsAt === null ? NaN : Date.parse(window.resetsAt);
    if (!Number.isFinite(resetsAt)) {
      unknownPercent += gainPercent;
    } else if (resetsAt <= now) {
      // 过期的测量还未刷新，不能将预计重置当成已恢复。
      overduePercent += gainPercent;
    } else {
      const group = groups.get(resetsAt) ?? { gainPercent: 0, accounts: 0 };
      group.gainPercent += gainPercent;
      group.accounts += 1;
      groups.set(resetsAt, group);
    }
  }
  let projected = remainingPercent;
  const steps = [...groups].sort(([a], [b]) => a - b).map(([time, group]) => {
    projected = Math.min(100, projected + group.gainPercent);
    return { resetsAt: new Date(time).toISOString(), ...group, remainingPercent: projected };
  });
  return { usedPercent, remainingPercent, steps, unknownPercent, overduePercent };
}
