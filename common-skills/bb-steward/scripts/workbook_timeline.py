"""工作簿时间与倒序排版；只处理路线 checkbox 和用户待办表。"""
from datetime import datetime
import re
from zoneinfo import ZoneInfo

SGT = ZoneInfo("Asia/Singapore")
STAMP = r"\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2}:\d{2} SGT)?"
CREATED = re.compile(r" <!-- steward-created: (.*?) -->")
COMPLETED = re.compile(r" （完成：(.*?)）")
CHECKBOX = re.compile(r"^\s*-\s*\[([ xX])\]\s*(.+)$")
ALIASES = {"路線": "路线", "用戶待辦": "用户待办"}


def date_key(value, now):
    value = value.strip().removesuffix(" SGT")
    if re.fullmatch(r"\d{2}-\d{2}", value):
        value = f"{now.year}-{value}"
    try:
        return datetime.fromisoformat(value).replace(tzinfo=SGT).timestamp()
    except ValueError:
        return float("-inf")


def route_identity(line):
    body = CHECKBOX.match(line).group(2)
    body = CREATED.sub("", COMPLETED.sub("", body))
    # 阶段编号优先；无编号时按冒号前标题，结果和状态可自由更新。
    stage = re.match(r"((?:阶段|階段|发布|發佈|Stage)\s*\d+)\b", body, re.I)
    return stage.group(1) if stage else re.split(r"[:：←]", body, maxsplit=1)[0].strip()


def cells(line):
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def sections(text):
    result = []
    for line in text.splitlines():
        if line.startswith("## "):
            name = line[3:].strip()
            result.append((ALIASES.get(name, name), [line]))
        elif result:
            result[-1][1].append(line)
        else:
            result.append(("", [line]))
    return result


def format_timeline(text, baseline=None, now=None):
    """时间是脚本观察到状态变化的时刻；旧的已完成行不补造历史完成时间。"""
    now = now or datetime.now(SGT)
    if now.tzinfo is None:
        raise ValueError("now 必须带时区")
    now = now.astimezone(SGT)
    stamp = now.strftime("%Y-%m-%d %H:%M:%S SGT")
    old_sections = dict(sections(baseline or ""))
    warnings = []
    output = []
    input_lines = 0
    for name, lines in sections(text):
        first_lineno = input_lines + 1
        input_lines += len(lines)
        old_lines = old_sections.get(name, [])
        if name == "路线":
            old = {route_identity(line): line for line in old_lines if CHECKBOX.match(line)}
            blocks, prefix = [], []
            for line in lines:
                if CHECKBOX.match(line):
                    blocks.append([line])
                elif blocks:
                    blocks[-1].append(line)
                else:
                    prefix.append(line)
            dated = []
            for block in blocks:
                line = block[0]
                prior = old.get(route_identity(line), "")
                created = CREATED.search(line) or CREATED.search(prior)
                created = created.group(1) if created else stamp
                done = CHECKBOX.match(line).group(1).lower() == "x"
                was_done = bool(prior and CHECKBOX.match(prior).group(1).lower() == "x")
                completed = COMPLETED.search(line) or (COMPLETED.search(prior) if was_done else None)
                completed = completed.group(1) if completed else None
                if done and not completed:
                    completed = stamp if baseline is not None and not was_done else "待核实"
                if done and completed == "待核实":
                    warnings.append(f"{route_identity(line)}：历史完成时间待核实")
                line = CREATED.sub("", COMPLETED.sub("", line))
                if done:
                    line += f" （完成：{completed}）"
                line += f" <!-- steward-created: {created} -->"
                block[0] = line
                # 历史完成时间未知的放最后；同一时间保持原顺序。
                dated.append((date_key(completed if done else created, now), block))
            lines = prefix + [line for _, block in sorted(dated, key=lambda x: x[0], reverse=True) for line in block]
        elif name == "用户待办":
            def tables(content):
                result = []
                for i, line in enumerate(content):
                    row = cells(line) if line.strip().startswith("|") else []
                    if "状态" in row and "事项" in row:
                        result.append((i, row))
                return result
            old_rows = {}
            for start, header in tables(old_lines):
                for line in old_lines[start + 2:]:
                    if not line.strip().startswith("|"):
                        break
                    row = dict(zip(header, cells(line)))
                    old_rows[row.get("编号", row.get("事项"))] = row
            # 逆向替换，保留表格以外的说明和其他表。
            for start, header in reversed(tables(lines)):
                end = start + 2
                rows = []
                while end < len(lines) and lines[end].strip().startswith("|"):
                    row = cells(lines[end])
                    if len(row) != len(header):
                        raise ValueError(
                            f"第 {first_lineno + end} 行：用户待办表列数不一致"
                            f"（应为 {len(header)} 列，实际 {len(row)} 列）：{lines[end]}"
                        )
                    rows.append(dict(zip(header, row)))
                    end += 1
                columns = header + [c for c in ("提出", "完成") if c not in header]
                dated = []
                for row in rows:
                    prior = old_rows.get(row.get("编号", row.get("事项")), {})
                    created = row.get("提出", "")
                    if date_key(created, now) == float("-inf"):
                        created = prior.get("提出") or stamp
                    row["提出"] = created
                    done = row["状态"] == "已完成"
                    completed = row.get("完成", "")
                    if completed in ("", "—", "-"):
                        completed = prior.get("完成", "") if prior.get("状态") == "已完成" else ""
                    if done and completed in ("", "—", "-"):
                        completed = stamp if baseline is not None and prior.get("状态") != "已完成" else "待核实"
                    row["完成"] = completed if done else "—"
                    if done and completed == "待核实":
                        warnings.append(f"{row.get('编号', row['事项'])}：历史完成时间待核实")
                    dated.append((date_key(completed if done else created, now), row))
                render = lambda row: "| " + " | ".join(row) + " |"
                lines[start:end] = [render(columns), render(["---"] * len(columns))] + [
                    render([row.get(c, "") for c in columns])
                    for _, row in sorted(dated, key=lambda x: x[0], reverse=True)]
        output.extend(lines)
    return "\n".join(output) + "\n", warnings
