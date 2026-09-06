#!/usr/bin/env python3
r"""按仓库清单同步本机 user-scope skill 软链。

脚本定义：
    读取仓库 `config/skill-symlinks.yaml`（推荐 user-scope 软链清单），把当前电脑的
    user-scope skills 目录（默认 `~/.agents/skills`）收敛到清单描述的状态：
    创建缺失的软链、修复指向错误的软链、把「指向已声明来源项目但不在清单里」的软链
    作为删除候选提示用户，并维护一份不提交 Git 的本机白名单。
    适用场景：一台新电脑 clone 本仓库后，一条命令完成 skill 软链同步；或日常校验漂移。

参数定义：
    --mode check|apply|register|remove   check=只报告不改（默认）；apply=执行同步，
                                        删除候选交互提示（--yes 跳过提示直接删）；
                                        register/remove=维护清单本身
    --skill <name>                       register/remove 模式必填；须存在于来源项目
    --source <project>                   register 可选：登记外部项目 skill（项目须已在
                                        清单 sources 声明，缺省会自动补一条声明）
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
    python3 scripts/sync_skill_symlinks.py --mode register --skill my-skill
    python3 scripts/sync_skill_symlinks.py --mode register --source mattpocock-skills --skill handoff

关键设计决策：
    - 清单 sources 只声明外部项目名，绝不写机器绝对路径；外部项目根按序解析：
      $SKILL_SOURCE_<NAME>_DIR > $SKILL_SOURCES_DIR/<项目名> > 本仓库同级目录 <项目名>。
      解析不到时相关条目按 stale 保守失败，不自动 clone。
    - 外部项目里的 skill 约定位于 skills/<bucket>/<name> 且含 SKILL.md；同名多 bucket
      视为歧义，保守失败。本仓库条目仍位于 common-skills/<name>。
    - 只管理「指向已声明来源项目 checkout」的软链；指向其他仓库的同名链接视为外部占用
      （conflict），绝不覆盖或删除，避免破坏用户其他工作区的配置。
    - 真实目录（非软链）一律不动，只报告 conflict；脚本永不递归删除。
    - 白名单记录在用户主目录（~/.agents/）而非仓库内，因为它属于本机环境偏好，
      提交进仓库会把一台电脑的特殊决定强加给所有其他电脑。
    - register/remove 重写清单时保留 `skills:` 之前的头部注释，其余结构由脚本规范化
      （按 name 排序），保证 diff 稳定可读。
    - Windows 兼容：优先创建 NTFS 符号链接（需管理员或开发者模式）；无特权时对目录
      退回 Junction（等价 mklink /J，无需特权）。链接识别用 os.readlink 而非
      Path.is_symlink()——后者不识别 Junction；Junction 存储目标带 \\?\ 前缀，比较前归一化。
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
# - 本仓库新增 skill 且要求软链到 user scope：--mode register --skill <name> [--note "..."]
# - 外部项目 skill：先在 sources 声明项目名，再 register --source <项目> --skill <name>
# - 删除/重命名 skill：--mode remove --skill <name>
# - 其他电脑 clone 本仓库后同步本机：--mode check 预览，--mode apply 执行
# 外部项目位置按序解析：$SKILL_SOURCE_<NAME>_DIR > $SKILL_SOURCES_DIR/<项目名> > 本仓库
# 同级目录 <项目名>；清单只写项目名，不写机器绝对路径。
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


def load_manifest(path: Path) -> tuple[list[dict], list[dict]]:
    """读取并校验清单；schema 错误按用法错误（退出码 2）保守失败。

    返回 (sources, skills)。sources 声明外部项目名；skills 条目可用 `source`
    指向某个已声明项目（缺省为本仓库 common-skills/<name>）。
    """
    if not path.is_file():
        raise SystemExit(f"manifest not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SystemExit(f"invalid manifest YAML ({path}): {exc}") from exc
    if not isinstance(data, dict) or data.get("version") != 1:
        raise SystemExit(f"invalid manifest ({path}): expected top-level 'version: 1'")
    sources = data.get("sources", [])
    if not isinstance(sources, list):
        raise SystemExit(f"invalid manifest ({path}): 'sources' must be a list")
    source_names: set[str] = set()
    for src in sources:
        name = src.get("name") if isinstance(src, dict) else None
        if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
            raise SystemExit(f"invalid manifest ({path}): every source needs a kebab-case string 'name'")
        if name in source_names:
            raise SystemExit(f"invalid manifest ({path}): duplicate source {name!r}")
        source_names.add(name)
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
        source = entry.get("source")
        if source is not None and (not isinstance(source, str) or source not in source_names):
            raise SystemExit(f"invalid manifest ({path}): skill {name!r} references undeclared source {source!r}")
    return sources, sorted(entries, key=lambda item: item["name"])


def dump_manifest(path: Path, sources: list[dict], entries: list[dict]) -> None:
    """重写清单：保留头部注释（skills: 键之前的注释/空行），条目规范化排序。"""
    header_lines: list[str] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("skills:"):
                break
            # 只保留注释与空行，避免把 version/sources 等结构性内容吸进 header
            if line.strip() == "" or line.lstrip().startswith("#"):
                header_lines.append(line)
    header = "\n".join(header_lines).rstrip() if header_lines else MANIFEST_HEADER.rstrip()
    data: dict = {"version": 1}
    if sources:
        data["sources"] = sources
    data["skills"] = sorted(entries, key=lambda item: item["name"])
    body = yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False).strip("\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{header}\n{body}\n", encoding="utf-8")


def source_env_var(source_name: str) -> str:
    return "SKILL_SOURCE_" + source_name.upper().replace("-", "_") + "_DIR"


def resolve_source_roots(sources: list[dict]) -> dict[str, Path | None]:
    """解析各来源项目根：'' 恒为本仓库；外部项目按环境变量 > $SKILL_SOURCES_DIR >
    本仓库同级目录解析，找不到返回 None（保守失败，不自动 clone）。"""
    roots: dict[str, Path | None] = {"": REPO_ROOT}
    for src in sources:
        name = src["name"]
        candidates: list[Path] = []
        override = os.environ.get(source_env_var(name), "").strip()
        if override:
            candidates.append(Path(override).expanduser())
        shared = os.environ.get("SKILL_SOURCES_DIR", "").strip()
        if shared:
            candidates.append(Path(shared).expanduser() / name)
        candidates.append(REPO_ROOT.parent / name)  # 约定：skill 仓库 clone 在同一父目录
        roots[name] = next((c.resolve() for c in candidates if c.is_dir()), None)
    return roots


def find_external_skill_dirs(project_root: Path, name: str) -> list[Path]:
    """外部项目里 name 的候选目录：skills/<bucket>/<name> 且含 SKILL.md。

    name 已过 kebab-case 校验（无 glob 元字符）；命中多个视为歧义，由调用方保守失败。
    """
    return [
        d
        for d in sorted(project_root.glob(f"skills/*/{name}"))
        if d.is_dir() and (d / "SKILL.md").is_file()
    ]


def entry_source_dir(entry: dict, roots: dict[str, Path | None]) -> Path:
    """解析条目的 skill 源目录；仅供 plan 已判定可解析（create/fix）的条目使用。"""
    source_name = entry.get("source") or ""
    project_root = roots[source_name]
    if source_name:
        return find_external_skill_dirs(project_root, entry["name"])[0]
    return COMMON_SKILLS / entry["name"]


def plan(root: Path, manifest: Path) -> list[tuple[str, str, str]]:
    """对比清单与现状，产出 (kind, name, detail) 列表；check/apply 共用。"""
    sources, entries = load_manifest(manifest)
    roots = resolve_source_roots(sources)
    names = {entry["name"] for entry in entries}
    managed_roots = [r for r in roots.values() if r is not None]
    findings: list[tuple[str, str, str]] = []

    for entry in entries:
        name = entry["name"]
        source_name = entry.get("source") or ""
        project_root = roots[source_name]
        link = root / name
        note = entry.get("note") or ""
        suffix = f" ({note})" if note else ""
        if project_root is None:
            findings.append(
                (
                    "stale",
                    name,
                    f"source project {source_name!r} not found on this machine "
                    f"(tried ${source_env_var(source_name)}, $SKILL_SOURCES_DIR/{source_name}, "
                    f"{REPO_ROOT.parent / source_name})",
                )
            )
            continue
        if source_name:
            matches = find_external_skill_dirs(project_root, name)
            if not matches:
                findings.append(("stale", name, f"no skills/*/{name} with SKILL.md under {project_root}{suffix}"))
                continue
            if len(matches) > 1:
                found = ", ".join(str(m) for m in matches)
                findings.append(("stale", name, f"ambiguous skill dirs under {project_root}: {found}{suffix}"))
                continue
            source = matches[0]
        else:
            source = COMMON_SKILLS / name
            if not source.is_dir():
                findings.append(("stale", name, f"manifest lists {source} but it does not exist{suffix}"))
                continue
        stored = link_target(link)
        if stored is None:
            if not link.exists():
                findings.append(("create", name, f"link {link} -> {source}"))
            else:
                findings.append(
                    ("conflict", name, f"{link} is a real directory/file, not managed here{suffix}")
                )
            continue
        if _same_file(stored, source):
            findings.append(("ok", name, "already linked"))
            continue
        try:
            through = link.resolve()
        except OSError:
            through = None
        if through is not None and _same_file(through, source):
            # 链接经中间路径最终落到事实源（软链中转）时同样视为已收敛。
            findings.append(("ok", name, "already linked"))
        elif _is_inside(stored, project_root):
            findings.append(("fix", name, f"link points to {stored}, expected {source}"))
        else:
            findings.append(
                ("conflict", name, f"{link} is owned by another checkout: {stored}{suffix}")
            )

    if root.is_dir():
        for child in sorted(root.iterdir()):
            first_hop = link_target(child)
            if first_hop is None or child.name in names:
                continue
            # 只管「直接指向已声明来源项目」的链接：经其他工作区软链中转再落入的，
            # 第一跳在来源项目外，属于那套体系的管辖区，这里不碰也不提示。
            owner = next((mr for mr in managed_roots if _is_inside(first_hop, mr)), None)
            if owner is None:
                continue
            label = owner.name or REPO_ROOT.name
            findings.append(("extra", child.name, f"user-scope link into managed source {label} not in manifest: {first_hop}"))
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


def link_target(link: Path) -> Path | None:
    r"""链接的存储目标（首跳，绝对化并去掉 Windows \\?\ 前缀）；非链接返回 None。

    用 os.readlink 而非 Path.is_symlink() 判定：Windows 上 Junction 不是符号链接，
    is_symlink() 会漏判；os.readlink 对符号链接和 Junction 都有效。
    """
    try:
        raw = os.readlink(link)
    except (OSError, ValueError):
        return None
    target = Path(raw)
    if not target.is_absolute():
        target = link.parent / target
        try:
            target = target.resolve()
        except OSError:
            pass
    text = str(target)
    if text.startswith("\\\\?\\"):
        text = text[4:]
    return Path(text)


def _normkey(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _same_file(a: Path, b: Path) -> bool:
    return _normkey(a) == _normkey(b)


def _is_inside(child: Path, parent: Path) -> bool:
    c, p = _normkey(child), _normkey(parent)
    return c == p or c.startswith(p.rstrip(os.sep) + os.sep)


def make_link(source: Path, link: Path) -> None:
    try:
        link.symlink_to(source, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            raise
        # 无符号链接特权时的 Windows 回退：目录用 Junction，等价 mklink /J，无需特权。
        import _winapi

        _winapi.CreateJunction(str(source), str(link))


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
    sources, entries = load_manifest(manifest)
    roots = resolve_source_roots(sources)
    entry_by_name = {entry["name"]: entry for entry in entries}
    whitelisted = {entry["name"] for entry in load_whitelist(whitelist)}
    findings = plan(root, manifest)

    if not root.is_dir():
        if not any(kind in {"create", "fix"} for kind, _, _ in findings):
            print(f"user-scope skills dir does not exist and nothing to create: {root}")
        root.mkdir(parents=True, exist_ok=True)

    unresolved = 0
    for kind, name, detail in findings:
        link = root / name
        if kind == "ok":
            print(f"[ok] {name}: already linked")
        elif kind == "create":
            source = entry_source_dir(entry_by_name[name], roots)
            make_link(source, link)
            print(f"[created] {name}: {link} -> {source}")
        elif kind == "fix":
            source = entry_source_dir(entry_by_name[name], roots)
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
    if manifest.is_file():
        sources, entries = load_manifest(manifest)
    else:
        # 首次使用：用默认头部初始化空清单，避免要求手工准备文件。
        sources, entries = [], []
        dump_manifest(manifest, sources, entries)
        print(f"[initialized] empty manifest at {manifest}")
    source_name = args.source or ""
    if source_name:
        if not NAME_PATTERN.fullmatch(source_name):
            raise SystemExit(f"invalid --source {source_name!r}: use kebab-case like 'my-project'")
        if not any(src["name"] == source_name for src in sources):
            sources.append({"name": source_name})
            print(f"[declared] source project {source_name} in {manifest}")
    roots = resolve_source_roots(sources)
    if source_name:
        project_root = roots[source_name]
        if project_root is None:
            print(f"[warning] source project {source_name!r} not found on this machine; registered without local verification")
        else:
            matches = find_external_skill_dirs(project_root, name)
            if len(matches) != 1:
                raise SystemExit(
                    f"expected exactly one skills/*/{name} with SKILL.md under {project_root}, "
                    f"found {len(matches)}; nothing to register"
                )
    elif not (COMMON_SKILLS / name).is_dir():
        raise SystemExit(f"skill directory not found: {COMMON_SKILLS / name}; nothing to register")
    note = (args.note or "").strip()
    for entry in entries:
        if entry["name"] == name:
            entry["note"] = note or entry.get("note") or ""
            if source_name:
                entry["source"] = source_name
            dump_manifest(manifest, sources, entries)
            print(f"[updated] manifest entry for {name}" + (f" ({note})" if note else ""))
            return 0
    new_entry: dict = {"name": name}
    if source_name:
        new_entry["source"] = source_name
    new_entry["note"] = note
    entries.append(new_entry)
    dump_manifest(manifest, sources, entries)
    label = f" ({source_name})" if source_name else ""
    print(f"[registered] {name} in {manifest}{label}" + (f" ({note})" if note else ""))
    return 0


def run_remove(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest).expanduser().resolve()
    name = args.skill
    if not manifest.is_file():
        raise SystemExit(f"manifest not found: {manifest}")
    sources, entries = load_manifest(manifest)
    remaining = [entry for entry in entries if entry["name"] != name]
    if len(remaining) == len(entries):
        raise SystemExit(f"skill {name!r} is not in {manifest}")
    dump_manifest(manifest, sources, remaining)
    print(f"[removed] {name} from {manifest} (user-scope symlink, if any, is left untouched)")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    epilog = """输出结果定义:
  stdout 逐条报告 [ok|created|fixed|deleted|whitelisted|skipped|conflict|stale] 与 summary 计数
  退出码: 0=已收敛; 1=存在漂移或未解决 conflict/stale; 2=用法或环境错误

调用范例:
  %(prog)s --mode check                      # 预览漂移，不改任何东西
  %(prog)s --mode apply                      # 执行同步，删除候选交互确认
  printf 'k\\n' | %(prog)s --mode apply      # 非交互保留并写入白名单
  %(prog)s --mode apply --yes                # 非交互直接删除 extra
  %(prog)s --mode register --skill my-skill
  %(prog)s --mode register --source mattpocock-skills --skill handoff
  %(prog)s --mode remove --skill my-skill"""
    parser = argparse.ArgumentParser(
        description="Sync user-scope skill symlinks per config/skill-symlinks.yaml (see module docstring for the full contract).",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--mode", choices=("check", "apply", "register", "remove"), default="check")
    parser.add_argument("--skill", help="skill name for register/remove (required for those modes)")
    parser.add_argument("--source", default="", help="register: external source project (must be declared in manifest sources; auto-declared when missing)")
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
