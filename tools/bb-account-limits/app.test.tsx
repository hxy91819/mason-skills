import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { JSDOM } from "jsdom";
import { act } from "react";
import { within } from "@testing-library/react";
import { installTestPluginRuntime, loadPluginApp, renderSlot } from "@get-bb/plugin-sdk/testing/app";
import type { AccountLimitsPanelSnapshot } from "./contract.js";
import { normalizeAntigravityUsage } from "./usage.js";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost" });
Object.assign(globalThis, {
  window: dom.window,
  document: dom.window.document,
  HTMLElement: dom.window.HTMLElement,
  Node: dom.window.Node,
  MutationObserver: dom.window.MutationObserver,
  IS_REACT_ACT_ENVIRONMENT: true,
});
Object.defineProperty(globalThis, "navigator", { configurable: true, value: dom.window.navigator });

test("概览统计账号记录、去掉重复身份标签，并保留多个模型各自的上限与重置时间", async t => {
  installTestPluginRuntime();
  dom.window.localStorage.clear();
  t.mock.timers.enable({ apis: ["Date"], now: new Date("2026-10-15T00:00:00Z") });
  const app = await loadPluginApp(() => import("./app.js"));
  const snapshot: AccountLimitsPanelSnapshot = { machines: [{ id: "local", source: "cliproxy", displayName: "本机", status: "connected", error: null,
    providers: [
      { id: "cliproxy-claude", displayName: "Claude", updatedAt: null, usage: { status: "ok", planLabel: null, windows: [] }, accounts: [
        { key: "work", label: "工作账号", weight: 1, usage: { status: "ok", planLabel: "工作账号", windows: [
          { label: "Weekly limit", usedPercent: 100, resetsAt: "2026-10-16T00:00:00Z" },
          { label: "Weekly scoped limit", usedPercent: 70, resetsAt: "2026-10-17T00:00:00Z" },
          { label: "Weekly Opus limit", usedPercent: 20, resetsAt: "2026-10-18T00:00:00Z" },
        ] } },
        { key: "other", label: "备用账号", weight: 1, usage: { status: "ok", planLabel: "Team Premium", windows: [] } },
        { key: "expired", label: "过期账号", weight: 1, usage: { status: "expired" } },
      ] },
      { id: "cliproxy-codex", displayName: "Codex", updatedAt: null, accounts: [], usage: { status: "ok", planLabel: null,
        windows: [{ accountLabel: "旧版账号", label: "Weekly limit", usedPercent: 25, resetsAt: null }] } },
    ] }] };
  const slot = renderSlot(app.navPanels[0]!, { subPath: "" }, { rpc: { readAccountLimits: () => snapshot } });
  t.after(() => { slot.lifecycle.unmount(); dom.window.localStorage.clear(); });
  await slot.findByText("Claude");
  assert.ok(slot.getByRole("heading", { level: 1, name: "账户额度" }));
  const overview = within(slot.getByLabelText("额度记录概览"));
  assert.ok(overview.getByText("2"));
  assert.ok(overview.getByText("4"));
  const work = within(slot.getByRole("region", { name: "工作账号 的额度" }));
  assert.equal(work.getAllByText("工作账号").length, 1);
  assert.ok(slot.getByText("Team Premium"));
  assert.ok(slot.getByText("账号登录已过期。"));
  const caps = within(work.getByRole("group", { name: "模型周上限" }));
  assert.equal(caps.getByRole("progressbar", { name: "Weekly scoped limit 剩余额度" }).getAttribute("aria-valuenow"), "30");
  assert.equal(caps.getByRole("progressbar", { name: "Weekly Opus limit 剩余额度" }).getAttribute("aria-valuenow"), "80");
  assert.ok(caps.getByText("还剩 2 天 0 小时重置"));
  assert.ok(caps.getByText("还剩 3 天 0 小时重置"));
  assert.equal(slot.getAllByText(/不可相加/).length, 1);
  assert.ok(slot.getByRole("region", { name: "旧版账号 的额度" }));
});

