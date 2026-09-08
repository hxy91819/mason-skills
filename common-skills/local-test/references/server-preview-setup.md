# 服务器：Caddy 统一认证的子域名预览

配合 [Mac 配置](macos-preview-setup.md)：`*.preview.test` 解析到内网服务器，用户从每个项目的 `/` 访问。默认由同一个 Caddy 提供 HTTPS，OAuth2 Proxy 提供统一账号密码的 Cookie 登录。项目自身有无账号体系都必须经过外层认证。

本文是参考配置，不表示目标服务器已部署。仅改文档/脚本的任务不自动安装服务、申请凭据或切换线上入口。

## 1. 架构与边界

```text
Mac → Caddy :443 → 共享 Cookie 会话校验 → 项目前端 / API / WebSocket
              ↘ /oauth2/sign_in → 共享 OAuth2 Proxy（127.0.0.1:4190）
```

所有项目共用一个 OAuth2 Proxy、htpasswd 账号文件和会话密钥。Cookie 设置 `Domain=.preview.test`，所以用户在任一已登记子域登录后可访问其他已登记子域；名称使用 `__Secure-` 前缀，不能使用只允许 host-only 的 `__Host-` 前缀。共享会话把所有接入的子域纳入同一信任边界，只接入自有、可信的预览应用；未知子域始终由 Caddy 拒绝。

已有 Nginx 可作为 Caddy 认证后的本机上游；也可由 Caddy 直接代理前后端。只有一个服务拥有对外 443，不能让 Caddy 和 Nginx 抢占端口，也不能保留绕过认证的旧对外端口。业务服务监听 loopback，容器端口不发布或仅绑定宿主 loopback。

这是对[静态 HTML 预览配方](../../../docs/authenticated-html-preview.md)的动态应用适配：使用显式 OAuth2 认证子请求，只将会话校验交给认证服务，业务 Authorization 保留。静态 HTML 的过期清理器不管理项目服务。

## 2. 一次性基础设施

以下以 Linux、systemd 为例。参考固定版本 Caddy 2.11.4、OAuth2 Proxy 7.15.4；安装时核对官方发布与对应摘要，不使用不固定的 latest。部署前阅读现有 Caddy 配置、服务单元、监听端口及数据目录，整合到现有实例，不覆盖主配置。

沿用静态 HTML 配方的 root 所有二进制、专用服务用户和账号文件。若已有 `/etc/html-preview/users.htpasswd`，直接共用它，不新建第二套账号。认证进程需有读取权限，业务进程不应有读取权限。新增账号使用交互式 `htpasswd -B`；`-c` 仅限文件不存在时首次创建。密码、哈希、会话密钥、证书私钥均不提交 Git。

将 Mac 签发的 `*.preview.test` 叶证书及私钥安装到仓库外，例如 `/etc/local-preview/tls/`。使用 root 所有、Caddy 服务组可读的目录 750、文件 640；Caddy 只读取，不能修改。CA 私钥留在 Mac。内网 `.test` 不走公网 ACME，不要求用户忽略证书错误。

建议目录：

```text
/etc/local-preview/tls/                       叶证书和私钥
/etc/local-preview/sites/operations.caddy     本项目 Caddy 片段
/etc/local-preview/sites/00-shared-auth.caddy 共享认证与跳转片段
/etc/local-preview/auth/gateway.cfg           共享认证配置
/etc/local-preview/auth/gateway.env           共享会话密钥
/var/lib/local-preview/environments.tsv       域名、上游端口、工作目录、归属
```

记录元数据，不记录账号明文或密钥。所有内容留在服务器本机，项目仓库只保留可移植脚本与配置样例。

## 3. 共享认证实例

共享实例监听 `127.0.0.1:4190`。登记新站点时只检查域名和业务上游端口；不新建认证端口、Cookie 名或会话密钥。

`/etc/local-preview/auth/gateway.cfg`：

