---
name: chatgpt-web-image
description: 通过已登录的 ChatGPT 浏览器生成并保存新位图；任务确需原创图片、用户指定网页生图，或需要续取已有会话图片时使用。已有图片编辑、SVG 和数据图表不触发。
---

# ChatGPT 网页生图

使用 Oracle CLI 的 browser engine 和 `--generate-image`，复用已登录的 Chromium profile。先确认 `oracle` 在 PATH，并用 `oracle --help --verbose` 确认当前版本支持 `--generate-image`。Oracle browser 只接 Chrome/Chromium CDP；Firefox 远程调试是 WebDriver BiDi，不能 attach。

## 浏览器入口

先探测本机 DevTools。`curl -sS -m 2 http://127.0.0.1:9222/json/version` 返回 `webSocketDebuggerUrl` 时，只 attach，不要再启动第二个浏览器：

```bash
oracle --engine browser --browser-attach-running --browser-model-strategy current \
  --generate-image /absolute/path/artifacts/teapot.png \
  -p "生成一张蓝绿色陶瓷茶壶的产品摄影，奶油色背景，柔和光照，无文字。"
```

端口不是 `9222` 时另加 `--remote-chrome <host:port>`。没有常驻 DevTools 时，使用 `--browser-manual-login`，让 Oracle 读取 `~/.oracle/config.json` 里的 `chromePath` 和 `manualLoginProfileDir`。该 profile 保存登录态；`--browser-keep-browser` 只决定进程是否常驻。无 `DISPLAY` 时，从用户图形会话复制 `DISPLAY`、`XAUTHORITY`、`DBUS_SESSION_BUS_ADDRESS` 再启动。页面出现登录按钮时停止并请用户在该 profile 登录一次，不要循环重试。

## 生成

根据交付物明确画面、用途和尺寸。输出路径优先使用用户指定位置；否则放在当前项目的 `artifacts/` 中，并避免覆盖已有文件。生图使用网页当前模型，保持 Medium，不要传 `--model gpt-*-pro`。账号与网页模型需支持图片生成；检查实际输出是否为图片。

Oracle 会在 ChatGPT 返回可下载图片时保存至指定路径；多张图片保存为带序号的相邻文件。完成以文件实际保存并可打开为准，检查图片内容后提供文件链接或直接展示。

## 恢复

若提交后超时，先用 `oracle status --hours 72` 找原会话，再用 `oracle session <id> --render` 查看结果和会话 artifacts。提示已提交但 CLI 失败时，先看已打开的 ChatGPT 标签是否已出图，已出则下载该图，不要重发。用户提供任意 ChatGPT 会话地址时，在同一已登录浏览器中打开该会话并下载已有图片；不为取图重新发送生成请求。Oracle 的会话记录可用于回看运行结果；本 Skill 不另建账本，当前没有图片质量裁决的聚合统计。
