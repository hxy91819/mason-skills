#!/usr/bin/env python3
"""巡检 Codex 账号剩余额度；若 codex 或 codex-l 等账号剩余额度 <= 40%，则关闭对应账号的 Fast。
若所有可监控账号均关闭 Fast，则联动关闭无法获取额度的账号（如 codex-b）。"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("BB_DISPATCH_CONFIG", Path.home() / ".config/bb-dispatch/config.yaml"))
QUOTA_THRESHOLD_PERCENT = 40.0  # 剩余额度阈值百分比


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


def check_and_fuse(config_path=CONFIG_PATH, dry_run=False):
    usage_data = get_usage()
    config_data, content = load_config(config_path)

    global_fast = True
    if config_data and isinstance(config_data, dict) and "fast" in config_data:
        global_fast = bool(config_data["fast"])
    elif content:
        m = re.search(r"^\s*fast:\s*(true|false)", content, re.MULTILINE)
        if m:
            global_fast = (m.group(1).lower() == "true")

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
        alias = provider_to_alias.get(provider_id)
        if alias and alias in agents and isinstance(agents[alias], dict):
            current_fast = agents[alias].get("fast", global_fast)
        else:
            current_fast = global_fast

        if rem <= QUOTA_THRESHOLD_PERCENT:
            fuse_triggered = True
            if alias and alias in agents and isinstance(agents[alias], dict):
                if current_fast is True:
                    fused_agents.append(alias)
                    reasons.append(f"{label} 剩余额度仅剩 {rem:.1f}% (<= {QUOTA_THRESHOLD_PERCENT}%)，已自动关闭该账号 Fast 开关（agents.{alias}.fast: false）")
                else:
                    reasons.append(f"{label} 剩余额度仅剩 {rem:.1f}% (<= {QUOTA_THRESHOLD_PERCENT}%)，该账号 Fast 已处于关闭状态")
            else:
                if global_fast is True:
                    fused_agents.append(None)
                    reasons.append(f"{label} 剩余额度仅剩 {rem:.1f}% (<= {QUOTA_THRESHOLD_PERCENT}%)，已自动关闭全局 Fast 开关（fast: false）")
                else:
                    reasons.append(f"{label} 剩余额度仅剩 {rem:.1f}% (<= {QUOTA_THRESHOLD_PERCENT}%)，全局 Fast 已处于关闭状态")
        else:
            if current_fast is True:
                measurable_fast_active_count += 1

    # 若存在可监控账号，且所有可监控账号的 Fast 均已关闭（本次熔断或此前已关），则联动关闭无法获取额度的账号
    if measurable_count > 0 and measurable_fast_active_count == 0:
        for provider_id, label in unmeasurable_accounts:
            alias = provider_to_alias.get(provider_id)
            if alias and alias in agents and isinstance(agents[alias], dict):
                current_fast = agents[alias].get("fast", global_fast)
                if current_fast is True:
                    fused_agents.append(alias)
                    fuse_triggered = True
                    reasons.append(f"{label} 无法获取额度，因所有可监控 Codex 账号均已关闭 Fast，联动关闭该账号 Fast（agents.{alias}.fast: false）")
                else:
                    reasons.append(f"{label} 无法获取额度，且 Fast 此前已处于关闭状态")
            else:
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
    else:
        action_taken = "kept_current"

    return {
        "action": action_taken,
        "fuse_triggered": fuse_triggered,
        "fused_agents": [a for a in fused_agents if a],
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
    if result["action"] == "fused_closed_fast":
        msg = f"⚠️ 触发额度熔断：{'; '.join(result['reasons'])}"
        print(msg)
        if args.notify_thread and not args.dry_run:
            notify_thread(args.notify_thread, f"[Codex 额度熔断告警] {'; '.join(result['reasons'])}")
    elif result["fuse_triggered"]:
        print(f"⚠️ 额度低于阈值，但 Fast 当前已处于关闭状态：{'; '.join(result['reasons'])}")
    else:
        print("✅ Codex 额度充足（均 > 40%），巡检正常。")


if __name__ == "__main__":
    main()
