---
name: bb-model-routing
description: 用户要求用 BB 派发任务或开线程时使用，例如“用 bb 派发任务”“用 bb 派发 codexl 做 xxx”“用 bb 派发 pi 做 xx”。查看或继续已有线程、模型咨询及修改本技能时不触发。
---

# BB 任务派发

为用户已要求的任务调用 `scripts/bb-dispatch`。工具别名、模型、推理级别和环境映射以用户配置为准；首次配置或调整映射时读取 [配置与派发](references/dispatch.md)，使用其中的配置模板。参数细节查 `bb-dispatch --help`。

## 判断与调用

- `simple`：局部改动，步骤与验收清楚。
- `medium`：范围明确，涉及少量模块或需要比较方案。
- `complex`：跨模块设计、根因难定位或较多不确定性。
- 排查问题、找 bug 额外传 `--kind debug`，即使任务简单也保留该类型。

```bash
bb-dispatch --difficulty medium --kind debug --task '<任务目标、范围与验收要求>'
```

用户指定工具或已有对应工具上下文时用 `--agent <配置别名>`，例如 codexl 或 pi。只有用户明确指定推理级别时才传 `--reasoning`；其余由脚本读取配置，尤其 GLM 5.3 Flash 的 `max` 不要按任务难度自行改写。命令未安装时直接执行本技能的 `scripts/bb-dispatch`。需要预览用 `--dry-run`，脚本已完成的环境与模型校验无需重复查询。

## 派发边界

Pi 的 GLM 5.3 Flash 默认走 Ollama Cloud，另有 Zai 路由，两者均用 `max`。观察到当前路由明确额度耗尽时，可以告知用户并切到另一条；具体别名和原线程续接方法见 [Pi 额度切换](references/dispatch.md#pi-额度切换)。用户限定渠道时保留其限制，普通超时或限速不视为额度耗尽。

权限须符合任务授权；配置缺失或校验失败时说明缺口，不静默换模型或升权。

并发任务可能产生修改冲突时，可以使用 `use-worktree` 隔离；无冲突时沿用当前环境。操作前检查分支、工作区和 worktree，遵守用户授权及当前 git wrapper；拦截时按 stderr 和 `git --wrapper-help` 处理，不绕过。隔离环境准备好后用 `--environment` 指定，脚本只使用已有 BB 环境。

根据返回结果报告线程 ID、实际选择和状态。创建成功不代表任务完成；创建结果不明时先查询线程，避免重复派发。
