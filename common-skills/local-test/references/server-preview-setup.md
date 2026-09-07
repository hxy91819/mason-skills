# 服务器：Caddy 统一认证的子域名预览

配合 [Mac 配置](macos-preview-setup.md)：`*.preview.test` 解析到内网服务器，用户从每个项目的 `/` 访问。默认由同一个 Caddy 提供 HTTPS，OAuth2 Proxy 提供统一账号密码的 Cookie 登录。项目自身有无账号体系都必须经过外层认证。

本文是参考配置，不表示目标服务器已部署。仅改文档/脚本的任务不自动安装服务、申请凭据或切换线上入口。

## 1. 架构与边界

```text
Mac → Caddy :443 → Cookie 会话校验 → 项目前端 / API / WebSocket
              ↘ /oauth2/sign_in → 本项目 OAuth2 Proxy（loopback）
```

所有项目共用 htpasswd 账号文件，每个项目使用独立 OAuth2 Proxy 实例、loopback 端口和会话密钥，Cookie 保持 host-only。账号密码统一，但每个子域首次登录一次；不设置共享父域 Cookie。每个实例只负责本项目，方便固定回跳地址和限制路由。

已有 Nginx 可作为 Caddy 认证后的本机上游；也可由 Caddy 直接代理前后端。只有一个服务拥有对外 443，不能让 Caddy 和 Nginx 抢占端口，也不能保留绕过认证的旧对外端口。业务服务监听 loopback，容器端口不发布或仅绑定宿主 loopback。

这是对[静态 HTML 预览配方](../../../docs/authenticated-html-preview.md)的动态应用适配：使用 forward_auth，只将会话校验交给认证服务，业务 Authorization 保留。静态 HTML 的过期清理器不管理项目服务。

## 2. 一次性基础设施

以下以 Linux、systemd 为例。参考固定版本 Caddy 2.11.4、OAuth2 Proxy 7.15.4；安装时核对官方发布与对应摘要，不使用不固定的 latest。部署前阅读现有 Caddy 配置、服务单元、监听端口及数据目录，整合到现有实例，不覆盖主配置。

沿用静态 HTML 配方的 root 所有二进制、专用服务用户和账号文件。若已有 `/etc/html-preview/users.htpasswd`，直接共用它，不新建第二套账号。认证进程需有读取权限，业务进程不应有读取权限。新增账号使用交互式 `htpasswd -B`；`-c` 仅限文件不存在时首次创建。密码、哈希、会话密钥、证书私钥均不提交 Git。

将 Mac 签发的 `*.preview.test` 叶证书及私钥安装到仓库外，例如 `/etc/local-preview/tls/`。使用 root 所有、Caddy 服务组可读的目录 750、文件 640；Caddy 只读取，不能修改。CA 私钥留在 Mac。内网 `.test` 不走公网 ACME，不要求用户忽略证书错误。

建议目录：

```text
/etc/local-preview/tls/                       叶证书和私钥
/etc/local-preview/sites/operations.caddy     本项目 Caddy 片段
/etc/local-preview/auth/operations.cfg        本项目认证配置
/etc/local-preview/auth/operations.env        本项目会话密钥
/var/lib/local-preview/environments.tsv       域名、端口、工作目录、归属、配置位置
```

记录元数据，不记录账号明文或密钥。所有内容留在服务器本机，项目仓库只保留可移植脚本与配置样例。

## 3. 项目认证实例

例：`operations.preview.test`，认证端口 `127.0.0.1:4190`。登记前检查域名、端口及文件归属；并发环境用 `operations-task123` 等唯一一级标签。

`/etc/local-preview/auth/operations.cfg`：

```toml
http_address = "127.0.0.1:4190"
reverse_proxy = true
trusted_proxy_ips = ["127.0.0.1/32"]
proxy_prefix = "/oauth2"
redirect_url = "https://operations.preview.test/oauth2/callback"
provider = "google"
client_id = "local-htpasswd-only"
client_secret = "unused-oauth-disabled"
htpasswd_file = "/etc/html-preview/users.htpasswd"
display_htpasswd_form = true
skip_provider_button = false
skip_jwt_bearer_tokens = false
upstreams = ["static://202"]
pass_basic_auth = false
pass_user_headers = false
pass_access_token = false
pass_authorization_header = false
cookie_name = "__Host-local_preview_session"
cookie_secure = true
cookie_httponly = true
cookie_samesite = "lax"
cookie_path = "/"
cookie_expire = "168h"
cookie_refresh = "0"
request_logging = false
auth_logging = true
standard_logging = true
custom_templates_dir = "/etc/html-preview/templates"
```

