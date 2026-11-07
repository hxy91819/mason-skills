#!/bin/sh
# 幂等初始化应用数据库：角色、数据库、schema、连接上限与 search_path。
# bundled 模式下由 PostgreSQL 官方镜像的 initdb 钩子首次执行，release 时再次执行；
# external 模式下由 `deploy.sh <env> db-init` 在一次性容器里执行。
# 管理员连接参数通过 PGHOST/PGPORT/PGUSER/PGPASSWORD 传入；本地容器使用默认 socket。
set -eu

: "${APP_DB_USER:?缺少 APP_DB_USER}"
: "${APP_DB_PASSWORD:?缺少 APP_DB_PASSWORD}"
: "${APP_DB_NAME:?缺少 APP_DB_NAME}"
: "${APP_DB_SCHEMA:?缺少 APP_DB_SCHEMA}"
connection_limit="${APP_DB_CONNECTION_LIMIT:-10}"
case "$connection_limit" in
  ''|*[!0-9]*)
    echo "APP_DB_CONNECTION_LIMIT 必须是正整数" >&2
    exit 1
    ;;
esac
admin_user="${PGUSER:-${POSTGRES_USER:-postgres}}"

# 角色和数据库必须分开判断：CREATE DATABASE 不能出现在事务或 DO 块里，用 psql 的 \gexec。
psql -v ON_ERROR_STOP=1 -U "$admin_user" -d postgres \
  -v app_user="$APP_DB_USER" \
  -v app_password="$APP_DB_PASSWORD" \
  -v app_db="$APP_DB_NAME" \
  -v conn_limit="$connection_limit" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user')
\gexec
ALTER ROLE :"app_user" WITH LOGIN PASSWORD :'app_password' CONNECTION LIMIT :conn_limit;
SELECT format('CREATE DATABASE %I OWNER %I', :'app_db', :'app_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'app_db')
\gexec
SQL

# schema 必须由应用角色拥有，迁移工具才能在其中建表。
psql -v ON_ERROR_STOP=1 -U "$admin_user" -d "$APP_DB_NAME" \
  -v app_user="$APP_DB_USER" \
  -v app_db="$APP_DB_NAME" \
  -v app_schema="$APP_DB_SCHEMA" <<'SQL'
CREATE SCHEMA IF NOT EXISTS :"app_schema" AUTHORIZATION :"app_user";
ALTER ROLE :"app_user" IN DATABASE :"app_db" SET search_path TO :"app_schema";
SQL

echo "数据库初始化完成：角色 $APP_DB_USER，数据库 $APP_DB_NAME，schema $APP_DB_SCHEMA。"
