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
PASS=0; FAIL=0

ok()   { PASS=$((PASS + 1)); echo "PASS: $*"; }
bad()  { FAIL=$((FAIL + 1)); echo "FAIL: $*"; }
check(){ if [[ "$2" == "$3" ]]; then ok "$1 ($2)"; else bad "$1: 期望 [$3] 实得 [$2]"; fi; }

cleanup() {
  for d in "$TMP/main" "$TMP/wt-alpha" "$TMP/wt-beta"; do
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

echo "=== 准备临时仓库 $TMP ==="
mkdir -p "$TMP/main"
cd "$TMP/main"
git init -q -b main .
git config user.email smoke@example.com
git config user.name smoke
cat >.local-test.yml <<YML
project: ltsmoke
database:
  prepare: echo prepared:\$LOCAL_TEST_NAMESPACE >> $TMP/prepare.log
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
echo "=== 1. doctor ==="
lt_in "$TMP/main" doctor; check "doctor 退出码" "$?" "0"

echo
echo "=== 2. 主 checkout start ==="
lt_in "$TMP/main" start; check "main start 退出码" "$?" "0"
MAIN_PORT="$(lt_in "$TMP/main" status | awk -F= '/^LT_PORT_WEB=/{print $2}')"
check "main 端口为基准端口" "$MAIN_PORT" "47710"
check "main HTTP" "$(http_code "$MAIN_PORT")" "200"
check "main namespace 为空" "$(lt_in "$TMP/main" status | awk -F= '/^LT_NAMESPACE=/{print $2}')" ""

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
  "database": { "prepare": "make db-prepare", "drop": "make db-drop" },
  "external": { "mode_env": "PARTNER_API_MODE" },
  "services": {
    "api": { "port": 8080, "cmd": "node server.js --port $LOCAL_TEST_PORT_API" },
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
echo "=== 结果: PASS=$PASS FAIL=$FAIL ==="
[[ $FAIL -eq 0 ]]
