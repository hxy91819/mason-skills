# 设计：单机部署状态机

## 分层

```text
本机（控制器）                        目标主机
─────────────────                    ─────────────────────────────
deploy.sh                             deploy_root/
  ├─ ansible-inventory --list           ├─ compose.deploy*.yml
  ├─ deploy_config.py prepare           ├─ Caddyfile.site
  ├─ docker buildx build                ├─ private.env (0600)
  ├─ docker save | ssh docker load      ├─ backup.env (0600)
  └─ ansible-playbook                   ├─ releases/<UTC>-<sha>.json[.ok]
                                        ├─ backups/<prefix>-<UTC>-<pid>.dump
                                        └─ current -> releases/...json
```

控制器负责构建、密钥校验、传输和编排；目标主机只负责运行容器、备份和提供状态。目标主机不保存构建上下文，也不需要 Git checkout。

## 为什么用 `current` + 记录文件

- `current` 是一个符号链接，指向 `releases/<UTC>-<sha>.json`。读当前版本只需读一个链接，不需要解析日志。
- 记录文件是发布事实源：commit、镜像名/ID、时间、模式、上一版本、回滚来源。
- `.ok` 是“冒烟通过”的标记，不是“文件存在”的标记。默认回滚只挑 `.ok`，避免回到一个发布到一半的版本。
- 回滚写 `rollback-*.json`，保留“从哪来、到哪去”，而不是覆盖原记录。

记录 schema：

```json
{
  "schema": 1,
  "action": "release",
  "project": "myapp",
  "environment": "prod",
  "sha": "<40 位提交>",
  "short_sha": "<12 位短提交>",
  "recorded_at": "<UTC 时间戳>",
  "api_image": "example/api:<short>",
  "api_image_id": "sha256:...",
  "web_image": "example/web:<short>",
  "web_image_id": "sha256:...",
  "database_mode": "bundled",
  "gateway_mode": "bundled",
  "previous": "releases/....json"
}
```

回滚记录额外有 `from` / `to`。记录里不放环境变量值、密码、token、请求头。

## 动作状态机

### bootstrap

1. 校验 Debian/Ubuntu、部署账号、sudo、变量。
2. 写 Docker 官方 apt 源，安装 Docker Engine、Buildx、Compose 插件，启用 Docker。
3. 部署账号加入 docker 组；创建 `deploy_root`（0700）、`backups`（0700）、`releases`（0755）。
4. 安装备份脚本、`backup.env`、systemd service/timer，启用 timer。
5. 安装 UFW，默认 deny incoming / allow outgoing / deny routed，只增补清单端口；不清除已有规则。
6. 读取 Compose 版本，校验 v2。

可重复执行；第二次应为 `changed=0`。`check` 用 `--check --diff`，不安装、不写入、不重载服务；Docker/Compose 尚未安装时跳过版本校验。

### release

1. `load_inventory`，取 `project_name`、`deploy_root`、`origin`、镜像/Dockerfile/Compose 路径、冒烟路径。
2. `clean_worktree_or_die`：工作区必须干净。
3. 取 HEAD 的 40 位 sha 和 12 位 short sha；时间戳 UTC。
4. `deploy_config.py prepare`：校验 `secrets.required`，生成缺失的 `secrets.generated`，渲染本机临时 `private.env`（0600）。
5. 构建 API/Web 镜像：`docker buildx build --platform <platform> --load --tag <repo>:<short> --file <dockerfile> <repo_root>`。
6. `docker save` 两个镜像，经 SSH 管道 `docker load` 到目标主机。
7. 运行 `release.yml`，传入 sha、镜像、镜像 ID、`private.env` 路径、清单变量。
8. role 内：复制 Compose、初始化脚本、渲染站点块、写 `private.env`、写 release 记录（先不切 `current`）。
9. bundled 数据库先 `up -d --wait postgres`，幂等重放初始化 SQL；再 `up -d --wait --remove-orphans`。
10. 重建 Web（清理旧上游连接）；bundled 网关重建一次加载站点块。
11. 请求 `smoke.paths`，全部 200；失败重试 `smoke.retries` 次，间隔 `smoke.delay` 秒。
12. 切 `current`，写 `.ok`，输出摘要。

