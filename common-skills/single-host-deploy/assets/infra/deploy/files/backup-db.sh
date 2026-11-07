#!/usr/bin/env bash
# 只备份本项目自己的数据库；不停止、恢复或清理共用实例中的其他数据库。
# 默认保留 14 天；可选地用 rclone 复制到异地，未配置时跳过。
set -euo pipefail
umask 077
db_container="${BACKUP_DB_CONTAINER:?请指定数据库容器}"
db_name="${BACKUP_DB_NAME:?请指定数据库名}"
db_user="${BACKUP_DB_USER:?请指定数据库角色}"
backup_dir="${BACKUP_DIR:?请指定备份目录}"
file_prefix="${BACKUP_FILE_PREFIX:-app}"
retention_days="${BACKUP_RETENTION_DAYS:-14}"
offsite_enabled="${BACKUP_OFFSITE_ENABLED:-false}"
offsite_remote="${BACKUP_OFFSITE_REMOTE:-}"

case "$retention_days" in
  ''|*[!0-9]*|0)
    echo "BACKUP_RETENTION_DAYS 必须是正整数" >&2
    exit 1
    ;;
esac
mkdir -p "$backup_dir"
backup_file="$backup_dir/${file_prefix}-$(date -u +%Y%m%dT%H%M%S)-$$.dump"
partial_file="$backup_file.partial"
trap 'rm -f -- "$partial_file"' EXIT
(set -o noclobber; docker exec "$db_container" pg_dump -U "$db_user" -d "$db_name" --format=custom --no-owner --no-privileges > "$partial_file")
mv -- "$partial_file" "$backup_file"
echo "数据库备份完成：$backup_file"

# 异地副本是可选钩子：默认关闭；启用但缺少配置时明确失败，避免误以为已有异备。
if [[ "$offsite_enabled" == "true" ]]; then
  [[ -n "$offsite_remote" ]] || { echo "已启用异地备份但未配置 BACKUP_OFFSITE_REMOTE" >&2; exit 1; }
  command -v rclone >/dev/null 2>&1 || { echo "已启用异地备份但主机未安装 rclone" >&2; exit 1; }
  if [[ -n "${BACKUP_RCLONE_CONFIG:-}" ]]; then
    export RCLONE_CONFIG="$BACKUP_RCLONE_CONFIG"
  fi
  rclone copy --no-traverse "$backup_file" "$offsite_remote"
  echo "异地副本完成：$offsite_remote"
else
  echo "异地备份未启用，跳过。"
fi

# 只在本次备份成功后清理自己的旧 dump；不触碰目录内其他文件。
find "$backup_dir" -maxdepth 1 -type f -name "${file_prefix}-*.dump" -mtime +"$retention_days" -delete
echo "已清理超过 ${retention_days} 天的本机备份。"
