#!/usr/bin/env bash
set -euo pipefail

# 定义：将共享工作区 Git wrapper 以软链安装到 PATH 目录。
# 参数：--target-dir 指定安装目录，--force 先备份冲突目标，--dry-run 只显示计划。
# 输出：成功时显示软链及源路径；冲突时保守失败，不覆盖现有文件。
# 决策：使用绝对软链，确保从任意工作目录调用时都指向同一份维护源。

usage() {
  cat <<'EOF'
Usage:
  install.sh [options]

Description:
  Installs the repository-maintained Git workspace guard as an absolute
  symbolic link named "git". The default target is ~/.local/bin/git.

Options:
  --target-dir <path>  Install into this directory instead of ~/.local/bin.
  --force              Back up a conflicting target, then install the link.
  --dry-run            Print the planned operation without changing files.
  -h, --help           Show this help.

Outputs:
  Success: prints the installed link and its source.
  Conflict: prints an error and exits 73 without replacing the target.
  Invalid arguments: exits 64.

Examples:
  ./install.sh
  ./install.sh --target-dir /usr/local/bin
  ./install.sh --force
EOF
}

log_error() {
  printf 'ERROR: %s\n' "$*" >&2
}

main() {
  local script_dir
  local source_path
  local install_dir=""
  local target_path
  local current_source=""
  local backup_path=""
  local force=0
  local dry_run=0

  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
  source_path="${script_dir}/git"

  while (($#)); do
    case "$1" in
      --target-dir)
        (($# >= 2)) || {
          log_error "--target-dir requires a path."
          return 64
        }
        install_dir="$2"
        shift 2
        ;;
      --force)
        force=1
        shift
        ;;
      --dry-run)
        dry_run=1
        shift
        ;;
      -h|--help)
        usage
        return 0
        ;;
      *)
        log_error "unknown option: $1"
        printf 'Run %s --help for usage.\n' "$0" >&2
        return 64
        ;;
    esac
  done

  if [[ -z "$install_dir" ]]; then
    [[ -n "${HOME:-}" ]] || {
      log_error "HOME is unset; provide --target-dir explicitly."
      return 64
    }
    install_dir="${HOME}/.local/bin"
  fi

  [[ -x "$source_path" ]] || {
    log_error "wrapper source is not executable: ${source_path}"
    return 66
  }
  [[ -n "$install_dir" ]] || {
    log_error "target directory cannot be empty."
    return 64
  }

  target_path="${install_dir%/}/git"
  if [[ -L "$target_path" ]]; then
    current_source="$(readlink -f -- "$target_path")"
    if [[ "$current_source" == "$source_path" ]]; then
      printf 'Already installed: %s -> %s\n' "$target_path" "$source_path"
      return 0
    fi
  fi

  if [[ -e "$target_path" || -L "$target_path" ]]; then
    if ((force == 0)); then
      log_error "target already exists: ${target_path}"
      log_error "use --force to back it up before installing."
      return 73
    fi
    backup_path="${target_path}.backup.$(date '+%Y%m%d%H%M%S')"
  fi

  if ((dry_run == 1)); then
    [[ -n "$backup_path" ]] && printf 'Would move: %s -> %s\n' "$target_path" "$backup_path"
    printf 'Would link: %s -> %s\n' "$target_path" "$source_path"
    return 0
  fi

  mkdir -p -- "$install_dir"
  if [[ -n "$backup_path" ]]; then
    mv -- "$target_path" "$backup_path"
    printf 'Backed up: %s -> %s\n' "$target_path" "$backup_path"
  fi
  ln -s -- "$source_path" "$target_path"
  printf 'Installed: %s -> %s\n' "$target_path" "$source_path"
}

main "$@"
