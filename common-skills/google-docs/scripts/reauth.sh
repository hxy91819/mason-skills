#!/usr/bin/env bash
# Authorize an rclone Drive remote on a headless box.
# Remote: GDOC_RCLONE_REMOTE (default gdrive). Scope: GDRIVE_SCOPE, comma-separated short names
# (default drive.readonly; full access: drive,documents,spreadsheets).
#   reauth.sh start            -> prints the Google consent URL to send to the user
#   reauth.sh finish '<url>'   -> takes the http://127.0.0.1:53682/?...code=... URL, saves token, verifies
# OAuth client: GDRIVE_CLIENT_ID / GDRIVE_CLIENT_SECRET, else the existing remote's client_id / client_secret.
set -euo pipefail
REMOTE=${GDOC_RCLONE_REMOTE:-gdrive}
SCOPE=${GDRIVE_SCOPE:-drive.readonly}
LOG=${TMPDIR:-/tmp}/rclone-auth-$REMOTE.log

conf() { rclone config show "$REMOTE" 2>/dev/null | sed -n "s/^$1 = //p"; }
CID=${GDRIVE_CLIENT_ID:-$(conf client_id)}
CSECRET=${GDRIVE_CLIENT_SECRET:-$(conf client_secret)}
[ -n "$CID" ] && [ -n "$CSECRET" ] || { echo "缺少 OAuth client：设置 GDRIVE_CLIENT_ID / GDRIVE_CLIENT_SECRET" >&2; exit 2; }

case "${1:-}" in
start)
  B=$(printf '{"scope":"%s","client_id":"%s","client_secret":"%s"}' "$SCOPE" "$CID" "$CSECRET" | base64 | tr -d '\n=' | tr '+/' '-_')
  nohup rclone authorize drive "$B" --auth-no-open-browser > "$LOG" 2>&1 &
  L=
  for _ in $(seq 20); do L=$(grep -o 'http://127.0.0.1:53682/auth?state=[^ ]*' "$LOG" || true); [ -n "$L" ] && break; sleep 0.5; done
  [ -n "$L" ] || { echo "rclone authorize 未启动，见 $LOG" >&2; exit 1; }
  curl -s -o /dev/null -w '%{redirect_url}\n' "$L"
  ;;
finish)
  curl -s "${2:?缺少回调地址}" > /dev/null
  for _ in $(seq 60); do grep -q 'End paste' "$LOG" 2>/dev/null && break; sleep 1; done
  B=$(grep -A1 'Paste the following' "$LOG" | tail -1)
  TOKEN=$(python3 -c 'import sys,base64,json;s=sys.argv[1];s+="="*(-len(s)%4);print(json.loads(base64.urlsafe_b64decode(s))["token"])' "$B" 2>/dev/null || true)
  [ -n "$TOKEN" ] || { echo "没拿到 token（日志保留在 $LOG），配置未改动" >&2; exit 1; }
  if rclone listremotes | grep -qx "$REMOTE:"; then
    rclone config update "$REMOTE" scope="$SCOPE" client_id="$CID" client_secret="$CSECRET" token="$TOKEN" config_refresh_token=false --non-interactive > /dev/null
  else
    rclone config create "$REMOTE" drive scope="$SCOPE" client_id="$CID" client_secret="$CSECRET" token="$TOKEN" config_refresh_token=false --non-interactive > /dev/null
  fi
  chmod 600 "$(rclone config file | tail -1)"
  rm -f "$LOG"
  T=$(rclone config dump | python3 -c 'import json,sys;print(json.loads(json.load(sys.stdin)[sys.argv[1]]["token"])["access_token"])' "$REMOTE")
  curl -s -H "Authorization: Bearer $T" 'https://www.googleapis.com/drive/v3/about?fields=user(emailAddress)' | python3 -c 'import json,sys;print("已授权账号:",json.load(sys.stdin)["user"]["emailAddress"])'
  ;;
*) echo "用法: $0 start | finish '<回调地址>'" >&2; exit 2 ;;
esac
