"""Workbook and ledger vocabulary shared by the steward scripts.

English is canonical. The Chinese literals below are backward-compatibility aliases: workbooks and ledgers
written before the English vocabulary keep validating, and the formatter keeps each file in its own language.
"""
import re

# ---------- Workbook sections ----------

ROUTE, DECISIONS, TODOS = "Route", "Key decisions", "User to-dos"
REQUIRED_SECTIONS = [ROUTE, DECISIONS, TODOS]
SECTION_ALIASES = {
    "路线": ROUTE, "路線": ROUTE,
    "关键决策": DECISIONS, "關鍵決策": DECISIONS,
    "用户待办": TODOS, "用戶待辦": TODOS,
}


def section_name(heading: str) -> str:
    return SECTION_ALIASES.get(heading, heading)


# ---------- Route states (after `←`) ----------

RUNNING, WAITING_USER, SCHEDULED, QUEUED_AFTER = "in progress", "waiting on user", "scheduled", "after"
STATES = (RUNNING, WAITING_USER, SCHEDULED, QUEUED_AFTER)
STATE_ALIASES = {"进行中": RUNNING, "等用户": WAITING_USER, "定时": SCHEDULED, "排在": QUEUED_AFTER}
STATE_HINT = "← in progress thr_xxx / waiting on user / scheduled MM-DD HH:MM <what> / after <item>: <dependent output>"
_STATE_RE = re.compile(r"(in progress|waiting on user|scheduled|after)\b", re.I)


def match_state(marker: str):
    """Return (state, literal, rest) for the state keyword `marker` starts with, or None."""
    for literal, state in STATE_ALIASES.items():
        if marker.startswith(literal):
            return state, literal, marker[len(literal):]
    m = _STATE_RE.match(marker)
    if m:
        return m.group(1).lower(), m.group(0), marker[m.end():]
    return None


def queued_target(literal: str, rest: str):
    """Split the rest of a queued-after marker into (dependency, dependent output); None when malformed."""
    parts = re.split(r"[:：]", rest, maxsplit=1)
    head = parts[0]
    output = parts[1].strip() if len(parts) > 1 else ""
    if literal == "排在":  # Legacy form: `排在 <item> 后：<output>`.
        if "后" not in head:
            return None
        head = head.rsplit("后", 1)[0]
    return (head.strip(), output) if output else None


# ---------- User to-dos ----------

TODO_COLUMNS = ("ID", "Status", "Item", "Background", "Recommendation", "Why only the user", "Blocks", "Raised", "Done")
TODO_COLUMN_ALIASES = {
    "编号": "ID", "状态": "Status", "事项": "Item", "背景": "Background", "建议": "Recommendation",
    "为什么只能用户做": "Why only the user", "挡住": "Blocks", "提出": "Raised", "完成": "Done",
}
TODO_COLUMN_LOCAL = {"zh": {v: k for k, v in TODO_COLUMN_ALIASES.items()}, "en": {c: c for c in TODO_COLUMNS}}
TODO_OPEN, TODO_DONE = "open", "done"
TODO_STATUS_ALIASES = {"待办": TODO_OPEN, "已完成": TODO_DONE}
TODO_CATEGORIES = ("credentials", "physical device", "external communication", "irreversible launch", "user reserved")
TODO_CATEGORY_ALIASES = ("凭据账号", "真机线下", "对外沟通", "不可逆上线", "用户保留")
NON_BLOCKING = {"", "-", "none", "not blocking", "无", "不挡"}


def todo_column(name: str) -> str:
    return TODO_COLUMN_ALIASES.get(name, name)


def todo_status(value: str) -> str:
    value = value.strip()
    return TODO_STATUS_ALIASES.get(value, value.lower())


def has_category(reason: str) -> bool:
    return reason.startswith(TODO_CATEGORY_ALIASES) or reason.lower().startswith(TODO_CATEGORIES)


def is_blocking(blocks: str) -> bool:
    return blocks.strip().lower() not in NON_BLOCKING


# ---------- Route timeline ----------

UNVERIFIED = {"zh": "待核实", "en": "unverified"}
COMPLETED_RE = re.compile(r" (?:（完成：(?P<zh>.*?)）|\(done: (?P<en>.*?)\))")


def completed_suffix(value: str, lang: str) -> str:
    return f" （完成：{value}）" if lang == "zh" else f" (done: {value})"


# ---------- Requirement ledger ----------

LEDGER_COLUMNS = ["Date", "Requirement", "Status", "Result", "Material"]
LEDGER_COLUMN_ALIASES = ["日期", "要求", "狀態", "結果", "材料"]
DONE, ADOPTED, PARTIAL, IN_PROGRESS, AWAITING_USER, SUPERSEDED, EXCLUDED = (
    "Done", "Adopted", "Partially adopted", "In progress", "Awaiting user", "Superseded", "Excluded")
LEDGER_STATES = (DONE, ADOPTED, PARTIAL, IN_PROGRESS, AWAITING_USER, SUPERSEDED, EXCLUDED)
LEDGER_STATE_ALIASES = {"完成": DONE, "採納": ADOPTED, "部分採納": PARTIAL, "進行中": IN_PROGRESS,
                        "待使用者": AWAITING_USER, "被覆蓋": SUPERSEDED, "排除": EXCLUDED}
# The BB steward plugin UI reads these two counts from ledger-check `summary` under their legacy keys.
PLUGIN_SUMMARY_KEYS = {IN_PROGRESS: "進行中", AWAITING_USER: "待使用者"}
PERIOD_RE = re.compile(r"## \d{4}-\d{2}-\d{2} (?:onward ?\(.+?\)|起[（(].+?[）)])")
PERIOD_HINT = "## <YYYY-MM-DD> onward (<topic>)"
SESSION_REPLY_RE = r"(?i:session\s*reply)|[會会][話话]回[覆复]"


def ledger_state(value: str):
    if value in LEDGER_STATE_ALIASES:
        return LEDGER_STATE_ALIASES[value]
    return next((s for s in LEDGER_STATES if s.lower() == value.lower()), None)


# ---------- Workbook header entry to the ledger ----------

LEDGER_LABEL_RE = re.compile(r"要求[帳帐]|requirements? ledger", re.I)
LEDGER_TARGET_RE = re.compile(r"-(?:要求[帳帐]|requirements)\.md(?:[#?]|$)")
HISTORY_LABELS = {"Requirements ledger (history log)", "要求帐（历史流水账）"}
