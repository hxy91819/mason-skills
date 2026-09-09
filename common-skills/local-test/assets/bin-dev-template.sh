#!/usr/bin/env bash
set -euo pipefail
# 脚本定义：本地多服务联调环境的统一启停入口（local-test skill 预设模式）。
# 用法：复制为项目 bin/dev，只填写下方"项目填空区"；机制函数无需改动。
# 关键决策：
#   - 每个 git worktree 是一个独立环境：namespace 决定库名后缀与端口偏移，多个 worktree 可并行；
#   - 中间件全机一份（compose），业务服务裸进程并以独立进程组启动，stop 杀整个进程组；
#   - 全机登记目录记录所有环境，status 可见、gc 回收孤儿、软上限防止资源耗尽，不做槽位租借；
#   - 主 checkout 无 namespace 时端口与库名维持原值；端口被未知进程占用即保守失败，不抢端口；
#   - stop 默认保留数据卷，destroy 只 drop 本环境的开发库，reset 清数据卷且必须显式确认。
readonly STATE_DIR=".local-test"
readonly RUN_DIR="$STATE_DIR/run"
readonly LOG_DIR="$STATE_DIR/logs"
readonly STOP_TIMEOUT=10
readonly REGISTRY_DIR="${LOCAL_TEST_REGISTRY_DIR:-$HOME/.local-test/registry}"
readonly MAX_ENVS="${LOCAL_TEST_MAX_ENVS:-5}"
readonly PORT_OFFSET_RANGE=200   # namespace 哈希映射到 [0, 200) 的端口偏移
# ==== 项目填空区（唯一需要修改的地方）================================
PROJECT_NAME=""            # 登记与日志中的项目名；留空则取仓库目录名
DOCKER_COMPOSE_FILE=""     # 中间件 docker compose 文件；留空则跳过中间件
DB_PREPARE_CMD=''          # 建库／迁移命令，运行时可读 $LOCAL_TEST_NAMESPACE 推导库名（用单引号延迟展开）；留空跳过
DB_DROP_CMD=''             # destroy／gc 时 drop 本环境开发库的命令，同样单引号；留空跳过
PREVIEW_URL="${PREVIEW_URL:-}" # 可用环境变量覆盖；默认从下方 Git-ignored 文件读取真实地址
PREVIEW_URL_FILE="$STATE_DIR/preview-url" # 单行完整 URL，纯文本读取，不作为 shell 执行
PREVIEW_LOGIN_URL="${PREVIEW_LOGIN_URL:-}" # 可覆盖本机入口登录链接
PREVIEW_LOGIN_URL_FILE="$STATE_DIR/preview-login-url"
GATEWAY_CONF=""            # 本环境 Caddy 配置路径，仅供 status 展示；共享网关由管理员维护
SERVICES=(
  # 名称|基准端口(仅监听 127.0.0.1)|启动命令|日志文件名
  # 启动命令在运行时由 bash -c 求值，用单引号包住整行，让 $LOCAL_TEST_PORT_<大写名称>、
  # $LOCAL_TEST_NAMESPACE 延迟展开取得本环境实际端口与 namespace
  # 'backend|8000|uvicorn app:app --host 127.0.0.1 --port $LOCAL_TEST_PORT_BACKEND|backend.log'
  # 'frontend|5173|npm run dev -- --host 127.0.0.1 --port $LOCAL_TEST_PORT_FRONTEND|frontend.log'
)
# ====================================================================
usage() {
  cat <<'EOF'
用法:
  bin/dev {start|stop|status|logs <service>|gc|destroy|reset --yes}
说明:
  本地多服务联调环境的统一启停入口。中间件走 docker compose 且全机一份，业务服务以
  裸进程按 worktree namespace 隔离启动并仅监听 127.0.0.1；对外暴露统一交给 Caddy。
选项:
  start            按中间件 -> 业务服务顺序拉起；幂等，本环境已拉起的服务跳过
  stop             逆序收敛：对进程组 SIGTERM 超时转 SIGKILL，校验端口释放；默认保留数据
  status           打印本环境各服务状态、端口，以及全机所有已登记环境
  logs <service>   跟踪指定服务日志（Ctrl-C 退出不影响服务）
  gc               回收全机孤儿环境：进程已死删登记；worktree 已删除则停进程、drop 库
  destroy          stop 后 drop 本环境开发库并删除登记；供 worktree teardown 调用，无环境时 no-op
  reset --yes      停止并清理数据卷后重新 start；仅用户明确要求"彻底重置"时使用
环境变量:
  LOCAL_TEST_NAMESPACE   覆盖 namespace（默认 linked worktree 取目录名，主 checkout 为空）
  LOCAL_TEST_REGISTRY_DIR 全机登记目录（默认 ~/.local-test/registry）
  LOCAL_TEST_MAX_ENVS    同时运行的环境软上限（默认 5）
输出结果定义:
  运行状态: .local-test/run/<service>.pid（进程组 id）、.local-test/run/port-offset
  服务日志: .local-test/logs/<service>.log
  全机登记: $LOCAL_TEST_REGISTRY_DIR/<project>--<namespace>
  退出码:   0 成功; 1 参数错误; 2 环境预检失败(端口被未知进程占用、超过软上限等); 3 服务启动失败
本机预览地址配置:
  在项目根目录执行脚本；将 .local-test/ 加入 .gitignore 或 .git/info/exclude。
  .local-test/preview-url 保存单行用户实际可访问的完整 URL（不含凭据）。
  .local-test/preview-login-url 保存入口登录链接；首次访问先登录再打开目标页面。
  PREVIEW_URL / PREVIEW_LOGIN_URL 可分别覆盖文件；status 显示配置值，不代表已验证可达。
示例:
  bin/dev start
  bin/dev logs backend
  LOCAL_TEST_NAMESPACE=task_123 bin/dev status
  bin/dev gc
EOF
}
log_info() { echo "INFO: $*"; }
log_error() { echo "ERROR: $*" >&2; }
is_up() {
  local port="$1"
  (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null || return 1
  exec 3>&- 3<&- || true
}
pgid_of() { local svc="$1"; cat "$RUN_DIR/$svc.pid" 2>/dev/null || echo ""; }
pgid_alive() {
  local pgid="$1"
  [[ -n "$pgid" ]] && kill -0 -- "-$pgid" 2>/dev/null
}
upper_ident() { printf '%s' "$1" | tr '[:lower:]-' '[:upper:]_' | tr -c 'A-Z0-9_\n' '_'; }

# ---- namespace / 端口 -------------------------------------------------
worktree_root() { git rev-parse --show-toplevel 2>/dev/null || pwd -P; }
canonical_namespace() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9_]+/_/g; s/_+/_/g; s/^_+|_+$//g'
}
resolve_namespace() {
  if [[ -n "${LOCAL_TEST_NAMESPACE:-}" ]]; then
    canonical_namespace "$LOCAL_TEST_NAMESPACE"; return
  fi
  local common git_dir
  common="$(git rev-parse --git-common-dir 2>/dev/null || true)"
  git_dir="$(git rev-parse --git-dir 2>/dev/null || true)"
  # linked worktree 的 git-dir 与 common-dir 不同；主 checkout 二者相同，namespace 为空
  if [[ -n "$common" && -n "$git_dir" && "$(cd "$common" && pwd -P)" != "$(cd "$git_dir" && pwd -P)" ]]; then
    canonical_namespace "$(basename "$(worktree_root)")"
  fi
}
hash_offset() {
  # cksum 在 macOS/Linux 都有；取模得到决定性偏移，0 保留给主 checkout
  local n
  n="$(printf '%s' "$1" | cksum | awk '{print $1}')"
  echo $(( n % (PORT_OFFSET_RANGE - 1) + 1 ))
}
resolve_port_offset() {
  # 无 namespace：偏移 0。有 namespace：优先读取本环境已记录偏移；否则哈希并在冲突时顺延
  [[ -z "$NAMESPACE" ]] && { echo 0; return; }
  if [[ -f "$RUN_DIR/port-offset" ]]; then cat "$RUN_DIR/port-offset"; return; fi
  local offset row base tries=0
  offset="$(hash_offset "$NAMESPACE")"
  while (( tries < PORT_OFFSET_RANGE )); do
    local clash=0
    for row in "${SERVICES[@]}"; do
      IFS='|' read -r _ base _ _ <<<"$row"
      is_up $(( base + offset )) && { clash=1; break; }
    done
    (( clash == 0 )) && { echo "$offset"; return; }
    offset=$(( offset % (PORT_OFFSET_RANGE - 1) + 1 )); tries=$((tries + 1))
  done
  log_error "namespace $NAMESPACE 在 $PORT_OFFSET_RANGE 个偏移内找不到空闲端口"; return 2
}
export_service_ports() {
  local row svc base
  for row in "${SERVICES[@]}"; do
    IFS='|' read -r svc base _ _ <<<"$row"
    export "LOCAL_TEST_PORT_$(upper_ident "$svc")=$(( base + PORT_OFFSET ))"
  done
  export LOCAL_TEST_NAMESPACE="$NAMESPACE"
}
service_port() { local base="$1"; echo $(( base + PORT_OFFSET )); }

