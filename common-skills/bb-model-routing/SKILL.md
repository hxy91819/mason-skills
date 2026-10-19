---
name: bb-model-routing
description: 用户显式调用 $bb-model-routing 并要求通过 BB 派发任务时使用，按配置创建 BB 任务线程；缺少派发配置时先检测 BB provider 与模型，引导用户确认并生成配置。常规任务、默认 subagent 调用及仅查看已有线程不触发。
disable-model-invocation: true
triggers:
  - user
---

# BB 任务派发

<!-- 触发条件集中在 description，避免重复维护。 -->

## 派发入口

Agent 自行决定使用 subagent，或用户只要求“用 subagent 检查一下”时，沿用宿主默认机制。查看或继续已有线程沿用现有上下文。

为用户已要求的任务调用 `scripts/bb-dispatch`。工具别名、模型、推理级别和环境映射以用户配置为准。派发前确认配置文件存在，`bb-dispatch` 报“无法读取配置”时也先核对该路径：文件确实不存在才进入 bootstrap，按[首次配置引导](references/bootstrap.md)边汇报进度边检测可用 provider 与模型，给出建议配置，经用户确认后写入并 dry-run 验证，再回到派发；文件存在但读不了是配置损坏，报告并修复，不新建覆盖。调整已有映射时读取[配置与派发](references/dispatch.md)。参数细节查 `bb-dispatch --help`。

## 判断与调用

难度只量一件事：任务的**不确定性**，即子线程开工时还不知道、必须自己弄清或裁决的东西。工作量、文件数、测试数、任务描述篇幅、“需要完整验证”，以及风险高低、缺陷级别、操作哪个环境、任务多重要、预算多宽，都在这个维度之外：当前模型能可靠执行高风险操作，风险由任务里的授权范围和审查规则控制。

每个任务单独判断，同一批任务也逐个归档：

1. 用一句话说出任务的**最大未知**：按父 agent 掌握的实际情况，子线程拿到任务时还不知道、必须自己弄清或裁决的那件事。
2. 按最大未知归档，拿不准时把最大未知说得更具体再对照：
   - `simple`：说不出最大未知。做什么、改哪里、怎么算完成都已写进任务文本，失败模式可预期（测试不过就修到过）。典型：按明确说明实现功能（代码量可以很大）、编写或执行既有测试、机械迁移、同步文档与配置。
   - `medium`：最大未知有边界，子线程能在圈定范围内把它闭合：要比较或探索方案、先做 POC 才能定实现路径；要在外部系统或服务上自己摸索交互步骤和异常分支；缺陷已复现、范围已圈定到某条链路或几个模块，根因未定位；验收标准要子线程自己补全或判断（“看是否可行”）。
   - `complex`：最大未知没有边界，任务本身又跨多个系统：根因连出在哪个系统都不知道；要在父 agent 尚未裁决的多个可行方案之间做跨系统的设计或架构取舍；父 agent 自己解决不了、要请专家咨询（Oracle）或裁决互相矛盾的结论（Judge）。
3. 只有一部分带未知时，把已闭合的实现、文档或固定清单验收拆出去按 `simple` 派，未知部分单独归档。

常见任务的对照：

- 在测试环境按清单逐项实测、缺陷只记录：步骤已写死是 `simple`；要子线程自己构造场景（注入故障、造坏数据、准备多账号）是 `medium`。
- 修复缺陷：根因已定位是 `simple`；只知道症状和所在链路是 `medium`。
- 按既定流程构造制品、发布或部署：`simple`；流程第一次跑、要边做边定步骤是 `medium`。
- 审查：需求与验收条件明确的闭合改动、修复后的增量补审是 `simple`；跨模块状态机、并发或安全边界的深度审查是 `medium`。
- 多个服务联动出错，没有复现也没有报错，不知道在哪一层：`complex`。

