import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";
import { act } from "react";
import { installTestPluginRuntime, loadPluginApp, renderSlot } from "@get-bb/plugin-sdk/testing/app";
import type { AccountLimitsPanelSnapshot } from "./contract.js";

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
      }],
    }],
  };
  const slot = renderSlot(app.navPanels[0]!, { subPath: "" }, {
    rpc: { readCliproxyUsage: () => snapshot },
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
    { method: "readCliproxyUsage", input: {} },
    { method: "readCliproxyUsage", input: { providerIds: ["cliproxy-claude"], force: true } },
  ]);
  await act(async () => { slot.getByRole("button", { name: "已用（Used）" }).click(); });
  const usedMeter = slot.getByRole("progressbar", { name: "Weekly limit 已用额度" });
  assert.equal(usedMeter.getAttribute("aria-valuenow"), "25");
  assert.equal((usedMeter.firstElementChild as HTMLElement).style.width, "25%");
  assert.ok(slot.getByText("25%"));
  assert.equal(slot.inspection.rpcCalls.length, 2);
  slot.lifecycle.unmount();

  const restored = renderSlot(app.navPanels[0]!, { subPath: "" }, { rpc: { readCliproxyUsage: () => snapshot } });
  await restored.findByText("Claude");
  assert.equal(restored.getByRole("button", { name: "已用（Used）" }).getAttribute("aria-pressed"), "true");
  assert.equal(restored.getByRole("progressbar", { name: "Weekly limit 已用额度" }).getAttribute("aria-valuenow"), "25");
  await act(async () => { restored.getByRole("button", { name: "剩余" }).click(); });
  assert.equal(restored.getByRole("progressbar", { name: "Weekly limit 剩余额度" }).getAttribute("aria-valuenow"), "75");
  restored.lifecycle.unmount();
  const remaining = renderSlot(app.navPanels[0]!, { subPath: "" }, { rpc: { readCliproxyUsage: () => snapshot } });
  await remaining.findByText("Claude");
  assert.equal(remaining.getByRole("button", { name: "剩余" }).getAttribute("aria-pressed"), "true");
  remaining.lifecycle.unmount();
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
      }],
    }],
  };
  const slot = renderSlot(app.navPanels[0]!, { subPath: "" }, { rpc: { readCliproxyUsage: () => snapshot } });
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
