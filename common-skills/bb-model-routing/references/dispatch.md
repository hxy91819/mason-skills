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

`fast` 控制派发是否请求 BB 的 Fast service tier。省略时默认 `true`；人手改配置文件为 `false` 即关闭。脚本不提供命令行覆盖，也不接受模型侧选择。优先级：`agents.<别名>.fast` > 环境配置 `environments.<id>.fast` > 顶层配置 `fast`。打开且模型支持 fast 时传 `--service-tier fast`；关闭或模型不支持 fast 时，只要 provider 列出 service tiers（含 `default`）就显式传 `--service-tier default`，硬性覆盖项目历史记忆偏好；整个 provider 均不支持 service tiers 时才省略该参数。

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

优先级：命令行覆盖 > `agents.<别名>` 配置 > 环境配置 > 顶层配置。候选始终由 defaults 决定，脚本不提供 `--agent` 覆盖入口。`environments.<精确环境 ID>` 可覆盖 defaults、agents、permission_mode、fast；同名 agent 整体替换，必须写出 provider 和 routes。每个 agent 可通过 `fast: true|false` 单独控制是否开启 Fast。目录路径模式尚无环境 ID，不应用 `environments.<id>` 覆盖，只使用顶层配置。模型的明确要求通过配置调整表达，思考深度的明确要求用 `--reasoning` 表达，Fast 只改配置文件，缺失配置时先补齐，不静默替换。

`--fallback-from <别名>` 把本次候选截取为从该别名起的后缀，供需要点名续派候选的调用方使用；别名不在候选中时报错，点名的别名本身不按冷却跳过。实际派发时链上位于该别名之前的候选按 provider 与模型冷却 15 分钟。一般改派不必传它：`--on-failure` 记下失败或 spawn 失败后，该候选已冷却，重跑同一命令就会跳过。负载均衡续派须保持原 route 和完整 `--task` 文本，才能复现候选顺序；需要补充进展时，续派保留原任务文本，创建成功后通过 `bb thread tell` 向新线程补充进展与位置。

`--closed-scope` 声明任务边界已闭合（目标文件、改法、验证方式均已明确），未配合 `--escalate-from <线程ID>` 时强制要求 `--difficulty simple`。`--max-task-chars`（默认 2500，0 为不限制）对未传 `--escalate-from` 的 `medium`/`complex` 任务检查有效指导长度（自动剥离 `autoreview` 审查标准、`ask-oracle` 证据块及 `large-task-orchestrator` 执行包/报告协议块后的字符数），超长时拒绝派发并提示改用 `simple` 或精简任务书。

`--on-failure <线程ID>` 处理报错的子线程，只看 BB 的结构化信息：线程不在 `error` 状态返回 `not-failed`；`bb provider-retry status` 列出 BB 自动重试时返回 `waiting`。报错线程上的排队消息要等线程被重试才送出，不算已有重试。账本 `retries` 记当前这次故障已安排的原会话重试次数，`retry_ts` 记最近一次安排的时间；`retries` 大于 0 时读 `bb thread log`：那之后还没有回合结束，说明上次的重试还没执行，返回 `waiting`；那之后有回合成功结束，说明那次故障已恢复，这次从头计（派发补记 `completed` 时也清零）。`bb provider-retry explain` 的结论是 `attempts-exhausted`（BB 已在原会话重试到上限）或 `beyond-maximum-wait`（额度重置超过它的最长等待）时不再重试；否则用 `bb thread retry --send-at` 在原会话安排下一次重试（1、2、4 分钟），返回 `retry-scheduled`；BB 回复该回合已有排队的重试（`retry_already_queued`）时返回 `waiting`。重试用尽或无法重试时记 `failed`，返回 `cooled` 与当前冷却；重试期间不改终态，线程之前的成功照样为冷却清零。读不到线程状态或日志时报错退出，稍后重跑同一命令。只处理账本里的线程；配合 `--dry-run` 只给出动作，不安排重试、不写账本。

`--record-decision <线程ID>` 配合 `--decision {accepted,rejected,reworked,escalated}` 把父线程裁决覆盖回写到本地账本（默认 `~/.cache/bb-dispatch/ledger.json`）。`completed` 由脚本按 BB 线程状态自动记录，`failed` 由 `--on-failure` 在重试用尽后记录；识别有误或放弃任务时配合 `--outcome` 改正；旧值 `failed_quota`、`failed_transient`、`failed_other` 仍可写，与 `failed` 一样计入连续失败。只回写裁决不改终态时间，冷却不会因此顺延。`--history-summary`（别名 `--stats`）只读输出按难度与候选的聚合统计、活跃冷却、确定性复盘 hooks，以及复盘日志 `ledger.events.jsonl` 近 7 天的重试与冷却汇总 `retry_review`（字段见 SKILL.md「可观测性」）。

