---
name: large-task-orchestrator
description: 用宿主原生 subagent 持续执行已有大型任务计划，直到完整交付或出现真实 blocker。
disable-model-invocation: true
---

# Large Task Orchestrator

这是流程类 Skill，仅在用户显式调用 `$large-task-orchestrator` 时运行。

当前 Agent 是 orchestrator。使用宿主提供的原生 subagent 能力调度 worker 与 reviewer；具体工具名因
coding agent 而异。计划、Git 和验证证据承载长期状态，subagent session 可以随时丢弃和替换。
核心流程不依赖外部代理 CLI、provider 路由表或某个特定 coding agent。

只接管已存在并通过 sibling `large-task-planning` v2 校验的计划。先读
[`../large-task-planning/references/plan-format.md`](../large-task-planning/references/plan-format.md)；维护两项
Skill 的共同边界时再读[联合核心设计](../../docs/large-task-system-design.md)。

## 角色边界

- **Orchestrator（当前 Agent）**：唯一控制面。拥有 Story 状态、计划调整、subagent 调度、结果裁决、
  Git checkpoint、整合与最终 push。
- **Worker（fresh subagent）**：一次只实现一张 Story。可在同一 Story 内接收修复 follow-up；不修改
  计划、不提交、不推送，也不继续派生 subagent。
- **Reviewer（独立 subagent）**：没有参与该 Story 的实现。只读检查并运行验证命令，不编辑文件、
  不修改计划。分别报告 Spec 与 Standards 两个轴，不让一个轴掩盖另一个。

默认同时只运行一个会写工作区的 Worker。共享工作区中的并行写入收益通常低于冲突与恢复成本。
只读调查或互不影响的 Reviewer 可以并行；只有已有隔离 worktree 且计划明确分配 write scope 时，才并行
多个 Worker。未经用户授权，不创建、切换或清理 branch/worktree。

## 启动或恢复

1. 读取适用的 `AGENTS.md`、`SPEC.md`、`STATUS.md`、`agent/plan.json` 与脚本状态；检查当前 branch、
   `git status --short`、`git worktree list` 和已有提交。保留无关并发改动。
2. 运行：

```bash
python3 <planning-skill>/scripts/epic_story.py check \
  --plan <topic>/agent/plan.json --stories-dir <topic>/agent/stories
python3 <planning-skill>/scripts/epic_story.py status \
  --plan <topic>/agent/plan.json --stories-dir <topic>/agent/stories --json
```

3. 对每个 `in_progress` Story，先对照 Story handoff、当前 diff、测试结果和 Git checkpoint。工作仍可用就
   继续；session 已丢失就把这些事实交给 fresh replacement Worker。不要因为对话压缩而重新领取。
4. 尽力启动本地 history run。History 是旁路复盘缓存；写入失败只警告，不改变计划状态或交付事实。

## 自主循环

持续执行下面的循环，不在 Story 之间停下来询问是否继续：

1. **选择 frontier。** 从 `status --json` 的 `ready` 中选择最能降低 Goal 风险的 Story；通常取第一项。
2. **原子领取。** 使用 `transition --expect todo --status in_progress --owner <worker-id>`。若预期状态失败，
   重新读取计划并协调并发事实。
3. **派发 fresh Worker。** 用 planning 的 `brief` 命令提取当前 Story、稳定边界、相关黄金案例和直接
   前置 handoff，再补充仓库规则、当前基线与并发 write scope。要求它先验证现状，在指定公开 seam 上
   按 red → green 的纵向小循环实现并运行相关测试。不要复制整个会话历史或全部计划。
4. **核对落盘事实。** Worker 回复不是完成证明。Orchestrator 检查 diff、工作区和命令证据，确认没有
   越界、丢失并发改动或只修改了报告。
5. **独立审查。** 派发未参与实现的 Reviewer，并固定本轮基线与 diff。要求分别检查：
   - `Spec`：Story Outcome/Acceptance 与相关黄金案例是否完整实现，有无漏项、错误或范围蔓延；
   - `Standards`：适用仓库规则、可维护性和明显 code smell；跳过工具已覆盖的纯格式噪声。
6. **裁决。** Reviewer 通过则由 orchestrator 运行必要测试；有可操作缺陷则把精确 finding 发回同一
   Worker 修复，再由 Reviewer 复核。新独立结果用插入 Story 承接；Goal 或用户边界失效才请求用户。
