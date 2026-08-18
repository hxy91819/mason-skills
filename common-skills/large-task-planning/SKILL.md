---
name: large-task-planning
description: 为大型工程任务建立可执行的 Epic、Story、门禁、证据和状态门户。
disable-model-invocation: true
---

# Large Task Planning

把大型工程拆成独立 Epic、少量结果型 Story、简洁的人读一览和脚本维护的 Agent JSON。Story 是 Agent 的单会话工程单元；人先确认意图并看全盘，产品验收可以在整个 Epic 完成后进行。

JSON 字段、模板和命令细节见 [`agent-schema.md`](agent-schema.md)。可重复示例提示词与触发脚本见 [`examples/token-login/`](examples/token-login/)。

## 1. 确认事实

1. 阅读仓库 `AGENTS.md`、根 `README.md`、现有方案和代码入口。
2. 检查主仓及相关 submodule 的 branch、`git status --short`、`git worktree list` 和基线 commit。
3. 分开记录事实、判断、假设、非目标和真正改变方案的待决策项。
4. 盘点消费者、接口、数据、后台任务、副作用、部署、测试和安全环境。

完成标准：目标、兼容边界、基线、不可触碰对象和决策项均可追溯。

### 重大决策先确认

把会改变用户拿到或必须运维的产品形态视为重大决策，包括发布物数量与组成、
主产物能否独立使用、安装与离线边界、兼容与迁移、支持环境、安全边界、外部依赖、
运维责任和显著成本。Agent 可以提出方案，但不能替用户确认。

开始规划时，先用普通语言向用户说明每项重大选择、用户可见后果、主要取舍，以及
理解选择所必需的被拒方案，再取得明确确认。用户批准综合计划，只有在其中已经清楚
披露这些后果时，才算确认相关决定；只列包名、组件名或实现动作不算充分披露。

执行中出现新的重大决策时，先停止依赖该决策的实现，把选择和后果写入相关 Epic 或
Story 的人读正文，递增 `intent_version` 并请求确认。不得先把决定写进 Agent JSON、
代码或测试，再把已经完成的实现反推为用户意图。

## 2. 固定文档角色和预算

正文有效字符指去掉 YAML、空白、Markdown 标记和链接目标后的可见字符。以下是硬上限，不是写作目标；能更短就更短。

| 文档 | 受众与内容 | 上限 |
| --- | --- | ---: |
| `README.md` | 人读项目入口，只链接一览、Epic 和 Agent 入口 | 1500 |
| `epics/EPIC-<ID>.md` | 愿景、全局设计图、成功标准、每个 Story 的范围地图、边界 | 3000 |
| `项目进展.md` | 脚本从 Agent JSON 生成的人读全盘 | 3000 |
| `stories/Story-NN[.M]-*.md` | 愿景、范围、重大决策、验收标准 | 2200 |
| `agent/STORY-NN[.M]-*.json` | Story 动态状态唯一源 | 一卡一 Story |
| `agent/风险与阻塞.json` | 待用户决策与后续关注 | 最多 6 项 |
| 其他 `agent/*.json` | 按需加载的矩阵、门禁、契约和共享协议 | 一文一主题 |
| `agent/evidence/*` | 证据产物，不经脚本规范化 | 按证据本身 |

人读层由 Agent 直接写 Markdown。Agent JSON 只通过 `template`、`write`、`patch` 和 `render` 更新；不得用手或普通编辑器改 `agent/*.json`。`项目进展.md` 整份由 `render` 覆盖生成。`agent/evidence/` 保存命令输出和固定产物，不作为状态源。

项目入口不复制状态表；全局知识索引只链接项目入口、Epic 和项目进展，不平铺 Story。人读文档不放三级标题或执行命令；只有 Epic 的「全局设计」可放架构图代码块。一个 Epic 最多 7 个 Story。

人读 Epic、Story、项目入口和项目进展不维护动态状态、负责人、阻塞或勾选进度。人读 Story 不链接执行卡；脚本按 Story ID 配对 `agent/STORY-NN[.M]-*.json`。

项目进展只允许以下二级章节：

- `Epic / Story 一览`：从执行卡收集 status、执行清单和 blocker，再只呈现人需要的状态、进度和下一步；
- `风险与阻塞`：收集非依赖性当前阻塞、待用户决策和后续关注项。

