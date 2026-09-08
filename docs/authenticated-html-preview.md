# 单服务器：账号密码登录 + 临时 HTML 预览

适用于有公网服务器、希望在手机浏览器查看私人 HTML 的个人工作空间。无需 Tailscale、额外中继或自行编写认证系统。本文是部署配方，不是自动安装器；执行前核对本机端口、目录和已有服务。

动态应用（前端、API、WebSocket）的子域名预览使用 [local-test 服务器配置](../common-skills/local-test/references/server-preview-setup.md)。两者可共用 Caddy 实例和账号库；动态应用通过独立认证子请求校验 Cookie，保留业务 Authorization，不直接套用本文删除 Authorization 的静态代理链路。项目服务生命周期不受本文 HTML 到期清理器管理。

Agent 发布生成的 HTML 时使用 [html-preview skill](../common-skills/html-preview/SKILL.md)，按其配置运行带文件锁的发布、续期和清理命令。新脚本与本文简易清理器不能同时管理同一目录，迁移方法见 [部署与清理](../common-skills/html-preview/references/setup.md)。

## 架构

```text
手机 Safari / 主屏幕 App
       │ HTTPS :443
       ▼
Caddy：证书管理、反向代理、Origin 检查
       ▼
OAuth2 Proxy：127.0.0.1:4180
账号密码表单 → 安全 Cookie，登录保持 7 天
       ▼
Caddy：127.0.0.1:4181
静态文件 /srv/html-preview/<id>/index.html

定时清理器：根据独立的到期记录删除指定预览目录
```

访问地址为 `https://preview.example.com/previews/<id>/`。两段内部代理都在本机，不需要 VPN。OAuth2 Proxy 使用成熟的 htpasswd 登录和 Cookie 实现；Caddy Basic Auth 的浏览器弹框更简单，但手机登录保持不如 Cookie 方案明确。

以下使用保留示例域名 `preview.example.com`，部署时统一替换成自己的域名。本文沿用验证过的 Caddy 2.11.4、OAuth2 Proxy 7.15.4 配置接口；新部署应检查当前维护版本、发布说明及校验和，不能直接拉取不固定版本的 `latest`。

## 1. 前置准备

