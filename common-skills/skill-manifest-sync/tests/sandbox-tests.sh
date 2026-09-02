#!/usr/bin/env bash
# skill-manifest-sync 的 Docker 沙箱测试：在干净容器内验证清单同步的完整生命周期。
# 运行方式（宿主）：docker build 后 docker run，见同级 run-sandbox.sh。
set -uo pipefail

SCRIPT=/work/repo/common-skills/skill-manifest-sync/scripts/sync_skill_symlinks.py
SKILLS=/root/.agents/skills
MANIFEST=/work/repo/config/skill-symlinks.yaml
PASS=0
FAIL=0

assert_ok() { # assert_ok <描述> <命令...>
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "PASS: $desc"; PASS=$((PASS+1)); else echo "FAIL: $desc"; FAIL=$((FAIL+1)); fi
}
assert_fail() { # 期望命令非零退出
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "FAIL: $desc (expected nonzero exit)"; FAIL=$((FAIL+1)); else echo "PASS: $desc"; PASS=$((PASS+1)); fi
}
assert_out() { # 期望 stdout 匹配 grep 模式；先捕获输出再 grep，避免 pipefail 把被测命令的非零退出传染给断言
  local desc="$1" pattern="$2" out rc=0; shift 2
  out=$("$@" 2>/dev/null) || rc=$?
  if printf '%s\n' "$out" | grep -q "$pattern"; then echo "PASS: $desc"; PASS=$((PASS+1)); else echo "FAIL: $desc (pattern not found: $pattern; rc=$rc)"; FAIL=$((FAIL+1)); fi
}

echo "=== 场景 1: 全新电脑（无 user scope），apply --yes 一次到位 ==="
rm -rf /root/.agents
apply_out=$(python3 "$SCRIPT" --mode apply --yes); rc=$?
assert_ok "apply 在空机器上退出 0" test "$rc" -eq 0
count=$(find "$SKILLS" -type l | wc -l)
assert_ok "创建了 16 个软链（15 清单项 + skill-manifest-sync）" test "$count" -eq 16
assert_ok "ask-oracle 链接指向容器内仓库" test "$(readlink "$SKILLS/ask-oracle")" = "/work/repo/common-skills/ask-oracle"
assert_ok "链接目标真实存在且含 SKILL.md" test -f "$SKILLS/autoreview/SKILL.md"

echo "=== 场景 2: check 无漂移 ==="
assert_ok "check 退出 0" python3 "$SCRIPT" --mode check

echo "=== 场景 3: extra 检测与 --yes 删除 ==="
ln -s /work/repo/common-skills/secure-release "$SKILLS/secure-release"
assert_fail "check 发现 extra 后退出 1" python3 "$SCRIPT" --mode check
assert_out "check 报告 secure-release 为 extra" "extra" python3 "$SCRIPT" --mode check
python3 "$SCRIPT" --mode apply --yes >/dev/null
assert_ok "apply --yes 删除了 extra 链接" test ! -e "$SKILLS/secure-release"
assert_ok "删除后 check 恢复干净" python3 "$SCRIPT" --mode check

echo "=== 场景 4: 交互保留 -> 白名单，后续不再提示 ==="
ln -s /work/repo/common-skills/secure-release "$SKILLS/secure-release"
printf 'k\n' | python3 "$SCRIPT" --mode apply >/dev/null
assert_ok "白名单文件已写入" test -s /root/.agents/skill-sync-whitelist.yaml
assert_out "白名单记录了 secure-release" "secure-release" cat /root/.agents/skill-sync-whitelist.yaml
assert_ok "白名单生效：check 退出 0" python3 "$SCRIPT" --mode check
assert_ok "白名单条目链接仍在（未被删除）" test -e "$SKILLS/secure-release"

echo "=== 场景 5: conflict 保护——真实目录占用绝不删除 ==="
rm "$SKILLS/what-changed"
mkdir -p "$SKILLS/what-changed" && echo "user data" > "$SKILLS/what-changed/local.txt"
assert_out "apply 报告 conflict" "\[conflict\] what-changed" python3 "$SCRIPT" --mode apply --yes
assert_ok "真实目录未被触碰" test -f "$SKILLS/what-changed/local.txt"
assert_fail "存在未解决 conflict 时 apply 退出 1" python3 "$SCRIPT" --mode apply --yes
rm -rf "$SKILLS/what-changed"

echo "=== 场景 6: fix——指向仓库内错误位置的软链被修复 ==="
ln -s /work/repo/common-skills/use-worktree "$SKILLS/what-changed"
python3 "$SCRIPT" --mode apply --yes >/dev/null
assert_ok "what-changed 被修复为正确目标" test "$(readlink "$SKILLS/what-changed")" = "/work/repo/common-skills/what-changed"

echo "=== 场景 7: 第三方中转链接不算 extra（管理边界）==="
mkdir -p /opt/other-workspace/.agents/skills
cp -r /work/repo/common-skills/secure-release /opt/other-workspace/.agents/skills/secure-release
ln -s /opt/other-workspace/.agents/skills/secure-release "$SKILLS/chained-skill"
assert_ok "穿透其他工作区的链接不被提示" python3 "$SCRIPT" --mode check
rm "$SKILLS/chained-skill"

echo "=== 场景 8: stale manifest 条目只报告不动手 ==="
cp "$MANIFEST" /tmp/manifest-bak.yaml
python3 - <<'EOF'
from pathlib import Path
p = Path("/work/repo/config/skill-symlinks.yaml")
p.write_text(p.read_text() + "- name: ghost-skill\n  note: 不存在的条目\n", encoding="utf-8")
EOF
assert_out "check 报告 stale" "\[stale\] ghost-skill" python3 "$SCRIPT" --mode check
assert_fail "stale 使 check 退出 1" python3 "$SCRIPT" --mode check
cp /tmp/manifest-bak.yaml "$MANIFEST"

echo "=== 场景 9: register / remove 维护清单 ==="
rm -f /root/.agents/skill-sync-whitelist.yaml   # 隔离场景 4 写入的本机白名单
python3 "$SCRIPT" --mode register --skill secure-release --note "测试登记" >/dev/null
assert_out "register 后清单含条目" "secure-release" cat "$MANIFEST"
assert_out "register 后 check 报 ok（场景 4 已保留链接）" "\[ok\] secure-release" python3 "$SCRIPT" --mode check
python3 "$SCRIPT" --mode remove --skill secure-release >/dev/null
rm "$SKILLS/secure-release"   # 清掉场景 4 保留的链接，恢复未链接基线
assert_ok "remove 后清单恢复" bash -c '! grep -q "secure-release" "$MANIFEST"'
# register 对不存在的 skill 保守失败
assert_fail "register 不存在的 skill 退出非零" python3 "$SCRIPT" --mode register --skill no-such-thing

echo "=== 场景 10: 危险操作边界与用法错误 ==="
assert_ok "--help 正常输出" bash -c "python3 $SCRIPT --help | grep -qi 'usage'"
assert_ok "--help 含输出定义与范例" bash -c "python3 $SCRIPT --help | grep -q '输出结果定义'"
assert_fail "非法 --mode 退出 2" python3 "$SCRIPT" --mode bogus
assert_fail "register 缺 --skill 退出 2" python3 "$SCRIPT" --mode register

echo
echo "结果：PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]