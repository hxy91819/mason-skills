---
name: ask-gpt-pro
description: 通过已登录的 ChatGPT 浏览器向 GPT Pro 咨询具体难题；用户明确要求 GPT Pro，或 Agent 调查后仍有会改变下一步的疑点时使用。普通实现、例行复查和宽泛第二意见不触发。
---

# Ask GPT Pro

使用 Oracle CLI 的 browser engine 发送一次性咨询。Oracle 负责浏览器连接、会话记录和回答抓取；登录态由浏览器 profile 保存。该 Skill 不管理 Chrome、显示服务或本机账号配置。

## 浏览器入口

先确认 `oracle` 可用，并从 `oracle --help --verbose` 确认当前版本支持所用参数。优先复用已有、已登录且开放 Chrome DevTools 的浏览器：

```bash
oracle --engine browser --browser-attach-running --model gpt-6-pro -p "<问题>"
```

浏览器端口不是默认值时，另加 `--remote-chrome <host:port>`。首次登录或需要 Oracle 自己持有持久 profile 时，使用 `--browser-manual-login --browser-keep-browser`；后续运行继续使用该 profile。`--browser-keep-browser` 只决定进程是否常驻，登录态保存在 profile 中。当前账号没有所写模型时，根据账号可用的 Pro 型号显式调整 `--model`，检查 Oracle 的模型选择结果，不依赖网页默认选择。

## 咨询与取回

用户明确要求 GPT Pro 时按其范围咨询。自动咨询仅用于已检查相关代码、文档或失败证据，仍有一个会改变下一步的具体疑点。Oracle 是一次性调用，问题中写明项目背景、关键文件、已验证事实、原样报错、约束和需要裁决的问题。附文件时先用 `--dry-run summary --files-report` 核对范围；只附必要文件，不附凭据。

Pro 回答可能耗时较久；使用宿主后台任务。若超时或连接中断，先用 `oracle status --hours 72` 找到原会话，再运行 `oracle session <id>` 续取，避免重复提交。完成条件是回答已取回并向提问方交付；咨询结论仍须由代码和测试验证。

Oracle 的会话目录保留运行日志和结果，可用 `oracle status --hours 72` 与 `oracle session <id>` 回看。本 Skill 不另建账本；Oracle 目前不记录主 Agent 对建议的接受裁决，也不提供按接受率聚合的复盘。