默认从 `bb status` 解析环境，项目使用该环境的所属项目。`--environment` 接受现有环境 ID 或本机已存在的目录路径：ID 模式下 `--project` 与环境所属项目必须匹配；路径模式下目录会解析为绝对路径并原样交给 BB 创建 project-checkout 附着环境，项目取 `--project` 或当前 `bb status`，两者都没有时须显式提供 `--project`。在 BB 线程里派发时关联当前父线程，跨环境、跨项目都保留关联。

每次调用会校验 provider 是否存在且可用、权限是否兼容、模型及 reasoning 是否在目录中。查询模型目录时同时传入配置中的 selected model，使刚发布但尚未进入普通目录的模型仍能由 provider 验证。ID 模式使用目标环境校验；路径模式不调用 `bb environment show`，而使用当前 `bb status` 的环境作为同 host 代理，没有当前环境时须在 BB 线程里运行或先准备可代理环境。返回 JSON 的 `selection.validation_environment` 记录实际校验环境，ID 模式下等于目标环境。`--dry-run` 同样执行只读校验并输出参数数组，不创建线程。实际派发返回 JSON 的 `selection` 和 BB 原始 `result`，每次调用最多发出一次 spawn（fallback 只发生在 spawn 前的校验阶段）；超时或响应异常时先查线程，避免重复创建。`selection.attempts` 记录链上失败候选及原因（含冷却中的候选），`selection.fallbacks` 记录未尝试的同档别名，`selection.reconciled` 列出本次按线程状态改记的终态。目录不做持久缓存，防止安装、账号或环境变化后继续使用过期配置。

验证：`python3 -m unittest discover -s scripts -p 'test_*.py'`（从技能目录运行）。

## Provider 并发限制

在 `agents.<别名>` 配置 `max_concurrency: 1`（正整数，省略表示不限制）。默认限制该 provider 全部模型；可用 `concurrency_models` 指定共享名额的模型 ID。下面只让 amp 的 medium 与 complex 合计最多运行 1 个，simple 使用的 grok46 不限量：

```yaml
agents:
  amp:
    provider: acp-amp
    max_concurrency: 1
    concurrency_models: [medium, high]
    routes:
      simple: {model: grok46, reasoning: medium}
      medium: {model: medium, reasoning: medium}
      complex: {model: high, reasoning: medium}
```

名额按实际 provider ID 共享，不按别名、难度、项目或父线程拆分。`concurrency_models` 必须是非空模型 ID 列表，需同时配置 `max_concurrency`，列表中的模型合计共用上限，列表外的模型不受容量限制。同一份有效环境配置中多个别名指向同一 provider 时，取已配置上限的最小值、合并受限模型集合；任一配置上限的别名省略模型范围，则限制全部模型。环境同名别名仍整体替换，需在替换项中保留所需上限。多个调用者应使用一致的限额配置；未配置上限的脚本调用仍按原行为派发。

同一台机器、同一 OS 用户、同一个 BB 服务下的脚本进程，通过固定的 `~/.cache/bb-dispatch/concurrency.lock` 串行完成查询、占位和创建；`--config`、`--ledger` 与 `BB_DISPATCH_LEDGER_PATH` 不改变锁和占位的位置。不同机器或 OS 用户不共享限制。锁只保护一次创建，任务运行期间不持锁；锁繁忙约 10 秒后明确退出且不创建线程，稍后可重试。

派发前读取 `bb thread list --include-hidden` 的实时状态，默认所有该 provider 的活跃线程都计入占用（包括其他入口创建的线程）。配置模型范围时，仅明确登记为范围外模型的线程不计入该池；BB 列表不返回模型，脚本通过占位中的模型 ID 识别自己的派发。旧占位和其他入口的线程缺少模型信息时，仍保守计入受限池，待对应回合结束后释放；范围外新派发本身不做容量检查。已归档线程（`archivedAt` 非 null）不占名额，残留队列、交互和已登记占位一并排除。这里以归档为容量边界；BB 归档可给已有运行回合保留约 30 秒宽限，因此归档释放名额不代表运行时已立即停止。未归档线程的待处理交互、运行中和未知状态仍保守占名额；`idle` 只有明确无排队消息、无待处理交互才释放。`error` 且明确无待处理交互时，已知队列状态 `none`、`waiting`、`failed` 不占名额：普通排队消息须等失败回合被 retry 才会送出，排队本身不代表运行；未知队列状态仍计数。除归档直接释放外，脚本新建线程额外保留占位，直到日志中出现派发后的 `turn/completed`，避免创建后的初始 `idle` 被误判为完成。中断若没有结束事件，仍保留占位，由下述恢复命令处理。对活跃线程和对应占位去重计数。

