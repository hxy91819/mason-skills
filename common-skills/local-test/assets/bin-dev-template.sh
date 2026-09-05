#!/usr/bin/env bash
set -euo pipefail

# 脚本定义：本地多服务联调环境的统一启停入口（local-test skill 预设模式）。
# 用法：复制为项目 bin/dev，只填写下方"项目填空区"；机制函数无需改动。
# 关键决策：启动前做端口预检、端口被占即保守失败（不抢端口，可能是其他 Agent 的现场）；
#           stop 默认保留数据卷，reset 清数据卷且必须显式确认，防止误删测试数据。

readonly STATE_DIR=".local-test"
readonly RUN_DIR="$STATE_DIR/run"
readonly LOG_DIR="$STATE_DIR/logs"
readonly STOP_TIMEOUT=10

# ==== 项目填空区（唯一需要修改的地方）================================
DOCKER_COMPOSE_FILE=""   # 中间件 docker compose 文件；留空则跳过中间件
NGINX_CONF=""            # nginx 配置路径（对外入口，见 SKILL.md 第 3 节）；留空则跳过
SERVICES=(
  # 名称|监听地址(仅 127.0.0.1)|启动命令|日志文件名
  # "backend|127.0.0.1:8000|uvicorn app:app --host 127.0.0.1 --port 8000|backend.log"
  # "frontend|127.0.0.1:5173|npm run dev -- --host 127.0.0.1|frontend.log"
)
# ====================================================================

usage() {
  cat <<'EOF'
用法:
  bin/dev {start|stop|status|logs <service>|reset --yes}

说明:
  本地多服务联调环境的统一启停入口。中间件走 docker compose，业务服务以
  裸进程启动并仅监听 127.0.0.1；对外暴露统一交给 Nginx（本脚本只管进程与容器）。

选项:
  start            按中间件 -> 业务服务 -> Nginx 顺序拉起；幂等，本环境已拉起的服务跳过
  stop             逆序收敛：SIGTERM 超时转 SIGKILL，校验端口释放；默认保留数据
  status           打印各服务存活状态、PID 与对外访问入口
  logs <service>   跟踪指定服务日志（Ctrl-C 退出不影响服务）
  reset --yes      停止并清理数据卷后重新 start；仅用户明确要求"彻底重置"时使用

输出结果定义:
  运行状态: .local-test/run/<service>.pid
  服务日志: .local-test/logs/<service>.log
  退出码:   0 成功; 1 参数错误; 2 环境预检失败(端口被未知进程占用等); 3 服务启动失败

示例:
  bin/dev start
  bin/dev logs backend
  bin/dev reset --yes
EOF
}

log_info() { echo "INFO: $*"; }
log_error() { echo "ERROR: $*" >&2; }

port_of() { local addr="$1"; echo "${addr##*:}"; }

is_up() {
  local port="$1"
  (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null || return 1
  exec 3>&- 3<&- || true
}

pid_of() { local svc="$1"; cat "$RUN_DIR/$svc.pid" 2>/dev/null || echo ""; }

alive() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

start_one() {
  local svc="$1" addr="$2" cmd="$3" logfile="$4" port pid
  port="$(port_of "$addr")"
  if is_up "$port"; then
    pid="$(pid_of "$svc")"
    if alive "$pid"; then
      log_info "$svc 已在运行 (pid $pid)，跳过"
    else
      # 端口被占但不是本脚本拉起的：可能是其他 Agent 或遗留进程，保守失败不抢端口
      log_error "$svc 端口 $port 被未知进程占用，非本环境拉起；请人工确认后处理"
      return 2
    fi
    return 0
  fi
  mkdir -p "$RUN_DIR" "$LOG_DIR"
  log_info "启动 $svc ($addr)"
  nohup bash -c "$cmd" >"$LOG_DIR/$logfile" 2>&1 &
  pid=$!
  echo "$pid" >"$RUN_DIR/$svc.pid"
  sleep 1
  if ! alive "$pid"; then
    log_error "$svc 启动后立即退出，查看 $LOG_DIR/$logfile"
    return 3
  fi
}

stop_one() {
  local svc="$1" addr="$2" port pid waited=0
  port="$(port_of "$addr")"
  pid="$(pid_of "$svc")"
  if alive "$pid"; then
    kill "$pid" 2>/dev/null || true
    while alive "$pid" && ((waited < STOP_TIMEOUT)); do sleep 1; waited+=1; done
    alive "$pid" && kill -9 "$pid" 2>/dev/null || true
    log_info "$svc (pid $pid) 已停止"
  fi
  rm -f "$RUN_DIR/$svc.pid"
  if is_up "$port"; then
    log_error "$svc 端口 $port 仍被占用（可能存在孤儿进程），请人工确认"
    return 2
  fi
}

compose_action() {
  local action="$1"
  [[ -z "$DOCKER_COMPOSE_FILE" ]] && return 0
  [[ -f "$DOCKER_COMPOSE_FILE" ]] || { log_error "找不到 $DOCKER_COMPOSE_FILE"; return 2; }
  # stop 用 stop 不用 down：容器与卷保留，符合"默认保留数据"
  docker compose -f "$DOCKER_COMPOSE_FILE" "$action"
}

nginx_action() {
  local action="$1"
  [[ -z "$NGINX_CONF" ]] && return 0
  case "$action" in
    start) nginx -c "$NGINX_CONF" ;;
    stop)  nginx -s quit -c "$NGINX_CONF" 2>/dev/null || true ;;
  esac
}

