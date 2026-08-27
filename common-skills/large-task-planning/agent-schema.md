# Agent JSON 契约

Agent 文档是结构化 JSON，只通过 `scripts/epic_story.py` 的 `template`、`write`、`patch` 写入。人读 Epic、Story、README 仍由 Agent 写 Markdown；`项目进展.md` 由 `render` 从本契约投影生成。

字段名、枚举和清单规则以脚本校验为准。本页给写作模板。

## 语言与语义章节

Epic 和全部 Story 都必须有相同的 `language`（BCP-47，例如 `zh-Hans`、`zh-Hant`、`en`）。人读 Markdown 的每个二级标题前必须有 `<!-- large-task-planning:<section-id> -->`；脚本按 section id 校验结构，不限制标题或正文语言。完整的 section id 列表和标记格式见 `SKILL.md`。

Epic 还必须有正整数 `goal_version`，并与 `agent/黄金验收.json` 一致。只有 Goal 或黄金验收契约变化才递增它；调整当前计划不递增。

## 黄金验收 `golden-acceptance`

路径固定为 `agent/黄金验收.json`。它保存用户提供或确认的完成边界，不保存执行结果：

```json
{
  "kind": "golden-acceptance",
  "schema_version": 1,
  "epic": "EPIC-NAME",
  "goal_version": 1,
  "updated": "2026-08-26",
  "provenance": "user-provided",
  "cases": [
    {
      "id": "GC-01",
      "title": "连续会话回答测试环境与审批问题",
      "fixture": ["固定知识库版本和测试账号。"],
      "interaction": ["用户询问测试环境搭建。", "同一会话追问审批人。"],
      "oracle": ["两次回答均与指定权威文档一致，且追问无需重复上下文。"],
      "required_paths": ["先查询知识库，再读取命中文档的仓库详情。"],
      "evidence": ["保存完整会话、命中文档、仓库版本和能力调用记录。"],
      "pass_condition": "所有 oracle 与必经路径在同一次验收中都有证据。"
    }
  ]
}
```

`provenance` 只能是 `user-provided` 或 `user-confirmed`。每个案例必须有唯一 `GC-NN`；
`fixture`、`interaction`、`oracle` 和 `evidence` 都是非空字符串数组，`required_paths` 可以为空。
没有已知正确结果的输入不能放入 `oracle`。在线日志、数据库或外部系统会漂移时，在 fixture
中固定快照、版本或有效验收窗口。

## 执行卡 `agent-card`

路径：`agent/STORY-NN[.M]-短标题.json`。文件名必须以 Story ID 加连字符开头。每个 Story 恰好一份。

```json
{
  "kind": "agent-card",
  "schema_version": 1,
  "story": "STORY-01",
  "title": "与 Story frontmatter 相同的结果导向标题。",
  "epic": "EPIC-NAME",
  "gate": "项目门禁 ID",
  "depends_on": ["STORY-00"],
  "intent_version": 1,
  "status": "todo",
  "owner": "待领取",
  "blocker": "无",
  "status_updated": "2026-08-18",
  "refreshed": "待领取",
  "code_baseline": "待领取",
  "owns": ["AUTH_STATE"],
  "verifies": [],
  "acceptance_cases": ["GC-01"],
  "goal": "完成时的可观察结果。",
  "decision_boundary": "不可变条件，以及 Agent 可在已确认方案内自行处理的实现取舍。",
  "technical_plan": "按顺序写实现路径，带代码锚点、本地运行方式、需要的测试数据与环境准备。",
  "authoritative_inputs": "本卡直接依赖的共享 JSON、代码入口、基线和前置执行卡路径。",
  "claim_checks": "领取时复核 intent_version、前置交接、代码入口和远端基线。",
  "checklist": [
    {"done": false, "text": "建立可失败的行为基线。"},
    {"done": false, "text": "实现本 Story 的核心结果。"},
    {"done": false, "text": "记录证据并完成交接。"}
  ],
  "steps": "按顺序写出实现步骤，每步以「判据：…」写明可验证的完成判据。",
  "verification": "命令、退出码、固定分母和交付证明。",
  "stop_conditions": "使已确认方案失效的输入漂移；暂停并回到计划修订。",
  "handoff": "起止版本、副作用、清理和下一个 Story 输入。"
}
```

