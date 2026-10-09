#!/usr/bin/env bash
# Run gog (Google Workspace CLI) with a fresh access token minted from an rclone Drive remote,
# so gog shares rclone's OAuth client/refresh token and needs no separate login or keyring.
#   scripts/gog.sh sheets get <id> 'Sheet1!A1:D10' -j
# Remote: GOG_RCLONE_REMOTE (default gdrive-rw, the full-access remote).
set -euo pipefail
REMOTE=${GOG_RCLONE_REMOTE:-gdrive-rw}
command -v gog >/dev/null || { echo "未安装 gog（https://github.com/openclaw/gogcli/releases）" >&2; exit 127; }
GOG_ACCESS_TOKEN=$(rclone config dump | python3 -c '
import json, sys, urllib.parse, urllib.request
c = json.load(sys.stdin).get(sys.argv[1]) or sys.exit(f"rclone 远端 {sys.argv[1]} 不存在")
body = urllib.parse.urlencode({
    "client_id": c["client_id"], "client_secret": c["client_secret"],
    "refresh_token": json.loads(c["token"])["refresh_token"], "grant_type": "refresh_token"}).encode()
print(json.load(urllib.request.urlopen("https://oauth2.googleapis.com/token", body, timeout=30))["access_token"])
' "$REMOTE")
export GOG_ACCESS_TOKEN
exec gog "$@"
