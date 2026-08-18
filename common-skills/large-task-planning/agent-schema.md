# Agent JSON 契约

Agent 文档是结构化 JSON，只通过 `scripts/epic_story.py` 的 `template`、`write`、`patch` 写入。人读 Epic、Story、README 仍由 Agent 写 Markdown；`项目进展.md` 由 `render` 从本契约投影生成。

字段名、枚举和清单规则以脚本校验为准。本页给写作模板。

## 执行卡 `agent-card`

路径：`agent/STORY-NN[.M]-短标题.json`。文件名必须以 Story ID 加连字符开头。每个 Story 恰好一份。

```json
{
  "kind": "agent-card",
  "schema_version": 1,
  "story": "STORY-01",
  "intent_version": 1,
  "status": "todo",
  "owner": "待领取",
  "blocker": "无",
  "status_updated": "2026-08-18",
  "refreshed": "待领取",
  "code_baseline": "待领取",
  "owns": ["AUTH_STATE"],
  "verifies": [],
  "goal": "完成时的可观察结果。",
  "decision_boundary": "不可变条件，以及必须询问的变化。",
  "technical_plan": "实现路径；精确参数放到共享契约。",
  "authoritative_inputs": "本卡直接依赖的共享 JSON、代码入口和基线。",
  "claim_checks": "领取时复核 intent_version、前置交接、代码入口和远端基线。",
  "checklist": [
    {"done": false, "text": "建立可失败的行为基线。"},
    {"done": false, "text": "实现本 Story 的核心结果。"},
    {"done": false, "text": "记录证据并完成交接。"}
  ],
  "steps": "按顺序写出实现步骤，每步带完成条件。",
  "verification": "命令、退出码、固定分母和交付证明。",
  "stop_conditions": "必须停止并询问的输入漂移。",
  "handoff": "起止版本、副作用、清理和下一个 Story 输入。"
}
```

`status` 只能是 `todo`、`in_progress`、`blocked`、`done`。`blocked` 时 `blocker` 不能为 `无`。开始后 `refreshed` 必须是日期，`code_baseline` 必须是实际版本。`owns` 至少一项，且必须出现在 Epic `coverage` 中。`checklist` 3～7 项；`done` 时必须全部为 `true`。

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

两项合计最多 6 条。没有时用空数组，不要写 `"无"`。

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
