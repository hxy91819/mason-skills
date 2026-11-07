---
name: single-host-deploy
description: 手动为一台 Linux 主机上的 Docker Compose 栈建立“部署即代码”：Ansible 从本机经 SSH 管理，一条命令完成 bootstrap、release、rollback、status、backup-now 与 db-init。
disable-model-invocation: true
triggers:
  - user
---

# 单机部署即代码

## 适用范围

一台 Linux 主机（Ubuntu 24.04 或 Debian 12+，x86_64/arm64），一个 Docker Compose 栈，控制器是开发机或运维机，经 SSH 管理目标主机。目标主机不装 Ansible 代理，不在主机上编译镜像。

不覆盖：Kubernetes、多主机编排、云主机创建、DNS/云安全组、镜像仓库、密钥托管服务、跨机房容灾。这些需要另一个工具或人工流程。

## 不变量

- **两样本机输入**：一份环境清单、一份密钥文件，都以 `.local.` 结尾并被 `.gitignore` 忽略。仓库只跟踪 `example.yml` 和 `example.secrets.env`。
- **密钥只在本地**：清单只写键名和模式，真实值只放在未跟踪的 `<env>.secrets.local.env`，权限 0600。发布日志、release 记录、文档和命令示例都不含值。
- **控制器构建**：用 `docker buildx` 构建目标平台镜像，`docker save | ssh docker load` 传输，不依赖镜像仓库。
- **不在目标机编译**：目标机只需要 SSH、sudo、Docker/Compose 和 `python3`。
- **发布只从干净提交**：`git status --short` 为空才允许 `release`；镜像标签用当前提交的 short sha。
- **current 最后切换**：所有服务健康、冒烟通过后，才把 `deploy_root/current` 指向本次 release 记录。任何一步失败都中止，保留旧 `current`。
- **`.ok` 标记成功**：只有冒烟通过的 release 记录才写 `.ok`；默认回滚按 `.ok` 历史找上一份。
- **清单与密钥分离**：清单描述“要什么”，密钥描述“凭什么”；不要把密码写进清单、release 记录或 Compose 文件。
- **共用网关只读**：`gateway.mode: external` 只把站点块渲染到部署目录并打印接入提示，不修改主机上的共用网关配置。

## 快速开始

```bash
cp infra/deploy/environments/example.yml infra/deploy/environments/prod.local.yml
cp infra/deploy/environments/example.secrets.env infra/deploy/environments/prod.secrets.local.env
chmod 600 infra/deploy/environments/prod.secrets.local.env
$EDITOR infra/deploy/environments/prod.local.yml
$EDITOR infra/deploy/environments/prod.secrets.local.env

infra/deploy/deploy.sh prod bootstrap
infra/deploy/deploy.sh prod release
infra/deploy/deploy.sh prod status
```

首次使用前，控制器安装固定版本的 ansible-core、collection、Docker Engine 与 Buildx。版本和安装命令见 `assets/infra/deploy/README.md`。

## 动作清单

| 动作 | 作用 | 关键边界 |
| --- | --- | --- |
| `bootstrap` | 写入 Docker 官方源、安装 Docker/Compose、创建部署账号与目录、安装备份 timer、按清单增补 UFW | 可重复执行；第二次应为 `changed=0`；`check` 只读 |
| `release` | 校验密钥、构建并传输镜像、渲染配置、启动、等健康、冒烟、切换 `current`、写 release 记录 | 只从干净提交；冒烟不过不切 `current` |
| `rollback [记录]` | 用历史 release 记录的镜像重新启动，冒烟后把 `current` 切回目标，并写 `rollback-*.json` | 不重建镜像、不改数据库、不改应用密钥；不适用不可逆迁移 |
| `status` | 只读展示当前 release、镜像、容器状态、备份 timer 和最近备份 | 不写任何文件 |
| `backup-now` | 立即执行一次数据库备份，走 systemd oneshot service | 失败给 `journalctl` 入口 |
| `db-init` | 仅 external 数据库：幂等创建角色、库、schema、连接上限和 `search_path` | 默认不执行，不会被 bootstrap/release 自动调用 |
| `check` | 对 bootstrap 执行 `--check --diff` | 只读；Docker/Compose 尚未安装时跳过版本校验 |
| `syntax-check` | 对所有 playbook 执行 `ansible-playbook --syntax-check` | 用 example 清单，不连主机 |
| `lint` | 执行 `ansible-lint` | 可选；提交前跑 |

## 运行历史与回看

