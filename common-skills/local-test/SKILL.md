---
name: local-test
description: Use only when actually starting, reusing, checking, or stopping a local multi-service integration or project-preview environment, or configuring its `lt` CLI. Do not use for ordinary code edits, unit tests, static HTML publishing, code review, or remote-only deployment.
disable-model-invocation: true
triggers:
  - user
---

# Local Test 环境规范与治理

流程类 skill；仅在用户明确调用 `$local-test` 时采用。机制全在 [bin/lt](bin/lt)（技术栈无关 CLI），项目只需一份 `.local-test.yml`；本文只留 CLI 替不了你的判断。

## 门禁适用范围

**触发**：需要启动或复用本地多服务联调环境做集成测试与功能验收；为项目配置 `lt` 与 `.local-test.yml`。仅远端发布受阻本身不触发。

**非目标（严禁触发）**：单纯跑单元测试；普通代码修改、重构、Bug 修复；代码评审或写文档；发布静态 HTML 给用户看（用 `html-preview`）；纯远端部署或 CI/CD 配置。

## 术语

* **本地环境**：当前工作机器，含其上所有 git worktree、中间件容器与裸进程。远端 Dev/Beta/staging 都不是。
* **worktree 环境**：某个 worktree 内由 `lt` 登记、拥有独立 namespace、端口与库名的一组业务进程。可多个并存。
* **本地开发库**（业务服务用）与**本地测试库**（自动化测试用）：都按 namespace 隔离，生命周期分开管理。

## 一、先跑 doctor

把 `bin/lt` 复制或软链到项目 `bin/lt`，任何操作前先 `lt doctor`：它检查 git、docker、cksum、进程组隔离方案（setsid / perl / bash job control，macOS 无 setsid 时自动回退并报告采用了哪种）与配置合法性，不启动任何东西。缺件先补，不要带着未知环境直接 `start`。

## 二、无配置时：扫描仓库生成

`lt init` 不做问卷。你扫描仓库产出 JSON 再交给 CLI：`cat scan.json | lt init`（或 `--from-json <file>`；已存在配置需 `--force` 才覆盖）。它同时用 `git check-ignore` 确认 `.local-test/` 被忽略，缺则追加到 `.git/info/exclude` 并提示。

扫描来源：`Procfile*`、`package.json` scripts、`docker-compose*.yml`、`Makefile`、`.env.example`、框架约定。**只有一种情况问用户**：某个外部系统调用是只读还是写入，代码里判断不出来时（见第五节）。其余自行决策。

`.local-test.yml` 用 CLI 自带解析器，不依赖 ruby/python/yq。**只支持**两空格缩进、最多三层、`key: value`、`#` 注释（整行或值后带空格）、可选成对单/双引号；**不支持**列表、锚点、多行标量、TAB、引号内转义。违反即报错并指出行号。

```yaml
project: saiens                      # 可选，默认仓库目录名
middleware: docker-compose.yml       # 可选
database:
  prepare: bin/rails db:prepare      # 可选，可读 $LOCAL_TEST_NAMESPACE 推导库名
  drop: bin/rails db:drop            # 可选，destroy/gc 用
external:
  mode_env: EXTERNAL_MODE            # 可选；有此项时 real 只允许主 checkout
services:
  web:
    port: 4777                       # 基准端口；实际端口 = 基准 + namespace 偏移
    cmd: bin/rails server -p $LOCAL_TEST_PORT_WEB
  css:
    cmd: bin/rails tailwindcss:watch # 无 port 的服务不做端口守卫
preview_url: http://127.0.0.1:$LOCAL_TEST_PORT_WEB
```

`cmd` 运行时由 `bash -c` 求值，可引用 `$LOCAL_TEST_NAMESPACE` 与 `$LOCAL_TEST_PORT_<服务名大写>`；`preview_url` 只做同名变量替换，不执行。服务顺序即配置顺序：`start` 按序、`stop` 逆序。配置原则：中间件容器化且全机一份、按 namespace 分库；业务服务默认裸进程（利于热重载与断点），不为每个 worktree 复制中间件，不用固定槽位环境池，不把未验证代码合入主干来借环境。

## 三、命令与退出码

`doctor` 体检 | `init` 生成配置 | `start` 幂等拉起 | `stop` 逆序收敛并校验端口释放（保留数据卷）| `status` 本环境加全机登记 | `logs <svc>` | `gc` 回收孤儿环境 | `destroy` stop 加 drop 库加删登记（供 worktree teardown 调用）| `reset --yes` 清数据卷，仅用户明确要求"彻底重置"时用。

退出码：`0` 成功；`1` 参数或配置错误；`2` 环境预检失败（端口被未知进程占用、超 `LOCAL_TEST_MAX_ENVS`、`real` 却不在主 checkout）；`3` 服务启动失败。

`lt status` 末尾有机器可读段，直接 grep 取值，别解析上面的人读排版：`LT_PROJECT` / `LT_NAMESPACE` / `LT_PORT_OFFSET` / `LT_EXTERNAL_MODE` / `LT_PORT_<SVC>` / `LT_URL` / `LT_LOGIN_URL`。

自测流程固定为：`lt start` → 从 `lt status` 取 `LT_URL` → 浏览器工具或 HTTP 客户端验证 → 按第四节决定保留或 `lt stop`；忘停由 teardown 与 `lt gc` 兜底。

