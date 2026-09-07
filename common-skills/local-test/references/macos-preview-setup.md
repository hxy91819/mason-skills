# Mac：一次配置通配符解析与开发证书

目标：在 Mac 上访问 `https://任意环境名.preview.test/`，全部指向同一台内网服务器。新增环境只改服务器 Nginx，Mac 无需逐条维护 hosts。本文使用保留测试后缀 `preview.test`；环境名只用一级，如 `task-123.preview.test`，不使用 `a.b.preview.test`。

前提：已安装 Homebrew，Mac 能访问服务器固定内网 IP 的 443 端口。以下 `192.0.2.10` 是文档示例地址，必须换成真实内网 IP。安装会请求本机管理员权限；本文是参考指引，不代表 Agent 已在 Mac 执行配置。

## 1. 安装本机 DNS

```bash
brew install dnsmasq mkcert
brew_prefix="$(brew --prefix)"
```

先检查本机 53 端口是否已有 DNS 服务：

```bash
sudo lsof -nP -iUDP:53 -iTCP:53
```

如果已有服务，先确认归属并整合配置，不要抢占或停止未知服务。检查 `$(brew --prefix)/etc/dnsmasq.conf` 及其 include，保留已有用途。在该配置中合并以下设置（IP 需替换）：

```ini
listen-address=127.0.0.1
bind-interfaces
address=/preview.test/192.0.2.10
local=/preview.test/
```

`local` 让这个后缀的其他记录类型也不向上游转发，避免新版 dnsmasq 将 AAAA 查询交给外部 DNS。此配置会解析根域及各级子域，但 HTTPS 通配符证书只覆盖一级子域。

验证后，以系统服务方式启动，保证重启后仍可用：

```bash
sudo "${brew_prefix}/sbin/dnsmasq" --test --conf-file="${brew_prefix}/etc/dnsmasq.conf"
sudo brew services start dnsmasq
```

若服务已经运行，配置修改后使用 `sudo brew services restart dnsmasq`。

## 2. 只接管 preview.test 的系统解析

创建 `/etc/resolver/preview.test`，已有文件先阅读并合并：

```text
nameserver 127.0.0.1
port 53
```

可用 `sudo mkdir -p /etc/resolver`、`sudo nano /etc/resolver/preview.test` 完成。这个配置不会更改正常域名的 DNS。

```bash
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder
scutil --dns
dig @127.0.0.1 operations.preview.test A +short
dscacheutil -q host -a name operations.preview.test
```

后两个查询都应返回服务器 IP。普通 `dig 域名` 不一定遵循 macOS 的分域 resolver，不能单独用它判断系统解析失败。若浏览器仍解析失败，检查浏览器安全 DNS、代理或 VPN 是否绕过系统解析；为 `*.preview.test` 使用系统 DNS 和直连规则，再重试。

## 3. 在 Mac 签发证书

```bash
mkcert -install
mkdir -p "$HOME/.local/share/local-preview-certs"
cd "$HOME/.local/share/local-preview-certs"
mkcert -cert-file preview.test.pem -key-file preview.test-key.pem '*.preview.test'
chmod 600 preview.test-key.pem
openssl x509 -in preview.test.pem -noout -subject -dates -ext subjectAltName
```

`mkcert -install` 创建开发 CA 并加入信任。Firefox 等使用独立证书库的客户端可能需额外配置；Firefox 可先 `brew install nss` 再运行 `mkcert -install`。重启浏览器后验证实际信任状态。

只将 `preview.test.pem` 和 `preview.test-key.pem` 通过 SSH/SCP 传给服务器管理员，按[服务器配置](server-preview-setup.md)安装。CA 私钥 `$(mkcert -CAROOT)/rootCA-key.pem` 始终留在 Mac，不传给服务器、Agent 或 Git。服务器上需要的仅是叶证书私钥。

自动化客户端若不使用系统证书库，可单独信任公开的 `rootCA.pem`。例如 curl 使用 `--cacert "$(mkcert -CAROOT)/rootCA.pem"`；Node 可在启动测试进程前设置 `NODE_EXTRA_CA_CERTS`。不用 `-k` 或全局关闭 TLS 校验作为验收方法。

## 4. 验收与长期维护

服务器配置完成后：

```bash
curl --cacert "$(mkcert -CAROOT)/rootCA.pem" -I https://operations.preview.test/
```

未提供入口凭据时应返回 `401`，而不是证书或解析错误。在浏览器打开该地址，输入服务器管理员设置的入口账号后应正常显示页面。再注册另一个一级子域并访问，确认 Mac 无需新增配置。

这是一次配置、长期使用，不是永久证书：

- 新增项目：只改服务器 Nginx。
- 服务器 IP 改变：改一次 dnsmasq 的 IP 并重启服务。
- 叶证书到期前：在同一 Mac、同一 CA 下重新执行签发命令，替换服务器证书并验证 reload；Mac 不需重新信任。可定期用 `openssl x509 -checkend 2592000 -noout -in preview.test.pem` 检查是否将在 30 天内到期。
- CA 到期或更换 Mac：需迁移可信 CA 或建立新 CA、重新信任和签发；不要通过不安全渠道搬运 CA 私钥。
- 撤销配置：仅删除自己添加的 resolver 与 dnsmasq 条目；共享 dnsmasq 不应被直接卸载。`mkcert -uninstall` 会影响所有依赖该 CA 的开发站点，确认范围后再使用。

参考：[mkcert](https://github.com/FiloSottile/mkcert)、[dnsmasq 手册](https://thekelleys.org.uk/dnsmasq/docs/dnsmasq-man.html)、Mac 本机 `man 5 resolver`。