发布事实源是主机上的 `deploy_root/releases/*.json` 和对应的 `.ok` 标记，不另建运行账本。回看命令：

```bash
infra/deploy/deploy.sh <env> status
ssh <host> "ls -1 <deploy_root>/releases/*.json.ok | sort"
```

缺口：没有跨环境聚合统计，也没有“谁在什么时候执行了 release”的人员字段；需要审计时在 CI 或工单系统记录，不要往 release 记录里塞请求头、环境变量值或密钥。

## 最小输入

| 输入 | 何时必须 | 说明 |
| --- | --- | --- |
| SSH 地址、端口、账号、私钥、可信主机指纹 | 必须 | 账号需能免密 sudo；工具不创建主机、不分发公钥 |
| 对外 origin（scheme + host + 端口） | 必须 | 决定网关 Host/Origin、OAuth 回调和冒烟地址 |
| 应用密钥 | 按应用 | 由清单的 `secrets.required` / `secrets.generated` 声明；生成值写回本地密钥文件 |
| external PostgreSQL 管理员密码与网络/容器 | `database.mode: external` 且执行 `db-init` 时必须 | 管理员密码只用于一次性初始化 |
| 外部网关的站点块接入 | `gateway.mode: external` 时必须 | 人工并入共用配置并重载；本工具不写共用配置 |
| 异地备份 rclone remote | 启用异地副本时必须 | 主机需安装 rclone 并提供配置 |
| 旧数据迁移窗口、最终备份、是否沿用应用密钥 | 迁移旧环境时必须 | 不迁移数据时不需要 |

云安全组/DNS 是独立输入：工具只管理主机内 UFW，不能替代云控制台。至少放行 SSH、80、443 和选定的 origin 端口。

## 清单与密钥

清单本身就是 Ansible YAML inventory：业务配置放在 `all.vars`，连接信息放在 `all.hosts.target`。关键字段：

| 字段 | 说明 |
| --- | --- |
| `project_name` | Compose 项目名、目录默认值、systemd 单元名、镜像默认名；只允许小写字母、数字、连字符 |
| `deploy_root` | 主机部署目录，默认 `/srv/<project>`，权限 0700 |
| `origin` | 公网访问地址，必须与 `gateway.host` / 端口一致 |
| `gateway.mode` | `bundled`（本栈内 Caddy）或 `external`（复用共用网关） |
| `gateway.tls_mode` | `auto`、`ip-shortlived`、`internal`、`off`（仅测试） |
| `database.mode` | `bundled`（本栈 PostgreSQL）或 `external`（已有实例） |
| `database.driver` | 应用连接串 scheme，例如 `postgresql+asyncpg`；按应用改 |
| `images.*` | API/Web 镜像仓库名、平台、Dockerfile 路径 |
| `compose.*` | 基础 Compose、bundled/external 数据库 override、bundled/external 网关 override |
| `app.env` / `app.secrets` | 额外环境变量；`app.secrets` 把环境变量名映射到密钥键 |
| `secrets.required` / `secrets.generated` | 必须由人提供、可自动生成的密钥键 |
| `backup.*` | 每日 UTC 时间、保留天数、文件前缀、异地副本钩子 |
| `firewall.allowed_tcp_ports` | 本项目需要放行的 TCP 端口；只增补，不删除已有规则 |
| `smoke.*` | 冒烟地址、路径列表、是否忽略证书、重试次数与间隔 |

密钥文件：

- 可自动生成：`APP_SECRET_KEY`、`DATABASE_PASSWORD`、`DATABASE_ADMIN_PASSWORD`，以及清单里 `secrets.generated` 声明的键。首次 `release` 缺失时生成并写回本地密钥文件（0600）。
- 必须由人提供：清单 `secrets.required` 里的键。缺失时 `release` 在构建前报错，不会改动主机。
- 发布前校验只打印键名，不打印值；主机上的 `private.env`、`backup.env` 权限均为 0600。
- 首次发布后不要删除密钥文件。重新生成应用密钥会让已有会话失效；重新生成数据库密码会让应用无法连接已有库。

## 两种模式

