# 单机部署骨架

这是 `single-host-deploy` 的可复制骨架。它把“本机经 SSH 管理一台 Linux 主机上的 Docker Compose 栈”收成一组 Ansible playbook 和一个入口脚本。复制到目标仓库的 `infra/deploy/` 后，按下方参数表改清单。

## 需要项目提供什么

骨架不包含应用本身。目标仓库还需要：

| 路径 | 内容 |
| --- | --- |
| `infra/docker/Dockerfile.api` | API 镜像；在控制器构建，目标主机只加载 |
| `infra/docker/Dockerfile.web` | Web 镜像；构建后由本栈或共用网关反向代理 |
| `infra/docker/compose.deploy.yml` | 基础 Compose：API、Worker、Web、Redis 等 |
| `infra/docker/compose.deploy.bundled-db.yml` | 同栈 PostgreSQL override |
| `infra/docker/compose.deploy.external-db.yml` | 外部 PostgreSQL 网络 override |
| `infra/docker/compose.deploy.bundled-gateway.yml` | 本栈 Caddy override |
| `infra/docker/compose.deploy.external-gateway.yml` | 共用网关 + loopback 上游 override |

约定：

- 服务名：`api`、`worker`、`web`、`postgres`、`edge`。改名时同步改 `app_release` 的任务和你的 Compose。
- 镜像变量：`DEPLOY_API_IMAGE`、`DEPLOY_WEB_IMAGE`；项目名：`COMPOSE_PROJECT_NAME`。
- 应用读 `DATABASE_URL`、`APP_SECRET_KEY`，以及清单 `app.env` / `app.secrets` 声明的变量。
- API 健康端点默认 `/api/ready`；Web 健康检查默认根路径。按项目改 `smoke.paths` 和 Compose healthcheck。
- bundled 数据库用命名卷，不发布宿主端口；初始化脚本挂到 `/docker-entrypoint-initdb.d/00-app-init.sh`。

## 控制器安装

版本固定为 ansible-core `2.19.15`、`community.docker 5.4.0`、`community.general 14.0.0`、`ansible.posix 2.2.2`。升级时同步改本文件、`requirements.yml` 和验证记录。

```bash
uv tool install ansible-core==2.19.15
uv tool install ansible-lint          # 可选
ansible-galaxy collection install -r infra/deploy/requirements.yml
docker buildx version                 # release 需要
```

`uv tool` 通常把命令装到 `~/.local/bin`，确认它在 `PATH` 中。目标主机只需要 SSH、sudo、Docker/Compose 和 `python3`。

## 使用

```bash
cp infra/deploy/environments/example.yml infra/deploy/environments/prod.local.yml
cp infra/deploy/environments/example.secrets.env infra/deploy/environments/prod.secrets.local.env
chmod 600 infra/deploy/environments/prod.secrets.local.env
$EDITOR infra/deploy/environments/prod.local.yml
$EDITOR infra/deploy/environments/prod.secrets.local.env

infra/deploy/deploy.sh prod bootstrap
infra/deploy/deploy.sh prod release
infra/deploy/deploy.sh prod status
infra/deploy/deploy.sh prod backup-now
```

静态检查：

```bash
infra/deploy/deploy.sh example syntax-check
infra/deploy/deploy.sh example lint
```

## 参数表

