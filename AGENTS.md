# Repository Agent Rules

## Skill invocation policy

每当创建、迁移或修改一个 skill，交付前必须先判断它的默认触发类型，并把判断结果告知用户。

### 分类与默认值

先阅读该 skill 的 `SKILL.md`，以及已有的 `agents/openai.yaml`（如果存在），再按主要使用方式分类：

- **流程类 skill**：负责规划、审查、复盘、治理、发布、迁移、编排，或包含审批门禁、用户决策或明显副作用的多步流程。默认仅显式触发，设置 `policy.allow_implicit_invocation: false`；用户需要通过 `$skill-name` 调用。它不会被隐式注入 Codex context。
- **被动型 skill**：提供可在请求自然匹配时由 agent 主动采用的通用能力，通常是低风险的格式化、生成、查询或验证。默认允许隐式触发，设置 `policy.allow_implicit_invocation: true`。
- **无法明确分类或两者混合**：采用流程类的保守默认值 `false`，并向用户说明不确定性和可选覆盖方式，不得静默选择。

分类依据是 skill 的实际工作流和风险，不是目录名称。可参考仓库现有设置：`distill`、`autoreview`、`large-task-planning`、`use-worktree`、`story-direction-review` 和 `ask-oracle` 为显式触发；`open-source-contribution` 为允许隐式触发。

仓库存在两种触发标记：Codex 优先读取 `agents/openai.yaml` 的 `policy.allow_implicit_invocation`；部分兼容旧技能还在 `SKILL.md` frontmatter 使用 `disable-model-invocation: true`。流程类 skill 必须以 `allow_implicit_invocation: false` 为 Codex 默认值，并保留或同步已有的 `disable-model-invocation: true`；被动型 skill 不得遗留与允许隐式触发相冲突的禁用标记。

### 配置与告知机制

1. 在 `agents/openai.yaml` 中写入或更新 `policy.allow_implicit_invocation`，保留无关的 `interface` 与 `dependencies` 字段；缺少该文件时创建最小完整配置。
2. 让 `SKILL.md` 的描述和正文与该策略一致：显式触发的 skill 要说明需要用户调用，允许隐式触发的 skill 不得声称只能手动调用。
3. 向用户报告：skill 名称、分类、默认策略、判断依据、配置文件，以及显式触发时的 `$skill-name` 用法；若采用保守默认，还要说明如何请求改为允许隐式触发。
4. 用 skill validator、YAML 解析和 `git diff --check` 验证；若配置或分类与用户明确要求冲突，以用户要求为准并在报告中说明。

## Skill 清单维护

`config/skill-symlinks.yaml` 是本仓库推荐 user-scope 软链的单一事实源：记录哪些 skill 推荐软链到全局（`~/.agents/skills`）。其他电脑拉取本仓库后，依据它即可复现同一套 skill 配置，无需口口相传。

- 在 `common-skills/` 新增 skill 且用户要求软链到 user scope 时，必须同步登记清单：
  `python3 common-skills/skill-manifest-sync/scripts/sync_skill_symlinks.py --mode register --skill <name> [--note "..."]`
- 删除或重命名 skill 时用 `--mode remove --skill <name>` 同步清单，避免留下悬空条目。
- 交付涉及 skill 增删的改动前，跑一次 `--mode check` 确认清单与本机实际软链一致。
- 本机同步入口是 `$skill-manifest-sync`：`--mode check` 预览、`--mode apply` 执行。apply 对「指向本仓库但不在清单里」的软链逐个提示删除；用户明确说保留时写入本机白名单 `~/.agents/skill-sync-whitelist.yaml`。白名单属于本机环境偏好，不提交 Git，也不得加进仓库的 `.gitignore` 之外的任何清单文件。
- 脚本只管理直接指向本仓库的软链：真实目录和经其他工作区中转的链接一律不碰，冲突只报告。

## 非开源 Skill

有些 skill 含内部账号映射、内网系统信息等明显不适合开源的内容（如 tccli 账号选择器）。这类 skill：

- 不得提交到本仓库或推送到远程；发现已落在 `common-skills/` 时，交付前移出。
- 直接以真实目录放在 `~/.agents/skills/<name>/`：触发行为与软链版一致，且天然在仓库、清单（`config/skill-symlinks.yaml`）和 `git add -A` 之外。
- 分类与触发策略仍按「Skill invocation policy」执行；若发现此类内容已进入 Git 历史，停止并报告用户，不得自行改写历史。

## 复杂 Skill 的可观测设计

新建或大改难以观测的 skill 时，必须按本仓库标准内置可观测设计。难以观测的判定：调用外部引擎/子进程、长时运行且内部有重试/fallback 状态迁移、输出是建议性结果且依赖人工裁决、或失败难以事后定位。参考实现：`large-task-orchestrator` 的 `scripts/orchestration_history.py`、`autoreview` 的 review history（`--history-summary`）。

标准组件（六项，全部落在已验证的两个参考实现上）：

1. **单一事实源**：本地、Git-ignored 的运行历史缓存，只由脚本维护，不用手改；存放在被审仓库或用户主目录之外，永不提交。
2. **最小事实**：只记复盘必需字段（engine/model/耗时/outcome/稳定 id）；prompt、正文、diff、日志、密钥一律不入库。
3. **决策回环**：主 Agent 的裁决（接受/拒绝等）用稳定 id 回写，使结果质量可度量；重复回写同一 id 是覆盖而非追加。
4. **聚合复盘**：提供只读聚合命令，输出按固定维度的统计与确定性复盘 hook（如低接受率、高 fallback 率），复盘基于明确的分子/分母。
5. **保留上限与折算**：滚动窗口 + 固定维度 rollup，防止无限增长；live 窗口与 rollup 不得重复计数。
6. **旁路失败**：记录失败只警告、绝不改变主流程结果；self-test 必须覆盖记账语义（滚动、覆盖、双计、未知 id 拒绝）。

无法全部满足时按保守处理：至少提供 check/show 式的只读聚合命令，并在 SKILL.md 说明缺口。

## 强制收尾动作

当前任务的改动完成且验证通过后，必须立即完成交付闭环；未完成闭环不得宣称任务完成：

1. 再次检查当前分支、`git status --short` 和 `git worktree list`，确认要交付的文件范围。将本次任务及用户明确要求交付的现有改动全部提交；本次用户要求“提交当前仓库所有内容”时，核对后使用 `git add -A`，不得遗漏未跟踪文件，也不得覆盖或丢弃并发改动。暂存前核对「非开源 Skill」边界，此类内容不得进入提交。
2. 将提交推送到其对应远端分支。
3. 若提交不在 `main`，切换到 `main`，将该分支合并到 `main`（优先快进；出现冲突时停止并报告），再推送 `main`。若提交本就在 `main`，确认 `main` 已推送即可视为合并步骤完成。
4. 收尾时必须停留在 `main`，并确认 `git status --short` 为空、没有未跟踪文件；这两项及推送成功共同构成完成标准。任何一项未满足，都继续处理或明确报告阻塞原因。

## Owner 交付权限

当当前用户明确是该仓库的 owner，或已由当前认证身份和远端仓库归属确认是 owner 时，完成用户要求的改动并通过必要校验后，可以直接提交并推送到当前目标分支，不再额外询问确认。推送前仍必须检查分支、工作区和 worktree，只暂存本次任务范围内的文件，并保留并发产生的无关改动。

这项权限只覆盖用户明确要求的仓库改动交付，不扩大修改范围，也不授权删除数据、改写历史或推送无关内容。无法确认 owner 身份时，提交可以继续，但推送前必须向用户确认。
