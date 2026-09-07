---
name: local-test
disable-model-invocation: true
description: Set up, run, and cleanly shut down a multi-service local test environment (DB/backend/frontend) for integration testing and verification. Use exclusively when the task requires spinning up or managing a local testing environment before deployment. Do not use for unit testing, ordinary code editing, code review, or remote-only deployment.
---

# Local Test 环境规范与治理

流程类 skill，默认仅由用户通过 `$local-test` 显式调用。

## 门禁适用范围

**仅在以下场景触发**：
* 需要在本地搭建或启动多服务联调环境（包含数据库、后端、前端等）进行本地集成测试与功能验收；
* 远端/云上发布或验证受阻，需要切换为在本地闭环验证功能；
* 编写或维护项目的本地统一启停与生命周期脚本（如 `bin/dev`）。

**非目标（严禁触发）**：
* 单纯运行单元测试（如 `go test ./...`、`npm test`、`pytest`）；
* 普通的代码逻辑修改、重构或 Bug 修复；
* 代码评审（Code Review）或文档编写；
* 纯远端服务器部署或云端 CI/CD 配置。

在面对复杂业务交付、云端流程阻塞或多服务联调时，**优先在本地构建测试环境完成功能闭环与验收**。通过统一脚本收敛本地服务的启动、停止与安全访问。

## 1. 启动策略与服务选型

* **优先本地测试**：在进入现网或长流程发布前，先在本地跑通全流程功能验证。
* **统一收敛脚本**：在项目中提供一个标准的统一管理脚本（推荐 `bin/dev` 或 `scripts/dev.sh`），统一管理所有本地进程与容器。
* **中间件优先容器化**：数据库（MySQL/PostgreSQL）、缓存（Redis）、消息队列等依赖服务，优先采用 Docker 容器启动并挂载本地卷。
* **业务服务因地制宜**：项目自身的前端与后端服务，由 Agent 自主判断采用 Docker 容器运行方便还是直接在宿主机裸进程启动方便（通常裸进程更有利于源码热重载与断点调试）。

## 2. 进程生命周期与数据保留

* **启停完整性**：管理脚本必须同时支持启动（`start`）、停止（`stop`）与状态检查（`status`），或者支持前台模式通过 `trap` 捕获 `INT/TERM` 优雅退出。
* **彻底干净收敛**：
  - 记录各服务 PID，停止时通过 `SIGTERM`（超时转 `SIGKILL`）确保所有进程退出；
  - 检查并清理对应端口，杜绝后台孤儿进程与端口僵死占用。
* **默认保留数据**：
  - 停止环境时仅关闭服务与容器，默认保留数据库数据文件与 Docker Volume；
  - 仅在用户明确提出“彻底重置本地测试数据”时，才清理数据卷。

## 3. 子域名根路径预览

默认架构：Mac 通配符 DNS + 受信任开发 CA + 服务器常驻共享 Nginx。每个环境使用独立的一级子域，如 `https://task-123.preview.test/`，共用 443。应用保持正式部署的根路径和 API 约定。

1. **检查前置条件**：确认域名后缀、证书位置、共享 Nginx 管理方式、认证方式和环境归属清单。首次配置 Mac 或解析/信任异常时读 [Mac 配置指引](references/macos-preview-setup.md)；首次配置服务器、注册/注销环境、代理或证书排障时读 [服务器配置方法](references/server-preview-setup.md)。缺少基础设施时报告具体缺口，继续可进行的本机测试，不擅自改成子路径预览。
2. **分配环境**：登记唯一一级子域、前后端本机端口、工作目录和归属；检查冲突，保留其他环境。注册配置按服务器文档的共享锁、校验和 reload 流程执行。
3. **保持应用部署语义**：页面从 `/` 访问，Nginx 按 Host 分流，API/WS 保持原路径。不得仅为预览修改 Vite base、Router basename、业务 API 路径或生产默认配置。正式部署原本使用子路径或用户明确要求时才采用子路径；已有为旧预览添加的前缀须先确认用途，再移除仅用于预览的部分。
4. **限定开发配置**：按需通过开发环境配置注入 allowed host、外部 URL、可信代理、HMR/WSS 地址和登录回调。Cookie 默认 host-only，不设置共享父域。无法完成真实认证回调时说明验收缺口，不将预览域名硬编码进业务代码。
5. **网络与认证**：仅共享 Nginx 对外暴露；宿主机业务服务监听 `127.0.0.1`，容器端口不发布或仅绑定宿主 loopback。所有页面、API 和 WS 受统一入口认证保护；Basic Auth 与业务 Authorization 冲突时按服务器文档使用适配的认证网关，不能关闭 API 保护。各测试客户端单独配置 CA 信任，验收不跳过 TLS 校验。
6. **验证和收尾**：验证认证、页面/静态资源、深层路由刷新、API、WS/HMR、登录和 TLS；停止一个环境后其他环境仍可用。报告实际覆盖与缺口。共享 Nginx 常驻，项目 stop 只停自己的服务并保留数据；销毁环境才注销自己的路由。

无桌面服务器上的浏览器预览采用以上入口；本机桌面调试可直接使用 localhost。用户明确选择独立端口等替代方式时遵从，同时说明 Cookie、解析和 TLS 的实际限制。

## 4. 启停模板与可观测性

### 启停收敛脚本预设模式 (`bin/dev`)

复制 [assets/bin-dev-template.sh](assets/bin-dev-template.sh) 为项目 `bin/dev`，只填脚本头部“项目填空区”（compose 文件、预览 URL、服务清单等配置项），共享 Nginx 的路由登记按服务器文档单独管理，脚本不启停 Nginx。预设契约：

* **接口**：`start`（幂等，本环境已拉起的服务跳过）/ `stop`（逆序收敛）/ `status`（含对外访问入口与账号提示）/ `logs <svc>` / `reset --yes`（清数据卷，仅用户明确要求时使用）。
* **运行状态收敛**：统一落在 `.local-test/`（`run/*.pid`、`logs/*.log`），`status` 能汇报各服务存活状态与 PID。
* **端口守卫**：启动前预检；端口被未知进程占用时保守失败（退出码 2）不抢端口——可能是其他 Agent 或遗留进程的现场。
* **停止收敛**：SIGTERM 超时转 SIGKILL，并校验端口释放；compose 用 `stop` 不用 `down`，默认保留数据卷。
* 偏离模板时保持同等契约；脚本头部注释沿用 script-writing-standard 的契约结构（定义/参数/输出/示例）。

`status` 是只读汇总入口：展示当前服务、PID、端口、预览 URL 和代理配置位置，不显示凭据。当前模板没有运行历史、裁决回写或滚动聚合，仅提供即时状态和本地日志；不得将即时状态当作历史成功率或完整验收证据。将 `.local-test/` 加入被测项目的 Git ignore，本地环境文件和日志不提交。
