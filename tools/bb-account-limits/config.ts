/** 在安装前按目标执行机器编辑；更改后重新 build/reload。这里不存放凭据。 */
export const config = {
  enabledProviders: ["acp-codexl", "acp-kiro"] as string[],
  codex: "codexl-bb",
  codexAcp: "codex-acp",
  kiro: "kiro-cli",
  agy: "agy",
  bun: "bun",
  // 启用 acp-agy 前改为目标执行机器上 agy/agy-entry.mjs 的绝对路径。
  agyEntry: "/absolute/path/to/bb-account-limits/agy/agy-entry.mjs",
  copilot: "copilot",
  codebuddy: "codebuddy",
};
