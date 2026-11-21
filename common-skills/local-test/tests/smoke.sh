#!/usr/bin/env bash
set -uo pipefail
# 脚本定义：bin/lt 的端到端冒烟测试。
# 用法：tests/smoke.sh（需要 git、python3、curl；不需要 docker）
# 关键决策：
#   - 在临时 git 仓库里造真实的主 checkout + linked worktree，因为 namespace、端口偏移、
#     gc 这些机制全部依赖真实的 git worktree 拓扑，mock 不了；
#   - 登记目录指向临时目录，避免污染开发机的 ~/.local-test。
LT="$(cd "$(dirname "$0")/.." && pwd)/bin/lt"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/lt-smoke.XXXXXX")"
export LOCAL_TEST_REGISTRY_DIR="$TMP/registry"
DROPLOG="$TMP/drop.log"
SEEDLOG="$TMP/seed.log"
VERIFYLOG="$TMP/verify.log"
PASS=0; FAIL=0

ok()   { PASS=$((PASS + 1)); echo "PASS: $*"; }
bad()  { FAIL=$((FAIL + 1)); echo "FAIL: $*"; }
check(){ if [[ "$2" == "$3" ]]; then ok "$1 ($2)"; else bad "$1: 期望 [$3] 实得 [$2]"; fi; }

cleanup() {
  for d in "$TMP/main" "$TMP/wt-alpha" "$TMP/wt-beta" \
      "$TMP/slow-port" "$TMP/dead-port" "$TMP/health-url" "$TMP/health-tcp" \
      "$TMP/health-fail" "$TMP/compose-flags" "$TMP/compose-plain" "$TMP/compose-missing"; do
    [[ -d "$d" ]] && (cd "$d" && "$LT" destroy >/dev/null 2>&1)
  done
  "$LT" gc >/dev/null 2>&1 || true
  pkill -f "lt-smoke" >/dev/null 2>&1 || true
  rm -rf "$TMP"
}
trap cleanup EXIT

http_code() {
  local port="$1" i code
  for i in 1 2 3 4 5 6 7 8 9 10; do
    code="$(curl -s -o /dev/null -m 2 -w '%{http_code}' "http://127.0.0.1:$port/" || true)"
    [[ "$code" == "200" ]] && { echo "$code"; return 0; }
    sleep 0.5
  done
  echo "${code:-000}"
}
lt_in() { local dir="$1"; shift; (cd "$dir" && "$LT" "$@"); }
make_repo() {
  local dir="$1"
  mkdir -p "$dir"
  git -C "$dir" init -q -b main
  git -C "$dir" config user.email smoke@example.com
  git -C "$dir" config user.name smoke
}
once_up() {
  curl -s -o /dev/null -m 1 -w '%{http_code}' "$1" 2>/dev/null || true
}

echo "=== 准备临时仓库 $TMP ==="
mkdir -p "$TMP/main"
cd "$TMP/main"
git init -q -b main .
git config user.email smoke@example.com
git config user.name smoke
cat >.local-test.yml <<YML
project: ltsmoke
database:
  mode: rebuildable
  prepare: echo prepared:\$LOCAL_TEST_NAMESPACE >> $TMP/prepare.log
  seed: echo seeded:\$LOCAL_TEST_NAMESPACE >> $SEEDLOG
  verify: echo verified:\$LOCAL_TEST_NAMESPACE >> $VERIFYLOG
  drop: echo dropped:\$LOCAL_TEST_NAMESPACE >> $DROPLOG
external:
  mode_env: SMOKE_MODE
services:
  web:
    port: 47710
    cmd: python3 -m http.server \$LOCAL_TEST_PORT_WEB --bind 127.0.0.1 --directory $TMP/lt-smoke-docroot
preview_url: http://127.0.0.1:\$LOCAL_TEST_PORT_WEB/
YML
mkdir -p "$TMP/lt-smoke-docroot"
echo hello >"$TMP/lt-smoke-docroot/index.html"
printf ".local-test/\n" >.gitignore
git add -A && git commit -qm init
git worktree add -q "$TMP/wt-alpha" -b alpha
git worktree add -q "$TMP/wt-beta" -b beta

