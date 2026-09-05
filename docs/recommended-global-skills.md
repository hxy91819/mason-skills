# 推荐全局技能规范与清单

本文档规范 `mason-skills` 仓库中允许推荐软链至用户级全局范围（User-Scope：`~/.agents/skills/`）的技能范围及准则。

单一事实源文件为 [`config/skill-symlinks.yaml`](../config/skill-symlinks.yaml)。其他工作区或新环境克隆本仓库后，均依据该清单和规范进行全局收敛，严禁随意将仓库内所有技能全量软链至全局。

---

## 一、推荐原则与准入标准

只有满足以下标准的技能才被纳入推荐全局清单：

1. **通用跨项目工程能力**：适用于各类代码库和开发任务（如架构规划、审查、测试、Git/Worktree 管理、发布与复盘）。
2. **高频复用与低副作用**：流程清晰，边界明确，不会隐式污染特定语言或业务项目的上下文。
3. **宿主无关性**：能在 Codex、Claude Code、Pi、Kimi Code、Kiro、agy 等各宿主之间稳定工作。

### 不推荐纳入全局的类别及原因

| 类别 | 代表技能 | 不推荐全局原因 | 建议使用方式 |
|---|---|---|---|
| **长链路专项工作流** | `article-workflow/*` 系列 (13 个技能) | 专用于长文写作与出版的分阶段链路，技能众多且高度耦合专项流程，全量软链会造成全局技能列表膨胀和上下文污染。 | 在具体写作项目或特定目录下按需引用。 |
| **特定领域/写作技能** | `article-polish` | 偏向文章精炼与翻译润色，属于特定内容创作场景。 | 按需在写作工作区引用。 |
| **仓库元工具与同步技能** | `skill-authoring-gate`、`skill-manifest-sync` | 属于管理本仓库技能规范与清单同步的元工具，直接使用本地脚本运行即可，无需占用全局 Agent 提示词空间。 | 通过脚本直接调用。 |
| **特定输出格式/外设依赖技能** | `tech-doc-html`、`ask-oracle` | 依赖特定交互设计模版或面向特定决策汇报场景，更适合按需显式加载或项目内配置。 | 项目级按需配置。 |

---

## 二、推荐全局技能清单（共 16 个）

当前清单经严格审计，仅包含以下 16 个核心工程与治理技能：

| 序号 | 技能名称 | 用途说明 | 默认触发机制 |
|:---:|---|---|---|
| 1 | `autoreview` | 提交/发布前的结构化代码审查 | 显式调用 (`$autoreview`) |
| 2 | `distill` | 从会话历史与实践中蒸馏可沉淀的规则与经验 | 显式调用 (`$distill`) |
| 3 | `harness-config-sync` | 跨 Agent 宿主（Codex/Claude/Pi 等）收敛 prompts 与 skills 布局 | 显式调用 (`$harness-config-sync`) |
| 4 | `large-task-orchestrator` | 用原生子 Agent 持续编排推进大型工程任务 | 显式调用 (`$large-task-orchestrator`) |
| 5 | `large-task-planning` | 大型工程任务的双层规划（人读 SPEC/STATUS + Agent 机器执行 plan.json） | 显式调用 (`$large-task-planning`) |
| 6 | `local-test` | 本地测试执行与环境启停安全规范 | 显式调用 (`$local-test`) |
| 7 | `mermaid-lint` | Markdown 中 Mermaid 图表的渲染级批量校验与自动修复 | 显式调用 (`$mermaid-lint`) |
| 8 | `open-source-contribution` | 开源贡献与发布前的合规与代码卫生审计 | 允许隐式触发 |
| 9 | `ppt-visual-review` | PPT / 单页视觉效果逐页验收 | 显式调用 (`$ppt-visual-review`) |
| 10 | `skill-test` | 隔离测试与验证 Skill 自身行为规范 | 显式调用 (`$skill-test`) |
| 11 | `spec-leak-review` | 界面/对外文本中的 Spec / Prompt 泄漏审查 | 显式调用 (`$spec-leak-review`) |
| 12 | `story-direction-review` | Story 完成后的方向偏差与未决假设独立复核 | 显式调用 (`$story-direction-review`) |
| 13 | `submit-pr-mr` | 提交 PR / MR 的标准前置检查与推送流程 | 显式调用 (`$submit-pr-mr`) |
| 14 | `use-worktree` | 在隔离的 Git worktree 中安全开展并发任务 | 显式调用 (`$use-worktree`) |
| 15 | `what-changed` | 用平实人读语言说明变更内容 | 显式调用 (`$what-changed`) |
| 16 | `worktree-cleanup` | 审计并安全清理已完成使命的 Git worktree | 显式调用 (`$worktree-cleanup`) |

---

## 三、同步与校验方式

### 1. 检查当前环境是否与推荐清单一致
```bash
python3 common-skills/skill-manifest-sync/scripts/sync_skill_symlinks.py --mode check
```
- 若完全收敛，退出码为 `0` 并报告 `summary: ok=16`。
- 若存在漂移或多余/缺失软链，会明确列出漂移项并返回非零退出码。

### 2. 执行收敛同步
```bash
python3 common-skills/skill-manifest-sync/scripts/sync_skill_symlinks.py --mode apply --yes
```
该命令会自动创建缺失的推荐软链，并移除已废弃的软链。

### 3. 清单变更维护规范
若后续确实需要新增或移除推荐全局的技能，必须严格遵循仓库 `AGENTS.md`：
- 新增推荐全局技能：`python3 common-skills/skill-manifest-sync/scripts/sync_skill_symlinks.py --mode register --skill <name> --note "..."`
- 移除推荐全局技能：`python3 common-skills/skill-manifest-sync/scripts/sync_skill_symlinks.py --mode remove --skill <name>`
- 同步更新本文档及 `config/skill-symlinks.yaml`。
