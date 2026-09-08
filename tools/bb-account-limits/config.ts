import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { z } from "zod";

/** 单个 Codex 账号入口：command 是包装 CLI，内部固定 CODEX_HOME 并原样转发全部参数。 */
const codexAccountSchema = z.object({
  id: z.string().min(1),
  displayName: z.string().min(1),
  command: z.string().min(1),
  icon: z.string().min(1),
});

const localConfigSchema = z.object({
  enabledProviders: z.array(z.string().min(1)).optional(),
  codex: z.string().min(1).optional(),
  codexAcp: z.string().min(1).optional(),
  codexAccounts: z.array(codexAccountSchema).optional(),
  kiro: z.string().min(1).optional(),
  agy: z.string().min(1).optional(),
  bun: z.string().min(1).optional(),
  agyEntry: z.string().min(1).optional(),
  copilot: z.string().min(1).optional(),
  codebuddy: z.string().min(1).optional(),
});

export type CodexAccount = z.infer<typeof codexAccountSchema>;
export type LocalAccountLimitsConfig = z.infer<typeof localConfigSchema>;

/**
 * 内置默认值：机器无关、可提交。目标机器的一切差异（可执行文件路径、账号列表、
 * CODEX_HOME 相关 wrapper 名）写在本目录 account-limits.local.json（已被 .gitignore），
 * 启动时读取并与默认值合并；文件缺失或损坏时退回默认值，不阻塞插件启动。
 */
const defaults = {
  enabledProviders: ["acp-codexl", "acp-kiro"],
  codex: "codexl-bb",
  codexAcp: "codex-acp",
  codexAccounts: [] as CodexAccount[],
  kiro: "kiro-cli",
  agy: "agy",
  bun: "bun",
  agyEntry: "/absolute/path/to/bb-account-limits/agy/agy-entry.mjs",
  copilot: "copilot",
  codebuddy: "codebuddy",
};

export type AccountLimitsConfig = typeof defaults;

export function loadLocalAccountLimitsConfigFile(
  file: URL,
  warn: (message: string) => void,
): Partial<AccountLimitsConfig> | null {
  let raw: string;
  try {
    raw = readFileSync(file, "utf8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException)?.code === "ENOENT") return null;
    warn(`local config unreadable (${(error as Error).message}); trying next candidate.`);
    return null;
  }
  let json: unknown;
  try {
    json = JSON.parse(raw);
  } catch {
    warn("local config is not valid JSON; trying next candidate.");
    return null;
  }
  const parsed = localConfigSchema.safeParse(json);
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    warn(`local config failed validation at ${issue.path.join(".") || "(root)"}: ${issue.message}; trying next candidate.`);
    return null;
  }
  // optional 字段可能以 undefined 落在结果里；过滤掉，避免覆盖默认值时引入 undefined。
  return Object.fromEntries(Object.entries(parsed.data).filter(([, value]) => value !== undefined)) as Partial<AccountLimitsConfig>;
}

/**
 * 解析顺序（命中即停）：
 * 1. ACCOUNT_LIMITS_LOCAL_CONFIG 环境变量指向的文件；
 * 2. $XDG_CONFIG_HOME/bb/account-limits/local.json（默认 ~/.config）——机器级稳定位置，
 *    host bundle 会被 BB 复制到 plugin-host-artifacts 的哈希目录运行，插件内相对路径在 host 侧不可靠；
 * 3. 插件根 ../account-limits.local.json —— 上游兼容与开发场景（server 侧 path 安装时可用）。
 * 全部缺失时静默使用内置默认值。
 */
export function localAccountLimitsConfigCandidates(): URL[] {
  const candidates: URL[] = [];
  const fromEnv = process.env.ACCOUNT_LIMITS_LOCAL_CONFIG;
  if (fromEnv) candidates.push(pathToFileURL(fromEnv));
  const xdg = process.env.XDG_CONFIG_HOME || join(homedir(), ".config");
  candidates.push(pathToFileURL(join(xdg, "bb", "account-limits", "local.json")));
  candidates.push(new URL("../account-limits.local.json", import.meta.url));
  return candidates;
}

export function loadLocalAccountLimitsConfig(
  candidates: URL[] = localAccountLimitsConfigCandidates(),
  warn: (message: string) => void = message => console.warn(`[account-limits] ${message}`),
): Partial<AccountLimitsConfig> {
  for (const file of candidates) {
    const overrides = loadLocalAccountLimitsConfigFile(file, warn);
    if (overrides !== null) return overrides;
  }
  return {};
}

export const config: AccountLimitsConfig = { ...defaults, ...loadLocalAccountLimitsConfig() };
