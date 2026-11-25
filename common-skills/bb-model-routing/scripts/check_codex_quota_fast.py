#!/usr/bin/env python3
"""Check remaining Codex account quota; when an account such as codex or codex-l is at or below the threshold,
turn off Fast for that account.
When every measurable account has Fast off, accounts whose quota cannot be read (such as codex-b) are turned off too.
With force_fast: true (global or per agent), Fast is forced on and exempt from the quota fuse.
quota_fuse in the config can customize the fuse threshold (e.g. only turn off at 95% used) and an automatic
restore time (e.g. restore tomorrow at noon)."""

import argparse
from datetime import datetime, timezone
import json
import os
import re
import subprocess
import sys
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("BB_DISPATCH_CONFIG", Path.home() / ".config/bb-dispatch/config.yaml"))
QUOTA_THRESHOLD_PERCENT = 40.0  # Default remaining-quota threshold in percent (i.e. fuse at 60% used)


def notify_thread(thread_id, message):
    if not thread_id:
        return False
    try:
        res = subprocess.run(["bb", "thread", "tell", thread_id, message], capture_output=True, text=True, timeout=15)
        return res.returncode == 0
    except Exception as exc:
        sys.stderr.write(f"failed to notify thread: {exc}\n")
        return False


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


def load_config(config_path):
    if not config_path.exists():
        return None, ""
    content = config_path.read_text(encoding="utf-8")
    try:
        from ruamel.yaml import YAML
        yaml = YAML()
        yaml.preserve_quotes = True
        data = yaml.load(content)
        return data, content
    except Exception:
        try:
            import yaml
            data = yaml.safe_load(content)
            return data, content
        except Exception:
            return None, content


def resolve_threshold(config_data, now_dt=None):
    default_rem_threshold = QUOTA_THRESHOLD_PERCENT
    default_used_threshold = 100.0 - default_rem_threshold
    if not config_data or not isinstance(config_data, dict):
        return default_rem_threshold, default_used_threshold, None

    fuse_cfg = config_data.get("quota_fuse")
    if not isinstance(fuse_cfg, dict):
        if "max_used_percent" in config_data:
            used_th = float(config_data["max_used_percent"])
            return 100.0 - used_th, used_th, None
        if "quota_threshold_percent" in config_data:
            rem_th = float(config_data["quota_threshold_percent"])
            return rem_th, 100.0 - rem_th, None
        return default_rem_threshold, default_used_threshold, None

    used_th = fuse_cfg.get("used_threshold_percent")
    rem_th = fuse_cfg.get("remaining_threshold_percent")
    if used_th is not None:
        target_rem = 100.0 - float(used_th)
        target_used = float(used_th)
    elif rem_th is not None:
        target_rem = float(rem_th)
        target_used = 100.0 - float(rem_th)
    else:
        target_rem = default_rem_threshold
        target_used = default_used_threshold

    restore_at_str = fuse_cfg.get("restore_at")
    if restore_at_str:
        try:
            restore_dt = datetime.fromisoformat(restore_at_str)
            current_time = now_dt or datetime.now(restore_dt.tzinfo or timezone.utc)
            if current_time >= restore_dt:
                def_used = float(fuse_cfg.get("default_used_threshold_percent", default_used_threshold))
                return 100.0 - def_used, def_used, "restored"
        except Exception:
            pass

    return target_rem, target_used, restore_at_str


def update_config_threshold_restored(config_path):
    try:
        from ruamel.yaml import YAML
        yaml = YAML()
        yaml.preserve_quotes = True
        with open(config_path, "r", encoding="utf-8") as f:
            d = yaml.load(f)
        if d and "quota_fuse" in d:
            d.pop("quota_fuse", None)
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(d, f)
            return True
    except Exception:
        pass
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            d = yaml.safe_load(f)
        if d and "quota_fuse" in d:
            d.pop("quota_fuse", None)
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(d, f, allow_unicode=True, sort_keys=False)
            return True
    except Exception:
        pass
    return False


