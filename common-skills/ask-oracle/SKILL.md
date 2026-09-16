---
name: ask-oracle
description: 咨询独立专家模型处理用户明确要求的 Oracle 审查，或主 Agent 直接调查后仍无法解决、足以改变高影响技术决策的具体疑点。普通复查、一般复杂任务、代码检索和宽泛第二意见不触发。
---

# Ask Oracle

通过 BB 派发一个只读专家线程，取得独立技术判断后返回结果。用户显式调用 `$ask-oracle` 时直接执行；自动触发只用于已完成直接调查后仍未解决的具体高影响问题。

## 咨询门槛

先自行读取相关代码、文档、diff 与失败证据。只有 Oracle 的答案会实质改变当前决策，且问题已经缩小到可裁决的判断、故障序列或方案取舍时才派发。用户明确要求 Oracle 时按其范围派发，无需先证明无法解决。

## 形成任务

把咨询任务写成以下信息结构，但只保留会改变判断的内容：

```markdown
# Goal
<用户要达成的结果与验收标准>

# Verified context
- <已验证事实、约束、文件位置、测试或失败证据>

# Proposals and hypotheses
- <来源方>: <候选方案或尚未验证的解释>

# Question for the oracle
<一个明确的技术判断；说明答案将决定什么>

# Expected response
<所需结论、证据、失败序列、推荐方案或最小修复；列出应忽略的范围>
```

区分已验证事实、来源方提案、主 Agent 假设和未知项；不把假设写成事实。已有可行选项应连同真实权衡交给 Oracle，而不是为了表面中立而删掉。使用 `@路径` 指向最相关文件，并明确要求专家检查这些文件或当前 diff。每项信息只出现一次。

## 派发并交付

调用 `$bb-model-routing`，由宿主在 project scope、user scope 或其他已安装来源中解析该 Skill。按它的派发入口提交以下参数：

```text
difficulty: complex
kind: oracle
permission-mode: accept-edits
title: Oracle: <简短问题>
task: <上述咨询任务>
```

由 `bb-model-routing` 从自己的 Skill 根目录运行内部派发器。宿主无法加载该 Skill 时报告依赖缺失，不猜测任何安装路径。

`oracle` 路由由用户配置决定；推荐默认值为 Codex `gpt-6-astra`、reasoning `xhigh`。不在任务正文中重复 provider、模型或 reasoning。派发失败时报告原路由错误，不静默改用其他模型。

记录返回的线程 ID、实际模型与状态。创建成功只是开始：等待 BB 的父线程完成通知，不轮询；通知到达后用 `bb thread output <线程 ID>` 读取最终输出。向用户返回 Oracle 的结论、关键依据和仍未解决的不确定性，并附线程链接或 ID。专家要求补充关键信息时，把具体缺口转告用户，不替专家猜测。

流程完成条件是专家结果已取回并交付，而不是只生成咨询简报或只创建线程。