echo
echo "=== 参数校验先于任何副作用 ==="
# 用真实 CLI 和临时配置观察 drop、共享中间件与状态文件；不接触本机环境。
mkdir -p "$TMP/args/.local-test/run" "$TMP/args/bin"
cat >"$TMP/args/.local-test.yml" <<YML
project: args
middleware: compose.yml
database:
  mode: rebuildable
  prepare: echo prepare >> $TMP/actions
  seed: echo seed >> $TMP/actions
  verify: echo verify >> $TMP/actions
  drop: echo drop >> $TMP/actions
services:
  web:
    cmd: echo service >> $TMP/actions
YML
touch "$TMP/args/compose.yml"
cat >"$TMP/args/bin/docker" <<SH
#!/usr/bin/env bash
echo docker >> "$TMP/actions"
SH
cp "$TMP/args/bin/docker" "$TMP/args/bin/tail"
chmod +x "$TMP/args/bin/docker" "$TMP/args/bin/tail"
# 单点回归：后置帮助必须保留 prepared 标记，也不能调用 drop 或 docker。
touch "$TMP/args/.local-test/run/db-prepared"
OUT="$(cd "$TMP/args" && PATH="$TMP/args/bin:$PATH" "$LT" stop --help 2>&1)"; RC=$?
check "stop --help 退出码" "$RC" "0"
if echo "$OUT" | grep -q '用法:'; then ok "后置帮助打印说明"; else bad "后置帮助未打印说明: $OUT"; fi
if [[ -f "$TMP/args/.local-test/run/db-prepared" && ! -f "$TMP/actions" ]]; then ok "后置帮助无副作用"; else bad "后置帮助执行了命令"; fi

# 所有子命令的两种后置帮助（包括已有有效参数之后），都不得执行。
for CMD_ARGS in 'doctor' 'init --force' 'init --from-json missing.json' 'start' 'stop' 'status' 'logs web' 'gc' 'destroy' 'reset --yes'; do
  for HELP in -h --help; do
    rm -f "$TMP/actions"
    touch "$TMP/args/.local-test/run/db-prepared"
    OUT="$(cd "$TMP/args" && PATH="$TMP/args/bin:$PATH" "$LT" $CMD_ARGS "$HELP" 2>&1)"; RC=$?
    check "$CMD_ARGS $HELP 退出码" "$RC" "0"
    if echo "$OUT" | grep -q '用法:' && [[ -f "$TMP/args/.local-test/run/db-prepared" && ! -f "$TMP/actions" ]]; then ok "$CMD_ARGS $HELP 只打印帮助"; else bad "$CMD_ARGS $HELP 执行了命令"; fi
  done
done
for CMD_ARGS in 'doctor' 'init --force' 'start' 'stop' 'status' 'logs web' 'gc' 'destroy' 'reset --yes'; do
  for BAD in --unknown -z; do
    rm -f "$TMP/actions"
    touch "$TMP/args/.local-test/run/db-prepared"
    OUT="$(cd "$TMP/args" && PATH="$TMP/args/bin:$PATH" "$LT" $CMD_ARGS "$BAD" 2>&1)"; RC=$?
    check "$CMD_ARGS $BAD 退出码" "$RC" "1"
    if echo "$OUT" | grep -q 'ERROR:' && [[ -f "$TMP/args/.local-test/run/db-prepared" && ! -f "$TMP/actions" ]]; then ok "$CMD_ARGS $BAD 拒绝且无副作用"; else bad "$CMD_ARGS $BAD 执行了命令"; fi
  done
done
for CMD_ARGS in 'init --from-json' 'stop extra' 'logs web extra'; do
  OUT="$(cd "$TMP/args" && PATH="$TMP/args/bin:$PATH" "$LT" $CMD_ARGS 2>&1)"; RC=$?
  check "$CMD_ARGS 拒绝无效参数" "$RC" "1"
done

echo
echo "=== 1. doctor ==="
lt_in "$TMP/main" doctor; check "doctor 退出码" "$?" "0"

echo
echo "=== 2. 主 checkout start ==="
lt_in "$TMP/main" start; check "main start 退出码" "$?" "0"
MAIN_PORT="$(lt_in "$TMP/main" status | awk -F= '/^LT_PORT_WEB=/{print $2}')"
check "main 端口为基准端口" "$MAIN_PORT" "47710"
check "main HTTP" "$(http_code "$MAIN_PORT")" "200"
check "main namespace 为空" "$(lt_in "$TMP/main" status | awk -F= '/^LT_NAMESPACE=/{print $2}')" ""
check "main 执行 seed" "$(cat "$SEEDLOG")" "seeded:"
check "main 执行重建验证" "$(cat "$VERIFYLOG")" "verified:"

