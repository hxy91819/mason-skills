---
name: google-doc-read
description: 读取 Google 表格/文档/幻灯片/Drive 文件链接的内容。消息里出现 docs.google.com 或 drive.google.com 链接、或用户要求查看别人分享的谷歌文档时使用。
---

# 读取 Google 文档链接

经 rclone 远端 `gdrive:`（Drive **只读** OAuth，能看到分享给该谷歌账号的文件）读取；失败时回退到公开导出链接（仅限「知道链接的人可查看」的文件）。远端名可用 `GDOC_RCLONE_REMOTE` 覆盖。下文 `scripts/` 指本 Skill 根目录下的脚本。

## 读取

```bash
scripts/gdoc_fetch.py '<链接或文件ID>' [--out /tmp/gdoc]
```

依赖 `rclone` 和 `uv`。输出每行一个本地文件路径，位于 `<out>/<文件ID>/`：

- 表格：`<名>.xlsx` 加每个页签一个 `<名>__<页签>.csv`（公式取计算值，整数不带 `.0`）。优先读 CSV。
- 文档：`<名>.md`。
- 幻灯片：`<名>.pptx`；普通 Drive 文件按原格式下载。

每次运行都重新拉取云端最新版本。读完即可删除下载目录。

失败时：

- `rclone 失败` 且公开链接返回登录页：文件没分享给已授权账号，请用户让对方分享给自己，或设为「知道链接的人可查看」。
- 未配置远端：按「新机器配置」处理。
- token 失效 / `invalid_grant`：按「重新授权」处理。

## 新机器配置

1. 安装 `rclone`、`uv`。
2. 从已配置好的机器复制 rclone 配置（`rclone config file` 查看路径）里的 `[gdrive]` 整段到新机器同一文件，`chmod 600`。用 `rclone lsd gdrive:` 验证。多台机器共用同一授权，在谷歌账号撤销时一起失效。
3. 没有可复制的机器时，按「重新授权」新建，事先设置 `GDRIVE_CLIENT_ID`、`GDRIVE_CLIENT_SECRET`。

OAuth client 要用户自建（rclone 自带的共享 client 在 2026 年内停用）：Google Cloud 项目启用 Drive API，创建 Desktop 类型 client，并把应用发布为 In production；停在 Testing 时 refresh token 7 天过期。发布前控制台要求 Branding 填写主页、隐私政策、服务条款链接及已在 Search Console 验证的授权域名。

## 重新授权（无头机器，用户手机即可完成）

1. `scripts/reauth.sh start`：输出谷歌授权地址，发给用户打开并同意（遇「未验证应用」点 高级 → 继续）。
2. 用户回传跳转后打不开的 `http://127.0.0.1:53682/?state=...&code=...` 地址。
3. `scripts/reauth.sh finish '<该地址>'`：换取 token、写入远端（不存在则创建）、打印已授权账号。拿不到 token 时不改配置并报错。code 只能用一次，失败从第 1 步重来。

token 只经脚本写入配置，不出现在对话里。
