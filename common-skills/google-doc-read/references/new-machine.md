# 在另一台机器启用

前提：已有一台机器配好 rclone 远端（下称「源机器」）。授权凭据可直接复制，不必重新点同意。多台机器共用同一份授权，在谷歌账号里撤销该应用时一起失效。

## 推荐路径（长期维护）

1. 同步 mason-skills，执行 `python3 common-skills/skill-manifest-sync/scripts/sync_skill_symlinks.py --mode apply`，把本 Skill 链接到 user scope。
2. 安装 `rclone`、`uv`、`curl`、`python3`。
3. 在源机器执行 `rclone config file` 找到配置文件，把其中 `[gdrive]` 整段（含 `client_id`、`client_secret`、`token`）追加到新机器的同一文件，`chmod 600`。通过 SSH 传输，凭据不经过聊天或公开渠道。
4. 验证：`rclone lsd gdrive:` 能列出目录；再用 `scripts/gdoc_fetch.py` 读一个已知链接，输出文件路径即通过。

以后 Skill 更新随仓库同步，授权不受影响。

## 最短路径（临时机器、一次性使用）

1. 安装 `rclone`、`uv`。
2. 从源机器 `scp` 两样东西：本 Skill 目录（放到新机器的 `~/.agents/skills/google-doc-read/`）和 rclone 配置中的 `[gdrive]` 段。
3. 同上第 4 步验证。

缺点：Skill 不随仓库更新，之后要手动替换。

## 没有可复制的源机器

已有 OAuth client 时，在新机器设置 `GDRIVE_CLIENT_ID`、`GDRIVE_CLIENT_SECRET`，按 SKILL.md「重新授权」走一遍，脚本会自动创建远端。连 client 都没有时，按 [new-account.md](new-account.md) 从头打通。
