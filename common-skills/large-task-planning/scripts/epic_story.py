#!/usr/bin/env python3
"""校验 Goal、Epic、Story、Agent JSON 状态源及内容预算，并生成或查询项目进展。

参数定义：check/status/render/completion-check 接收 Epic 文件和 Story 目录；write/patch/template 接收 Agent JSON 路径。
输出定义：check/status/completion-check 只读；write/patch 校验后规范化写入 Agent JSON；render 先同步依赖阻塞，再整份生成项目进展。
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


SCHEMA_VERSION = 1
KIND_CARD = "agent-card"
KIND_RISK = "risk-register"
KIND_REFERENCE = "agent-reference"
KIND_GOLDEN = "golden-acceptance"
STATUS_IDS = ("todo", "in_progress", "blocked", "done")
DASHBOARD_LABELS = {
    "zh-Hans": {
        "progress": "项目进展",
        "notice": "> 本文由脚本根据 Agent JSON 状态源生成，请勿手工修改。",
        "overview": "Epic / Story 一览",
        "risks": "风险与阻塞",
        "epic": "Epic",
        "stories": "Story",
        "completed": "已完成",
        "current_progress": "当前推进",
        "ready": "可领取",
        "none": "无",
        "story": "Story",
        "status": "状态",
        "progress_column": "进度",
        "checklist": "执行清单",
        "current_result": "当前结果或下一步",
        "blocked": "阻塞",
        "all_done": "全部完成",
        "current_blocker": "当前阻塞",
        "planning_pending": "规划待决",
        "follow_up": "后续关注",
        "no_risks": "当前没有规划待决或后续关注的风险。",
        "risk_type": "类型",
        "item": "事项",
        "status_labels": {"todo": "待开始", "in_progress": "进行中", "blocked": "阻塞", "done": "已完成"},
    },
    "zh-Hant": {
        "progress": "專案進展",
        "notice": "> 本文由腳本根據 Agent JSON 狀態來源產生，請勿手動修改。",
        "overview": "Epic / Story 一覽",
        "risks": "風險與阻塞",
        "epic": "Epic",
        "stories": "Story",
        "completed": "已完成",
        "current_progress": "目前推進",
        "ready": "可領取",
        "none": "無",
        "story": "Story",
        "status": "狀態",
        "progress_column": "進度",
        "checklist": "執行清單",
        "current_result": "目前結果或下一步",
        "blocked": "阻塞",
        "all_done": "全部完成",
        "current_blocker": "目前阻塞",
        "planning_pending": "規劃待決",
        "follow_up": "後續關注",
        "no_risks": "目前沒有規劃待決或後續關注的風險。",
        "risk_type": "類型",
        "item": "事項",
        "status_labels": {"todo": "待開始", "in_progress": "進行中", "blocked": "阻塞", "done": "已完成"},
    },
    "en": {
        "progress": "Project Progress",
        "notice": "> This page is generated from the Agent JSON source of truth. Do not edit it manually.",
        "overview": "Epic / Story Overview",
        "risks": "Risks and Blockers",
        "epic": "Epic",
        "stories": "Stories",
        "completed": "completed",
        "current_progress": "Current progress",
        "ready": "Ready to claim",
        "none": "none",
        "story": "Story",
        "status": "Status",
        "progress_column": "Progress",
        "checklist": "Checklist",
        "current_result": "Current result or next step",
        "blocked": "Blocked",
        "all_done": "All complete",
        "current_blocker": "Current blocker",
        "planning_pending": "Planning decision",
        "follow_up": "Follow-up",
        "no_risks": "There are no pending planning decisions or follow-up risks.",
        "risk_type": "Type",
        "item": "Item",
        "status_labels": {"todo": "Not started", "in_progress": "In progress", "blocked": "Blocked", "done": "Done"},
    },
}
STORY_ID_RE = re.compile(r"^STORY-(\d{2})(?:\.([1-9]\d*))?$")
EPIC_ID_RE = re.compile(r"^EPIC-[A-Z0-9][A-Z0-9-]*$")
COVERAGE_ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9_.:-]*$")
GATE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
GOLDEN_CASE_ID_RE = re.compile(r"^GC-(?:0[1-9]|[1-9]\d+)$")
LANGUAGE_TAG_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
SECTION_MARKER_COMMENT_RE = re.compile(
    r"^<!--\s*large-task-planning:([a-z][a-z0-9-]*)\s*-->[ \t]*$", re.MULTILINE
)
SECTION_MARKER_RE = re.compile(
    r"^<!--\s*large-task-planning:([a-z][a-z0-9-]*)\s*-->[ \t]*\n^##\s+(.+?)\s*$",
    re.MULTILINE,
)
DECISION_MARKER_RE = re.compile(
    r"^<!--\s*large-task-planning:decision\s+owner=(user|agent|pending)\s*-->[ \t]*\n"
    r"^([1-9]\d*)\.\s+.+?(?=^<!--\s*large-task-planning:decision\s+owner=|"
    r"^<!--\s*large-task-planning:(?!decision\s+owner=)|\Z)",
    re.MULTILINE | re.DOTALL,
)
DECISION_ITEM_RE = re.compile(r"^([1-9]\d*)\.\s+.+?(?=^[1-9]\d*\.\s+|\Z)", re.MULTILINE | re.DOTALL)
FENCE_LINE_RE = re.compile(r"^```[^\n]*$", re.MULTILINE)
FENCED_CODE_BLOCK_RE = re.compile(
    r"^```([^\s`]*)[ \t]*\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL
)
DEPENDENCY_UNFINISHED_RE = re.compile(r"^(STORY-\d{2}(?:\.[1-9]\d*)?) 未完成$")
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]+\)")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
MARKDOWN_MARKUP_RE = re.compile(r"[\s`*_>#|:\-\[\](){}\\]+")
MIN_CHECKLIST_ITEMS = 3
MAX_CHECKLIST_ITEMS = 7
MAX_CHECKLIST_ITEM_CHARS = 120
OVERVIEW_CONTENT_LIMIT = 1500
EPIC_CONTENT_LIMIT = 3000
STORY_CONTENT_LIMIT = 2200
DASHBOARD_CONTENT_LIMIT = 3000
EPIC_SECTIONS = ("vision", "global-design", "manual-acceptance", "success-criteria", "story-map", "project-boundaries", "authoritative-documents")
STORY_SECTIONS = ("vision", "scope", "key-decisions", "acceptance-criteria")
DASHBOARD_SECTIONS = ("epic-story-overview", "risks-blockers")
OVERVIEW_SECTIONS = ("project-overview", "epics", "agent-entry")
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
CARD_IDENTITY_FIELDS = ("title", "epic", "gate", "depends_on")
CARD_FIELD_ORDER = (
    "kind",
    "schema_version",
    "story",
    *CARD_IDENTITY_FIELDS,
    "intent_version",
    "status",
    "owner",
    "blocker",
    "status_updated",
    "refreshed",
    "code_baseline",
    "owns",
    "verifies",
    "acceptance_cases",
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
GOLDEN_FIELD_ORDER = (
    "kind",
    "schema_version",
    "epic",
    "goal_version",
    "updated",
    "provenance",
    "cases",
)
GOLDEN_CASE_FIELDS = (
    "id",
    "title",
    "fixture",
    "interaction",
    "oracle",
    "required_paths",
    "evidence",
    "pass_condition",
)
GOLDEN_PROVENANCE = ("agent-drafted", "user-provided", "user-confirmed")
RISK_LIST_FIELDS = ("pending_decisions", "watch_items")
RISK_SECTION_FIELDS = {
    "planning-pending": "pending_decisions",
    "follow-up": "watch_items",
}


class DocumentError(Exception):
    """表示文档格式或项目状态不满足契约。"""


@dataclass(frozen=True)
class WorkItem:
    path: Path
    metadata: Dict[str, object]
    body: str
    headings: Tuple[str, ...]
    sections: Tuple[str, ...]

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
    def acceptance_cases(self) -> Tuple[str, ...]:
        value = self.data.get("acceptance_cases", [])
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

    def items(self, section: str) -> Tuple[str, ...]:
        field = RISK_SECTION_FIELDS[section]
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
    if kind == KIND_GOLDEN:
        return _order_keys(data, GOLDEN_FIELD_ORDER)
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


def _sections(body: str) -> Tuple[str, ...]:
    return tuple(match.group(1) for match in SECTION_MARKER_RE.finditer(body))


def _section(body: str, section: str) -> str:
    markers = tuple(SECTION_MARKER_RE.finditer(body))
    for index, marker in enumerate(markers):
        if marker.group(1) == section:
            end = markers[index + 1].start() if index + 1 < len(markers) else len(body)
            return body[marker.end() : end]
    return ""


def load_item(path: Path) -> WorkItem:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DocumentError(f"无法读取 {path}: {exc}") from exc
    metadata, body = _parse_frontmatter(path, text)
    headings = tuple(match.group(1).strip() for match in HEADING_RE.finditer(body))
    return WorkItem(path, metadata, body, headings, _sections(body))


def _require_fields(item: WorkItem, fields: Sequence[str]) -> List[str]:
    return [f"{item.path}: 缺少 frontmatter 字段 {field}" for field in fields if field not in item.metadata]


def _reject_fields(item: WorkItem, fields: Sequence[str]) -> List[str]:
    return [
        f"{item.path}: 人读文档不保存动态字段 {field}，请改为维护 Agent JSON"
        for field in fields
        if field in item.metadata
    ]


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
    for section in required:
        count = item.sections.count(section)
        if count == 0:
            errors.append(f"{item.path}: 缺少语义章节 {section}")
        elif count > 1:
            errors.append(f"{item.path}: 语义章节 {section} 只能出现一次")
        elif not _section(item.body, section).strip():
            errors.append(f"{item.path}: 语义章节 {section} 不能为空")


def _validate_section_contract(
    path: Path,
    body: str,
    headings: Sequence[str],
    sections: Sequence[str],
    allowed: Sequence[str],
    errors: List[str],
) -> None:
    marker_count = len(tuple(SECTION_MARKER_COMMENT_RE.finditer(body)))
    if marker_count != len(sections) or len(headings) != len(sections):
        errors.append(
            f"{path}: 每个二级标题都必须紧接在 <!-- large-task-planning:<section-id> --> 语义标记后"
        )
    unexpected = [section for section in sections if section not in allowed]
    if unexpected:
        errors.append(f"{path}: 存在不允许的语义章节: {', '.join(unexpected)}")
        return
    duplicates = sorted({section for section in sections if sections.count(section) > 1})
    if duplicates:
        errors.append(f"{path}: 语义章节重复: {', '.join(duplicates)}")
        return
    expected = tuple(section for section in allowed if section in sections)
    if tuple(sections) != expected:
        errors.append(f"{path}: 语义章节顺序必须为: {' -> '.join(allowed)}")


def _validate_language(item: WorkItem, errors: List[str]) -> None:
    language = str(item.metadata.get("language", "")).strip()
    if not LANGUAGE_TAG_RE.fullmatch(language):
        errors.append(f"{item.path}: language 必须是 BCP-47 语言标签，如 zh-Hans、zh-Hant 或 en")


def dashboard_labels(language: str) -> Dict[str, object]:
    normalized = language.lower()
    if normalized.startswith(("zh-hant", "zh-tw", "zh-hk", "zh-mo")):
        return DASHBOARD_LABELS["zh-Hant"]
    if normalized == "zh" or normalized.startswith(("zh-hans", "zh-cn", "zh-sg")):
        return DASHBOARD_LABELS["zh-Hans"]
    return DASHBOARD_LABELS["en"]


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
    section = _section(epic.body, "global-design")
    if not section.strip():
        return

    section_blocks = tuple(FENCED_CODE_BLOCK_RE.finditer(section))
    if not section_blocks:
        errors.append(f"{epic.path}: global-design 必须包含至少一张 Mermaid 或 fenced text 架构图")
    for block in section_blocks:
        language = block.group(1)
        diagram = block.group(2).strip()
        if language not in {"mermaid", "text"}:
            errors.append(f"{epic.path}: global-design 的架构图只能使用 mermaid 或 text 代码块")
        if not diagram:
            errors.append(f"{epic.path}: global-design 的架构图不能为空")

    all_blocks = tuple(FENCED_CODE_BLOCK_RE.finditer(epic.body))
    fence_lines = tuple(FENCE_LINE_RE.finditer(epic.body))
    if len(all_blocks) != len(section_blocks) or len(fence_lines) != 2 * len(all_blocks):
        errors.append(f"{epic.path}: 只能在 global-design 中保留完整的架构图代码块")


def _validate_key_decisions(story: WorkItem, card: AgentCard, errors: List[str]) -> None:
    """确保人读决策可追溯到用户边界或 Agent 方案判断。"""
    section = _section(story.body, "key-decisions").strip()
    if not section:
        return

    plain_decisions = tuple(DECISION_ITEM_RE.finditer(section))
    if not plain_decisions:
        errors.append(f"{story.path}: key-decisions 必须使用从 1 开始的连续编号")
        return
    numbers = tuple(int(match.group(1)) for match in plain_decisions)
    if numbers != tuple(range(1, len(plain_decisions) + 1)):
        errors.append(f"{story.path}: key-decisions 必须使用从 1 开始的连续编号")

    markers = tuple(DECISION_MARKER_RE.finditer(section))
    if len(markers) != len(plain_decisions):
        errors.append(
            f"{story.path}: 每项关键决策必须紧接在 <!-- large-task-planning:decision owner=user|agent|pending --> 后"
        )
    has_pending = any(marker.group(1) == "pending" for marker in markers)
    if has_pending and card.status != "blocked":
        errors.append(f"{card.path}: 存在 pending 关键决策时 status 必须为 blocked")


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
        "acceptance_cases",
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
    if status not in STATUS_IDS:
        errors.append(f"{path}: status 必须是 {', '.join(STATUS_IDS)}")
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
    acceptance_cases = data.get("acceptance_cases")
    if not isinstance(acceptance_cases, list):
        errors.append(f"{path}: acceptance_cases 必须是字符串数组")
    elif any(
        not isinstance(item, str) or not GOLDEN_CASE_ID_RE.fullmatch(item)
        for item in acceptance_cases
    ):
        errors.append(f"{path}: acceptance_cases 只允许 GC-NN")
    elif len(acceptance_cases) != len(set(acceptance_cases)):
        errors.append(f"{path}: acceptance_cases 不得包含重复案例")
    for field in CARD_STRING_FIELDS:
        value = data.get(field)
        if field in data and (not isinstance(value, str) or not value.strip()):
            errors.append(f"{path}: {field} 必须是非空字符串")
    for field in ("title", "epic"):
        value = data.get(field)
        if field in data and (not isinstance(value, str) or not value.strip()):
            errors.append(f"{path}: {field} 必须是非空字符串")
    if "gate" in data:
        gate = data.get("gate")
        if not isinstance(gate, str) or not gate.strip():
            errors.append(f"{path}: gate 必须是非空字符串")
        elif not GATE_ID_RE.fullmatch(gate):
            errors.append(f"{path}: gate 必须是稳定的字母数字标识")
    card_deps = data.get("depends_on")
    if "depends_on" in data:
        if not isinstance(card_deps, list) or any(
            not isinstance(item, str) or not item.strip() for item in card_deps
        ):
            errors.append(f"{path}: depends_on 必须是非空字符串数组")
        elif len(card_deps) != len(set(card_deps)):
            errors.append(f"{path}: depends_on 不得包含重复 Story")
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


def _validate_nonempty_string_list(
    path: Path,
    label: str,
    value: object,
    errors: List[str],
    *,
    allow_empty: bool = False,
) -> None:
    if not isinstance(value, list):
        errors.append(f"{path}: {label} 必须是字符串数组")
    elif not allow_empty and not value:
        errors.append(f"{path}: {label} 不能为空")
    elif any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{path}: {label} 只允许非空字符串")


def validate_golden_document(
    path: Path,
    data: Dict[str, object],
    epic_id: str | None = None,
    goal_version: int | None = None,
) -> List[str]:
    errors: List[str] = []
    _require_schema_meta(path, data, KIND_GOLDEN, errors)
    extra = sorted(set(data) - set(GOLDEN_FIELD_ORDER))
    if extra:
        errors.append(f"{path}: 存在未知字段: {', '.join(extra)}")
    for field in GOLDEN_FIELD_ORDER:
        if field not in data:
            errors.append(f"{path}: 缺少字段 {field}")
    if epic_id is not None and data.get("epic") != epic_id:
        errors.append(f"{path}: epic 必须引用 {epic_id}")
    version = data.get("goal_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        errors.append(f"{path}: goal_version 必须是正整数")
    elif goal_version is not None and version != goal_version:
        errors.append(f"{path}: goal_version 必须与 Epic 一致")
    _validate_iso_date(path, "updated", data.get("updated", ""), errors)
    if data.get("provenance") not in set(GOLDEN_PROVENANCE):
        errors.append(f"{path}: provenance 必须是 {' 或 '.join(GOLDEN_PROVENANCE)}")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append(f"{path}: cases 必须是非空对象数组")
        return errors
    seen: set[str] = set()
    for index, case in enumerate(cases, 1):
        label = f"cases[{index}]"
        if not isinstance(case, dict):
            errors.append(f"{path}: {label} 必须是对象")
            continue
        extra_case_fields = sorted(set(case) - set(GOLDEN_CASE_FIELDS))
        if extra_case_fields:
            errors.append(f"{path}: {label} 存在未知字段: {', '.join(extra_case_fields)}")
        for field in GOLDEN_CASE_FIELDS:
            if field not in case:
                errors.append(f"{path}: {label} 缺少字段 {field}")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not GOLDEN_CASE_ID_RE.fullmatch(case_id):
            errors.append(f"{path}: {label}.id 必须匹配 GC-NN")
        elif case_id in seen:
            errors.append(f"{path}: 黄金案例 ID 重复: {case_id}")
        else:
            seen.add(case_id)
        for field in ("title", "pass_condition"):
            if not isinstance(case.get(field), str) or not str(case.get(field, "")).strip():
                errors.append(f"{path}: {label}.{field} 必须是非空字符串")
        for field in ("fixture", "interaction", "oracle", "evidence"):
            _validate_nonempty_string_list(path, f"{label}.{field}", case.get(field), errors)
        _validate_nonempty_string_list(
            path,
            f"{label}.required_paths",
            case.get("required_paths"),
            errors,
            allow_empty=True,
        )
    return errors


def validate_agent_document(path: Path, data: Dict[str, object]) -> List[str]:
    kind = str(data.get("kind", ""))
    if kind == KIND_CARD:
        return validate_card_document(path, data)
    if kind == KIND_RISK:
        return validate_risk_document(path, data)
    if kind == KIND_REFERENCE:
        return validate_reference_document(path, data)
    if kind == KIND_GOLDEN:
        return validate_golden_document(path, data)
    return [
        f"{path}: kind 必须是 {KIND_CARD}、{KIND_RISK}、{KIND_REFERENCE} 或 {KIND_GOLDEN}"
    ]


def _agent_dir(stories: Sequence[WorkItem]) -> Path:
    return stories[0].path.parent.parent / "agent"


def _load_risk_register(epic: WorkItem, stories: Sequence[WorkItem]) -> RiskRegister:
    path = _agent_dir(stories) / "风险与阻塞.json"
    data = load_json_document(path)
    return RiskRegister(path, data)


def _load_golden_acceptance(stories: Sequence[WorkItem]) -> Tuple[Path, Dict[str, object]]:
    path = _agent_dir(stories) / "黄金验收.json"
    return path, load_json_document(path)


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
    identity = (
        ("title", story.metadata.get("title")),
        ("epic", story.metadata.get("epic")),
        ("gate", story.metadata.get("gate")),
    )
    for field, expected in identity:
        if field in card.data and expected is not None and str(card.data.get(field)) != str(expected):
            errors.append(f"{card.path}: {field} 必须与 {story.path.name} 一致")
    card_deps = card.data.get("depends_on")
    if isinstance(card_deps, list):
        if tuple(str(item) for item in card_deps) != story.depends_on:
            errors.append(f"{card.path}: depends_on 必须与 {story.path.name} 一致")
    return card


def _story_progress(card: AgentCard) -> Tuple[Tuple[bool, str], ...]:
    """执行卡是唯一进度源，人读 Story 不保存勾选状态。"""
    return card.checklist


def validate_dashboard(path: Path, text: str, language: str) -> List[str]:
    errors: List[str] = []
    headings = tuple(match.group(1).strip() for match in HEADING_RE.finditer(text))
    sections = _sections(text)
    for required in DASHBOARD_SECTIONS:
        if required not in sections:
            errors.append(f"{path}: 缺少自动生成语义章节 {required}")
    _validate_section_contract(path, text, headings, sections, DASHBOARD_SECTIONS, errors)
    _validate_flat_document(path, text, errors, allow_tables=True)
    _validate_budget(path, text, DASHBOARD_CONTENT_LIMIT, errors)
    if str(dashboard_labels(language)["notice"]) not in text:
        errors.append(f"{path}: 必须声明本文由 Agent 资料自动生成")
    return errors


def validate_overview(path: Path, text: str) -> List[str]:
    errors: List[str] = []
    headings = tuple(match.group(1).strip() for match in HEADING_RE.finditer(text))
    sections = _sections(text)
    for required in OVERVIEW_SECTIONS:
        if required not in sections:
            errors.append(f"{path}: 缺少语义章节 {required}")
    _validate_section_contract(path, text, headings, sections, OVERVIEW_SECTIONS, errors)
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


def _mentions_stable_id(text: str, stable_id: str) -> bool:
    """匹配完整稳定 ID，避免 GC-01 被 GC-010 等相似文本误报为证据。"""
    return re.search(
        rf"(?<![A-Za-z0-9]){re.escape(stable_id)}(?![A-Za-z0-9])",
        text,
    ) is not None


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
    errors.extend(
        _require_fields(
            epic,
            ("kind", "id", "title", "updated", "goal_version", "coverage", "language"),
        )
    )
    errors.extend(_reject_fields(epic, ("status", "owner", "blocker")))
    if epic.metadata.get("kind") != "epic":
        errors.append(f"{epic.path}: kind 必须为 epic")
    if not EPIC_ID_RE.fullmatch(str(epic.metadata.get("id", ""))):
        errors.append(f"{epic.path}: Epic id 必须匹配 EPIC-[A-Z0-9-]+")
    elif epic.path.parent.name != "epics" or epic.path.name != f"{epic.metadata.get('id')}.md":
        errors.append(f"{epic.path}: Epic 必须独立保存为 epics/{epic.metadata.get('id')}.md")
    if not str(epic.metadata.get("title", "")).strip():
        errors.append(f"{epic.path}: title 不能为空")
    _validate_date(epic, errors)
    _validate_language(epic, errors)
    goal_version_value = epic.metadata.get("goal_version")
    if not str(goal_version_value).isdigit() or int(str(goal_version_value or "0")) < 1:
        errors.append(f"{epic.path}: goal_version 必须是正整数")
        goal_version: int | None = None
    else:
        goal_version = int(str(goal_version_value))
    _validate_sections(epic, ("vision", "global-design", "manual-acceptance", "success-criteria", "story-map"), errors)
    _validate_section_contract(epic.path, epic.body, epic.headings, epic.sections, EPIC_SECTIONS, errors)
    _validate_flat_document(epic.path, epic.body, errors, allow_tables=True, allow_code_blocks=True)
    _validate_global_design(epic, errors)
    story_map = _section(epic.body, "story-map")
    coverage_value = epic.metadata.get("coverage")
    coverage_ids = tuple(str(item) for item in coverage_value) if isinstance(coverage_value, list) else ()
    if not isinstance(coverage_value, list) or not coverage_ids:
        errors.append(f"{epic.path}: coverage 必须使用非空内联列表")
    elif len(coverage_ids) != len(set(coverage_ids)):
        errors.append(f"{epic.path}: coverage 不得包含重复项")
    for coverage_id in coverage_ids:
        if not COVERAGE_ID_RE.fullmatch(coverage_id):
            errors.append(f"{epic.path}: coverage 标识格式无效: {coverage_id}")

    golden_path: Path | None = None
    golden_case_ids: Tuple[str, ...] = ()
    try:
        golden_path, golden_data = _load_golden_acceptance(stories)
    except DocumentError as exc:
        errors.append(str(exc))
    else:
        errors.extend(
            validate_golden_document(
                golden_path,
                golden_data,
                epic.item_id,
                goal_version,
            )
        )
        cases = golden_data.get("cases")
        if isinstance(cases, list):
            golden_case_ids = tuple(
                str(case.get("id"))
                for case in cases
                if isinstance(case, dict) and isinstance(case.get("id"), str)
            )

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
                    "language",
                ),
            )
        )
        errors.extend(_reject_fields(story, ("status", "owner", "blocker")))
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
        _validate_language(story, errors)
        if story.metadata.get("language") != epic.metadata.get("language"):
            errors.append(f"{story.path}: language 必须与 {epic.path.name} 一致")
        _validate_sections(story, ("vision", "scope", "acceptance-criteria"), errors)
        _validate_section_contract(story.path, story.body, story.headings, story.sections, STORY_SECTIONS, errors)
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
        for case_id in card.acceptance_cases:
            if case_id not in golden_case_ids:
                errors.append(f"{card.path}: acceptance_cases 引用了不存在的黄金案例 {case_id}")
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

    if stories and agent_cards and golden_case_ids:
        final_story = stories[-1]
        final_card = agent_cards.get(final_story.item_id)
        if final_card is not None:
            missing_cases = [
                case_id for case_id in golden_case_ids if case_id not in final_card.acceptance_cases
            ]
            if missing_cases:
                errors.append(
                    f"{final_card.path}: 最后一个 Story 必须验收全部黄金案例，缺少: "
                    f"{', '.join(missing_cases)}"
                )

            ancestors: set[str] = set()

            def collect_ancestors(story_id: str) -> None:
                story = story_by_id.get(story_id)
                if story is None:
                    return
                for dependency in story.depends_on:
                    if dependency in ancestors:
                        continue
                    ancestors.add(dependency)
                    collect_ancestors(dependency)

            collect_ancestors(final_story.item_id)
            unlinked = [story.item_id for story in stories[:-1] if story.item_id not in ancestors]
            if unlinked:
                errors.append(
                    f"{final_story.path}: 最后一个 Story 必须传递依赖全部前置 Story，缺少: "
                    f"{', '.join(unlinked)}"
                )
            if final_card.status == "done":
                verification = str(final_card.data.get("verification", ""))
                missing_evidence = [
                    case_id
                    for case_id in golden_case_ids
                    if not _mentions_stable_id(verification, case_id)
                ]
                if missing_evidence:
                    errors.append(
                        f"{final_card.path}: 黄金验收完成证据缺少案例: "
                        f"{', '.join(missing_evidence)}"
                    )

    reserved_agent_paths: List[Path] = [card.path for card in agent_cards.values()]
    if golden_path is not None:
        reserved_agent_paths.append(golden_path)
    try:
        register = _load_risk_register(epic, stories)
    except DocumentError as exc:
        errors.append(str(exc))
    else:
        reserved_agent_paths.append(register.path)
        errors.extend(validate_risk_document(register.path, register.data, epic.item_id))
        if register.items("planning-pending"):
            active_cards = [
                card.path.name for card in agent_cards.values() if card.status in {"todo", "in_progress", "done"}
            ]
            if active_cards:
                errors.append(
                    f"{register.path}: 存在规划待决事项时所有 Story 必须为 blocked，当前非阻塞卡: "
                    f"{', '.join(active_cards)}"
                )
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
    labels = dashboard_labels(str(epic.metadata["language"]))
    statuses = labels["status_labels"]
    cards = _load_agent_cards(stories)
    register = _load_risk_register(epic, stories)
    completed = sum(1 for card in cards.values() if card.status == "done")
    active = [story.item_id for story in stories if cards[story.item_id].status == "in_progress"]
    ready = ready_story_ids(stories, cards)
    epic_status = derived_epic_status(cards)
    epic_link = _markdown_link(f"{epic.item_id} {epic.title}", epic.path, dashboard_path.parent)
    lines = [
        f"# {epic.title} {labels['progress']}",
        "",
        str(labels["notice"]),
        "",
        "<!-- large-task-planning:epic-story-overview -->",
        f"## {labels['overview']}",
        "",
        f"- {labels['epic']}：{epic_link}（{statuses[epic_status]}）",
        f"- {labels['stories']}：{completed}/{len(stories)} {labels['completed']}",
        f"- {labels['current_progress']}：{', '.join(active) if active else labels['none']}",
        f"- {labels['ready']}：{', '.join(ready) if ready else labels['none']}",
        "",
        f"| {labels['story']} | {labels['status']} | {labels['progress_column']} | {labels['current_result']} |",
        "| --- | --- | ---: | --- |",
    ]
    for story in stories:
        card = cards[story.item_id]
        progress = _story_progress(card)
        done_count = sum(1 for checked, _ in progress if checked)
        next_item = next((text for checked, text in progress if not checked), str(labels["all_done"]))
        story_link = _markdown_link(f"{story.item_id} {story.title}", story.path, dashboard_path.parent)
        checklist = f"{done_count}/{len(progress)}"
        if card.status == "blocked":
            current = f"{labels['blocked']}：{card.blocker}"
        elif card.status == "done":
            current = progress[-1][1] if progress else str(labels["all_done"])
        else:
            current = next_item
        lines.append(
            "| "
            + " | ".join(
                (
                    _table_cell(story_link),
                    _table_cell(statuses[card.status]),
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
            risk_rows.append((str(labels["current_blocker"]), f"{story_link}：{card.blocker}"))
    risk_rows.extend((str(labels["planning_pending"]), item) for item in register.items("planning-pending"))
    risk_rows.extend((str(labels["follow_up"]), item) for item in register.items("follow-up"))
    lines.extend(("", "<!-- large-task-planning:risks-blockers -->", f"## {labels['risks']}", ""))
    if not risk_rows:
        lines.append(str(labels["no_risks"]))
    else:
        lines.extend((f"| {labels['risk_type']} | {labels['item']} |", "| --- | --- |"))
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
        if not _report_errors(validate_dashboard(args.dashboard, expected, str(epic.metadata["language"]))):
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


def command_completion_check(args: argparse.Namespace) -> int:
    """只在完整计划、最终验收和人读投影同时收口时返回成功。"""
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
    overview = args.overview.read_text(encoding="utf-8")
    if not _report_errors(validate_overview(args.overview, overview)):
        return 1
    current = args.dashboard.read_text(encoding="utf-8")
    expected = dashboard_document(epic, stories, args.dashboard)
    if not _report_errors(validate_dashboard(args.dashboard, expected, str(epic.metadata["language"]))):
        return 1
    if expected != current:
        print(f"ERROR: 仪表盘已过期，请运行 render: {args.dashboard}", file=sys.stderr)
        return 1

    cards = _load_agent_cards(stories)
    unfinished = [story.item_id for story in stories if cards[story.item_id].status != "done"]
    if unfinished:
        print(f"ERROR: 仍有未完成 Story: {', '.join(unfinished)}", file=sys.stderr)
        return 1
    _, golden = _load_golden_acceptance(stories)
    cases = golden.get("cases")
    case_count = len(cases) if isinstance(cases, list) else 0
    print(
        f"OK: {epic.item_id}; stories={len(stories)}/{len(stories)}; "
        f"golden_cases={case_count}/{case_count}"
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
    if not _report_errors(validate_dashboard(args.dashboard, updated, str(epic.metadata["language"]))):
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
            "content_target": EPIC_CONTENT_LIMIT,
        },
        "stories": story_payloads,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        labels = dashboard_labels(str(epic.metadata["language"]))
        statuses = labels["status_labels"]
        print(f"{epic.item_id} {epic.title}: {statuses[derived_epic_status(cards)]}")
        print(f"{labels['ready']}: {', '.join(ready) if ready else labels['none']}")
        for story in stories:
            card = cards[story.item_id]
            progress = _story_progress(card)
            done_count = sum(1 for checked, text in progress if checked)
            next_item = next((text for checked, text in progress if not checked), str(labels["all_done"]))
            print(
                f"{story.item_id}\t{statuses[card.status]}\t"
                f"{labels['checklist']} {done_count}/{len(progress)}\t{next_item}"
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
    if kind not in {KIND_CARD, KIND_RISK, KIND_REFERENCE, KIND_GOLDEN}:
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
        if kind == KIND_GOLDEN and field not in GOLDEN_FIELD_ORDER:
            raise DocumentError(f"{args.file}: 未知黄金验收字段 {field}")
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
    if kind == KIND_GOLDEN and args.set and not any(
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
        "title": "待填写",
        "epic": "EPIC-NAME",
        "gate": "GATE-ID",
        "depends_on": [],
        "intent_version": 1,
        "status": "todo",
        "owner": "待领取",
        "blocker": "无",
        "status_updated": date.today().isoformat(),
        "refreshed": "待领取",
        "code_baseline": "待领取",
        "owns": ["COVERAGE"],
        "verifies": [],
        "acceptance_cases": ["GC-01"],
        "goal": "用可观察结果说明本 Story 完成时发生了什么。",
        "decision_boundary": "列出不可变条件和 Agent 可在已确认方案内自行处理的实现取舍。",
        "technical_plan": "按顺序写实现路径，带代码锚点、本地运行方式、需要的测试数据与环境准备。",
        "authoritative_inputs": "列出本卡直接依赖的共享 JSON、代码入口、基线和前置执行卡。",
        "claim_checks": "复核 intent_version、前置交接、代码入口和远端基线。",
        "checklist": [
            {"done": False, "text": "建立可失败的行为基线。"},
            {"done": False, "text": "实现本 Story 的核心结果。"},
            {"done": False, "text": "记录证据并完成交接。"},
        ],
        "steps": "按顺序写出实现步骤，每步以「判据：…」写明可验证的完成判据。",
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


def template_golden(epic_id: str) -> Dict[str, object]:
    return {
        "kind": KIND_GOLDEN,
        "schema_version": SCHEMA_VERSION,
        "epic": epic_id,
        "goal_version": 1,
        "updated": date.today().isoformat(),
        "provenance": "agent-drafted",
        "cases": [
            {
                "id": "GC-01",
                "title": "待填写的黄金案例",
                "fixture": ["写明可复现的环境、账号、版本和固定输入。"],
                "interaction": ["按顺序写用户操作或逐轮对话。"],
                "oracle": ["写明已知正确结果及其权威依据。"],
                "required_paths": [],
                "evidence": ["写明需要保存的产品结果与能力调用证据。"],
                "pass_condition": "全部 oracle 与必经路径在同一次验收中有证据时通过。",
            }
        ],
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
    elif args.kind == KIND_GOLDEN:
        if not args.epic_id:
            raise DocumentError("template golden-acceptance 需要 --epic-id")
        data = template_golden(args.epic_id)
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
            "  check/status/completion-check 不修改文件；write/patch/template 规范化写入 Agent JSON；\n"
            "  completion-check 仅在全部 Story、黄金验收证据和 dashboard 收口时成功；\n"
            "  render 先同步执行卡依赖阻塞，再整份生成 dashboard；错误写入 stderr。\n"
            "  0=成功，1=格式/状态/仪表盘校验失败，2=命令行或 I/O 错误。\n\n"
            "示例:\n"
            "  epic_story.py check --epic topic/epics/EPIC-ID.md --stories-dir topic/stories\n"
            "  epic_story.py render --epic topic/epics/EPIC-ID.md --stories-dir topic/stories "
            "--dashboard topic/项目进展.md\n"
            "  epic_story.py status --epic topic/epics/EPIC-ID.md --stories-dir topic/stories --json\n"
            "  epic_story.py completion-check --epic topic/epics/EPIC-ID.md --stories-dir topic/stories "
            "--overview topic/README.md --dashboard topic/项目进展.md\n"
            "  epic_story.py template agent-card --story STORY-01 --file topic/agent/STORY-01-标题.json\n"
            "  epic_story.py template golden-acceptance --epic-id EPIC-NAME --file topic/agent/黄金验收.json\n"
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

    completion = subparsers.add_parser(
        "completion-check",
        help="确认全部 Story、黄金验收证据和人读投影已收口",
    )
    add_common(completion)
    completion.add_argument("--overview", type=Path, required=True, help="人读项目入口")
    completion.add_argument("--dashboard", type=Path, required=True, help="自动生成的项目进展")
    completion.set_defaults(handler=command_completion_check)

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
    template.add_argument(
        "kind",
        choices=(KIND_CARD, KIND_RISK, KIND_REFERENCE, KIND_GOLDEN),
        help="文档类型",
    )
    template.add_argument("--file", type=Path, help="写入路径；省略则打印到 stdout")
    template.add_argument("--story", help="agent-card 的 Story ID")
    template.add_argument("--epic-id", help="risk-register 或 golden-acceptance 的 Epic ID")
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
