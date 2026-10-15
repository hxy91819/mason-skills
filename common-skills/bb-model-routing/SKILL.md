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

难度衡量的是子线程执行中要自行消化多少不确定性，不是工作量。三档互斥，按定义归类，没有默认档；拿不准时回到定义核对，而不是保守选高档或省钱选低档。

`simple`：边界已闭合。做什么、改哪里、怎么算完成都已写进任务文本，子线程不需要做方案选择，失败模式可预期（测试不过就修到过）。典型：按明确说明实现功能（代码量可以很大）、编写或执行既有测试、按固定清单独立验收、对闭合边界改动或增量修复做代码审查、机械迁移、按已定位根因修 bug、按既定命令打包或部署、同步文档与配置。

`medium`：边界待闭合，子线程要自己把它闭合。任一条成立即属于此档：

- 需要比较或探索方案、先做 POC 才能确定实现路径；
- 需要与一个以上外部系统或服务交互且交互路径或异常分支未在任务中定死，需子线程自行探测与处理；
- bug 范围已圈定但跨多个模块或系统，根因未定位；
- 验收标准需要子线程自己补全或判断（“看是否可行”）。

`complex`：根因完全未定位且跨系统；跨系统设计或架构裁决；高影响且难以回退的技术决定；专家咨询与异常裁决（Judge）。

文件数、测试数、任务描述篇幅、“需要完整验证”都不是分档依据。父 agent 已经在派发前查清改法、定好接口与架构裁决、或把外部系统/部署的交互步骤写死时，不确定性已被父 agent 消化，任务就落到 `simple`（或把原本的 `complex` 降为 `medium`）；不能一边在父会话做完预调查、写出微操级任务文本，一边仍按任务名义复杂度选 `medium` 或 `complex`。避免把“探索方案 + 编码实现 + 部署运维 + 多轮审查”混包进同一个子线程而被动推高难度；能拆出闭合边界的实现、文档或固定清单验收时，拆开按 `simple` 派发。保留不确定性直接派 `medium`，是把探索成本转给子线程，只在父 agent 自己探索更贵时才这么做。

父 agent 可以根据实际情况在归类结果之上升档：同一任务此前的低档线程表现不佳（失败、反复返工、产出需要大量纠正）、用户对该任务提出了更高的质量要求、或父 agent 掌握的上下文表明不确定性比任务文本显示的更多。用户要求“高质量 / 不省 token”时，只对核心设计、疑难根因定位或最终把关升档；已拆出明确规格的编码、文档同步、增量补审和固定清单验收仍按实际不确定性归类，不把所有子任务一刀切锁死在 `complex`。升档时传入 `--escalate-from <前序失败线程ID>` 并在派发报告里说明依据；没有这类依据时按定义归类，不把升档当作保守默认。

脚本内置两项确定性分档门禁：
- 传入 `--closed-scope` 声明边界已闭合时，强制要求 `--difficulty simple`（除非同时提供 `--escalate-from <前序线程ID>` 并通过存在性校验）。
- 传入 `--difficulty medium|complex` 且未提供 `--escalate-from` 时，有效任务指导长度（自动剥离 `# Review agent 提示词` 固定审查标准）默认不得超过 `--max-task-chars 2500` 字符；超限说明父线程已完成细化，应改用 `simple` 或精简任务书。

同一个“验证”或“审查”按边界归类：按既有用例、固定清单执行的独立验收，以及需求与验收条件明确的闭合边界代码审查、修复后增量补审是 `simple`；跨模块状态机/并发边界未闭合的深度审查，或判断某个方案能否跑通的 POC 验证是 `medium`。

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

