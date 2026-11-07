# 排错路径

## 先定位在哪一层

| 层 | 典型症状 | 先看 |
| --- | --- | --- |
| 控制器 | Ansible/SSH/Docker Buildx 直接报错 | `ansible-inventory -i <manifest> --list`、`ssh -v`、`docker buildx version` |
| 清单/密钥 | 发布前断言失败 | `deploy.sh <env> release` 的 stderr；只核对键名，不打印值 |
| 传输 | `docker load` 失败、镜像不存在 | 目标机 `docker image ls`、磁盘空间 |
| 编排 | Compose 起不来、健康检查失败 | 目标机同组 `-f`/`--env-file` 的 `ps`、`logs` |
| 应用 | 健康端点 503、页面 502 | API/Worker 日志、数据库连接、依赖状态 |
| 入口 | 证书错误、403、404、SW 不更新 | 网关配置、证书状态、缓存头、DNS/安全组 |
| 备份 | timer 不跑、dump 缺失/损坏 | `systemctl`、`journalctl`、`pg_restore --list` |

## Ansible / SSH

- `Host key verification failed`：把目标主机指纹加入 `~/.ssh/known_hosts`。不要长期用 `StrictHostKeyChecking=no`；那会掩盖中间人风险。
- `sudo: a password is required`：部署账号必须免密 sudo。不要把 sudo 密码写进清单或命令历史。
- `docker: permission denied`：重新登录让 docker 组生效；`bootstrap` 已把账号加入组。
- `No module named ...`：目标机缺 `python3` 或集合没装。先 `ansible-galaxy collection install -r infra/deploy/requirements.yml`。
- `ansible-playbook` 报 `DEFAULT_LOCAL_TMP` 权限错误：设置可写的 `ANSIBLE_LOCAL_TEMP` 和 `ANSIBLE_HOME`，不要用不可写的家目录缓存。

## 发布前

- 工作区不干净：先提交或清理未跟踪文件；不要在发布时用 `git stash`。
- 密钥缺失：按 `secrets.required` 补齐；不要手工改主机 `private.env`。
- 镜像构建失败：确认控制器有 Buildx、目标平台模拟器/多架构支持、Dockerfile 路径在仓库内。
- Compose 文件不存在：清单里的 `compose.*` 是仓库相对路径；确认文件已入库，不是只在某台机器上。

## 发布中

### Compose 启动失败

在目标机用和 `deploy.sh` 相同的组合执行：

```bash
docker compose --project-name <project> \
  --env-file <deploy_root>/private.env \
  -f <deploy_root>/compose.deploy.yml \
  -f <deploy_root>/compose.deploy.<db-mode>-db.yml \
  -f <deploy_root>/compose.deploy.<gateway-mode>-gateway.yml \
  ps
```

再看日志：

```bash
docker compose ... logs --tail 100 api worker web
```

不要输出 `docker compose config`：它可能展开密钥。不要把完整 env 贴进工单。

### 健康检查失败

- API 健康端点 503：看数据库连接、迁移版本、依赖（Redis/队列）、应用密钥。
- Worker 健康检查超时：低 CPU 限额下导入应用可能超过 30 秒；先看 CPU 配额和启动日志，不要直接把 timeout 调到很大来“通过”。
- Web 健康检查失败：看 Web 容器是否能访问 API/Worker，反向代理上游是否写对。

### 冒烟失败

- 502/503：入口网关已指向新上游，但上游没健康；先修应用，不要反复切 `current`。
- 证书错误：确认 DNS 指向、80/443 或选定端口可达、ACME 出站可用；`ip-shortlived` 需要公网可达。
- 403：检查网关的 Origin 允许列表、Host 转发、上游端口。
- 静态资源 404：检查 `deploy_root` 里的 Web 产物、`try_files` fallback、`/sw.js` 重写。

## 回滚

1. `deploy.sh <env> status` 确认当前记录和容器状态。
2. `deploy.sh <env> rollback` 回到上一份 `.ok`；或显式指定 `releases/<记录>.json`。
3. 如果回滚后应用仍报数据库错误，检查是否执行过不可逆迁移；这种情况恢复备份，不要继续回滚镜像。
4. 回滚不改数据库、不改应用密钥；如果密钥已经轮换，旧镜像可能无法解密旧会话，需要单独处理。

## 备份

- timer 不跑：`systemctl status <project>-db-backup.timer`、`systemctl list-timers`、`journalctl -u <project>-db-backup.timer`。
- service 失败：`journalctl -u <project>-db-backup.service -n 100 --no-pager`。
- dump 为空/损坏：检查 `docker exec` 的容器名、库名、角色权限、磁盘空间；用 `pg_restore --list` 验证。
- 异地副本失败：确认主机安装了 `rclone`、配置路径可读、remote 可写；异地失败时本机 dump 应保留。
- 保留期清理：脚本只删自己前缀的 dump；不要手工 `rm` 整个备份目录。

## 网关与证书

- bundled：`docker compose ... logs edge`；确认 `Caddyfile.site` 已挂载，证书状态在 `caddy_data` 卷。
- external：本工具只渲染站点块，不重载共用网关；把 `Caddyfile.site` 并入共用配置，按共用网关流程校验、重载。
- 证书续期失败：检查 ACME 账户、80/443 可达、DNS、系统时间；不要把 `tls internal` 用到公网。
- 入口改了但页面仍旧：检查 DNS TTL、共用网关 upstream、浏览器缓存、Service Worker 缓存（见 `mobile-web-shell` 的离线更新）。

## 数据库

- `db-init` 失败：确认 `database.mode=external`、管理员密码、网络可达、容器名/库名/角色名合法；幂等重放不会删除已有数据。
- `search_path` 不对：用应用角色连接执行 `SELECT current_schema(), current_setting('search_path')`；确认 `ALTER ROLE ... IN DATABASE ... SET search_path` 已执行。
- 连接数打满：核对应用池 + Worker 池 + 管理连接与实例 `max_connections`；不要只调大应用池。
- 恢复后表缺失：确认空库恢复、没有预建同名 schema、`pg_restore --no-owner --no-privileges`、迁移版本正确。

## 记录

排错结束后记录：

- 失败的动作、时间、环境、commit/镜像；
- 直接错误和相关日志片段（脱敏）；
- 根因和修复；
- 是否影响数据/入口/备份；
- 下次如何提前发现。

不要只留一句“重启后好了”。发布机制的价值在于下次能更快定位。