test("初次读取有加载状态，空数据可刷新，刷新失败保留页面并恢复操作", async t => {
  installTestPluginRuntime();
  dom.window.localStorage.clear();
  const app = await loadPluginApp(() => import("./app.js"));
  let resolveInitial!: (snapshot: AccountLimitsPanelSnapshot) => void;
  const initial = new Promise<AccountLimitsPanelSnapshot>(resolve => { resolveInitial = resolve; });
  const slot = renderSlot(app.navPanels[0]!, { subPath: "" }, { rpc: { readAccountLimits: (input: unknown) => {
    if ((input as { force?: boolean }).force) throw new Error("暂时无法刷新");
    return initial;
  } } });
  t.after(() => { slot.lifecycle.unmount(); dom.window.localStorage.clear(); });
  assert.ok(slot.getByRole("status").textContent?.includes("正在读取账户额度"));
  assert.equal((slot.getByRole("button", { name: "刷新全部" }) as HTMLButtonElement).disabled, true);
  await act(async () => { resolveInitial({ machines: [] }); });
  assert.ok(await slot.findByText("暂无可显示的账户额度。"));
  await act(async () => { slot.getByRole("button", { name: "刷新全部" }).click(); });
  assert.equal(slot.getByRole("alert").textContent, "暂时无法刷新");
  assert.ok(slot.getByText("暂无可显示的账户额度。"));
  assert.equal((slot.getByRole("button", { name: "刷新全部" }) as HTMLButtonElement).disabled, false);
  assert.deepEqual(slot.inspection.rpcCalls.map(call => call.input), [{}, { force: true }]);
});

test("Claude 将模型周上限置于总周额度之下，两种来源及账号和池视图都保持原始百分比", async t => {
  installTestPluginRuntime();
  const app = await loadPluginApp(() => import("./app.js"));
  for (const source of ["cliproxy", "account-pool"] as const) {
    dom.window.localStorage.clear();
    const windows = [
      { label: "5-hour limit", usedPercent: 0, resetsAt: null },
      { label: "Weekly limit", usedPercent: 100, resetsAt: "2026-10-20T00:00:00Z" },
      { label: source === "cliproxy" ? "Weekly scoped limit" : "Weekly · fable", usedPercent: 27, resetsAt: "2026-10-21T00:00:00Z" },
    ];
    const snapshot: AccountLimitsPanelSnapshot = { machines: [{ id: source, source, displayName: source,
      status: "connected", error: null, providers: [{
        id: source === "cliproxy" ? "cliproxy-claude" : "account-pool:claude-code", displayName: "Claude",
        updatedAt: null, usage: { status: "ok", planLabel: null, windows: [] },
        accounts: [
          { key: "regular", label: "总周已耗尽", weight: 1, usage: { status: "ok", planLabel: null, windows } },
          { key: "missing", label: "未报总周", weight: 1, usage: { status: "ok", planLabel: null, windows: windows.filter(w => w.label !== "Weekly limit") } },
        ],
      }],
    }] };
    const slot = renderSlot(app.navPanels[0]!, { subPath: "" }, { rpc: { readAccountLimits: () => snapshot } });
    t.after(() => { slot.lifecycle.unmount(); dom.window.localStorage.clear(); });
    await slot.findByText("Claude");
    const regular = within(slot.getByRole("region", { name: "总周已耗尽 的额度" }));
    const weekly = within(regular.getByRole("group", { name: "周额度" }));
    assert.ok(weekly.getByText("总周额度"));
    assert.ok(weekly.getByText("总周额度已用尽"));
    assert.equal(slot.getAllByText(/不可相加/).length, 1);
    assert.equal(weekly.getByRole("progressbar", { name: "Weekly limit 剩余额度" }).getAttribute("aria-valuenow"), "0");
    const scoped = within(weekly.getByRole("group", { name: "模型周上限" }));
    assert.ok(scoped.getByText("Fable 周上限"));
    assert.equal(scoped.getByRole("progressbar").getAttribute("aria-valuenow"), "73");
    assert.match(scoped.getByRole("progressbar").getAttribute("aria-valuetext")!, /以 Fable 自身周上限计算/);
    assert.ok(scoped.getByText(/重置/));
    const missing = within(slot.getByRole("region", { name: "未报总周 的额度" }));
    assert.ok(missing.getByText("总周额度未返回"));
    assert.equal(missing.getAllByRole("progressbar").length, 2);
    assert.ok(!missing.queryByText("总周额度已用尽"));
    await act(async () => { slot.getByRole("button", { name: "已用（Used）" }).click(); });
    assert.equal(scoped.getByRole("progressbar").getAttribute("aria-valuenow"), "27");
    assert.equal(weekly.getByRole("progressbar", { name: "Weekly limit 已用额度" }).getAttribute("aria-valuenow"), "100");
    await act(async () => { slot.getByRole("button", { name: "池" }).click(); });
    const regularPool = within(slot.getByRole("region", { name: "含全模型周额度 的池额度" }));
    const poolWeekly = within(regularPool.getByRole("group", { name: "周额度" }));
    assert.equal(slot.getAllByText(/不可相加/).length, 1);
    assert.equal(within(poolWeekly.getByRole("group", { name: "模型周上限" })).getByRole("progressbar").getAttribute("aria-valuenow"), "27");
    assert.ok(within(slot.getByRole("region", { name: "未报告全模型周额度 的池额度" })).getByText("总周额度未返回"));
    slot.lifecycle.unmount();
  }
});

