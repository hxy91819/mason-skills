# BB Account Limits

BB 本地 provider 插件：将 CodexL、Kiro、AGY 账户额度接入原生 `system.usageLimits` 和 Provider Usage 面板；将 Cliproxy 的账户额度放入侧边栏独立的“账户额度”页面。附带 Copilot、CodeBuddy 原生 ACP 入口与独立图标；这两者没有额度适配。

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
| `enabledProviders` | 启用的原生 provider ID，以及要在“账户额度”页面显示的 `cliproxy-<provider>` 分组；默认仅 CodexL、Kiro |
| `codex` | CodexL 无权限参数包装入口，或直接指定 `codex` |
| `codexAcp` | `@agentclientprotocol/codex-acp` 的可执行文件 |
| `codexAccounts` | 额外 Codex 账号：与 `acp-codexl` 同构注册，`command` 是该账号的包装 CLI，`icon` 可填内置 glyph 或插件相对 SVG 路径 |
| `kiro` / `agy` | 对话和额度查询共同使用的 CLI 路径 |
| `bun` / `agyEntry` | AGY ACP 启动器；后者必须是执行机器上的绝对路径 |
| `copilot` / `codebuddy` | 可选的原生 ACP CLI 路径 |
| `cliproxy` | 通过 CLIProxyAPI 管理接口读取指定 OAuth 账户的额度；详见下节 |

`config.ts` 只保留机器无关的默认值；上表所有键都可在 local JSON 里覆盖，未知键忽略。命令默认从 **BB 执行进程的 PATH** 查找；找不到时在 local JSON 里填绝对路径。修改配置后重新构建、reload；local JSON 是运行时读取的，只改它时 reload 即可、无需重新构建。多个执行机器必须有兼容的命令路径，单份插件配置不做每机器映射。

覆盖文件的解析顺序（命中即停）：

1. `ACCOUNT_LIMITS_LOCAL_CONFIG` 环境变量指向的文件；
2. `$XDG_CONFIG_HOME/bb/account-limits/local.json` —— 推荐位置；host bundle 会被 BB 复制到 `plugin-host-artifacts` 的哈希目录运行，插件内相对路径在 host 侧不可靠；
3. 插件根 `account-limits.local.json`（已在 `.gitignore`）—— 仅作上游兼容与本地开发；server 侧可用，host 侧不可依赖。

可启用 ID：`acp-codexl`、`acp-kiro`、`acp-agy`、`acp-copilot`、`acp-codebuddy`，以及 `codexAccounts` 里自定义的 ID。另可用每个配置供应商对应的 `cliproxy-<provider>`（例如 `cliproxy-antigravity`）控制该供应商是否出现在“账户额度”页面；它不是 Provider，不会加入模型选择器。仅启用已准备好的入口。不要把账号、token、原机器认证目录放入源码；机器相关配置全部留在 local JSON。

CodexL 包装脚本应原样转发参数，不固定注入 `danger-full-access` 或 `approval=never`。如果不需要账户隔离，`codex` 配置可直接填已登录的 `codex` 命令；provider ID 仍为 `acp-codexl`。

### Cliproxy 供应商聚合额度

Cliproxy 配额以**账户**为单位配置、以**上游供应商**为单位显示。相同 `provider` 的账户会聚合成“账户额度”侧边栏页面中的一张卡：每个额度行带账号标签，不会把不同账号或不同限额池相加。`cliproxy-<provider>` 只控制这张卡是否显示；不注册为 BB Provider，因此不会出现在模型选择器或原生 Provider Usage 面板。

```json
{
  "enabledProviders": ["acp-codexl", "cliproxy-claude", "cliproxy-xai", "cliproxy-antigravity"],
  "cliproxy": {
    "managementBaseUrl": "http://127.0.0.1:8317/v0/management",
    "managementKeyFile": "/home/me/.config/cliproxyapi/management.key",
    "accounts": [
      {
        "id": "claude-work",
        "provider": "claude",
        "authIndex": "<stable-auth_index-from-Cliproxy>",
        "label": "Claude 工作账号"
      },
      {
        "id": "claude-personal",
        "provider": "claude",
        "account": "personal",
        "label": "Claude 个人账号"
      },
      {
        "id": "grok",
        "provider": "xai",
        "authIndex": "<stable-auth_index-from-Cliproxy>",
        "label": "Grok"
      },
      {
        "id": "gemini-1",
        "provider": "antigravity",
        "authIndex": "<stable-auth_index-from-Cliproxy>",
        "label": "Gemini · 账号 1"
      },
      {
        "id": "other-provider",
        "provider": "other-provider",
        "authIndex": "<stable-auth_index-from-Cliproxy>",
        "label": "其他供应商账号",
        "cachedWindows": [
          {
            "label": "月额度",
            "usedPercentSignal": "X-Provider-Used-Percent",
            "resetsAtSignal": "X-Provider-Reset-At",
            "scale": "percent"
          }
        ]
      }
    ]
  }
}
```

