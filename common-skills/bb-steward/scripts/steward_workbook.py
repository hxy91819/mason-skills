#!/usr/bin/env python3
"""BB 管家工作簿（Workbook）结构、容量与提交节流门禁。

用法：
  python3 steward_workbook.py --mode check --file docs/steward/<topic>.md
  python3 steward_workbook.py --mode should-commit --file docs/steward/<topic>.md

stdout 输出 JSON；退出码 0 表示通过，2 表示门禁未通过或参数错误。
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

REQUIRED_SECTIONS = ["路线", "关键决策", "用户待办"]
DEFAULT_MAX_NONEMPTY_LINES = 45
DEFAULT_MAX_LINE_CHARS = 180
DEFAULT_MAX_ROUTE_ITEMS = 10
DEFAULT_MAX_DECISIONS = 12

MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
WIKI_LINK_RE = re.compile(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]")
CHECKBOX_RE = re.compile(r"^-\s*\[([ xX])\]\s*(.+)$")


def visible_length(line: str) -> int:
    """计算剥离 Markdown URL 目标后的可见字符长度。"""
    s = MD_LINK_RE.sub(r"\1", line)
    s = WIKI_LINK_RE.sub(r"\1", s)
    return len(s.strip())


def parse_workbook(text: str):
    lines = text.splitlines()
    title = None
    sections = {}
    section_order = []
    current_section = None
    subheadings = []

    for lineno, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if stripped.startswith("# ") and title is None and current_section is None:
            title = stripped[2:].strip()
            continue
        if stripped.startswith("## "):
            sec_name = stripped[3:].strip()
            section_order.append(sec_name)
            current_section = sec_name
            sections.setdefault(sec_name, [])
            continue
        if stripped.startswith("###"):
            subheadings.append((lineno, stripped))
        if current_section is not None:
            sections[current_section].append((lineno, raw))

    return {
        "lines": lines,
        "title": title,
        "section_order": section_order,
        "sections": sections,
        "subheadings": subheadings,
    }


def check_workbook(text: str, max_nonempty_lines=DEFAULT_MAX_NONEMPTY_LINES,
                   max_line_chars=DEFAULT_MAX_LINE_CHARS,
                   max_route_items=DEFAULT_MAX_ROUTE_ITEMS,
                   max_decisions=DEFAULT_MAX_DECISIONS):
    parsed = parse_workbook(text)
    errors = []
    nonempty_lines = [ln for ln in parsed["lines"] if ln.strip()]

    if not parsed["title"]:
        errors.append("缺少一级标题（# <目标一句话>）。")

    if parsed["section_order"] != REQUIRED_SECTIONS:
        errors.append(
            f"二级标题必须且只能按顺序为 {REQUIRED_SECTIONS}，当前为 {parsed['section_order']}。"
        )

    if parsed["subheadings"]:
        first_ln, first_h = parsed["subheadings"][0]
        errors.append(f"第 {first_ln} 行出现不允许的子标题 {first_h!r}；工作簿保持三段扁平结构。")

    if len(nonempty_lines) > max_nonempty_lines:
        errors.append(
            f"非空行总数 {len(nonempty_lines)} 超过一屏上限 {max_nonempty_lines}；请先删减或将细碎矩阵移回项目文档/Issue。"
        )

    for lineno, raw in enumerate(parsed["lines"], start=1):
        vlen = visible_length(raw)
        if vlen > max_line_chars:
            errors.append(
                f"第 {lineno} 行可见字符数 {vlen} 超过上限 {max_line_chars}；路线与决策每条只留结论，不塞过程流水账。"
            )

    route_lines = parsed["sections"].get("路线", [])
    route_items = []
    for lineno, raw in route_lines:
        s = raw.strip()
        if not s:
            continue
        if s.startswith("|") and s.endswith("|"):
            errors.append(
                f"第 {lineno} 行在「路线」中使用了表格；子任务矩阵应放在项目 Issue 或计划文档中，路线只留阶段行与当前位置。"
            )
        m = CHECKBOX_RE.match(s)
        if m:
            route_items.append((lineno, m.group(1).lower() == "x", "←" in s, m.group(2)))

    if len(route_items) > max_route_items:
        errors.append(f"「路线」阶段数 {len(route_items)} 超过上限 {max_route_items}。")

    decision_lines = parsed["sections"].get("关键决策", [])
    decisions = [raw.strip() for _, raw in decision_lines if raw.strip().startswith("- ")]
    if len(decisions) > max_decisions:
        errors.append(
            f"「关键决策」条数 {len(decisions)} 超过上限 {max_decisions}；新决定覆盖旧决定时应原地替换，随线程消亡的局部取舍不入簿。"
        )

    return {
        "ok": len(errors) == 0,
        "stats": {
            "nonempty_lines": len(nonempty_lines),
            "route_items": len(route_items),
            "decision_items": len(decisions),
        },
        "errors": errors,
    }


def extract_state_signature(text: str):
    """提取决定工作簿是否发生实质状态跃迁的签名，忽略括号内的过程文字微调。"""
    parsed = parse_workbook(text)
    route_sig = []
    for _, raw in parsed["sections"].get("路线", []):
        s = raw.strip()
        m = CHECKBOX_RE.match(s)
        if m:
            checked = m.group(1).lower() == "x"
            is_current = "←" in s
            # 提取冒号或左括号前的阶段主干名称
            body = m.group(2).split("←", 1)[0].strip()
            stem = re.split(r"[（(—\-:：]", body, maxsplit=1)[0].strip()
            route_sig.append((stem, checked, is_current))

    decision_sig = []
    for _, raw in parsed["sections"].get("关键决策", []):
        s = raw.strip()
        if s.startswith("- "):
            decision_sig.append(re.sub(r"\s+", " ", s[2:].strip()))

    todo_sig = []
    for _, raw in parsed["sections"].get("用户待办", []):
        s = raw.strip()
        if not s or s == "无。" or s == "无":
            continue
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) >= 2 and cells[0] not in ("状态", "---") and not all(set(c) <= {"-", ":"} for c in cells):
                status = cells[0]
                item = cells[1]
                blocker = cells[3] if len(cells) >= 4 else ""
                todo_sig.append((status, item, blocker))

    return {
        "route": route_sig,
        "decisions": decision_sig,
        "todos": todo_sig,
    }


def head_content_for(file_path: Path):
    file_path = file_path.resolve()
    try:
        top = subprocess.run(
            ["git", "-C", str(file_path.parent), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()
        rel = file_path.relative_to(Path(top).resolve()).as_posix()
        shown = subprocess.run(
            ["git", "-C", top, "show", f"HEAD:{rel}"],
            capture_output=True, text=True, timeout=10,
        )
        if shown.returncode != 0:
            return None
        return shown.stdout
    except Exception:
        return None


def should_commit_workbook(file_path: Path, check_args: dict, baseline_text: str | None = None):
    text = file_path.read_text()
    check_res = check_workbook(text, **check_args)
    if not check_res["ok"]:
        return {
            **check_res,
            "file": str(file_path),
            "should_commit": False,
            "reason": "check_failed",
            "changed_sections": [],
        }

    old_text = baseline_text if baseline_text is not None else head_content_for(file_path)
    if old_text is None:
        return {
            **check_res,
            "file": str(file_path),
            "should_commit": True,
            "reason": "new_file",
            "changed_sections": REQUIRED_SECTIONS,
        }

    old_sig = extract_state_signature(old_text)
    new_sig = extract_state_signature(text)
    changed = []
    if old_sig["route"] != new_sig["route"]:
        changed.append("路线")
    if old_sig["decisions"] != new_sig["decisions"]:
        changed.append("关键决策")
    if old_sig["todos"] != new_sig["todos"]:
        changed.append("用户待办")

    return {
        **check_res,
        "file": str(file_path),
        "should_commit": len(changed) > 0,
        "reason": "state_changed" if changed else "no_structural_state_change",
        "changed_sections": changed,
    }


def parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", required=True, choices=["check", "should-commit"], help="check=校验结构与容量；should-commit=校验并判断相对 HEAD 是否有实质状态变化")
    p.add_argument("--file", required=True, help="工作簿 Markdown 文件路径")
    p.add_argument("--max-nonempty-lines", type=int, default=DEFAULT_MAX_NONEMPTY_LINES)
    p.add_argument("--max-line-chars", type=int, default=DEFAULT_MAX_LINE_CHARS)
    p.add_argument("--max-route-items", type=int, default=DEFAULT_MAX_ROUTE_ITEMS)
    p.add_argument("--max-decisions", type=int, default=DEFAULT_MAX_DECISIONS)
    return p


def main():
    args = parser().parse_args()
    fpath = Path(args.file).expanduser()
    if not fpath.is_file():
        print(json.dumps({"ok": False, "file": str(fpath), "errors": [f"文件不存在：{fpath}"]}, ensure_ascii=False, indent=2))
        return 2
    check_args = {
        "max_nonempty_lines": args.max_nonempty_lines,
        "max_line_chars": args.max_line_chars,
        "max_route_items": args.max_route_items,
        "max_decisions": args.max_decisions,
    }
    if args.mode == "check":
        res = {"file": str(fpath), **check_workbook(fpath.read_text(), **check_args)}
    else:
        res = should_commit_workbook(fpath, check_args)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
