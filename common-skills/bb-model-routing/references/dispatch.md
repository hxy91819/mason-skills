# 配置与派发

依赖 Python 3.10+、PyYAML、PATH 中的 `bb`。入口为技能目录内的 `scripts/bb-dispatch`，也可将它软链为用户命令 `~/.local/bin/bb-dispatch`。

## 首次配置与迁移

配置路径优先级：`--config` > `BB_DISPATCH_CONFIG` > `~/.config/bb-dispatch/config.yaml`。文件不存在时按[首次配置引导](bootstrap.md)检测环境、给出建议并经用户确认后写入；调整已有映射时复用引导第 1 步的只读命令查看目标环境实际提供的 provider 与模型（ID 使用返回值），检查 `permissionModes` 和模型的 `supportedReasoningEfforts`，多个候选缺乏选择依据时询问用户。目录能证明可用性，不能证明价格和任务质量。结构以 [config.example.yaml](config.example.yaml) 为准，尖括号值必须替换，不能直接派发；将选择写入任意别名，例如 `primary`，然后配置各难度的默认别名。配置不含凭据，认证由 BB provider 管理。

配置格式为 `version: 2`。迁移时把扁平的 `agents.<别名>.model/reasoning` 移到 `agents.<别名>.routes.<难度>`；同一 provider 的不同模型和难度保留在这个别名下。脚本不接受旧格式。配置服务多个环境时使用 `environments` 覆盖。脚本只读取配置，不安装 provider 或覆盖配置。新配置先运行 `--dry-run` 验证，再派发。模型目录不会自动生成用户的模型偏好。

## 派发与配置规则

```bash
bb-dispatch --difficulty simple --task '补充 README 示例' --dry-run
bb-dispatch --difficulty medium --task '定位登录失败，给出复现和修复'
bb-dispatch --difficulty simple --task '验证用户登录与权限判定测试用例' --dry-run
bb-dispatch --difficulty complex --task '审查证据并裁决指定的技术问题' --dry-run
```

`--task` 只传递任务本身：目标、范围、必要输入和验收要求。provider、模型、推理级别、权限和目录校验由脚本和配置处理，不能写进子线程 prompt，也不要求子 agent 重复检查。用户直接给出 provider 或模型要求时，调用方须调整用户配置，再调用脚本。

默认权限为 `accept-edits`。用户可在顶层或环境配置中设置已授权的 `permission_mode`；权限不兼容时报告错误，不自动升级。

配置 `version: 2`。`defaults` 将 simple/medium/complex 映射到路由。字符串或有序别名列表使用 `fallback`：脚本按配置顺序校验并派发首个可用候选。需要在候选间分摊独立任务时使用显式配置：

```yaml
defaults:
  simple:
    mode: load-balance
    candidates: [primary, backup]
```

`load-balance` 以路由项和完整任务文本做稳定散列，为每个任务排列等权候选。按额度比例分摊时使用权重映射：

```yaml
defaults:
  complex:
    mode: weighted-load-balance
    candidates:
      weekly-quota: 2
      monthly-quota: 1
      paused-quota: 0  # 额度恢复后改回正权重
```

`weighted-load-balance` 接受非负有限数字，`0` 表示暂停该候选：抽选、fallback 和 `--fallback-from` 均不会使用它，也不校验其 provider 或模型。每档至少需要一个正权重候选，全为 `0` 时明确报错。长期选择概率与正权重成比例；权重只表达相对比例，不代表并发上限。两种负载模式都不维护计数器，不同任务会分散，同一任务的选择和 fallback 顺序保持稳定。所有模式均在首选项校验失败时继续同档候选。每个 `agents.<别名>` 只写一次 `provider`，并在 `routes.<难度>` 或 `routes.default` 中写 `model` 与可选的 `reasoning`；缺少两者时跳过该候选，切换候选不改变难度。同一 provider 因而可按难度选择不同模型，且无需为模型组合创建别名。显式 reasoning 仍须通过模型目录校验；省略或设为 null 时使用 provider 默认值。

每次派发都会创建独立 BB 会话，负载均衡不会拆分或迁移同一会话的上下文。provider 的前缀缓存是否跨独立会话命中由 provider、账号和模型决定；候选落到不同 provider 或模型时不假定它们共享缓存。

路由项只由 `--difficulty simple|medium|complex` 决定；候选仅在存在该难度或显式 `default` 时参与。难度归类标准只在 SKILL.md「判断与调用」维护，本文不复述。没有任何匹配项会报错，不会猜测模型。

优先级：命令行覆盖 > 环境配置 > 顶层配置。候选始终由 defaults 决定，脚本不提供 `--agent` 覆盖入口。`environments.<精确环境 ID>` 可覆盖 defaults、agents、permission_mode；同名 agent 整体替换，必须写出 provider 和 routes。目录路径模式尚无环境 ID，不应用 `environments.<id>` 覆盖，只使用顶层配置。模型的明确要求通过配置调整表达，思考深度的明确要求用 `--reasoning` 表达，缺失配置时先补齐，不静默替换。

`--fallback-from <别名>` 把本次候选截取为从该别名起的后缀，供需要点名续派候选的调用方使用；别名不在候选中时报错，点名的别名本身不按冷却跳过。实际派发时链上位于该别名之前的候选按 provider 与模型冷却 15 分钟。一般改派不必传它：`--on-failure` 记下失败或 spawn 失败后，该候选已冷却，重跑同一命令就会跳过。负载均衡续派须保持原 route 和完整 `--task` 文本，才能复现候选顺序；需要补充进展时，续派保留原任务文本，创建成功后通过 `bb thread tell` 向新线程补充进展与位置。