provider/client 字段是本地 htpasswd 模式的程序占位，外部 OAuth 路由由 Caddy 阻断；不是 Google 登录。使用静态 HTML 配方的本地账号表单模板，不显示第三方登录按钮。配置 htpasswd 后不需要 `email_domains`；保持 `skip_provider_button=false`，避免跳入已禁用的 OAuth 流程。会话文件中只保存 `OAUTH2_PROXY_COOKIE_SECRET`，按原配方生成随机密钥并持久化；每项目分别生成，不覆盖已有密钥。

为每个实例建立 systemd 单元，沿用原配方的 `User`、沙箱和 `Restart=on-failure`，将 `EnvironmentFile`、`--config` 指向本项目文件。认证服务先启动；停止认证服务时入口必须拒绝或报错，不能自动放行业务。账号更新后重启各认证实例；改密码不自动撤销已有 Cookie，需轮换各实例密钥才能使旧会话失效。

## 4. Caddy 项目路由

将项目片段 import 到现有 Caddyfile。项目片段包含完整站点块，如下；已有全局块不重复创建。这里前端 5173、API 8001 仅为示例，按项目实际路由契约调整。

```caddyfile
https://operations.preview.test {
    tls /etc/local-preview/tls/preview.test.pem /etc/local-preview/tls/preview.test-key.pem

    @login {
        path /oauth2/sign_in /oauth2/sign_out
        method GET POST
    }
    @authPath path /oauth2 /oauth2/*
    @badLoginOrigin {
        path /oauth2/sign_in
        method POST
        not header Origin https://operations.preview.test
    }
    @loginPost {
        path /oauth2/sign_in
        method POST
    }
    @api path /api /api/*

    route {
        respond @badLoginOrigin "Forbidden" 403
        request_body @loginPost {
            max_size 16KB
        }
        handle @login {
            reverse_proxy 127.0.0.1:4190 {
                header_up -Authorization
                header_up -Proxy-Authorization
                header_up X-Forwarded-Host operations.preview.test
                header_up X-Forwarded-Proto https
            }
        }
        handle @authPath {
            respond "Not found" 404
        }
        handle {
            forward_auth 127.0.0.1:4190 {
                uri /oauth2/auth
                header_up -Authorization
                header_up -Proxy-Authorization
                header_up X-Forwarded-Host operations.preview.test
                header_up X-Forwarded-Proto https
            }
            reverse_proxy @api 127.0.0.1:8001
            reverse_proxy 127.0.0.1:5173
        }
    }
}
```

`route` 保持先认证后代理的执行顺序，`handle` 隔离登录路径。仅认证子请求移除 Authorization（htpasswd 本身也支持 Basic session，清除此头才能强制使用 Cookie），业务请求保留原始 Authorization、URI 和方法；不从认证响应复制身份头到业务请求。不得把业务 file_server、API 或 WebSocket 放在认证之前。代理上游无 URI 改写，应用仍使用自己的根路径。

未登录的业务请求返回 401，认证异常返回失败；不将 API/WS 请求统一重定向成 HTML 登录页。用户首次访问登录入口 `https://operations.preview.test/oauth2/sign_in?rd=/`，登录后回到根路径，再访问目标页面。保留目标路径时由脚本对 rd 参数进行 URL 编码，不接受任意外域回跳。`/oauth2` 是网关保留命名空间，若应用已使用该路径，选择并同步修改本项目 proxy_prefix、Caddy 匹配器和登录 URL，不修改业务认证接口。

这里不套用静态配方的全局固定 Origin 拒绝规则：动态应用可能有自己的跨域契约。登录表单仍严格限制 Origin；业务保持原有 CSRF/CORS 防护，确需跨域时配置明确白名单。子域之间可能属于同一 site，host-only Cookie 不等于完整安全租户隔离；只接入可信开发应用，不给业务进程读取认证配置的权限。