## 四、生命周期决策

环境覆盖同一需求的开发、联调与预览验收，可跨多轮对话运行。每次继续任务先 `lt status` 并检查健康状态，复用归属明确、适用于当前目录与配置的服务；只补启缺失服务，热更新可生效就直接复用，确需重启只重启受影响服务。

* **保持运行**：需求仍在开发或修复、后续仍需联调、用户仍需预览、正等待反馈或验收时保留。单轮回复结束、一次测试通过、提交推送完成、短暂无请求，都不代表环境已无用途。
* **停止资源**：用户明确要求，或上下文已明确需求结束/取消且无后续预览、验收、联调或其他使用者依赖时，停掉不再需要的服务。一次性测试进程可单独释放；仍支撑预览的数据库等依赖继续保留。
* **用途不明确**：暂时保留并在交付里简述运行状态与预览地址，不为每轮保留重复询问；不凭空设定空闲超时。
* **归属消失即回收**：worktree 被移除、进程组已死、登记失效，由 `lt gc` 与 teardown 自动回收，不算"空闲超时"。空闲回收只在项目或用户明确配置时启用。
* **默认保留数据**：`stop` 只关服务与容器，保留数据文件与 Volume；只有用户明确要求"彻底重置本地测试数据"才 `lt reset --yes`。

项目有 worktree teardown 脚本时在末尾调 `lt destroy`；没有就由 agent 在任务结束时 `lt stop` 或 `lt destroy`。

## 五、外部系统依赖

1. **先分类调用点**：只读调用可直接共享；写入且有回调、或带通知／扣款等副作用的才需隔离，通常只有少数落在后者。代码里判断不出属于哪类时，问用户。
2. **worktree 一律 mock，`real` 只在主 checkout**：配置 `external.mode_env` 后由 CLI 强制，worktree 内以 `real` 启动直接退出码 2，不靠人记规则。真实联调把目标分支 checkout 到主 checkout 再启动，同一时间只联调一个分支。mock 服务作为全机一份的中间件启动（WireMock、Prism 等），需要特定场景时用带 namespace 的桩配置覆盖。
3. **回调与归属**：webhook 只配主 checkout 的端口，不做分发器；主 checkout 在外部系统建的资源名称或备注带分支名，便于清理排查。

规模变大、多人同时需要真实联调时再升级为带超时的全机租约和 webhook 分发器；在此之前不预先引入这些复杂度。

## 六、交付格式

必须给出：**预览 URL（Markdown 完整链接）**、**namespace**、**保留还是停止**（保留附停止命令，停止说明原因）。

给链接前读 `lt status` 核对它对应当前环境与真实网关路由；只在服务器验证过就说明客户端尚未验证，缺入口就报缺口，停止后说明不可用。不从日志复制 localhost，不编造未配置的子域名：服务器的 `127.0.0.1`、`0.0.0.0` 与容器地址只用于内部诊断，除非浏览器同机或用户已建隧道，否则不得当交付链接。`.local-test/preview-url` 与 `.local-test/preview-login-url` 各存一行完整 URL（不含凭据），优先级高于配置里的 `preview_url`。

## 七、子域名根路径预览（可选）

无桌面服务器上的浏览器预览走此入口，本机桌面调试直接用 localhost。架构：通配符 DNS + 受信任开发 CA + 常驻共享 Caddy 与 Cookie 认证，每个环境一个一级子域（如 `https://task-123.preview.test/`）共用 443。网关常驻，不随 `lt start/stop` 启停，`lt` 不管理网关与认证设施；配置细节见 [Mac 配置指引](references/macos-preview-setup.md)、[服务器配置方法](references/server-preview-setup.md) 与 [assets/shared-preview-auth.caddy](assets/shared-preview-auth.caddy)，本节只列不可让步的约束：

* 先确认域名后缀、证书、网关管理方式、认证方式与归属清单；缺基础设施就报缺口并继续可做的本机测试，不擅自改成子路径预览。
* 保持部署语义：页面从 `/` 访问，Caddy 按 Host 分流，API/WS 保持原路径。不得仅为预览改 Vite base、Router basename、业务 API 路径或生产默认配置，也不把预览域名硬编码进业务代码。
* 只有共享 Caddy 对外暴露，所有项目复用一个 OAuth2 Proxy 与 Cookie 会话；共享父域 Cookie 用 `Domain=.preview.test` 与 `__Secure-`（`__Host-` 只允许 host-only）。未登录的文档导航跳登录页，API 与 WS 仍 401。宿主机服务监听 `127.0.0.1`，容器端口不发布或仅绑 loopback；各客户端单独信任 CA，验收不跳过 TLS 校验。
* 交付前验证认证、页面、深层路由刷新、API、WS/HMR 与 TLS 并报告缺口；销毁环境时才注销自己的路由。

## 八、可观测性边界

`lt status` 是只读汇总：服务、PID、端口、预览 URL、代理配置位置，不显示凭据。CLI 没有运行历史、裁决回写或滚动聚合，只有即时状态与本地日志 `.local-test/logs/<svc>.log`；不得把即时状态当历史成功率或完整验收证据。`.local-test/` 必须被 Git 忽略。改动 `bin/lt` 后必须跑通 [tests/smoke.sh](tests/smoke.sh)（需 git、python3、curl，不需 docker）。
