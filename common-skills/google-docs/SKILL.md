---
name: google-docs
description: 读写用户 Google Drive 中的表格、文档、幻灯片和文件。消息里出现 docs.google.com 或 drive.google.com 链接，或用户要求查看、新建、修改、上传、删除谷歌文档/表格时使用。
---

# Google Docs 读写

两个 rclone 远端共用同一个自建 OAuth client：

| 远端 | 权限 | 用途 |
|---|---|---|
| `gdrive:` | `drive.readonly` | 读取（默认）。能看到分享给该账号的文件；失败时回退到公开导出链接 |
| `gdrive-rw:` | `drive,documents,spreadsheets` | 新建、修改、上传、删除；也能写入别人分享且给了编辑权限的文件 |

下文 `scripts/` 指本 Skill 根目录下的脚本。

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
- 未配置远端：按「配置」一节处理。

## 写入

单元格、文档正文等结构化编辑用 `scripts/gog.sh <gog 子命令>`：它用 `gdrive-rw:` 的 refresh token 现换 access token 后执行 [gog](https://github.com/openclaw/gogcli)，不需要 gog 自己登录（启动时提示 `Using direct access token` 属正常）。远端可用 `GOG_RCLONE_REMOTE` 覆盖。子命令用 `gog <服务> --help` 查。常用：

```bash
scripts/gog.sh sheets create '<标题>' -j                                  # 新建表格，返回 spreadsheetId
scripts/gog.sh sheets update <id> 'Sheet1!A1:B2' --values-json '[["name","qty"],["apple",3]]'
scripts/gog.sh sheets append <id> 'Sheet1!A:B' --values-json '[["pear",5]]'
scripts/gog.sh sheets get <id> 'Sheet1!A1:D20' -j
scripts/gog.sh docs create '<标题>' -j                                     # 新建文档
scripts/gog.sh docs write <id> --file note.md --markdown --replace        # 覆盖正文；--append 追加
scripts/gog.sh docs cat <id>
scripts/gog.sh drive ls -j / drive search '<关键词>' -j / drive delete <id> --force
```

整份文件上传用 rclone。把本地 csv/xlsx/docx 转成谷歌原生格式时，`--drive-import-formats` 和 `--drive-export-formats` 要给同一格式，否则报 `can't convert ... different export filetype`：

```bash
rclone copy report.xlsx gdrive-rw:<目录> --drive-import-formats xlsx --drive-export-formats xlsx
```

删除进回收站（`gog drive delete`、`rclone delete` 均如此），30 天内可在 Drive 网页恢复。
- token 失效 / `invalid_grant`：按「重新授权」处理。

## 配置

- 在另一台机器启用（已有配好的机器可复制授权）：读 [references/new-machine.md](references/new-machine.md)。
- 打通新的谷歌账号、从零自建 OAuth client，或给账号开通写入（`gdrive-rw:`）：读 [references/new-account.md](references/new-account.md)。

## 重新授权（无头机器，用户手机即可完成）

只读远端直接运行；`gdrive-rw` 前缀 `GDOC_RCLONE_REMOTE=gdrive-rw GDRIVE_SCOPE=drive,documents,spreadsheets`。

1. `scripts/reauth.sh start`：输出谷歌授权地址，发给用户打开并同意（遇「未验证应用」点 高级 → 继续）。
2. 用户回传跳转后打不开的 `http://127.0.0.1:53682/?state=...&code=...` 地址。
3. `scripts/reauth.sh finish '<该地址>'`：换取 token、写入远端（不存在则创建）、打印已授权账号。拿不到 token 时不改配置并报错。code 只能用一次，失败从第 1 步重来。

token 只经脚本写入配置，不出现在对话里。
