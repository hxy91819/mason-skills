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

从可用 provider 中选择符合用户要求的模型，检查 `permissionModes` 和模型的 `supportedReasoningEfforts`；多个候选缺乏选择依据时询问用户。目录能证明可用性，不能证明价格和任务质量。将选择写入任意别名，例如 `primary`，然后配置各难度和 debug 的默认别名；不要求安装特定 provider 或购买特定渠道。

迁移时保留已有别名和无关设置，将失效路由替换为目标环境的实际 ID；同一配置服务多个环境时使用 `environments` 覆盖。脚本只读取配置，不安装 provider 或覆盖配置。新配置先运行 `--dry-run` 验证，再派发。模型目录不会自动生成用户的模型偏好。

## 派发与配置规则

```bash
bb-dispatch --difficulty simple --task '补充 README 示例' --dry-run
bb-dispatch --difficulty medium --kind debug --task '定位登录失败，给出复现和修复'
bb-dispatch --difficulty medium --agent primary --task '执行已授权的任务' --dry-run
```

默认权限为 `accept-edits`。用户可在顶层或环境配置中设置已授权的 `permission_mode`；权限不兼容时报告错误，不自动升级。

配置 `version: 1`。`defaults` 将 simple/medium/complex/debug 映射到工具别名，`agents` 为别名定义 provider/model/reasoning。reasoning 可省略或设为 null，也可以是固定字符串或按 simple/medium/complex 配置的映射；映射中缺失的难度使用 provider 默认值。显式值仍须通过模型目录校验。`environments.<精确环境 ID>` 可覆盖 defaults、agents、permission_mode；同名工具配置整体替换，必须写出 provider 和 model；reasoning 可省略或设为 null，表示使用 provider 默认值。无环境覆盖时使用顶层配置；实际可用性仍向目标环境校验。

优先级：命令行覆盖 > 环境配置 > 顶层配置。`--kind debug` 优先难度路由，`--agent` 优先 debug。脚本不从任务文本猜测类型；调用 Agent 负责识别排障任务。模型和思考深度的明确要求用配置别名、`--reasoning` 表达，缺失配置时先补齐，不静默替换。

默认从 `bb status` 解析环境，项目使用该环境的所属项目。`--project` 和 `--environment` 可显式指定，但必须匹配；只使用现有环境，不建分支或 worktree。同项目同环境时关联当前父线程。

每次调用会校验 provider 是否存在且可用、权限是否兼容、模型及 reasoning 是否在目录中。`--dry-run` 同样执行只读校验并输出参数数组，不创建线程。实际派发返回 JSON 的 `selection` 和 BB 原始 `result`，只调用一次 spawn；超时或响应异常时先查线程，避免重复创建。目录不做持久缓存，防止安装、账号或环境变化后继续使用过期配置。

验证：`python3 -m unittest discover -s scripts -p 'test_*.py'`（从技能目录运行）。

## 路由不可用

脚本不自动 fallback。provider 不可用、模型被移除或额度耗尽时，报告原路由和错误；用户选定替代别名后重新校验。创建结果未知时先查询原线程，避免重复派发。继续已有线程前，确认原回合结束并核对已完成工作，按该 provider 支持的续接方式操作；不要以重新创建整个任务冒充续接。