| | bundled | external |
| --- | --- | --- |
| 数据库 | 同栈 PostgreSQL，命名卷，不发布宿主端口 | 主机已有实例，通过 Docker 网络接入 |
| 数据库初始化 | 首次 initdb 钩子 + 每次 release 幂等重放 | `deploy.sh <env> db-init`，默认不执行 |
| 网关 | 本栈 Caddy，端口由清单指定 | 主机已有共用网关，本站只绑定 loopback 上游 |
| TLS | `auto` 域名证书、`ip-shortlived` IP 短期证书、`internal` 仅验证 | 由共用网关现有证书配置负责 |
| 日志 | stdout + Docker 轮转 | 站点块写文件，10MiB×3，字段脱敏 |
| 共用设施 | 不涉及 | 本工具不执行 `caddy reload`，不写共用配置 |

external 数据库的 `db-init` 通过一次性 `postgres:18.6-alpine` 容器连接，幂等创建应用角色（非超级用户、连接上限）、数据库、schema、`ALTER ROLE ... SET search_path`，最后用应用角色连接确认 `current_schema()`。管理员密码只通过环境变量传入，不写入主机运行配置。

## 发布与回滚

发布流程：

1. 校验密钥，生成缺失的可生成密钥，渲染本机临时 `private.env`（0600，结束即删）。
2. 用当前提交的 short sha 构建 API 与 Web 镜像（目标平台、`--load`）。
3. `docker save` 两个镜像，经 SSH 管道 `docker load` 到目标主机。
4. 渲染 Compose、网关站点块、`private.env` 与 release 记录到 `deploy_root`。
5. bundled 数据库先启动 PostgreSQL，幂等重放初始化 SQL；再 `compose up -d --wait`。
6. API/Worker 健康后，强制重建 Web 以清理旧上游连接；bundled 网关再重建一次加载新站点配置。
7. 从目标主机请求 `smoke.paths` 里的每个路径，全部 200 才把 `current` 指向本次记录。
8. 写 `releases/<UTC>-<sha>.json`，包含 commit、镜像名/ID、时间、数据库/网关模式、上一版本；冒烟通过后写 `.ok`。

回滚：

- 默认回滚到 `current` 之前最近一份 `.ok` 记录；也可显式指定 `releases/<记录>.json`。
- 读取目标记录，校验镜像名与当前参数一致；用记录里的镜像标签重新渲染 `private.env`（应用密钥/数据库配置保持当前值）。
- `compose up -d --wait`、重建 Web、冒烟通过后切回 `current`，写 `rollback-*.json`。
- 回滚不重建镜像、不改数据库、不改应用密钥。跨数据库迁移的回滚不适用：新版本已执行不可逆迁移时，应恢复数据库备份，而不是只回滚镜像。

## 首次切换线上环境

目标：在旧机制仍在运行时准备好新栈，把停机窗口压到“停旧 → 起新 → 冒烟”这一小段。

1. **盘点与预检**：确认新栈镜像已加载、密钥/清单就绪、外部数据库/网关可达；按 `references/migration-inventory.md` 记录旧栈的容器、网络、端口、环境变量键名和数据位置。
2. **最终备份**：停写后对旧库做最终 dump；用 `pg_restore --list` 验证 dump 可读，记录文件大小和路径。
3. **行数快照**：对全部业务表记录 `count(*)`，保存在本机或主机旧栈目录；切换后逐表比对。
4. **停旧**：停止旧 Web/API/Worker（以及不再需要的旧网关上游），保留旧容器、镜像、Compose 和配置，不要删除。
5. **起新**：执行正式 `release`；首次 external 数据库先做迁移/恢复，再启动新栈。等待健康，关注 Worker 在 CPU 限额下的健康检查超时，不要为了通过而放宽检查。
6. **冒烟**：首页、健康端点、静态 Manifest、Service Worker、登录/关键 API 都按实际契约验证；浏览器打开公网地址，确认无 page error。
7. **切入口**：确认新栈公网可达后，才把共用网关指向新上游或切换 DNS；记录切换时间和停机窗口。
8. **失败回旧**：任一步失败，用旧 Compose + 旧私有配置 + 旧镜像启动原栈，先恢复入口，再排查。旧数据写入后不能盲目把入口指回旧库；先评估迁移和新增写入。

切换后保留：旧配置、旧 Compose、旧镜像、最终 dump、旧 runtime 卷、切换时间、停机窗口、行数表和冒烟证据。首次切换没有旧机制的 release 记录，不能用默认 `rollback` 回到旧 Compose；紧急恢复走旧栈材料。

## 换机盘点

先分类证据，再决定哪些能自动化：