test("Antigravity 面板显示实际套餐，周额度耗尽时不显示停用的 5h 余量", async t => {
  installTestPluginRuntime();
  dom.window.localStorage.clear();
  const app = await loadPluginApp(() => import("./app.js"));
  const accounts = ["Ultra", "Pro"].map(tier => {
    const usage = normalizeAntigravityUsage({ groups: [
      { displayName: "Gemini Models", buckets: [{ window: "5h", remainingFraction: 1 }] },
      { displayName: "Claude and GPT models", buckets: [
        { window: "weekly", remainingFraction: tier === "Pro" ? 0 : 1 },
        { window: "5h", remainingFraction: 1, disabled: tier === "Pro" },
      ] },
    ] }, { provider: "antigravity", authIndex: tier }, `Google AI ${tier}`);
    assert.ok(usage.supported && usage.usage.status === "ok");
    return { key: tier, label: `${tier} account`, weight: 1,
      usage: { status: "ok" as const, planLabel: usage.usage.planLabel, windows: usage.usage.windows } };
  });
  const snapshot: AccountLimitsPanelSnapshot = { machines: [{
    id: "test-host", source: "cliproxy", displayName: "本机", status: "connected", error: null,
    providers: [{ id: "cliproxy-antigravity", displayName: "Gemini · Antigravity", updatedAt: null,
      usage: { status: "ok", planLabel: null, windows: [] }, accounts }],
  }] };
  const slot = renderSlot(app.navPanels[0]!, { subPath: "" }, { rpc: { readAccountLimits: () => snapshot } });
  t.after(() => { slot.lifecycle.unmount(); dom.window.localStorage.clear(); });
  await slot.findByText("Google AI Ultra");
  await slot.findByText("Google AI Pro");
  const pro = within(slot.getByRole("region", { name: "Pro account 的额度" }));
  assert.equal(pro.queryByRole("progressbar", { name: "Claude and GPT models: 5-hour limit 剩余额度" }), null);
  assert.equal(pro.getByRole("progressbar", { name: "Claude and GPT models: Weekly limit 剩余额度" }).getAttribute("aria-valuenow"), "0");
  const ultra = within(slot.getByRole("region", { name: "Ultra account 的额度" }));
  assert.equal(ultra.getByRole("progressbar", { name: "Claude and GPT models: 5-hour limit 剩余额度" }).getAttribute("aria-valuenow"), "100");
});

