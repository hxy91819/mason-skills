# HTML 预览：一次性部署与自动清理

本技能只发布副本，不自动安装或改写服务器入口。首次部署先读[账号密码 HTML 预览配方](../../../docs/authenticated-html-preview.md)，复用 Caddy、OAuth2 Proxy、账号文件和登录模板。内网 `.test` 使用 [Mac 开发 CA](../../local-test/references/macos-preview-setup.md)，不套用公网 ACME；动态项目与静态站点并存方式参考 [Caddy 统一入口](../../local-test/references/server-preview-setup.md)。

## 本机配置

管理员准备独立静态站点，如 `html.preview.test`，在认证之后把 `/previews/*` 映射到专用静态目录，保持原配方不列目录、不跟随发布的符号链接、不公开状态文件的边界。同站点静态 HTML 之间同源，只托管当前可信任务产物。

示例 `/etc/html-preview/publish.json`（真实地址由管理员核实替换，配置不提交 Git）：

```json
{
  "publish_root": "/srv/html-preview",
  "state_root": "/var/lib/html-preview-expiry",
  "base_url": "https://html.preview.test/previews",
  "login_url": "https://html.preview.test/oauth2/sign_in"
}
```

base_url 是 ID 之前的路径，login_url 不带 query，脚本会生成编码后的 rd。两者必须同一 HTTPS origin，不能包含凭据。目录必须绝对路径、互不包含、无符号链接，发布和状态目录都只能由管理账号写入，组和其他用户不可写；状态目录不能作为 HTTP 根目录或位于被测仓库。

目录初始创建示例沿用原配方：发布根 root:preview-auth、750；状态目录 root:root、700。脚本应由有权写这些目录的管理员或明确配置的发布账号执行，Caddy 用户只读。若使用专用发布账号，调整目录所有者而非授予所有用户写权限。状态、日志、真实配置均在 Git 外，不能将 root 服务的执行文件指向普通用户可修改的 checkout。

## 安装清理器

将本技能 `scripts/preview.py` 审核后安装到 `/opt/html-preview/preview.py`，root 所有、755。该脚本仅用 Python 标准库和 Linux 文件锁，无需 pip 安装。变更脚本后由管理员更新此安装副本，不让系统服务直接执行仓库文件。

本版登记格式与旧文档的简易 expires_at 记录不同。旧记录不会被新 gc 自动接管；先用旧清理器完成已有产物的回收，或明确清点迁移，再切换。**同一发布目录不并行运行旧 gc.py 与新 preview.py gc**，否则旧清理器不会遵守新版文件锁和额外文件保护。保留旧产物和源文件，不为迁移清空发布根。

替换已有清理服务前核对其用途；以下单元使用原配方的服务名，以便迁移而不重复安装 timer：

```ini
# /etc/systemd/system/html-preview-gc.service
[Unit]
Description=Remove registered expired HTML preview copies
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /opt/html-preview/preview.py --config /etc/html-preview/publish.json gc
User=root
Group=root
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
NoNewPrivileges=true
ReadWritePaths=/srv/html-preview /var/lib/html-preview-expiry
UMask=0027
```

```ini
# /etc/systemd/system/html-preview-gc.timer
[Unit]
Description=Check HTML preview expiry every five minutes
[Timer]
OnCalendar=*:0/5
Persistent=true
[Install]
WantedBy=timers.target
```

自定义目录时同步更新单元 ReadWritePaths。`publish` 与 timer 使用相同配置、状态目录和管理身份，续期/清理通过同一个文件锁串行执行。停止 timer 不删除文件；切换配置前要避免已有 gc 进程仍在运行。

```bash
sudo systemd-analyze verify /etc/systemd/system/html-preview-gc.service /etc/systemd/system/html-preview-gc.timer
sudo systemctl daemon-reload
sudo systemctl enable --now html-preview-gc.timer
sudo systemctl list-timers html-preview-gc.timer
sudo python3 /opt/html-preview/preview.py --config /etc/html-preview/publish.json show
```

只有目录、配置、网关均就绪才启用 timer。无需为每次 HTML 发布重启 Caddy 或认证服务。默认 24 小时到期，每五分钟清理；主机关闭或清理失败会延后，不保证到秒拒绝访问。

## 验收与运维

发布测试自包含 HTML，确认输出真实 URL/登录链接与到期时间。未登录不能读取正文；登录后 HTML 及其资源正常。删除测试 ID 后目标 404，源文件仍存在。测试到期行为可用脚本的单元测试，不为验收改写真实预览记录或机器时间。

检查 timer 有下一次运行时间，`systemctl status html-preview-gc.service` 与 journal 能显示最近结果。首次手动运行 `gc` 会实际删除当前到期副本，需先 `show` 核对。续期仅更新登记；过期但尚未删除的副本可续期，已删除的必须重新发布。

gc 遇到未知格式、额外文件、损坏记录或符号链接会保留并返回错误。管理员先核实来源再处置，不能自动删除这些异常来获得“干净”状态。清理仅 unlink index.html 后移除空目录，不递归删除任意树；未登记目录、发布源和其他项目资源不会被扫描删除。
