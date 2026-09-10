import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";
import { act } from "react";
import { installTestPluginRuntime, loadPluginApp, renderSlot } from "@get-bb/plugin-sdk/testing/app";
import type { AccountLimitsPanelSnapshot } from "./contract.js";

const dom = new JSDOM("<!doctype html><html><body></body></html>");
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
  assert.ok(slot.getByText(/插件每 30 分钟更新缓存，供应商卡片可单独刷新。/));
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
  slot.lifecycle.unmount();
});
