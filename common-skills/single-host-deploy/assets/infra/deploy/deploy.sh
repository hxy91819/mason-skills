#!/usr/bin/env bash
# 部署入口：从本机经 SSH 管理目标主机，一条命令完成主机初始化、发布、回滚、
# 状态、备份与外部数据库初始化。真实凭据只放在未跟踪的 <env>.secrets.local.env。
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$DEPLOY_DIR/../.." && pwd)"
ENV_DIR="$DEPLOY_DIR/environments"
CONFIG_TOOL="$DEPLOY_DIR/deploy_config.py"
TMP_DIR=""
INVENTORY_JSON=""
VARS_JSON=""
PRIVATE_ENV=""
SSH_COMMON_ARGS=()

cleanup() {
  if [[ -n "$TMP_DIR" && -d "$TMP_DIR" ]]; then
    rm -rf -- "$TMP_DIR"
  fi
}
trap cleanup EXIT

die() {
  printf '错误：%s\n' "$*" >&2
  exit 1
}

info() {
  printf '==> %s\n' "$*" >&2
}

usage() {
  cat <<'EOF'
用法: infra/deploy/deploy.sh <环境> <动作> [参数]

环境:
  example              只用于 syntax-check / lint
  <env>                读取 environments/<env>.local.yml 与 <env>.secrets.local.env

动作:
  bootstrap            主机初始化（Docker、部署账号/目录、UFW、备份 timer），可重复执行
  release              从干净工作区的当前提交构建并发布 API/Web，等待健康并冒烟
  rollback [记录]      切回上一份 release 记录，或指定 releases/<记录>.json
  status               查看当前 release、容器健康、备份 timer 与最近备份
  backup-now           立即执行一次数据库备份（走 systemd service）
  db-init              仅 external 数据库：幂等创建角色/库/schema、连接上限与 search_path
  check                对 bootstrap 执行 --check --diff（只读，不产生变更）
  syntax-check         对所有 playbook 执行 ansible-playbook --syntax-check
  lint                 执行 ansible-lint

首次使用见 README.md 与 docs/agent-guides/deployment.md（如果项目有）。
EOF
}

[[ $# -ge 1 ]] || { usage; exit 1; }
ENV_NAME="$1"
ACTION="${2:-help}"
shift 2 || true

if [[ "$ACTION" == "help" || "$ACTION" == "--help" || "$ACTION" == "-h" ]]; then
  usage
  exit 0
fi

if [[ "$ENV_NAME" == "example" ]]; then
  MANIFEST="$ENV_DIR/example.yml"
  SECRETS="$ENV_DIR/example.secrets.env"
else
  MANIFEST="$ENV_DIR/$ENV_NAME.local.yml"
  SECRETS="$ENV_DIR/$ENV_NAME.secrets.local.env"
fi

case "$ACTION" in
  bootstrap|release|rollback|status|backup-now|db-init|check|syntax-check|lint) ;;
  *)
    usage
    die "未知动作：$ACTION"
    ;;
esac

if [[ "$ENV_NAME" == "example" && "$ACTION" != "syntax-check" && "$ACTION" != "lint" ]]; then
  die "example 清单只用于静态检查；请复制为 <env>.local.yml 后使用真实环境。"
fi

[[ -f "$MANIFEST" ]] || die "找不到环境清单 $MANIFEST；请从 environments/example.yml 复制并填写。"

new_tmp() {
  if [[ -z "$TMP_DIR" ]]; then
    TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/deploy.XXXXXX")"
    chmod 700 "$TMP_DIR"
  fi
}

ensure_ansible() {
  command -v ansible-playbook >/dev/null 2>&1 \
    || die "未找到 ansible-playbook。按 README.md 安装并固定版本。"
  command -v ansible-inventory >/dev/null 2>&1 \
    || die "未找到 ansible-inventory；ansible-core 安装不完整。"
}

ensure_docker() {
  command -v docker >/dev/null 2>&1 || die "未找到 docker 命令。"
}

ensure_buildx() {
  docker buildx version >/dev/null 2>&1 || die "未找到 docker buildx，请安装 Buildx 插件。"
}

load_inventory() {
  ensure_ansible
  new_tmp
  INVENTORY_JSON="$TMP_DIR/inventory.json"
  ansible-inventory -i "$MANIFEST" --list > "$INVENTORY_JSON"
}

