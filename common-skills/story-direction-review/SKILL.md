---
name: story-direction-review
description: 独立检查已实现 Story 是否仍朝向结构化计划的 Goal，以及后续路线是否需要调整。
disable-model-invocation: true
---

# Story Direction Review

这是流程类 Skill，仅在用户显式调用 `$story-direction-review` 时运行。默认只读；普通代码缺陷、格式和
局部重构交给 Story 的 Spec/Standards review，本 Skill 只判断方向和计划影响。

## 建立独立视角

优先由未实现该 Story 的 Reviewer 执行。先运行 sibling `large-task-planning/scripts/epic_story.py brief`
取得稳定边界、目标 Story、相关黄金案例与直接前置 Handoff，再读 `status --json` 了解后续结果与依赖；
有疑点时查看 `SPEC.md`、原始证据和代码。不要把 `STATUS.md` 当成 Agent 状态源。

区分四类事实：稳定 Goal 与用户边界、Story 原意、实际交付与证据、新发现的实现假设。

## 检查方向

1. 实际结果是否满足 Story Outcome/Acceptance，还是用局部通过替代了用户结果。
2. 新事实是否推翻 `agent/plan.json` 的 Goal、黄金 oracle、边界或后续 Story 前提。
3. 黄金案例和纵向结果是否有重大遗漏，`final_story` 是否仍能闭合全部依赖路径。
4. 下一张 Story 是否能凭自身 Context 与前置 Handoff 开工，而无需发明产品决定。

## 给出唯一结论

- `CONTINUE`：方向和后续前提成立。
- `PATCH`：同一 Story 内有明确小遗漏；给出 Worker 可直接使用的修复提示。
- `INSERT_STORY`：出现新的独立工程结果；说明插入位置、依赖、验收和最小计划影响。
- `REPLAN`：Goal、黄金判据或用户边界失效；列出需要用户决定的一个最小问题。

Reviewer 不修改文件或状态。若用户另行要求应用结论，由 orchestrator 保留既有 Story ID 和已完成证据；
插入使用 `STORY-NN.M`；改变 Story Outcome/Acceptance 时递增 `intent_version`；改变 Goal、黄金判据或
用户边界时先取得用户决定并递增 `goal_version`。

## 输出

```text
结论：CONTINUE | PATCH | INSERT_STORY | REPLAN

方向证据：
- <原定结果与实际证据>
- <新事实对后续计划的影响>
- <黄金覆盖或重大遗漏>

计划动作：<无需调整，或最小调整>
下一步提示词：<Worker、orchestrator 或决策人可直接使用的内容>
```

完成标准：结论唯一、证据可追溯、没有普通代码审查噪声，下一会话能直接继续或明确停止。