- Debian/Ubuntu、systemd；安装 Python 3、`apache2-utils`（提供 `htpasswd`）。
- 从 [Caddy releases](https://github.com/caddyserver/caddy/releases) 和 [OAuth2 Proxy releases](https://github.com/oauth2-proxy/oauth2-proxy/releases) 下载匹配 CPU 架构的二进制并校验官方摘要。
- root 拥有的二进制安装到 `/opt/html-preview/caddy` 和 `/opt/html-preview/oauth2-proxy`，权限 755。
- 公网只开放入口 TCP443、必要的 SSH；4180、4181 只监听本机，Caddy管理API关闭。以下配置通过443验证证书，不占用80。
- 若443已有服务，将配置整合进现有代理，不能启动第二个进程抢占端口。

创建服务用户和目录；已有用户/配置时先检查、备份，不覆盖：

```bash
sudo useradd --system --home /var/lib/html-preview --shell /usr/sbin/nologin preview-auth
sudo install -d -o root -g preview-auth -m 750 /etc/html-preview
sudo install -d -o preview-auth -g preview-auth -m 750 /var/lib/html-preview
sudo install -d -o root -g preview-auth -m 750 /srv/html-preview
sudo install -d -o root -g root -m 700 /var/lib/html-preview-expiry
```

本例只有管理员发布文件，服务用户只读产物。不要把仓库或用户主目录直接作为站点根目录。

## 2. 账号与会话密钥

交互输入密码，避免进入 shell 历史和进程参数。`-c` 仅限首次创建，不可用于已有用户文件：

```bash
sudo htpasswd -cB /etc/html-preview/users.htpasswd viewer
sudo chown root:preview-auth /etc/html-preview/users.htpasswd
sudo chmod 640 /etc/html-preview/users.htpasswd
```

生成会话密钥，不显示其值；文件已存在则停止：

```bash
sudo python3 - <<'PY'
import grp, os, secrets
fd = os.open('/etc/html-preview/session.env', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
with os.fdopen(fd, 'w') as f:
    f.write('OAUTH2_PROXY_COOKIE_SECRET=' + secrets.token_urlsafe(32) + '\n')
os.chown('/etc/html-preview/session.env', 0, grp.getgrnam('preview-auth').gr_gid)
PY
```

密码哈希、session.env、TLS私钥均属于敏感数据，不提交 Git。使用独立长随机密码并保存在密码管理器中。

## 3. OAuth2 Proxy 配置

保存为 `/etc/html-preview/oauth2-proxy.cfg`，`root:preview-auth`、640：

```toml
http_address = "127.0.0.1:4180"
reverse_proxy = true
trusted_proxy_ips = ["127.0.0.1/32"]
proxy_prefix = "/oauth2"
redirect_url = "https://preview.example.com/oauth2/callback"
# 本地密码表单模式；程序要求provider字段，公网OAuth入口由Caddy阻断。
provider = "google"
client_id = "local-htpasswd-only"
client_secret = "unused-oauth-disabled"
htpasswd_file = "/etc/html-preview/users.htpasswd"
display_htpasswd_form = true
upstreams = ["http://127.0.0.1:4181/"]
pass_basic_auth = false
pass_user_headers = false
pass_access_token = false
pass_authorization_header = false
skip_provider_button = false
cookie_name = "__Host-preview_session"
cookie_secure = true
cookie_httponly = true
cookie_samesite = "lax"
cookie_path = "/"
cookie_expire = "168h"
cookie_refresh = "0"
request_logging = false
auth_logging = true
standard_logging = true
```

这里没有 Google 账号接入，client 字段为无效占位。默认登录模板会显示第三方按钮，正式交付时应使用 [OAuth2 Proxy 自定义模板](https://oauth2-proxy.github.io/oauth2-proxy/configuration/overview/) 隐藏它，只保留本地表单：

```html
{{define "sign_in.html"}}
<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>登录预览</title></head>
<body><h1>登录预览</h1>
{{if eq .StatusCode 400 401}}<p role="alert">账号或密码不正确。</p>{{end}}
<form method="POST" action="{{.ProxyPrefix}}/sign_in">
<input type="hidden" name="rd" value="{{.Redirect}}">
<label>账号 <input name="username" autocomplete="username" autocapitalize="none" required></label>
<label>密码 <input name="password" type="password" autocomplete="current-password" required></label>
<button type="submit">登录</button></form><p>仅在自己的设备上登录，保持7天。</p></body></html>
{{end}}
```

保存到 `/etc/html-preview/templates/sign_in.html`，目录750、文件640，属组preview-auth。在上述TOML中增加：

```toml
custom_templates_dir = "/etc/html-preview/templates"
```

## 4. Caddy 配置

保存为 `/etc/html-preview/Caddyfile`，`root:preview-auth`、640：

```caddyfile
{
    admin off
    auto_https disable_redirects
}
https://preview.example.com {
    tls {
        issuer acme {
            dir https://acme-v02.api.letsencrypt.org/directory
            disable_http_challenge
        }
    }
    @foreignOrigin {
        header Origin *
        not header Origin https://preview.example.com
    }
    @unsafeLogin {
        path /oauth2/sign_in
        method POST
        not header Origin https://preview.example.com
    }
    @oauthDisabled path /oauth2/start /oauth2/callback
    @loginPost {
        path /oauth2/sign_in
        method POST
    }
    route {
        respond @foreignOrigin "Forbidden" 403
        respond @unsafeLogin "Forbidden" 403
        respond @oauthDisabled "Not found" 404
        request_body @loginPost {
            max_size 16KB
        }
        reverse_proxy 127.0.0.1:4180 {
            header_up -Authorization
            header_up -Proxy-Authorization
        }
    }
}
http://:4181 {
    bind 127.0.0.1
    handle_path /previews/* {
        root * /srv/html-preview
        header Cache-Control "no-store"
        header X-Content-Type-Options "nosniff"
        file_server {
            hide .*
        }
    }
    respond "Not found" 404
}
```

本例关闭Caddy管理API，避免本机其他用户通过无认证的管理口改写路由。修改配置后先validate，再执行 `sudo systemctl restart html-preview-gateway`；会有短暂中断，不使用reload。

预览分流在认证之后，不能把 file_server 放到绕过认证的公网路径。不要启用 `browse`。文件服务不应承载符号链接或凭据；`hide .*` 不能替代发布时的文件选择。4181只绑定本机，但不按127.0.0.1匹配Host，否则转发的公网Host可能导致空响应。

### 没有域名，直接用公网IP

可使用支持公网IP短期证书的ACME服务；本例使用Let's Encrypt：

1. 将所有 `preview.example.com` 替换为服务器实际固定公网IP。
2. Caddy全局块增加 `default_sni <实际公网IP>`，兼容不发送SNI的IP客户端。
3. 在issuer acme块增加 `profile shortlived`。
4. 保持TCP443公网可达，Caddy自动申请、提前续期并加载证书。

IP证书有效期短，约6天，必须监测自动续期。首次签发成功不等于已经验证未来续期。不得用自签名证书让手机长期忽略警告。换IP后需更新Origin、redirect_url、证书及手机入口。

## 5. 服务托管

`/etc/systemd/system/html-preview-auth.service`：

```ini
[Unit]
Description=HTML preview cookie authentication
After=network-online.target
Wants=network-online.target
[Service]
User=preview-auth
Group=preview-auth
EnvironmentFile=/etc/html-preview/session.env
ExecStart=/opt/html-preview/oauth2-proxy --config=/etc/html-preview/oauth2-proxy.cfg
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/html-preview-gateway.service`：

```ini
[Unit]
Description=HTML preview HTTPS gateway
After=network-online.target html-preview-auth.service
Wants=network-online.target html-preview-auth.service
[Service]
User=preview-auth
Group=preview-auth
Environment=XDG_DATA_HOME=/var/lib/html-preview
Environment=XDG_CONFIG_HOME=/var/lib/html-preview/config
ExecStart=/opt/html-preview/caddy run --config /etc/html-preview/Caddyfile --adapter caddyfile
Restart=on-failure
RestartSec=5
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/var/lib/html-preview
UMask=0027
[Install]
WantedBy=multi-user.target
```

校验成功后启动，检查证书签发日志：

```bash
sudo -u preview-auth /opt/html-preview/caddy validate --config /etc/html-preview/Caddyfile --adapter caddyfile
sudo systemctl daemon-reload
sudo systemctl enable --now html-preview-auth html-preview-gateway
sudo journalctl -u html-preview-gateway -u html-preview-auth -n 50 --no-pager
```

## 6. 发布与到期删除

最简单的发布产物是**单个可信HTML，样式与脚本内联**。需要外部文件时逐个复制允许的CSS/JS/图片，使用相对路径；不递归复制源码仓库、依赖目录或符号链接。

以下在服务器上发布指定HTML。独立到期记录不放在可访问的静态目录。参数只有源文件路径和TTL，不包含密码：

```bash
sudo python3 - /absolute/path/to/page.html 24 <<'PY'
import grp, json, os, pathlib, secrets, sys, time
source = pathlib.Path(sys.argv[1])
hours = int(sys.argv[2])
if source.is_symlink() or not source.is_file() or source.suffix.lower() != '.html':
    raise SystemExit('需要可信HTML文件，不能是符号链接')
if not 1 <= hours <= 168:
    raise SystemExit('TTL必须为1到168小时')
preview_id = 'p-' + secrets.token_hex(8)
root = pathlib.Path('/srv/html-preview') / preview_id
root.mkdir(mode=0o750)
gid = grp.getgrnam('preview-auth').gr_gid
os.chown(root, 0, gid)
# 先登记到期，复制中断时也有清理记录。
record = pathlib.Path('/var/lib/html-preview-expiry') / (preview_id + '.json')
record.write_text(json.dumps({'expires_at': time.time() + hours * 3600}))
os.chmod(record, 0o600)
target = root / 'index.html'
target.write_bytes(source.read_bytes())
os.chown(target, 0, gid)
os.chmod(target, 0o640)
print('/previews/' + preview_id + '/')
PY
```

将输出路径接到自己的HTTPS入口即可。链接不可猜测只是便利措施，真正的权限由登录控制。更新同一个预览可原子替换其index.html，并按需要更新到期记录。

清理器保存为root拥有、755的 `/opt/html-preview/gc.py`：

```python
#!/usr/bin/env python3
import json
import pathlib
import re
import shutil
import time

root = pathlib.Path('/srv/html-preview')
state = pathlib.Path('/var/lib/html-preview-expiry')
for record in state.glob('p-*.json'):
    preview_id = record.stem
    if record.is_symlink() or not re.fullmatch(r'p-[0-9a-f]{16}', preview_id):
        continue
    try:
        expires = float(json.loads(record.read_text())['expires_at'])
        if not expires <= time.time():
            continue
        target = root / preview_id
        if target.is_symlink():
            continue
        if target.exists():
            shutil.rmtree(target)
        record.unlink()
    except (OSError, ValueError, KeyError, TypeError):
        print('清理失败，保留记录：' + preview_id)
```

该脚本只处理受控根目录下、符合格式且有到期记录的产物，不处理源文件或整个目录树。根目录和到期记录必须仅管理员可写。

`/etc/systemd/system/html-preview-gc.service`：

```ini
[Unit]
Description=Remove expired HTML previews
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /opt/html-preview/gc.py
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/srv/html-preview /var/lib/html-preview-expiry
NoNewPrivileges=true
```

`/etc/systemd/system/html-preview-gc.timer`：

```ini
[Unit]
Description=Check expired previews every five minutes
[Timer]
OnCalendar=*:0/5
Persistent=true
[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now html-preview-gc.timer
sudo systemctl list-timers html-preview-gc.timer
```

这是**定时清理**，不是逐请求校验过期：正常情况下到期后最多约5分钟删除；停机或清理失败会延后。要严格到秒拒绝访问，需要额外的过期校验服务，不能仅依赖Caddy静态文件服务。

## 7. 验收、维护与边界

部署验收应验证可观察行为：

- 未登录的预览和CSS/图片不能返回真实内容；不要把200登录页当作预览成功。
- 登录正确后得到host-only、Secure、HttpOnly、SameSite=Lax、7天Cookie；错误密码拒绝，篡改Cookie也拒绝。
- 新页面及相对资源加载正常；无目录列表、无符号链接逃逸和凭据文件。
- 删除或到期清理后，已登录访问返回404，源文件仍在。
- 重启认证服务后有效Cookie仍可用；退出链接 `/oauth2/sign_out?rd=/` 清除当前浏览器Cookie。
- 443证书可信，4180/4181无公网监听、2019管理API未监听；服务重启恢复、定时器正常。

简化版未内置登录限速。长期公网运行建议加Fail2ban或代理限速，规则只统计**POST /oauth2/sign_in且401**的实际密码提交；不能把所有401都计为失败，否则手机正常资源请求可能被误封。使用日志匹配时核对真实日志格式，不记录密码、Cookie或请求正文。

维护要点：

- 改密码用 `sudo htpasswd -B /etc/html-preview/users.htpasswd viewer`，不加 `-c`；重启认证服务。已有Cookie不会因改密码自动全部撤销。
- session.env必须持久化；轮换其密钥并重启认证服务可使全部旧Cookie失效。退出只清除本浏览器Cookie，不会撤销已被复制的Cookie。
- 7天会话不保证iOS永不清理网站数据；Safari和主屏幕App可能各自需要首次登录。
- 预览之间同源，只适合可信页面，不应混放陌生脚本、生产后台或不同权限用户的内容。
- 备份配置、密码哈希、会话密钥和Caddy数据时加密保存；公开文档只放无敏感信息的配置模板。
- 调整登录页只改HTML模板，不自行实现密码验证或Cookie密码学。

本文的认证链路来自已验证部署；这里的单机静态目录与定时清理是简化方案，不依赖原环境的技能脚本。按以上验收检查目标服务器，不能把原部署的验收结果直接当成新服务器已经通过。
