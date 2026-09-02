#!/usr/bin/env python3
"""按仓库清单同步本机 user-scope skill 软链。

脚本定义：
    读取仓库 `config/skill-symlinks.yaml`（推荐 user-scope 软链清单），把当前电脑的
    user-scope skills 目录（默认 `~/.agents/skills`）收敛到清单描述的状态：
    创建缺失的软链、修复指向错误的软链、把「指向本仓库但不在清单里」的软链作为
    删除候选提示用户，并维护一份不提交 Git 的本机白名单。
    适用场景：一台新电脑 clone 本仓库后，一条命令完成 skill 软链同步；或日常校验漂移。

参数定义：
    --mode check|apply|register|remove   check=只报告不改（默认）；apply=执行同步，
                                        删除候选交互提示（--yes 跳过提示直接删）；
                                        register/remove=维护清单本身
    --skill <name>                       register/remove 模式必填；须存在于 common-skills/
    --note <text>                        register 模式可选备注
    --manifest <path>                    清单路径（默认 <repo>/config/skill-symlinks.yaml）
    --skills-dir <path>                  user-scope skills 目录（默认 $AGENTS_HOME/skills，再退 ~/.agents/skills）
    --whitelist <path>                   本机白名单（默认 <skills 目录同级>/skill-sync-whitelist.yaml）
    --yes                                apply 模式非交互：删除候选直接删除，不写白名单
    -h, --help                           帮助

输出结果定义：
    stdout：逐条 `[类型] 名字 详情` 报告 + 末尾 summary 计数；无产物文件（白名单除外）
    退出码：0 = 已收敛（check 无漂移 / apply 完成且无遗留）；1 = 存在漂移或未解决的
            conflict/stale 项；2 = 用法或环境错误（缺 PyYAML、清单非法、参数错误）

调用范例：
    python3 scripts/sync_skill_symlinks.py --mode check
    python3 scripts/sync_skill_symlinks.py --mode apply --yes
    printf 'k\n' | python3 scripts/sync_skill_symlinks.py --mode apply   # 交互保留并加白名单
    python3 scripts/sync_skill_symlinks.py --mode register --skill my-skill --note "收尾审查"

关键设计决策：
    - 只管理「指向本仓库 checkout」的软链；指向其他仓库的同名链接视为外部占用
      （conflict），绝不覆盖或删除，避免破坏用户其他工作区的配置。
    - 真实目录（非软链）一律不动，只报告 conflict；脚本永不递归删除。
    - 白名单记录在用户主目录（~/.agents/）而非仓库内，因为它属于本机环境偏好，
      提交进仓库会把一台电脑的特殊决定强加给所有其他电脑。
    - register/remove 重写清单时保留 `skills:` 之前的头部注释，其余结构由脚本规范化
      （按 name 排序），保证 diff 稳定可读。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - 环境错误走退出码 2
    print("ERROR: PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parents[3]
COMMON_SKILLS = REPO_ROOT / "common-skills"
DEFAULT_MANIFEST = REPO_ROOT / "config" / "skill-symlinks.yaml"
MANIFEST_HEADER = """\
# mason-skills 推荐 user-scope 软链清单
# 维护规则见仓库 AGENTS.md「Skill 清单维护」；skill 入口为 $skill-manifest-sync。
# - 新增 skill 且要求软链到 user scope：--mode register --skill <name> [--note "..."]
# - 删除/重命名 skill：--mode remove --skill <name>
# - 其他电脑 clone 本仓库后同步本机：--mode check 预览，--mode apply 执行
"""
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
WHITELIST_HEADER = """\
# skill-manifest-sync 本机白名单：确认保留、不随清单删除的 user-scope 软链。
# 属于本机环境偏好，不提交 Git；条目由 --mode apply 交互选择 k 时自动写入。
"""


def skills_root(args: argparse.Namespace) -> Path:
    """解析 user-scope skills 目录：--skills-dir > $AGENTS_HOME/skills > ~/.agents/skills。"""
    if args.skills_dir:
        return Path(args.skills_dir).expanduser().resolve()
    home = os.environ.get("AGENTS_HOME", "").strip()
    base = Path(home).expanduser() if home else Path.home() / ".agents"
    return (base / "skills").resolve()


def whitelist_path(args: argparse.Namespace, root: Path) -> Path:
    if args.whitelist:
        return Path(args.whitelist).expanduser().resolve()
    return root.parent / "skill-sync-whitelist.yaml"


def load_manifest(path: Path) -> list[dict]:
    """读取并校验清单；schema 错误按用法错误（退出码 2）保守失败。"""
    if not path.is_file():
        raise SystemExit(f"manifest not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SystemExit(f"invalid manifest YAML ({path}): {exc}") from exc
    if not isinstance(data, dict) or data.get("version") != 1:
        raise SystemExit(f"invalid manifest ({path}): expected top-level 'version: 1'")
    entries = data.get("skills", [])
    if not isinstance(entries, list):
        raise SystemExit(f"invalid manifest ({path}): 'skills' must be a list")
    names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise SystemExit(f"invalid manifest ({path}): every skill needs a string 'name'")
        name = entry["name"]
        if not NAME_PATTERN.fullmatch(name):
            raise SystemExit(f"invalid manifest ({path}): bad skill name {name!r} (use kebab-case)")
        if name in names:
            raise SystemExit(f"invalid manifest ({path}): duplicate skill {name!r}")
        names.add(name)
    return sorted(entries, key=lambda item: item["name"])


def dump_manifest(path: Path, entries: list[dict]) -> None:
    """重写清单：保留头部注释（skills: 键之前的注释/空行），条目规范化排序。"""
    header_lines: list[str] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("skills:"):
                break
            # 只保留注释与空行，避免把旧的 version 等结构性内容吸进 header
            if line.strip() == "" or line.lstrip().startswith("#"):
                header_lines.append(line)
    header = "\n".join(header_lines).rstrip() if header_lines else MANIFEST_HEADER.rstrip()
    body = yaml.dump(
        {"version": 1, "skills": sorted(entries, key=lambda item: item["name"])},
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).strip("\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{header}\n{body}\n", encoding="utf-8")


def plan(root: Path, manifest: Path) -> list[tuple[str, str, str]]:
    """对比清单与现状，产出 (kind, name, detail) 列表；check/apply 共用。"""
    entries = load_manifest(manifest)
    names = {entry["name"] for entry in entries}
    findings: list[tuple[str, str, str]] = []

    for entry in entries:
        name = entry["name"]
        source = COMMON_SKILLS / name
        link = root / name
        note = entry.get("note") or ""
        suffix = f" ({note})" if note else ""
        if not source.is_dir():
            findings.append(("stale", name, f"manifest lists {source} but it does not exist{suffix}"))
            continue
        if not link.exists() and not link.is_symlink():
            findings.append(("create", name, f"link {link} -> {source}"))
            continue
        if not link.is_symlink():
            findings.append(
                ("conflict", name, f"{link} is a real directory/file, not managed here{suffix}")
            )
            continue
        try:
            target = link.resolve()
        except OSError:
            target = Path(os.readlink(link))
        if target == source.resolve():
            findings.append(("ok", name, "already linked"))
        elif target.is_relative_to(REPO_ROOT):
            findings.append(("fix", name, f"link points to {target}, expected {source}"))
        else:
            findings.append(
                ("conflict", name, f"{link} is owned by another checkout: {target}{suffix}")
            )

    if root.is_dir():
        for child in sorted(root.iterdir()):
            if not child.is_symlink():
                continue
            # 只管「直接指向本仓库」的链接：经其他工作区软链中转再落到本仓库的，
            # 第一跳在 repo 外，属于那套体系的管辖区，这里不碰也不提示。
            first_hop = Path(os.readlink(child))
            if not first_hop.is_absolute():
                first_hop = (child.parent / first_hop).resolve()
            if not first_hop.is_relative_to(REPO_ROOT) or child.name in names:
                continue
            findings.append(("extra", child.name, f"user-scope link into this repo not in manifest: {first_hop}"))
    return findings


def load_whitelist(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise SystemExit(f"invalid whitelist YAML ({path}): {exc}") from exc
    entries = data.get("whitelist", [])
    return [entry for entry in entries if isinstance(entry, dict) and isinstance(entry.get("name"), str)]


def add_to_whitelist(path: Path, name: str, reason: str) -> None:
    entries = load_whitelist(path)
    if any(entry["name"] == name for entry in entries):
        return
    entries.append(
        {
            "name": name,
            "reason": reason,
            "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.dump(
        {"version": 1, "whitelist": entries},
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).strip("\n")
    path.write_text(f"{WHITELIST_HEADER}{body}\n", encoding="utf-8")


def make_link(source: Path, link: Path) -> None:
    link.symlink_to(source, target_is_directory=True)


def relink(link: Path, source: Path) -> None:
    # 仅对确认存在的符号链接执行 unlink，绝不触碰真实目录。
    link.unlink()
    make_link(source, link)


def read_answer(prompt: str) -> str:
    """读用户选择：tty 用 input()；管道/重定向从 stdin 读一行，EOF 按 skip。"""
    if not sys.stdin.isatty():
        line = sys.stdin.readline()
        return line.strip().lower() if line else "n"
    while True:
        answer = input(prompt).strip().lower()
        if answer in {"d", "k", "n"}:
            return answer
        print("  please answer d, k, or n.")


def prompt_extra(name: str, detail: str, whitelist: Path) -> str:
    """删除候选选择：d=删除 / k=保留并写白名单 / n=跳过。"""
    print(f"extra symlink: {detail}")
    return read_answer(f"  {name}: delete [d], keep and whitelist [k], skip this run [n]? ")


def run_apply(args: argparse.Namespace) -> int:
    root = skills_root(args)
    manifest = Path(args.manifest).expanduser().resolve()
    whitelist = whitelist_path(args, root)
    entries = load_manifest(manifest)
    whitelisted = {entry["name"] for entry in load_whitelist(whitelist)}
    findings = plan(root, manifest)

    if not root.is_dir():
        if not any(kind in {"create", "fix"} for kind, _, _ in findings):
            print(f"user-scope skills dir does not exist and nothing to create: {root}")
        root.mkdir(parents=True, exist_ok=True)

    unresolved = 0
    for kind, name, detail in findings:
        source = COMMON_SKILLS / name
        link = root / name
        if kind == "ok":
            print(f"[ok] {name}: already linked")
        elif kind == "create":
            make_link(source, link)
            print(f"[created] {name}: {link} -> {source}")
        elif kind == "fix":
            relink(link, source)
            print(f"[fixed] {name}: now {link} -> {source}")
        elif kind == "extra":
            if name in whitelisted:
                print(f"[whitelisted] {name}: {detail}")
                continue
            if args.yes:
                link.unlink()
                print(f"[deleted] {name}: {detail}")
            else:
                answer = prompt_extra(name, detail, whitelist)
                if answer == "d":
                    link.unlink()
                    print(f"[deleted] {name}: {detail}")
                elif answer == "k":
                    add_to_whitelist(whitelist, name, "kept during apply (user choice)")
                    print(f"[whitelisted] {name}: recorded in {whitelist}")
                else:
                    print(f"[skipped] {name}: {detail}")
                    unresolved += 1
        else:
            # conflict / stale：保守失败，只报告，由用户手动裁决。
            print(f"[{kind}] {name}: {detail}")
            unresolved += 1

    summary(report=findings, unresolved=unresolved)
    return 1 if unresolved else 0


def run_check(args: argparse.Namespace) -> int:
    root = skills_root(args)
    manifest = Path(args.manifest).expanduser().resolve()
    whitelisted = {entry["name"] for entry in load_whitelist(whitelist_path(args, root))}
    findings = plan(root, manifest)
    unresolved = 0
    for kind, name, detail in findings:
        if kind == "ok":
            print(f"[ok] {name}: already linked")
            continue
        if kind == "extra" and name in whitelisted:
            print(f"[whitelisted] {name}: {detail}")
            continue
        print(f"[{kind}] {name}: {detail}")
        unresolved += 1
    summary(report=findings, unresolved=unresolved)
    return 1 if unresolved else 0


def summary(report: list[tuple[str, str, str]], unresolved: int) -> None:
    counts: dict[str, int] = {}
    for kind, _, _ in report:
        counts[kind] = counts.get(kind, 0) + 1
    parts = [f"{kind}={count}" for kind, count in sorted(counts.items())]
    tail = f"; unresolved={unresolved}" if unresolved else ""
    print(f"summary: {', '.join(parts) if parts else 'no entries'}{tail}")


def run_register(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest).expanduser().resolve()
    name = args.skill
    if not NAME_PATTERN.fullmatch(name):
        raise SystemExit(f"invalid --skill {name!r}: use kebab-case like 'my-skill'")
    source = COMMON_SKILLS / name
    if not source.is_dir():
        raise SystemExit(f"skill directory not found: {source}; nothing to register")
    if not manifest.is_file():
        # 首次使用：用默认头部初始化空清单，避免要求手工准备文件。
        dump_manifest(manifest, [])
        print(f"[initialized] empty manifest at {manifest}")
    entries = load_manifest(manifest)
    note = (args.note or "").strip()
    for entry in entries:
        if entry["name"] == name:
            entry["note"] = note or entry.get("note") or ""
            dump_manifest(manifest, entries)
            print(f"[updated] manifest entry for {name}" + (f" ({note})" if note else ""))
            return 0
    entries.append({"name": name, "note": note})
    dump_manifest(manifest, entries)
    print(f"[registered] {name} in {manifest}" + (f" ({note})" if note else ""))
    return 0


def run_remove(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest).expanduser().resolve()
    name = args.skill
    if not manifest.is_file():
        raise SystemExit(f"manifest not found: {manifest}")
    entries = load_manifest(manifest)
    remaining = [entry for entry in entries if entry["name"] != name]
    if len(remaining) == len(entries):
        raise SystemExit(f"skill {name!r} is not in {manifest}")
    dump_manifest(manifest, remaining)
    print(f"[removed] {name} from {manifest} (user-scope symlink, if any, is left untouched)")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    epilog = """输出结果定义:
  stdout 逐条报告 [ok|created|fixed|deleted|whitelisted|skipped|created|conflict|stale] 与 summary 计数
  退出码: 0=已收敛; 1=存在漂移或未解决 conflict/stale; 2=用法或环境错误

