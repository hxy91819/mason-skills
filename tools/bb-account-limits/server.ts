import { config } from "./config.js";
import type { BbPluginApi, PluginProviderDeclaration } from "@get-bb/plugin-sdk";
import { agyProvider } from "./agy-provider.js";
import { extraProviders } from "./extra-providers.js";

const agents: Array<{ id: string; displayName: string; command: string; args: string[]; env: Record<string, string>; login: string; icon: string; usageOnly?: boolean }> = [
  { id: "acp-codexl", displayName: "CodexL", command: config.codexAcp, args: [], env: { CODEX_PATH: config.codex, INITIAL_AGENT_MODE: "agent-full-access" }, login: "codexl-bb login", icon: "Terminal" },
  // 额外 Codex 账号与 acp-codexl 同构：codex-acp 通过 CODEX_PATH 拿到账号隔离的 codex 包装 CLI。
  ...config.codexAccounts.map(account => ({
    id: account.id, displayName: account.displayName, command: config.codexAcp, args: [] as string[],
    env: { CODEX_PATH: account.command, INITIAL_AGENT_MODE: "agent-full-access" }, login: `${account.command} login`, icon: account.icon,
  })),
  { id: "acp-kiro", displayName: "Kiro", command: config.kiro, args: ["acp"], env: {}, login: "kiro-cli login", icon: "Bug" },
  // These entries exist solely for BB's native usage surface. Empty fallback
  // models keep an account quota from being chosen as an executable ACP agent.
  ...config.cliproxy.accounts.filter(account => account.enabled !== false).map(account => ({
    id: `cliproxy-${account.id}`,
    displayName: account.label ?? `${account.provider} quota`,
    command: "cliproxy-quota-only",
    args: [] as string[],
    env: {},
    login: "Configure the Cliproxy management key and account selector",
    icon: "ChartColumn",
    usageOnly: true,
  })),
];

export const providers = agents.map((agent): PluginProviderDeclaration => ({
  id: agent.id,
  displayName: agent.displayName,
  family: agent.usageOnly ? "cliproxy" : "acp",
  icon: agent.icon,
  strings: {
    installUrl: agent.usageOnly ? "https://help.router-for.me/management/api" : agent.id === "acp-kiro" ? "https://kiro.dev/docs/cli/" : "https://github.com/agentclientprotocol/codex-acp",
    signInHint: agent.usageOnly ? "This is a usage-only Cliproxy account entry." : `Run \`${agent.login}\` on the machine, then reload usage.`,
    expiredHint: agent.usageOnly ? "Check the Cliproxy credential and management key, then reload usage." : `Session expired. Run \`${agent.login}\`, then reload usage.`,
  },
  experimental_bridgeOptions: {
    acpDialect: "generic",
    usageOnly: agent.usageOnly === true,
    acpLaunchSpec: { displayName: agent.displayName, command: agent.command, args: agent.args, env: agent.env },
  },
  maintenance: { health: !agent.usageOnly, usage: true, installation: false },
  models: { scope: "host" },
  capabilities: {
    supportsServiceTier: true,
    supportsNativeUserQuestion: false,
    supportsManualCompaction: false,
    fork: "none",
    supportsThreadArchive: false,
    supportsThreadRename: false,
    permissionModes: ["full"],
    reasoningLevels: ["low", "medium", "high", "xhigh", "max"],
  },
  serviceTiers: [{ id: "default", label: "Default" }, { id: "fast", label: "Fast" }],
  composerActions: [],
}));

export default function accountLimitsPlugin(bb: BbPluginApi) {
  const enabled = [...providers, agyProvider, ...extraProviders].filter(p => config.enabledProviders.includes(p.id));
  for (const provider of enabled) bb.providers.register(provider);
  bb.cli.register({
    name: "account-limits",
    summary: "Query local and Cliproxy account limits through BB's native usage limits service",
    commands: [{ name: "show", summary: "Read account limits", usage: "bb account-limits [--host <id>]" }],
    async run(argv) {
      if (argv.includes("--help")) return { exitCode: 0, stdout: "Usage: bb account-limits [--host <id>]\n" };
      if (argv.length !== 0 && !(argv.length === 2 && argv[0] === "--host")) {
        return { exitCode: 2, stderr: "Usage: bb account-limits [--host <id>]\n" };
      }
      const usage = await bb.sdk.system.usageLimits(argv.length ? { hostId: argv[1] } : {});
      return { exitCode: 0, stdout: JSON.stringify(Object.fromEntries(enabled.filter(p => p.maintenance?.usage).map(p => [p.id, usage[p.id] ?? null])), null, 2) + "\n" };
    },
  });
}