def update_config_file(config_path, content, fused_agents, global_fallback=False):
    if not global_fallback and fused_agents:
        # Try ruamel.yaml first to preserve formatting and comments
        try:
            from ruamel.yaml import YAML
            yaml = YAML()
            yaml.preserve_quotes = True
            with open(config_path, "r", encoding="utf-8") as f:
                d = yaml.load(f)
            if d and "agents" in d:
                for alias in fused_agents:
                    if alias in d["agents"]:
                        d["agents"][alias]["fast"] = False
                with open(config_path, "w", encoding="utf-8") as f:
                    yaml.dump(d, f)
                return True
        except Exception:
            pass

        # Try standard pyyaml
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                d = yaml.safe_load(f)
            if d and "agents" in d:
                for alias in fused_agents:
                    if alias in d["agents"]:
                        d["agents"][alias]["fast"] = False
                with open(config_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(d, f, allow_unicode=True, sort_keys=False)
                return True
        except Exception:
            pass

    # Fallback to regex global fast replacement
    new_content = re.sub(r"^\s*fast:\s*true", "fast: false", content, flags=re.MULTILINE)
    config_path.write_text(new_content, encoding="utf-8")
    return True


def check_and_fuse(config_path=CONFIG_PATH, dry_run=False, now_dt=None):
    usage_data = get_usage()
    config_data, content = load_config(config_path)

    global_fast = True
    global_force_fast = False
    if config_data and isinstance(config_data, dict):
        if "fast" in config_data:
            global_fast = bool(config_data["fast"])
        global_force_fast = bool(config_data.get("force_fast", False))
    elif content:
        m = re.search(r"^\s*fast:\s*(true|false)", content, re.MULTILINE)
        if m:
            global_fast = (m.group(1).lower() == "true")
        mf = re.search(r"^\s*force_fast:\s*(true|false)", content, re.MULTILINE)
        if mf:
            global_force_fast = (mf.group(1).lower() == "true")

    rem_threshold, used_threshold, threshold_status = resolve_threshold(config_data, now_dt=now_dt)
    threshold_restored = (threshold_status == "restored")
    if threshold_restored and not dry_run:
        update_config_threshold_restored(config_path)

    agents = {}
    if config_data and isinstance(config_data, dict):
        agents = config_data.get("agents") or {}

    provider_to_alias = {}
    for alias, agent_cfg in agents.items():
        if isinstance(agent_cfg, dict):
            p = agent_cfg.get("provider")
            if p:
                provider_to_alias[p] = alias

    monitored = [
        ("codex", "codex (main)"),
        ("codex-l", "codex-l (L account)"),
        ("codex-b", "codex-b (B account)"),
    ]

    accounts_stat = {}
    reasons = []
    fused_agents = []
    fuse_triggered = False

    measurable_count = 0
    measurable_fast_active_count = 0
    unmeasurable_accounts = []

    for provider_id, label in monitored:
        stat, err = parse_remaining(usage_data, provider_id)
        accounts_stat[provider_id] = stat or {"error": err}
        if stat is None:
            unmeasurable_accounts.append((provider_id, label))
            continue

        measurable_count += 1
        rem = stat["remaining_percent"]
        used = stat["used_percent"]
        alias = provider_to_alias.get(provider_id)
        account_force_fast = global_force_fast
        if alias and alias in agents and isinstance(agents[alias], dict):
            if "force_fast" in agents[alias]:
                account_force_fast = bool(agents[alias]["force_fast"])
            current_fast = agents[alias].get("fast", global_fast)
        else:
            current_fast = global_fast

        if rem <= rem_threshold:
            if account_force_fast:
                reasons.append(f"{label} used {used:.1f}% (>= {used_threshold:.1f}%), but force_fast: true is set; exempt from the fuse")
                if current_fast is True:
                    measurable_fast_active_count += 1
            else:
                fuse_triggered = True
                if alias and alias in agents and isinstance(agents[alias], dict):
                    if current_fast is True:
                        fused_agents.append(alias)
                        reasons.append(f"{label} used {used:.1f}% (>= {used_threshold:.1f}%), only {rem:.1f}% left (<= {rem_threshold:.1f}%); turned off Fast for this account (agents.{alias}.fast: false)")
                    else:
                        reasons.append(f"{label} used {used:.1f}% (>= {used_threshold:.1f}%); Fast is already off for this account")
                else:
                    if global_fast is True:
                        fused_agents.append(None)
                        reasons.append(f"{label} used {used:.1f}% (>= {used_threshold:.1f}%); turned off global Fast (fast: false)")
                    else:
                        reasons.append(f"{label} used {used:.1f}% (>= {used_threshold:.1f}%); global Fast is already off")
        else:
            if current_fast is True:
                measurable_fast_active_count += 1

    # When measurable accounts exist and all of them have Fast off (fused now or earlier), also turn off accounts whose quota cannot be read
    if measurable_count > 0 and measurable_fast_active_count == 0:
        for provider_id, label in unmeasurable_accounts:
            alias = provider_to_alias.get(provider_id)
            account_force_fast = global_force_fast
            if alias and alias in agents and isinstance(agents[alias], dict):
                if "force_fast" in agents[alias]:
                    account_force_fast = bool(agents[alias]["force_fast"])
                if account_force_fast:
                    reasons.append(f"{label} quota unavailable, but force_fast: true is set; exempt from the linked fuse")
                    continue
                current_fast = agents[alias].get("fast", global_fast)
                if current_fast is True:
                    fused_agents.append(alias)
                    fuse_triggered = True
                    reasons.append(f"{label} quota unavailable and every measurable Codex account has Fast off; turned off Fast for this account too (agents.{alias}.fast: false)")
                else:
                    reasons.append(f"{label} quota unavailable, and Fast was already off")
            else:
                if account_force_fast:
                    reasons.append(f"{label} quota unavailable, but force_fast: true is set; exempt from the linked fuse")
                    continue
                if global_fast is True:
                    fused_agents.append(None)
                    fuse_triggered = True
                    reasons.append(f"{label} quota unavailable and every measurable Codex account has Fast off; turned off global Fast too (fast: false)")

    action_taken = "none"
    if fused_agents:
        if not dry_run:
            global_fallback = any(a is None for a in fused_agents) or not agents
            valid_agents = [a for a in fused_agents if a]
            update_config_file(config_path, content, valid_agents, global_fallback=global_fallback)
        action_taken = "fused_closed_fast"
    elif fuse_triggered:
        action_taken = "already_closed"
    elif global_force_fast:
        action_taken = "forced_fast"
    else:
        action_taken = "kept_current"

    return {
        "action": action_taken,
        "fuse_triggered": fuse_triggered,
        "fused_agents": [a for a in fused_agents if a],
        "force_fast": global_force_fast,
        "threshold_restored": threshold_restored,
        "remaining_threshold": rem_threshold,
        "used_threshold": used_threshold,
        "reasons": reasons,
        "accounts": accounts_stat,
    }


def main():
    parser = argparse.ArgumentParser(description="Check remaining Codex account quota and turn off Fast per account (or linked) when over the limit")
    parser.add_argument("--dry-run", action="store_true", help="dry run; do not modify the config file")
    parser.add_argument("--notify-thread", default=os.environ.get("BB_NOTIFY_THREAD"), help="BB thread ID to notify when the state changes")
    args = parser.parse_args()

    result = check_and_fuse(dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("threshold_restored"):
        msg = f"🔔 The temporary Fast fuse threshold expired; restored the default threshold (used >= {result['used_threshold']:.1f}%, i.e. remaining <= {result['remaining_threshold']:.1f}%)."
        print(msg)
        if args.notify_thread and not args.dry_run:
            notify_thread(args.notify_thread, msg)

    if result["action"] == "fused_closed_fast":
        msg = f"⚠️ Quota fuse triggered: {'; '.join(result['reasons'])}"
        print(msg)
        if args.notify_thread and not args.dry_run:
            notify_thread(args.notify_thread, f"[Codex quota fuse alert] {'; '.join(result['reasons'])}")
    elif result["action"] == "forced_fast":
        print(f"⚡ force_fast mode: {'; '.join(result['reasons']) if result['reasons'] else 'all accounts keep Fast on, exempt from the fuse.'}")
    elif result["fuse_triggered"]:
        print(f"⚠️ Quota below threshold, but Fast is already off: {'; '.join(result['reasons'])}")
    else:
        print(f"✅ Codex quota is sufficient (all used < {result['used_threshold']:.1f}%, all remaining > {result['remaining_threshold']:.1f}%); check OK.")


if __name__ == "__main__":
    main()
