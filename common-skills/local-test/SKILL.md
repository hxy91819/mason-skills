---
name: local-test
description: Use only when actually starting, reusing, checking, or stopping a local multi-service integration or project-preview environment, or modifying its unified startup script. Do not use for ordinary code edits, unit tests, static HTML publishing, code review, or remote-only deployment.
disable-model-invocation: true
---

# Local Test 环境规范与治理

流程类 skill；仅在用户明确调用 `$local-test` 时采用。只有任务实际涉及本地联调或项目预览环境的启停、复用、检查及统一脚本维护时才适用。

## 门禁适用范围

**仅在以下场景触发**：
* 需要在本地搭建或启动多服务联调环境（包含数据库、后端、前端等）进行本地集成测试与功能验收；
* 已决定转为本地联调，并实际需要启动或复用该环境（仅远端发布受阻本身不触发）；
* 编写或维护项目的本地统一启停与生命周期脚本（如 `bin/dev`）。

**非目标（严禁触发）**：
* 单纯运行单元测试（如 `go test ./...`、`npm test`、`pytest`）；
* 普通的代码逻辑修改、重构或 Bug 修复；
* 代码评审（Code Review）或文档编写；
* 发布生成的静态 HTML 给用户查看（使用 `html-preview`，不启动项目服务）；
* 纯远端服务器部署或云端 CI/CD 配置。

触发后，通过统一脚本管理本地服务并完成所需联调验收；不因代码变更或一般验证需求自动搭建多服务环境。

## 术语

* **本地环境**：当前工作机器，含其上的所有 git worktree、中间件容器与裸启动的业务进程。远端 Dev、Beta、staging 等都不是本地环境。
* **worktree 环境**：某个 git worktree 内由统一脚本登记、拥有独立 namespace、端口与数据库名的一组业务进程。同一本地环境可同时存在多个 worktree 环境。
* **本地开发库**：worktree 环境的业务服务所用数据库；**本地测试库**：自动化测试套件所用数据库。二者都按 namespace 隔离，但生命周期分开管理。

## 1. 启动策略与服务选型

* **优先本地测试**：在进入现网或长流程发布前，先在本地跑通全流程功能验证。
* **统一收敛脚本**：在项目中提供一个标准的统一管理脚本（推荐 `bin/dev` 或 `scripts/dev.sh`），统一管理所有本地进程与容器。
* **中间件优先容器化**：数据库（MySQL/PostgreSQL）、缓存（Redis）、消息队列等依赖服务，优先采用 Docker 容器启动并挂载本地卷。
* **业务服务因地制宜**：项目自身的前端与后端服务，由 Agent 自主判断采用 Docker 容器运行方便还是直接在宿主机裸进程启动方便（通常裸进程更有利于源码热重载与断点调试）。默认裸进程；唯一需要隔离的状态在数据库与文件系统里，由 namespace 解决，不需要逐 worktree 复制容器。
* **中间件全机一份，按 namespace 分库**：数据库容器全机只跑一个，每个 worktree 环境用自己的库名（原库名加 namespace 后缀）；不为每个 worktree 复制一套中间件，也不使用固定槽位式环境池。
* **不合并到主干再测**：功能在自己的 worktree 环境验证，不把未验证代码合入主干或共享分支来借用环境。

## 2. 进程生命周期与数据保留

### 何时复用、保留与停止

环境生命周期覆盖同一项目需求的开发、联调和用户预览验收，可跨多轮对话持续运行。每次继续任务先检查 `status` 和必要的健康状态，复用归属明确、适用于当前工作目录与配置的服务；仅补启缺失服务，代码热更新可生效时直接复用，确需重启时只重启受影响服务。