test("Claude 池视图把没有全模型周额度的账号单独合并，两种来源共用分组", async t => {
  installTestPluginRuntime();
  const app = await loadPluginApp(() => import("./app.js"));
  for (const source of ["cliproxy", "account-pool"] as const) {
    dom.window.localStorage.clear();
    const account = (key: string, percent: number, weekly: boolean, weight: number) => ({
      key, label: key, weight, usage: { status: "ok" as const, planLabel: null, windows: [
        { label: "5-hour limit", usedPercent: percent, resetsAt: null },
        ...(weekly ? [{ label: "Weekly limit", usedPercent: 50, resetsAt: null }] : []),
        { label: "Weekly scoped limit", usedPercent: percent, resetsAt: null },
      ] },
    });
    const snapshot: AccountLimitsPanelSnapshot = { machines: [{
      id: source, source, displayName: source, status: "connected", error: null,
      providers: [{ id: source === "cliproxy" ? "cliproxy-claude" : "account-pool:claude-code",
        displayName: "Claude", updatedAt: null,
        usage: { status: "ok", planLabel: null, windows: [] },
        accounts: [account("有周额度 A", 20, true, 2), account("有周额度 B", 80, true, 1),
          account("未报周额度 A", 0, false, 2), account("未报周额度 B", 30, false, 1)],
      }],
    }] };
    const slot = renderSlot(app.navPanels[0]!, { subPath: "" }, { rpc: { readAccountLimits: () => snapshot } });
    t.after(() => { slot.lifecycle.unmount(); dom.window.localStorage.clear(); });
    await slot.findByText("Claude");
    await act(async () => { slot.getByRole("button", { name: "池" }).click(); });
    const regular = within(slot.getByRole("region", { name: "含全模型周额度 的池额度" }));
    const withoutWeekly = within(slot.getByRole("region", { name: "未报告全模型周额度 的池额度" }));
    assert.equal(regular.getByRole("progressbar", { name: "5h 剩余额度" }).getAttribute("aria-valuenow"), "60");
    assert.equal(withoutWeekly.getByRole("progressbar", { name: "5h 剩余额度" }).getAttribute("aria-valuenow"), "90");
    assert.equal(regular.getByRole("progressbar", { name: "7d 剩余额度" }).getAttribute("aria-valuenow"), "50");
    assert.equal(withoutWeekly.queryByRole("progressbar", { name: "7d 剩余额度" }), null);
    assert.equal(withoutWeekly.getByRole("progressbar", { name: "scoped 剩余额度" }).getAttribute("aria-valuenow"), "90");
    assert.ok(regular.getAllByText(/覆盖 2\/2/).length > 0);
    assert.ok(withoutWeekly.getAllByText(/覆盖 2\/2/).length > 0);
    await act(async () => { slot.getByRole("button", { name: "账号" }).click(); });
    assert.ok(slot.getByRole("region", { name: "未报周额度 A 的额度" }));
    slot.lifecycle.unmount();
  }
});

test("账户额度导航使用插件的额度图标", async () => {
  const app = await loadPluginApp(() => import("./app.js"));
  const panel = app.navPanels.find(panel => panel.path === "account-limits");
  const manifest = JSON.parse(await readFile(new URL("./package.json", import.meta.url), "utf8"));
  assert.equal(panel?.icon, "CircleDollarSign");
  assert.equal(panel.icon, manifest.bb.branding.icon);
});

