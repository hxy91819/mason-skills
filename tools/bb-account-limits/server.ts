import { config } from "./config.js";
import type { BbPluginApi, PluginProviderDeclaration } from "@get-bb/plugin-sdk";
import { agyProvider } from "./agy-provider.js";
import { extraProviders } from "./extra-providers.js";

const agents: Array<{ id: string; displayName: string; command: string; args: string[]; env: Record<string, string>; login: string }> = [
  { id: "acp-codexl", displayName: "CodexL", command: config.codexAcp, args: [], env: { CODEX_PATH: config.codex }, login: "codexl-bb login" },
  { id: "acp-kiro", displayName: "Kiro", command: config.kiro, args: ["acp"], env: {}, login: "kiro-cli login" },
];

export const providers = agents.map((agent): PluginProviderDeclaration => ({
  id: agent.id,
  displayName: agent.displayName,
  family: "acp",
  icon: agent.id === "acp-codexl" ? "Terminal" : "Bug",
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
    permissionModes: ["accept-edits", "full"],
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
    summary: "Query CodexL, Kiro and AGY through BB's native usage limits service",
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
