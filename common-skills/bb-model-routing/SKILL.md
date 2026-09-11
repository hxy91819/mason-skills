---
name: bb-model-routing
description: 用户要求用 BB 派发任务或开线程时使用，通过 `$bb-model-routing` 显式调用。查看或继续已有线程、模型咨询及修改本技能时不触发。
disable-model-invocation: true
---

# BB 任务派发

本技能默认仅显式触发，使用 `$bb-model-routing` 调用。

为用户已要求的任务调用 `scripts/bb-dispatch`。工具别名、模型、推理级别和环境映射以用户配置为准；首次配置或调整映射时读取 [配置与派发](references/dispatch.md)，使用其中的配置模板。参数细节查 `bb-dispatch --help`。

## 判断与调用

- `simple`：局部改动，步骤与验收清楚。
- `medium`：范围明确，涉及少量模块或需要比较方案。
- `complex`：跨模块设计、根因难定位或较多不确定性。
- 排查问题、找 bug 额外传 `--kind debug`，即使任务简单也保留该类型。
- 专门做测试验证、单测编写或执行验证额外传 `--kind test`。

```bash
bb-dispatch --difficulty medium --kind debug --task '<任务目标、范围与验收要求>'
bb-dispatch --difficulty medium --kind test --task '<测试目标、范围与验收要求>'
```

`--task` 只写任务目标、范围、输入和验收要求。provider、模型、推理级别和可用性检查是派发元数据：由 `bb-dispatch` 根据配置和目录决定，不写入子线程 prompt，也不要求子 agent 在开始前重新查询或确认。用户明确指定 provider 或模型时，将该要求映射到配置别名或配置调整，仍不把路由要求带入 `--task`。

用户指定工具别名或已有对应工具上下文时用 `--agent <配置别名>`，别名由用户配置定义，不推断本机已安装哪些工具。只有用户明确指定推理级别时才传 `--reasoning`；其余由脚本读取配置。配置未指定时省略该参数，使用 provider 默认值。命令未安装时直接执行本技能的 `scripts/bb-dispatch`。需要预览用 `--dry-run`，脚本已完成的环境与模型校验无需重复查询。

## 派发边界

所有 provider、模型、推理级别和默认路由均来自用户配置；脚本在创建前完成相应目录校验。父 agent 只负责选择任务难度、类型和配置别名，不能把路由选择或二次校验职责下放给子 agent。首次使用先按参考文档查询目标环境，再填写配置。缺少配置时完成配置准备，校验通过后再派发。

路由不可用或额度耗尽时报告原因；仅使用用户明确选择的替代配置别名，不内置渠道优先级或自动切换。

权限须符合任务授权；配置缺失或校验失败时说明缺口，不静默换模型或升权。

并发任务可能产生修改冲突时，可以使用 `use-worktree` 隔离；无冲突时沿用当前环境。操作前检查分支、工作区和 worktree，遵守用户授权。隔离环境准备好后用 `--environment` 指定，脚本只使用已有 BB 环境。

派发标题由脚本统一加 `[Agent]` 前缀；需要简短标题时传 `--title`，省略时从任务文本截取。

根据返回结果报告线程 ID、实际选择和状态。创建成功不代表任务完成；创建结果不明时先查询线程，避免重复派发。

## 作为编排后端

`large-task-orchestrator` 的确定性 driver 通过本技能派 Worker、Validator 与异常时的 Judge：Worker 按
能力档映射为 `--difficulty`，Validator 固定 `--difficulty simple --kind test`，Judge 固定 `--difficulty complex --kind judge`。
driver 只传任务文本、难度、类型与已有环境，路由仍由本配置决定；状态机、wait/output/tell 兼容性见其
[`references/bb-dispatch-loop.md`](../large-task-orchestrator/references/bb-dispatch-loop.md)。

`defaults.test` 决定 Validator 路由，`defaults.judge` 单独决定 Judge 路由，Worker 使用难度路由或
`debug` 路由。`agents.<别名>.routes` 按角色、难度和 `default` 项配置模型与 reasoning，选择规则见
[配置与派发](references/dispatch.md)。

## 可观测性

使用 `--dry-run` 只读检查当前选择、目标环境和启动参数；派发返回实际选择与原始创建回执。当前没有持久运行历史、裁决回写或跨运行聚合，无法统计长期成功率；故障定位依赖返回错误和 BB 线程记录。
