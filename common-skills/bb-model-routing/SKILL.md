---
name: bb-model-routing
description: 用户显式调用 $bb-model-routing 要求通过 BB 派发时，或已在运行的流程（bb-steward、large-task-orchestrator、autoreview、ppt-visual-review、ask-oracle 等）在正文中声明依赖时使用，按配置创建 BB 任务线程；缺少派发配置时先检测 BB provider 与模型，引导用户确认并生成配置。常规任务、未声明依赖的流程、默认 subagent 调用及仅查看已有线程不触发。
---

# BB 任务派发

<!-- 触发条件集中在 description，避免重复维护。 -->

## 派发入口

Agent 自行决定使用 subagent，或用户只要求“用 subagent 检查一下”时，沿用宿主默认机制。查看或继续已有线程沿用现有上下文。

为用户已要求的任务调用 `scripts/bb-dispatch`。工具别名、模型、推理级别和环境映射以用户配置为准。派发前确认配置文件存在，`bb-dispatch` 报“无法读取配置”时也先核对该路径：文件确实不存在才进入 bootstrap，按[首次配置引导](references/bootstrap.md)边汇报进度边检测可用 provider 与模型，给出建议配置，经用户确认后写入并 dry-run 验证，再回到派发；文件存在但读不了是配置损坏，报告并修复，不新建覆盖。调整已有映射时读取[配置与派发](references/dispatch.md)。参数细节查 `bb-dispatch --help`。

## 判断与调用

按下面的顺序判断，每个任务单独判，同一批也逐个判。风险高低本身不升档，升档只看②③④。

1. **① `complex`**：Oracle 或 Judge 角色；或者父线程说不出问题落在哪个系统，也列不出候选方案，且任务跨多个系统。Oracle / Judge 是角色例外，固定 `complex`，不受“说得出系统或候选方案就不归 complex”的检验。不是这两个角色时，能说出系统或候选方案之一就不归 `complex`。
2. **② `medium`**：测试通过不等于做对。包括并发、锁与崩溃恢复；租户或安全隔离边界的改动；下「可以发布/签字」结论；流程要求且没有第二审查人或 CI 兜底的唯一审查人（主 Agent 逐条核实不算第二审查人）。
3. **③ `medium`**：父线程写不出验收标准，说不出怎样算做完。
4. **④ 升一档**：同一任务的前序线程失败或返工，用 `--escalate-from <前序线程ID>` 升一档（`simple` → `medium` → `complex`，每次只升一档），并在派发报告里说明。升到 `complex` 时带这个凭证即可，不必再满足①的跨系统条件。
5. **⑤ 其余一律 `simple`**。包括执行发布与部署（有备份或回滚）、圈定的调研、可复现的缺陷定位、按清单验证、需求明确的审查。独立审查默认 `simple`；只有②里的唯一审查人条件才把审查定为 `medium`。执行发布/部署不是下发布签字结论：前者 `simple`，后者是②。

只有一部分属于②或③时，把其余部分拆出去按 `simple` 派，②③部分单独归档。④按整任务升档，不拆。

用户点名某一档时照办，仍过脚本门禁。点名 `complex` 时 `--unknown` 写「用户点名：<原因>」。点名 `medium` 时不传 `--closed-scope`。门禁拒绝时说明原因，请用户确认改档或补齐凭证。

常见任务对照（不另定条件，命中上面哪一条就用哪一档）：

- 圈定的调研或设计、可复现的缺陷定位或修复、按清单实测、扫描、比对或补登记：`simple`。
- 执行发布、部署或合并（按既定流程，或有备份或回滚）：`simple`。下「可以发布/签字」结论：`medium`。
- 需求明确的独立审查：`simple`。只有流程要求、且没有第二审查人或 CI 兜底时：`medium`。
- 父线程写不出怎样算做完：`medium`。
- Oracle、Judge，或多个系统联动出错、没有复现也没有报错、说不出在哪一层也列不出候选方案：`complex`。

