---
kind: story
id: STORY-01
epic: EPIC-TOKEN-LOGIN
title: 一次性令牌签发与邮箱投递
gate: COMPONENT
depends_on: []
updated: 2026-08-18
intent_version: 1
language: zh-Hans
---

# 一次性令牌签发与邮箱投递

<!-- large-task-planning:vision -->
## 愿景

员工在登录页输入企业邮箱后，一分钟内收到一封登录邮件，里面有一次可用的登录链接和验证码。令牌在服务端安全生成，只保存摘要。这是后续验证、防护和审计的唯一输入源。

<!-- large-task-planning:scope -->
## 范围

登录页新增邮箱输入与申请入口；令牌生成、摘要存储和邮件投递按 Epic「全局设计」与《一次性令牌契约》执行，邮件文案一并交付。令牌校验、会话建立、强制频控和审计事件不在本 Story 内。

<!-- large-task-planning:key-decisions -->
## 关键决策

<!-- large-task-planning:decision owner=user -->
1. **令牌通过企业邮箱投递，同一封邮件同时提供登录链接与 6 位验证码。**
   - 决定者：用户。
   - Agent 建议：对比 IM 机器人和短信渠道后建议邮箱方案，用户采纳；链接方便桌面端，验证码方便手机查看邮件时使用。
   - 结果与影响：用户无需安装或运维新客户端；代价是登录依赖邮件服务可用性，投递时延要在 STORY-05 验收。

<!-- large-task-planning:acceptance-criteria -->
## 验收标准

- 企业邮箱提交后 1 分钟内收到邮件，链接与验证码都可用。
- 非企业域名邮箱被拒绝，并提示原因。
- 服务端不存明文令牌，只存摘要、签发时间与到期时间。
- 登录页与邮件文案为中文，不出现技术术语。