# ---- 全机登记 ---------------------------------------------------------
registry_key() { echo "${PROJECT_NAME}--${NAMESPACE:-main}"; }
registry_write() {
  mkdir -p "$REGISTRY_DIR"
  {
    echo "project=$PROJECT_NAME"
    echo "namespace=${NAMESPACE:-}"
    echo "worktree=$WORKTREE"
    echo "port_offset=$PORT_OFFSET"
    echo "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    local row svc base
    for row in "${SERVICES[@]}"; do
      IFS='|' read -r svc base _ _ <<<"$row"
      echo "service=$svc:$(service_port "$base"):$(pgid_of "$svc")"
    done
  } >"$REGISTRY_DIR/$(registry_key)"
}
registry_remove() { rm -f "$REGISTRY_DIR/$(registry_key)"; }
registry_entry_alive() {
  # 任一登记的进程组存活即视为环境存活
  local file="$1" line pgid
  while IFS= read -r line; do
    [[ "$line" == service=* ]] || continue
    pgid="${line##*:}"
    pgid_alive "$pgid" && return 0
  done <"$file"
  return 1
}
count_live_envs() {
  local file n=0
  for file in "$REGISTRY_DIR"/*; do
    [[ -f "$file" ]] || continue
    [[ "$(basename "$file")" == "$(registry_key)" ]] && continue
    registry_entry_alive "$file" && n=$((n + 1))
  done
  echo "$n"
}
worktree_registered() {
  # 判断登记的 worktree 路径是否仍存在于其仓库的 git worktree 清单
  local path="$1"
  [[ -d "$path" ]] || return 1
  git -C "$path" worktree list --porcelain 2>/dev/null | grep -Fxq "worktree $path"
}

# ---- 单服务启停 -------------------------------------------------------
start_one() {
  local svc="$1" base="$2" cmd="$3" logfile="$4" port pgid
  port="$(service_port "$base")"
  if is_up "$port"; then
    pgid="$(pgid_of "$svc")"
    if pgid_alive "$pgid"; then
      log_info "$svc 已在运行 (pgid $pgid, 端口 $port)，跳过"
      return 0
    fi
    # 端口被占但不是本环境拉起的：可能是其他 Agent 或遗留进程，保守失败不抢端口
    log_error "$svc 端口 $port 被未知进程占用，非本环境拉起；请人工确认后处理"
    return 2
  fi
  mkdir -p "$RUN_DIR" "$LOG_DIR"
  log_info "启动 $svc (127.0.0.1:$port)"
  # setsid 让服务成为独立进程组，stop 时可整组回收 foreman/watcher 等子进程
  setsid bash -c "$cmd" >"$LOG_DIR/$logfile" 2>&1 < /dev/null &
  pgid=$!
  echo "$pgid" >"$RUN_DIR/$svc.pid"
  sleep 1
  if ! pgid_alive "$pgid"; then
    log_error "$svc 启动后立即退出，查看 $LOG_DIR/$logfile"
    rm -f "$RUN_DIR/$svc.pid"
    return 3
  fi
}
stop_pgid() {
  local pgid="$1" waited=0
  pgid_alive "$pgid" || return 0
  kill -TERM -- "-$pgid" 2>/dev/null || true
  while pgid_alive "$pgid" && ((waited < STOP_TIMEOUT)); do sleep 1; waited=$((waited + 1)); done
  pgid_alive "$pgid" && kill -KILL -- "-$pgid" 2>/dev/null || true
  sleep 0.2
  ! pgid_alive "$pgid"
}
stop_one() {
  local svc="$1" base="$2" port pgid
  port="$(service_port "$base")"
  pgid="$(pgid_of "$svc")"
  if [[ -n "$pgid" ]]; then
    stop_pgid "$pgid" && log_info "$svc (pgid $pgid) 已停止" || log_error "$svc (pgid $pgid) 无法终止"
  fi
  rm -f "$RUN_DIR/$svc.pid"
  if is_up "$port"; then
    log_error "$svc 端口 $port 仍被占用（可能存在孤儿进程），请人工确认"
    return 2
  fi
}
compose_action() {
  [[ -z "$DOCKER_COMPOSE_FILE" ]] && return 0
  [[ -f "$DOCKER_COMPOSE_FILE" ]] || { log_error "找不到 $DOCKER_COMPOSE_FILE"; return 2; }
  # stop 用 stop 不用 down：容器与卷保留，符合"默认保留数据"；中间件全机共享，多环境共用
  docker compose -f "$DOCKER_COMPOSE_FILE" "$@"
}

# ---- 子命令 -----------------------------------------------------------
cmd_start() {
  local row rc=0 live
  live="$(count_live_envs)"
  if (( live >= MAX_ENVS )); then
    log_error "全机已有 $live 个环境在运行，达到软上限 LOCAL_TEST_MAX_ENVS=$MAX_ENVS；先 bin/dev status 查看并停止不需要的环境"
    return 2
  fi
  compose_action up -d || rc=3
  if [[ -n "$DB_PREPARE_CMD" && ! -f "$RUN_DIR/db-prepared" ]]; then
    mkdir -p "$RUN_DIR"
    log_info "准备本地开发库 (namespace: ${NAMESPACE:-<none>})"
    bash -c "$DB_PREPARE_CMD" || { log_error "本地开发库准备失败"; return 3; }
    touch "$RUN_DIR/db-prepared"
  fi
  mkdir -p "$RUN_DIR"; echo "$PORT_OFFSET" >"$RUN_DIR/port-offset"
  for row in "${SERVICES[@]}"; do
    IFS='|' read -r svc base cmd logfile <<<"$row"
    start_one "$svc" "$base" "$cmd" "$logfile" || rc=$?
  done
  registry_write
  ((rc == 0)) && log_info "环境已就绪 (namespace: ${NAMESPACE:-<none>}, 端口偏移 $PORT_OFFSET)，入口见 bin/dev status"
  ((rc == 2)) && log_info "存在被未知进程占用的端口，处置前先 bin/dev status 人工确认"
  return $rc
}
cmd_stop() {
  local row rc=0 i
  local reversed=()
  for ((i=${#SERVICES[@]}-1; i>=0; i--)); do reversed+=("${SERVICES[i]}"); done
  for row in "${reversed[@]}"; do
    IFS='|' read -r svc base _ _ <<<"$row"
    stop_one "$svc" "$base" || rc=2
  done
  registry_remove
  # 中间件全机共享：其他环境仍在运行时不停止容器
  if (( $(count_live_envs) == 0 )); then
    compose_action stop || rc=2
    ((rc == 0)) && log_info "已全部停止（数据卷保留）"
  else
    ((rc == 0)) && log_info "本环境已停止；中间件仍被其他环境使用，保留运行"
  fi
  return $rc
}
cmd_status() {
  local row svc base logfile port pgid state
  echo "== 本环境 =="
  echo "  项目: $PROJECT_NAME  namespace: ${NAMESPACE:-<none>}  端口偏移: $PORT_OFFSET  worktree: $WORKTREE"
  echo "== 中间件 =="
  [[ -n "$DOCKER_COMPOSE_FILE" ]] && docker compose -f "$DOCKER_COMPOSE_FILE" ps --format '{{.Name}}: {{.Status}}' 2>/dev/null || echo "(未配置)"
  echo "== 业务服务 =="
  for row in "${SERVICES[@]}"; do
    IFS='|' read -r svc base _ logfile <<<"$row"
    port="$(service_port "$base")"
    pgid="$(pgid_of "$svc")"
    if is_up "$port"; then state="UP  (127.0.0.1:$port, pgid ${pgid:-unknown})"; else state="DOWN (127.0.0.1:$port)"; fi
    printf '  %-12s %s\n' "$svc" "$state"
  done
  echo "== 对外入口 =="
  local preview_url="$PREVIEW_URL" login_url="$PREVIEW_LOGIN_URL"
  if [[ -z "$preview_url" && -f "$PREVIEW_URL_FILE" ]]; then
    preview_url="$(cat "$PREVIEW_URL_FILE")" || return 2
  fi
  if [[ -z "$login_url" && -f "$PREVIEW_LOGIN_URL_FILE" ]]; then
    login_url="$(cat "$PREVIEW_LOGIN_URL_FILE")" || return 2
  fi
  if [[ -n "$login_url" ]]; then
    printf '  入口登录地址（首次访问先登录）: %s\n' "$login_url"
  else
    echo "  (未登记入口登录地址，请核对本机网关配置)"
  fi
  if [[ -n "$preview_url" ]]; then
    printf '  用户预览地址（配置值，需单独验证可达）: %s\n' "$preview_url"
    printf '  代理配置: %s\n' "${GATEWAY_CONF:-由管理员登记}"
    echo "  入口凭据由管理员提供；共享网关不随本环境启停"
  else
    echo "  (未登记用户预览地址；请配置 $PREVIEW_URL_FILE，勿将内部监听地址当作预览链接)"
  fi
  echo "== 全机已登记环境 ($REGISTRY_DIR) =="
  local file any=0
  for file in "$REGISTRY_DIR"/*; do
    [[ -f "$file" ]] || continue
    any=1
    if registry_entry_alive "$file"; then state="ALIVE"; else state="DEAD "; fi
    printf '  %s %-40s %s\n' "$state" "$(basename "$file")" "$(grep '^worktree=' "$file" | cut -d= -f2-)"
  done
  ((any == 0)) && echo "  (无)"
}
cmd_logs() {
  local target="$1" row svc logfile
  [[ -z "$target" ]] && { log_error "logs 需要服务名，可选: 见 SERVICES 填空区"; return 1; }
  for row in "${SERVICES[@]}"; do
    IFS='|' read -r svc _ _ logfile <<<"$row"
    if [[ "$svc" == "$target" ]]; then
      tail -n 100 -f "$LOG_DIR/$logfile"
      return 0
    fi
  done
  log_error "未知服务 $target"
  return 1
}
cmd_gc() {
  local file key path line pgid rc=0 reclaimed=0
  for file in "$REGISTRY_DIR"/*; do
    [[ -f "$file" ]] || continue
    key="$(basename "$file")"
    path="$(grep '^worktree=' "$file" | cut -d= -f2-)"
    if ! registry_entry_alive "$file"; then
      log_info "gc: $key 进程已退出，删除登记"
      rm -f "$file"; reclaimed=$((reclaimed + 1)); continue
    fi
    if ! worktree_registered "$path"; then
      log_info "gc: $key 的 worktree 已不存在 ($path)，终止进程组"
      while IFS= read -r line; do
        [[ "$line" == service=* ]] || continue
        pgid="${line##*:}"
        stop_pgid "$pgid" || { log_error "gc: 无法终止 pgid $pgid"; rc=2; }
      done <"$file"
      # worktree 已删，其本地开发库只能由 gc 回收；drop 命令按登记的 namespace 执行
      if [[ -n "$DB_DROP_CMD" ]]; then
        LOCAL_TEST_NAMESPACE="$(grep '^namespace=' "$file" | cut -d= -f2-)" bash -c "$DB_DROP_CMD" \
          || { log_error "gc: $key drop 开发库失败"; rc=2; }
      fi
      rm -f "$file"; reclaimed=$((reclaimed + 1))
    fi
  done
  log_info "gc 完成，回收 $reclaimed 个环境"
  return $rc
}
cmd_destroy() {
  local rc=0
  if [[ ! -d "$RUN_DIR" && ! -f "$REGISTRY_DIR/$(registry_key)" ]]; then
    log_info "destroy: 本环境从未启动，无需处理"
    return 0
  fi
  cmd_stop || rc=$?
  if [[ -n "$DB_DROP_CMD" && -f "$RUN_DIR/db-prepared" ]]; then
    log_info "drop 本地开发库 (namespace: ${NAMESPACE:-<none>})"
    bash -c "$DB_DROP_CMD" || { log_error "drop 开发库失败"; rc=2; }
  fi
  rm -rf "$RUN_DIR"
  registry_remove
  return $rc
}
cmd_reset() {
  [[ "${1:-}" == "--yes" ]] || { log_error "reset 会清理数据卷，必须带 --yes 且经用户明确要求"; return 1; }
  cmd_stop || true
  rm -f "$RUN_DIR/db-prepared"
  [[ -n "$DOCKER_COMPOSE_FILE" ]] && docker compose -f "$DOCKER_COMPOSE_FILE" down -v || true
  log_info "数据卷已清理，执行 bin/dev start 重建环境"
}
main() {
  local cmd="${1:-}"
  WORKTREE="$(worktree_root)"
  PROJECT_NAME="${PROJECT_NAME:-$(basename "$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null | xargs -r dirname || pwd -P)")}"
  NAMESPACE="$(resolve_namespace)"
  PORT_OFFSET="$(resolve_port_offset)" || exit 2
  export_service_ports
  case "$cmd" in
    start) cmd_start ;;
    stop)  cmd_stop ;;
    status) cmd_status ;;
    logs)  shift; cmd_logs "${1:-}" ;;
    gc)    cmd_gc ;;
    destroy) cmd_destroy ;;
    reset) shift; cmd_reset "${1:-}" ;;
    -h|--help|help|'') usage ;;
    *) usage; log_error "未知命令 $cmd"; return 1 ;;
  esac
}
main "$@"
