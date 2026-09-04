# Large task plan v2 格式

`agent/plan.json` 与 `agent/stories/*.json` 是唯一事实源。脚本拒绝未知字段，防止运行过程中不断沉积
临时规则。完整参数以 `scripts/epic_story.py --help` 为准。

## Agent plan

```json
{
  "kind": "large-task-plan",
  "schema_version": 2,
  "id": "EPIC-EXAMPLE",
  "title": "用户可理解的目标名称",
  "goal_version": 1,
  "updated": "2026-09-04",
  "language": "zh-Hans",
  "spec": {
    "problem_statement": "用户现在遇到的问题。",
    "solution": "完成后用户如何使用和感知结果。",
    "user_stories": [
      {
        "id": "US-01",
        "actor": "目标用户",
        "want": "完成一项可观察操作",
        "benefit": "获得明确价值"
      }
    ],
    "boundaries": ["已确认的兼容、安全、发布或运维边界。"],
    "decisions": [
      {
        "id": "D-01",
        "decision": "已经选定的方向",
        "rationale": "选择依据与替代方案。",
        "impact": "对用户、实现和回退的影响。",
        "owner": "user"
      }
    ],
    "testing": {
      "seams": ["最高且稳定的公开行为边界。"],
      "strategy": "如何用独立 oracle 和纵向 red-green 循环验证。"
    },
    "out_of_scope": ["本轮明确不交付的结果。"]
  },
  "golden_acceptance": [
    {
      "id": "GC-01",
      "title": "一条完整用户路径",
      "fixture": ["可复现环境、版本、账号和输入。"],
      "actions": ["按顺序执行的用户操作。"],
      "oracle": ["来自规格、已知样例或权威系统的正确结果。"],
      "evidence": ["要保留的产品输出和验证事实。"]
    }
  ],
  "final_story": "STORY-03"
}
```

`owner=user` 表示会改变产品或交付边界的用户决定；`owner=agent` 表示边界内可逆技术决定。
`EPIC-*` ID 只为已有项目连续性保留，不意味着还要生成 Epic Markdown。

## Agent Story

```json
{
  "kind": "large-task-story",
  "schema_version": 2,
  "id": "STORY-01",
  "plan": "EPIC-EXAMPLE",
  "title": "一条可验证的纵向结果",
  "intent_version": 1,
  "status": "todo",
  "blocked_by": [],
  "covers": ["GC-01"],
  "outcome": "完成后新增的可观察能力，以及明确不包含什么。",
  "acceptance": [
    {
      "id": "AC-01",
      "criterion": "通过公开入口观察到行为。",
      "passed": false
    }
  ],
  "context": {
    "test_seams": ["公开接口、命令或用户界面。"],
    "code_anchors": ["稳定的入口文件、符号或搜索词。"],
    "authoritative_inputs": ["规格、ADR 或前置约束。"],
    "write_scope": ["允许修改并应与并发工作隔离的区域。"],
    "stop_conditions": ["会改变 Goal 或用户边界的新事实。"]
  },
  "owner": null,
  "blocker": null,
  "updated": "2026-09-04",
  "handoff": null
}
```

状态只有：

- `todo`：未领取，`owner` 与 `blocker` 都是 `null`。
- `in_progress`：Worker 实现与 Reviewer 往返都属于此状态。
- `blocked`：`blocker` 写无法在现有边界内解决的具体事实。
- `done`：所有 Acceptance 均为 `passed=true`，并有完整 Handoff。

完成时 Handoff 格式：

```json
{
  "summary": "已经成立的可观察结果。",
  "verification": ["命令、退出码或证据路径。"],
  "remaining": [],
  "risks": ["仍需关注但不阻止完成的风险。"],
  "next": "下一张 Story 需要知道的事实。"
}
```

`covers` 只表示该 Story 推进或复验的黄金案例，不表示测试 ID，也不保存命令结果。

## 人读投影

`render` 在计划根目录生成：

- `SPEC.md`：按人的理解顺序说明动机、最终体验、用户承诺、边界、关键取舍、完成证明和高层结果路线。
- `STATUS.md`：先给当前判断，再说明正在推进、接下来、之后路线、需要关注和已经得到的结果。

这两份 Markdown 不是 JSON 字段清单，也不是 Epic/Story 卡片集合。它们不显示内部 ID、依赖图、模型、
session、owner、代码路径或命令日志；黄金案例只显示场景名称和人能理解的准备、动作、正确结果与证据。
Agent Story 仍是执行边界，但在人读文档中只以有意义的结果名称与结果描述出现。

`check` 会比较完整生成结果，投影缺失或过期即失败。不要手改生成文档。

## 常用命令

```bash
python3 scripts/epic_story.py render --plan <agent/plan.json> --stories-dir <agent/stories>
python3 scripts/epic_story.py check --plan <agent/plan.json> --stories-dir <agent/stories>
python3 scripts/epic_story.py status --plan <agent/plan.json> --stories-dir <agent/stories> --json
python3 scripts/epic_story.py brief --plan <agent/plan.json> --stories-dir <agent/stories> --story STORY-01
python3 scripts/epic_story.py write --file <agent/stories/STORY-01.json> --from <draft.json>
python3 scripts/epic_story.py completion-check --plan <agent/plan.json> --stories-dir <agent/stories>
```
