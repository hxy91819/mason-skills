import { config } from "./config.js";
import type { PluginProviderDeclaration } from "@get-bb/plugin-sdk";

const agents: Array<{ id: string; displayName: string; icon: string; launch: {
  displayName: string; command: string; args: string[]; env: Record<string, string>;
  permissionCli: Record<string, string[]>;
} }> = [
  {
    id: "acp-copilot", displayName: "GitHub Copilot", icon: "Bot",
    launch: {
      displayName: "GitHub Copilot", command: config.copilot,
      args: ["--acp"], env: {}, permissionCli: { full: ["--yolo"] },
    },
  },
  {
    id: "acp-codebuddy", displayName: "CodeBuddy", icon: "Code",
    launch: {
      displayName: "CodeBuddy", command: config.codebuddy,
      args: ["--acp"], env: {}, permissionCli: {
        full: ["--permission-mode", "bypassPermissions"],
        workspaceWrite: ["--permission-mode", "acceptEdits"],
      },
    },
  },
];

export const extraProviders = agents.map(({ launch, ...agent }): PluginProviderDeclaration => ({
  ...agent, family: "acp",
  experimental_bridgeOptions: { acpLaunchSpec: launch },
  models: { scope: "host" },
  maintenance: { health: true, usage: false, installation: false },
  capabilities: {
    supportsServiceTier: true, supportsNativeUserQuestion: false,
    supportsManualCompaction: false, supportsThreadArchive: false,
    supportsThreadRename: false, fork: "none",
    permissionModes: ["accept-edits", "full"],
    reasoningLevels: ["low", "medium", "high", "xhigh", "max"],
  },
  serviceTiers: [{ id: "default", label: "Default" }, { id: "fast", label: "Fast" }],
  composerActions: [],
}));
