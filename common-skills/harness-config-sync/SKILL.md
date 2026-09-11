---
name: harness-config-sync
description: 在多个 Agent 宿主之间自动收敛用户级或项目级 prompts 与 skills，标准内容保留单一事实源，宿主专有路径使用软链接入。
disable-model-invocation: true
triggers:
  - user
---

# Harness Config Sync

一次调用完成盘点、迁移、链接和验证。不要把 `check`、`apply`、`migrate` 暴露成连续的用户决策；显式调用已授权在请求范围内执行可逆的本地文件迁移。只有同名实体内容无法安全合并时才停止并请用户裁决。

## 收敛目标

- 用户级事实源：prompt 为 `~/.agents/AGENTS.md`，skills 为 `~/.agents/skills/`。mason-skills checkout 存在时，user prompt 正文托管于该仓库的 `config/user-agents.md`，`~/.agents/AGENTS.md` 软链到它，编辑即改仓库文件，经 Git 在各环境间收敛；无 checkout 时维持普通文件现状。
- 项目级事实源：prompt 为仓库根 `AGENTS.md`，skills 为 `.agents/skills/`。
- CodeBuddy、Claude Code、Kiro 的专有入口只保留软链；CodeBuddy 的独立个人规则可继续放在 `~/.codebuddy/rules/`。
- Kimi Code 原生读取上述标准 prompt 和 skills，不为同一内容创建 `$KIMI_CODE_HOME` 或 `.kimi-code` 镜像。
- agy（Antigravity CLI）project 级原生读取上述标准路径；user 级只在 `~/.gemini/config/` 保留两条软链接入，不建其他镜像。
- Devin project 级与 user skills 原生读取上述标准路径；user prompt 经 `~/.config/devin/AGENTS.md` 软链接入，不建 `.devin/` 或 `.windsurf/` 镜像。
- 内容只在事实源编辑。同步只治理布局，不改 Skill 正文、调用策略、仓库业务文档、Git 历史或 submodule 状态。

## 自动确定范围

按用户原话推断，不额外询问：

- 提到全局、用户级、home 或 `~/`：处理 user scope。
- 提到仓库、项目级或当前项目：处理当前 Git 仓库。
- 明确提到两者或全部：两者都处理。
- 未指定时，在 Git 仓库内只处理当前项目；否则只处理 user scope。

只配置用户点名的宿主；用户泛指“各 Agent”时处理当前已安装或已有配置目录的 Codex、CodeBuddy、Claude Code、Kiro、Kimi Code、agy、Pi（存在 `pi` 可执行文件或 `~/.pi/agent/` 即视为已安装）和 Devin（存在 `devin` 可执行文件或 `~/.config/devin/` 即视为已安装）。宿主版本探测、文档查询和新会话黑盒测试不是默认步骤；仅在实际路径行为与本契约矛盾或用户明确要求时执行。

## 单次自动收敛

### 1. 快速盘点

先检查根入口的类型和 `readlink -f` 终点，不展开完整 skills 列表：

| 范围 | Prompt 入口 | Skills 入口 |
|---|---|---|
| user | `~/.codex/AGENTS.md`、`~/.codebuddy/CODEBUDDY.md`、`~/.claude/CLAUDE.md`、`~/.kiro/steering/*.md`、`~/.gemini/config/AGENTS.md`、`~/.pi/agent/AGENTS.md`、`~/.config/devin/AGENTS.md` | `~/.codex/skills`、`~/.codebuddy/skills`、`~/.claude/skills`、`~/.kiro/skills`、`~/.gemini/config/skills`、`~/.config/devin/skills` |
| project | `AGENTS.md`、`CLAUDE.md`、`.kiro/steering/agents.md`；CodeBuddy 无 `CODEBUDDY.md` 时直接使用 `AGENTS.md` | `.agents/skills` 及需要专有入口的宿主项目 skills 目录 |

Kimi Code 走原生快速路径：user scope 直接检查 `~/.agents/AGENTS.md`、`~/.agents/skills/`，project scope 直接检查从项目根到当前目录适用的 `AGENTS.md`/`agents.md` 和 `.agents/skills/`。仅当已有 Kimi 专有内容时再检查 `$KIMI_CODE_HOME/AGENTS.md`、`$KIMI_CODE_HOME/skills/`、项目 `.kimi-code/AGENTS.md` 与 `.kimi-code/skills/`；`KIMI_CODE_HOME` 未设置时默认为 `~/.kimi-code`。

agy 走原生快速路径：project scope 直接检查仓库根 `AGENTS.md` 和 `.agents/skills/`，不需要专有入口；user scope 只检查 `~/.gemini/config/AGENTS.md` 与 `~/.gemini/config/skills` 两条软链。实测注意：新仓库需先注册 project（如 `agy --new-project`）agy 才会加载 project 级内容；`~/.agents/AGENTS.md` 不被 agy 原生发现，必须经 user 软链接入。

Pi 走原生快速路径：user scope 检查 `~/.pi/agent/AGENTS.md`，skills 直接原生读取 `~/.agents/skills/`，不建任何专有 skills 入口；project scope 与标准宿主相同（仓库根 `AGENTS.md` 与 `.agents/skills/`）。