同一事实只维护一次：愿景/全局设计/边界在 Epic，范围/重大决策/验收标准在 Story，动态状态/执行清单/证据在执行卡，开放风险在风险登记，项目进展只是自动生成的投影。

“同一事实只维护一次”不等于把重大决定藏在 Agent 资料里。人读 Story 说明选择、原因、
取舍和用户影响；执行卡与契约只补充精确参数和实现细节。

### 人读层使用普通语言

对项目 `README`、Epic、项目进展和 Story 重新解释，不把 Agent JSON 压缩后直接贴给人：

1. 先补一两句必要背景，再回答“为什么做、现在到哪、下一步是什么”。文档应脱离历史会话也能读懂。
2. 使用 ASD-STE100 式简明表达：一句只讲一个意思，优先使用主动句、短句和常用词。
3. 使用项目面向协作者的主要语言，并在同一套文档中保持一致。缩写和无法替代的项目名词首次出现时，用一句普通语言说明含义。
4. 把技术动作翻译为人关心的结果。例如“固定验收版本”比列出提交号更适合人读层；精确版本仍放 Agent JSON。
5. 人读层只保留影响范围、进度、风险、取舍和决策的数字。SHA、checksum、manifest、artifact、fixture、runner、owner、命令和文件级差异放入 `agent/`。
6. 重大变化必须直接说明最终产品形态和用户要做什么。不能用“平台包”“发布检查”或组件名代替“主包是否可独立安装、需要几个发布物”等实际后果。

完成检查：不参与执行的人应能在一分钟内说清项目目标、当前阶段、主要阻塞和下一项工作；不能做到就继续重写，而不是继续删字。

## 3. 创建独立 Epic

每个 Epic 保存为 `epics/EPIC-<ID>.md`，文件名必须等于 frontmatter 的 `id`：

```yaml
---
kind: epic
id: EPIC-<NAME>
title: <标题>
updated: YYYY-MM-DD
coverage: [<结果级覆盖项>]
---
```

二级章节按顺序使用：`愿景`、`全局设计`、`成功标准`、`Story 地图`，可选 `项目边界`、`权威文档`。愿景只回答完成后改变什么。成功标准使用二元门禁。Story 地图用一句话写出每个 Story 的范围并链接人读 Story，不复制验收标准、执行清单或证据。权威文档只链给人读资料；Agent JSON 由执行卡的 `authoritative_inputs` 引用。

`全局设计` 是整个 Epic 唯一的方案源。先识别 Epic 内各个独立能力流，再分别用普通语言说明最终产品形态和端到端路径。不同参与者、生命周期或系统边界的能力各用一张最小图；不要因为它们属于同一 Epic，就增加不存在的箭头、顺序或依赖。共享组件可以在多张图中重复作为上下文，只有真实的数据流或部署依赖才能连线。

每张图展示一个能力的系统边界、主要数据或请求流、组件职责和必要的部署或分发关系；不放文件级实现、命令或动态版本。图使用 Mermaid `flowchart`/`sequenceDiagram` 或 fenced `text` 框图，并用粗体短句标明对应能力。使用 Mermaid 时按 `mermaid-lint` 的安全基线编写，并用真实渲染器校验。

Epic 按共同业务目标或发布边界组织，不按数据库、API、测试等技术层拆。一个 Epic 可以包含多个独立交付结果；图应保留这些结果的独立性。方向已验证且多个 Epic 会反复修改同一核心组件时，优先合并为一个较大 Epic；只有风险边界、反馈窗口或独立价值确实不同才拆分。

`coverage` 只列结果级覆盖项，例如一个领域、一次全量验收或一次切换；详细接口和场景继续由 Agent 矩阵维护。每项必须由一张执行卡通过 `owns` 唯一主责，其他执行卡可用 `verifies` 声明复核，避免遗漏和重复归属。

## 4. 拆结果型 Story

按一位 Agent 能在一次会话内完整理解、实施、验证、记录证据、提交和交接的工程结果拆分，不按文件、case 或单条命令拆。只有独立交付/回退、证据角色、权限副作用、冻结窗口或上下文无法闭环时才拆新 Story。Story 只能依赖编号更早的 Story，完成后工程结果必须独立成立，但不要求逐 Story 人工验收或单独提供用户价值。