echo
echo "=== 3. worktree 并行 start ==="
lt_in "$TMP/wt-alpha" start; check "alpha start 退出码" "$?" "0"
ALPHA_PORT="$(lt_in "$TMP/wt-alpha" status | awk -F= '/^LT_PORT_WEB=/{print $2}')"
ALPHA_NS="$(lt_in "$TMP/wt-alpha" status | awk -F= '/^LT_NAMESPACE=/{print $2}')"
check "alpha namespace" "$ALPHA_NS" "wt_alpha"
if [[ "$ALPHA_PORT" != "$MAIN_PORT" ]]; then ok "alpha 端口与 main 不同 ($ALPHA_PORT vs $MAIN_PORT)"; else bad "alpha 端口与 main 相同"; fi
check "alpha HTTP" "$(http_code "$ALPHA_PORT")" "200"
check "main 仍存活" "$(http_code "$MAIN_PORT")" "200"
check "LT_URL 展开" "$(lt_in "$TMP/wt-alpha" status | awk -F= '/^LT_URL=/{sub(/^LT_URL=/,"");print}')" "http://127.0.0.1:$ALPHA_PORT/"

echo
echo "=== 4. 重复 start 幂等 ==="
OUT="$(lt_in "$TMP/wt-alpha" start 2>&1)"; RC=$?
check "重复 start 退出码" "$RC" "0"
if echo "$OUT" | grep -q "已在运行"; then ok "重复 start 跳过已运行服务"; else bad "重复 start 未跳过: $OUT"; fi
check "重复 start 后端口不变" "$(lt_in "$TMP/wt-alpha" status | awk -F= '/^LT_PORT_WEB=/{print $2}')" "$ALPHA_PORT"

echo
echo "=== 5. 软上限 ==="
OUT="$(LOCAL_TEST_MAX_ENVS=1 lt_in "$TMP/wt-beta" start 2>&1)"; RC=$?
check "软上限拒绝退出码" "$RC" "2"
if echo "$OUT" | grep -q "软上限"; then ok "软上限提示可见"; else bad "无软上限提示: $OUT"; fi

echo
echo "=== 6. external real 校验 ==="
OUT="$(SMOKE_MODE=real lt_in "$TMP/wt-beta" start 2>&1)"; RC=$?
check "worktree real 被拒" "$RC" "2"
if echo "$OUT" | grep -q "只允许在主 checkout"; then ok "real 拒绝原因可见"; else bad "无 real 拒绝提示: $OUT"; fi
OUT="$(SMOKE_MODE=real lt_in "$TMP/main" status 2>&1)"; RC=$?
check "主 checkout real status 退出码" "$RC" "0"
check "主 checkout real 模式生效" "$(echo "$OUT" | awk -F= '/^LT_EXTERNAL_MODE=/{print $2}')" "real"
check "worktree 默认 mock" "$(lt_in "$TMP/wt-alpha" status | awk -F= '/^LT_EXTERNAL_MODE=/{print $2}')" "mock"

echo
echo "=== 7. stop 释放端口 ==="
lt_in "$TMP/main" stop; check "main stop 退出码" "$?" "0"
sleep 1
if curl -s -o /dev/null -m 2 "http://127.0.0.1:$MAIN_PORT/"; then bad "main 端口仍可访问"; else ok "main 端口已释放"; fi
check "alpha 不受影响" "$(http_code "$ALPHA_PORT")" "200"
if grep -qx 'dropped:' "$DROPLOG"; then ok "stop 回收 main 可重建数据库"; else bad "stop 未回收 main 数据库"; fi

echo
echo "=== 8. 删除 worktree 后 gc ==="
: >"$DROPLOG"
rm -rf "$TMP/wt-alpha"
OUT="$(lt_in "$TMP/main" gc 2>&1)"; RC=$?
check "gc 退出码" "$RC" "0"
if echo "$OUT" | grep -q "worktree 已不存在"; then ok "gc 识别失联 worktree"; else bad "gc 未识别: $OUT"; fi
sleep 1
if curl -s -o /dev/null -m 2 "http://127.0.0.1:$ALPHA_PORT/"; then bad "gc 后 alpha 端口仍可访问"; else ok "gc 已终止 alpha 进程组"; fi
check "gc 执行了 drop" "$(cat "$DROPLOG")" "dropped:wt_alpha"
if [[ -f "$LOCAL_TEST_REGISTRY_DIR/ltsmoke--wt_alpha" ]]; then bad "gc 未删登记"; else ok "gc 已删登记"; fi

