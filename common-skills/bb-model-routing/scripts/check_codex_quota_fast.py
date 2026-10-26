#!/usr/bin/env python3
"""巡检 Codex 账号剩余额度；若 codex 或 codex-l 任意账号剩余额度 <= 40%，则关闭 Fast。"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("BB_DISPATCH_CONFIG", Path.home() / ".config/bb-dispatch/config.yaml"))
QUOTA_THRESHOLD_PERCENT = 40.0  # 剩余额度阈值百分比


def get_usage():
    try:
        res = subprocess.run(["bb", "settings", "usage", "--json"], capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            return json.loads(res.stdout)
    except Exception:
        pass

    try:
        res = subprocess.run(["bb", "account-limits"], capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            providers = {}
            for m in data.get("bbProviders", {}).get("machines", []):
                for p in m.get("providers", []):
                    providers[p.get("id")] = p.get("usage", {})
            return providers
    except Exception:
        pass
    return {}


def parse_remaining(usage_data, provider_id):
    info = usage_data.get(provider_id, {})
    if info.get("status") != "ok":
        return None, info.get("status", "unknown")
    windows = info.get("windows", [])
    weekly = next((w for w in windows if "weekly" in (w.get("label", "").lower() + w.get("kind", "").lower())), None)
    if not weekly and windows:
        weekly = windows[0]
    if not weekly:
        return None, "no_window"
    used = weekly.get("usedPercent")
    if used is None:
        return None, "no_used_percent"
    remaining = 100.0 - float(used)
    resets_at = weekly.get("resetsAt")
    return {"used_percent": float(used), "remaining_percent": remaining, "resets_at": resets_at}, "ok"


def check_and_fuse(config_path=CONFIG_PATH, dry_run=False):
    usage_data = get_usage()
    codex_stat, codex_err = parse_remaining(usage_data, "codex")
    codexl_stat, codexl_err = parse_remaining(usage_data, "codex-l")

    fast_active = None
    content = ""
    if config_path.exists():
        content = config_path.read_text(encoding="utf-8")
        m = re.search(r"^\s*fast:\s*(true|false)", content, re.MULTILINE)
        if m:
            fast_active = (m.group(1).lower() == "true")

    fuse_triggered = False
    reasons = []

    for name, stat, err in [("codex (主号)", codex_stat, codex_err), ("codex-l (L号)", codexl_stat, codexl_err)]:
        if stat is not None:
            rem = stat["remaining_percent"]
            if rem <= QUOTA_THRESHOLD_PERCENT:
                fuse_triggered = True
                reasons.append(f"{name} 剩余额度仅剩 {rem:.1f}% (<= {QUOTA_THRESHOLD_PERCENT}%)")

    action_taken = "none"
    if fuse_triggered:
        if fast_active is True:
            if not dry_run:
                new_content = re.sub(r"^\s*fast:\s*true", "fast: false", content, flags=re.MULTILINE)
                config_path.write_text(new_content, encoding="utf-8")
            action_taken = "fused_closed_fast"
        else:
            action_taken = "already_closed"
    else:
        action_taken = "kept_current"

    return {
        "action": action_taken,
        "fuse_triggered": fuse_triggered,
        "fast_active_before": fast_active,
        "reasons": reasons,
        "accounts": {
            "codex": codex_stat or {"error": codex_err},
            "codex-l": codexl_stat or {"error": codexl_err},
        }
    }


def main():
    dry_run = "--dry-run" in sys.argv
    result = check_and_fuse(dry_run=dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["action"] == "fused_closed_fast":
        print(f"⚠️ 触发额度熔断：{'; '.join(result['reasons'])}，已自动关闭 Fast！")
    elif result["fuse_triggered"]:
        print("⚠️ 额度低于阈值，但 Fast 当前已处于关闭状态。")
    else:
        print("✅ Codex 额度充足（均 > 40%），巡检正常。")


if __name__ == "__main__":
    main()