test("账户额度页面注册为导航面板并显示独立 Cliproxy 数据", async () => {
  installTestPluginRuntime();
  const app = await loadPluginApp(() => import("./app.js"));
  assert.equal(app.navPanels.length, 1);
  assert.equal(app.navPanels[0]?.path, "account-limits");

  const snapshot: AccountLimitsPanelSnapshot = {
    machines: [{
      id: "host-local",
      displayName: "本机",
      status: "connected",
      error: null,
      providers: [{
        id: "cliproxy-claude",
        displayName: "Claude",
        updatedAt: "2026-09-09T01:30:22.000Z",
        usage: {
          status: "ok",
          planLabel: "Claude · Cliproxy · 2/2 accounts",
          windows: [
            { accountLabel: "Claude 工作账号", label: "Claude 工作账号 · Weekly limit", usedPercent: 25, resetsAt: "2026-09-15T01:30:22.000Z" },
            { accountLabel: "Claude 个人账号", label: "Claude 个人账号 · 5-hour limit", usedPercent: 50, resetsAt: "2026-09-10T01:30:22.000Z" },
          ],
        },
        accounts: [
          { key: "claude-work", label: "Claude 工作账号", weight: 1, usage: { status: "ok", planLabel: null, windows: [{ label: "Weekly limit", usedPercent: 25, resetsAt: "2026-09-15T01:30:22.000Z" }] } },
          { key: "claude-personal", label: "Claude 个人账号", weight: 1, usage: { status: "ok", planLabel: null, windows: [{ label: "5-hour limit", usedPercent: 50, resetsAt: "2026-09-10T01:30:22.000Z" }] } },
        ],
      }],
    }],
  };
  const slot = renderSlot(app.navPanels[0]!, { subPath: "" }, {
    rpc: { readAccountLimits: () => snapshot },
  });
  await slot.findByText("Claude");
  assert.ok(slot.getByText("2/2"));
  assert.ok(slot.getByRole("region", { name: "Claude 工作账号 的额度" }));
  assert.ok(slot.getByRole("region", { name: "Claude 个人账号 的额度" }));
  await act(async () => {
    slot.getByRole("button", { name: "刷新 Claude 额度" }).click();
    await new Promise(resolve => setImmediate(resolve));
  });
  assert.equal(slot.getByRole("progressbar", { name: "Weekly limit 剩余额度" }).getAttribute("aria-valuenow"), "75");
  assert.deepEqual(slot.inspection.rpcCalls, [
    { method: "readAccountLimits", input: {} },
    { method: "readAccountLimits", input: { source: "cliproxy", providerIds: ["cliproxy-claude"], force: true } },
  ]);
  await act(async () => { slot.getByRole("button", { name: "已用（Used）" }).click(); });
  const usedMeter = slot.getByRole("progressbar", { name: "Weekly limit 已用额度" });
  assert.equal(usedMeter.getAttribute("aria-valuenow"), "25");
  assert.equal((usedMeter.firstElementChild as HTMLElement).style.width, "25%");
  assert.ok(slot.getByText("25%"));
  assert.equal(slot.inspection.rpcCalls.length, 2);
  slot.lifecycle.unmount();

  const restored = renderSlot(app.navPanels[0]!, { subPath: "" }, { rpc: { readAccountLimits: () => snapshot } });
  await restored.findByText("Claude");
  assert.equal(restored.getByRole("button", { name: "已用（Used）" }).getAttribute("aria-pressed"), "true");
  assert.equal(restored.getByRole("progressbar", { name: "Weekly limit 已用额度" }).getAttribute("aria-valuenow"), "25");
  await act(async () => { restored.getByRole("button", { name: "剩余" }).click(); });
  assert.equal(restored.getByRole("progressbar", { name: "Weekly limit 剩余额度" }).getAttribute("aria-valuenow"), "75");
  restored.lifecycle.unmount();
  const remaining = renderSlot(app.navPanels[0]!, { subPath: "" }, { rpc: { readAccountLimits: () => snapshot } });
  await remaining.findByText("Claude");
  assert.equal(remaining.getByRole("button", { name: "剩余" }).getAttribute("aria-pressed"), "true");
  remaining.lifecycle.unmount();
  dom.window.localStorage.clear();
});