cmd_start() {
  local row r rc=0
  compose_action "up -d" || rc=3
  for row in "${SERVICES[@]}"; do
    IFS='|' read -r svc addr cmd logfile <<<"$row"
    start_one "$svc" "$addr" "$cmd" "$logfile" || rc=$?
  done
  nginx_action "start" || rc=3
  ((rc == 0)) && log_info "环境已就绪，入口见 bin/dev status"
  ((rc == 2)) && log_info "存在被未知进程占用的端口，处置前先 bin/dev status 人工确认"
  return $rc
}

cmd_stop() {
  local row rc=0
  nginx_action "stop"
  local reversed=()
  local i
  for ((i=${#SERVICES[@]}-1; i>=0; i--)); do reversed+=("${SERVICES[i]}"); done
  for row in "${reversed[@]}"; do
    IFS='|' read -r svc addr cmd logfile <<<"$row"
    stop_one "$svc" "$addr" || rc=2
  done
  compose_action "stop" || rc=2
  ((rc == 0)) && log_info "已全部停止（数据卷保留）"
  return $rc
}

cmd_status() {
  local row svc addr logfile port pid state
  echo "== 中间件 =="
  [[ -n "$DOCKER_COMPOSE_FILE" ]] && docker compose -f "$DOCKER_COMPOSE_FILE" ps --format '{{.Name}}: {{.Status}}' 2>/dev/null || echo "(未配置)"
  echo "== 业务服务 =="
  for row in "${SERVICES[@]}"; do
    IFS='|' read -r svc addr _ logfile <<<"$row"
    port="$(port_of "$addr")"
    pid="$(pid_of "$svc")"
    if is_up "$port"; then state="UP  ($addr, pid ${pid:-unknown})"; else state="DOWN"; fi
    printf '%-12s %s\n' "$svc" "$state"
  done
  echo "== 对外入口 =="
  if [[ -n "$NGINX_CONF" ]]; then
    grep -E 'listen|auth_basic_user_file' "$NGINX_CONF" | sed 's/^/  /'
    echo "  账号密码见 $NGINX_CONF 引用的 htpasswd 文件"
  else
    echo "  (未配置 Nginx，服务仅限本机访问)"
  fi
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

cmd_reset() {
  [[ "${1:-}" == "--yes" ]] || { log_error "reset 会清理数据卷，必须带 --yes 且经用户明确要求"; return 1; }
  cmd_stop || true
  [[ -n "$DOCKER_COMPOSE_FILE" ]] && docker compose -f "$DOCKER_COMPOSE_FILE" down -v || true
  log_info "数据卷已清理，执行 bin/dev start 重建环境"
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    start) cmd_start ;;
    stop)  cmd_stop ;;
    status) cmd_status ;;
    logs)  shift; cmd_logs "${1:-}" ;;
    reset) shift; cmd_reset "${1:-}" ;;
    -h|--help|help|'') usage ;;
    *) usage; log_error "未知命令 $cmd"; return 1 ;;
  esac
}

main "$@"