get() {
  local path="$1"
  local default="${2-}"
  if [[ $# -ge 2 ]]; then
    python3 "$CONFIG_TOOL" get --inventory-json "$INVENTORY_JSON" --path "$path" --default "$default"
  else
    python3 "$CONFIG_TOOL" get --inventory-json "$INVENTORY_JSON" --path "$path"
  fi
}

load_ssh() {
  SSH_HOST="$(get _meta.hostvars.target.ansible_host)"
  SSH_PORT="$(get _meta.hostvars.target.ansible_port 22)"
  SSH_USER="$(get _meta.hostvars.target.ansible_user)"
  SSH_KEY="$(get _meta.hostvars.target.ansible_ssh_private_key_file)"
  SSH_KEY="${SSH_KEY/#\~/$HOME}"
  local common
  common="$(get _meta.hostvars.target.ansible_ssh_common_args '')"
  SSH_COMMON_ARGS=()
  if [[ -n "$common" ]]; then
    read -r -a SSH_COMMON_ARGS <<< "$common"
  fi
  SSH_TARGET="$SSH_USER@$SSH_HOST"
}

ssh_run() {
  ssh -p "$SSH_PORT" -i "$SSH_KEY" "${SSH_COMMON_ARGS[@]}" "$SSH_TARGET" "$@"
}

run_playbook() {
  local playbook="$1"
  shift
  (cd "$DEPLOY_DIR" && ansible-playbook -i "$MANIFEST" "playbooks/$playbook" "$@")
}

prepare_secrets() {
  local action="$1"
  local api_image="${2-}"
  local web_image="${3-}"
  new_tmp
  VARS_JSON="$TMP_DIR/vars.json"
  local -a args=(
    prepare
    --inventory-json "$INVENTORY_JSON"
    --secrets-file "$SECRETS"
    --action "$action"
    --vars-output "$VARS_JSON"
  )
  if [[ "$action" == "release" || "$action" == "rollback" ]]; then
    PRIVATE_ENV="$TMP_DIR/private.env"
    args+=(--api-image "$api_image" --web-image "$web_image" --private-env-output "$PRIVATE_ENV")
  fi
  python3 "$CONFIG_TOOL" "${args[@]}"
}

clean_worktree_or_die() {
  local dirty
  dirty="$(git -C "$REPO_ROOT" status --porcelain --untracked-files=normal)"
  if [[ -n "$dirty" ]]; then
    printf '%s\n' "$dirty" >&2
    die "工作区不干净：只允许从干净工作区的提交发布。"
  fi
}

build_image() {
  local tag="$1"
  local dockerfile="$2"
  local platform="$3"
  info "构建 $tag（$platform）"
  docker buildx build \
    --platform "$platform" \
    --load \
    --tag "$tag" \
    --file "$REPO_ROOT/$dockerfile" \
    "$REPO_ROOT"
}

do_bootstrap() {
  ensure_ansible
  load_inventory
  run_playbook bootstrap.yml
}

do_check() {
  ensure_ansible
  load_inventory
  info "只读检查：--check --diff，不会产生变更"
  run_playbook bootstrap.yml --check --diff
}

do_release() {
  ensure_ansible
  ensure_docker
  ensure_buildx
  load_inventory
  load_ssh
  clean_worktree_or_die

  local sha short platform api_repo web_repo api_dockerfile web_dockerfile
  local api_image web_image api_id web_id timestamp
  sha="$(git -C "$REPO_ROOT" rev-parse HEAD)"
  short="$(git -C "$REPO_ROOT" rev-parse --short=12 HEAD)"
  platform="$(get _meta.hostvars.target.images.platform)"
  api_repo="$(get _meta.hostvars.target.images.api_repository)"
  web_repo="$(get _meta.hostvars.target.images.web_repository)"
  api_dockerfile="$(get _meta.hostvars.target.images.api_dockerfile)"
  web_dockerfile="$(get _meta.hostvars.target.images.web_dockerfile)"
  api_image="$api_repo:$short"
  web_image="$web_repo:$short"
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"

  info "发布提交 $sha（$short）"
  prepare_secrets release "$api_image" "$web_image"
  build_image "$api_image" "$api_dockerfile" "$platform"
  build_image "$web_image" "$web_dockerfile" "$platform"
  api_id="$(docker image inspect --format '{{.Id}}' "$api_image")"
  web_id="$(docker image inspect --format '{{.Id}}' "$web_image")"

  info "传输镜像到 $SSH_TARGET"
  docker save "$api_image" "$web_image" | ssh_run 'docker load'

  run_playbook release.yml \
    -e "release_action=release" \
    -e "release_sha=$sha" \
    -e "release_short_sha=$short" \
    -e "release_timestamp=$timestamp" \
    -e "release_api_image=$api_image" \
    -e "release_web_image=$web_image" \
    -e "release_api_image_id=$api_id" \
    -e "release_web_image_id=$web_id" \
    -e "private_env_file=$PRIVATE_ENV" \
    -e "repo_root=$REPO_ROOT" \
    -e "@$VARS_JSON"
}

do_rollback() {
  ensure_ansible
  load_inventory
  load_ssh
  new_tmp

  local deploy_root current target record_file api_image web_image sha short timestamp
  local -a fields=()
  deploy_root="$(get _meta.hostvars.target.deploy_root)"
  current="$(ssh_run "readlink '$deploy_root/current' 2>/dev/null || true")"
  current="${current#"$deploy_root"/}"
  [[ -n "$current" ]] || die "主机上没有 current release 记录，无法回滚。"

  target="${1-}"
  target="${target#"$deploy_root"/}"
  target="${target%.ok}"
  if [[ -n "$target" ]]; then
    [[ "$target" == releases/* ]] || target="releases/$target"
  else
    local -a records=()
    mapfile -t records < <(ssh_run "cd '$deploy_root' && ls -1 releases/*.json.ok 2>/dev/null | sed 's/\\.ok$//' | sort")
    local previous=""
    local item
    for item in "${records[@]}"; do
      [[ "$item" == "$current" ]] && break
      previous="$item"
    done
    [[ -n "$previous" ]] || die "找不到 $current 之前的 release 记录；可显式指定 releases/<记录>.json。"
    target="$previous"
  fi

  record_file="$TMP_DIR/record.json"
  ssh_run "cat '$deploy_root/$target'" > "$record_file"
  mapfile -t fields < <(python3 - "$record_file" <<'PY'
import json
import sys

with open(sys.argv[1], encoding='utf-8') as stream:
    record = json.load(stream)
for key in ('api_image', 'web_image', 'sha', 'short_sha'):
    print(record.get(key, ''))
PY
)
  api_image="${fields[0]:-}"
  web_image="${fields[1]:-}"
  sha="${fields[2]:-}"
  short="${fields[3]:-}"
  [[ -n "$api_image" && -n "$web_image" && -n "$sha" ]] || die "目标 release 记录缺少镜像或提交信息。"

  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  info "回滚到 $target（$short）"
  prepare_secrets rollback "$api_image" "$web_image"
  run_playbook release.yml \
    -e "release_action=rollback" \
    -e "release_sha=$sha" \
    -e "release_short_sha=$short" \
    -e "release_timestamp=$timestamp" \
    -e "release_api_image=$api_image" \
    -e "release_web_image=$web_image" \
    -e "release_api_image_id=" \
    -e "release_web_image_id=" \
    -e "rollback_from_record=$current" \
    -e "rollback_to_record=$target" \
    -e "private_env_file=$PRIVATE_ENV" \
    -e "repo_root=$REPO_ROOT" \
    -e "@$VARS_JSON"
}

do_db_init() {
  ensure_ansible
  load_inventory
  prepare_secrets db-init
  run_playbook db-init.yml -e "@$VARS_JSON"
}

do_status() {
  ensure_ansible
  load_inventory
  run_playbook status.yml
}

do_backup_now() {
  ensure_ansible
  load_inventory
  run_playbook backup-now.yml
}

do_syntax_check() {
  ensure_ansible
  local playbook
  for playbook in "$DEPLOY_DIR"/playbooks/*.yml; do
    info "syntax-check $(basename "$playbook")"
    (cd "$DEPLOY_DIR" && ansible-playbook -i environments/example.yml --syntax-check "$playbook")
  done
}

do_lint() {
  command -v ansible-lint >/dev/null 2>&1 || die "未找到 ansible-lint；可用 uv tool install ansible-lint 安装。"
  (cd "$DEPLOY_DIR" && ansible-lint)
}

case "$ACTION" in
  bootstrap) do_bootstrap ;;
  check) do_check ;;
  release) do_release ;;
  rollback) do_rollback "${1-}" ;;
  db-init) do_db_init ;;
  status) do_status ;;
  backup-now) do_backup_now ;;
  syntax-check) do_syntax_check ;;
  lint) do_lint ;;
esac
