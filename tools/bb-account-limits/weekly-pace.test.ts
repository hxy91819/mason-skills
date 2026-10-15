import assert from "node:assert/strict";
import { test } from "node:test";
import type { CliproxyAccountUsageEntry } from "./contract.js";
import { buildWeeklyPace, isWeeklyBudget } from "./weekly-pace.js";

const now = Date.parse("2026-10-15T00:00:00Z");
const at = (hours: number) => new Date(now + hours * 3_600_000).toISOString();
function account(label: string, remaining: number, hours: number, weight = 1): CliproxyAccountUsageEntry {
  return { key: label, label, weight, updatedAt: at(0), usage: { status: "ok", planLabel: null,
    windows: [{ label: "Weekly limit", usedPercent: 100 - remaining, resetsAt: at(hours) }] } };
}

test("按剩余周时间判断宽裕、正常与紧张，不因绝对余量或即将重置单独提升建议", () => {
  for (const [remaining, hours, level] of [
    [50, 24, "generous"], [80, 144, "normal"], [20, 144, "conserve"],
    [100, 168, "normal"], [60, 72, "normal"], [1, 0.1, "normal"],
    [0, 24, "exhausted"], [8, 24, "conserve"], [8, 6, "normal"],
  ] as const) assert.equal(buildWeeklyPace([account("a", remaining, hours)], "7d", now).level, level, `${remaining}% / ${hours}h`);
});

test("双门槛留出正常区间，少量余量在临近重置时也不建议敞开使用", () => {
  assert.equal(buildWeeklyPace([account("a", 20, 24)], "7d", now).level, "normal");
  assert.equal(buildWeeklyPace([account("a", 30, 48)], "7d", now).level, "normal");
  assert.equal(buildWeeklyPace([account("a", 40, 24)], "7d", now).level, "generous");
});

test("池使用各账号的周时间和容量权重，单个临期账号不让长期紧张的整池变宽裕", () => {
  const accounts = [account("soon", 80, 1), account("later", 5, 144, 9)];
  const before = JSON.stringify(accounts);
  const result = buildWeeklyPace(accounts, "7d", now);
  assert.equal(result.level, "conserve");
  assert.equal(result.remainingPercent, 12.5);
  assert.deepEqual(result.expiringAccounts, ["soon"]);
  assert.equal(result.expiringRemainingPercent, 8);
  assert.match(result.reason, /优先使用 soon/u);
  assert.equal(JSON.stringify(accounts), before);
  // 相同的平均余量和最早重置，其他账号重置更近时应有不同建议。
  assert.equal(buildWeeklyPace([accounts[0]!, account("later", 5, 1, 9)], "7d", now).level, "normal");
});

test("不把缺测、过期或未知时间当作正常余量；过时的临期账号不产生可多用提示", () => {
  const stale = { ...account("stale", 80, 1), updatedAt: at(-2) };
  const missingTime = { ...account("unknown", 80, 1), updatedAt: null };
  const missingReset = account("unknown-reset", 80, 1);
  if (missingReset.usage.status === "ok") missingReset.usage.windows[0]!.resetsAt = null;
  const failed: CliproxyAccountUsageEntry = { key: "bad", label: "bad", weight: 1, usage: { status: "error", message: "offline" } };
  for (const accounts of [[], [stale], [missingTime], [missingReset], [account("overdue", 80, -1)],
    [account("outside-week", 80, 169)], [account("ok", 80, 1), failed]]) {
    const result = buildWeeklyPace(accounts, "7d", now, at(0));
    assert.equal(result.level, "unknown");
    assert.deepEqual(result.expiringAccounts, []);
  }
  const legacy = { ...account("legacy", 50, 24), updatedAt: undefined };
  assert.equal(buildWeeklyPace([legacy], "7d", now, at(0)).level, "generous");
  assert.equal(buildWeeklyPace([missingTime], "7d", now, at(0)).level, "unknown");
});

test("窗口按真实身份匹配并首条去重，5h 与模型上限不稀释总周或参与总周判断", () => {
  const entry = account("a", 50, 24);
  assert.ok(entry.usage.status === "ok");
  entry.usage.windows = [
    { id: "weekly-all", label: "Weekly limit", usedPercent: 50, resetsAt: at(24) },
    { id: "weekly-all", label: "Weekly limit", usedPercent: 100, resetsAt: at(144) },
    { id: "fable", label: "Weekly scoped limit", usedPercent: 100, resetsAt: at(144) },
    { label: "5-hour limit", usedPercent: 90, resetsAt: at(1) },
  ];
  assert.equal(buildWeeklyPace([entry], "weekly-all", now).level, "generous");
  assert.equal(buildWeeklyPace([entry], "7d", now).level, "unknown");
  assert.equal(buildWeeklyPace([entry], "fable", now).level, "unknown");
  for (const label of ["Weekly limit", "7d", "Gemini Models: Weekly limit", "Claude and GPT models: Weekly limit", "Gem 7d", "C/G 7d"]) assert.ok(isWeeklyBudget(label), label);
  for (const label of ["5-hour limit", "Weekly scoped limit", "Weekly Opus limit", "Opus 7d", "Monthly limit"]) assert.equal(isWeeklyBudget(label), false, label);
});

test("5h 只约束当下是否能使用，不改变周节奏；分组的短限不会阻断另一模型组", () => {
  const entry = account("a", 50, 24);
  assert.ok(entry.usage.status === "ok");
  entry.usage.windows.push({ label: "5-hour limit", usedPercent: 100, resetsAt: at(1) });
  const blocked = buildWeeklyPace([entry], "7d", now);
  assert.equal(blocked.level, "blocked");
  assert.deepEqual(blocked.expiringAccounts, []);
  assert.match(blocked.reason, /周额度判断为“可多用”/u);
  assert.equal(buildWeeklyPace([entry, account("b", 50, 24)], "7d", now).level, "generous");
  entry.usage.windows[0]!.label = "Gemini Models: Weekly limit";
  entry.usage.windows[1]!.label = "Claude and GPT models: 5-hour limit";
  assert.equal(buildWeeklyPace([entry], "Gem 7d", now).level, "generous");
});

test("时钟越过重置时间只等待刷新，不能推断新周期已经恢复可用", () => {
  const entry = account("a", 50, 0.5);
  assert.equal(buildWeeklyPace([entry], "7d", now).level, "generous");
  const result = buildWeeklyPace([entry], "7d", now + 3_600_000);
  assert.equal(result.level, "unknown");
  assert.match(result.reason, /待刷新/u);
});
