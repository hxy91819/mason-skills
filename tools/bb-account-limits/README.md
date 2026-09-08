# BB Account Limits

BB 本地 provider 插件：将 CodexL、Kiro、AGY 账户额度接入原生 `system.usageLimits` 和 Provider Usage 面板。附带 Copilot、CodeBuddy 原生 ACP 入口与独立图标；这两者没有额度适配。

使用 BB 0.42+ 和公开 Plugin SDK 0.4.47。无需修改 BB 安装文件。此目录是可安装插件，不是 skill。

## 配置

先在执行机器安装并登录需要的 CLI，然后创建机器级覆盖文件 **`$XDG_CONFIG_HOME/bb/account-limits/local.json`**（默认 `~/.config/bb/account-limits/local.json`，不属于本仓库、不会提交）；格式不合法或字段缺失时退回内置默认并写警告日志：

```json
{
  "enabledProviders": ["acp-codex-saiens", "acp-codex-omnidrome"],
  "codex": "codex",
  "codexAcp": "/home/me/.local/share/codex-acp/node_modules/.bin/codex-acp",
  "codexAccounts": [
    { "id": "acp-codex-saiens", "displayName": "🟦 Codex · saiens", "command": "codex-saiens-bb", "icon": "./icons/codex-saiens.svg" }
  ]
}
```

| 配置 | 用途 |
|---|---|
| `enabledProviders` | 注册的 provider ID；默认仅 CodexL、Kiro |
| `codex` | CodexL 无权限参数包装入口，或直接指定 `codex` |
| `codexAcp` | `@agentclientprotocol/codex-acp` 的可执行文件 |
| `codexAccounts` | 额外 Codex 账号：与 `acp-codexl` 同构注册，`command` 是该账号的包装 CLI，`icon` 可填内置 glyph 或插件相对 SVG 路径 |
| `kiro` / `agy` | 对话和额度查询共同使用的 CLI 路径 |
| `bun` / `agyEntry` | AGY ACP 启动器；后者必须是执行机器上的绝对路径 |
| `copilot` / `codebuddy` | 可选的原生 ACP CLI 路径 |

`config.ts` 只保留机器无关的默认值；上表所有键都可在 local JSON 里覆盖，未知键忽略。命令默认从 **BB 执行进程的 PATH** 查找；找不到时在 local JSON 里填绝对路径。修改配置后重新构建、reload；local JSON 是运行时读取的，只改它时 reload 即可、无需重新构建。多个执行机器必须有兼容的命令路径，单份插件配置不做每机器映射。

覆盖文件的解析顺序（命中即停）：

1. `ACCOUNT_LIMITS_LOCAL_CONFIG` 环境变量指向的文件；
2. `$XDG_CONFIG_HOME/bb/account-limits/local.json` —— 推荐位置；host bundle 会被 BB 复制到 `plugin-host-artifacts` 的哈希目录运行，插件内相对路径在 host 侧不可靠；
3. 插件根 `account-limits.local.json`（已在 `.gitignore`）—— 仅作上游兼容与本地开发；server 侧可用，host 侧不可依赖。

可启用 ID：`acp-codexl`、`acp-kiro`、`acp-agy`、`acp-copilot`、`acp-codebuddy`，以及 `codexAccounts` 里自定义的 ID。仅启用已准备好的入口。不要把账号、token、原机器认证目录放入源码；机器相关配置全部留在 local JSON。

CodexL 包装脚本应原样转发参数，不固定注入 `danger-full-access` 或 `approval=never`。如果不需要账户隔离，`codex` 配置可直接填已登录的 `codex` 命令；provider ID 仍为 `acp-codexl`。

## 安装

从此目录执行：

```bash
npm ci --include=dev --ignore-scripts
npm run typecheck
npm test
bb plugin build .
bb plugin install . --yes
bb plugin enable provider-usage
bb account-limits
```

依赖：Node/npm、BB，以及所启用 provider 的 CLI；Codex ACP 适配器可用 `npm install -g @agentclientprotocol/codex-acp@1.10.0` 安装。依赖锁已固定，但需要的 CLI 登录由用户在各自执行机器完成。

**重复注册检查**：安装前用 `bb provider list` 和 `bb plugin config provider-acp` 检查同名 ID。将接管条目的原配置另存备份，只移除 `customAgents` 中相同的条目，保留其他入口。如果已有旧版 `account-limits` 路径安装，记录旧路径后改为此目录；不要同时注册这些 ID。

安装后查询真实模型和额度：

```bash
bb provider list --environment <environment-id> --json
bb provider models acp-kiro --environment <environment-id> --json
bb account-limits --host <host-id>
```

额度显示在 BB 原生查询和内置 Provider Usage 面板中，不需要另一套面板。

## 可选 AGY

```bash
cd agy
npm ci --ignore-scripts
```

另行安装 Bun 和已登录的 `agy` CLI。将 `config.ts` 中 `agyEntry` 设置为本目录下 `agy/agy-entry.mjs` 的绝对路径，并在 `enabledProviders` 加入 `acp-agy`。该启动器在模型缓存为空时先查询目录，再调用固定的 `antigravity-acp@1.1.0`；禁止适配器另行下载 CLI。

**AGY 仅支持 Full Access**：上游适配器无条件跳过 CLI 审批。不要宣称支持 BB 的受限模式。模型缓存与会话绑定位于执行用户的 `~/.agy-acp`，原生会话由 AGY 管理，均不提交 Git。

Copilot 使用 `--acp`，Full Access 映射 `--yolo`；CodeBuddy 使用 `--acp`，权限映射 `acceptEdits` / `bypassPermissions`，高风险操作可能仍确认。保持 provider ID 即可继续引用已有 BB 线程，但升级后仍应验证恢复行为。

## 查询语义与限制

- CodexL：app-server 账户接口，显示各模型组额度窗口，不启动模型回合。
- Kiro：内置 `/usage` 的套餐 credits；重置只有日期，因此不伪造 UTC 时刻或倒计时。
- AGY：内置 `/usage` 的各模型组剩余百分比转换为已用百分比，保留 UTC 重置时间。
- CLI 未提供的信息保持为空；未知格式、超时、非零退出等不显示成零用量。
- 查询有输出上限、20 秒超时、取消与进程清理；同一 bridge 中的重复查询合并。支持 POSIX/macOS，Windows 尚未实测。
- Copilot/CodeBuddy 仅注册入口，不包含额度查询。

图标使用 BB 已支持的名称：CodexL=Terminal、Kiro=Bug、AGY=Zap、Copilot=Bot、CodeBuddy=Code。

## 更新和回退

修改 `config.ts` 或 local JSON 后：只改 JSON 时 `bb plugin reload account-limits`；改了代码则 `bb plugin build .` 再 reload。验证模型发现和额度查询，不仅检查安装成功。

回退到旧路径插件时重新安装原路径。回退为普通 ACP 条目时先禁用本插件，再将备份条目合并回当前 `customAgents`，避免重复 ID；不删除线程、认证或原生会话数据。

测试覆盖额度解析、失败状态、精度、超时/取消、退出清理和 ACP bridge conformance。`test-runtime.mjs` 为 SDK 0.4.47 的测试运行时提供 CJS require 支持。