父 agent 派发前查清改法、定好接口与架构裁决、或把外部系统的交互步骤写死，这部分不确定性就已消化，按剩下的最大未知归档。保留不确定性直接派 `medium`，是把探索成本转给子线程，只在父 agent 自己探索更贵时才这么做。

升档的依据有两种：同一任务此前的低档线程失败、反复返工或产出需要大量纠正，这时传入 `--escalate-from <前序线程ID>` 并在派发报告里说明；或者用户点名要求某个任务用哪一档。

脚本内置两项确定性分档门禁：
- 传入 `--closed-scope` 声明边界已闭合时，强制要求 `--difficulty simple`（除非同时提供 `--escalate-from <前序线程ID>` 并通过存在性校验）。
- 传入 `--difficulty medium|complex` 且未提供 `--escalate-from` 时，有效任务指导长度（自动剥离 `autoreview` 审查标准、`ask-oracle` 证据块与 `large-task-orchestrator` 执行包/报告协议块）默认不得超过 `--max-task-chars 2500` 字符；超限说明父线程已完成细化，应改用 `simple` 或精简任务书。

```bash
bb-dispatch --difficulty simple --closed-scope --task '按 tests/ 既有用例验证登录流程，失败项修到通过'
bb-dispatch --difficulty medium --task '验证用 X 方案替换 Y 是否可行，给出 POC 与结论'
bb-dispatch --difficulty medium --escalate-from thr_xxx --task '<低档线程失败后升档重派的任务>'
bb-dispatch --difficulty complex --task '<已调查证据、待裁决问题与预期输出>'
```

`--task` 依 [派发任务模板](references/task-template.md) 填：目标、先读、开工前对齐远端、授权范围与根因位置、自行引入的决定必须单列、交付与验证、回复格式。`--task` 只写任务目标、范围、输入和验收要求。provider、模型、推理级别和可用性检查是派发元数据：由 `bb-dispatch` 根据配置和目录决定，不写入子线程 prompt，也不要求子 agent 在开始前重新查询或确认。用户明确要求改变 provider 或模型时，调整用户配置后再派发，仍不把路由要求带入 `--task`。

每次派发按 `defaults.<难度>` 选择候选；父 agent 只选择任务难度，provider 和模型由用户配置决定。脚本不接受 `--agent`，已有工具上下文也不构成绕过配置的例外。只有用户明确指定推理级别时才传 `--reasoning`；其余由脚本读取配置。配置未指定时省略该参数，使用 provider 默认值。命令未安装时直接执行本技能的 `scripts/bb-dispatch`。需要预览用 `--dry-run`，脚本已完成的环境与模型校验无需重复查询。

## 派发边界

所有 provider、模型、推理级别和默认路由均来自用户配置；脚本在创建前完成相应目录校验。父 agent 只负责选择任务难度，不能把路由选择或二次校验职责下放给子 agent。缺少配置时先走 bootstrap，三档 dry-run 通过后再派发。

`defaults.<难度>` 默认使用 fallback：单个别名固定选择，有序别名链按序校验并派发首个可用候选。需要分摊独立任务时配置 `mode: load-balance`；需要按额度比例分摊时配置 `mode: weighted-load-balance`，并把 `candidates` 写成“别名: 非负权重”映射，`0` 表示暂停该候选，抽选与 fallback 均跳过；至少保留一个正权重候选。脚本按难度与完整任务文本做稳定散列来排列候选，不维护共享计数，同一任务可复现选择与 fallback 顺序。每个候选只按本次难度或显式 `default` 解析自己的 `routes`；缺少两者时跳过该候选。候选全部不可用时汇总各候选错误报告；spawn 发出后不重试，spawn 失败的候选随即冷却，确认线程未创建后重跑同一命令就会换下一个候选。具体格式和负载均衡续派约束见[配置与派发](references/dispatch.md)。