test("池视图把同供应商账号额度聚合成一池并记住选择", async () => {
  installTestPluginRuntime();
  const app = await loadPluginApp(() => import("./app.js"));
  const snapshot: AccountLimitsPanelSnapshot = {
    machines: [{
      id: "host-local",
      displayName: "本机",
      status: "connected",
      error: null,
      providers: [{
        id: "cliproxy-claude",
        displayName: "Claude",
        updatedAt: "2026-09-09T01:30:22.000Z",
        usage: { status: "ok", planLabel: "Claude · Cliproxy · 2/2 accounts", windows: [
          { accountLabel: "Claude 工作账号", label: "Claude 工作账号 · Weekly limit", usedPercent: 20, resetsAt: "2026-09-15T01:30:22.000Z" },
          { accountLabel: "Claude 个人账号", label: "Claude 个人账号 · Weekly limit", usedPercent: 60, resetsAt: "2026-09-12T01:30:22.000Z" },
        ] },
        accounts: [
          { key: "k1", label: "Claude 工作账号", weight: 3, usage: { status: "ok", planLabel: null, windows: [{ label: "Weekly limit", usedPercent: 20, resetsAt: "2026-09-15T01:30:22.000Z" }] } },
          { key: "k2", label: "Claude 个人账号", weight: 1, usage: { status: "ok", planLabel: null, windows: [{ label: "Weekly limit", usedPercent: 60, resetsAt: "2026-09-12T01:30:22.000Z" }] } },
        ],
      }],
    }],
  };
  const slot = renderSlot(app.navPanels[0]!, { subPath: "" }, { rpc: { readAccountLimits: () => snapshot } });
  await slot.findByText("Claude");
  assert.ok(slot.getByRole("region", { name: "Claude 工作账号 的额度" }));
  await act(async () => { slot.getByRole("button", { name: "池" }).click(); });
  // (3×20 + 1×60) / 4 = 30，剩余模式显示 70%；覆盖 2/2。
  const meter = slot.getByRole("progressbar", { name: "7d 剩余额度" });
  assert.equal(meter.getAttribute("aria-valuenow"), "70");
  assert.ok(slot.getByText(/覆盖 2\/2/));
  assert.equal(slot.queryByRole("region", { name: "Claude 工作账号 的额度" }), null);
  slot.lifecycle.unmount();

  const restored = renderSlot(app.navPanels[0]!, { subPath: "" }, { rpc: { readAccountLimits: () => snapshot } });
  await restored.findByText("Claude");
  assert.equal(restored.getByRole("button", { name: "池" }).getAttribute("aria-pressed"), "true");
  assert.ok(restored.getByRole("progressbar", { name: "7d 剩余额度" }));
  restored.lifecycle.unmount();
  dom.window.localStorage.clear();
});

test("各账号额度直接显示重置倒计时，并随时间更新而不重新查询", async t => {
  t.mock.timers.enable({ apis: ["Date", "setInterval"], now: new Date("2026-09-27T00:00:00Z") });
  installTestPluginRuntime();
  const app = await loadPluginApp(() => import("./app.js"));
  const cases = [
    ["2026-09-29T03:40:00Z", "还剩 2 天 3 小时重置"],
    ["2026-09-27T03:17:00Z", "还剩 3 小时 17 分钟重置"],
    ["2026-09-27T00:02:00Z", "还剩 2 分钟重置"],
    ["2026-09-27T00:00:30Z", "不到 1 分钟重置"],
    ["2026-09-27T00:00:00Z", "已到重置时间，待刷新"],
    [null, "重置时间未知"],
  ] as const;
  const snapshot: AccountLimitsPanelSnapshot = {
    machines: [{ id: "local", displayName: "本机", status: "connected", error: null,
      providers: [{ id: "cliproxy-claude", displayName: "Claude", updatedAt: "2026-09-27T00:00:00Z",
        usage: { status: "ok", planLabel: null, windows: cases.map(([resetsAt], index) => ({
          accountLabel: `账号 ${index}`, label: "Weekly limit", usedPercent: 25, resetsAt,
        })) },
        accounts: cases.map(([resetsAt], index) => ({
          key: `account-${index}`, label: `账号 ${index}`, weight: 1,
          usage: { status: "ok" as const, planLabel: null, windows: [{ label: "Weekly limit", usedPercent: 25, resetsAt }] },
        })),
      }],
    }],
  };
  const slot = renderSlot(app.navPanels[0]!, { subPath: "" }, { rpc: { readAccountLimits: () => snapshot } });
  t.after(() => slot.lifecycle.unmount());
  await slot.findByText("Claude");
  for (const [index, [, expected]] of cases.entries()) {
    const account = slot.getByRole("region", { name: `账号 ${index} 的额度` });
    assert.ok(account.textContent?.includes(expected), `${expected} must be visible in the account row`);
    assert.ok(!account.textContent?.includes("2026-"));
  }
  await act(async () => { t.mock.timers.tick(60_000); });
  assert.ok(slot.getByText("还剩 1 分钟重置"));
  assert.ok(slot.getByText("还剩 3 小时 16 分钟重置"));
  assert.ok(slot.getByRole("region", { name: "账号 3 的额度" }).textContent?.includes("已到重置时间，待刷新"));
  assert.equal(slot.inspection.rpcCalls.length, 1);
});