* **保持运行**：需求仍在开发或修复、后续仍需联调、用户仍需预览、正在等待用户反馈或验收时，保留所需服务及其依赖。单轮回复结束、一次测试通过、提交或推送完成、短暂无请求，都不代表环境已无用途。
* **停止资源**：用户明确要求停止，或上下文已明确该需求结束/取消且没有后续预览、验收、联调或其他使用者依赖时，停止本环境不再需要的服务。可独立释放已完成用途的一次性测试进程；仍支撑预览的数据库等依赖继续保留。
* **用途不明确**：暂时保留并在交付中简短说明运行状态与预览地址，不为每轮保留重复询问。后续上下文明确不再需要时再停止；不凭空设定空闲超时。
* **归属消失即回收**：worktree 被移除、进程组已死、登记记录失效，这三种情况由 `gc` 与 worktree teardown 挂钩自动回收，不算“空闲超时”。空闲时间回收只在项目或用户明确配置时启用。
* **交接**：交付时说明环境保留还是停止；保留时给出预览 URL、入口登录 URL 和停止命令，停止时说明原因。检查资源归属及共享依赖，只操作本环境拥有且不再被使用的资源。

### 确定停止后的执行约束

* **启停完整性**：管理脚本必须同时支持启动（`start`）、停止（`stop`）与状态检查（`status`）。需跨轮预览的服务采用能持续运行的托管方式；前台 `trap` 清理仅适用于结束后确实不再需要的一次性任务。
* **停止完整性**：
  - 每个服务以独立会话／进程组启动并记录进程组 id，停止时对整个进程组发 `SIGTERM`（超时转 `SIGKILL`），保证 foreman、dev server、watcher 等子进程一起退出，不只杀父进程；
  - 检查并清理对应端口，杜绝后台孤儿进程与端口僵死占用；
  - 停止后清除本 worktree 状态文件与全机登记记录。
* **默认保留数据**：
  - 停止环境时仅关闭服务与容器，默认保留数据库数据文件与 Docker Volume；
  - 仅在用户明确提出“彻底重置本地测试数据”时，才清理数据卷。

## 3. 多 worktree 并行隔离

同一本地环境常有多个 agent 各自在 worktree 内工作。统一脚本必须保证任意两个 worktree 环境可同时运行且互不干扰，同时所有环境可被列出、单独停止、自动回收。

1. **namespace 由 worktree 决定**：linked worktree 默认取目录名，主 checkout 默认为空；可用 `LOCAL_TEST_NAMESPACE` 显式覆盖。canonical 化为小写 `a-z0-9_`。主 checkout 未设 namespace 时库名、端口全部维持原值，向后兼容。
2. **库名带后缀**：应用的开发库配置读取 namespace 环境变量，设置时库名加 `_<namespace>` 后缀。有条件时从维护中的模板库（PostgreSQL `TEMPLATE`）复制建库再跑 migration，让每个功能从同一份基线数据开始；模板不存在时退回普通 prepare。
3. **端口决定性推导**：从 namespace 哈希得到端口偏移，加到各服务基准端口上；被占用时顺延并把实际偏移写入本 worktree 状态目录，同一环境重复启动 URL 稳定。主 checkout 端口被未知进程占用时仍保守失败，不抢端口。
4. **执行期文件落在 worktree 内**：附件、pid、log、状态文件都在各自 worktree 的 `.local-test/`，天然隔离。
5. **全机登记目录**：每个运行中的环境在 `~/.local-test/registry/`（可用 `LOCAL_TEST_REGISTRY_DIR` 覆盖）留一条记录：项目、namespace、worktree 实体路径、进程组 id、端口、启动时间。`status` 同时列出本环境与全机所有环境。
6. **软上限而非槽位**：`start` 前统计全机存活环境数，超过 `LOCAL_TEST_MAX_ENVS`（默认 5）则拒绝并列出占用者。上限只防资源耗尽，身份永远由 worktree 决定，不做领取／排队。
7. **回收路径**：`gc` 遍历登记目录，进程组已死则删记录；worktree 路径已不在 `git worktree list` 中则杀进程组、按项目配置 drop 本地开发库、删记录。`destroy` 供 worktree teardown 挂钩调用：stop 加 drop 库加删记录，无环境时安全 no-op。
8. **挂钩 worktree 生命周期**：项目若有 worktree setup／teardown 脚本，setup 负责写入 namespace 与端口到 ignored env 文件并准备本地开发库，teardown 末尾调用 `destroy`。没有这类脚本时由 agent 在任务结束时执行 `stop` 或 `destroy`。
9. **tmux 等会话名带 namespace**：任何固定名字的 session、容器名、锁文件，只要可能被两个 worktree 同时使用，都要带上 namespace。

