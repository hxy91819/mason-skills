#!/usr/bin/env python3
"""校验 Epic、Story、Agent JSON 状态源及内容预算，并生成或查询项目进展。

参数定义：check/status/render 接收 Epic 文件和 Story 目录；write/patch/template 接收 Agent JSON 路径。
输出定义：check/status 只读；write/patch 校验后规范化写入 Agent JSON；render 先同步依赖阻塞，再整份生成项目进展。
退出码：0 成功，1 文档或仪表盘校验失败，2 I/O 或命令行错误。
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Sequence, Tuple


GENERATED_NOTICE = "> 本文由脚本根据 Agent JSON 状态源生成，请勿手工修改。"
SCHEMA_VERSION = 1
KIND_CARD = "agent-card"
KIND_RISK = "risk-register"
KIND_REFERENCE = "agent-reference"
STATUS_LABELS = {
    "todo": "待开始",
    "in_progress": "进行中",
    "blocked": "阻塞",
    "done": "已完成",
}
STORY_ID_RE = re.compile(r"^STORY-(\d{2})(?:\.([1-9]\d*))?$")
EPIC_ID_RE = re.compile(r"^EPIC-[A-Z0-9][A-Z0-9-]*$")
COVERAGE_ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9_.:-]*$")
GATE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
DECISION_ITEM_RE = re.compile(r"^([1-9]\d*)\.\s+.+?(?=^[1-9]\d*\.\s+|\Z)", re.MULTILINE | re.DOTALL)
FENCE_LINE_RE = re.compile(r"^```[^\n]*$", re.MULTILINE)
FENCED_CODE_BLOCK_RE = re.compile(
    r"^```([^\s`]*)[ \t]*\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL
)
DEPENDENCY_UNFINISHED_RE = re.compile(r"^(STORY-\d{2}(?:\.[1-9]\d*)?) 未完成$")
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]+\)")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
MARKDOWN_MARKUP_RE = re.compile(r"[\s`*_>#|:\-\[\](){}\\]+")
HUMAN_DYNAMIC_LINE_RE = re.compile(
    r"^(?:-\s*)?(状态|负责人|阻塞|完成进度|当前进展)[：:]\s*\S", re.MULTILINE
)
HUMAN_DYNAMIC_HEADING_RE = re.compile(
    r"^##\s+(当前状态|项目状态|门禁状态|关键基线)\s*$", re.MULTILINE
)
MIN_CHECKLIST_ITEMS = 3
MAX_CHECKLIST_ITEMS = 7
MAX_STORIES = 7
MAX_CHECKLIST_ITEM_CHARS = 120
OVERVIEW_CONTENT_LIMIT = 1500
EPIC_CONTENT_LIMIT = 3000
STORY_CONTENT_LIMIT = 2200
DASHBOARD_CONTENT_LIMIT = 3000
EPIC_HEADINGS = ("愿景", "全局设计", "成功标准", "Story 地图", "项目边界", "权威文档")
STORY_HEADINGS = ("愿景", "范围", "关键决策", "验收标准")
DASHBOARD_HEADINGS = ("Epic / Story 一览", "风险与阻塞")
OVERVIEW_HEADINGS = ("项目一览", "Epic", "Agent 入口")
MAX_RISK_ITEMS = 6
CARD_STRING_FIELDS = (
    "goal",
    "decision_boundary",
    "technical_plan",
    "authoritative_inputs",
    "claim_checks",
    "steps",
    "verification",
    "stop_conditions",
    "handoff",
)
CARD_FIELD_ORDER = (
    "kind",
    "schema_version",
    "story",
    "intent_version",
    "status",
    "owner",
    "blocker",
    "status_updated",
    "refreshed",
    "code_baseline",
    "owns",
    "verifies",
    *CARD_STRING_FIELDS[:5],
    "checklist",
    *CARD_STRING_FIELDS[5:],
)
RISK_FIELD_ORDER = (
    "kind",
    "schema_version",
    "epic",
    "updated",
    "pending_decisions",
    "watch_items",
)
REFERENCE_FIELD_ORDER = ("kind", "schema_version", "id", "title", "updated", "body")
RISK_LIST_FIELDS = ("pending_decisions", "watch_items")
RISK_HEADING_FIELDS = {
    "待用户决策": "pending_decisions",
    "后续关注": "watch_items",
}


class DocumentError(Exception):
    """表示文档格式或项目状态不满足契约。"""


@dataclass(frozen=True)
class WorkItem:
    path: Path
    metadata: Dict[str, object]
    body: str
    headings: Tuple[str, ...]

    @property
    def item_id(self) -> str:
        return str(self.metadata["id"])

    @property
    def title(self) -> str:
        return str(self.metadata["title"])

    @property
    def depends_on(self) -> Tuple[str, ...]:
        value = self.metadata.get("depends_on", [])
        return tuple(str(item) for item in value) if isinstance(value, list) else ()

    @property
    def content_chars(self) -> int:
        return visible_char_count(self.body)


@dataclass(frozen=True)
class AgentCard:
    path: Path
    data: Dict[str, object]

    @property
    def owns(self) -> Tuple[str, ...]:
        value = self.data.get("owns", [])
        return tuple(str(item) for item in value) if isinstance(value, list) else ()

    @property
    def verifies(self) -> Tuple[str, ...]:
        value = self.data.get("verifies", [])
        return tuple(str(item) for item in value) if isinstance(value, list) else ()

    @property
    def status(self) -> str:
        return str(self.data.get("status", ""))

    @property
    def owner(self) -> str:
        return str(self.data.get("owner", ""))

    @property
    def blocker(self) -> str:
        return str(self.data.get("blocker", ""))

    @property
    def checklist(self) -> Tuple[Tuple[bool, str], ...]:
        items = self.data.get("checklist", [])
        if not isinstance(items, list):
            return ()
        result: List[Tuple[bool, str]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            result.append((bool(item.get("done")), str(item.get("text", "")).strip()))
        return tuple(result)


@dataclass(frozen=True)
class RiskRegister:
    path: Path
    data: Dict[str, object]

    def items(self, heading: str) -> Tuple[str, ...]:
        field = RISK_HEADING_FIELDS[heading]
        value = self.data.get(field, [])
        if not isinstance(value, list):
            return ()
        return tuple(str(item).strip() for item in value if str(item).strip())


def visible_char_count(text: str) -> int:
    """按人实际阅读的正文计数，排除链接目标、注释、空白和 Markdown 标记。"""
    text = LINK_RE.sub(r"\1", text)
    text = HTML_COMMENT_RE.sub("", text)
    return len(MARKDOWN_MARKUP_RE.sub("", text))


def story_order_key(story_id: str) -> Tuple[int, int, str]:
    """按主编号和插入号排序；无效 ID 留到格式校验并排在有效 ID 之后。"""
    match = STORY_ID_RE.fullmatch(story_id)
    if not match:
        return (sys.maxsize, sys.maxsize, story_id)
    return (int(match.group(1)), int(match.group(2) or 0), "")


def dump_json(data: Dict[str, object]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _order_keys(data: Dict[str, object], field_order: Sequence[str]) -> Dict[str, object]:
    ordered: Dict[str, object] = {}
    for key in field_order:
        if key in data:
            ordered[key] = data[key]
    for key, value in data.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def canonicalize_document(data: Dict[str, object]) -> Dict[str, object]:
    kind = str(data.get("kind", ""))
    if kind == KIND_CARD:
        return _order_keys(data, CARD_FIELD_ORDER)
    if kind == KIND_RISK:
        return _order_keys(data, RISK_FIELD_ORDER)
    return _order_keys(data, REFERENCE_FIELD_ORDER)


def load_json_document(path: Path) -> Dict[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DocumentError(f"无法读取 {path}: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DocumentError(f"{path}: JSON 无效: {exc}") from exc
    if not isinstance(data, dict):
        raise DocumentError(f"{path}: Agent 文档必须是 JSON 对象")
    return data


def write_json_document(path: Path, data: Dict[str, object]) -> None:
    _atomic_write(path, dump_json(canonicalize_document(data)))


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_value(raw: str, path: Path, line_number: int) -> object:
    value = raw.strip()
    if value.startswith("["):
        if not value.endswith("]"):
            raise DocumentError(f"{path}:{line_number}: 列表缺少右方括号")
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_strip_quotes(item.strip()) for item in inner.split(",")]
    return _strip_quotes(value)


def _parse_frontmatter(path: Path, text: str) -> Tuple[Dict[str, object], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise DocumentError(f"{path}: 文件必须以 YAML frontmatter 开始")
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise DocumentError(f"{path}: frontmatter 缺少结束标记 ---") from exc

    metadata: Dict[str, object] = {}
    for index, line in enumerate(lines[1:end], 2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise DocumentError(f"{path}:{index}: frontmatter 仅支持 key: value")
        key, raw_value = line.split(":", 1)
        key = key.strip()
        if not key or key in metadata:
            raise DocumentError(f"{path}:{index}: key 为空或重复: {key!r}")
        metadata[key] = _parse_value(raw_value, path, index)
    return metadata, "\n".join(lines[end + 1 :]).strip() + "\n"


def _section(body: str, heading: str) -> str:
    match = re.search(rf"^##\s+{re.escape(heading)}\s*$", body, re.MULTILINE)
    if not match:
        return ""
    next_heading = re.search(r"^##\s+", body[match.end() :], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(body)
    return body[match.end() : end]


def load_item(path: Path) -> WorkItem:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DocumentError(f"无法读取 {path}: {exc}") from exc
    metadata, body = _parse_frontmatter(path, text)
    headings = tuple(match.group(1).strip() for match in HEADING_RE.finditer(body))
    return WorkItem(path, metadata, body, headings)


def _require_fields(item: WorkItem, fields: Sequence[str]) -> List[str]:
    return [f"{item.path}: 缺少 frontmatter 字段 {field}" for field in fields if field not in item.metadata]


def _reject_fields(item: WorkItem, fields: Sequence[str]) -> List[str]:
    return [
        f"{item.path}: 人读文档不保存动态字段 {field}，请改为维护 Agent JSON"
        for field in fields
        if field in item.metadata
    ]


def _reject_human_dynamic_body(path: Path, text: str, errors: List[str]) -> None:
    """拒绝人读正文里的手工状态缓存，自动生成的项目进展不调用本检查。"""
    for match in HUMAN_DYNAMIC_LINE_RE.finditer(text):
        errors.append(f"{path}: 人读文档不保存手工动态状态“{match.group(1)}”")
    for match in HUMAN_DYNAMIC_HEADING_RE.finditer(text):
        errors.append(f"{path}: 人读文档不保存手工动态章节“{match.group(1)}”")


def _validate_date(item: WorkItem, errors: List[str]) -> None:
    value = str(item.metadata.get("updated", ""))
    try:
        date.fromisoformat(value)
    except ValueError:
        errors.append(f"{item.path}: updated 必须是 YYYY-MM-DD，当前为 {value!r}")


def _validate_iso_date(path: Path, field: str, value: object, errors: List[str]) -> None:
    try:
        date.fromisoformat(str(value))
    except ValueError:
        errors.append(f"{path}: {field} 必须是 YYYY-MM-DD，当前为 {value!r}")


def _validate_sections(item: WorkItem, required: Sequence[str], errors: List[str]) -> None:
    for heading in required:
        count = item.headings.count(heading)
        if count == 0:
            errors.append(f"{item.path}: 缺少二级标题 ## {heading}")
        elif count > 1:
            errors.append(f"{item.path}: 二级标题 ## {heading} 只能出现一次")
        elif not _section(item.body, heading).strip():
            errors.append(f"{item.path}: ## {heading} 不能为空")


def _validate_heading_contract(
    path: Path, headings: Sequence[str], allowed: Sequence[str], errors: List[str]
) -> None:
    unexpected = [heading for heading in headings if heading not in allowed]
    if unexpected:
        errors.append(f"{path}: 存在不允许的二级标题: {', '.join(unexpected)}")
        return
    duplicates = sorted({heading for heading in headings if headings.count(heading) > 1})
    if duplicates:
        errors.append(f"{path}: 二级标题重复: {', '.join(duplicates)}")
        return
    expected = tuple(heading for heading in allowed if heading in headings)
    if tuple(headings) != expected:
        errors.append(f"{path}: 二级标题顺序必须为: {' -> '.join(allowed)}")


def _validate_flat_document(
    path: Path,
    body: str,
    errors: List[str],
    *,
    allow_tables: bool,
    allow_code_blocks: bool = False,
) -> None:
    if not allow_code_blocks and "```" in body:
        errors.append(f"{path}: 本层文档不允许代码块，命令和实现细节应放入 agent/ 或代码")
    if re.search(r"^#{3,6}\s+", body, re.MULTILINE):
        errors.append(f"{path}: 本层文档不允许三级及更深标题")
    if not allow_tables and re.search(r"^\|", body, re.MULTILINE):
        errors.append(f"{path}: 本层文档不使用表格，请改成短句或链接到下层资料")


def _validate_budget(path: Path, text: str, limit: int, errors: List[str]) -> None:
    actual = visible_char_count(text)
    if actual > limit:
        errors.append(f"{path}: 正文有效字符 {actual} 超过上限 {limit}，请下沉细节并改为链接")


def _validate_global_design(epic: WorkItem, errors: List[str]) -> None:
    """架构图只属于全局设计；独立能力可以各自使用一张图。"""
    section = _section(epic.body, "全局设计")
    if not section.strip():
        return

    section_blocks = tuple(FENCED_CODE_BLOCK_RE.finditer(section))
    if not section_blocks:
        errors.append(f"{epic.path}: ## 全局设计必须包含至少一张 Mermaid 或 fenced text 架构图")
    for block in section_blocks:
        language = block.group(1)
        diagram = block.group(2).strip()
        if language not in {"mermaid", "text"}:
            errors.append(f"{epic.path}: ## 全局设计的架构图只能使用 mermaid 或 text 代码块")
        if not diagram:
            errors.append(f"{epic.path}: ## 全局设计的架构图不能为空")

    all_blocks = tuple(FENCED_CODE_BLOCK_RE.finditer(epic.body))
    fence_lines = tuple(FENCE_LINE_RE.finditer(epic.body))
    if len(all_blocks) != len(section_blocks) or len(fence_lines) != 2 * len(all_blocks):
        errors.append(f"{epic.path}: 只能在 ## 全局设计中保留完整的架构图代码块")


def _validate_key_decisions(story: WorkItem, card: AgentCard, errors: List[str]) -> None:
    """确保人读决策可追溯到用户确认与 Agent 建议。"""
    section = _section(story.body, "关键决策").strip()
    if not section:
        return

    decisions = tuple(DECISION_ITEM_RE.finditer(section))
    if not decisions:
        errors.append(f"{story.path}: ## 关键决策必须使用从 1 开始的连续编号")
        return
    numbers = tuple(int(match.group(1)) for match in decisions)
    if numbers != tuple(range(1, len(decisions) + 1)):
        errors.append(f"{story.path}: ## 关键决策必须使用从 1 开始的连续编号")

    has_pending = False
    for number, match in zip(numbers, decisions):
        decision = match.group(0)
        for label in ("决定者：", "Agent 建议：", "结果与影响："):
            if not re.search(rf"{re.escape(label)}\s*\S+", decision):
                errors.append(f"{story.path}: 关键决策 {number} 缺少 {label}")
        owner = re.search(r"决定者：\s*(用户|待用户确认)", decision)
        if not owner:
            errors.append(f"{story.path}: 关键决策 {number} 的决定者只能是用户或待用户确认")
        elif owner.group(1) == "待用户确认":
            has_pending = True
    if has_pending and card.status != "blocked":
        errors.append(f"{card.path}: 人读 Story 存在待用户确认的关键决策时 status 必须为 blocked")


def _require_schema_meta(path: Path, data: Dict[str, object], kind: str, errors: List[str]) -> None:
    if data.get("kind") != kind:
        errors.append(f"{path}: kind 必须为 {kind}")
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"{path}: schema_version 必须为 {SCHEMA_VERSION}")


def validate_card_document(path: Path, data: Dict[str, object]) -> List[str]:
    errors: List[str] = []
    _require_schema_meta(path, data, KIND_CARD, errors)
    extra = sorted(set(data) - set(CARD_FIELD_ORDER))
    if extra:
        errors.append(f"{path}: 存在未知字段: {', '.join(extra)}")
    required = (
        "kind",
        "schema_version",
        "story",
        "intent_version",
        "status",
        "owner",
        "blocker",
        "status_updated",
        "refreshed",
        "code_baseline",
        "owns",
        "verifies",
        *CARD_STRING_FIELDS,
        "checklist",
    )
    for field in required:
        if field not in data:
            errors.append(f"{path}: 缺少字段 {field}")
    story_id = str(data.get("story", ""))
    if story_id and not STORY_ID_RE.fullmatch(story_id):
        errors.append(f"{path}: story 必须匹配 STORY-NN 或 STORY-NN.M")
    elif story_id and not path.name.startswith(f"{story_id}-"):
        errors.append(f"{path}: 文件名必须以 {story_id}- 开始")
    if path.suffix != ".json":
        errors.append(f"{path}: Agent 执行卡必须是 .json")
    intent = data.get("intent_version")
    if not isinstance(intent, int) or isinstance(intent, bool) or intent < 1:
        errors.append(f"{path}: intent_version 必须是正整数")
    status = str(data.get("status", ""))
    if status not in STATUS_LABELS:
        errors.append(f"{path}: status 必须是 {', '.join(STATUS_LABELS)}")
    for field in ("owner", "blocker"):
        if not str(data.get(field, "")).strip():
            errors.append(f"{path}: {field} 不能为空")
    _validate_iso_date(path, "status_updated", data.get("status_updated", ""), errors)
    refreshed = str(data.get("refreshed", "")).strip()
    baseline = str(data.get("code_baseline", "")).strip()
    if refreshed != "待领取":
        _validate_iso_date(path, "refreshed", refreshed, errors)
    if status in {"in_progress", "done"}:
        if refreshed == "待领取":
            errors.append(f"{path}: Story 开始后 refreshed 不能为待领取")
        if baseline in {"", "待领取"}:
            errors.append(f"{path}: Story 开始后 code_baseline 必须记录实际版本")
        if str(data.get("owner", "")) == "待领取":
            errors.append(f"{path}: {status} 时 owner 不能为待领取")
    blocker = str(data.get("blocker", "")).strip()
    if status == "blocked" and blocker in {"", "无"}:
        errors.append(f"{path}: status=blocked 时 blocker 必须说明阻塞")
    if status != "blocked" and blocker not in {"", "无"}:
        errors.append(f"{path}: blocker 非“无”时 status 必须为 blocked")
    for field in ("owns", "verifies"):
        value = data.get(field)
        if not isinstance(value, list):
            errors.append(f"{path}: {field} 必须是字符串数组")
        elif any(not isinstance(item, str) or not item.strip() for item in value):
            errors.append(f"{path}: {field} 只允许非空字符串")
        elif len(value) != len(set(str(item) for item in value)):
            errors.append(f"{path}: {field} 不得包含重复覆盖项")
    if isinstance(data.get("owns"), list) and not data["owns"]:
        errors.append(f"{path}: owns 至少包含一个覆盖项")
    for field in CARD_STRING_FIELDS:
        value = data.get(field)
        if field in data and (not isinstance(value, str) or not value.strip()):
            errors.append(f"{path}: {field} 必须是非空字符串")
    checklist = data.get("checklist")
    if not isinstance(checklist, list):
        errors.append(f"{path}: checklist 必须是对象数组")
        return errors
    if not MIN_CHECKLIST_ITEMS <= len(checklist) <= MAX_CHECKLIST_ITEMS:
        errors.append(
            f"{path}: 执行清单必须包含 {MIN_CHECKLIST_ITEMS}～{MAX_CHECKLIST_ITEMS} 个复选项"
        )
    done_count = 0
    for index, item in enumerate(checklist, 1):
        if not isinstance(item, dict) or set(item) - {"done", "text"}:
            errors.append(f"{path}: checklist[{index}] 只能包含 done 和 text")
            continue
        if not isinstance(item.get("done"), bool):
            errors.append(f"{path}: checklist[{index}].done 必须是布尔值")
        if not isinstance(item.get("text"), str) or not str(item.get("text", "")).strip():
            errors.append(f"{path}: checklist[{index}].text 必须是非空字符串")
        else:
            length = visible_char_count(str(item["text"]))
            if length > MAX_CHECKLIST_ITEM_CHARS:
                errors.append(
                    f"{path}: 执行清单单项有效字符 {length} 超过上限 {MAX_CHECKLIST_ITEM_CHARS}: {item['text']}"
                )
        if item.get("done") is True:
            done_count += 1
    all_done = bool(checklist) and done_count == len(checklist)
    if status == "done" and not all_done:
        errors.append(f"{path}: status=done 时所有执行清单项必须勾选")
    if all_done and status != "done":
        errors.append(f"{path}: 执行清单已全部完成，Story status 应为 done")
    return errors


def validate_risk_document(path: Path, data: Dict[str, object], epic_id: str | None = None) -> List[str]:
    errors: List[str] = []
    _require_schema_meta(path, data, KIND_RISK, errors)
    extra = sorted(set(data) - set(RISK_FIELD_ORDER))
    if extra:
        errors.append(f"{path}: 存在未知字段: {', '.join(extra)}")
    for field in RISK_FIELD_ORDER:
        if field not in data:
            errors.append(f"{path}: 缺少字段 {field}")
    if epic_id is not None and data.get("epic") != epic_id:
        errors.append(f"{path}: epic 必须引用 {epic_id}")
    _validate_iso_date(path, "updated", data.get("updated", ""), errors)
    total = 0
    for field in RISK_LIST_FIELDS:
        value = data.get(field)
        if not isinstance(value, list):
            errors.append(f"{path}: {field} 必须是字符串数组")
            continue
        if any(not isinstance(item, str) or not item.strip() for item in value):
            errors.append(f"{path}: {field} 只允许非空字符串")
        total += len(value)
    if total > MAX_RISK_ITEMS:
        errors.append(f"{path}: 待决策与后续关注合计最多 {MAX_RISK_ITEMS} 项，当前 {total} 项")
    return errors


def validate_reference_document(path: Path, data: Dict[str, object]) -> List[str]:
    errors: List[str] = []
    _require_schema_meta(path, data, KIND_REFERENCE, errors)
    for field in ("id", "title", "updated"):
        if field not in data or not str(data.get(field, "")).strip():
            errors.append(f"{path}: 缺少非空字段 {field}")
    _validate_iso_date(path, "updated", data.get("updated", ""), errors)
    if "body" not in data:
        errors.append(f"{path}: 缺少字段 body")
    return errors


def validate_agent_document(path: Path, data: Dict[str, object]) -> List[str]:
    kind = str(data.get("kind", ""))
    if kind == KIND_CARD:
        return validate_card_document(path, data)
    if kind == KIND_RISK:
        return validate_risk_document(path, data)
    if kind == KIND_REFERENCE:
        return validate_reference_document(path, data)
    return [f"{path}: kind 必须是 {KIND_CARD}、{KIND_RISK} 或 {KIND_REFERENCE}"]


def _agent_dir(stories: Sequence[WorkItem]) -> Path:
    return stories[0].path.parent.parent / "agent"


def _load_risk_register(epic: WorkItem, stories: Sequence[WorkItem]) -> RiskRegister:
    path = _agent_dir(stories) / "风险与阻塞.json"
    data = load_json_document(path)
    return RiskRegister(path, data)


def _load_agent_card(story: WorkItem) -> AgentCard:
    agent_dir = _agent_dir([story])
    markdown_cards = sorted(agent_dir.glob(f"{story.item_id}-*.md")) if agent_dir.is_dir() else []
    if markdown_cards:
        raise DocumentError(
            f"{story.path}: Agent 执行卡必须是 JSON，请用 write 写入 {story.item_id}-*.json，"
            f"当前仍有 {markdown_cards[0].name}"
        )
    cards = sorted(agent_dir.glob(f"{story.item_id}-*.json")) if agent_dir.is_dir() else []
    if len(cards) != 1:
        raise DocumentError(
            f"{story.path}: 必须有且仅有一份 agent/{story.item_id}-*.json 执行卡，当前 {len(cards)} 份"
        )
    path = cards[0]
    return AgentCard(path, load_json_document(path))


def _validate_agent_card(story: WorkItem, errors: List[str]) -> AgentCard | None:
    try:
        card = _load_agent_card(story)
    except DocumentError as exc:
        errors.append(str(exc))
        return None
    errors.extend(validate_card_document(card.path, card.data))
    if card.data.get("story") != story.item_id:
        errors.append(f"{card.path}: story 必须为 {story.item_id}")
    story_intent = str(story.metadata.get("intent_version", ""))
    card_intent = card.data.get("intent_version")
    if str(card_intent) != story_intent:
        errors.append(f"{card.path}: intent_version 必须与 {story.path.name} 一致")
    return card


def _story_progress(card: AgentCard) -> Tuple[Tuple[bool, str], ...]:
    """执行卡是唯一进度源，人读 Story 不保存勾选状态。"""
    return card.checklist


def validate_dashboard(path: Path, text: str) -> List[str]:
    errors: List[str] = []
    headings = tuple(match.group(1).strip() for match in HEADING_RE.finditer(text))
    for required in DASHBOARD_HEADINGS:
        if required not in headings:
            errors.append(f"{path}: 缺少自动生成章节 ## {required}")
    _validate_heading_contract(path, headings, DASHBOARD_HEADINGS, errors)
    _validate_flat_document(path, text, errors, allow_tables=True)
    _validate_budget(path, text, DASHBOARD_CONTENT_LIMIT, errors)
    if GENERATED_NOTICE not in text:
        errors.append(f"{path}: 必须声明本文由 Agent 资料自动生成")
    return errors


def validate_overview(path: Path, text: str) -> List[str]:
    errors: List[str] = []
    _reject_human_dynamic_body(path, text, errors)
    headings = tuple(match.group(1).strip() for match in HEADING_RE.finditer(text))
    for required in OVERVIEW_HEADINGS:
        if required not in headings:
            errors.append(f"{path}: 缺少二级标题 ## {required}")
    _validate_heading_contract(path, headings, OVERVIEW_HEADINGS, errors)
    _validate_flat_document(path, text, errors, allow_tables=False)
    _validate_budget(path, text, OVERVIEW_CONTENT_LIMIT, errors)
    return errors


def _load_agent_cards(stories: Sequence[WorkItem]) -> Dict[str, AgentCard]:
    return {story.item_id: _load_agent_card(story) for story in stories}


def derived_epic_status(cards: Dict[str, AgentCard]) -> str:
    statuses = tuple(card.status for card in cards.values())
    if statuses and all(status == "done" for status in statuses):
        return "done"
    if any(status == "in_progress" for status in statuses):
        return "in_progress"
    if any(status == "blocked" for status in statuses):
        return "blocked"
    return "todo"


def ready_story_ids(stories: Sequence[WorkItem], cards: Dict[str, AgentCard]) -> Tuple[str, ...]:
    completed = {story_id for story_id, card in cards.items() if card.status == "done"}
    return tuple(
        story.item_id
        for story in stories
        if cards[story.item_id].status == "todo" and set(story.depends_on).issubset(completed)
    )


def first_unfinished_dependency(story: WorkItem, completed: Sequence[str] | set[str]) -> str | None:
    done = set(completed)
    return next((item for item in story.depends_on if item not in done), None)


def planned_dependency_gate(
    story: WorkItem, card: AgentCard, completed: Sequence[str] | set[str]
) -> Tuple[str, str] | None:
    """若只因前置 Story 未完成而阻塞，返回应对齐的 status/blocker。"""
    unfinished = first_unfinished_dependency(story, completed)
    blocker = card.blocker.strip()
    if card.status == "todo" and unfinished is not None and blocker in {"", "无"}:
        return ("blocked", f"{unfinished} 未完成")
    if card.status == "blocked" and DEPENDENCY_UNFINISHED_RE.fullmatch(blocker):
        if unfinished is None:
            return ("todo", "无")
        wanted = f"{unfinished} 未完成"
        if blocker != wanted:
            return ("blocked", wanted)
    return None


def stale_dependency_gates(stories: Sequence[WorkItem]) -> Tuple[str, ...]:
    cards = _load_agent_cards(stories)
    completed = {story_id for story_id, card in cards.items() if card.status == "done"}
    return tuple(
        story.item_id
        for story in stories
        if planned_dependency_gate(story, cards[story.item_id], completed)
    )


def sync_dependency_gates(stories: Sequence[WorkItem]) -> Tuple[str, ...]:
    """只在 Agent JSON 同步依赖阻塞，人读 Story 始终保持纯意图。"""
    cards = _load_agent_cards(stories)
    completed = {story_id for story_id, card in cards.items() if card.status == "done"}
    changed: List[str] = []
    today = date.today().isoformat()
    for story in stories:
        card = cards[story.item_id]
        planned = planned_dependency_gate(story, card, completed)
        if planned is None:
            continue
        status, blocker = planned
        data = copy.deepcopy(card.data)
        data["status"] = status
        data["blocker"] = blocker
        data["status_updated"] = today
        write_json_document(card.path, data)
        changed.append(story.item_id)
    return tuple(changed)


def _validate_optional_agent_json(agent_dir: Path, errors: List[str], reserved: Sequence[Path]) -> None:
    reserved_names = {path.name for path in reserved}
    if not agent_dir.is_dir():
        return
    for path in sorted(agent_dir.glob("*.md")):
        errors.append(f"{path}: Agent 文档必须是 JSON，请用 write 写入对应 .json")
    for path in sorted(agent_dir.glob("*.json")):
        if path.name in reserved_names:
            continue
        try:
            data = load_json_document(path)
        except DocumentError as exc:
            errors.append(str(exc))
            continue
        errors.extend(validate_agent_document(path, data))


def validate_project(epic: WorkItem, stories: Sequence[WorkItem]) -> List[str]:
    errors: List[str] = []
    errors.extend(_require_fields(epic, ("kind", "id", "title", "updated", "coverage")))
    errors.extend(_reject_fields(epic, ("status", "owner", "blocker")))
    _reject_human_dynamic_body(epic.path, epic.body, errors)
    if epic.metadata.get("kind") != "epic":
        errors.append(f"{epic.path}: kind 必须为 epic")
    if not EPIC_ID_RE.fullmatch(str(epic.metadata.get("id", ""))):
        errors.append(f"{epic.path}: Epic id 必须匹配 EPIC-[A-Z0-9-]+")
    elif epic.path.parent.name != "epics" or epic.path.name != f"{epic.metadata.get('id')}.md":
        errors.append(f"{epic.path}: Epic 必须独立保存为 epics/{epic.metadata.get('id')}.md")
    if not str(epic.metadata.get("title", "")).strip():
        errors.append(f"{epic.path}: title 不能为空")
    _validate_date(epic, errors)
    _validate_sections(epic, ("愿景", "全局设计", "成功标准", "Story 地图"), errors)
    _validate_heading_contract(epic.path, epic.headings, EPIC_HEADINGS, errors)
    _validate_flat_document(epic.path, epic.body, errors, allow_tables=True, allow_code_blocks=True)
    _validate_global_design(epic, errors)
    _validate_budget(epic.path, epic.body, EPIC_CONTENT_LIMIT, errors)
    story_map = _section(epic.body, "Story 地图")
    coverage_value = epic.metadata.get("coverage")
    coverage_ids = tuple(str(item) for item in coverage_value) if isinstance(coverage_value, list) else ()
    if not isinstance(coverage_value, list) or not coverage_ids:
        errors.append(f"{epic.path}: coverage 必须使用非空内联列表")
    elif len(coverage_ids) != len(set(coverage_ids)):
        errors.append(f"{epic.path}: coverage 不得包含重复项")
    for coverage_id in coverage_ids:
        if not COVERAGE_ID_RE.fullmatch(coverage_id):
            errors.append(f"{epic.path}: coverage 标识格式无效: {coverage_id}")

    if len(stories) > MAX_STORIES:
        errors.append(f"{epic.path}: 一个 Epic 最多 {MAX_STORIES} 个 Story，当前 {len(stories)} 个")

    story_by_id: Dict[str, WorkItem] = {}
    agent_cards: Dict[str, AgentCard] = {}
    for story in stories:
        errors.extend(
            _require_fields(
                story,
                (
                    "kind",
                    "id",
                    "epic",
                    "title",
                    "gate",
                    "depends_on",
                    "updated",
                    "intent_version",
                ),
            )
        )
        errors.extend(_reject_fields(story, ("status", "owner", "blocker")))
        _reject_human_dynamic_body(story.path, story.body, errors)
        story_id = str(story.metadata.get("id", ""))
        if story.metadata.get("kind") != "story":
            errors.append(f"{story.path}: kind 必须为 story")
        if not STORY_ID_RE.fullmatch(story_id):
            errors.append(f"{story.path}: Story id 必须匹配 STORY-NN 或 STORY-NN.M")
        elif not story.path.name.startswith(f"Story-{story_id.removeprefix('STORY-')}-"):
            errors.append(f"{story.path}: 文件名必须以 Story-{story_id.removeprefix('STORY-')}- 开始")
        if story_id in story_by_id:
            errors.append(f"{story.path}: Story id 与 {story_by_id[story_id].path} 重复")
        story_by_id[story_id] = story
        if story.metadata.get("epic") != epic.metadata.get("id"):
            errors.append(f"{story.path}: epic 必须引用 {epic.metadata.get('id')}")
        gate = str(story.metadata.get("gate", ""))
        if not GATE_ID_RE.fullmatch(gate):
            errors.append(f"{story.path}: gate 必须是稳定的字母数字标识")
        if not isinstance(story.metadata.get("depends_on"), list):
            errors.append(f"{story.path}: depends_on 必须使用内联列表，如 [STORY-01]")
        if not str(story.metadata.get("intent_version", "")).isdigit() or int(
            str(story.metadata.get("intent_version", "0"))
        ) < 1:
            errors.append(f"{story.path}: intent_version 必须是正整数")
        if not str(story.metadata.get("title", "")).strip():
            errors.append(f"{story.path}: title 不能为空")
        _validate_date(story, errors)
        _validate_sections(story, ("愿景", "范围", "验收标准"), errors)
        _validate_heading_contract(story.path, story.headings, STORY_HEADINGS, errors)
        _validate_flat_document(story.path, story.body, errors, allow_tables=False)
        _validate_budget(story.path, story.body, STORY_CONTENT_LIMIT, errors)
        card = _validate_agent_card(story, errors)
        if card:
            agent_cards[story_id] = card
            _validate_key_decisions(story, card, errors)
        if story.path.name not in story_map:
            errors.append(f"{epic.path}: Story 地图未链接 {story.path.name}")

    for story_id, story in story_by_id.items():
        match = STORY_ID_RE.fullmatch(story_id)
        if match and match.group(2):
            base_story_id = f"STORY-{match.group(1)}"
            if base_story_id not in story_by_id:
                errors.append(f"{story.path}: 插入 Story 缺少主编号 {base_story_id}")

    coverage_set = set(coverage_ids)
    owners: Dict[str, List[str]] = {}
    for card in agent_cards.values():
        for coverage_id in card.owns:
            owners.setdefault(coverage_id, []).append(str(card.data.get("story", card.path.name)))
            if coverage_id not in coverage_set:
                errors.append(f"{card.path}: owns 引用了 Epic 未声明的覆盖项 {coverage_id}")
        for coverage_id in card.verifies:
            if coverage_id not in coverage_set:
                errors.append(f"{card.path}: verifies 引用了 Epic 未声明的覆盖项 {coverage_id}")
    for coverage_id in coverage_ids:
        claimed_by = owners.get(coverage_id, [])
        if not claimed_by:
            errors.append(f"{epic.path}: 覆盖项 {coverage_id} 没有 Story 主责")
        elif len(claimed_by) > 1:
            errors.append(f"{epic.path}: 覆盖项 {coverage_id} 被多个 Story 主责: {', '.join(claimed_by)}")

    for story in stories:
        for dependency in story.depends_on:
            if dependency == story.item_id:
                errors.append(f"{story.path}: depends_on 不得引用自己")
            elif dependency not in story_by_id:
                errors.append(f"{story.path}: depends_on 引用了不存在的 {dependency}")
            elif story_order_key(dependency) > story_order_key(story.item_id):
                errors.append(f"{story.path}: depends_on 不得前向依赖 {dependency}")
            elif (
                story.item_id in agent_cards
                and dependency in agent_cards
                and agent_cards[story.item_id].status in {"in_progress", "done"}
                and agent_cards[dependency].status != "done"
            ):
                errors.append(
                    f"{agent_cards[story.item_id].path}: {agent_cards[story.item_id].status} "
                    f"但依赖 {dependency} 尚未完成"
                )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(story_id: str, chain: Tuple[str, ...]) -> None:
        if story_id in visiting:
            errors.append(f"Story 依赖存在环: {' -> '.join(chain + (story_id,))}")
            return
        if story_id in visited or story_id not in story_by_id:
            return
        visiting.add(story_id)
        for dependency in story_by_id[story_id].depends_on:
            visit(dependency, chain + (story_id,))
        visiting.remove(story_id)
        visited.add(story_id)

    for story_id in story_by_id:
        visit(story_id, ())

    reserved_agent_paths: List[Path] = [card.path for card in agent_cards.values()]
    try:
        register = _load_risk_register(epic, stories)
    except DocumentError as exc:
        errors.append(str(exc))
    else:
        reserved_agent_paths.append(register.path)
        errors.extend(validate_risk_document(register.path, register.data, epic.item_id))
    if stories:
        _validate_optional_agent_json(_agent_dir(stories), errors, reserved_agent_paths)
    return errors


def load_project(epic_path: Path, stories_dir: Path) -> Tuple[WorkItem, List[WorkItem]]:
    if not stories_dir.is_dir():
        raise DocumentError(f"Story 目录不存在: {stories_dir}")
    epic = load_item(epic_path)
    story_paths = sorted(stories_dir.glob("Story-*.md"))
    if not story_paths:
        raise DocumentError(f"Story 目录中没有 Story-*.md: {stories_dir}")
    stories = [load_item(path) for path in story_paths]
    stories.sort(key=lambda item: story_order_key(item.item_id))
    return epic, stories


def _markdown_link(label: str, target: Path, base: Path) -> str:
    relative = os.path.relpath(target, base).replace(os.sep, "/")
    return f"[{label}]({relative})"


def _table_cell(value: object) -> str:
    return str(value).replace("\n", " ").replace("|", r"\|")


def dashboard_document(epic: WorkItem, stories: Sequence[WorkItem], dashboard_path: Path) -> str:
    cards = _load_agent_cards(stories)
    register = _load_risk_register(epic, stories)
    completed = sum(1 for card in cards.values() if card.status == "done")
    active = [story.item_id for story in stories if cards[story.item_id].status == "in_progress"]
    ready = ready_story_ids(stories, cards)
    epic_status = derived_epic_status(cards)
    epic_link = _markdown_link(f"{epic.item_id} {epic.title}", epic.path, dashboard_path.parent)
    lines = [
        f"# {epic.title} 项目进展",
        "",
        GENERATED_NOTICE,
        "",
        "## Epic / Story 一览",
        "",
        f"- Epic：{epic_link}（{STATUS_LABELS[epic_status]}）",
        f"- Story：{completed}/{len(stories)} 已完成",
        f"- 当前推进：{', '.join(active) if active else '无'}",
        f"- 可领取：{', '.join(ready) if ready else '无'}",
        "",
        "| Story | 状态 | 进度 | 当前结果或下一步 |",
        "| --- | --- | ---: | --- |",
    ]
    for story in stories:
        card = cards[story.item_id]
        progress = _story_progress(card)
        done_count = sum(1 for checked, _ in progress if checked)
        next_item = next((text for checked, text in progress if not checked), "全部完成")
        story_link = _markdown_link(f"{story.item_id} {story.title}", story.path, dashboard_path.parent)
        checklist = f"{done_count}/{len(progress)}"
        if card.status == "blocked":
            current = f"阻塞：{card.blocker}"
        elif card.status == "done":
            current = progress[-1][1] if progress else "已完成"
        else:
            current = next_item
        lines.append(
            "| "
            + " | ".join(
                (
                    _table_cell(story_link),
                    _table_cell(STATUS_LABELS[card.status]),
                    _table_cell(checklist),
                    _table_cell(current),
                )
            )
            + " |"
        )
    risk_rows: List[Tuple[str, str]] = []
    for story in stories:
        card = cards[story.item_id]
        if card.status == "blocked" and not DEPENDENCY_UNFINISHED_RE.fullmatch(card.blocker):
            story_link = _markdown_link(story.item_id, story.path, dashboard_path.parent)
            risk_rows.append(("当前阻塞", f"{story_link}：{card.blocker}"))
    risk_rows.extend(("待用户决策", item) for item in register.items("待用户决策"))
    risk_rows.extend(("后续关注", item) for item in register.items("后续关注"))
    lines.extend(("", "## 风险与阻塞", ""))
    if not risk_rows:
        lines.append("当前没有需要用户决策或后续关注的风险。")
    else:
        lines.extend(("| 类型 | 事项 |", "| --- | --- |"))
        for kind, item in risk_rows:
            lines.append(f"| {_table_cell(kind)} | {_table_cell(item)} |")
    return "\n".join(lines).rstrip() + "\n"


def _atomic_write(path: Path, text: str) -> None:
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            handle.write(text)
            temporary = Path(handle.name)
        temporary.chmod(path.stat().st_mode if path.exists() else 0o644)
        os.replace(temporary, path)
    except OSError as exc:
        if temporary and temporary.exists():
            temporary.unlink()
        raise DocumentError(f"无法写入 {path}: {exc}") from exc


def _validate_or_report(epic: WorkItem, stories: Sequence[WorkItem]) -> bool:
    errors = validate_project(epic, stories)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return False
    return True


def _report_errors(errors: Sequence[str]) -> bool:
    if not errors:
        return True
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return False


def command_check(args: argparse.Namespace) -> int:
    epic, stories = load_project(args.epic, args.stories_dir)
    if not _validate_or_report(epic, stories):
        return 1
    stale = stale_dependency_gates(stories)
    if stale:
        print(
            f"ERROR: 依赖阻塞已过期，请运行 render: {', '.join(stale)}",
            file=sys.stderr,
        )
        return 1
    if args.overview:
        overview = args.overview.read_text(encoding="utf-8")
        if not _report_errors(validate_overview(args.overview, overview)):
            return 1
    if args.dashboard:
        current = args.dashboard.read_text(encoding="utf-8")
        expected = dashboard_document(epic, stories, args.dashboard)
        if not _report_errors(validate_dashboard(args.dashboard, expected)):
            return 1
        if expected != current:
            print(f"ERROR: 仪表盘已过期，请运行 render: {args.dashboard}", file=sys.stderr)
            return 1
    cards = _load_agent_cards(stories)
    print(
        f"OK: {epic.item_id}; stories={len(stories)}; "
        f"completed={sum(card.status == 'done' for card in cards.values())}"
    )
    return 0


def command_render(args: argparse.Namespace) -> int:
    epic, stories = load_project(args.epic, args.stories_dir)
    if not _validate_or_report(epic, stories):
        return 1
    synced = sync_dependency_gates(stories)
    if synced:
        epic, stories = load_project(args.epic, args.stories_dir)
        if not _validate_or_report(epic, stories):
            return 1
    current = args.dashboard.read_text(encoding="utf-8") if args.dashboard.exists() else ""
    updated = dashboard_document(epic, stories, args.dashboard)
    if not _report_errors(validate_dashboard(args.dashboard, updated)):
        return 1
    notes = [f"已同步依赖阻塞: {', '.join(synced)}"] if synced else []
    if updated == current:
        notes.append(f"项目进展已是最新: {args.dashboard}")
        print("OK: " + "；".join(notes))
        return 0
    _atomic_write(args.dashboard, updated)
    notes.append(f"已生成项目进展: {args.dashboard}")
    print("OK: " + "；".join(notes))
    return 0


def command_status(args: argparse.Namespace) -> int:
    epic, stories = load_project(args.epic, args.stories_dir)
    if not _validate_or_report(epic, stories):
        return 1
    cards = _load_agent_cards(stories)
    ready = ready_story_ids(stories, cards)
    story_payloads = []
    for story in stories:
        card = cards[story.item_id]
        progress = _story_progress(card)
        done_count = sum(1 for checked, _ in progress if checked)
        next_item = next((text for checked, text in progress if not checked), "全部完成")
        story_payloads.append(
            {
                "id": story.item_id,
                "title": story.title,
                "gate": story.metadata["gate"],
                "status": card.status,
                "card": str(card.path),
                "checklist_done": done_count,
                "checklist_total": len(progress),
                "depends_on": list(story.depends_on),
                "owner": card.owner,
                "blocker": card.blocker,
                "next_item": next_item,
                "content_chars": story.content_chars,
                "content_limit": STORY_CONTENT_LIMIT,
            }
        )
    payload = {
        "epic": {
            "id": epic.item_id,
            "title": epic.title,
            "status": derived_epic_status(cards),
            "coverage": list(epic.metadata.get("coverage", [])),
            "stories_completed": sum(card.status == "done" for card in cards.values()),
            "stories_total": len(stories),
            "ready_stories": list(ready),
            "content_chars": epic.content_chars,
            "content_limit": EPIC_CONTENT_LIMIT,
        },
        "stories": story_payloads,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"{epic.item_id} {epic.title}: {STATUS_LABELS[derived_epic_status(cards)]}")
        print(f"可领取: {', '.join(ready) if ready else '无'}")
        for story in stories:
            card = cards[story.item_id]
            progress = _story_progress(card)
            done_count = sum(1 for checked, text in progress if checked)
            next_item = next((text for checked, text in progress if not checked), "全部完成")
            print(
                f"{story.item_id}\t{STATUS_LABELS[card.status]}\t"
                f"执行清单 {done_count}/{len(progress)}\t{next_item}"
            )
    return 0


def _read_json_payload(from_path: Path | None) -> Dict[str, object]:
    if from_path is not None:
        return load_json_document(from_path)
    raw = sys.stdin.read()
    if not raw.strip():
        raise DocumentError("write 需要从 --from 或 stdin 读取 JSON 对象")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DocumentError(f"stdin JSON 无效: {exc}") from exc
    if not isinstance(data, dict):
        raise DocumentError("Agent 文档必须是 JSON 对象")
    return data


def command_write(args: argparse.Namespace) -> int:
    data = _read_json_payload(args.from_path)
    errors = validate_agent_document(args.file, data)
    if not _report_errors(errors):
        return 1
    write_json_document(args.file, data)
    print(f"OK: 已写入 {args.file}")
    return 0


def coerce_set_value(raw: str) -> object:
    stripped = raw.strip()
    if stripped in {"true", "false"}:
        return stripped == "true"
    if re.fullmatch(r"-?\d+", stripped):
        return int(stripped)
    if stripped[:1] in {"[", "{", '"'}:
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise DocumentError(f"--set 值不是合法 JSON: {raw}") from exc
    return raw


def command_patch(args: argparse.Namespace) -> int:
    data = load_json_document(args.file)
    kind = str(data.get("kind", ""))
    if kind not in {KIND_CARD, KIND_RISK, KIND_REFERENCE}:
        raise DocumentError(f"{args.file}: 无法 patch 未知 kind {kind!r}")
    changed_status_fields = False
    for assignment in args.set or []:
        if "=" not in assignment:
            raise DocumentError(f"--set 必须是 field=value，当前为 {assignment!r}")
        field, raw = assignment.split("=", 1)
        field = field.strip()
        if not field:
            raise DocumentError("--set 字段名不能为空")
        if kind == KIND_CARD and field not in CARD_FIELD_ORDER:
            raise DocumentError(f"{args.file}: 未知执行卡字段 {field}")
        if kind == KIND_RISK and field not in RISK_FIELD_ORDER:
            raise DocumentError(f"{args.file}: 未知风险登记字段 {field}")
        data[field] = coerce_set_value(raw)
        if field in {"status", "owner", "blocker"}:
            changed_status_fields = True
    if args.check_item is not None:
        if kind != KIND_CARD:
            raise DocumentError("只有执行卡支持 --check-item")
        checklist = data.get("checklist")
        if not isinstance(checklist, list) or not 1 <= args.check_item <= len(checklist):
            raise DocumentError(f"{args.file}: checklist 序号必须在 1 到清单长度之间")
        item = checklist[args.check_item - 1]
        if not isinstance(item, dict):
            raise DocumentError(f"{args.file}: checklist[{args.check_item}] 必须是对象")
        item["done"] = not args.undone
    if kind == KIND_CARD and changed_status_fields and not any(
        assignment.split("=", 1)[0].strip() == "status_updated" for assignment in args.set or []
    ):
        data["status_updated"] = date.today().isoformat()
    if kind == KIND_RISK and args.set and not any(
        assignment.split("=", 1)[0].strip() == "updated" for assignment in args.set or []
    ):
        data["updated"] = date.today().isoformat()
    errors = validate_agent_document(args.file, data)
    if not _report_errors(errors):
        return 1
    write_json_document(args.file, data)
    print(f"OK: 已更新 {args.file}")
    return 0


def template_card(story_id: str) -> Dict[str, object]:
    return {
        "kind": KIND_CARD,
        "schema_version": SCHEMA_VERSION,
        "story": story_id,
        "intent_version": 1,
        "status": "todo",
        "owner": "待领取",
        "blocker": "无",
        "status_updated": date.today().isoformat(),
        "refreshed": "待领取",
        "code_baseline": "待领取",
        "owns": ["COVERAGE"],
        "verifies": [],
        "goal": "用可观察结果说明本 Story 完成时发生了什么。",
        "decision_boundary": "列出不可变条件和必须询问用户的变化。",
        "technical_plan": "说明实现路径，精确参数放到共享契约。",
        "authoritative_inputs": "列出本卡直接依赖的共享 JSON、代码入口和基线。",
        "claim_checks": "复核 intent_version、前置交接、代码入口和远端基线。",
        "checklist": [
            {"done": False, "text": "建立可失败的行为基线。"},
            {"done": False, "text": "实现本 Story 的核心结果。"},
            {"done": False, "text": "记录证据并完成交接。"},
        ],
        "steps": "按顺序写出实现步骤，每步带完成条件。",
        "verification": "记录命令、退出码、固定分母和交付证明。",
        "stop_conditions": "列出必须停止并询问的输入漂移。",
        "handoff": "记录起止版本、副作用、清理和下一个 Story 输入。",
    }


def template_risk(epic_id: str) -> Dict[str, object]:
    return {
        "kind": KIND_RISK,
        "schema_version": SCHEMA_VERSION,
        "epic": epic_id,
        "updated": date.today().isoformat(),
        "pending_decisions": [],
        "watch_items": [],
    }


def template_reference(doc_id: str, title: str) -> Dict[str, object]:
    return {
        "kind": KIND_REFERENCE,
        "schema_version": SCHEMA_VERSION,
        "id": doc_id,
        "title": title,
        "updated": date.today().isoformat(),
        "body": {},
    }


def command_template(args: argparse.Namespace) -> int:
    if args.kind == KIND_CARD:
        if not args.story:
            raise DocumentError("template agent-card 需要 --story")
        data = template_card(args.story)
    elif args.kind == KIND_RISK:
        if not args.epic_id:
            raise DocumentError("template risk-register 需要 --epic-id")
        data = template_risk(args.epic_id)
    else:
        if not args.doc_id or not args.title:
            raise DocumentError("template agent-reference 需要 --id 和 --title")
        data = template_reference(args.doc_id, args.title)
    text = dump_json(canonicalize_document(data))
    if args.file:
        if not _report_errors(validate_agent_document(args.file, data)):
            return 1
        write_json_document(args.file, data)
        print(f"OK: 已写入模板 {args.file}")
        return 0
    sys.stdout.write(text)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="校验人读 Epic/Story，并用脚本维护 Agent JSON、生成项目进展。",
        epilog=(
            "输出与退出码:\n"
            "  check/status 不修改文件；write/patch/template 规范化写入 Agent JSON；\n"
            "  render 先同步执行卡依赖阻塞，再整份生成 dashboard；错误写入 stderr。\n"
            "  0=成功，1=格式/状态/仪表盘校验失败，2=命令行或 I/O 错误。\n\n"
            "示例:\n"
            "  epic_story.py check --epic topic/epics/EPIC-ID.md --stories-dir topic/stories\n"
            "  epic_story.py render --epic topic/epics/EPIC-ID.md --stories-dir topic/stories "
            "--dashboard topic/项目进展.md\n"
            "  epic_story.py status --epic topic/epics/EPIC-ID.md --stories-dir topic/stories --json\n"
            "  epic_story.py template agent-card --story STORY-01 --file topic/agent/STORY-01-标题.json\n"
            "  epic_story.py write --file topic/agent/STORY-01-标题.json --from card.json\n"
            "  epic_story.py patch --file topic/agent/STORY-01-标题.json --set status=in_progress "
            "--set owner=Codex --check-item 1"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--epic", type=Path, required=True, help="Epic Markdown 文件")
        subparser.add_argument("--stories-dir", type=Path, required=True, help="包含 Story-*.md 的目录")

    check = subparsers.add_parser("check", help="校验意图、Agent JSON、依赖和可选项目进展新鲜度")
    add_common(check)
    check.add_argument("--overview", type=Path, help="同时检查人读项目入口的结构和字数")
    check.add_argument("--dashboard", type=Path, help="同时检查自动生成的项目进展是否为最新")
    check.set_defaults(handler=command_check)

    render = subparsers.add_parser("render", help="同步 Agent 依赖阻塞后整份生成项目进展")
    add_common(render)
    render.add_argument("--dashboard", type=Path, required=True, help="要生成的项目进展文件")
    render.set_defaults(handler=command_render)

    status = subparsers.add_parser("status", help="输出 Epic/Story 当前状态")
    add_common(status)
    status.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    status.set_defaults(handler=command_status)

    write = subparsers.add_parser("write", help="校验并规范化写入一份 Agent JSON")
    write.add_argument("--file", type=Path, required=True, help="要写入的 Agent JSON 路径")
    write.add_argument("--from", dest="from_path", type=Path, help="读取 JSON 的文件；省略则读 stdin")
    write.set_defaults(handler=command_write)

    patch = subparsers.add_parser("patch", help="按字段更新已有 Agent JSON")
    patch.add_argument("--file", type=Path, required=True, help="要更新的 Agent JSON 路径")
    patch.add_argument("--set", action="append", default=[], help="field=value，值可以是 JSON")
    patch.add_argument("--check-item", type=int, help="将执行清单第 N 项标为完成，从 1 开始")
    patch.add_argument("--undone", action="store_true", help="与 --check-item 一起使用，取消勾选")
    patch.set_defaults(handler=command_patch)

    template = subparsers.add_parser("template", help="输出或写入一份合法的 Agent JSON 模板")
    template.add_argument("kind", choices=(KIND_CARD, KIND_RISK, KIND_REFERENCE), help="文档类型")
    template.add_argument("--file", type=Path, help="写入路径；省略则打印到 stdout")
    template.add_argument("--story", help="agent-card 的 Story ID")
    template.add_argument("--epic-id", help="risk-register 的 Epic ID")
    template.add_argument("--id", dest="doc_id", help="agent-reference 的 id")
    template.add_argument("--title", help="agent-reference 的标题")
    template.set_defaults(handler=command_template)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except DocumentError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERROR: I/O 失败: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
