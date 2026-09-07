---
name: bb-model-routing
description: 仅当用户明确要求使用 BB 启动或创建线程（thread）执行任务时使用，例如“用 bb 开一个 codexl 线程来编码”或“用 bb 开线程找 bug”。未要求启动线程的编码、排障或模型咨询，查看或继续已有线程，以及编写或修改本技能时不触发。
---

# BB 线程模型选择

为用户已要求启动的 BB 线程选择 provider、模型与推理级别。这是用户的派发偏好，不是通用模型能力排名；不负责拆分任务或自动增加线程。

## 选择规则

用户本次明确指定的配置优先；未指定的字段按下表补齐。用户只说 CodexL 时，将其解析为 BB provider `acp-codexl`，不传 `codexl`。

| 用户指定的工具 | BB provider ID | 默认模型 | 推理级别 | 通常分配的任务 |
| --- | --- | --- | --- | --- |
| Codex | `codex` | Astra（`gpt-6-astra`） | `low` 或 `medium` | 排查问题、找 bug，以及复杂任务 |
| CodexL | `acp-codexl` | Astra（`gpt-6-astra`） | `low` 或 `medium` | 排查问题、找 bug，以及复杂任务 |
| Pi | `pi` | GLM 5.3 Flash（优先 `zai/glm-5.3-flash`） | `max` | 简单和中等任务 |
| Cursor | `acp-cursor` | Grok 4.6（`grok-4.6`） | `high` | 简单和中等任务 |

- **排查问题、找 bug 优先**：未指定工具时优先 Codex/CodexL，即使问题看起来简单，也不按下面的普通任务规则分给 Pi 或 Cursor。已有 CodexL 偏好或上下文时用 CodexL，否则默认 Codex。
- **其他简单任务**：局部改动、明确步骤、容易验证。未指定工具时优先 Pi。
- **其他中等任务**：范围明确、涉及少量模块、方案较清楚。未指定工具时仍优先 Pi；用户偏好 Cursor 或任务已有 Cursor 上下文时选 Cursor。
- **复杂**：跨模块设计、难复现问题、较多不确定性或约束。未指定工具时优先 Codex；用户指定 CodexL 时使用 CodexL。
- Astra 选 `low`：排查范围局部、复现明确、线索集中；或方案、边界和验收已经清楚，主要是按既定方案实现。选 `medium`：问题难复现、根因不明、多个假设需验证，或涉及设计取舍、跨模块约束。按分析难度选择，不因出现“bug”或“排查”就一律选 `medium`。默认策略最高为 `medium`，不因任务难就自行升到更高档。
- 难度是未指定配置时的推荐依据；用户指定 Pi、Cursor、Codex 或 CodexL 时保留其选择，不按难度擅自换工具。

## 将推荐变成准确的启动参数

1. 用 `bb status --json` 确认上下文；缺少项目或环境时从 BB 查询并匹配用户指定的目标，不猜 ID。默认沿用目标现有环境。
2. 在目标环境执行 `bb provider list --environment <environment-id> --json`，确认选中的精确 ID 存在且可用，然后执行 `bb provider models <provider-id> --environment <environment-id> --json`。按模型名称匹配目录中的精确 ID，核对推理级别；需要 provider 前缀的模型 ID 原样保留。
3. **模型列表返回成功不代表 provider 有效。** 先以 provider 列表校验 ID；BB 某些版本对未知 provider 仍返回模型列表。目标模型或级别缺失、匹配有歧义时，说明具体缺口并询问替代选择，不静默换模型、升级推理或修改插件配置。
4. 简短说明任务难度和选择理由。启动时显式传入 `--provider`、`--model`、`--reasoning-level`，避免项目记忆默认值覆盖推荐。BB 操作细节按可用的 `bb-cli` 技能或 `bb thread spawn --help` 查询；本技能不改变权限、分支或 worktree 策略。

启动参数示例（先解析项目与环境 ID）：

```bash
bb thread spawn --project <project-id> --environment <environment-id> \
  --provider acp-codexl --model gpt-6-astra --reasoning-level medium \
  --prompt '<任务目标、范围与验收要求>' --json
```

派发后用 `bb thread show <thread-id> --json` 核对实际配置与状态，报告线程 ID、provider、模型、推理级别和选择理由。排队或 provisioning 尚未完成时如实报告；不要仅凭创建成功声称任务已经运行，也不要重复派发。