echo
echo "=== 9. init 生成配置并确保 ignore ==="
mkdir -p "$TMP/fresh"
cd "$TMP/fresh"
git init -q -b main .
git config user.email smoke@example.com
git config user.name smoke
echo x >f.txt && git add -A && git commit -qm init
cat >"$TMP/scan.json" <<'JSON'
{
  "project": "fresh-app",
  "database": {
    "mode": "rebuildable",
    "prepare": "make db-prepare",
    "seed": "make db-seed",
    "verify": "make db-verify",
    "drop": "make db-drop"
  },
  "external": { "mode_env": "PARTNER_API_MODE" },
  "services": {
    "api": { "port": 8080, "health": "http://127.0.0.1:$LOCAL_TEST_PORT_API/health", "cmd": "node server.js --port $LOCAL_TEST_PORT_API" },
    "css": { "cmd": "npm run watch:css" }
  },
  "preview_url": "http://127.0.0.1:$LOCAL_TEST_PORT_API/"
}
JSON
OUT="$("$LT" init --from-json "$TMP/scan.json" 2>&1)"; RC=$?
check "init 退出码" "$RC" "0"
if [[ -f "$TMP/fresh/.local-test.yml" ]]; then ok "init 生成 .local-test.yml"; else bad "未生成配置"; fi
echo "--- 生成的 .local-test.yml ---"; cat "$TMP/fresh/.local-test.yml"; echo "---"
if git check-ignore -q .local-test/; then ok ".local-test 已被 git ignore"; else bad ".local-test 未被 ignore"; fi
OUT="$("$LT" init --from-json "$TMP/scan.json" 2>&1)"; RC=$?
check "重复 init 被拒" "$RC" "1"
OUT="$("$LT" init --force --from-json "$TMP/scan.json" 2>&1)"; RC=$?
check "--force 覆盖" "$RC" "0"
"$LT" doctor >/dev/null 2>&1; check "生成的配置能通过 doctor 解析" "$?" "0"
check "无 port 的服务不产出 LT_PORT" "$("$LT" status 2>/dev/null | grep -c '^LT_PORT_CSS=')" "0"
check "有 port 的服务产出 LT_PORT" "$("$LT" status 2>/dev/null | awk -F= '/^LT_PORT_API=/{print $2}')" "8080"

echo
echo "=== 10. setsid 缺失时的进程组回退 ==="
for MODE in perl monitor; do
  cd "$TMP/main"
  LOCAL_TEST_SPAWN_MODE="$MODE" "$LT" start >/dev/null 2>&1; RC=$?
  check "spawn=$MODE start 退出码" "$RC" "0"
  check "spawn=$MODE HTTP" "$(http_code "$MAIN_PORT")" "200"
  PG="$(cat "$TMP/main/.local-test/run/web.pid")"
  # 进程组组长的 pgid 必须等于自身 pid，否则 stop 会误杀 lt 自己所在的进程组
  check "spawn=$MODE 自成进程组" "$(ps -o pgid= -p "$PG" | tr -d ' ')" "$PG"
  "$LT" stop >/dev/null 2>&1
  check "spawn=$MODE stop 后端口释放" "$(curl -s -o /dev/null -m 2 "http://127.0.0.1:$MAIN_PORT/" && echo up || echo down)" "down"
done

echo
echo "=== 11. 端口、health 与 compose 参数 ==="
mkdir -p "$TMP/docroot"
echo hi >"$TMP/docroot/index.html"
cat >"$TMP/lt-smoke-sleep.sh" <<'SH'
#!/usr/bin/env bash
exec sleep 60
SH
chmod +x "$TMP/lt-smoke-sleep.sh"
cat >"$TMP/lt-smoke-health.py" <<'PY'
import sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer
port, delay, mode = int(sys.argv[1]), float(sys.argv[2]), sys.argv[3]
started = time.time()
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        ready = mode == "flip" and (time.time() - started) >= delay
        self.send_response(200 if ready else 503)
        self.end_headers()
    def log_message(self, *args):
        pass