计划执行中途需要在两个既有 Story 之间插入工作时，使用 `STORY-NN.M`，例如 `STORY-03.1` 位于 `STORY-03` 与 `STORY-04` 之间。主编号 Story 必须存在；`M` 是不带前导零的正整数，并按数值排序，因此 `.10` 位于 `.2` 之后。插入 Story 依赖最近的前置结果，原后续 Story 改为依赖最后一个插入 Story；保留既有 Story ID 和文件名。初次规划仍使用连续的 `STORY-NN`。

每个 Story 保存为 `stories/Story-NN-短标题.md`；插入 Story 使用 `stories/Story-NN.M-短标题.md`：

```yaml
---
kind: story
id: <Story ID>
epic: EPIC-<NAME>
title: <结果导向标题>
gate: <稳定的项目门禁 ID>
depends_on: [<前置 Story ID>]
updated: YYYY-MM-DD
intent_version: <从 1 开始的正整数>
---
```

二级章节按顺序使用：`愿景`、`范围`、可选 `关键决策`、`验收标准`。Story 只说明该交付单元的结果、边界、已确认决策和完成条件；完整方案通过范围中的一句话指向 Epic「全局设计」，不再写「解决方案概览」。

人读 Story 不放 TODO、复选框、交付证据或执行卡链接。`验收标准` 只定义用户确认的完成结果，不记录执行过程或已通过结果。可勾选进度和真实验证证据只维护在对应执行卡。

存在重大决策时，`关键决策` 必填。`关键决策` 按 1、2、3 连续编号，每项单独写清：

- `决定者：用户`，或在尚未确认时写 `决定者：待用户确认`；Agent 不是重大决策的决定者。
- `Agent 建议：…`，明确建议内容以及用户采纳或否决的结果；如果是用户直接决定，则写“无，用户直接决定”。
- `结果与影响：…`，说明用户将得到什么、需要做什么和主要代价。

生成每项重大决策时使用以下固定格式：

```markdown
1. **<已选择或待确认的产品决定>。**
   - 决定者：<用户｜待用户确认>。
   - Agent 建议：<建议内容，以及用户采纳或否决的结果>。
   - 结果与影响：<用户所得、用户动作和主要代价>。
```

待用户确认的重大决策必须让执行卡保持 `blocked`，并在 blocker 中指向人读决策。执行卡的 `decision_boundary` 必须回指该决策，不得首次引入改变产品或发布形态的选择。

愿景、范围、关键决策和验收标准属于人确认的意图。Agent 可用 `patch` 更新执行卡的 status、owner、blocker 和清单；修改人确认意图前必须获得当前任务的明确授权，并递增 `intent_version`。

用脚本创建执行卡：

```bash
python3 <skill-dir>/scripts/epic_story.py template agent-card \
  --story STORY-NN --file <topic>/agent/STORY-NN-短标题.json
```

创建后立即 `write` 或 `patch` 填入真实 `owns`、目标、边界、清单和权威输入。`checklist` 保持 3～7 项，每项不超过 120 个有效字符。`claim_checks` 复核意图版本、前置交接、当前代码入口和远端基线。

为每个 Epic 建立风险登记：

```bash
python3 <skill-dir>/scripts/epic_story.py template risk-register \
  --epic-id EPIC-<NAME> --file <topic>/agent/风险与阻塞.json
```

`pending_decisions` 和 `watch_items` 只记录需要用户选择、新授权或未来明确复核的开放事项。没有时保持空数组。依赖等待、已关闭问题、普通实现任务、通用风险提示和已有验收覆盖不进入此文档。

共享协议、门禁、矩阵和需求使用 `kind: agent-reference` 的 JSON，同样只通过 `template`/`write`/`patch` 更新。执行卡用路径列出本 Story 真正要加载的共享文档。

## 5. 保持基线与门禁

对需要基线控制的工程，分别记录不可变行为参考、可运行测试资产、持续开发的 live head 和本轮 acceptance commit。可观察增量同步更新范围、场景、目标实现和受影响证据；Schema、认证或破坏性协议变化形成 blocker。