`defaults.<难度>` 默认使用 fallback：单个别名固定选择，有序别名链按序校验并派发首个可用候选。需要分摊独立任务时配置 `mode: load-balance`；需要按额度比例分摊时配置 `mode: weighted-load-balance`，并把 `candidates` 写成“别名: 正权重”映射。脚本按难度与完整任务文本做稳定散列来排列候选，不维护共享计数，同一任务可复现选择与 fallback 顺序。每个候选只按本次难度或显式 `default` 解析自己的 `routes`；缺少两者时跳过该候选。候选全部不可用时汇总各候选错误报告；spawn 发出后不重试，确认线程未创建后用 `--fallback-from <候选别名>` 续派。具体格式和负载均衡续派约束见[配置与派发](references/dispatch.md)。

每次派发本来就是独立 BB 会话，负载均衡不会拆分会话上下文。不要额外规避前缀缓存；但不同 provider 或模型之间也不假定共享缓存。

权限须符合任务授权；配置缺失或校验失败时说明缺口，不静默换模型或升权。

派发标题由脚本按难度加前缀：`simple` 为 🟢、`medium` 为 🟡、`complex` 为 🔴；需要简短标题时传 `--title`，省略时从任务文本截取。

根据返回结果报告线程 ID、实际选择和状态；发生 fallback 时说明链上失败原因与实际候选。创建成功不代表任务完成；创建结果不明时先查询线程，避免重复派发。

## 等待与并发

等待由 BB 的通知驱动，不靠轮询。子线程回合完成、失败或被中断时，BB 会向父线程投递系统通知（父线程忙时先排队，空闲时作为新回合送达，内容含子线程最终输出摘要）；子线程卡在待处理交互时另有求助通知。脚本在父子同项目时自动关联父线程，通知沿这条关联回到父线程。用户可能直接在子线程里对话并改变其授权或方向；通知会标明该回合是否由用户直接发起，此时以用户对子线程的指令为准，不要据此发出纠正、停止或重派指令，除非用户要求。派发后结束当前回合或转做其他工作，收到通知再读取结果、决定下一步；`bb thread wait` 循环、反复 `show` 或 sleep 后重查都属于多余的轮询，只在创建结果未知等需要立即确认时查询一次。

子线程因 provider 不可用、额度耗尽或会话错误而失败或中断时，按 `selection.fallbacks` 记录的未尝试链用 `--fallback-from <下一别名>` 改派：沿用原 difficulty 与完整任务文本以复现候选顺序；失败线程已有部分产出时，创建成功后通过 `bb thread tell` 补充进展与位置。这区别于任务被拒、正常完成或待处理交互——那些不是路由失败，不改派。链耗尽后如实报告，不循环改派。

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

1. **最小事实与滚动折算**：每次派发仅记录 `id`、`ts`、`difficulty`、`agent`、`provider`、`model`、`reasoning`、`task_chars`、`outcome`、`decision`，不存任务正文、diff 或日志。live 窗口保留最近 200 条，超出部分自动折算进固定维度 `rollups`，live 与 rollup 不重复计数。
2. **决策回环与自动熔断冷却（Circuit Breaker）**：子线程完成或失败后，父 agent 用稳定线程 ID 覆盖回写结果与裁决（未知 ID 拒绝报错）：
   ```bash
   bb-dispatch --record-decision <线程ID> --outcome completed --decision accepted
   bb-dispatch --record-decision <线程ID> --outcome failed_quota --decision rejected
   ```
   回写 `failed_quota`（如 403 额度耗尽，冷却 6 小时）、`failed_transient`（如 429/503，冷却 15 分钟），或使用 `--fallback-from` 续派跳过的候选，均会自动进入冷却期；冷却期内同档派发优先跳过该候选（若同档全部候选均在冷却则保底降级尝试，避免死锁）。
3. **聚合复盘与偏斜检测**：运行 `bb-dispatch --history-summary`（或 `--stats`）只读输出按难度占比、各候选失败率/接受率、当前活跃冷却及确定性复盘 hooks（`simple_share_low` 当总派发 $\ge 5$ 且 `simple` 占比 $<20\%$、`high_failure_rate` 当候选失败率 $\ge 30\%$、`low_acceptance_rate` 当候选接受率 $<50\%$）。派发时若触发复盘 hook，返回 JSON 的 `selection.warnings` 会同步携带提醒。
