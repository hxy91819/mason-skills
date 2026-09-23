---
name: autoreview
description: "提交或发布前的代码审查；通过 bb-model-routing 派发独立 review agent。"
disable-model-invocation: true
triggers:
  - user
---

# Auto Review

这是用户显式调用 `$autoreview` 的审查流程。必须先按名称加载 `$bb-model-routing`；其路由配置是 reviewer 的 provider、模型、推理级别与 fallback 的唯一来源。依赖不可用时报告缺失，不改用本机 CLI 或宿主 subagent。

## 派发审查

先确定准确的审查目标：未提交改动、分支相对指定 base 的差异，或指定 commit；同时整理原始需求和验收条件。读取[审查提示词](references/review-prompt.md)，把其中完整的审查标准、输出格式与本次具体范围一起写入 `--task`。按已加载的 `$bb-model-routing` 契约调用其派发入口，固定使用 `medium` 难度：

```bash
bb-dispatch --difficulty medium --task '<仓库、Git 审查范围、原始需求、验收条件，以及 references/review-prompt.md 的完整审查标准和输出格式>'
```

将占位文本换成实际路径、ref、需求和提示词内容；不要只把提示词文件路径交给 reviewer，因为派发环境可能无法读取该文件。模型或推理级别不写入 `--task`；目标环境和失败续派按 `$bb-model-routing` 的规则处理。向用户报告线程 ID、实际选择和状态；通过 BB 完成通知接收结果。创建线程不等于审查完成。

## 核实与收尾

主 Agent 逐条核实发现，阅读相关代码与必要的依赖契约。接受当前任务范围内真实、可操作的缺陷；说明拒绝项理由。修复后运行相关验证，再对新差异派发一次 `medium` 审查，直到没有仍需处理的发现。超出原任务的产品或接口决策交给用户决定。

最终报告列出审查范围、线程 ID、验证结果，以及发现的处理结果。用 `bb thread show <线程ID>` 回看派发与审查记录；当前没有跨线程的自动裁决统计。
