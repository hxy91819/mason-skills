---
name: ask-gpt-pro
description: 主 Agent 通过已登录的 ChatGPT 浏览器向 GPT Pro 咨询具体难题；用户明确要求 GPT Pro，或直接调查后仍有足以改变高影响技术决策的具体疑点时使用。正在回答咨询的专家、技能维护、普通实现与复查、一般复杂任务、代码检索和宽泛第二意见不触发。
---

# Ask GPT Pro

使用 Oracle CLI 的 browser engine 发送一次性咨询。Oracle 负责浏览器连接、会话记录和回答抓取；登录态由 Chromium profile 保存。先确认 `oracle` 在 PATH，并用 `oracle --version`、`oracle --help --verbose` 和 `oracle session --help` 确认当前版本支持所用参数。Oracle browser 只接 Chrome/Chromium CDP；Firefox 远程调试是 WebDriver BiDi，不能 attach。

## 浏览器入口

先探测本机 DevTools。`curl -sS -m 2 http://127.0.0.1:9222/json/version` 返回 `webSocketDebuggerUrl` 时，只 attach，不要再启动第二个浏览器：

```bash
oracle --engine browser --browser-attach-running --model gpt-6-pro --browser-archive never --verbose -p "<问题>"
```

端口不是 `9222` 时另加 `--remote-chrome <host:port>`。没有常驻 DevTools 时，使用 `--browser-manual-login`，让 Oracle 读取 `~/.oracle/config.json` 里的 `chromePath` 和 `manualLoginProfileDir`。该 profile 保存登录态；`--browser-keep-browser` 只决定进程是否常驻。无 `DISPLAY` 时，从用户图形会话复制 `DISPLAY`、`XAUTHORITY`、`DBUS_SESSION_BUS_ADDRESS` 再启动。页面出现登录按钮时停止并请用户在该 profile 登录一次，不要循环重试。当前账号没有所写模型时，根据账号可用的 Pro 型号显式调整 `--model`，检查 Oracle 的模型选择结果，不依赖网页默认选择。

2026-10-15 实测 Oracle **0.21.5** 可操作改版后的 ChatGPT：模型菜单列出 `GPT-6` 和 `GPT-5.6 Sol`；输入框按钮显示当前推理强度（如 `Medium`、`Pro`），aria-label 为 `Select ChatGPT model`。菜单中的 Thinking effort / Power 滑杆最右档为 `Pro`。以页面可见标签和滑杆状态核对，按钮的 `data-selected-reasoning-effort` 可能仍为 `medium`，不能单独作为强度依据。

`--model gpt-6-pro` 会选择 `GPT-6` 并将推理强度设为 `Pro`，默认 `--browser-model-strategy select` 即可；无需手动预选，也无需 `current` 绕过选择。`--reasoning-effort` / `--reasoning-mode` 是 API 参数，不用它们设置网页滑杆。加 `--verbose` 核对最终两条证据：

- `Model selection evidence`：`requestedKey=gpt-6-pro; target=GPT-6; resolvedLabel=GPT-6`，且 `verified=yes`。
- `Thinking effort evidence`：`requestedLevel=pro; resolvedLabel=Pro`，且 `verified=yes`。状态可以是 `switched` 或已选中。

实测该版本能识别发送成功并自动取回 `OK`。0.21.1 在该页面上找不到模型按钮；手动预选后也可能报 `Prompt did not appear` 且续取为 `Assistant turns: 0`，应升级后使用上述流程。运行前记录页面模型和强度；咨询结束或失败后恢复原值，并重新打开菜单核对；恢复默认偏好时刷新原新会话页再核对。实测已完成的 Pro 咨询页重载后仍可能显示该轮的 Pro，需与新会话默认强度分开核验。

发送问题的 browser 调用（包括 manual-login 和 follow-up）默认显式传入 `--browser-archive never`，将会话保留在 ChatGPT 历史中。只有用户明确要求归档时才改用其他策略。Oracle 自身的默认 `auto` 会归档成功的非项目单次咨询；本机通用默认可在 `~/.oracle/config.json` 的 `browser` 对象中设置 `archiveConversations: "never"`，CLI 显式参数优先。`oracle session <id>` 只取回已有记录，无需加归档参数。

## 咨询与取回

用户明确要求 GPT Pro 时按其范围咨询，无需先证明无法解决。主 Agent 自动咨询仅用于已检查相关代码、文档或失败证据，仍有足以改变高影响技术决策的具体疑点，且问题已缩小到可裁决的判断、故障序列或方案取舍。Oracle 是一次性调用，问题中写明项目背景、关键文件、已验证事实、原样报错、约束和需要裁决的问题。附文件时先用 `--dry-run summary --files-report` 核对范围；只附必要文件，不附凭据。

Pro 回答可能耗时较久；使用宿主后台任务。若超时、连接中断或报发送识别失败，先用 `oracle status --hours 72` 找到原会话，检查已有记录和页面，避免重复提交：

```bash
oracle session <id>
oracle session <id> --live
# 回答已经完成，需要重新读取网页并保存时：
oracle session <id> --harvest --write-output <回答文件>
```

`oracle session <id>` 回放本地记录；`--live` 跟踪原网页直到完成、停滞或断开，`--harvest` 读取当前已有回答。页面匹配有歧义时，后两者可加 `--browser-tab <targetId或会话URL>` 明确绑定；`--no-recover` 可关闭自动重开网页。默认找不到存活标签页时会尝试重新打开已保存的会话 URL。0.21.5 实测：自动咨询结束关闭专用标签页后，`--harvest` 成功重开原会话；`--harvest` 和 `--live` 均返回 `State: completed`、`Assistant turns: 1`、`Capture identity: matched` 和 `OK`，无需再次发问。若仍为 0，检查是否绑定了正确会话、网页是否已显示回答，不能把空抓取当作咨询完成。

完成条件是回答已取回并向提问方交付，且页面设置已恢复；咨询结论仍须由代码和测试验证。

Oracle 的会话目录保留运行日志和结果，可用 `oracle status --hours 72` 与 `oracle session <id>` 回看。本 Skill 不另建账本；Oracle 目前不记录主 Agent 对建议的接受裁决，也不提供按接受率聚合的复盘。