`status` 只能是 `todo`、`in_progress`、`blocked`、`done`。`blocked` 时 `blocker` 不能为 `无`。开始后 `refreshed` 必须是日期，`code_baseline` 必须是实际版本。`owns` 至少一项，且必须出现在 Epic `coverage` 中。`acceptance_cases` 只引用黄金验收中的案例；前序 Story 标出它推进的案例，依赖链最后一个 Story 必须列出全部案例。每张卡的范围应能让 Agent 在两到三轮会话压缩内完成实现、验证、证据和交接；超过这个容量就按独立结果或上下文交接点拆分。`checklist` 3～7 项；`done` 时必须全部为 `true`。

`title`、`epic`、`gate`、`depends_on` 是可选的身份冗余，让执行卡单独被加载或渲染时自解释（例如工作台 UI 只读一张卡）。省略合法；填写时脚本会在 `check`/`render` 校验它们与人读 Story 的同名 frontmatter 一致，漂移即报错，因此 Story 始终是唯一事实源。

执行卡只收影响执行决策的信息：做什么、不做什么、照什么做、怎么算完成、何时停。背景叙述和执行时顺手能从权威输入读到的内容不入卡，指路即可。

`steps` 每步用「判据：…」标注该步完成的可验证条件，避免写成「完成：…」——后者在规划期读起来像已经完成。`technical_plan` 必须让执行 agent 不靠重新摸索就能开工：按顺序写改动路径并给出代码锚点（文件、函数），写明本地如何运行和验证，Story 依赖特定本地状态或测试数据时（如需要两个内容不同的会话、特定权限账号）写出准备步骤。方案参照的现有实现同样列入 `authoritative_inputs`。Story 有前置时，把前置执行卡路径列入 `authoritative_inputs`：领取会话按最小加载规则只读本卡及其直接引用，前置交接必须经由该字段可达，`claim_checks` 才有东西可复核。

最后一个 Story 是黄金验收与收口卡。它的 `verification` 在完成时必须逐项包含所有 `GC-NN`
及证据位置，并以该卡的 `code_baseline` 作为同一轮全量验收的 acceptance commit。案例失败后，
保留失败证据并在它之前插入修复 Story；修复后重跑失败案例，再重跑全部案例。

创建：

```bash
python3 scripts/epic_story.py template agent-card --story STORY-01 --file topic/agent/STORY-01-标题.json
```

领取或勾选：

```bash
python3 scripts/epic_story.py patch --file topic/agent/STORY-01-标题.json \
  --set status=in_progress --set owner=Codex \
  --set refreshed=2026-08-18 --set code_baseline=abc123 \
  --check-item 1
```

替换长字段时，先读当前 JSON，改完后：

```bash
python3 scripts/epic_story.py write --file topic/agent/STORY-01-标题.json --from card.json
```

## 风险登记 `risk-register`

路径固定为 `agent/风险与阻塞.json`。

```json
{
  "kind": "risk-register",
  "schema_version": 1,
  "epic": "EPIC-NAME",
  "updated": "2026-08-18",
  "pending_decisions": [],
  "watch_items": ["上游版本变化时重跑真实验收。"]
}
```

两项合计最多 6 条。`pending_decisions` 只承接规划期经对话仍未关闭的例外待决项，规划结束时必须清空。没有时用空数组，不要写 `"无"`。

## 共享资料 `agent-reference`

门禁、核心决策、接口契约、安全矩阵和用户需求都用这一形态。`body` 可以是对象、数组或字符串，由该主题自己的结构决定。

```json
{
  "kind": "agent-reference",
  "schema_version": 1,
  "id": "core-decisions",
  "title": "核心决策",
  "updated": "2026-08-18",
  "body": {
    "D-01": "企业版使用破坏性 v2，不兼容或迁移 v1。"
  }
}
```

`agent/*.md` 不再合法。若旧项目仍有 Markdown 执行卡或风险登记，先按本契约写成 JSON，用 `write` 落入 `agent/`，再删除对应 `.md`。证据文件放 `agent/evidence/`，不走本契约。