每次派发本来就是独立 BB 会话，负载均衡不会拆分会话上下文。不要额外规避前缀缓存；但不同 provider 或模型之间也不假定共享缓存。

权限须符合任务授权；配置缺失或校验失败时说明缺口，不静默换模型或升权。

派发标题由脚本按难度加前缀：`simple` 为 🟢、`medium` 为 🟡、`complex` 为 🔴；需要简短标题时传 `--title`，省略时从任务文本截取。

根据返回结果报告线程 ID、实际选择和状态；发生 fallback 时说明链上失败原因与实际候选。创建成功不代表任务完成；创建结果不明时先查询线程，避免重复派发。

## 等待与并发

等待由 BB 的通知驱动，不靠轮询。子线程回合完成、失败或被中断时，BB 会向父线程投递系统通知（父线程忙时先排队，空闲时作为新回合送达，内容含子线程最终输出摘要）；子线程卡在待处理交互时另有求助通知。脚本在父子同项目时自动关联父线程，通知沿这条关联回到父线程。用户可能直接在子线程里对话并改变其授权或方向；通知会标明该回合是否由用户直接发起，此时以用户对子线程的指令为准，不要据此发出纠正、停止或重派指令，除非用户要求。派发后结束当前回合或转做其他工作，收到通知再读取结果、决定下一步；`bb thread wait` 循环、反复 `show` 或 sleep 后重查都属于多余的轮询，只在创建结果未知等需要立即确认时查询一次。

子线程每条中途消息都会唤醒或打断父线程，所以关联父线程时脚本在任务末尾附加固定的「回报方式」：进度、阶段发现和新建资源留到回合结束按任务要求一次交代，需要即时留底的写进工作区文件。任务确需中途汇报时在 `--task` 里写明，正文优先；续派时直接复用子线程首条消息也可以，脚本会先去掉这段，候选顺序不变。子线程仍发来只含进度的中途消息（`[bb message from thread:…]`，不是完成通知）时，不回复、不复述，一句话结束回合，其中的事实等最终回复一并处理；同一子线程反复发送时，用 `bb thread tell` 提醒它一次。

子线程因 provider 不可用、额度耗尽或会话错误而报错时，运行 `bb-dispatch --on-failure <线程ID>`，按返回的 `action` 处理，全程不用判断失败类型。重试分两层：先在原会话退避重试，偶发错误在这一层消化，上下文和已完成的工作都还在；用尽才计入派发冷却。`waiting` 表示 BB 已排了自动重试（它只管过载与限流），`retry-scheduled` 表示脚本已用 BB 定时重试在原会话安排下一次（1、2、4 分钟各一次），两者都结束回合等通知，再报错就再跑同一命令；`cooled` 表示原会话重试用尽，或 BB 已重试到上限、判定额度短期回不来，脚本已记失败并冷却该 provider 与模型，这时用原 difficulty 与完整任务文本重跑 `bb-dispatch` 就会换候选，失败线程已有部分产出时，创建成功后通过 `bb thread tell` 补充进展与位置；`not-failed` 表示线程已恢复，照常等通知。BB 的自动重试要等太久时，先 `bb provider-retry cancel <线程ID>`，再用 `--record-decision <线程ID> --outcome failed` 记失败后改派，免得同一任务做两遍。这区别于任务被拒、正常完成或待处理交互——那些不是路由失败，不重试也不改派。同一任务换过候选仍失败就如实报告，不循环改派。

并行前按任务性质分流：

- 只读任务（调研、审查、检索、验证）不改动共享状态，可以连续派发、并行执行。
- 写入任务先看依赖：后一个任务消费前一个任务的产出时，按依赖顺序串行派发，等前一个的完成通知到达后再派下一个；只有彼此独立、写入目标不重叠的写入任务才并行。

并发写入可能产生修改冲突时，用 `use-worktree` 隔离；无冲突时沿用当前环境。操作前检查分支、工作区和 worktree，遵守用户授权。隔离 worktree 准备好后可把目录路径传给 `--environment`，由 BB 创建附着环境。