失败处理：任何一步失败都中止；`current` 保持旧值。查看目标机 `docker compose ... ps/logs` 和 release 记录；不要手工改 `current` 来“跳过”失败。

### rollback

1. 读 `current` 链接，得到当前记录路径。
2. 无参数时，从 `releases/*.json.ok` 排序，找当前记录之前最近一份；有参数时，接受 `releases/<记录>.json` 或裸文件名，去掉 `.ok` 后缀。
3. 从目标机读取目标记录为 JSON，取 `api_image`、`web_image`、`sha`、`short_sha`。
4. `deploy_config.py prepare --action rollback`：要求当前应用密钥存在，不重新生成；渲染当前值的 `private.env`。
5. `release.yml` 传 `release_action=rollback`、目标镜像、`rollback_from_record`、`rollback_to_record`。
6. role 校验目标记录存在、镜像与记录一致；`compose up -d --wait`、重建 Web、冒烟。
7. 切 `current` 到目标记录，写 `rollback-*.json`。

回滚不重建镜像、不改数据库、不改应用密钥。跨数据库迁移的回滚不适用：新版本已执行不可逆迁移时，应恢复数据库备份，而不是只回滚镜像。

### status / backup-now / db-init

- `status`：只读。读 `current`、容器 `ps`、备份 timer 状态、最近 dump、external 站点块路径。不输出 `compose config`。
- `backup-now`：`systemctl start <project>-db-backup.service`，失败给 `journalctl` 入口；成功后找最近 dump。
- `db-init`：只允许 external 数据库；要求管理员密码；幂等创建角色/库/schema/连接上限/`search_path`；最后用应用角色连接验证。默认不执行，不会被 bootstrap/release 自动调用。

## 清单参数化

`deploy.sh` 不写死项目名或文件路径，全部从清单读：

- `project_name`、`deploy_root`、`origin`
- `images.api_repository` / `web_repository` / `platform` / `api_dockerfile` / `web_dockerfile`
- `compose.base`、`compose.database.bundled|external`、`compose.gateway.bundled|external`
- `app.env`、`app.secrets`、`secrets.required`、`secrets.generated`
- `database.mode/driver/user/name/schema/connection_limit/host/port/network/container/admin_user`
- `gateway.mode/host/http_port/https_port/tls_mode/acme_email/allowed_origins/upstream_port/log_mode/log_path`
- `backup.file_prefix/daily_utc/retention_days/offsite`
- `firewall.manage/allowed_tcp_ports`
- `smoke.base_url/insecure/retries/delay/paths`

`app.env` 是“环境变量 -> 字面值”，`app.secrets` 是“环境变量 -> 密钥键”。`deploy_config.py` 把二者合并进 `private.env`；`private.env` 里的值只存在主机 0600 文件，不进 release 记录。

`secrets.required` / `secrets.generated` 只负责校验和生成，不自动注入。需要注入容器的键必须出现在 `app.secrets` 的“值”一侧；这样密钥文件和 `private.env` 的暴露面是显式选择的。

## 扩展点

- 应用需要额外必填密钥：加 `secrets.required`，不要改脚本。
- 应用需要把密钥映射成特定环境变量：加 `app.secrets`。
- 应用需要额外环境变量：加 `app.env`。
- 应用有多个健康路径：加 `smoke.paths`。
- 应用需要不同的数据库连接串：改 `database.driver`。
- 应用需要多个 Web/Worker 服务：改 Compose 和 `app_release` 的健康顺序；不要把所有服务塞进一个 `up --wait` 后假设依赖顺序正确。
- 需要接入共用网关：`gateway.mode: external`，把 `deploy_root/Caddyfile.site` 的内容并入共用配置，按共用网关流程校验、重载；本工具不写共用配置。

## 失败与可观测性

- 所有命令输出在 stderr（`info`）或 Ansible 日志；release 记录和 `.ok` 是事后复盘的事实源。
- `private.env` 用完即删；`no_log: true` 覆盖密钥相关任务。
- 备份脚本失败只影响备份，不影响应用；但 `backup-now` 会把失败返回给调用方。
- 不建独立运行账本：发布历史已经在 `releases/*.json`，用 `deploy.sh <env> status` 和 `ls releases/` 回看。缺口是：没有跨环境的聚合统计，也没有“谁在什么时候执行了 release”的人员字段；需要时在 CI 或工单系统记录。