```toml
http_address = "127.0.0.1:4190"
reverse_proxy = true
trusted_proxy_ips = ["127.0.0.1/32"]
proxy_prefix = "/oauth2"
redirect_url = "https://html.preview.test/oauth2/callback"
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
cookie_name = "__Secure-preview_gateway_session"
cookie_domains = [".preview.test"]
whitelist_domains = [".preview.test"]
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

provider/client 字段是本地 htpasswd 模式的程序占位，外部 OAuth 路由由 Caddy 阻断；不是 Google 登录。使用静态 HTML 配方的本地账号表单模板，不显示第三方登录按钮。配置 htpasswd 后不需要 `email_domains`；保持 `skip_provider_button=false`，避免跳入已禁用的 OAuth 流程。会话文件只保存一份 `OAUTH2_PROXY_COOKIE_SECRET`，按原配方生成随机密钥并持久化。`cookie_domains` 与 `whitelist_domains` 只允许该受控父域，不接受任意外部回跳。

建立一个 `local-preview-auth@gateway.service`，沿用原配方的 `User`、沙箱和 `Restart=on-failure`，将 `EnvironmentFile`、`--config` 指向共享文件。认证服务先启动；停止认证服务时入口必须拒绝或报错，不能自动放行业务。账号更新后重启这一个实例；改密码不自动撤销已有 Cookie，需轮换共享密钥才能使旧会话失效。

从旧的站点级配置迁移时，可保留其中一个既有 systemd 实例名和环境文件以避免复制密钥；只要 Caddy 全部指向它且其余实例已停用，它就是唯一的共享认证服务。登记文件必须记录实际保留的单元名。

## 4. Caddy 项目路由

将 [共享认证片段](../assets/shared-preview-auth.caddy) 复制为 `/etc/local-preview/sites/00-shared-auth.caddy`，再将项目片段 import 到现有 Caddyfile。`00-` 前缀保证片段定义先于各站点使用。下面以前端 5173、API 8001 为例；按项目实际路由契约调整。

```caddyfile
https://operations.preview.test {
    tls /etc/local-preview/tls/preview.test.pem /etc/local-preview/tls/preview.test-key.pem

    @badLoginOrigin {
        path /oauth2/sign_in /oauth2/sign_out
        method POST
        not header Origin https://operations.preview.test
    }
    @api path /api /api/*

    route {
        respond @badLoginOrigin "Forbidden" 403
        import preview_shared_login
        handle {
            route {
                import preview_shared_check
                reverse_proxy @api 127.0.0.1:8001
                reverse_proxy 127.0.0.1:5173
            }
        }
    }
}
```

`preview_shared_login` 隔离登录路径；`preview_shared_check` 仅认证子请求移除 Authorization，再把认证成功的请求交给业务上游。业务请求保留原始 Authorization、URI 和方法；不从认证响应复制身份头到业务请求。不得把业务 file_server、API 或 WebSocket 放在认证之前。代理上游无 URI 改写，应用仍使用自己的根路径。

未登录的顶层 HTML 导航返回 302 到同站 `/oauth2/sign_in?rd=<编码后的相对路径>`，登录后自动回到原页面；API、资源和 WS 保持 401，认证异常返回失败。`rd` 只允许相对路径且排除 `/oauth2`，不接受任意外域回跳。`/oauth2` 是网关保留命名空间，若应用已使用该路径，选择并同步修改本项目 proxy_prefix、Caddy 匹配器和登录 URL，不修改业务认证接口。

这里不套用静态配方的全局固定 Origin 拒绝规则：动态应用可能有自己的跨域契约。登录表单仍严格限制 Origin；业务保持原有 CSRF/CORS 防护，确需跨域时配置明确白名单。共享 `.preview.test` Cookie 把所有接入子域放入同一安全边界；只接入可信开发应用，不给业务进程读取认证配置的权限。

Caddy 默认支持 WebSocket 升级；HMR 按需用开发配置注入外部域名、WSS 和 443。Cookie 认证检查发生在握手阶段，退出不保证立即断开已建立的 WS。长连接及流式 API 另做验收。应用的生产 base、basename、API 路径保持不变。

## 5. 配置更新与生命周期

修改前重新读取归属清单与目标配置，使用同一个管理员级锁覆盖登记、写入、校验和加载，保留旧配置用于本次失败恢复。未知子域不应命中业务兜底站点。

先执行实际安装二进制的校验，例如：

```bash
sudo -u preview-auth /opt/html-preview/caddy validate --config /etc/html-preview/Caddyfile --adapter caddyfile
```

网关有受权限保护的 Unix socket 管理端点时，校验后使用 `systemctl reload html-preview-gateway`；没有该端点时才 `restart` 并报告短暂中断。正常项目 start/stop 不触发网关重启，不能为了方便开放无认证 TCP 管理端口。部署时报告实际加载方式和影响。

已有 Nginx 接管迁移要先备好 Caddy 配置和回退方案，在入口切换前确认影响；不自动停止其他项目。迁移完成后检查旧端口不能绕过认证。基础设施准备不足时完成独立脚本改造并报告缺口，不伪造可用预览地址。

何时保留或停止按 [SKILL.md 第 2 节](../SKILL.md#2-进程生命周期与数据保留)：同需求开发、预览、等待验收期间持续复用业务服务；共享网关和认证基础设施常驻。销毁环境才按归属注销站点；不停止或删除共享认证实例，默认保留业务数据，不影响其他环境。

## 6. 地址记录与验收

项目脚本在 Git-ignored 的本机配置记录两个完整地址：`PREVIEW_URL`（目标页面）与 `PREVIEW_LOGIN_URL`（入口登录页，必要时带编码后的 rd）。`status` 分开展示，交付时同时给出可点击链接；首次用户先登录入口，再按需要登录业务平台。不要把业务自身登录成功当作入口认证验收。

在 Mac 与自动化客户端分别配置 DNS 和 CA 信任。服务器上的 curl 可用 `--resolve 域名:443:127.0.0.1 --cacert /path/to/rootCA.pem`，不使用 `-k` 验收 TLS；只有服务器验证时注明客户端尚未实测。

验收必须覆盖：

- 未登录时 HTML 页面导航跳转至带同站 `rd` 的登录页；API、静态资源和 WS 握手不返回业务内容且保持 401；错误密码和伪造 Cookie 被拒绝，认证服务不可用时不能放行。
- 登录后 Cookie 为 `.preview.test`、Secure、HttpOnly；在另一个已登记子域访问时不再次登录。
- 业务 Bearer 头、请求方法、API 路径与请求体保留；业务自己的认证仍有效。
- 页面深层路由刷新、WS/HMR、流式接口按项目需要正常；退出和认证命名空间不冲突。
- 旧入口、后端和认证端口均无法从公司网络绕过网关；未知子域被拒绝。
- 可停止的测试环境停一个不影响其他环境，不为重复测试中断用户预览。

证书续签由 Mac 使用原 CA 重新签发，服务器替换叶证书与私钥，校验后按真实网关加载方式更新；客户端不需重新信任同一 CA。参考：[Caddy reverse_proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)、[OAuth2 Proxy 集成](https://oauth2-proxy.github.io/oauth2-proxy/configuration/integration/)、[静态 HTML 配方](../../../docs/authenticated-html-preview.md)。

本文配置已用上述固定版本、临时 TLS 信任和 loopback 高端口验证：未认证拒绝与页面跳转、表单登录、跨子域 Cookie 复用、Bearer/方法/请求体保留、WSS 帧收发和认证停机拒绝均通过。测试使用临时回显上游，不代表实际项目、Mac 浏览器、systemd、真实网络隔离及证书续签已经验收；部署后仍按本节逐项检查。
