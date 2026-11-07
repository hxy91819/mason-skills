# 首次切换线上环境

## 目标与边界

旧机制（手工 Compose、脚本、另一套目录）仍在运行时，把流量切到新的单机部署机制。目标是：

- 旧栈可回退材料完整；
- 停机窗口可计量；
- 新栈在上线前已经完成镜像加载、配置渲染和数据库准备；
- 失败时能在几分钟内恢复旧入口，而不是现场排查。

首次切换没有旧机制的 release 记录，不能用默认 `rollback` 回到旧 Compose。紧急恢复走旧栈材料。

## 切换前

### 1. 盘点旧栈

按 `migration-inventory.md` 记录：

- 容器名、镜像标签/digest、Compose 文件、网络、端口绑定；
- 私有 env 键名（不记录值）、JWT/会话是否沿用、外部 OAuth/模型/推送配置；
- 数据库实例、角色、库、schema、连接上限、迁移版本；
- 网关/证书、UFW、云安全组、DNS；
- 备份目录、脚本、timer、最近一次可读 dump；
- runtime/日志/卷、旧镜像归档、hotfix 目录；
- 浏览器验收路径和账号角色。

### 2. 预加载新镜像

在控制器构建并 `docker save | ssh docker load`，或从可信归档加载。确认目标机：

```bash
docker image inspect <api-image> --format '{{.Id}}'
docker image inspect <web-image> --format '{{.Id}}'
```

镜像 ID 写进 release 记录；标签不是内容相同的证明。

### 3. 准备新清单与密钥

```bash
cp infra/deploy/environments/example.yml infra/deploy/environments/prod.local.yml
cp infra/deploy/environments/example.secrets.env infra/deploy/environments/prod.secrets.local.env
chmod 600 infra/deploy/environments/prod.secrets.local.env
```

关键决定：

- 数据库沿用旧实例还是新建？沿用则 `database.mode: external`，并先执行 `db-init` 或填入已有角色密码。
- 应用密钥是否沿用？沿用才能保留已有会话；重新生成会让旧会话失效。
- 网关是新建还是复用共用网关？复用则 `gateway.mode: external`，只渲染站点块，人工并入。
- 是否迁移旧数据？迁移则准备最终 dump、恢复窗口和行数快照。

## 停机窗口

保守计量：从发出“停止旧写流量”到首次观测公网首页和健康端点都 200。不要用“容器启动时间”冒充停机窗口。

### 1. 停写

停止旧 Web/API/Worker，保留旧容器和配置：

```bash
docker compose --project-name <old-project> --env-file <old-env> -f <old-compose> stop web api worker
```

如果旧栈只有一个应用容器，停应用容器即可；不要删除卷、镜像或配置。

### 2. 最终备份

```bash
docker exec <db-container> pg_dump -U <user> -d <db> \
  --format=custom --no-owner --no-privileges > <backup-dir>/final-<UTC>.dump
pg_restore --list <backup-dir>/final-<UTC>.dump | head
```

记录文件路径、大小、`pg_restore --list` 是否成功。备份没有验证可读，不算最终备份。

### 3. 行数快照

对全部业务表记录行数，切换后逐表比对：

```sql
SELECT schemaname, relname, n_live_tup
FROM pg_stat_user_tables
ORDER BY schemaname, relname;
```

`n_live_tup` 是估算值；需要精确值时对每张表执行 `SELECT count(*)`。把结果保存为 CSV/文本，和切换后的结果做 diff。记录迁移版本：

```sql
SELECT version_num FROM alembic_version;
```

如果项目不用 Alembic，换成自己的迁移版本表。

### 4. 迁移/恢复数据

- external 数据库：由管理员创建属于应用角色的空库（不要预建备份内的 schema），再用 `pg_restore --no-owner --no-privileges --exit-on-error --single-transaction` 恢复；恢复后设置 `search_path`。
- bundled 数据库：先让 PostgreSQL 容器健康，再在空库恢复；不要删除数据卷。恢复后重放一次初始化脚本，应用角色权限和 `search_path`。
- 恢复后核对：迁移版本、表数量、关键表行数、角色权限、余额/账本类数据（如果有）。

### 5. 启动新栈

```bash
infra/deploy/deploy.sh prod release
```

首次 external 数据库如果还没初始化，先：

```bash
infra/deploy/deploy.sh prod db-init
```

`db-init` 默认不执行，也不会被 `release` 自动调用。Worker 在低 CPU 限额下可能需要多次健康检查才通过；不要为了通过而放宽健康检查或绕过依赖顺序。

### 6. 冒烟

至少验证：

- `origin/` 返回 200，页面无 JS page error；
- `origin/<health-path>` 返回 200；
- `/sw.js` 返回 200，`Service-Worker-Allowed: /`；
- Manifest、图标、启动图 200；
- 登录/关键 API 按实际契约工作；
- `deploy.sh status` 显示容器健康、当前 release、备份 timer；
- `backup-now` 成功，dump 可读。

用浏览器在手机视口打开公网地址，走一遍关键路径；不要只看 `curl`。

### 7. 切入口

确认新栈公网可达后，才把共用网关指向新上游，或切换 DNS。记录切换时间、操作人、入口变化。

### 8. 失败回旧

任一步失败：

1. 用旧 Compose、旧私有配置、旧镜像启动旧栈；
2. 先恢复入口（网关/DNS），再排查新栈；
3. 如果新栈已经产生写入，不能盲目把入口指回旧库；先评估数据回迁、迁移版本和新增写入。

旧栈启动后，记录：

- 旧栈恢复时间；
- 新栈失败点（哪一步、什么错误）；
- 是否发生数据写入；
- 下一次尝试前需要修复什么。

## 切换后

保留：

- 旧配置、旧 Compose、旧镜像、旧 runtime 卷；
- 最终 dump、行数快照、迁移版本；
- 新 release 记录和 `.ok`；
- 停机窗口、冒烟证据、浏览器截图。

在旧栈目录建一个 `legacy-<日期>/`，放旧 `private.env`、`backup.env`、旧 Compose、停机时间、最终备份路径和行数表。权限保持 0600。不要删除，直到确认不需要回退。

## 检查表

- [ ] 旧栈盘点完成，主机独有项和未核实项都列出
- [ ] 新镜像已加载，镜像 ID 已记录
- [ ] 清单与密钥分离，密钥 0600，真实值不在仓库
- [ ] 数据库模式、密钥沿用、数据迁移、入口方式都已决定
- [ ] 最终备份完成且 `pg_restore --list` 可读
- [ ] 行数快照和迁移版本已保存
- [ ] 停机窗口开始时间已记录
- [ ] 新栈健康、冒烟通过，`current` 已切换
- [ ] 备份 timer 和 `backup-now` 验证通过
- [ ] 旧栈回退材料和入口恢复步骤可执行
- [ ] 未验证项（公网 ACME、异地备份、恢复演练等）已写明

## 常见风险

- 只备份不验证：dump 损坏时，切换失败就没有退路。
- 用 `n_live_tup` 当精确行数：估算值会漂移，关键表要 `count(*)`。
- 迁移后预建同名 schema：`pg_restore` 会跳过或冲突；空库恢复时让备份自己建 schema。
- 切换后才发现 OAuth 回调/推送密钥没配：提前在清单和密钥里校验。
- 旧栈容器还在跑但入口已切走：旧 Worker 可能继续消费任务；停写要停干净。
- 回滚镜像但不回滚数据库：不可逆迁移后，旧镜像可能读不了新 schema；这种情况恢复备份，不要只回滚镜像。