Caddy 默认支持 WebSocket 升级；HMR 按需用开发配置注入外部域名、WSS 和 443。Cookie 认证检查发生在握手阶段，退出不保证立即断开已建立的 WS。长连接及流式 API 另做验收。应用的生产 base、basename、API 路径保持不变。

## 5. 配置更新与生命周期

修改前重新读取归属清单与目标配置，使用同一个管理员级锁覆盖登记、写入、校验和加载，保留旧配置用于本次失败恢复。未知子域不应命中业务兜底站点。

先执行实际安装二进制的校验，例如：

```bash
sudo -u preview-auth /opt/html-preview/caddy validate --config /etc/html-preview/Caddyfile --adapter caddyfile
```

原配方使用 `admin off`，必须校验后 `systemctl restart html-preview-gateway`，会短暂中断全部入口，不能承诺无损 reload。正常项目 start/stop 不触发网关重启。需频繁注册项目时，可由管理员另行配置受权限保护的 Unix socket 管理端点和 reload 流程；不能为了方便开放无认证 TCP 管理端口。部署时报告实际加载方式和影响。

已有 Nginx 接管迁移要先备好 Caddy 配置和回退方案，在入口切换前确认影响；不自动停止其他项目。迁移完成后检查旧端口不能绕过认证。基础设施准备不足时完成独立脚本改造并报告缺口，不伪造可用预览地址。

何时保留或停止按 [SKILL.md 第 2 节](../SKILL.md#2-进程生命周期与数据保留)：同需求开发、预览、等待验收期间持续复用业务服务；共享网关和认证基础设施常驻。销毁环境才按归属注销站点及其认证实例，默认保留业务数据，不影响其他环境。

## 6. 地址记录与验收

项目脚本在 Git-ignored 的本机配置记录两个完整地址：`PREVIEW_URL`（目标页面）与 `PREVIEW_LOGIN_URL`（入口登录页，必要时带编码后的 rd）。`status` 分开展示，交付时同时给出可点击链接；首次用户先登录入口，再按需要登录业务平台。不要把业务自身登录成功当作入口认证验收。

在 Mac 与自动化客户端分别配置 DNS 和 CA 信任。服务器上的 curl 可用 `--resolve 域名:443:127.0.0.1 --cacert /path/to/rootCA.pem`，不使用 `-k` 验收 TLS；只有服务器验证时注明客户端尚未实测。

验收必须覆盖：

- 未登录时页面、API、静态资源、WS 握手不返回业务内容；错误密码和伪造 Cookie 被拒绝，认证服务不可用时不能放行。
- 登录后 Cookie 为 host-only、Secure、HttpOnly；另一个子域仍需首次登录，统一账号可用。
- 业务 Bearer 头、请求方法、API 路径与请求体保留；业务自己的认证仍有效。
- 页面深层路由刷新、WS/HMR、流式接口按项目需要正常；退出和认证命名空间不冲突。
- 旧入口、后端和认证端口均无法从公司网络绕过网关；未知子域被拒绝。
- 可停止的测试环境停一个不影响其他环境，不为重复测试中断用户预览。

证书续签由 Mac 使用原 CA 重新签发，服务器替换叶证书与私钥，校验后按真实网关加载方式更新；客户端不需重新信任同一 CA。参考：[Caddy forward_auth](https://caddyserver.com/docs/caddyfile/directives/forward_auth)、[OAuth2 Proxy 集成](https://oauth2-proxy.github.io/oauth2-proxy/configuration/integration/)、[静态 HTML 配方](../../../docs/authenticated-html-preview.md)。

本文配置已用上述固定版本、临时 TLS 信任和 loopback 高端口验证：未认证拒绝、表单登录、Cookie 隔离、Bearer/方法/请求体保留、WSS 帧收发和认证停机拒绝均通过。测试使用临时回显上游，不代表实际项目、Mac 浏览器、systemd、真实网络隔离及证书续签已经验收；部署后仍按本节逐项检查。
