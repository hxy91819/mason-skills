import assert from "node:assert/strict";
import { test } from "node:test";
import { buildPoolRecovery } from "./pool-recovery.js";
import { aggregateCliproxyPool } from "./pool.js";
import type { CliproxyAccountUsageEntry } from "./contract.js";

const now = Date.parse("2026-10-15T00:00:00Z");
const at = (hours: number) => new Date(now + hours * 3_600_000).toISOString();
function account(key: string, usedPercent: number, resetsAt: string | null, weight = 1): CliproxyAccountUsageEntry {
  return { key, label: key, weight, usage: { status: "ok", planLabel: null,
    windows: [{ label: "Weekly limit", usedPercent, resetsAt }] } };
}

test("恢复批次按时间排序，使用与池均值相同的加权百分点并给出累计余量", () => {
  const accounts = [account("later", 60, at(3)), account("soon", 30, at(1), 2)];
  const forecast = buildPoolRecovery(accounts, "7d", now)!;
  assert.deepEqual(forecast, { usedPercent: 40, remainingPercent: 60, unknownPercent: 0, overduePercent: 0, steps: [
    { resetsAt: at(1), gainPercent: 20, remainingPercent: 80, accounts: 1 },
    { resetsAt: at(3), gainPercent: 20, remainingPercent: 100, accounts: 1 },
  ] });
  const pool = aggregateCliproxyPool(accounts);
  assert.ok(pool.status === "ok");
  assert.equal(pool.windows[0]!.usedPercent, forecast.usedPercent);
});

test("同一时刻合为一批，零消耗账号保留在窗口分母，不产生虚构恢复量", () => {
  const accounts = [account("a", 60, at(1)), account("b", 20, "2026-10-15T09:00:00+08:00"), account("unused", 0, at(2), 2)];
  const forecast = buildPoolRecovery(accounts, "7d", now)!;
  assert.equal(forecast.remainingPercent, 80);
  assert.deepEqual(forecast.steps, [{ resetsAt: at(1), gainPercent: 20, remainingPercent: 100, accounts: 2 }]);
  assert.deepEqual(buildPoolRecovery([account("unused", 0, at(1))], "7d", now)?.steps, []);
});

test("未知与已到期测量单独保留，失败或缺窗口账号不稀释预测，不修改原快照", () => {
  const accounts = [account("future", 40, at(1)), account("past", 40, at(-1)), account("unknown", 40, null), account("invalid", 40, "invalid")];
  accounts.push({ key: "failed", label: "failed", weight: 100, usage: { status: "expired" } });
  accounts.push({ key: "other-window", label: "other", weight: 100, usage: { status: "ok", planLabel: null,
    windows: [{ label: "5-hour limit", usedPercent: 100, resetsAt: at(1) }] } });
  const before = JSON.stringify(accounts);
  const forecast = buildPoolRecovery(accounts, "7d", now)!;
  assert.equal(forecast.remainingPercent, 60);
  assert.equal(forecast.unknownPercent, 20);
  assert.equal(forecast.overduePercent, 10);
  assert.deepEqual(forecast.steps, [{ resetsAt: at(1), gainPercent: 10, remainingPercent: 70, accounts: 1 }]);
  assert.equal(JSON.stringify(accounts), before);
  assert.equal(buildPoolRecovery([], "7d", now), null);
});

test("同名但不同模型身份的窗口分开预测，同一账号重复窗口只采用第一条", () => {
  const entry = account("a", 0, null);
  assert.ok(entry.usage.status === "ok");
  entry.usage.windows = [
    { id: "model-a", label: "Weekly limit", usedPercent: 80, resetsAt: at(1) },
    { id: "model-b", label: "Weekly limit", usedPercent: 20, resetsAt: at(2) },
    { id: "model-a", label: "Weekly limit", usedPercent: 100, resetsAt: at(9) },
  ];
  assert.equal(buildPoolRecovery([entry], "model-a", now)?.steps[0]?.gainPercent, 80);
  assert.equal(buildPoolRecovery([entry], "model-b", now)?.steps[0]?.gainPercent, 20);
  assert.equal(buildPoolRecovery([entry], "7d", now), null);
});

test("时钟越过重置时间只标记待刷新，当前余量不会自动增加，也不重复推算下一轮", () => {
  const accounts = [account("a", 100, at(1)), account("b", 40, at(2))];
  const initial = buildPoolRecovery(accounts, "7d", now)!;
  assert.equal(initial.remainingPercent, 30);
  const later = buildPoolRecovery(accounts, "7d", now + 90 * 60_000)!;
  assert.equal(later.remainingPercent, 30);
  assert.equal(later.overduePercent, 50);
  assert.deepEqual(later.steps, [{ resetsAt: at(2), gainPercent: 20, remainingPercent: 50, accounts: 1 }]);
});