HTTPServer(("127.0.0.1", port), H).serve_forever()
PY

make_repo "$TMP/slow-port"
cat >"$TMP/slow-port/.local-test.yml" <<YML
project: slowport
services:
  web:
    port: 47931
    cmd: sleep 3 && python3 -m http.server \$LOCAL_TEST_PORT_WEB --bind 127.0.0.1 --directory $TMP/docroot
YML
OUT="$(LOCAL_TEST_HEALTH_TIMEOUT=15 lt_in "$TMP/slow-port" start 2>&1)"; RC=$?
check "慢端口 start 退出码" "$RC" "0"
check "start 返回时端口已可访问" "$(once_up http://127.0.0.1:47931/)" "200"
lt_in "$TMP/slow-port" stop >/dev/null 2>&1 || true

make_repo "$TMP/dead-port"
cat >"$TMP/dead-port/.local-test.yml" <<YML
project: deadport
services:
  web:
    port: 47932
    cmd: $TMP/lt-smoke-sleep.sh
YML
OUT="$(LOCAL_TEST_HEALTH_TIMEOUT=2 lt_in "$TMP/dead-port" start 2>&1)"; RC=$?
check "端口从不开启的退出码" "$RC" "3"
if echo "$OUT" | grep -q '.local-test/logs/web.log'; then ok "超时指出日志"; else bad "超时未指出日志: $OUT"; fi
if echo "$OUT" | grep -q '环境已就绪'; then bad "未就绪仍报就绪: $OUT"; else ok "未就绪不报就绪"; fi
lt_in "$TMP/dead-port" stop >/dev/null 2>&1 || true

make_repo "$TMP/health-url"
cat >"$TMP/health-url/.local-test.yml" <<YML
project: healthurl
services:
  api:
    port: 47933
    health: http://127.0.0.1:\$LOCAL_TEST_PORT_API/api/health
    cmd: python3 $TMP/lt-smoke-health.py \$LOCAL_TEST_PORT_API 4 flip
YML
OUT="$(LOCAL_TEST_HEALTH_TIMEOUT=15 lt_in "$TMP/health-url" start 2>&1)"; RC=$?
check "health URL start 退出码" "$RC" "0"
check "start 返回时 health 已是 2xx" "$(once_up http://127.0.0.1:47933/api/health)" "200"
lt_in "$TMP/health-url" stop >/dev/null 2>&1 || true

make_repo "$TMP/health-tcp"
cat >"$TMP/health-tcp/.local-test.yml" <<YML
project: healthtcp
services:
  web:
    health: tcp:47937
    cmd: sleep 3 && python3 -m http.server 47937 --bind 127.0.0.1 --directory $TMP/docroot
YML
OUT="$(LOCAL_TEST_HEALTH_TIMEOUT=15 lt_in "$TMP/health-tcp" start 2>&1)"; RC=$?
check "tcp health start 退出码" "$RC" "0"
check "start 返回时 tcp 端口已开" "$(once_up http://127.0.0.1:47937/)" "200"
lt_in "$TMP/health-tcp" stop >/dev/null 2>&1 || true

make_repo "$TMP/health-fail"
cat >"$TMP/health-fail/.local-test.yml" <<YML
project: healthfail
services:
  web:
    port: 47934
    health: http://127.0.0.1:\$LOCAL_TEST_PORT_WEB/api/health
    cmd: python3 $TMP/lt-smoke-health.py \$LOCAL_TEST_PORT_WEB 999 fail
YML
OUT="$(LOCAL_TEST_HEALTH_TIMEOUT=3 lt_in "$TMP/health-fail" start 2>&1)"; RC=$?
check "health 失败退出码" "$RC" "3"
if echo "$OUT" | grep -q '.local-test/logs/web.log'; then ok "health 失败指出日志"; else bad "health 失败未指出日志: $OUT"; fi
if echo "$OUT" | grep -q '环境已就绪'; then bad "health 失败仍报就绪"; else ok "health 失败不报就绪"; fi
check "health 失败后停掉本次拉起的进程" "$(once_up http://127.0.0.1:47934/api/health)" "000"
lt_in "$TMP/health-fail" stop >/dev/null 2>&1 || true

