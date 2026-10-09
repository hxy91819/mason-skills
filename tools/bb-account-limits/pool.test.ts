import assert from "node:assert/strict";
import { test } from "node:test";
import { aggregateCliproxyPool, normalizeCliproxyWindow } from "./pool.js";
import type { CliproxyAccountUsageEntry } from "./contract.js";

function account(key: string, weight: number, windows: Array<{ label: string; usedPercent: number; resetsAt: string | null }>): CliproxyAccountUsageEntry {
  return { key, label: key, weight, usage: { status: "ok", planLabel: null, windows } };
}

function failing(key: string): CliproxyAccountUsageEntry {
  return { key, label: key, weight: 1, usage: { status: "error", message: "query failed" } };
}

test("池聚合按权重合成已用百分比并保留最早重置时间", () => {
  const pool = aggregateCliproxyPool([
    account("a", 2, [{ label: "5-hour limit", usedPercent: 30, resetsAt: "2026-10-05T08:00:00Z" }]),
    account("b", 1, [{ label: "5-hour limit", usedPercent: 60, resetsAt: "2026-10-05T06:00:00Z" }]),
  ]);
  assert.equal(pool.status, "ok");
  if (pool.status !== "ok") return;
  assert.deepEqual(pool.windows, [{
    id: "5h", kind: "five-hour", label: "5h",
    usedPercent: 40, resetsAt: "2026-10-05T06:00:00.000Z",
    accounts: 2, exhausted: 0,
  }]);
});

test("缺窗口的账号不计入该窗口的权重和覆盖率", () => {
  const pool = aggregateCliproxyPool([
    account("a", 1, [
      { label: "5-hour limit", usedPercent: 10, resetsAt: null },
      { label: "Weekly limit", usedPercent: 50, resetsAt: null },
    ]),
    account("b", 3, [{ label: "5-hour limit", usedPercent: 70, resetsAt: null }]),
  ]);
  assert.equal(pool.status, "ok");
  if (pool.status !== "ok") return;
  const fiveHour = pool.windows.find(window => window.id === "5h");
  const weekly = pool.windows.find(window => window.id === "7d");
  assert.equal(fiveHour?.usedPercent, 55); // (1×10 + 3×70) / 4
  assert.equal(fiveHour?.accounts, 2);
  assert.equal(weekly?.usedPercent, 50);
  assert.equal(weekly?.accounts, 1);
});

test("失败账号不进入池统计，耗尽账号单独计数", () => {
  const pool = aggregateCliproxyPool([
    account("a", 1, [{ label: "Weekly limit", usedPercent: 100, resetsAt: null }]),
    account("b", 1, [{ label: "Weekly limit", usedPercent: 40, resetsAt: null }]),
    failing("c"),
  ]);
  assert.equal(pool.status, "ok");
  if (pool.status !== "ok") return;
  assert.equal(pool.okAccounts, 2);
  assert.equal(pool.totalAccounts, 3);
  const weekly = pool.windows.find(window => window.id === "7d");
  assert.equal(weekly?.usedPercent, 70);
  assert.equal(weekly?.accounts, 2);
  assert.equal(weekly?.exhausted, 1);
});

test("没有任何 ok 账号或空池时报错，绝不显示 0 用量", () => {
  const empty = aggregateCliproxyPool([]);
  assert.equal(empty.status, "error");
  const allFailed = aggregateCliproxyPool([failing("a"), failing("b")]);
  assert.equal(allFailed.status, "error");
});

test("窗口归一化覆盖分组前缀与非标准窗口", () => {
  assert.deepEqual(normalizeCliproxyWindow("5-hour limit"), { id: "5h", kind: "five-hour", label: "5h" });
  assert.deepEqual(normalizeCliproxyWindow("Weekly limit"), { id: "7d", kind: "weekly", label: "7d" });
  assert.deepEqual(normalizeCliproxyWindow("Weekly scoped limit"), { id: "scoped", kind: "custom", label: "scoped" });
  assert.deepEqual(normalizeCliproxyWindow("Gemini Models: 5-hour limit"), { id: "Gem 5h", kind: "custom", label: "Gem 5h" });
  assert.deepEqual(normalizeCliproxyWindow("Gemini Models: Weekly limit"), { id: "Gem 7d", kind: "custom", label: "Gem 7d" });
  assert.deepEqual(normalizeCliproxyWindow("Claude and GPT models: 5-hour limit"), { id: "C/G 5h", kind: "custom", label: "C/G 5h" });
  assert.deepEqual(normalizeCliproxyWindow("Claude and GPT models: Weekly limit"), { id: "C/G 7d", kind: "custom", label: "C/G 7d" });
});
