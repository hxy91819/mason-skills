# 服务器：共享 Nginx 按子域名提供 HTTPS 预览

配合 [Mac 配置](macos-preview-setup.md)：所有 `*.preview.test` 解析到本服务器，Nginx 常驻并共用 443，项目从 `/` 访问。以下以 Linux、systemd 和宿主机 Nginx 为例；已有 Nginx 时合并配置，不能覆盖主配置或抢占现有端口。

## 1. 一次性准备

确认 Mac 到服务器的内网路由及 443 可达；防火墙仅向需要访问的内网来源放行。检查 `ss -ltnp` 与现有 Nginx include，确认 443 的归属。按发行版安装 Nginx 和 `htpasswd`（Debian/Ubuntu 的 `apache2-utils`）。

将 Mac 签发的服务器证书和私钥装入 `/etc/nginx/local-preview/tls/`：目录 root 所有、权限 700；私钥 root 所有、权限 600，证书可为 644。适用于 root master 的标准 Nginx 服务；非 root 服务按实际用户授予最小读取权限。CA 私钥不应出现在服务器。所有证书、密码文件和本机状态放在仓库外。

创建入口密码文件（交互式输入，不把密码写在命令行）：

```bash
sudo mkdir -p /etc/nginx/local-preview/tls /etc/nginx/local-preview/sites
sudo chmod 700 /etc/nginx/local-preview/tls
sudo htpasswd -c /etc/nginx/local-preview/htpasswd preview
```

`-c` 仅用于首次创建；文件已存在时去掉 `-c`，避免覆盖其他账号。密码文件应仅允许 root 和 Nginx worker 组读取，例如权限 640，组按本机 `www-data` / `nginx` 实际选择。通过安全渠道告知使用者凭据；htpasswd 存的是哈希，不能从中找回明文密码。

## 2. 接入共享配置

在现有 `http {}` 内增加一次：

```nginx
map $http_upgrade $local_preview_connection {
    default upgrade;
    '' close;
}
include /etc/nginx/local-preview/sites/*.conf;
```

创建 `/etc/nginx/local-preview/proxy.conf`（在 location 内引用）：

```nginx
proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $local_preview_connection;
proxy_read_timeout 300s;
```

这里假定浏览器直连 Nginx；若前面已有代理，按可信代理边界配置真实客户端地址，不直接相信客户端提供的转发头。流式接口需要时在对应 location 增加 `proxy_buffering off`。

以下兜底 server 只在 443 尚无 default server 时添加；已有兜底时整合其未知主机拒绝行为。Nginx 1.19.4 及以上支持拒绝未知 SNI 握手：

```nginx
server {
    listen 443 ssl default_server;
    server_name _;
    ssl_reject_handshake on;
    return 444;
}
```

不要配置自动转发所有未知子域的通配符业务 server。只有登记过的环境可以访问。旧版本需使用证书加拒绝响应等兼容配置，或升级后再使用该指令。

## 3. 注册一个环境

为每个环境选唯一的一级标签，例如 `operations-alice`。登记域名、本机前后端端口、工作目录、归属、配置文件位置到仓库外的本机清单（如 `/var/lib/local-preview/environments.tsv`，只记录路由元数据）。检查域名、端口和配置文件均未被其他环境占用。

为便于阅读，下例使用 `operations.preview.test`，保存为 `/etc/nginx/local-preview/sites/operations.conf`：

```nginx
server {
    listen 443 ssl;
    server_name operations.preview.test;
    ssl_certificate /etc/nginx/local-preview/tls/preview.test.pem;
    ssl_certificate_key /etc/nginx/local-preview/tls/preview.test-key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    auth_basic "Local Preview";
    auth_basic_user_file /etc/nginx/local-preview/htpasswd;

    location /api/ {
        include /etc/nginx/local-preview/proxy.conf;
        proxy_pass http://127.0.0.1:8001;
    }
    location / {
        include /etc/nginx/local-preview/proxy.conf;
        proxy_pass http://127.0.0.1:5173;
    }
}
```

`proxy_pass` 不附加 URI，保留原始 `/api/...` 路径。`/api/` 仅为示例，按项目正式部署约定添加精确 `/api`、其他 API 或 WebSocket 路由；不要为了套示例改业务路径。未登录也不能绕过 API 的入口认证。

HTTP Basic Auth 占用 `Authorization` 头：若业务使用 Bearer/其他同头认证，不能把 Basic Auth 硬套到该业务流程。应由管理员配置覆盖页面、API 和 WebSocket 的统一会话认证网关（例如基于 Cookie 的 `auth_request`），再进行联调；不能通过关闭 API 认证来绕过冲突。该替代网关不在本文模板实现范围内。

应用仅通过开发配置设定具体 allowed host、外部 URL 和可信代理。HMR 如不能自动推导，设置开发用 `wss`、当前子域和客户端端口 443。保持生产 base、路由和 API 路径不变，避免 `allowedHosts: true` 这类全放开配置。Cookie 默认 host-only；不同子域仍可能属于同一 site，不能当作完全隔离的安全租户，保留应用原有 CSRF 防护。

## 4. 校验、启停与并发

每次配置变更前重新读取目标文件。用同一个管理员级锁（如 `flock /run/lock/local-preview-nginx.lock`）覆盖读取、登记、修改、验证和 reload 的整个过程；所有管理入口遵守同一锁。只管理归属本环境的文件，保留旧文件内容供本次失败恢复，不重写其他环境配置。

```bash
sudo nginx -t
sudo systemctl reload nginx
```

只有校验成功才 reload，并检查服务状态与错误日志。失败时恢复本次拥有的配置，再验证；不得停止共享 Nginx。首次启动由管理员在配置校验后使用 `systemctl enable --now nginx`，日常项目脚本不负责它的启停。

业务前后端监听 `127.0.0.1`。容器内部可以监听容器网卡，但数据库等不对外发布，确需宿主机访问的端口绑定 `127.0.0.1:宿主端口:容器端口`。

项目 `bin/dev stop` 仅停止本环境进程与容器，默认保留数据和代理登记；服务停止后已认证请求出现 502 属于预期，不能据此终止其他环境。销毁环境时，按归属注销其配置和清单记录，校验后 reload。通用脚本模板不自动注册或注销路由，由 Agent 或管理员按本节执行。

## 5. 验收与续签

在 Mac 上完成 DNS 和 CA 信任后，检查：

- 未认证访问页面和 API 均返回 401；认证后页面、静态资源、深层路由刷新及 API 正常。
- WebSocket/HMR 使用 WSS，登录回调使用该环境 HTTPS 地址，Cookie 范围正确。
- 同时启动两个环境，停止其中一个后另一个仍可访问。
- 未登记子域被拒绝，业务端口不对外暴露。

服务器自身不自动拥有 Mac 的 DNS 或 CA 信任。服务器工具验证可用公开的 CA 证书加显式解析：

```bash
curl --resolve operations.preview.test:443:127.0.0.1 \
  --cacert /path/to/rootCA.pem -I https://operations.preview.test/
```

不要使用 `-k` 作为 TLS 验收。浏览器自动化所在机器也需配置对应解析与 CA 信任；Mac 配置不会自动传播。

证书到期前由 Mac 用同一 CA 重新签发，管理员替换服务器证书与私钥，执行 `nginx -t` 后 reload，并从 Mac 验证有效期。证书更新不要求修改每个项目或重新信任同一个 CA。

参考：[Nginx HTTPS](https://nginx.org/en/docs/http/configuring_https_servers.html)、[WebSocket 代理](https://nginx.org/en/docs/http/websocket.html)。
