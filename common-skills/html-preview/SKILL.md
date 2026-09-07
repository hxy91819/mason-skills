---
name: html-preview
description: Use only when an agent-generated static HTML report, chart, or demo must be published as a browser link for the user, or when renewing, inspecting, or deleting an existing HTML preview. Do not use for merely writing HTML files, editing application code, running project servers, or publishing production sites.
---

# HTML 预览发布

流程类 skill；按用户明确要求允许隐式触发，也可显式调用 `$html-preview`。只处理已生成且需要交付浏览器链接的静态 HTML，以及这些预览的生命周期。用户只要文件或已使用 IDE 内嵌展示并未要求服务器链接时，不额外发布。

## 发布前

1. 确认已有可信 HTML 和交付给用户查看的需要。默认接收自包含单文件 HTML，样式/脚本内联；图表数据随文件携带。需要相对资源时先在原产物之外生成自包含副本，不能递归复制仓库、依赖目录或带凭据的配置。脚本不会分析 HTML 的全部网络请求；逐项确认外部资源可用且适合交付。只发布当前任务可信产物，不托管陌生脚本或混入生产后台。
2. 读取本机 `/etc/html-preview/publish.json` 或管理员指定配置，核实真实 HTTPS 入口、发布目录、到期状态目录及清理 timer。首次安装或基础设施缺失时读 [部署与清理](references/setup.md)，完成可独立进行的文件准备并说明缺口；不擅自覆盖 Caddy、创建账号或编造地址。
3. 页面和全部资源必须经过现有 Caddy/OAuth2 Proxy 统一认证，账号库可与项目预览共用；平台是否自带登录不影响该要求。新静态站点不要占用现有项目根路径。地址与凭据分开记录，不读取或输出密码、Cookie、密钥。

## 发布、验证、交付

使用 [scripts/preview.py](scripts/preview.py)，参数契约见 `--help`。发布/续期默认 24 小时，允许 1 到 168 小时；用户说“临时看一下”无需再问 TTL，发布时必须告知到期时间。显式要求更长时先商定保留方式，不静默改成永久。

```bash
python3 /path/to/html-preview/scripts/preview.py --config /etc/html-preview/publish.json publish /absolute/path/report.html
python3 /path/to/html-preview/scripts/preview.py --config /etc/html-preview/publish.json show
```

脚本输出 ID、完整预览 URL、入口登录 URL、UTC 到期时间以及副本存在状态。将到期时间换算为用户时区，在回复中给出 `[入口登录](实际登录URL)`、`[打开预览](实际URL)` 和到期时间；用户已登录时可直接打开预览。只能从实际配置及命令输出取地址，不用服务器 localhost，也不把 `access_verified: false` 当作验收成功。

验证未登录不能取得 HTML，已登录后目标文件和必要资源可访问；只能在服务器验证时说明 Mac/用户浏览器未测。不要为查看一个 HTML 启动项目开发服务器，或绕过 TLS/认证。存在配置缺口或失效清理 timer 时明确报告，不能宣称“可点击且会自动清理”。

## 生命周期

- 查询 `show [ID]`：只读汇总登记、副本存在和到期状态；无历史内容、源文件路径或访问日志。
- 续期 `renew ID --hours 24`：用户仍需查看，或当前任务明确延长预览时使用；已删除的副本需从源重新发布。普通 Agent 回复、查看状态或静默访问不续期。
- 删除 `delete ID`：用户要求撤下或已明确不再需要时，仅删除该发布副本。
- 自动清理 `gc`：由 systemd timer 独立运行，只处理本脚本有效登记且到期的副本；Agent 会话结束不影响 timer。未知格式、符号链接、额外文件只报告并保留，不能为了清空目录而递归删除。

有效期是回收时间，不是严格的请求级过期控制。通常到期后一个 timer 周期内删除；停机/失败会延迟。HTML 副本的 TTL 不适用于 `local-test` 的项目进程；开发或等待验收的项目服务按其自身生命周期管理。

## 状态与失败边界

本机状态是发布/删除的事实源，由脚本在文件锁内原子更新，放在发布根之外、Git 外。只记 ID、目录绑定摘要、创建/到期时间与格式版本，不存 prompt、源路径、正文、凭据。发布先登记再复制，中断留下的空副本仍可到期回收；gc 单条失败继续检查其他记录，并以非零退出码及错误列表报告。

当前提供 `show` 即时汇总，没有长期运行历史、裁决回写或滚动统计；不把它描述为完整审计。自动清理只减少已登记副本，异常记录保留待处理，不强行折算或丢弃。源 HTML 始终由原任务自行保留。
