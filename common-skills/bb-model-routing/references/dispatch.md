# 配置与派发

依赖 Python 3.10+、PyYAML、PATH 中的 `bb`。入口为技能目录内的 `scripts/bb-dispatch`，也可将它软链为用户命令 `~/.local/bin/bb-dispatch`。

## 首次配置与迁移

配置路径优先级：`--config` > `BB_DISPATCH_CONFIG` > `~/.config/bb-dispatch/config.yaml`。先读取已有配置；没有时，以 [config.example.yaml](config.example.yaml) 为模板创建用户配置。模板中的尖括号值必须替换，不能直接派发。配置不含凭据，认证由 BB provider 管理。

先使用以下只读命令发现目标环境实际提供的能力（ID 使用返回值）：

```bash
bb status --json
bb provider list --environment <environment-id> --json
bb provider models <provider-id> --environment <environment-id> --json
```

从可用 provider 中选择符合用户要求的模型，检查 `permissionModes` 和模型的 `supportedReasoningEfforts`；多个候选缺乏选择依据时询问用户。目录能证明可用性，不能证明价格和任务质量。将选择写入任意别名，例如 `primary`，然后配置各难度、debug、test 和 judge 的默认别名；不要求安装特定 provider 或购买特定渠道。

配置格式为 `version: 2`。迁移时把扁平的 `agents.<别名>.model/reasoning` 移到 `agents.<别名>.routes.<路由>`；同一 provider 的不同模型、难度和角色保留在这个别名下。脚本不接受旧格式。配置服务多个环境时使用 `environments` 覆盖。脚本只读取配置，不安装 provider 或覆盖配置。新配置先运行 `--dry-run` 验证，再派发。模型目录不会自动生成用户的模型偏好。

## 派发与配置规则

```bash
bb-dispatch --difficulty simple --task '补充 README 示例' --dry-run
bb-dispatch --difficulty medium --kind debug --task '定位登录失败，给出复现和修复'
bb-dispatch --difficulty medium --kind test --task '验证用户登录与权限判定测试用例' --dry-run
bb-dispatch --difficulty complex --kind judge --task '根据 Worker 失败证据裁决下一步动作' --dry-run
bb-dispatch --difficulty medium --agent primary --task '执行已授权的任务' --dry-run
```

`--task` 只传递任务本身：目标、范围、必要输入和验收要求。provider、模型、推理级别、权限和目录校验由脚本和配置处理，不能写进子线程 prompt，也不要求子 agent 重复检查。用户直接给出 provider 或模型要求时，调用方须把它转换为匹配的配置别名或配置变更，再调用脚本。

默认权限为 `accept-edits`。用户可在顶层或环境配置中设置已授权的 `permission_mode`；权限不兼容时报告错误，不自动升级。

配置 `version: 2`。`defaults` 将 simple/medium/complex/debug/test/judge 映射到 provider 别名；每个 `agents.<别名>` 只写一次 `provider`，并在 `routes.<路由>` 中为每个难度或角色写 `model` 与可选的 `reasoning`。同一 provider 因而可按难度选择不同模型，且无需为模型组合创建别名。显式 reasoning 仍须通过模型目录校验；省略或设为 null 时使用 provider 默认值。

路由解析顺序为 `debug`、`test`、`judge` 等角色项，其次是 `simple`、`medium`、`complex` 难度项，最后才是可选 `default` 项。例如 Validator 固定传 `simple --kind test`，所以优先选 `routes.test`；若配置只有 `routes.simple`，才选它。没有任何匹配项会报错，不会猜测模型。所有 `defaults` 键都是显式配置，Judge 不再自动沿用 complex。

优先级：命令行覆盖 > 环境配置 > 顶层配置。`--kind debug|test|judge` 先决定 defaults 和 routes 的角色项，`--agent` 覆盖 defaults；它仍使用本次的 kind 和 difficulty 选择该 agent 的 routes。`environments.<精确环境 ID>` 可覆盖 defaults、agents、permission_mode；同名 agent 整体替换，必须写出 provider 和 routes。脚本不从任务文本猜测类型；调用 Agent 负责识别排障、测试或编排异常裁决任务。模型和思考深度的明确要求用配置别名、`--reasoning` 表达，缺失配置时先补齐，不静默替换。

默认从 `bb status` 解析环境，项目使用该环境的所属项目。`--project` 和 `--environment` 可显式指定，但必须匹配；只使用现有环境，不建分支或 worktree。同项目同环境时关联当前父线程。

每次调用会校验 provider 是否存在且可用、权限是否兼容、模型及 reasoning 是否在目录中。`--dry-run` 同样执行只读校验并输出参数数组，不创建线程。实际派发返回 JSON 的 `selection` 和 BB 原始 `result`，只调用一次 spawn；超时或响应异常时先查线程，避免重复创建。目录不做持久缓存，防止安装、账号或环境变化后继续使用过期配置。

验证：`python3 -m unittest discover -s scripts -p 'test_*.py'`（从技能目录运行）。

## 路由不可用

脚本不自动 fallback。provider 不可用、模型被移除或额度耗尽时，报告原路由和错误；用户选定替代别名后重新校验。创建结果未知时先查询原线程，避免重复派发。继续已有线程前，确认原回合结束并核对已完成工作，按该 provider 支持的续接方式操作；不要以重新创建整个任务冒充续接。

## 会话标题

脚本创建的会话统一以 `[Agent] ` 开头。`--title` 指定正文；省略或仅空白时使用任务文本。脚本折叠空白、移除重复前缀，正文最多 80 字符（含省略号）。创建命令始终传 `--title`，`selection.title` 返回实际提交的标题。建议传简短标题，避免任务细节直接出现在会话列表。前缀只标识经此脚本派发的会话，不代表所有 Agent 发起的会话；后续显式重命名仍可改变标题。