| 字段 | 说明 |
| --- | --- |
| `project_name` | Compose 项目名、目录默认值、systemd 单元名、镜像默认名；小写字母/数字/连字符 |
| `environment_name` | 写进 release 记录的环境名 |
| `deploy_root` | 主机部署目录；默认 `/srv/<project>`，权限 0700 |
| `origin` | 公网访问地址；决定网关 Host/Origin 与冒烟默认地址 |
| `gateway.mode` | `bundled` 或 `external` |
| `gateway.host` / `http_port` / `https_port` | 证书、Host/Origin 和入口端口 |
| `gateway.tls_mode` | `auto`、`ip-shortlived`、`internal`、`off` |
| `gateway.acme_email` | bundled 的 ACME 账户邮箱；可留空 |
| `gateway.allowed_origins` | 额外允许的 Origin；`origin` 总是允许 |
| `gateway.upstream_port` | external 模式：Web 的 loopback 端口 |
| `gateway.log_mode` / `log_path` | `auto`、`stdout`、`file`；file 时用 `log_path` |
| `database.mode` | `bundled` 或 `external` |
| `database.driver` | 连接串 scheme，默认 `postgresql+asyncpg` |
| `database.user/name/schema/connection_limit` | 应用角色、库、schema、连接上限 |
| `database.host/port/network/container/admin_user` | external 模式必填；`container` 用于备份 `docker exec` |
| `images.api_repository` / `web_repository` | 镜像仓库名 |
| `images.platform` | 目标平台，例如 `linux/amd64` |
| `images.api_dockerfile` / `web_dockerfile` | 仓库相对路径 |
| `compose.base` | 基础 Compose 路径 |
| `compose.database.bundled/external` | 数据库 override 路径 |
| `compose.gateway.bundled/external` | 网关 override 路径 |
| `app.env` | 额外环境变量：变量名 -> 字面值 |
| `app.secrets` | 环境变量 -> 密钥键映射 |
| `secrets.required` | 必须由人提供的密钥键 |
| `secrets.generated` | 可自动生成的额外密钥键 |
| `backup.file_prefix` | 备份文件名前缀；默认 `project_name` |
| `backup.daily_utc` / `retention_days` | 每日备份时间和保留天数 |
| `backup.offsite.*` | 可选异地副本；`enabled`、`remote`、`rclone_config` |
| `firewall.manage` / `allowed_tcp_ports` | 是否管理 UFW、放行哪些 TCP 端口 |
| `smoke.base_url` / `insecure` / `retries` / `delay` / `paths` | 冒烟地址、证书校验、重试和路径 |

内置密钥：`APP_SECRET_KEY`、`DATABASE_PASSWORD`、`DATABASE_ADMIN_PASSWORD`。`secrets.required` 和 `app.secrets` 引用的键必须在密钥文件里填写；`secrets.generated` 会在缺失时生成。

`secrets.required` / `secrets.generated` 只负责校验和生成；要把某个键注入容器，请在 `app.secrets` 里加一行“环境变量: 密钥键”。不写映射的键只保存在本地密钥文件，不会进入 `private.env`。

## 动作

| 动作 | 说明 |
| --- | --- |
| `bootstrap` | 主机初始化：Docker、部署账号/目录、备份 timer、UFW；可重复执行 |
| `release` | 从干净提交构建、传输、启动、等健康、冒烟、切 `current` |
| `rollback [记录]` | 回到上一份 `.ok`，或指定 `releases/<记录>.json`；不重建镜像 |
| `status` | 只读查看当前 release、容器、备份 timer 和最近备份 |
| `backup-now` | 立即执行一次备份 |
| `db-init` | 仅 external：幂等创建角色/库/schema |
| `check` | 对 bootstrap 执行 `--check --diff` |
| `syntax-check` | 所有 playbook 的语法检查 |
| `lint` | ansible-lint |

## 安全

- 真实密钥只放未跟踪的 `<env>.secrets.local.env`；仓库只跟踪 `example.yml` 和 `example.secrets.env`。
- 主机 `private.env`、`backup.env` 0600；部署目录 0700；备份 0600。
- 不要把 `docker compose config` 的输出贴进日志或工单，它可能展开密钥。
- external 网关模式不写共用配置；只渲染站点块，人工并入并重载。
- 部署账号不是 root；Docker 组本身等同 root 权限，这是当前主机模型的已知边界。

## 排错

先看 `deploy.sh <env> status`，再在目标机用同一组 `-f` / `--env-file` 执行 `docker compose ... ps` 和 `logs`。证书、备份、数据库的排错路径见 `references/troubleshooting.md`。