agent 在 worktree 内的自测流程固定为：`start` 取得本环境 URL → 用浏览器工具或 HTTP 客户端验证 → 交付时按第 2 节决定保留或 `stop`；忘记停止由 teardown 与 `gc` 兜底。

## 4. 子域名根路径预览

默认架构：Mac 通配符 DNS + 受信任开发 CA + 服务器常驻共享 Caddy 与 Cookie 认证。每个环境使用独立的一级子域，如 `https://task-123.preview.test/`，共用 443。应用保持正式部署的根路径和 API 约定。

1. **检查前置条件**：确认域名后缀、证书位置、共享网关管理方式、认证方式和环境归属清单。首次配置 Mac 或解析/信任异常时读 [Mac 配置指引](references/macos-preview-setup.md)；首次配置服务器、注册/注销环境、代理或证书排障时读 [服务器配置方法](references/server-preview-setup.md)。缺少基础设施时报告具体缺口，继续可进行的本机测试，不擅自改成子路径预览。
2. **分配环境**：登记唯一一级子域、前后端及认证实例本机端口、工作目录和归属；检查冲突，保留其他环境。注册配置按服务器文档的共享锁、校验和配置加载流程执行。
3. **保持应用部署语义**：页面从 `/` 访问，Caddy 按 Host 分流，API/WS 保持原路径。不得仅为预览修改 Vite base、Router basename、业务 API 路径或生产默认配置。正式部署原本使用子路径或用户明确要求时才采用子路径；已有为旧预览添加的前缀须先确认用途，再移除仅用于预览的部分。
4. **限定开发配置**：按需通过开发环境配置注入 allowed host、外部 URL、可信代理、HMR/WSS 地址和登录回调。默认由一个外部网关会话覆盖 `*.preview.test`：Cookie 使用 `Domain=.preview.test` 与 `__Secure-` 前缀，不能使用只允许 host-only 的 `__Host-` 前缀。只有所有接入子域同属可信预览边界时才启用共享父域；无法完成真实认证回调时说明验收缺口，不将预览域名硬编码进业务代码。
5. **网络与认证**：仅共享 Caddy 对外暴露，所有项目复用一个 OAuth2 Proxy、账号库和 Cookie 会话，再代理页面、API、静态资源和 WS；平台自身登录不能替代入口认证。未登录的浏览器文档导航跳转到 `/oauth2/sign_in?rd=<同站相对路径>`，API、资源与 WS 仍返回 401。仅认证子请求清除 Authorization，业务 Bearer 头照常传递；认证失败或不可用时拒绝业务访问。宿主机服务监听 `127.0.0.1`，容器端口不发布或仅绑定宿主 loopback；旧 Nginx 可作为本机上游，旧对外端口不得绕过认证。各客户端单独配置 CA 信任，验收不跳过 TLS 校验。
6. **验证和交接**：验证认证、页面/静态资源、深层路由刷新、API、WS/HMR、登录和 TLS，报告实际覆盖与缺口。按第 2 节判断环境保留或停止，收尾不自动执行 stop。验证停止隔离性时使用可停止的测试环境，不中断仍需使用的预览。共享网关常驻，项目 stop 只停自己的服务并保留数据；销毁环境才注销自己的路由。

无桌面服务器上的浏览器预览采用以上入口；本机桌面调试可直接使用 localhost。用户明确选择独立端口等替代方式时遵从，同时说明 Cookie、解析和 TLS 的实际限制。

### 用户可访问地址的单一来源

