---
name: large-task-planning
description: 为大型工程任务建立可执行的 Epic、Story、门禁、证据和状态门户。
disable-model-invocation: true
---

# Large Task Planning

把大型工程拆成独立 Epic、少量结果型 Story、简洁的人读一览和按需加载的 Agent 资料。Story 是 Agent 的单会话工程单元；人先确认意图并看全盘，产品验收可以在整个 Epic 完成后进行。

## 1. 确认事实

1. 阅读仓库 `AGENTS.md`、根 `README.md`、现有方案和代码入口。
2. 检查主仓及相关 submodule 的 branch、`git status --short`、`git worktree list` 和基线 commit。
3. 分开记录事实、判断、假设、非目标和真正改变方案的待决策项。
4. 盘点消费者、接口、数据、后台任务、副作用、部署、测试和安全环境。

完成标准：目标、兼容边界、基线、不可触碰对象和决策项均可追溯。

## 2. 固定文档角色和预算

正文有效字符指去掉 YAML、空白、Markdown 标记和链接目标后的可见字符。以下是硬上限，不是写作目标；能更短就更短。

| 文档 | 受众与内容 | 上限 |
| --- | --- | ---: |
| `README.md` | 人读项目入口，只链接一览、Epic 和 Agent 入口 | 1500 |
| `epics/EPIC-<ID>.md` | 一个 Epic 一篇；愿景、成功标准、Story 地图、边界、权威入口 | 3000 |
| `项目进展.md` | 人读全盘；Story、门禁、关键基线、风险与阻塞 | 3000 |
| `stories/Story-NN[.M]-*.md` | 人和 Agent 共读；愿景、范围、方案概览、TODO、验收、证据 | 2200 |
| `agent/STORY-NN[.M]-*.md` | 当前 Story 执行卡；决策边界、覆盖、技术方案、领取检查、步骤和交接 | 不设统一字数上限，一卡一 Story |
| 其他 `agent/*.md` | 按需加载的矩阵、门禁、动态证据和共享协议 | 不设统一字数上限，保持一文一主题 |

项目入口不复制状态表；全局知识索引只链接项目入口、Epic 和项目进展，不平铺 Story。Epic、Story 和项目进展不放代码块、三级标题或执行命令。一个 Epic 最多 7 个 Story。

项目进展只允许以下二级章节：

- `Epic / Story 一览`：脚本生成；
- `门禁状态`：最多 3 行；
- `关键基线`：最多 6 行；
- `风险与阻塞`：最多 6 行。

同一事实只维护一次：动态状态在项目进展，愿景/边界在 Epic，TODO/验收和方案概览在 Story，版本/证据在清单，命令/场景在 `agent/`。其他文档只链接。

### 人读层使用普通语言

对项目 `README`、Epic、项目进展和 Story 重新解释，不把 Agent 资料压缩后直接贴给人：

1. 先补一两句必要背景，再回答“为什么做、现在到哪、下一步是什么”。文档应脱离历史会话也能读懂。
2. 使用 ASD-STE100 式简明表达：一句只讲一个意思，优先使用主动句、短句和常用词。
3. 使用项目面向协作者的主要语言，并在同一套文档中保持一致。缩写和无法替代的项目名词首次出现时，用一句普通语言说明含义。
4. 把技术动作翻译为人关心的结果。例如“固定验收版本”比列出提交号更适合人读层；精确版本仍放 Agent 文档。
5. 人读层只保留影响范围、进度、风险、取舍和决策的数字。SHA、checksum、manifest、artifact、fixture、runner、owner、命令和文件级差异放入 `agent/`。

完成检查：不参与执行的人应能在一分钟内说清项目目标、当前阶段、主要阻塞和下一项工作；不能做到就继续重写，而不是继续删字。

## 3. 创建独立 Epic

每个 Epic 保存为 `epics/EPIC-<ID>.md`，文件名必须等于 frontmatter 的 `id`：

```yaml
---
kind: epic
id: EPIC-<NAME>
title: <标题>
status: todo | in_progress | blocked | done
owner: <团队或负责人>
updated: YYYY-MM-DD
coverage: [<结果级覆盖项>]
---
```

二级章节按顺序使用：`愿景`、`成功标准`、`Story 地图`，可选 `项目边界`、`权威文档`。愿景只回答完成后改变什么；成功标准使用二元门禁；Story 地图链接每个 Story，不复制其 TODO、验收和证据。

