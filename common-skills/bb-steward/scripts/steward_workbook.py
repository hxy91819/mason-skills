#!/usr/bin/env python3
"""BB 管家工作簿（Workbook）结构、容量、提交节流与收尾对账门禁。

用法：
  python3 steward_workbook.py --mode ledger-check --file docs/steward/<topic>-要求帳.md
  python3 steward_workbook.py --mode check --file docs/steward/<topic>.md
  python3 steward_workbook.py --mode should-commit --file docs/steward/<topic>.md
  python3 steward_workbook.py --mode reconcile [--live] --file docs/steward/<topic>.md

reconcile 检查路线未完成行的状态标记与用户待办的原因类别；--live 另经 `bb thread list`
核对「进行中」的线程是否还活着。
stdout 输出 JSON；退出码 0 表示通过，2 表示门禁未通过或参数错误。
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

REQUIRED_SECTIONS = ["路线", "关键决策", "用户待办"]
# 项目文档规范可能要求繁体中文，标题按同义词归一后再比对。
SECTION_ALIASES = {"路線": "路线", "關鍵決策": "关键决策", "用戶待辦": "用户待办"}
DEFAULT_MAX_NONEMPTY_LINES = 45
DEFAULT_MAX_LINE_CHARS = 180
DEFAULT_MAX_ROUTE_ITEMS = 10
DEFAULT_MAX_DECISIONS = 12

MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
WIKI_LINK_RE = re.compile(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]")
CHECKBOX_RE = re.compile(r"^-\s*\[([ xX])\]\s*(.+)$")

# 收尾对账：路线未完成行 `←` 之后的四种状态，与用户待办「为什么只能用户做」的五个类别。
STATE_RUNNING, STATE_WAITING_USER, STATE_SCHEDULED, STATE_QUEUED_AFTER = "进行中", "等用户", "定时", "排在"
STATE_KEYWORDS = (STATE_RUNNING, STATE_WAITING_USER, STATE_SCHEDULED, STATE_QUEUED_AFTER)
STATE_HINT = "← 进行中 thr_xxx / 等用户 / 定时 MM-DD HH:MM / 排在 X 后：依赖的产出"
TODO_CATEGORIES = ("凭据账号", "真机线下", "对外沟通", "不可逆上线", "用户保留")
NON_BLOCKING = {"", "-", "无", "不挡"}
THREAD_ID_RE = re.compile(r"(?<![A-Za-z0-9_])thr_[a-z0-9]{6,}")
SCHEDULE_RE = re.compile(r"(?:(\d{4})-)?(\d{1,2})-(\d{1,2})\s*(\d{1,2})[:：](\d{2})")
# 阶段编号：「阶段5」「发布 1–6」「阶段1–4、9、12–14」「Stage 2」，用来把待办的“挡住”栏和依赖对象对到路线行。
STAGE_ID_RE = re.compile(
    r"(阶段|发布|stage)\s*(\d+(?:\s*[–—\-~～至到]\s*\d+)?(?:\s*[、,，/和]\s*\d+(?:\s*[–—\-~～至到]\s*\d+)?)*)", re.I)
# BB 线程状态里只有 idle 和 error 是停着的；pending/starting/active/stopping 都算在动。
SETTLED_STATUSES = ("idle", "error")
DEFAULT_GRACE_MINUTES = 30
# 这些后台活动在跑时，空闲线程仍算在干活；Plan 模式等审批不算。
ALIVE_ACTIVITY_KEYS = ("activeBackgroundAgentCount", "activeBackgroundCommandCount", "activeGoalCount", "activeWorkflowCount")


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
            sec_name = SECTION_ALIASES.get(sec_name, sec_name)
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


LEDGER_COLUMNS = ["日期", "要求", "狀態", "結果", "材料"]
LEDGER_STATES = {"完成", "採納", "部分採納", "進行中", "待使用者", "被覆蓋", "排除"}
EMPTY_CELL = {"", "-", "—", "无", "無", "待补", "待補", "...", "…"}
EMPTY_RESULTS = {"完成", "已完成", "已採納", "採納", "已采纳", "采纳", "已處理", "已处理",
                 "處理完畢", "处理完毕", "已落實", "已落实", "已解决", "已解決", "done", "ok"}
LEDGER_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def check_ledger(text: str):
    """检查时期表与逐项结果；不推断业务真实性或要求是否记全。"""
    errors, rows, periods = [], 0, 0
    summary = dict.fromkeys(sorted(LEDGER_STATES), 0)
    in_period, tables, header, separator = False, 0, False, False
    fenced = False

    def error(lineno, message):
        errors.append(f"第 {lineno} 行：{message}")

    def close_period(lineno):
        if in_period and tables != 1:
            error(lineno, "每个时期必须且只能有一张要求表。")
        if header and not separator:
            error(lineno, "表头后缺少五列 Markdown 分隔行。")

    last_line = 1
    for lineno, raw in enumerate(text.splitlines(), 1):
        last_line = lineno
        line = raw.strip()
        if line.startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        if line.startswith("## "):
            close_period(lineno)
            in_period = bool(re.fullmatch(r"## \d{4}-\d{2}-\d{2} 起[（(].+?[）)]", line))
            if not in_period:
                error(lineno, "时期标题应为 ## <YYYY-MM-DD> 起（主题）。")
            periods += int(in_period)
            tables, header, separator = 0, False, False
            continue
        if not line.startswith("|"):
            if header and not separator:
                error(lineno, "表头后缺少五列 Markdown 分隔行。")
            header, separator = False, False
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip("|"))]
        if not in_period:
            error(lineno, "要求表必须位于时期标题下。")
        if not header:
            tables += 1
            header = True
            separator = False
            if cells != LEDGER_COLUMNS:
                error(lineno, f"表头必须为 {' | '.join(LEDGER_COLUMNS)}。")
            continue
        if not separator:
            separator = True
            if len(cells) == 5 and all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                continue
            error(lineno, "表头后缺少五列 Markdown 分隔行。")
        if len(cells) != 5:
            error(lineno, f"要求行必须有五列，当前 {len(cells)} 列。")
            continue
        rows += 1
        date, requirement, status, result, material = cells
        if date in EMPTY_CELL or requirement in EMPTY_CELL:
            error(lineno, "日期与要求不能为空。")
        if status in summary:
            summary[status] += 1
        if status not in LEDGER_STATES:
            error(lineno, f"未知状态「{status}」；仅允许 {'、'.join(sorted(LEDGER_STATES))}。")
        normalized = re.sub(r"[\s`*。.!！；;]+", "", result).lower()
        vacuous = (normalized in EMPTY_RESULTS or bool(re.fullmatch(
            r"(?:已|已经|已經)?(?:全部|全數|全部都|均|都)?(?:完成|處理|处理|採納|采纳|落實|落实|解决|解決)(?:了|完畢|完毕)?",
            normalized)))
        if result in EMPTY_CELL or vacuous:
            error(lineno, "结果须写具体结论，不能只写完成／已完成等空话。")
        if status in {"完成", "採納"}:
            # 文件地址也可定位本机材料；裸预览名不是地址。
            located = (any(m.group(2).strip() not in EMPTY_CELL for m in LEDGER_LINK_RE.finditer(material))
                       or re.search(r"https?://\S+|(?:/|\./|\.\./|~/)[^\s、；;]+|\bPR\s*#?\d+|\b[0-9a-f]{7,40}\b|[會会][話话]回[覆复]", material))
            if not located:
                error(lineno, f"{status}须有材料链接、文件地址、commit、PR 或明确写會話回覆。")
        if status == "被覆蓋":
            target = re.search(
                r"(?:被|由)\s*(.+?)\s*(?:取代|替代|覆蓋|覆盖)|"
                r"(?:取代者|替代者|覆蓋者|覆盖者|改為|改为|改由)[:：]?\s*(.+)", result)
            if not target or next((g for g in target.groups() if g), "").strip() in EMPTY_CELL | {"後續要求", "后续要求", "後續需求", "后续需求", "其他要求", "其他需求"}:
                error(lineno, "被覆蓋的结果须指出被哪一列或哪件事取代。")
        if status == "排除":
            no_reason = re.fullmatch(
                r"(?:已|已经|已經)?(?:排除|取消|不做|不採納|不采纳|不執行|不执行)"
                r"(?:(?:這|这|該|该|此)(?:個|个)?(?:要求|需求|事項|事项|任務|任务))?", normalized)
            if result in EMPTY_CELL or vacuous or no_reason or normalized in {"無需處理", "无需处理"}:
                error(lineno, "排除须在结果写原因。")
    close_period(last_line)
    if not periods:
        errors.append("缺少时期标题：## <YYYY-MM-DD> 起（主题）。")
    return {"ok": not errors, "stats": {"periods": periods, "rows": rows}, "summary": summary, "errors": errors}


def check_workbook_file(file_path: Path, **check_args):
    text = file_path.read_text()
    res = check_workbook(text, **check_args)
    # 标头是第一个二级标题前的内容；只检查要求帐入口，不扩大到一般材料链接。
    for line in text.splitlines():
        if line.startswith("## "):
            break
        for match in LEDGER_LINK_RE.finditer(line):
            label, target = match.groups()
            target = target.strip().strip("<>")
            url = urlsplit(target)
            path = unquote(url.path)
            if not (re.search(r"要求[帳帐]", label) or re.search(r"-要求[帳帐]\.md$", path)):
                continue
            if url.scheme or url.netloc or not path or not (file_path.parent / path).is_file():
                res["errors"].append(f"要求帐链接必须指向存在的本地文件：{target}")
    res["ok"] = not res["errors"]
    return res


def route_stem(body: str) -> str:
    """路线行冒号或左括号前的阶段主干名称，作为跨编辑稳定的行标识。"""
    return re.split(r"[（(—\-:：]", body.split("←", 1)[0].strip(), maxsplit=1)[0].strip()


def parse_schedule(text: str, now: datetime):
    """解析 `MM-DD HH:MM`（可带年份）为本地时间；省略年份时取离 now 最近的那一年。"""
    m = SCHEDULE_RE.search(text)
    if not m:
        return None
    year, month, day, hour, minute = m.groups()
    try:
        if year:
            return datetime(int(year), int(month), int(day), int(hour), int(minute))
        candidates = [datetime(now.year + d, int(month), int(day), int(hour), int(minute)) for d in (-1, 0, 1)]
    except ValueError:
        return None
    return min(candidates, key=lambda c: abs((c - now).total_seconds()))


def parse_marker(body: str, now: datetime):
    """解析未完成行 `←` 之后的状态。返回 (state, detail)：state 为四种关键词之一，无效时为 None、detail 写原因。"""
    if "←" not in body:
        return None, "缺状态"
    marker = body.rsplit("←", 1)[1].strip()
    for keyword in STATE_KEYWORDS:
        if not marker.startswith(keyword):
            continue
        rest = marker[len(keyword):]
        if keyword == STATE_RUNNING and not THREAD_ID_RE.search(body):
            return None, "进行中但没写线程 ID"
        if keyword == STATE_SCHEDULED and parse_schedule(rest, now) is None:
            return None, "定时没写 MM-DD HH:MM"
        if keyword == STATE_QUEUED_AFTER:
            reason = re.split(r"[:：]", rest, maxsplit=1)
            if "后" not in reason[0] or len(reason) < 2 or not reason[1].strip():
                return None, "排在…后 没写依赖的产出"
        return keyword, marker
    return None, f"状态「{marker[:12]}」不在四种之内"


def state_signature(body: str):
    """状态签名：进行中/等用户只看关键词（换线程 ID 不算跃迁），定时看时间，排在看依赖对象。"""
    if "←" not in body:
        return None
    marker = body.rsplit("←", 1)[1].strip()
    if marker.startswith(STATE_SCHEDULED):
        m = SCHEDULE_RE.search(marker)
        return (STATE_SCHEDULED, m.group(0) if m else marker)
    if marker.startswith(STATE_QUEUED_AFTER):
        return (STATE_QUEUED_AFTER, re.split(r"[:：]", marker, maxsplit=1)[0])
    for keyword in (STATE_RUNNING, STATE_WAITING_USER):
        if marker.startswith(keyword):
            return (keyword,)
    return ("其他", marker)


def table_cells(line: str):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_todos(parsed):
    """解析用户待办表格；按表头名取列，缺表头时按模板列序。"""
    columns = {"状态": 0, "事项": 1, "为什么只能用户做": 2, "挡住": 3, "提出": 4}
    todos = []
    for lineno, raw in parsed["sections"].get("用户待办", []):
        s = raw.strip()
        if not (s.startswith("|") and s.endswith("|")):
            continue
        cells = table_cells(s)
        if all(set(c) <= {"-", ":", " "} for c in cells):
            continue
        if cells and cells[0] == "状态":
            columns = {name: idx for idx, name in enumerate(cells)}
            continue

        def cell(name):
            idx = columns.get(name)
            return cells[idx] if idx is not None and idx < len(cells) else ""

        todos.append({
            "line": lineno,
            "status": cell("状态"),
            "item": cell("事项"),
            "reason": cell("为什么只能用户做"),
            "blocks": cell("挡住"),
        })
    return todos


def plain_label(text: str, limit=24) -> str:
    s = WIKI_LINK_RE.sub(r"\1", MD_LINK_RE.sub(r"\1", text)).replace("`", "").replace("*", "").strip()
    return s if len(s) <= limit else s[:limit] + "…"


def row_head(body: str) -> str:
    """路线行第一个冒号前的标题部分（先展开 Markdown 链接，免得 URL 里的冒号截断）。"""
    head = MD_LINK_RE.sub(r"\1", body.split("←", 1)[0])
    return re.split(r"[:：]", head, maxsplit=1)[0]


def stage_ids(text: str):
    ids = set()
    for m in STAGE_ID_RE.finditer(text):
        prefix = m.group(1).lower()
        for part in re.split(r"[、,，/和]", m.group(2)):
            nums = [int(n) for n in re.findall(r"\d+", part)]
            if len(nums) >= 2 and 0 <= nums[1] - nums[0] < 100:
                ids.update((prefix, n) for n in range(nums[0], nums[1] + 1))
            elif nums:
                ids.add((prefix, nums[0]))
    return ids


def squash(text: str) -> str:
    return re.sub(r"\s+", "", plain_label(text, limit=10**6)).lower()


def refers_to(text: str, head: str) -> bool:
    """text（待办“挡住”栏或依赖对象）是否指向标题为 head 的路线行：有阶段编号时比编号，否则比去空白后的标题。"""
    ids = stage_ids(head)
    if ids:
        return bool(ids & stage_ids(text))
    h, t = squash(head), squash(text)
    return len(h) >= 2 and len(t) >= 2 and (h in t or t in h)


def normalize_thread(raw: dict) -> dict:
    activity = raw.get("activity") or {}
    return {
        "id": raw.get("id"),
        "status": raw.get("status"),
        "archived": bool(raw.get("archivedAt")),
        # queuedWork 为 waiting 才是还有消息等着送达；failed 是送达失败，不算在动。
        "queued": raw.get("queuedWork") == "waiting",
        "interaction": bool(raw.get("hasPendingInteraction")),
        "background": any((activity.get(k) or 0) > 0 for k in ALIVE_ACTIVITY_KEYS),
        "updated_at": (raw.get("updatedAt") or 0) / 1000,
        "parent": raw.get("parentThreadId"),
        "provider": raw.get("providerId"),
    }


def thread_state(info, now_ts: float, grace_seconds: float) -> str:
    """alive=在跑/排队/有后台活动；recent=刚结束不到宽限期（完成通知可能还在路上）。"""
    if info is None:
        return "missing"
    if info["archived"]:
        return "archived"
    if info["interaction"]:
        return "interaction"
    if info["status"] not in SETTLED_STATUSES or info["queued"] or info["background"]:
        return "alive"
    if info["status"] == "error":
        return "failed"
    if now_ts - info["updated_at"] < grace_seconds:
        return "recent"
    return "stopped"


def describe_thread(tid: str, state: str, info, now_ts: float) -> str:
    if state == "stopped":
        hours = (now_ts - info["updated_at"]) / 3600
        return f"{tid} 已空闲 {hours:.1f} 小时"
    return f"{tid} " + {"missing": "找不到", "archived": "已归档", "failed": "失败且没有排队的重试",
                        "interaction": "在等待交互"}.get(state, state)


def bb_thread_list(*args):
    """调用 `bb thread list ... --json`，返回规范化线程列表；失败抛 RuntimeError。"""
    try:
        res = subprocess.run(["bb", "thread", "list", *args, "--json"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"bb thread list 调用失败：{exc}") from exc
    try:
        data = json.loads(res.stdout)
    except ValueError as exc:
        raise RuntimeError(f"bb thread list 返回非 JSON：{res.stderr.strip()[:300]}") from exc
    if res.returncode or not isinstance(data, list):
        raise RuntimeError(f"bb thread list 失败：{res.stdout.strip()[:300] or res.stderr.strip()[:300]}")
    return [normalize_thread(t) for t in data]


def fetch_threads(ids):
    """按 ID 批量查线程，返回 {id: info}；查不到的 ID 不出现在结果里。"""
    found = {}
    ids = sorted(set(ids))
    for start in range(0, len(ids), 200):
        args = []
        for tid in ids[start:start + 200]:
            args += ["--thread", tid]
        for info in bb_thread_list(*args):
            found[info["id"]] = info
    return found


def running_thread_ids(text: str):
    """仅提取未完成且标为「进行中」的路线引用；不改变对账的 referenced_threads 口径。"""
    ids = set()
    for _, raw in parse_workbook(text)["sections"].get("路线", []):
        match = CHECKBOX_RE.match(raw.strip())
        if match and match.group(1).lower() != "x":
            body = match.group(2)
            if parse_marker(body, datetime.now())[0] == STATE_RUNNING:
                ids.update(THREAD_ID_RE.findall(body))
    return sorted(ids)


def reconcile_workbook(text: str, now: datetime | None = None, threads: dict | None = None,
                       unlisted_alive: int = 0, grace_minutes: int = DEFAULT_GRACE_MINUTES):
    """收尾对账。threads 为 None 时只做静态检查；给出时核对「进行中」线程的存活。

    unlisted_alive>0 表示管家另有未写进路线的在跑子线程（工作簿取自远端、可能还没提交新线程 ID），
    这时「进行中但线程已停」降为 minor。problems 里 severity=nudge 的项让 ok 为 False。
    """
    now = now or datetime.now()
    now_ts = now.timestamp()
    grace = grace_minutes * 60
    parsed = parse_workbook(text)
    problems = []
    stats = {"open_rows": 0, STATE_RUNNING: 0, STATE_WAITING_USER: 0, STATE_SCHEDULED: 0, STATE_QUEUED_AFTER: 0}
    referenced = set()

    def add(kind, severity, line, label, detail):
        problems.append({"kind": kind, "severity": severity, "line": line, "label": label, "detail": detail})

    rows = []
    for lineno, raw in parsed["sections"].get("路线", []):
        m = CHECKBOX_RE.match(raw.strip())
        if m:
            rows.append({"line": lineno, "done": m.group(1).lower() == "x", "body": m.group(2), "head": row_head(m.group(2))})
    todos = parse_todos(parsed)
    blocking = [t for t in todos if t["status"] == "待办" and t["blocks"] not in NON_BLOCKING]

    for row in rows:
        lineno, body = row["line"], row["body"]
        referenced.update(THREAD_ID_RE.findall(body))
        if row["done"]:
            continue
        stats["open_rows"] += 1
        label = plain_label(route_stem(body))
        state, detail = parse_marker(body, now)
        if state is None:
            add("no_state", "nudge", lineno, label, detail)
            continue
        stats[state] += 1
        if state == STATE_WAITING_USER:
            if not any(refers_to(t["blocks"], row["head"]) for t in blocking):
                add("user_wait_unbacked", "nudge", lineno, label, "标等用户，但没有“挡住”栏指向这一行的未完成待办")
        elif state == STATE_QUEUED_AFTER:
            target = re.split(r"[:：]", detail, maxsplit=1)[0][len(STATE_QUEUED_AFTER):].rsplit("后", 1)[0].strip()
            # 依赖对上本簿路线行且都已完成时，这一行已经可以推进；对不上的视为外部依赖，不判。
            matched = [r for r in rows if r is not row and refers_to(target, r["head"])]
            if matched and all(r["done"] for r in matched):
                add("dependency_done", "nudge", lineno, label, f"前置「{plain_label(target)}」已完成，这一行该推进了")
        elif state == STATE_SCHEDULED:
            due = parse_schedule(detail[len(STATE_SCHEDULED):], now)
            if due is not None and now_ts - due.timestamp() > grace:
                add("schedule_passed", "nudge", lineno, label, f"定时 {due:%m-%d %H:%M} 已过")
        elif state == STATE_RUNNING and threads is not None:
            ids = THREAD_ID_RE.findall(body)
            states = {tid: thread_state(threads.get(tid), now_ts, grace) for tid in ids}
            waiting = [tid for tid, st in states.items() if st == "interaction"]
            if waiting:
                add("child_waiting", "nudge", lineno, label, "、".join(f"{tid} 在等待交互" for tid in waiting))
            if not waiting and not any(st in ("alive", "recent") for st in states.values()):
                detail = "标进行中，但" + "、".join(describe_thread(tid, st, threads.get(tid), now_ts) for tid, st in states.items())
                if unlisted_alive:
                    add("stale_running", "minor", lineno, label, detail + f"（另有 {unlisted_alive} 条未写进路线的子线程在跑）")
                else:
                    add("stale_running", "nudge", lineno, label, detail)

    for todo in (t for t in todos if t["status"] == "待办"):
        if not todo["reason"].startswith(TODO_CATEGORIES):
            severity = "nudge" if todo in blocking else "minor"
            add("todo_category_missing", severity, todo["line"], plain_label(todo["item"]),
                "用户待办原因没以类别开头（" + "、".join(TODO_CATEGORIES) + "）")

    return {
        "ok": not any(p["severity"] == "nudge" for p in problems),
        "stats": stats,
        "referenced_threads": sorted(referenced),
        "problems": problems,
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
            route_sig.append((route_stem(m.group(2)), checked, state_signature(m.group(2))))

    decision_sig = []
    for _, raw in parsed["sections"].get("关键决策", []):
        s = raw.strip()
        if s.startswith("- "):
            decision_sig.append(re.sub(r"\s+", " ", s[2:].strip()))

    todo_sig = [(t["status"], t["item"], t["blocks"]) for t in parse_todos(parsed)]

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
    check_res = check_workbook_file(file_path, **check_args)
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
    p.add_argument("--mode", required=True, choices=["check", "should-commit", "reconcile", "ledger-check"],
                   help="ledger-check=校验要求帐；check=校验结构、容量与要求帐入口；should-commit=校验并判断相对 HEAD 是否有实质状态变化；reconcile=收尾对账")
    p.add_argument("--file", required=True, help="工作簿或要求帐 Markdown 文件路径")
    p.add_argument("--live", action="store_true", help="reconcile 时经 bb thread list 核对「进行中」线程是否还活着")
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
        res = {"file": str(fpath), **check_workbook_file(fpath, **check_args)}
    elif args.mode == "ledger-check":
        res = {"file": str(fpath), **check_ledger(fpath.read_text())}
    elif args.mode == "reconcile":
        text = fpath.read_text()
        threads, warnings = None, []
        if args.live:
            try:
                threads = fetch_threads(reconcile_workbook(text)["referenced_threads"])
            except RuntimeError as exc:
                warnings.append(f"线程核对跳过：{exc}")
        res = {"file": str(fpath), **reconcile_workbook(text, threads=threads)}
        if warnings:
            res["warnings"] = warnings
    else:
        res = should_commit_workbook(fpath, check_args)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