## 作为编排后端

`large-task-orchestrator` 的确定性 driver 通过 `bb-dispatch` 派 Worker、Validator 与异常时的 Judge：Worker 按
能力档映射为 `--difficulty`，Validator 固定 `--difficulty simple`，Judge 固定 `--difficulty complex`。
driver 只传任务文本、难度与已有环境，路由仍由本配置决定；状态机、wait/output/tell 兼容性见其
所属 `$large-task-orchestrator` 的 `references/bb-dispatch-loop.md`；需要该契约时由宿主加载目标 Skill，不按 sibling 路径读取。driver 是脚本状态机，
用 `bb thread wait` 阻塞等待并自带 stall 处理，与会话内父 agent 的通知路径相互独立。

三类线程都只使用 `simple`、`medium`、`complex` 难度路由。`agents.<别名>.routes` 按难度和 `default` 项配置模型与 reasoning，选择规则见[配置与派发](references/dispatch.md)。

## 可观测性

脚本在本地 Git-ignored 路径 `~/.cache/bb-dispatch/ledger.json`（可通过 `--ledger` 或 `BB_DISPATCH_LEDGER_PATH` 覆盖）维护运行账本与熔断冷却表，读写异常旁路告警、绝不阻塞主派发：

1. **最小事实与滚动折算**：每次派发仅记录 `id`、`ts`、`difficulty`、`agent`、`provider`、`model`、`reasoning`、`task_chars`、`outcome`、`outcome_ts`、`retries`、`decision`，不存任务正文、diff 或日志。live 窗口保留最近 200 条，48 小时内的条目还要识别终态、计算冷却，超出也照留；更早的超出部分自动折算进固定维度 `rollups`，live 与 rollup 不重复计数。账本读改写加文件锁，写入前重读合并，并行派发与回写互不覆盖。
2. **两层退避的熔断冷却与决策回环（Circuit Breaker）**：两层都不读报错文字、不分失败类型。原会话一层由 `--on-failure` 负责：BB 已排自动重试时不插手，否则按 1、2、4 分钟在原会话重试，用尽（或 BB 已重试到上限、判定额度短期回不来）才记 `failed`，细则见[配置与派发](references/dispatch.md)。派发一层按 provider 与模型冷却，只看 48 小时内的终态：首次失败冷却 15 分钟，冷却期内的失败只顺延，冷却结束后再失败才翻倍，最长 6 小时，成功一次清零；每次派发先读一次 `bb thread list`，把 48 小时内仍记为 `spawned`、已空闲且没有排队消息和待处理交互的线程记为 `completed`，读不到时告警跳过。spawn 失败和被 `--fallback-from` 跳过的候选另冷却 15 分钟。冷却中的候选优先跳过，全部冷却时仍挑一个试，避免死锁。父 agent 用稳定线程 ID 回写裁决（未知 ID 拒绝报错，重复回写覆盖）；终态有误、或放弃任务要记失败时加 `--outcome`：
   ```bash
   bb-dispatch --on-failure <线程ID>
   bb-dispatch --record-decision <线程ID> --decision accepted
   bb-dispatch --record-decision <线程ID> --outcome failed --decision rejected
   ```
3. **聚合复盘与偏斜检测**：运行 `bb-dispatch --history-summary`（或 `--stats`）只读输出（同样先按线程状态补齐终态，但不写账本）按难度占比、各候选失败率/接受率、当前活跃冷却及确定性复盘 hooks（`simple_share_low` 当总派发 $\ge 5$ 且 `simple` 占比 $<20\%$、`high_failure_rate` 当候选失败率 $\ge 30\%$、`low_acceptance_rate` 当候选接受率 $<50\%$）。派发时若触发复盘 hook，返回 JSON 的 `selection.warnings` 会同步携带提醒。