Epic 按可独立成立的业务/交付结果拆，不按数据库、API、测试等技术层拆。方向已验证且多个 Epic 会反复修改同一核心组件时，优先合并为一个较大 Epic；只有风险边界、反馈窗口或独立价值确实不同才拆分。

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
status: todo | in_progress | blocked | done
gate: <稳定的项目门禁 ID>
owner: <负责人或待领取>
depends_on: [<前置 Story ID>]
blocker: 无 | <精确阻塞>
updated: YYYY-MM-DD
intent_version: <从 1 开始的正整数>
---
```

二级章节按顺序使用：`愿景`、`范围`、可选 `解决方案概览`、`TODO`、`验收标准`、可选 `交付证据`。方案概览用 2～5 条短句，以结果语言解释大致路径和关键取舍，让不参与实现的人也能看懂；不放命令、动态版本或实现细节。TODO 保持 3～7 项，每项不超过 120 个有效字符。

愿景、范围、解决方案概览和验收标准属于人确认的意图。Agent 可更新 status、owner、blocker、TODO 勾选和交付证据；修改人确认意图前必须获得当前任务的明确授权，并递增 `intent_version`。

每个 Story 必须直接链接唯一的 `agent/STORY-NN[.M]-<标题>执行卡.md`。执行卡使用以下 frontmatter：

```yaml
---
story: <Story ID>
intent_version: <与 Story 一致>
refreshed: 待领取 | YYYY-MM-DD
code_baseline: 待领取 | <领取时核实的版本>
owns: [<唯一主责覆盖项>]
verifies: [<复核覆盖项>]
---
```

执行卡按顺序使用：`目标与完成信号`、`决策边界`、`技术方案`、`权威输入`、`领取检查`、`执行步骤`、`验证与证据`、`停止条件`、`交接`。`决策边界` 写本 Story 的不可变条件和必须询问的变化；`领取检查` 复核意图版本、前置交接、当前代码入口和远端基线。步骤写清完成条件；共享事实链接矩阵、门禁或清单，不复制全文。

## 5. 保持基线与门禁

对需要基线控制的工程，分别记录不可变行为参考、可运行测试资产、持续开发的 live head 和本轮 acceptance commit。可观察增量同步更新范围、场景、目标实现和受影响证据；Schema、认证或破坏性协议变化形成 blocker。

开工前做二元 readiness 判断：`ready` 表示 Agent 能只凭 Story、已刷新执行卡及其直接引用完成工作；`blocked` 表示仍需自行发明需求、架构或验收决策。缺失关键决定、覆盖项无人主责或权威资料互相冲突时保持 blocked；缺少与当前 Story 无关的文档类型不构成 blocker。

Story 是工作拆分，门禁是项目定义的授权条件。先定义少量稳定门禁，再让 Story 引用门禁 ID。例如：

| 示例门禁 | 授权 |
| --- | --- |
| READY | 范围、基线和环境可复现，允许开工 |
| COMPONENT | 一个可独立交付部分的行为、质量和证据通过 |
| RELEASE | 全量、部署、观测和回退条件通过，允许进入发布决策 |

门禁使用固定分母、唯一通过条件、证据和撤销规则；进度使用 `已完成/总数`。

## 6. 自动检查和生成一览

使用 `scripts/epic_story.py`：

```bash
python3 <skill-dir>/scripts/epic_story.py check \
  --epic <topic/epics/EPIC-ID.md> --stories-dir <topic/stories> \
  --overview <topic/README.md> --dashboard <topic/项目进展.md>
python3 <skill-dir>/scripts/epic_story.py render \
  --epic <topic/epics/EPIC-ID.md> --stories-dir <topic/stories> \
  --dashboard <topic/项目进展.md>
python3 <skill-dir>/scripts/epic_story.py status \
  --epic <topic/epics/EPIC-ID.md> --stories-dir <topic/stories> --json
```

仪表盘只保留一组 `epic-story-dashboard` 标记。脚本检查项目入口、独立 Epic 路径、章节、字数、Story 数量、TODO、插入编号、数值顺序、前向依赖/依赖环、状态、链接和仪表盘新鲜度；同时检查意图版本一致、覆盖项唯一主责，以及进行中 Story 已记录执行卡刷新日期和代码基线。`render` 会按 `depends_on` 同步「STORY-XX 未完成」阻塞后再替换受控区块；真实阻塞（例如环境未就绪）不会被改写。`check` 在该依赖阻塞过期时失败。

## 7. 驱动 Agent 闭环

从项目进展的“可领取”项选择第一个 Story，只加载该 Story、对应执行卡及执行卡直接引用的共享资料。先执行 `领取检查`，更新 `refreshed` 和 `code_baseline`；确认 intent_version、覆盖、代码入口和上一 Story 交接一致后，才能设置 `in_progress` 和 owner。随后保存首次失败、修复根因并从统一入口复验；满足全部 TODO 和验收后设置 `done`，再运行 `render`（会自动放开仅因前置未完成而阻塞的下一 Story），更新证据并提交推送，执行会话到此停止。

只有用户显式要求方向检查时，才在领取下一 Story 前调用 `$story-direction-review`。方向检查只看结果是否偏航、重大遗漏和新事实对后续计划的影响，不替代代码审查。`INSERT_STORY` 优先使用最近已完成 Story 的插入号；只有主要目标、门禁或假设失效时才使用 `REPLAN`。

交接包含 Story ID、TODO 计数、起止版本、命令/退出码、固定分母、artifact/checksum、数据/副作用/cleanup、Git 状态、blocker 和下一 Story 输入。

完成标准：格式与预算检查通过，仪表盘最新，门禁/清单/证据一致，链接可解析，只提交本任务文件。