`--closed-scope` 声明任务边界已闭合（目标文件、改法、验证方式均已明确），未配合 `--escalate-from <线程ID>` 时强制要求 `--difficulty simple`。`--max-task-chars`（默认 2500，0 为不限制）对未传 `--escalate-from` 的 `medium`/`complex` 任务检查有效指导长度（自动剥离 `autoreview` 审查标准、`ask-oracle` 证据块及 `large-task-orchestrator` 执行包/报告协议块后的字符数），超长时拒绝派发并提示改用 `simple` 或精简任务书。

`--on-failure <线程ID>` 处理报错的子线程，只看 BB 的结构化信息：线程不在 `error` 状态返回 `not-failed`；线程有排队消息，或 `bb provider-retry status` 列出 BB 自动重试时返回 `waiting`；`bb provider-retry explain` 的结论是 `attempts-exhausted`（BB 已在原会话重试到上限）或 `beyond-maximum-wait`（额度重置超过它的最长等待）时不再重试；否则用 `bb thread retry --send-at` 在原会话安排下一次重试（1、2、4 分钟），返回 `retry-scheduled`，次数记在账本 `retries`，线程成功过又报错时从头计。重试用尽或无法重试时记 `failed`，返回 `cooled` 与当前冷却。只处理账本里的线程；配合 `--dry-run` 只给出动作，不安排重试、不写账本。

`--record-decision <线程ID>` 配合 `--decision {accepted,rejected,reworked,escalated}` 把父线程裁决覆盖回写到本地账本（默认 `~/.cache/bb-dispatch/ledger.json`）。`completed` 由脚本按 BB 线程状态自动记录，`failed` 由 `--on-failure` 在重试用尽后记录；识别有误或放弃任务时配合 `--outcome` 改正；旧值 `failed_quota`、`failed_transient`、`failed_other` 仍可写，与 `failed` 一样计入连续失败。只回写裁决不改终态时间，冷却不会因此顺延。`--history-summary`（别名 `--stats`）只读输出按难度与候选的聚合统计、活跃冷却及确定性复盘 hooks。

默认从 `bb status` 解析环境，项目使用该环境的所属项目。`--environment` 接受现有环境 ID 或本机已存在的目录路径：ID 模式下 `--project` 与环境所属项目必须匹配；路径模式下目录会解析为绝对路径并原样交给 BB 创建 project-checkout 附着环境，项目取 `--project` 或当前 `bb status`，两者都没有时须显式提供 `--project`。同项目时关联当前父线程，跨环境也保留关联；跨项目不关联。

每次调用会校验 provider 是否存在且可用、权限是否兼容、模型及 reasoning 是否在目录中。查询模型目录时同时传入配置中的 selected model，使刚发布但尚未进入普通目录的模型仍能由 provider 验证。ID 模式使用目标环境校验；路径模式不调用 `bb environment show`，而使用当前 `bb status` 的环境作为同 host 代理，没有当前环境时须在 BB 线程里运行或先准备可代理环境。返回 JSON 的 `selection.validation_environment` 记录实际校验环境，ID 模式下等于目标环境。`--dry-run` 同样执行只读校验并输出参数数组，不创建线程。实际派发返回 JSON 的 `selection` 和 BB 原始 `result`，每次调用最多发出一次 spawn（fallback 只发生在 spawn 前的校验阶段）；超时或响应异常时先查线程，避免重复创建。`selection.attempts` 记录链上失败候选及原因（含冷却中的候选），`selection.fallbacks` 记录未尝试的同档别名，`selection.reconciled` 列出本次按线程状态改记的终态。目录不做持久缓存，防止安装、账号或环境变化后继续使用过期配置。

验证：`python3 -m unittest discover -s scripts -p 'test_*.py'`（从技能目录运行）。

## 路由不可用

候选切换只覆盖派发前校验：provider 不存在或不可用、权限不兼容、模型或 reasoning 不在目录时，记录该候选错误并试下一个；全部失败时汇总各候选错误。spawn 一旦发出即不重试，失败的候选随即冷却：失败或结果不明时先 `bb thread list`/`bb thread show` 确认是否已创建，确认未创建后保持难度与任务文本重跑同一命令。线程运行期报错（额度耗尽、provider 中断、会话错误）按 SKILL.md「等待与并发」运行 `--on-failure`：原会话退避重试用尽才记失败、冷却该候选，再重跑同一命令换候选；确定性调用方（如编排 driver）也可持久化 `selection.fallbacks`，用 `--fallback-from` 自行点名。继续已有线程前，确认原回合结束并核对已完成工作，按该 provider 支持的续接方式操作；不要以重新创建整个任务冒充续接。

## 会话标题

脚本按 `--difficulty` 为标题加前缀：`simple` 为 `🟢 `、`medium` 为 `🟡 `、`complex` 为 `🔴 `。`--title` 指定正文；省略或仅空白时使用任务文本。脚本折叠空白，移除开头已有的旧 `[Agent]` 或难度圆点前缀，再加上本次难度的圆点；正文最多 80 字符（含省略号）。创建命令始终传 `--title`，`selection.title` 返回实际提交的标题。建议传简短标题，避免任务细节直接出现在会话列表。后续显式重命名仍可改变标题；已有线程不会自动改名。
