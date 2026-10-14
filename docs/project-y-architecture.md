# 项目 Y 架构参考：单体 + 两端前端 + 原型的仓库形状

[来源项目轮廓](domain-guardrails.md#来源项目项目-y)的具体结构，去掉业务名词后记录，供下一个同类项目起步时照抄或对照。不是标准，是一份已经跑通的形状。

## 一、仓库布局

```text
contracts/openapi.yaml        传输类型唯一来源；Go／TS 类型由 just gen 生成，不手改生成物
backend/
  cmd/{api,migrate,seed,bootstrap,import}   组装与启动；迁移；开发种子；首个管理者；一次性数据导入
  internal/
    kernel/                   Actor、错误类型、Clock、Date 等领域内核，无依赖
    identity/                 公司、帐号、工作阶段（聚合：公司、帐号）
    sites/                    项目、场地、设备（聚合：项目、设备）
    inventory/                可分配资源与分配历史（聚合：每种资源一个）
    workorders/               工单聚合：阶段指派、各阶段记录、操作记录、转换与可见范围
    attachments/              附件归属、直传签名、确认与清理
    platform/{api,auth,config,db,httpx,logging,objectstore,version}
  migrations/                 goose 版本化 SQL
packages/
  api-client/                 生成的类型、请求入口、CSRF／Request-ID、显示标签对照表
  ui/                         token、呈现组件、页面骨架；只接 props（/theme、/ops、/field 子入口）
apps/
  ops-web/                    桌面运营端（React 18 + antd + React Router + TanStack Query）
  field-web/                  移动现场端（React 18 + antd-mobile，PWA manifest）
prototype/                    点击原型（同栈），在 workspace 内共用 packages/ui，独立建置与发布
tests/e2e/                    Playwright：跨端冒烟、真实 API；visual/ 视觉门禁与棘轮清单
deploy/                       compose.dev／prod／drill、Dockerfile、Caddyfile、备份与复原脚本
docs/
  raw/                        来源素材快照（客户材料、既有工具），只读
  analysis/{requirements,architecture,adr,review,plan}
  agents/                     Agent 工作规则：issue、分流标签、决策、领域影响评估
  steward/                    管家工作簿：路线与用户待办，只放链接与当前位置
CONTEXT.md                    术语表：词条、定义、Avoid
AGENTS.md / CLAUDE.md         Agent 入口：文档分层、开发规范、设计优先级、导航表
justfile / mise.toml          唯一命令入口与工具锁版；CI 只调 just
```

每个后端模块内部：聚合与领域函数在模块根（`workorder.go`、`types.go`、`view.go`），`usecase/`（命令 `*_cmd.go`、查询 `get_*.go`／`list_*.go`），`sqlc/`＋`sqlcgen/`（查询与生成），`http/`（handler 只调用例与 DTO），`repotest/`（内存与 PostgreSQL 两个仓储跑同一套），`apitest/`（httptest + 真库的黑盒冒烟）。不是每个模块都要有每一层。

## 二、一个请求的路径

```text
浏览器 ──Cookie──► 中间层：工作阶段校验、CSRF（自定义标头 + Origin 允许清单）、Request-ID、限速
            └─► handler：解 DTO，不比业务字段
                  └─► 用例：事务开始 → 仓储加载聚合（命令路径锁根行）→ 聚合方法 → Save(version 检查) → ViewFor(actor) → 提交
                        └─► 仓储：聚合 ↔ 多张表拆装只在这里；跨聚合唯一性靠索引与计数表锁
返回：投影 DTO，含 allowedActions、可见区块、候选槽位；前端只渲染
```

- 认证在中间层，授权在聚合（依赖单据数据）。
- 命令用例可跨多个聚合但一笔事务；查询用例加载 → `ViewFor` → 再向别的模块取读模型组 DTO。
- 列表查询用领域定义的 `VisibleScope(actor)` 交给仓储翻成 SQL。

## 三、认证与会话

- 密码 argon2id；HttpOnly／Secure／SameSite=Lax Cookie；移动端长滑动期、桌面端短闲置期，到期与延长规则只在会话聚合一份。
- CSRF：自定义标头 + Origin 允许清单（环境变量）；受信代理清单决定取哪个客户端 IP。
- 登录限速按帐号与 IP 各一档，含成功登录；首个管理者由命令建立，之后帐号由管理者建与重设。
- 认证只读投影不锁帐号，延长才锁定重验。

## 四、附件

- 直传对象存储：后端签短效 PUT → 前端上传 → 后端确认绑定；未确认的暂存有到期清理。
- 键名由后端生成（稳定 ID 段 + 阶段 + 槽位 + 扩展名），危险字符映射表固定；前端禁止键名字面值，只有显示标签对照表。
- 每阶段必拍／选拍槽位与数量上限由工单聚合推导，前端按 `requiredPhotoKeys` 渲染。
- 签名 URL 的 Host 必须与浏览器看到的入口一致；种子按 API 允许来源设置 bucket CORS。

## 五、前端结构

- 两端互不 import；都只依赖 `packages/api-client` 与 `packages/ui`；`packages/ui` 不依赖 apps、原型或 API 客户端（dependency-cruiser）。
- 页面按功能组织；状态从 TanStack Query 取投影，可否操作完全来自 `allowedActions`；lint 禁按角色／阶段比较决定操作。
- 原型用同一套 `packages/ui`，但 store、授权判断、种子、预览控制台留在原型；正式两端不得 import 原型。

## 六、测试与 CI 分层

| 层 | 工具 | 守什么 |
| --- | --- | --- |
| 聚合单元 | Go test，内存仓储 | 不变量（测试名带文档编号，脚本追溯） |
| 用例双仓储 | `repotest`，Testcontainers 每案例独立库 | `VisibleScope` 翻译一致、409 真发生 |
| API 黑盒 | `httptest` + 真 PostgreSQL | 认证、CSRF、公司隔离、并发指派 |
| 前端单元 | Vitest + Testing Library | 组件按 props 渲染、动态槽位 |
| E2E | Playwright，真 API／PG／对象存储，`seed-dev` 每轮独立库与桶 | 跨端主流程、越权、上传 |
| 视觉门禁 | Playwright 固定容器 | 结构比原型骨架、像素比正式基准、棘轮清单 |
| 静态 | depguard、ruleguard、ESLint、dependency-cruiser、gen-check、docs-check、gitleaks、govulncheck | import 方向、禁止位置、契约一致、文档链接与用词 |

`just check`（快）与 `just check-all`（含 E2E、视觉、建置、漏洞）；CI 四个 job：文档检查、check-all、正式镜像建置不推送、干净环境复原演练。

## 七、部署与本机测试

- 正式：Compose（API、Caddy 网关、PostgreSQL、迁移 job），镜像由 CI 建置；对象存储用云端 S3 兼容服务；异机备份与复原演练脚本进 CI。
- 开发：`compose.dev.yaml` 起 PostgreSQL 与 S3 兼容服务；`just dev` 起 API 与两端 Vite。
- 本机测试环境：单一 Caddy 入口承载两端静态资源、`/api`、对象存储 bucket 路径；外层由 Tailscale 或公网网关终止 TLS 再反代到入口；每个 worktree 用 `COMPOSE_PROJECT_NAME` 与独立端口隔离。

## 八、文档链与决策

- 需求：`docs/raw` 原件 → issue 决策地图子条目（答案附证据）→ 功能清单（期别栏定范围）→ 领域文档（转换表、可见范围、不变量编号）→ 编号测试。
- 架构：ADR 记"选了／没选／为什么／翻盘条件／对实作的影响"；实现偏离时加实作注记。
- Agent 入口：`AGENTS.md` 四类内容——文档分层、开发规范与设计优先级、skills 与 issue 规则、导航表；`docs/agents/domain.md` 的领域影响评估让 Agent 收到需求先定级。
- 管家工作簿：路线只放链接与当前位置，用户待办表单独一节，只有管家会话写。

相关：[领域设计不跑偏](domain-guardrails.md)、[架构不腐化](architecture-anti-erosion.md)、[原型到正式实现复盘](prototype-to-production-lessons.md)。