test("统一页面同时显示两种来源，共用池与账号切换，刷新 Account Pooler 保留 Cliproxy 并移除旧账号", async t => {
  dom.window.localStorage.clear();
  installTestPluginRuntime();
  const app = await loadPluginApp(() => import("./app.js"));
  const account = (key: string, percent: number) => ({ key, label: key, weight: 1,
    usage: { status: "ok" as const, planLabel: "Pro", windows: [{ label: "Weekly limit", usedPercent: percent, resetsAt: null }] } });
  const provider = (id: string, accounts: ReturnType<typeof account>[]) => ({
    id, displayName: id.endsWith("codex") ? "Codex" : "Claude", updatedAt: "2026-10-05T10:00:00Z",
    accounts, usage: { status: "ok" as const, planLabel: null, windows: accounts.flatMap(a => a.usage.windows.map(w => ({ ...w, accountLabel: a.label }))) },
  });
  const cliproxy: AccountLimitsPanelSnapshot["machines"][number] = {
    id: "local", displayName: "本机", status: "connected", error: null,
    providers: [provider("cliproxy-codex", [account("Cliproxy 账号", 20)])],
  };
  const pool: AccountLimitsPanelSnapshot["machines"][number] = {
    id: "source:account-pool", source: "account-pool", displayName: "Account Pooler", status: "connected", error: null,
    providers: [provider("account-pool:codex", [account("Pool A", 20), account("Pool B", 60)]),
      provider("account-pool:claude-code", [account("将被移除的账号", 30)])],
  };
  pool.providers[0]!.accounts.push({ key: "failed", label: "Pool 失败账号", weight: 1, usage: { status: "expired" } });
  const slot = renderSlot(app.navPanels[0]!, { subPath: "" }, { rpc: { readAccountLimits: (raw: unknown) => {
    const input = raw as { source?: string; force?: boolean };
    if (input.source === "account-pool") return { machines: [{ ...pool, providers: [provider("account-pool:codex", [account("Pool A", 80)])] }] };
    return { machines: [cliproxy, pool] };
  } } });
  t.after(() => { slot.lifecycle.unmount(); dom.window.localStorage.clear(); });
  await slot.findByRole("region", { name: "Account Pooler 的账户额度" });
  const poolSection = () => within(slot.getByRole("region", { name: "Account Pooler 的账户额度" }));
  const clipSection = () => within(slot.getByRole("region", { name: "本机 的账户额度" }));
  assert.ok(poolSection().getByRole("region", { name: "Pool A 的额度" }));
  assert.ok(poolSection().getByRole("region", { name: "Pool B 的额度" }));
  assert.ok(poolSection().getByText("账号登录已过期。"));
  assert.ok(clipSection().getByText("Cliproxy"));
  await act(async () => { slot.getByRole("button", { name: "池" }).click(); });
  assert.equal(poolSection().getAllByRole("progressbar")[0]!.getAttribute("aria-valuenow"), "60");
  assert.equal(clipSection().getByRole("progressbar").getAttribute("aria-valuenow"), "80");
  assert.ok(poolSection().getByText(/覆盖 2\/3/));
  assert.equal(poolSection().queryByRole("region", { name: "Pool A 的额度" }), null);
  await act(async () => { slot.getByRole("button", { name: "已用（Used）" }).click(); });
  assert.equal(poolSection().getAllByRole("progressbar")[0]!.getAttribute("aria-valuenow"), "40");
  await act(async () => {
    slot.getByRole("button", { name: "刷新 Account Pooler Codex 额度" }).click();
    await new Promise(resolve => setImmediate(resolve));
  });
  assert.equal(poolSection().getByRole("progressbar").getAttribute("aria-valuenow"), "80");
  assert.equal(clipSection().getByRole("progressbar").getAttribute("aria-valuenow"), "20");
  assert.equal(poolSection().queryByRole("button", { name: "刷新 Account Pooler Claude 额度" }), null);
  assert.deepEqual(slot.inspection.rpcCalls, [
    { method: "readAccountLimits", input: {} },
    { method: "readAccountLimits", input: { source: "account-pool", providerIds: ["account-pool:codex"], force: true } },
  ]);
  await act(async () => { slot.getByRole("button", { name: "账号" }).click(); });
  assert.ok(poolSection().getByRole("region", { name: "Pool A 的额度" }));
  assert.equal(poolSection().queryByRole("region", { name: "Pool B 的额度" }), null);
});