候选满额时记录 `selection.attempts` 并尝试同档下一个候选；全部满额时明确报错，不等待、不创建队列、不计失败或熔断冷却。全部候选处于冷却、或用 `--fallback-from` 点名，也不能绕过容量限制。`selection.concurrency` 返回选中 provider 的 `limit` 和派发前 `used`，有模型范围时附带 `models`；范围外模型不返回容量限制。`--dry-run` 只读检查容量，不占位、不改并发状态，结果只是当时快照。

并发占位保存在同目录的 `concurrency.json`，独立于可旁路失败的统计账本，只保存占位 ID、provider、模型 ID、时间和线程 ID。范围外模型也登记占位，以便后续派发明确排除它们；它们不占用受限模型池。占位文件损坏、无法加锁或保存时明确失败；查不到实时线程状态时跳过受限候选。不会因为统计账本失败而取消限制。spawn 前先写占位，超时、异常或进程崩溃后不自动释放未知创建结果，避免重复派发：

```bash
bb-dispatch --concurrency-status
bb thread list --include-hidden --json
bb thread show <线程ID> --json
bb-dispatch --release-reservation <占位ID>
```

`--concurrency-status` 只读输出整个 provider 的实时占用与仍在占用的最小事实，不写状态；其中 `usage` 为所有模型的总量，模型范围实际用量以派发时的 `selection.concurrency.used` 为准，登记模型可在 `reservations` 中查看。确认该次创建未成功，或对应回合已经结束后，用稳定占位 ID 释放；未知 ID 拒绝，重复释放不会误删其他占位；配合 `--dry-run` 只预览。释放占位不会停止线程，仍活跃的线程继续由 BB 状态计数。正常结束的占位在后续派发时自动清理，未决占位持续保留供恢复，不按时间强制过期。

限制覆盖脚本的新建派发入口。旧线程继续对话、`--on-failure` 的原会话重试、BB 自动重试、直接创建线程不会先申请名额，仍可能与已派任务重叠；它们处于活跃状态时会影响下一次脚本派发。BB 已持久化线程状态、回合日志和父线程通知，可用 `bb thread show` / `bb thread log <线程ID> --all --json` 回看。此处只提供当前容量及恢复查询，不另建历史账本；并发等待时间与满额跳过次数暂不聚合，历史派发与质量裁决继续使用原有 `--history-summary`。

## 路由不可用

候选切换只覆盖派发前校验：provider 不存在或不可用、权限不兼容、模型或 reasoning 不在目录时，记录该候选错误并试下一个；全部失败时汇总各候选错误。spawn 一旦发出即不重试，失败的候选随即冷却：失败或结果不明时先 `bb thread list`/`bb thread show` 确认是否已创建，确认未创建后保持难度与任务文本重跑同一命令。线程运行期报错（额度耗尽、provider 中断、会话错误）按 SKILL.md「等待与并发」运行 `--on-failure`：原会话退避重试用尽才记失败、冷却该候选，再重跑同一命令换候选；确定性调用方（如编排 driver）也可持久化 `selection.fallbacks`，用 `--fallback-from` 自行点名。继续已有线程前，确认原回合结束并核对已完成工作，按该 provider 支持的续接方式操作；不要以重新创建整个任务冒充续接。

## 会话标题

脚本按 `--difficulty` 和候选 agent 为标题加前缀：
- **颜色代表难度**：`simple` 为绿色、`medium` 为黄色、`complex` 为红色。
- **形状代表账号**：通过 agent 配置的 `shape` 或默认别名映射识别：
  - 圆形（默认 / `codex`）：`🟢` / `🟡` / `🔴`
  - 方形（`codexl` / `codex-l` / `shape: square`）：`🟩` / `🟨` / `🟥`
  - 心形（`codexb` / `codex-b` / `shape: heart`）：`💚` / `💛` / `❤️`

`--title` 指定正文；省略或仅空白时使用任务文本。脚本折叠空白，移除开头已有的旧 `[Agent]`、难度圆点或形状前缀，再加上本次难度与账号对应的前缀；正文最多 80 字符（含省略号）。创建命令始终传 `--title`，`selection.title` 返回实际提交的标题。建议传简短标题，避免任务细节直接出现在会话列表。后续显式重命名仍可改变标题；已有线程不会自动改名。