`authIndex` 是 Cliproxy `/auth-files` 返回的稳定运行时 ID，优先使用；它可避免相同 provider 下多个账号名称相同或变更时选错账户。若不想保存 ID，可用 `account` 精确匹配 Cliproxy 返回的 `account`、`email`、`name` 或 `label` 字段；匹配到多个账号时插件会拒绝查询并提示改用 `authIndex`。`managementKeyEnv` 优先于 `managementKeyFile`，密钥值本身永远不写入 JSON 或日志。

Claude 账号通过 Cliproxy 的 `/api-call` 在服务端代入 OAuth token，读取 Anthropic 官方 usage 响应；响应不可用时，会降级显示 Cliproxy 缓存的 5 小时、周和 scoped 周限额信号。`provider: "xai"` 是 Cliproxy 的 Grok 供应商标识，插件会读取其账单接口的当前周期与产品额度。`provider: "antigravity"` 会先从 Google Code Assist 读取项目 ID，再读取 Gemini、Claude/GPT 的 5 小时与周额度摘要；每个账户保持独立行。`provider: "zai"` 会显示为 Z.ai；待 Cliproxy 提供其认证记录或缓存额度信号后，可与其他未内置直连查询的 provider 一样通过 `cachedWindows` 映射。`scale` 选 `fraction` 时会将 0–1 转为百分比，默认为 `percent`。没有额度数据绝不显示为零。单个账号失败不会影响同一聚合卡中的其他账号。

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

原生 Provider Usage 面板继续显示 CodexL、Kiro、AGY 等真实 Provider；Cliproxy 额度在 BB 侧边栏打开“账户额度”查看。`bb account-limits` 的 JSON 同时包含 `providers`（原生额度）和 `cliproxy`（独立页面使用的数据）。

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
- Cliproxy：在独立“账户额度”页面按供应商聚合显示；Claude 显示官方 session/weekly/scoped weekly 窗口，Grok 显示当前周期和产品额度，Antigravity 显示 Gemini 与 Claude/GPT 的 5 小时/周额度摘要。查询失败时仅显示已缓存且可验证的限额信号。
- CLI 未提供的信息保持为空；未知格式、超时、非零退出等不显示成零用量。
- 查询有输出上限、20 秒超时、取消与进程清理；同一 bridge 中的重复查询合并。支持 POSIX/macOS，Windows 尚未实测。
- Copilot/CodeBuddy 仅注册入口，不包含额度查询。

图标使用 BB 已支持的名称：CodexL=Terminal、Kiro=Bug、AGY=Zap、Copilot=Bot、CodeBuddy=Code。

## 更新和回退

修改 `config.ts` 或 local JSON 后：只改 JSON 时 `bb plugin reload account-limits`；改了代码则 `bb plugin build .` 再 reload。验证模型发现和额度查询，不仅检查安装成功。

回退到旧路径插件时重新安装原路径。回退为普通 ACP 条目时先禁用本插件，再将备份条目合并回当前 `customAgents`，避免重复 ID；不删除线程、认证或原生会话数据。

测试覆盖额度解析、失败状态、精度、超时/取消、退出清理和 ACP bridge conformance。`test-runtime.mjs` 为 SDK 0.4.47 的测试运行时提供 CJS require 支持。

### AGY 长任务时限

ACP 启动环境设置 `AGY_EXTRA_ARGS="--print-timeout 2h"`，覆盖 `agy -p` 默认的 5 分钟等待。2026-09-09 实际故障日志显示默认时限会在 turn in progress 时截断任务，适配器却返回 end_turn；此配置解除 5 分钟截断，但超过 2 小时仍可能触发同类退出，不代表已解决所有 ACP 稳定性问题。更改后 reload 插件；已加载的 idle AGY 线程先 stop 释放旧运行时，再继续原线程。