Devin 走原生快速路径：project scope 直接检查仓库根 `AGENTS.md` 和 `.agents/skills/`；user scope skills 直接检查 `~/.agents/skills/`，prompt 检查 `~/.config/devin/AGENTS.md` 软链。仅当已有 Devin 专有内容时再检查 `~/.config/devin/skills/`、`~/.codeium/<channel>/skills/`（channel 为 `windsurf`/`windsurf-next`/`windsurf-insiders`）、`.devin/skills/` 与 `.windsurf/skills/`。`~/.claude/CLAUDE.md` 也会被 Devin 无条件读取，但标准接入点是 `~/.config/devin/AGENTS.md`，不依赖 Claude 目录存在。Windows 下 Devin 全局路径为 `%APPDATA%\devin\`（即 `AGENTS.md` 与 `skills/` 在其下）。

若所有入口已解析到事实源，抽查 prompt 和一个 `SKILL.md` 可读后立即结束。只有根入口不一致、存在实体目标或断链时才枚举受影响目录。

项目 scope 开始和结束时检查当前分支、`git status --short` 与 `git worktree list`，保留所有无关并发改动。

### 2. 自动迁移差异

对每个不一致入口顺着软链找到真实内容，再执行：

1. 事实源缺失而专有入口只有一个实体来源：把该实体迁到事实源。
2. 多个来源包含不同名称：合并到事实源。
3. 同名内容字节一致：保留事实源一份，把被替换项放入备份。
4. 同名实体内容不同、来源归属不明确或目标会逃逸请求范围：停止该项，报告双方路径与差异，让用户裁决；其他独立项可继续。
5. 替换任何实体或错误链接前先备份。user scope 使用 `~/.agents/harness-config-sync-backups/<timestamp>/`；project scope 使用被本地忽略的 `.local/harness-config-sync-backups/<timestamp>/`。

Kimi 专有路径只保留真正的 Kimi-only 增量。把其中可跨宿主共享的内容迁入标准事实源；不要把标准内容反向链接到 Kimi 专有路径，因为 Kimi 会同时扫描两套目录，重复名称还会引入优先级覆盖。

断裂链接不作为内容迁移；有明确事实源时备份后重建，没有明确来源时报告阻塞。不要为了修复链接自动初始化 submodule、下载依赖或修改 Skill 行为。

### 3. 接入仓库事实源（user prompt）

`mason-skills` 仓库的 `config/user-agents.md` 是共享 user-scope prompt 的托管内容源。在第 2 步把各宿主入口收敛到 `~/.agents/AGENTS.md` 之后，发现 checkout 即按序接入：

1. 发现 checkout：用户给过路径就用该路径；否则对 `~/.agents/skills/` 下任一指向本仓库的软链 `readlink -f`，从解析结果反推仓库根（其下须存在 `config/skill-symlinks.yaml` 才认定）；仍找不到时停止该项并请用户提供 checkout 路径，不自行 clone。
2. `~/.agents/AGENTS.md` 缺失或为断裂链接且仓库含 `config/user-agents.md`：备份后建立指向 `<checkout>/config/user-agents.md` 的绝对软链。
3. `~/.agents/AGENTS.md` 为普通文件且与仓库文件字节一致：备份普通文件后替换为同一软链。
4. 两者内容不同：停止该项，报告双方路径与差异，由用户裁决以哪边为准（常见做法：先把线上最新内容提交进仓库并推送，再接入软链）；其他独立项可继续。
5. 无 checkout 或仓库无该文件：保持普通文件现状作为事实源，最终报告说明仓库托管未启用。

Windows 注意：prompt 是文件级链接，Junction 不适用；按第 4 步的 Windows 建链规则用 `mklink` 建立文件符号链接（需管理员或开发者模式）。无特权且不能建链时按第 4 条停止该项报告，不得用普通文件副本替代事实源；Git Bash 的 `ln -s` 默认执行复制，禁止用于建链。

接入后 prompt 正文的修改都落在仓库 checkout 内，按仓库规则提交推送；其他环境 pull 后由本 skill 重建软链完成收敛。

### 4. 建立宿主入口

Prompt 使用文件级相对软链（user scope 跨配置目录时可使用绝对软链）：

- user：Codex、CodeBuddy、Claude 和 Kiro steering 均指向 `~/.agents/AGENTS.md`；agy 经 `~/.gemini/config/AGENTS.md`、Pi 经 `~/.pi/agent/AGENTS.md`、Devin 经 `~/.config/devin/AGENTS.md` 软链指向同一文件。
- project：`CLAUDE.md -> AGENTS.md`，`.kiro/steering/agents.md -> ../../AGENTS.md`；CodeBuddy 默认不创建 `CODEBUDDY.md`。
- Kimi Code：不建链接；原生使用 user `~/.agents/AGENTS.md` 和 project `AGENTS.md`。Kimi-specific 指令仅在确有专属差异时保留于 `$KIMI_CODE_HOME/AGENTS.md` 或 `.kimi-code/AGENTS.md`。

Skills 优先使用目录级软链，因为新增 Skill 可自动出现：

- user：Codex、CodeBuddy、Claude 和 Kiro 的 skills 根目录指向 `~/.agents/skills/`，agy 经 `~/.gemini/config/skills` 软链指向同一目录；Kimi Code 与 Devin 原生扫描该目录。
- project 无 `.agents/skill-catalog.json` 时：需要专有入口的目标目录可完全由共享 Skill 管理，就让整个宿主 skills 目录指向 `.agents/skills/`；Kimi Code、Codex、agy 和 Devin 不需要专有入口。
- project 有 catalog，或宿主目录需要只暴露选定 Skill 时：对需要专有入口的宿主直接运行一次脚本并带 `--apply`；脚本会先完成全量冲突预检，有任一冲突则零写入，不需要先 dry run 再征求确认。

Windows 建链规则：目录级 skills 入口用 `mklink /J`（Junction，无需特权）；文件级 prompt 入口用 `mklink`（需管理员或开发者模式）。Git Bash 的 `ln -s` 默认执行复制而非建链，禁止使用；`readlink -f` 在 Git Bash 中可解析符号链接与 Junction，第 1 步盘点命令通用。`sync_skill_symlinks.py` 在 Windows 无符号链接特权时对目录自动退回 Junction，链接识别兼容两种形态。

```bash
python3 ~/.kiro/skills/harness-config-sync/scripts/sync_project_agent_skills.py \
  --repo "$PWD" --target .kiro/skills --apply