将内部监听地址、用户预览地址和入口登录地址分开记录。服务器的 `127.0.0.1`、`localhost`、`0.0.0.0` 和容器地址只用于内部诊断；除非确认浏览器就在同机或用户已建立对应本机隧道，否则不得作为交付链接。

在启动脚本附近明确记录地址来源：推荐 `.local-test/preview-url` 保存一行完整的实际访问 URL，包含协议、主机、必要端口、页面路径及非敏感查询参数，脚本注释指出该文件用途，并由 `status` 输出。写入前确认 `.local-test/` 已被 `.gitignore` 或 `.git/info/exclude` 排除，使用 `git check-ignore` 验证；若文件已被跟踪，忽略规则不会生效，先报告并处理本次范围内的跟踪问题。也可在不提交 Git 的本机脚本中注释记录真实 URL；可提交模板只放通用示例和配置入口。入口登录地址另存 `.local-test/preview-login-url`，由 `status` 同时输出；未登录的页面导航会跳转登录，非页面请求仍返回 401，交付时同时提供 `[入口登录](实际登录URL)` 和目标页面链接。不要在 URL 中记录密码、token 或登录凭据。

给用户链接前，读取当前配置或 `status`，核对其对应当前环境和真实网关路由。按用户访问方式验证 DNS、TLS、认证入口及目标页面；只能在服务器验证时明确客户端尚未验证。缺少实际入口则说明缺口，不从开发服务器日志复制 localhost，也不编造未配置的子域名。交付使用 Markdown 完整链接 `[打开预览](实际URL)`；环境迁移、端口或目标页面改变时同步更新地址记录。停止后说明不可用，不将保存的 URL 当作运行证明。

## 5. 启停模板与可观测性

### 启停收敛脚本预设模式 (`bin/dev`)

复制 [assets/bin-dev-template.sh](assets/bin-dev-template.sh) 为项目 `bin/dev`，只填脚本头部“项目填空区”（compose 文件、预览 URL、服务清单等配置项），共享网关的路由登记按服务器文档单独管理，脚本不启停网关或认证基础设施。预设契约：

* **接口**：`start`（幂等，本环境已拉起的服务跳过）/ `stop`（逆序收敛，杀进程组）/ `status`（本环境与全机登记）/ `logs <svc>` / `gc`（回收全机孤儿环境）/ `destroy`（stop 加 drop 本地开发库，供 teardown 调用）/ `reset --yes`（清数据卷，仅用户明确要求时使用）。
* **运行状态收敛**：统一落在 `.local-test/`（`run/*.pid`、`run/port-offset`、`logs/*.log`），全机登记落在 `~/.local-test/registry/`；`status` 汇报各服务存活状态、进程组与端口。
* **namespace 注入**：脚本把 `LOCAL_TEST_NAMESPACE` 与每个服务的 `LOCAL_TEST_PORT_<SERVICE>` 导出给业务进程；应用配置据此推导库名与跨服务地址，项目填空区提供 `DB_PREPARE_CMD` 与 `DB_DROP_CMD`。
* **端口守卫**：有 namespace 时端口由哈希推导、冲突顺延；主 checkout 端口被未知进程占用时保守失败（退出码 2）不抢端口——可能是其他 Agent 或遗留进程的现场。
* **停止收敛**：对进程组 SIGTERM 超时转 SIGKILL，并校验端口释放；compose 用 `stop` 不用 `down`，默认保留数据卷。
* **软上限**：`start` 前检查全机存活环境数不超过 `LOCAL_TEST_MAX_ENVS`。
* 偏离模板时保持同等契约；脚本头部注释沿用 script-writing-standard 的契约结构（定义/参数/输出/示例）。

`status` 是只读汇总入口：展示当前服务、PID、端口、预览 URL 和代理配置位置，不显示凭据。当前模板没有运行历史、裁决回写或滚动聚合，仅提供即时状态和本地日志；不得将即时状态当作历史成功率或完整验收证据。将 `.local-test/` 加入被测项目的 Git ignore，本地环境文件和日志不提交。