test("Gemini 已缓存的逆序窗口在账号和池视图都显示 5h 再 7d，并保留模型分组", async t => {
  dom.window.localStorage.clear();
  installTestPluginRuntime();
  const app = await loadPluginApp(() => import("./app.js"));
  const windows = [
    { label: "Gemini Models: Weekly limit", usedPercent: 21, resetsAt: null },
    { label: "Gemini Models: 5-hour limit", usedPercent: 16, resetsAt: null },
    { label: "Claude and GPT models: Weekly limit", usedPercent: 31, resetsAt: null },
    { label: "Claude and GPT models: 5-hour limit", usedPercent: 26, resetsAt: null },
  ];
  const snapshot: AccountLimitsPanelSnapshot = { machines: [{
    id: "local", displayName: "本机", status: "connected", error: null,
    providers: [{ id: "cliproxy-antigravity", displayName: "Gemini", updatedAt: "2026-10-05T10:00:00Z",
      accounts: [{ key: "gem", label: "Gemini 账号", weight: 1, usage: { status: "ok", planLabel: null, windows } }],
      usage: { status: "ok", planLabel: null, windows: windows.map(window => ({ ...window, accountLabel: "Gemini 账号" })) },
    }],
  }] };
  const slot = renderSlot(app.navPanels[0]!, { subPath: "" }, { rpc: { readAccountLimits: () => snapshot } });
  t.after(() => { slot.lifecycle.unmount(); dom.window.localStorage.clear(); });
  await slot.findByText("Gemini 账号");
  assert.deepEqual(slot.getAllByRole("progressbar").map(meter => meter.getAttribute("aria-label")), [
    "Gemini Models: 5-hour limit 剩余额度", "Gemini Models: Weekly limit 剩余额度",
    "Claude and GPT models: 5-hour limit 剩余额度", "Claude and GPT models: Weekly limit 剩余额度",
  ]);
  await act(async () => { slot.getByRole("button", { name: "池" }).click(); });
  assert.deepEqual(slot.getAllByRole("progressbar").map(meter => meter.getAttribute("aria-label")), [
    "Gem 5h 剩余额度", "Gem 7d 剩余额度", "C/G 5h 剩余额度", "C/G 7d 剩余额度",
  ]);
  assert.deepEqual(windows.map(window => window.usedPercent), [21, 16, 31, 26]);
});
