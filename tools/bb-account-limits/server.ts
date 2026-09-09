import { config } from "./config.js";
import type { BbPluginApi, PluginProviderDeclaration } from "@get-bb/plugin-sdk";
import { agyProvider } from "./agy-provider.js";
import { accountLimitsHostContract, accountLimitsPanelRpcContract, accountLimitsPanelSnapshotSchema } from "./contract.js";
import { extraProviders } from "./extra-providers.js";

const agents: Array<{ id: string; displayName: string; command: string; args: string[]; env: Record<string, string>; login: string; icon: string }> = [
  { id: "acp-codexl", displayName: "CodexL", command: config.codexAcp, args: [], env: { CODEX_PATH: config.codex, INITIAL_AGENT_MODE: "agent-full-access" }, login: "codexl-bb login", icon: "Terminal" },
  // 额外 Codex 账号与 acp-codexl 同构：codex-acp 通过 CODEX_PATH 拿到账号隔离的 codex 包装 CLI。
  ...config.codexAccounts.map(account => ({
    id: account.id, displayName: account.displayName, command: config.codexAcp, args: [] as string[],
    env: { CODEX_PATH: account.command, INITIAL_AGENT_MODE: "agent-full-access" }, login: `${account.command} login`, icon: account.icon,
  })),
  { id: "acp-kiro", displayName: "Kiro", command: config.kiro, args: ["acp"], env: {}, login: "kiro-cli login", icon: "Bug" },
];

export const providers = agents.map((agent): PluginProviderDeclaration => ({
  id: agent.id,
  displayName: agent.displayName,
  family: "acp",
  icon: agent.icon,
  strings: {
    installUrl: agent.id === "acp-kiro" ? "https://kiro.dev/docs/cli/" : "https://github.com/agentclientprotocol/codex-acp",
    signInHint: `Run \`${agent.login}\` on the machine, then reload usage.`,
    expiredHint: `Session expired. Run \`${agent.login}\`, then reload usage.`,
  },
  experimental_bridgeOptions: {
    acpDialect: "generic",
    acpLaunchSpec: { displayName: agent.displayName, command: agent.command, args: agent.args, env: agent.env },
  },
  maintenance: { health: true, usage: true, installation: false },
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
  const host = bb.hosts.experimental_client({ contract: accountLimitsHostContract });
  const readPanelSnapshot = async () => {
    const machines = await Promise.all((await bb.sdk.hosts.list()).map(async machine => {
      if (machine.status === "disconnected") {
        return { id: machine.id, displayName: machine.name, status: "disconnected" as const, providers: [], error: null };
      }
      try {
        const snapshot = await host.call("readCliproxyUsage", {}, { hostId: machine.id });
        return { id: machine.id, displayName: machine.name, status: "connected" as const, providers: snapshot.providers, error: null };
      } catch (error) {
        return {
          id: machine.id,
          displayName: machine.name,
          status: "error" as const,
          providers: [],
          error: error instanceof Error ? error.message : "读取此机器的 Cliproxy 额度失败。",
        };
      }
    }));
    return accountLimitsPanelSnapshotSchema.parse({ machines });
  };
  bb.rpc.register(accountLimitsPanelRpcContract, { readCliproxyUsage: readPanelSnapshot });
  bb.cli.register({
    name: "account-limits",
    summary: "Query native provider limits and the Cliproxy account-limits panel data",
    commands: [{ name: "show", summary: "Read account limits", usage: "bb account-limits [--host <id>]" }],
    async run(argv) {
      if (argv.includes("--help")) return { exitCode: 0, stdout: "Usage: bb account-limits [--host <id>]\n" };
      if (argv.length !== 0 && !(argv.length === 2 && argv[0] === "--host")) {
        return { exitCode: 2, stderr: "Usage: bb account-limits [--host <id>]\n" };
      }
      const [usage, panel] = await Promise.all([
        bb.sdk.system.usageLimits(argv.length ? { hostId: argv[1] } : {}),
        readPanelSnapshot(),
      ]);
      const cliproxy = argv.length === 0 ? panel : { machines: panel.machines.filter(machine => machine.id === argv[1]) };
      const native = Object.fromEntries(enabled.filter(p => p.maintenance?.usage).map(p => [p.id, usage[p.id] ?? null]));
      return { exitCode: 0, stdout: JSON.stringify({ providers: native, cliproxy }, null, 2) + "\n" };
    },
  });
}