7. **完成 Story。** 通过 planning 的 `write` 更新 Story JSON：把已证明的 Acceptance 设为 `passed=true`，
   在 Handoff 中记录可观察结果、命令/证据与 Reviewer 结论、剩余事项、残余风险和下一 Story 输入。
   随后 `transition --status done`、运行 `check`，并由 orchestrator 创建包含 Story ID 的 Git checkpoint；
   `SPEC.md` 与 `STATUS.md` 由脚本同步刷新。
8. **继续。** 重新计算 frontier，直到 `final_story` 完成或没有可推进工作。

每次 context compaction 前，先把当前阶段、证据和精确下一步写回 Story Handoff。恢复顺序固定为
Agent JSON → Git/diff → history；subagent 对话只在仍可访问且确有需要时读取。

## Subagent 报告契约

不要求 provider 特有 JSON 或事件流。Worker 最终回复应简短包含：

```text
Result: worker_done | blocked | failed
Changed: <可观察结果和文件>
Verified: <命令及结果>
Remaining: <未完成工作或 none>
Handoff: <替换 Worker 继续所需上下文>
```

Reviewer 最终回复保持两个轴，并给出唯一结论：

```text
Spec: pass | <findings>
Standards: pass | <findings>
Conclusion: CONTINUE | PATCH | INSERT_STORY | REPLAN
```

格式帮助协调，但事实仍以工作区、测试和计划为准。Reviewer 意外写文件时，不接受其结论；先隔离该
改动与并发现场，再派发新的只读 Reviewer。

## 计划演化与 blocker

Orchestrator 在既定 Goal 和用户边界内拥有实现路径，可以重排、插入、合并或改写未开始的 Story。
修改 Story 结果或验收时递增 `intent_version`，保留完成证据和既有 ID；插入使用 `STORY-NN.M`。

只有以下情况询问用户：缺少必要凭据或权限；下一步具有破坏性、难回退、明显外部影响或显著成本；
选择会改变 Goal、黄金 oracle、公开契约或用户边界；同一语义区域的并发修改无法判断；受影响链的
安全恢复路径已经耗尽。先继续其他独立 ready Story，只阻塞受影响链。提问时给出证据、已尝试恢复、
影响范围和一个最小决策。

普通实现不确定、首次测试失败、subagent 消失或等价技术方案选择都由 orchestrator 解决。最终验收
失败时保留失败证据：实现缺陷插入修复 Story；fixture/环境错误修复验收环境；Goal 或边界错误才请求
用户。不得降低黄金判据来获得绿色结果。

## History 与复盘

复杂长时运行需要最小可观测性，但不需要第二套状态账本。使用
[`scripts/orchestration_history.py`](scripts/orchestration_history.py) 维护 Git-ignored 的
`<repo>/.local/large-task-orchestrator/run-history.json`：

```bash
python3 <skill-dir>/scripts/orchestration_history.py --repository <repo> start \
  --run-id <stable-run-id> --plan-ref <topic>
python3 <skill-dir>/scripts/orchestration_history.py --repository <repo> attempt start \
  --run-id <run-id> --attempt-id <story-role-attempt> --story <STORY-ID> \
  --role worker --agent <host-agent> --route host-native \
  --plan-ref <topic>/agent/stories/<Story.json>
python3 <skill-dir>/scripts/orchestration_history.py --repository <repo> attempt finish \
  --run-id <run-id> --attempt-id <story-role-attempt> --outcome worker-done
```

Worker 与 Reviewer 每次 turn 各记录一个 attempt；真实 plan change、blocked episode 和 Git checkpoint
记录 event。只保存 engine/model/耗时/outcome/reason/stable id 等最小事实，不保存 prompt、回复、diff、
测试日志或密钥。`show` 提供带分母的聚合复盘；记录失败只告警并继续权威流程。

## 收口与交付

完成 `final_story` 前，在同一 acceptance commit 上运行全部黄金案例和跨 Story 整合检查。然后：

1. 运行 `completion-check`，确认全部 Story、验收勾选、依赖与黄金覆盖收口。
2. 检查完整 diff、branch、`git status --short`、`git worktree list` 与待推送提交，只提交授权范围。
3. 推送当前目标分支到明确 upstream；不 force-push、不绕过 hook、不猜测歧义 remote。
4. 查询真实 upstream，确认其 commit 等于本地交付 HEAD。
5. 尽力执行 history `finish --outcome delivered --plan <topic>/agent/plan.json \
   --stories-dir <topic>/agent/stories`。

只有计划完成门禁、整合测试、授权提交和远端 HEAD 都成立时报告完成。History 写入失败作为遥测告警
报告，但不推翻已经由 Plan、测试和 Git 证明的交付。