用 `bb-dispatch --history-summary` 看各档接受率。

父 agent 不必为了降档先把改法、接口或交互步骤查清。后续任务按本清单重新归档：设计、根因或裁决已经完成时，落地、执行部署、补 PR、补登记和按清单验收是 `simple`。

用户可在 `projects.<BB项目ID>.min_difficulty` 配置项目下限；脚本自动抬升路由并保留请求难度，以下门禁按请求难度检查，详见[配置与派发](references/dispatch.md#项目最低难度)。

脚本内置三项确定性门禁，拒绝条件不因本节改口：

- 传入 `--closed-scope` 且未传 `--escalate-from` 时，强制 `--difficulty simple`。属于②的任务不传 `--closed-scope`；用户点名 `medium` 时也不传。
- 实际创建线程（非 `--dry-run`）的 `complex` 未传 `--escalate-from` 时，必须用 `--unknown` 写一句原因，截断后记入账本。用户点名 `complex` 时写成「用户点名：<原因>」。`--dry-run` 不要求。
- 未传 `--escalate-from` 的 `medium`/`complex`，有效任务指导（自动剥离 `autoreview` 审查标准、`ask-oracle` 证据块与 `large-task-orchestrator` 执行包/报告协议块）默认不得超过 `--max-task-chars 2500`。直接派②③且任务书确需超长时传 `--max-task-chars 0`，并在派发报告说明；不要为了过门禁改传 `--escalate-from`。

```bash
bb-dispatch --difficulty simple --closed-scope --task '按 tests/ 既有用例验证登录流程，失败项修到通过'
bb-dispatch --difficulty simple --task '问题已圈定：验证用 X 方案替换 Y 是否可行，给出结论与依据'
bb-dispatch --difficulty medium --task '改动租户隔离边界；测试通过不足以证明没有泄漏'
bb-dispatch --difficulty medium --escalate-from thr_xxx --task '<前序线程失败或返工后升一档>'
bb-dispatch --difficulty complex --unknown '用户点名：<原因>' --task '<待裁决问题与预期输出>'
```

`--task` 依 [派发任务模板](references/task-template.md) 填：目标、先读、开工前对齐远端、授权范围与根因位置、自行引入的决定必须单列、交付与验证、回复格式。`--task` 只写任务目标、范围、输入和验收要求。provider、模型、推理级别和可用性检查是派发元数据：由 `bb-dispatch` 根据配置和目录决定，不写入子线程 prompt，也不要求子 agent 在开始前重新查询或确认。用户明确要求改变 provider 或模型时，调整用户配置后再派发，仍不把路由要求带入 `--task`。

每次派发按 `defaults.<难度>` 选择候选；父 agent 只选择任务难度，provider 和模型由用户配置决定。脚本不接受 `--agent`，已有工具上下文也不构成绕过配置的例外。只有用户明确指定推理级别时才传 `--reasoning`；其余由脚本读取配置。配置未指定时省略该参数，使用 provider 默认值。`fast` 只看用户配置（省略默认 `false`，可在顶层配置也可在 `agents.<别名>.fast` 针对特定账号单独配置；周期临近重置或需临时突击使用时可在配置中加 `force_fast: true` 强制开启并豁免巡检熔断），人手改文件即可开关 Fast service tier；脚本不提供命令行覆盖。命令未安装时直接执行本技能的 `scripts/bb-dispatch`。需要预览用 `--dry-run`，脚本已完成的环境与模型校验无需重复查询。

## 派发边界

所有 provider、模型、推理级别、Fast service tier 和默认路由均来自用户配置；脚本在创建前完成相应目录校验。父 agent 只负责选择任务难度，不能把路由选择或二次校验职责下放给子 agent。缺少配置时先走 bootstrap，三档 dry-run 通过后再派发。

`defaults.<难度>` 默认使用 fallback：单个别名固定选择，有序别名链按序校验并派发首个可用候选。需要分摊独立任务时配置 `mode: load-balance`；需要按额度比例分摊时配置 `mode: weighted-load-balance`，并把 `candidates` 写成“别名: 非负权重”映射，`0` 表示暂停该候选，抽选与 fallback 均跳过；至少保留一个正权重候选。脚本按难度与完整任务文本做稳定散列来排列候选，不维护共享计数，同一任务可复现选择与 fallback 顺序。每个候选只按本次难度或显式 `default` 解析自己的 `routes`；缺少两者时跳过该候选。候选全部不可用时汇总各候选错误报告；spawn 发出后不重试，spawn 失败的候选随即冷却，确认线程未创建后重跑同一命令就会换下一个候选。具体格式和负载均衡续派约束见[配置与派发](references/dispatch.md)。

每次派发本来就是独立 BB 会话，负载均衡不会拆分会话上下文。不要额外规避前缀缓存；但不同 provider 或模型之间也不假定共享缓存。

权限按用户配置解析；原生 Codex 未指定权限时优先使用 Approve for me（`auto`），覆盖顺序见[配置与派发](references/dispatch.md)。配置缺失或校验失败时说明缺口，不静默换模型或升权。

派发标题由脚本按难度和账号加前缀：颜色代表难度（绿=简单/黄=中等/红=复杂），形状代表账号（圆=主号/方=L号/心=B号/书=M号）；需要简短标题时传 `--title`，省略时从任务文本截取。

根据返回结果报告线程 ID、实际选择和状态；线程 ID 在 `result.thread.id` 或 `result.id`（已知两种回执形状），先取前者，缺失再取后者。按标题回查线程时用包含匹配，因为标题带上述前缀。发生 fallback 时说明链上失败原因与实际候选。创建成功不代表任务完成；创建结果不明时先查询线程，避免重复派发。

## 等待与并发

需要限制某个 provider 的同时运行量时，在对应 `agents.<别名>` 配置 `max_concurrency`。脚本按 provider 跨难度和本机派发进程共享名额，可用 `concurrency_models` 指定共享上限的模型集合，范围外模型不限制；满额走同档 fallback，全部满额明确退出；创建结果不明时保留占位。已归档线程不占名额；未归档的 `error` 线程仅有等待 retry 的排队消息、明确无待处理交互时不占名额，运行中与待处理交互仍保守计数。配置、状态查询、恢复和限制范围见[配置与派发的并发限制](references/dispatch.md#provider-并发限制)。

等待由 BB 的通知驱动，不靠轮询。子线程回合完成、失败或被中断时，BB 会向父线程投递系统通知（父线程忙时先排队，空闲时作为新回合送达，内容含子线程最终输出摘要）；子线程卡在待处理交互时另有求助通知。脚本在 BB 线程里派发时自动关联当前父线程，跨环境、跨项目也保持关联，通知沿这条关联回到父线程。用户可能直接在子线程里对话并改变其授权或方向；通知会标明该回合是否由用户直接发起，此时以用户对子线程的指令为准，不要据此发出纠正、停止或重派指令，除非用户要求。派发后结束当前回合或转做其他工作，收到通知再读取结果、决定下一步；`bb thread wait` 循环、反复 `show` 或 sleep 后重查都属于多余的轮询，只在创建结果未知等需要立即确认时查询一次。

子线程每条中途消息都会唤醒或打断父线程，所以关联父线程时脚本在任务末尾附加固定的「回报方式」：进度、阶段发现和新建资源留到回合结束按任务要求一次交代，需要即时留底的写进工作区文件。任务确需中途汇报时在 `--task` 里写明，正文优先；续派时直接复用子线程首条消息也可以，脚本会先去掉这段，候选顺序不变。子线程仍发来只含进度的中途消息（`[bb message from thread:…]`，不是完成通知）时，不回复、不复述，一句话结束回合，其中的事实等最终回复一并处理；同一子线程反复发送时，用 `bb thread tell` 提醒它一次。

长任务（等 CI、等审查、分多批执行）每个回合结束都会唤醒父线程。这类任务派发时加 `--parent-notifications stuck`（或在配置顶层写 `parent_notifications: stuck`）：BB 只在子线程失败、被中断或等审批时自动唤醒父线程，脚本改附"只在要审批、要决定或卡住、阶段完成、发现越界问题时 `bb thread tell` 父线程"的回报方式。停摆仍由父线程的对账发现，不靠逐回合通知。

子线程因 provider 不可用、额度耗尽或会话错误而报错时，运行 `bb-dispatch --on-failure <线程ID>`，按返回的 `action` 处理，全程不用判断失败类型。重试分两层：先在原会话退避重试，偶发错误在这一层消化，上下文和已完成的工作都还在；用尽才计入派发冷却。`waiting` 表示已有重试排着：BB 的自动重试（覆盖 provider 过载、5xx/连接中断和带重置时间的额度窗口；用 `bb provider-retry explain` 看它为什么跳过），或上次安排的原会话重试还没执行；`retry-scheduled` 表示脚本已用 BB 定时重试在原会话安排下一次（1、2、4 分钟各一次），两者都结束回合等通知，再报错就再跑同一命令；`cooled` 表示原会话重试用尽，或 BB 已重试到上限、判定额度短期回不来，脚本已记失败并冷却该 provider 与模型，这时用原 difficulty 与完整任务文本重跑 `bb-dispatch` 就会换候选，失败线程已有部分产出时，创建成功后通过 `bb thread tell` 补充进展与位置；`not-failed` 表示线程已恢复，照常等通知。BB 的自动重试要等太久时，先 `bb provider-retry cancel <线程ID>`，再用 `--record-decision <线程ID> --outcome failed` 记失败后改派，免得同一任务做两遍。这区别于任务被拒、正常完成或待处理交互——那些不是路由失败，不重试也不改派。同一任务换过候选仍失败就如实报告，不循环改派。

并行前按任务性质分流：

- 只读任务（调研、审查、检索、验证）不改动共享状态，可以连续派发、并行执行。
- 写入任务先看依赖：后一个任务消费前一个任务的产出时，按依赖顺序串行派发，等前一个的完成通知到达后再派下一个；只有彼此独立、写入目标不重叠的写入任务才并行。

并发写入可能产生修改冲突时，用 `use-worktree` 隔离；无冲突时沿用当前环境。操作前检查分支、工作区和 worktree，遵守用户授权。隔离 worktree 准备好后可把目录路径传给 `--environment`，由 BB 创建附着环境。子线程的环境目录在回合内保持原样：沿用当前环境时它就是父线程的工作树；即使是专为子线程准备的目录，回合内删掉也会让回合报错、最终回复送不到父线程。任务书因此写明：要切分支就另建 worktree，由子线程自己清理；专用环境目录等父线程收到回复后再清理。

## 作为编排后端

`large-task-orchestrator` 的确定性 driver 通过 `bb-dispatch` 派 Worker、Validator 与异常时的 Judge：Worker 按
能力档映射为 `--difficulty`，Validator 固定 `--difficulty simple`，Judge 固定 `--difficulty complex`。
driver 只传任务文本、难度与已有环境，路由仍由本配置决定；状态机、wait/output/tell 兼容性见其
所属 `$large-task-orchestrator` 的 `references/bb-dispatch-loop.md`；需要该契约时由宿主加载目标 Skill，不按 sibling 路径读取。driver 是脚本状态机，
用 `bb thread wait` 阻塞等待并自带 stall 处理，与会话内父 agent 的通知路径相互独立。

三类线程都只使用 `simple`、`medium`、`complex` 难度路由。`agents.<别名>.routes` 按难度和 `default` 项配置模型与 reasoning，选择规则见[配置与派发](references/dispatch.md)。

## 可观测性

脚本在本地 Git-ignored 路径 `~/.cache/bb-dispatch/ledger.json`（可通过 `--ledger` 或 `BB_DISPATCH_LEDGER_PATH` 覆盖）维护运行账本与熔断冷却表，读写异常旁路告警、绝不阻塞主派发：

1. **最小事实与滚动折算**：每次派发仅记录 `id`、`ts`、`project`、`parent_thread`、`difficulty`、`requested_difficulty`、`agent`、`provider`、`model`、`reasoning`、`task_chars`、`outcome`、`outcome_ts`、`retries`、`retry_ts`、`decision`，填写时另记 `unknown`（截断到 120 字）与 `escalated_from`，不存任务正文、diff 或线程日志。live 窗口保留最近 200 条，48 小时内的条目还要识别终态、计算冷却，超出也照留；更早的超出部分自动折算进固定维度 `rollups`，live 与 rollup 不重复计数。账本读改写加文件锁，写入前重读合并，并行派发与回写互不覆盖。
2. **两层退避的熔断冷却与决策回环（Circuit Breaker）**：两层都不读报错文字、不分失败类型。原会话一层由 `--on-failure` 负责：已有重试排着时不插手，否则按 1、2、4 分钟在原会话重试，用尽（或 BB 已重试到上限、判定额度短期回不来）才记 `failed`，成功过又报错从头计，细则见[配置与派发](references/dispatch.md)。派发一层按 provider 与模型冷却，只看 48 小时内的终态：首次失败冷却 15 分钟，冷却期内的失败只顺延，冷却结束后再失败才翻倍，最长 6 小时，成功一次清零；每次派发先读一次 `bb thread list`，把 48 小时内还在等结果（仍记为 `spawned`，或成功过又在原会话重试）、已空闲且没有排队消息和待处理交互的线程记为 `completed`，读不到时告警跳过。spawn 失败和被 `--fallback-from` 跳过的候选另冷却 15 分钟。冷却中的候选优先跳过，全部冷却时仍挑一个试，避免死锁。父 agent 用稳定线程 ID 回写裁决（未知 ID 拒绝报错，重复回写覆盖）；终态有误、或放弃任务要记失败时加 `--outcome`：
   ```bash
   bb-dispatch --on-failure <线程ID>
   bb-dispatch --record-decision <线程ID> --decision accepted
   bb-dispatch --record-decision <线程ID> --outcome failed --decision rejected
   ```
3. **聚合复盘与偏斜检测**：运行 `bb-dispatch --history-summary`（或 `--stats`）只读输出（同样先按线程状态补齐终态，但不写账本）按难度占比、各候选失败率/接受率、当前活跃冷却及确定性复盘 hooks（`simple_share_low` 当总派发 $\ge 5$ 且 `simple` 占比 $<20\%$、`high_failure_rate` 当候选至少 3 次且失败率 $\ge 30\%$、`low_acceptance_rate` 当候选至少 3 次裁决且接受率 $<50\%$、`complex_share_high` 当某父线程至少 5 次派发、且最近至多 10 次里 `complex` $\ge 3$ 次且占比 $\ge 30\%$），`by_parent` 列出各父线程最近 10 次的分档。全局占比会被其他会话稀释，长会话的分档漂移看本父线程这一项。派发时 `selection.warnings` 携带全局 hook 与本父线程的 `complex_share_high`，并逐条写到 stderr，只取 stdout 线程 ID 时也看得到。
4. **复盘日志**：账本旁的 `ledger.events.jsonl` 只追加 `dispatch`（`diverted` 为因冷却绕开的候选）、`deferred`（交给 BB 自动重试）、`retry`、`recovered`、`cooled`（带原因与等级）五类事件，不存任务正文，超过 4 MB 丢掉较早的一半。`--history-summary` 的 `retry_review` 汇总近 7 天的计数、`retry_recovery_rate`（原会话重试过的故障里最终恢复的比例），以及按次数、原因、provider 与模型、日期的分布，用来判断重试是否奏效、冷却是否频繁、走势是否正常。