- **仓库声明式**：Compose、Dockerfile、迁移、systemd 模板、Ansible role。
- **仓库手工命令/文字**：文档描述了操作，但没有可执行脚本。
- **主机独有**：只在该主机查到的网关、证书、防火墙、历史 hotfix、私有配置。
- **私有文件**：本机或主机的未跟踪配置；只记录键名，不记录值。
- **未核实**：当前证据无法确认；不能据此断言“只在人脑里”。

盘点至少覆盖：OS/架构/资源、SSH 与 sudo、Docker/Compose、构建与传输、部署目录与权限、私有 env 键名、数据库实例/角色/库/schema/连接预算、迁移版本、JWT/会话连续性、模型与登录凭据、网关与证书、UFW 与云安全组、DNS、备份目录/脚本/timer/恢复演练、镜像标签与 digest、旧 runtime/卷、CI/CD 与镜像仓库、验收入口与账号。详细清单见 `references/migration-inventory.md`。

## 故障排查

| 现象 | 处理 |
| --- | --- |
| `Host key verification failed` | 把目标主机指纹加入 `known_hosts`；不要长期用 `StrictHostKeyChecking=no` |
| `sudo: a password is required` | 部署账号必须免密 sudo；不要把 sudo 密码写进清单 |
| `docker: permission denied` | 重新登录让 docker 组生效；bootstrap 已把账号加入组 |
| `docker buildx` 不存在 | 控制器安装 Buildx 插件；release 需要它 |
| Compose 启动失败 | 在目标机用同一组 `-f`/`--env-file` 执行 `docker compose ... ps`、`logs --tail 100`；不要输出 `config`（可能含密钥） |
| 冒烟 502/503 | 看 API/Worker 健康与数据库连接；健康端点 503 通常表示依赖未就绪 |
| 证书申请失败 | 确认 DNS/公网 80/443（或选定端口）可达；IP 证书用 `ip-shortlived` 且需要 ACME 出站 |
| 备份 service 失败 | `journalctl -u <project>-db-backup.service -n 100 --no-pager`；核对 `backup.env` 的容器名、库名、目录 |
| 密钥缺失报错 | 按报错补齐 `secrets.required`；不要手工改主机 `private.env` |

## 安全边界

- 真实密钥只放未跟踪的 `<env>.secrets.local.env`；仓库、文档、命令示例和 release 记录都不含值。
- 主机 `private.env`、`backup.env` 0600；部署目录 0700；备份 0600。
- 不引入 sops 或加密入库；换机时由人重新提供密钥。
- 部署账号不是 root；Docker 组本身等同 root 权限，这是当前主机模型的已知边界。
- UFW 只增补规则，不清除共用主机已有规则；不要 `ufw reset`。
- external 网关模式不写共用配置；发布日志不包含请求 header 与 URI query。

## 验证与完成条件

静态检查：

```bash
infra/deploy/deploy.sh example syntax-check
infra/deploy/deploy.sh example lint          # 可选
```

在一次性目标或本机容器上验证（不要拿生产当试验场）：

- `bootstrap` 跑两次，第二次 `changed=0`；`check` 只读。
- `release` 完成构建/传输/启动/冒烟/写记录/切 `current`。
- `status` 能读到当前记录、容器状态、备份 timer。
- `backup-now` 产出 dump，并用 `pg_restore --list` 验证可读。
- `rollback` 能回到上一份 `.ok`，并写审计记录。
- bundled 数据库初始化、external 数据库 `db-init` 幂等、external 网关站点块渲染。

未验证项要写明：公网 ACME 签发与续期、云安全组/DNS、rclone 异地副本、arm64 构建、真实数据恢复演练。`--check` 通过不等于这些通过。

完成条件：清单和密钥分离；真实值不在仓库；`syntax-check` 通过；在目标环境完成一次发布、状态、备份和回滚验证；首次切换有最终备份、行数快照、冒烟证据和回旧路径。

## 资产与引用

| 路径 | 内容 | 什么时候读 |
| --- | --- | --- |
| `assets/infra/deploy/` | 去项目化的 `infra/deploy` 骨架，含 deploy.sh、deploy_config.py、playbooks、roles、env 示例 | 新建部署机制 |
| `references/design.md` | 动作状态机、release/rollback 细节、记录 schema、失败处理 | 改 deploy 脚本或 role |
| `references/cutover.md` | 首次切换线上环境的检查表、行数 SQL、停机窗口、回旧边界 | 迁移旧环境 |
| `references/migration-inventory.md` | 换机盘点方法与最小输入 | 接手一台现有主机 |
| `references/troubleshooting.md` | 部署、证书、备份、数据库的排错路径 | 发布失败 |
