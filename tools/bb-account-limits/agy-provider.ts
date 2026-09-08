import { config } from "./config.js";
import type { PluginProviderDeclaration } from "@get-bb/plugin-sdk";

export const agyProvider: PluginProviderDeclaration = {
  id: "acp-agy",
  displayName: "Antigravity (AGY)",
  family: "acp",
  icon: "Zap",
  strings: {
    installUrl: "https://github.com/shubzkothekar/antigravity-acp",
    signInHint: "Run `agy` on the machine to sign in.",
    expiredHint: "Run `agy` on the machine to renew the login.",
  },
  experimental_bridgeOptions: {
    acpDialect: "generic",
    acpLaunchSpec: {
      displayName: "Antigravity (AGY)",
      command: config.bun,
      args: [config.agyEntry],
      env: { AGY_BIN: config.agy, AGY_SKIP_DOWNLOAD: "1" },
    },
  },
  maintenance: { health: true, usage: true, installation: false },
  models: { scope: "host" },
  capabilities: {
    // antigravity-acp 1.1.0 无条件跳过 agy 审批，不能向用户声明支持受限模式。
    permissionModes: ["full"],
    supportsServiceTier: false,
    supportsNativeUserQuestion: false,
    supportsManualCompaction: false,
    supportsThreadArchive: false,
    supportsThreadRename: false,
    fork: "none",
    reasoningLevels: ["medium"],
  },
  composerActions: [],
};
