---
name: ask-gpt-pro
description: 通过已登录的 ChatGPT 浏览器向 GPT Pro 咨询具体难题；用户明确要求 GPT Pro，或 Agent 调查后仍有会改变下一步的疑点时使用。普通实现、例行复查和宽泛第二意见不触发。
---

# Ask GPT Pro

使用 Oracle CLI 的 browser engine 发送一次性咨询。Oracle 负责浏览器连接、会话记录和回答抓取；登录态由 Chromium profile 保存。先确认 `oracle` 在 PATH，并用 `oracle --help --verbose` 确认当前版本支持所用参数。Oracle browser 只接 Chrome/Chromium CDP；Firefox 远程调试是 WebDriver BiDi，不能 attach。

## 浏览器入口

先探测本机 DevTools。`curl -sS -m 2 http://127.0.0.1:9222/json/version` 返回 `webSocketDebuggerUrl` 时，只 attach，不要再启动第二个浏览器：

```bash
oracle --engine browser --browser-attach-running --model gpt-6-pro --browser-archive never -p "<问题>"
```

端口不是 `9222` 时另加 `--remote-chrome <host:port>`。没有常驻 DevTools 时，使用 `--browser-manual-login`，让 Oracle 读取 `~/.oracle/config.json` 里的 `chromePath` 和 `manualLoginProfileDir`。该 profile 保存登录态；`--browser-keep-browser` 只决定进程是否常驻。无 `DISPLAY` 时，从用户图形会话复制 `DISPLAY`、`XAUTHORITY`、`DBUS_SESSION_BUS_ADDRESS` 再启动。页面出现登录按钮时停止并请用户在该 profile 登录一次，不要循环重试。当前账号没有所写模型时，根据账号可用的 Pro 型号显式调整 `--model`，检查 Oracle 的模型选择结果，不依赖网页默认选择。

GPT-6 Astra 在 ChatGPT 的高级模型选择器中显示为 `Latest`（本地化界面可能显示“最新”），Pro 档位的输入框标签为 `6 Pro`。`--model gpt-6-pro` 需要 Oracle 同时支持这一模型选择器和 Pro 档位；核对实际选择结果，不能只根据 CLI 接受模型参数就判定已适配。

发送问题的 browser 调用（包括 manual-login 和 follow-up）默认显式传入 `--browser-archive never`，将会话保留在 ChatGPT 历史中。只有用户明确要求归档时才改用其他策略。Oracle 自身的默认 `auto` 会归档成功的非项目单次咨询；本机通用默认可在 `~/.oracle/config.json` 的 `browser` 对象中设置 `archiveConversations: "never"`，CLI 显式参数优先。`oracle session <id>` 只取回已有记录，无需加归档参数。

## 咨询与取回

用户明确要求 GPT Pro 时按其范围咨询。自动咨询仅用于已检查相关代码、文档或失败证据，仍有一个会改变下一步的具体疑点。Oracle 是一次性调用，问题中写明项目背景、关键文件、已验证事实、原样报错、约束和需要裁决的问题。附文件时先用 `--dry-run summary --files-report` 核对范围；只附必要文件，不附凭据。

Pro 回答可能耗时较久；使用宿主后台任务。若超时或连接中断，先用 `oracle status --hours 72` 找到原会话，再运行 `oracle session <id>` 续取，避免重复提交。完成条件是回答已取回并向提问方交付；咨询结论仍须由代码和测试验证。

Oracle 的会话目录保留运行日志和结果，可用 `oracle status --hours 72` 与 `oracle session <id>` 回看。本 Skill 不另建账本；Oracle 目前不记录主 Agent 对建议的接受裁决，也不提供按接受率聚合的复盘。