调用范例:
  %(prog)s --mode check                      # 预览漂移，不改任何东西
  %(prog)s --mode apply                      # 执行同步，删除候选交互确认
  printf 'k\\n' | %(prog)s --mode apply      # 非交互保留并写入白名单
  %(prog)s --mode apply --yes                # 非交互直接删除 extra
  %(prog)s --mode register --skill my-skill --note "一句话用途"
  %(prog)s --mode remove --skill my-skill"""
    parser = argparse.ArgumentParser(
        description="Sync user-scope skill symlinks per config/skill-symlinks.yaml (see module docstring for the full contract).",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--mode", choices=("check", "apply", "register", "remove"), default="check")
    parser.add_argument("--skill", help="skill name for register/remove (required for those modes)")
    parser.add_argument("--note", default="", help="optional note recorded with register")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--skills-dir", default="", help="user-scope skills dir (default: $AGENTS_HOME/skills or ~/.agents/skills)")
    parser.add_argument("--whitelist", default="", help="local whitelist file (default: <skills dir parent>/skill-sync-whitelist.yaml)")
    parser.add_argument("--yes", action="store_true", help="apply mode: delete extra links without prompting")
    args = parser.parse_args(argv)
    if args.mode in {"register", "remove"} and not args.skill:
        parser.error(f"--skill is required for --mode {args.mode}")
    if args.mode != "apply" and args.yes:
        parser.error("--yes is only valid with --mode apply")
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.mode == "check":
        return run_check(args)
    if args.mode == "apply":
        return run_apply(args)
    if args.mode == "register":
        return run_register(args)
    return run_remove(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))