---
name: local-test
description: Guide for setting up and managing a safe, self-contained local test environment before deployment. Use when running local verification, functional testing, integration debugging, or preparing dev scripts.
---

# Local Test 环境规范与治理

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

## 3. 安全隔离与对外网络暴露

在服务器环境调测时，必须防范未授权访问：

* **内部服务严格隔离**：所有后端 API、数据库、缓存及监控端口，**强制仅监听 `127.0.0.1`**，严禁绑定 `0.0.0.0`，禁止直接对公网或内网其他机器暴露。
* **前端暴露与可视化判断**：
  - 检查当前环境是否具备本地可视化桌面环境；
  - 若为无桌面服务器环境（Server/Cloud VM），前端页面必须通过统一的本地 Nginx 对外暴露。
* **Nginx 统一反代与密码保护**：
  - 仅允许 Nginx 监听对外端口（如 `18800` 等非敏感放通端口）；
  - 对外入口必须强制启用统一密码保护（HTTP Basic Auth），拦截一切未经授权的探测；
  - 前端静态页面/开发服务器与后端 `/api/` 均统一挂载在该 Nginx 下进行反代分发。

## 4. 架构与实现参考

脚本设计应保持精简，重点在于收敛与容错，Agent 可根据具体技术栈自由发挥。

### Nginx 密码保护与统一反代骨架

```nginx
events { worker_connections 1024; }
http {
    server {
        listen 18800;
        server_name _;

        auth_basic "Local Dev Area";
        auth_basic_user_file /path/to/dev-htpasswd;

        # 后端 API 反代
        location /api/ {
            proxy_pass http://127.0.0.1:8001/api/;
            proxy_set_header Host $host;
        }

        # 前端反代 (支持 WebSocket 热重载)
        location / {
            proxy_pass http://127.0.0.1:5173;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
    }
}
```

### 启停收敛脚本参考模式 (`bin/dev`)

```bash
#!/usr/bin/env bash
set -euo pipefail

cmd="${1:-start}"
case "$cmd" in
  start)
    # 1. 检查并拉起中间件 (Docker)
    # 2. 生成本地 htpasswd 与 nginx.conf
    # 3. 启动后端 (127.0.0.1) 并记录 PID
    # 4. 启动前端 (127.0.0.1) 并记录 PID
    # 5. 启动 Nginx (对外端口)
    ;;
  stop)
    # 逐个 kill PID，检查端口释放，保留 MySQL/Docker 数据
    ;;
  status)
    # 打印各进程状态与对外访问入口及账号密码
    ;;
esac
```
