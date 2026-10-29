#!/usr/bin/env python3
"""巡检 Codex 账号剩余额度；若 codex 或 codex-l 等账号剩余额度 <= 阈值，则关闭对应账号的 Fast。
若所有可监控账号均关闭 Fast，则联动关闭无法获取额度的账号（如 codex-b）。
若配置了 force_fast: true（全局或 agent 级），则强制开启 Fast 并豁免额度熔断。
支持在配置中通过 quota_fuse 自定义熔断阈值（如已用 95% 再关）及自动恢复时间（如明天中午恢复）。"""

import argparse
from datetime import datetime, timezone
import json
import os
import re
import subprocess
import sys
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("BB_DISPATCH_CONFIG", Path.home() / ".config/bb-dispatch/config.yaml"))
QUOTA_THRESHOLD_PERCENT = 40.0  # 默认剩余额度阈值百分比（即已用 60% 熔断）


def notify_thread(thread_id, message):
    if not thread_id:
        return False
    try:
        res = subprocess.run(["bb", "thread", "tell", thread_id, message], capture_output=True, text=True, timeout=15)
        return res.returncode == 0
    except Exception as exc:
        sys.stderr.write(f"通知线程失败: {exc}\n")
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
        ("codex", "codex (主号)"),
        ("codex-l", "codex-l (L号)"),
        ("codex-b", "codex-b (B号)"),
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
                reasons.append(f"{label} 已用达到 {used:.1f}% (>= {used_threshold:.1f}%)，但已配置 force_fast: true，豁免熔断")
                if current_fast is True:
                    measurable_fast_active_count += 1
            else:
                fuse_triggered = True
                if alias and alias in agents and isinstance(agents[alias], dict):
                    if current_fast is True:
                        fused_agents.append(alias)
                        reasons.append(f"{label} 已用达到 {used:.1f}% (>= {used_threshold:.1f}%)，剩余仅剩 {rem:.1f}% (<= {rem_threshold:.1f}%)，已自动关闭该账号 Fast 开关（agents.{alias}.fast: false）")
                    else:
                        reasons.append(f"{label} 已用达到 {used:.1f}% (>= {used_threshold:.1f}%)，该账号 Fast 已处于关闭状态")
                else:
                    if global_fast is True:
                        fused_agents.append(None)
                        reasons.append(f"{label} 已用达到 {used:.1f}% (>= {used_threshold:.1f}%)，已自动关闭全局 Fast 开关（fast: false）")
                    else:
                        reasons.append(f"{label} 已用达到 {used:.1f}% (>= {used_threshold:.1f}%)，全局 Fast 已处于关闭状态")
        else:
            if current_fast is True:
                measurable_fast_active_count += 1

    # 若存在可监控账号，且所有可监控账号的 Fast 均已关闭（本次熔断或此前已关），则联动关闭无法获取额度的账号
    if measurable_count > 0 and measurable_fast_active_count == 0:
        for provider_id, label in unmeasurable_accounts:
            alias = provider_to_alias.get(provider_id)
            account_force_fast = global_force_fast
            if alias and alias in agents and isinstance(agents[alias], dict):
                if "force_fast" in agents[alias]:
                    account_force_fast = bool(agents[alias]["force_fast"])
                if account_force_fast:
                    reasons.append(f"{label} 无法获取额度，但已配置 force_fast: true，豁免联动熔断")
                    continue
                current_fast = agents[alias].get("fast", global_fast)
                if current_fast is True:
                    fused_agents.append(alias)
                    fuse_triggered = True
                    reasons.append(f"{label} 无法获取额度，因所有可监控 Codex 账号均已关闭 Fast，联动关闭该账号 Fast（agents.{alias}.fast: false）")
                else:
                    reasons.append(f"{label} 无法获取额度，且 Fast 此前已处于关闭状态")
            else:
                if account_force_fast:
                    reasons.append(f"{label} 无法获取额度，但已配置 force_fast: true，豁免联动熔断")
                    continue
                if global_fast is True:
                    fused_agents.append(None)
                    fuse_triggered = True
                    reasons.append(f"{label} 无法获取额度，因所有可监控 Codex 账号均已关闭 Fast，联动关闭全局 Fast 开关（fast: false）")

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
    parser = argparse.ArgumentParser(description="巡检 Codex 账号剩余额度并在超限时独立/联动熔断 Fast")
    parser.add_argument("--dry-run", action="store_true", help="乾跑模式，不修改配置文件")
    parser.add_argument("--notify-thread", default=os.environ.get("BB_NOTIFY_THREAD"), help="状态切换时通知的目标 BB 线程 ID")
    args = parser.parse_args()

    result = check_and_fuse(dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("threshold_restored"):
        msg = f"🔔 临时 Fast 熔断阈值已到期，已自动恢复默认阈值（已用 >= {result['used_threshold']:.1f}%，即剩余 <= {result['remaining_threshold']:.1f}%）。"
        print(msg)
        if args.notify_thread and not args.dry_run:
            notify_thread(args.notify_thread, msg)

    if result["action"] == "fused_closed_fast":
        msg = f"⚠️ 触发额度熔断：{'; '.join(result['reasons'])}"
        print(msg)
        if args.notify_thread and not args.dry_run:
            notify_thread(args.notify_thread, f"[Codex 额度熔断告警] {'; '.join(result['reasons'])}")
    elif result["action"] == "forced_fast":
        print(f"⚡ force_fast 强制开启模式：{'; '.join(result['reasons']) if result['reasons'] else '所有账号保持开启 Fast，豁免熔断。'}")
    elif result["fuse_triggered"]:
        print(f"⚠️ 额度低于阈值，但 Fast 当前已处于关闭状态：{'; '.join(result['reasons'])}")
    else:
        print(f"✅ Codex 额度充足（已用均 < {result['used_threshold']:.1f}%，剩余均 > {result['remaining_threshold']:.1f}%），巡检正常。")


if __name__ == "__main__":
    main()