```

对 CodeBuddy 和 Claude 分别使用 `.codebuddy/skills`、`.claude/skills`。Kimi Code、Codex 与 Devin 直接读取 `.agents/skills`，不运行 catalog 链接脚本；agy 同样原生读取 `.agents/skills`，且实测不跟随 `.agents/skills/` 内的子目录软链，catalog 软链对 agy 无效——它的 Skill 实体必须落在 `.agents/skills/` 真实子目录中。catalog 只登记团队共享的标准入口；机器绝对路径指向的个人 Skill 不进入 catalog。

Kimi Code 默认合并自动发现目录；`extra_skill_dirs` 只追加目录，可以保留。`kimi --skills-dir` 会替换自动发现目录；发现固定启动脚本使用该参数时，确保其中显式包含所需标准目录，或者报告它会绕过同步结果。Kimi 手动调用 Skill 使用 `/skill:<name>`；`disable-model-invocation: true` 可直接控制其自动调用，`agents/openai.yaml` 只服务支持该文件的其他宿主。Devin 手动调用使用 `/<name>`；`disable-model-invocation` 与 `agents/openai.yaml` 对 Devin 均无效，其等效控制是 SKILL.md frontmatter 的 `triggers: [user]`（缺省 `[user, model]` 允许 agent 自动触发）。

### 5. 本地排除与验证

项目中新建且仅服务本机宿主的 `CLAUDE.md`、`.claude/`、`.codebuddy/`、`.kiro/` 等入口写入 `.git/info/exclude`，保持幂等；团队已跟踪的入口遵循仓库约定，不擅自改为本地排除。不要仅为 Kimi 创建 `.kimi-code/`、为 Devin 创建 `.devin/` 或 `.windsurf/`；已有 `.kimi-code/local.toml` 是机器本地配置，按 Kimi 官方建议保持未跟踪。

完成标准：

1. 需要适配的宿主入口均为预期软链；Kimi Code、Codex、agy、Pi 与 Devin 的标准原生路径直接存在且可读。
2. 可透过 prompt 入口读取正文，可透过每个目标 skills 入口读取非空 `SKILL.md`。
3. 当前加载路径无断链或重复的 Kimi 标准镜像；备份目录不计入加载路径。
4. catalog 脚本复跑显示全部 `KEEP`，无 `CREATE` 或 `CONFLICT`。
5. `git status --short` 只包含任务相关的团队事实源变化；本机宿主入口被正确忽略。

最终只报告范围、事实源、创建/迁移/备份数量、冲突和验证结果。提醒用户重启宿主会话使新 prompt/skills 生效；除非用户明确要求，不再启动宿主做额外行为测试。报告显式调用时同时给出通用 `$<name>`、Kimi `/skill:<name>` 和 Devin `/<name>` 语法。

## Catalog 安全契约

`.agents/skill-catalog.json` 示例：

```json
{"skills": [{"name": "demo-skill", "path": ".agents/skills/demo-skill"}]}
```

同步脚本只创建 catalog 条目对应的相对软链。catalog 路径必须按字面位于 `.agents/skills/`；实体 Skill 必须解析在 `.agents/skills/` 内，软链 Skill 可解析到同一仓库内的工具或 submodule，但不能逃逸仓库；每个来源必须含非空 `SKILL.md`。已有正确相对链接保持不变，文件、目录、断链或不同目标链接均作为 `CONFLICT`，整次执行零写入。脚本不 stage、commit，也不修改 `.gitignore` 或 `.git/info/exclude`。