fake_docker() {
  local dir="$1"
  mkdir -p "$dir/bin"
  cat >"$dir/bin/docker" <<SH
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$TMP/docker-args"
exit 0
SH
  chmod +x "$dir/bin/docker"
  printf 'services: {}\n' >"$dir/compose.yml"
}
lt_path() { local dir="$1"; shift; (cd "$dir" && PATH="$dir/bin:$PATH" "$LT" "$@"); }

make_repo "$TMP/compose-flags"
fake_docker "$TMP/compose-flags"
printf 'X=1\n' >"$TMP/compose-flags/.env.local"
cat >"$TMP/compose-flags/.local-test.yml" <<YML
project: composeflags
middleware: compose.yml
middleware_project: demo-dev
middleware_env_file: .env.local
services:
  web:
    port: 47935
    cmd: python3 -m http.server \$LOCAL_TEST_PORT_WEB --bind 127.0.0.1 --directory $TMP/docroot
YML
rm -f "$TMP/docker-args"
OUT="$(lt_path "$TMP/compose-flags" start 2>&1)"; RC=$?
check "带上项目名与 env 档的 start" "$RC" "0"
if grep -q "health: 'http://127.0.0.1:\$LOCAL_TEST_PORT_API/health'" "$TMP/fresh/.local-test.yml"; then ok "init 写出 health"; else bad "init 未写出 health"; fi
if grep -Fxq 'compose -p demo-dev -f compose.yml --env-file .env.local up -d' "$TMP/docker-args"; then ok "compose up 与项目调用一致"; else bad "compose up 参数不一致: $(cat "$TMP/docker-args" 2>/dev/null)"; fi
rm -f "$TMP/docker-args"
lt_path "$TMP/compose-flags" status >/dev/null 2>&1 || true
if grep -q -- '--env-file .env.local ps' "$TMP/docker-args"; then ok "status 也带 env 档与项目名"; else bad "status 未带 compose 参数: $(cat "$TMP/docker-args" 2>/dev/null)"; fi
rm -f "$TMP/docker-args"
lt_path "$TMP/compose-flags" stop >/dev/null 2>&1 || true
if grep -Fxq 'compose -p demo-dev -f compose.yml --env-file .env.local stop' "$TMP/docker-args"; then ok "stop 也带 env 档与项目名"; else bad "stop 参数不一致: $(cat "$TMP/docker-args" 2>/dev/null)"; fi

make_repo "$TMP/compose-plain"
fake_docker "$TMP/compose-plain"
cat >"$TMP/compose-plain/.local-test.yml" <<YML
project: composeplain
middleware: compose.yml
services:
  web:
    port: 47936
    cmd: python3 -m http.server \$LOCAL_TEST_PORT_WEB --bind 127.0.0.1 --directory $TMP/docroot
YML
rm -f "$TMP/docker-args"
OUT="$(lt_path "$TMP/compose-plain" start 2>&1)"; RC=$?
check "旧配置 start 仍成功" "$RC" "0"
if grep -Fxq 'compose -f compose.yml up -d' "$TMP/docker-args" && ! grep -e '--env-file' -e ' -p ' "$TMP/docker-args"; then ok "未声明时不额外传 -p 与 --env-file"; else bad "旧调用被改变: $(cat "$TMP/docker-args" 2>/dev/null)"; fi
lt_path "$TMP/compose-plain" stop >/dev/null 2>&1 || true

make_repo "$TMP/compose-missing"
fake_docker "$TMP/compose-missing"
cat >"$TMP/compose-missing/.local-test.yml" <<YML
project: composemissing
middleware: compose.yml
middleware_env_file: missing.env
services:
  web:
    cmd: $TMP/lt-smoke-sleep.sh
YML
rm -f "$TMP/docker-args"
OUT="$(lt_path "$TMP/compose-missing" start 2>&1)"; RC=$?
check "env 档缺失退出码" "$RC" "2"
if [[ ! -f "$TMP/docker-args" ]]; then ok "env 档缺失时不调用 docker"; else bad "env 档缺失仍调用了 docker: $(cat "$TMP/docker-args")"; fi
if echo "$OUT" | grep -q 'missing.env'; then ok "缺失 env 档的路径可见"; else bad "未指出缺失的 env 档: $OUT"; fi

echo
echo "=== 结果: PASS=$PASS FAIL=$FAIL ==="
[[ $FAIL -eq 0 ]]
