---
name: chatgpt-web-image
description: 通过已登录的 ChatGPT 浏览器生成并保存新位图；任务确需原创图片、用户指定网页生图，或需要续取已有会话图片时使用。已有图片编辑、SVG 和数据图表不触发。
---

# ChatGPT 网页生图

使用 Oracle CLI 的 browser engine 和 `--generate-image`，复用已登录的浏览器 profile。先用 `oracle --help --verbose` 确认当前版本支持 `--generate-image`。本 Skill 不依赖特定机器上的 Chrome 服务、脚本仓库或包装命令。

## 生成

根据交付物明确画面、用途和尺寸。输出路径优先使用用户指定位置；否则放在当前项目的 `artifacts/` 中，并避免覆盖已有文件。复用已有、已登录且开放 Chrome DevTools 的浏览器：

```bash
oracle --engine browser --browser-attach-running \
  --generate-image /absolute/path/artifacts/teapot.png \
  -p "生成一张蓝绿色陶瓷茶壶的产品摄影，奶油色背景，柔和光照，无文字。"
```

非默认浏览器端口另加 `--remote-chrome <host:port>`。没有常驻浏览器时，Oracle 可用 `--browser-manual-login` 启动持久 profile；首次登录时加 `--browser-keep-browser` 方便完成登录。登录态保存在 profile，关闭浏览器进程后仍可复用。账号与网页模型需支持图片生成；若使用当前选中的模型，检查实际输出是否为图片。需要指定模型时显式加 `--model <账号可用型号>`。

Oracle 会在 ChatGPT 返回可下载图片时保存至指定路径；多张图片保存为带序号的相邻文件。完成以文件实际保存并可打开为准，检查图片内容后提供文件链接或直接展示。

## 恢复

若提交后超时，先用 `oracle status --hours 72` 找原会话，再用 `oracle session <id> --render` 查看结果和会话 artifacts。用户提供任意 ChatGPT 会话地址时，在同一已登录浏览器中打开该会话并下载已有图片；不为取图重新发送生成请求。Oracle 的会话记录可用于回看运行结果；本 Skill 不另建账本，当前没有图片质量裁决的聚合统计。