开工前做二元 readiness 判断：`ready` 表示 Agent 能只凭 Story、已刷新执行卡及其直接引用完成工作；`blocked` 表示仍需自行发明需求、架构或验收决策。缺失关键决定、覆盖项无人主责或权威资料互相冲突时保持 blocked；缺少与当前 Story 无关的文档类型不构成 blocker。

重大决策没有可追溯的用户确认，或只存在于 Agent 资料、代码和测试中时，同样必须保持
`blocked`。已完成实现不能替代确认，也不能作为解除阻塞的依据。

Story 是工作拆分，门禁是项目定义的授权条件。先定义少量稳定门禁，再让 Story 引用门禁 ID。例如：

| 示例门禁 | 授权 |
| --- | --- |
| READY | 范围、基线和环境可复现，允许开工 |
| COMPONENT | 一个可独立交付部分的行为、质量和证据通过 |
| RELEASE | 全量、部署、观测和回退条件通过，允许进入发布决策 |

门禁使用固定分母、唯一通过条件、证据和撤销规则；进度使用 `已完成/总数`。

## 6. 用脚本维护状态并生成一览

使用 `scripts/epic_story.py`。完整参数以 `--help` 为准。

```bash
python3 <skill-dir>/scripts/epic_story.py check \
  --epic <topic/epics/EPIC-ID.md> --stories-dir <topic/stories> \
  --overview <topic/README.md> --dashboard <topic/项目进展.md>
python3 <skill-dir>/scripts/epic_story.py render \
  --epic <topic/epics/EPIC-ID.md> --stories-dir <topic/stories> \
  --dashboard <topic/项目进展.md>
python3 <skill-dir>/scripts/epic_story.py status \
  --epic <topic/epics/EPIC-ID.md> --stories-dir <topic/stories> --json
python3 <skill-dir>/scripts/epic_story.py write \
  --file <topic/agent/STORY-NN-标题.json> --from card.json
python3 <skill-dir>/scripts/epic_story.py patch \
  --file <topic/agent/STORY-NN-标题.json> \
  --set status=in_progress --set owner=Codex --check-item 1
```

脚本检查项目入口、独立 Epic 路径、全局设计与架构图、Story 意图、Agent JSON、依赖、覆盖主责和风险登记。`render` 只在执行卡同步「STORY-XX 未完成」依赖阻塞，然后整份覆盖生成 `项目进展.md`；非依赖性阻塞保持不变。`check` 在生成结果过期、人读文档含动态字段、Agent 目录残留 Markdown 或风险登记不合格时失败。

领取、勾选、阻塞和交接都先 `patch` 或 `write`，再 `render`。长字段（`handoff`、`verification`、`technical_plan`）用 `write` 整份替换；短字段和清单用 `patch`。

## 7. 驱动 Agent 闭环

从项目进展的“可领取”项选择第一个 Story。用 `status --json` 取执行卡路径，只加载该 Story、对应 JSON 及 `authoritative_inputs` 直接引用的共享资料。先执行 `claim_checks`，再用 `patch` 更新 `status`、`owner`、`status_updated`、`refreshed` 和 `code_baseline`；确认 intent_version、覆盖、代码入口和上一 Story 交接一致后，才能设置 `in_progress`。随后保存首次失败、修复根因并从统一入口复验；满足全部执行清单和人读验收标准后 `patch` 为 `done`，再运行 `render`，更新证据并提交推送，执行会话到此停止。

领取和交接都要复核本 Story 是否出现新的重大决策。若有，先更新人读 Story、撤销受影响
门禁并取得确认；不得让执行卡成为人第一次发现该决定的地方。

只有用户显式要求方向检查时，才在领取下一 Story 前调用 `$story-direction-review`。方向检查只看结果是否偏航、重大遗漏和新事实对后续计划的影响，不替代代码审查。`INSERT_STORY` 优先使用最近已完成 Story 的插入号；只有主要目标、门禁或假设失效时才使用 `REPLAN`。

交接写入执行卡 `handoff`：Story ID、执行清单计数、起止版本、命令/退出码、固定分母、artifact/checksum、数据/副作用/cleanup、Git 状态、blocker 和下一 Story 输入。

完成标准：格式与预算检查通过，仪表盘最新，门禁/清单/证据一致，Agent JSON 均由脚本写入，只提交本任务文件。
