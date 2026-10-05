# 打通一个新的谷歌账号

## 先判断走哪条路

| 情况 | 做法 | 用时 |
|---|---|---|
| 已有一个正式发布（In production）的自建 client，要给**另一个谷歌账号**授权 | 复用该 client：`GDOC_RCLONE_REMOTE=<新远端名> GDRIVE_CLIENT_ID=... GDRIVE_CLIENT_SECRET=... scripts/reauth.sh start`，按 SKILL.md「重新授权」完成；读取时同样带 `GDOC_RCLONE_REMOTE` | 约 1 分钟 |
| 没有自建 client（新用户，或旧 client 已删除） | 走下面的完整流程 | 约 20 分钟 |

External + In production 的应用可被任意谷歌账号授权，未审核时上限 100 个用户。rclone 自带的共享 client 在 2026 年内停用，不作为长期方案。

## 完整流程

人负责登录和点「同意」；控制台点击可交给浏览器 Agent（见文末）；网站和授权脚本由本机 Agent 完成。全程使用**同一个谷歌账号**：GCP 项目所有者、Search Console 验证者、最终授权账号一致。浏览器同时登录多个账号时，核对 URL 里的 `/u/<n>/` 和右上角头像。

### 1. GCP 项目与 API

- https://console.cloud.google.com/projectcreate 新建项目，确认顶部项目选择器已切到它。
- 启用 Drive API（`apis/library/drive.googleapis.com`）。读取只需要 Drive；Sheets/Docs API 仅在改用 gog 等按 API 读取的工具时才需要。

### 2. OAuth 同意屏幕（Google Auth Platform）

- https://console.cloud.google.com/auth/overview → Get started：App name、User support email、Audience 选 **External**、Developer contact email。
- **Data access 保持为空**。rclone 授权时自行申请 `drive.readonly`；在这里添加敏感/受限 scope 会把发布引向审核流程。

### 3. 准备域名与三个页面

新版控制台中，Branding 未填主页、隐私政策、服务条款链接和授权域名时，Audience 页的 **Publish app 按钮禁用**，提示 “To publish your app, you must complete your configuration on the Branding page.”。

没有自有域名时，用 GitHub Pages 用户站点 `<github用户名>.github.io`（2026-10 实测被接受为授权域名）：

```bash
gh repo create <user>/<user>.github.io --public   # 放 index.html / privacy.html / terms.html / .nojekyll
gh api -X POST repos/<user>/<user>.github.io/pages -f 'source[branch]=main' -f 'source[path]=/'
```

页面内容要点（英文即可）：
- 主页：说明这是个人非商业工具，用 rclone 以只读方式读取本人 Drive，不对公众提供。
- 隐私政策：访问的数据与 scope、仅下载到本人服务器且用后删除、token 只存本地配置、不出售不共享不用于广告或训练模型、撤销地址 https://myaccount.google.com/permissions 、遵守 Google API Services User Data Policy（含 Limited Use）、联系方式（可用仓库 issues，避免在公开页面放邮箱）。
- 服务条款：个人自用、按现状提供、可随时撤销。

部署后用 `curl` 确认三个地址均返回 200。

### 4. Search Console 验证域名

- https://search.google.com/search-console/welcome → 选 **URL prefix**，填 `https://<user>.github.io/`。
- 验证方法选 **HTML file**，只需记下文件名（`google<随机串>.html`），**先别点 Verify**。
- 在网站根目录放入同名文件，内容为单行 `google-site-verification: google<随机串>.html`，推送后用 `curl` 确认线上内容一致，再点 Verify，看到 Ownership verified。
- 验证文件和三个页面以后都不能删，否则会影响已发布的应用配置。

### 5. 填写 Branding 并发布

- https://console.cloud.google.com/auth/branding ：Home page、Privacy policy、Terms of service 填上面三个地址；Authorized domains 添加 `<user>.github.io`；Save。不上传 logo（有 logo 会触发审核要求）。
- https://console.cloud.google.com/auth/audience ：Publish app → 弹窗 “Push to production?” 直接 **Confirm**。不点 Prepare/Submit for verification。状态显示 **In production** 即完成。
- 停在 Testing 也能临时使用（须把账号加入 Test users），但 refresh token 7 天过期。

### 6. 创建 Desktop client

https://console.cloud.google.com/auth/clients → Create client → 类型 **Desktop app**。记下 Client ID（`….apps.googleusercontent.com`）和 Client secret（`GOCSPX-…`）。Desktop client 的 secret 不构成访问凭据，真正的凭据是授权后生成的 token；仍只放在本机配置或环境变量，不写进公开仓库。

### 7. 授权与验证

- `GDRIVE_CLIENT_ID=... GDRIVE_CLIENT_SECRET=... scripts/reauth.sh start`，把输出的地址交给用户。
- 用户选对账号；出现「Google 尚未验证此应用」时点 高级 → 转至 <应用名> → 继续/允许；回传打不开的 `http://127.0.0.1:53682/?state=...&code=...` 地址。
- `scripts/reauth.sh finish '<地址>'`：打印已授权账号，核对是否为目标账号；再用 `scripts/gdoc_fetch.py` 读一个该账号能访问的表格链接。
- 迁移自旧授权（如 rclone 共享 client）时，验证通过后请用户在 https://myaccount.google.com/permissions 撤销旧条目，保留新应用。

## 易错点

- 授权码只能用一次。`finish` 失败要从 `start` 重来；脚本拿不到 token 时不会改配置。
- 不要用 `pkill -f 'rclone authorize'` 之类按命令行匹配的方式清理进程：当前 shell 的命令行也含这段文字，会把自己杀掉。用 `pgrep -f '^rclone authorize'` 精确匹配。
- 发布按钮禁用时，原因在 Branding 未填完整，补齐域名和页面，不填假域名，也不进入审核流程。
- 失效场景：约 6 个月未使用、用户撤销应用、改密码或账号安全事件、删除 Pages 仓库/GCP 项目/client、谷歌收紧未审核应用的受限 scope 政策。前几项均可通过「重新授权」恢复。

## 委托浏览器 Agent 的要点

- 用户先在该浏览器登录目标账号；提示词写明遇到登录、两步验证、结算页面立即停下。
- 每一步给出直达 URL 和按含义找按钮的说明（界面中英文、布局会变）。
- 明确禁止项：不填假域名、不添加 scope、不上传 logo、不点 Submit for verification。
- 要求按固定格式回报（项目 ID、各步骤结果、Publishing status、报错原文、Client ID/secret）。
- Search Console 分两段：第一段只拿验证文件名不点 Verify；本机部署文件并确认上线后，第二段再点 Verify、填 Branding、发布。
- 授权「同意」这一步建议由用户本人完成。
