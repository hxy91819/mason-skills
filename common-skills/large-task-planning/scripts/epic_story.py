#!/usr/bin/env python3
"""校验 Epic、Story、执行卡、覆盖映射及内容预算，并生成或查询项目仪表盘。

参数定义：通过子命令接收 Epic 文件、Story 目录和可选仪表盘路径。
输出定义：check/status 只读；render 仅替换仪表盘的受控标记区块；错误写入 stderr。
退出码：0 成功，1 文档或仪表盘校验失败，2 I/O 或命令行错误。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Sequence, Tuple


START_MARKER = "<!-- epic-story-dashboard:start -->"
END_MARKER = "<!-- epic-story-dashboard:end -->"
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
TODO_RE = re.compile(r"^- \[([ xX])\]\s+(.+?)\s*$", re.MULTILINE)
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]+\)")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
MARKDOWN_MARKUP_RE = re.compile(r"[\s`*_>#|:\-\[\](){}\\]+")
MIN_TODOS = 3
MAX_TODOS = 7
MAX_STORIES = 7
MAX_TODO_CHARS = 120
OVERVIEW_CONTENT_LIMIT = 1500
EPIC_CONTENT_LIMIT = 3000
STORY_CONTENT_LIMIT = 2200
DASHBOARD_CONTENT_LIMIT = 3000
EPIC_HEADINGS = ("愿景", "成功标准", "Story 地图", "项目边界", "权威文档")
STORY_HEADINGS = ("愿景", "范围", "解决方案概览", "TODO", "验收标准", "交付证据")
AGENT_CARD_HEADINGS = (
    "目标与完成信号",
    "决策边界",
    "技术方案",
    "权威输入",
    "领取检查",
    "执行步骤",
    "验证与证据",
    "停止条件",
    "交接",
)
DASHBOARD_HEADINGS = ("Epic / Story 一览", "门禁状态", "关键基线", "风险与阻塞")
OVERVIEW_HEADINGS = ("项目一览", "Epic", "Agent 入口")
DASHBOARD_ROW_LIMITS = {"门禁状态": 3, "关键基线": 6, "风险与阻塞": 6}


class DocumentError(Exception):
    """表示文档格式或项目状态不满足契约。"""


@dataclass(frozen=True)
class WorkItem:
    path: Path
    metadata: Dict[str, object]
    body: str
    headings: Tuple[str, ...]
    todos: Tuple[Tuple[bool, str], ...]

    @property
    def item_id(self) -> str:
        return str(self.metadata["id"])

    @property
    def title(self) -> str:
        return str(self.metadata["title"])

    @property
    def status(self) -> str:
        return str(self.metadata["status"])

    @property
    def depends_on(self) -> Tuple[str, ...]:
        value = self.metadata.get("depends_on", [])
        return tuple(str(item) for item in value) if isinstance(value, list) else ()

    @property
    def todo_done(self) -> int:
        return sum(1 for checked, _ in self.todos if checked)

    @property
    def next_todo(self) -> str:
        return next((text for checked, text in self.todos if not checked), "全部完成")

    @property
    def content_chars(self) -> int:
        return visible_char_count(self.body)


@dataclass(frozen=True)
class AgentCard:
    path: Path
    metadata: Dict[str, object]
    body: str
    headings: Tuple[str, ...]

    @property
    def owns(self) -> Tuple[str, ...]:
        value = self.metadata.get("owns", [])
        return tuple(str(item) for item in value) if isinstance(value, list) else ()

    @property
    def verifies(self) -> Tuple[str, ...]:
        value = self.metadata.get("verifies", [])
        return tuple(str(item) for item in value) if isinstance(value, list) else ()


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
    todo_section = _section(body, "TODO")
    todos = tuple(
        (match.group(1).lower() == "x", match.group(2).strip())
        for match in TODO_RE.finditer(todo_section)
    )
    return WorkItem(path, metadata, body, headings, todos)


def _require_fields(item: WorkItem, fields: Sequence[str]) -> List[str]:
    return [f"{item.path}: 缺少 frontmatter 字段 {field}" for field in fields if field not in item.metadata]


def _validate_date(item: WorkItem, errors: List[str]) -> None:
    value = str(item.metadata.get("updated", ""))
    try:
        date.fromisoformat(value)
    except ValueError:
        errors.append(f"{item.path}: updated 必须是 YYYY-MM-DD，当前为 {value!r}")


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


def _validate_flat_document(path: Path, body: str, errors: List[str], *, allow_tables: bool) -> None:
    if "```" in body:
        errors.append(f"{path}: 本层文档不允许代码块，命令和实现细节应放入 agent/ 或代码")
    if re.search(r"^#{3,6}\s+", body, re.MULTILINE):
        errors.append(f"{path}: 本层文档不允许三级及更深标题")
    if not allow_tables and re.search(r"^\|", body, re.MULTILINE):
        errors.append(f"{path}: 本层文档不使用表格，请改成短句或链接到下层资料")


def _validate_budget(path: Path, text: str, limit: int, errors: List[str]) -> None:
    actual = visible_char_count(text)
    if actual > limit:
        errors.append(f"{path}: 正文有效字符 {actual} 超过上限 {limit}，请下沉细节并改为链接")


def _validate_agent_card(story: WorkItem, errors: List[str]) -> AgentCard | None:
    agent_dir = story.path.parent.parent / "agent"
    cards = sorted(agent_dir.glob(f"{story.item_id}-*.md")) if agent_dir.is_dir() else []
    if len(cards) != 1:
        errors.append(f"{story.path}: 必须有且仅有一份 agent/{story.item_id}-*.md 执行卡，当前 {len(cards)} 份")
        return None
    card = cards[0]
    if f"../agent/{card.name}" not in story.body:
        errors.append(f"{story.path}: 必须直接链接 ../agent/{card.name}")
    try:
        text = card.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"无法读取 {card}: {exc}")
        return None
    try:
        metadata, body = _parse_frontmatter(card, text)
    except DocumentError as exc:
        errors.append(str(exc))
        return None
    headings = tuple(match.group(1).strip() for match in HEADING_RE.finditer(body))
    for heading in AGENT_CARD_HEADINGS:
        count = headings.count(heading)
        if count != 1:
            errors.append(f"{card}: 二级标题 ## {heading} 必须出现一次，当前 {count} 次")
        elif not _section(body, heading).strip():
            errors.append(f"{card}: ## {heading} 不能为空")
    _validate_heading_contract(card, headings, AGENT_CARD_HEADINGS, errors)
    required = ("story", "intent_version", "refreshed", "code_baseline", "owns", "verifies")
    for field in required:
        if field not in metadata:
            errors.append(f"{card}: 缺少 frontmatter 字段 {field}")
    if metadata.get("story") != story.item_id:
        errors.append(f"{card}: story 必须为 {story.item_id}")
    if str(metadata.get("intent_version", "")) != str(story.metadata.get("intent_version", "")):
        errors.append(f"{card}: intent_version 必须与 {story.path.name} 一致")
    for field in ("owns", "verifies"):
        value = metadata.get(field)
        if not isinstance(value, list):
            errors.append(f"{card}: {field} 必须使用内联列表")
        elif len(value) != len(set(str(item) for item in value)):
            errors.append(f"{card}: {field} 不得包含重复覆盖项")
    if isinstance(metadata.get("owns"), list) and not metadata["owns"]:
        errors.append(f"{card}: owns 至少包含一个覆盖项")
    refreshed = str(metadata.get("refreshed", "")).strip()
    baseline = str(metadata.get("code_baseline", "")).strip()
    if refreshed != "待领取":
        try:
            date.fromisoformat(refreshed)
        except ValueError:
            errors.append(f"{card}: refreshed 必须是 YYYY-MM-DD 或待领取")
    if story.status in {"in_progress", "done"}:
        if refreshed == "待领取":
            errors.append(f"{card}: Story 开始后 refreshed 不能为待领取")
        if baseline in {"", "待领取"}:
            errors.append(f"{card}: Story 开始后 code_baseline 必须记录实际版本")
    if f"../stories/{story.path.name}" not in body:
        errors.append(f"{card}: 必须回链 ../stories/{story.path.name}")
    return AgentCard(card, metadata, body, headings)


def _table_data_rows(section: str) -> int:
    rows = [line for line in section.splitlines() if line.startswith("|") and line.endswith("|")]
    return max(0, len(rows) - 2)


def validate_dashboard(path: Path, text: str) -> List[str]:
    errors: List[str] = []
    headings = tuple(match.group(1).strip() for match in HEADING_RE.finditer(text))
    if "Epic / Story 一览" not in headings:
        errors.append(f"{path}: 缺少自动生成章节 ## Epic / Story 一览")
    _validate_heading_contract(path, headings, DASHBOARD_HEADINGS, errors)
    _validate_flat_document(path, text, errors, allow_tables=True)
    _validate_budget(path, text, DASHBOARD_CONTENT_LIMIT, errors)
    for heading, limit in DASHBOARD_ROW_LIMITS.items():
        rows = _table_data_rows(_section(text, heading))
        if rows > limit:
            errors.append(f"{path}: ## {heading} 最多 {limit} 行，当前 {rows} 行")
    return errors


def validate_overview(path: Path, text: str) -> List[str]:
    errors: List[str] = []
    headings = tuple(match.group(1).strip() for match in HEADING_RE.finditer(text))
    for required in OVERVIEW_HEADINGS:
        if required not in headings:
            errors.append(f"{path}: 缺少二级标题 ## {required}")
    _validate_heading_contract(path, headings, OVERVIEW_HEADINGS, errors)
    _validate_flat_document(path, text, errors, allow_tables=False)
    _validate_budget(path, text, OVERVIEW_CONTENT_LIMIT, errors)
    return errors


def ready_story_ids(stories: Sequence[WorkItem]) -> Tuple[str, ...]:
    completed = {story.item_id for story in stories if story.status == "done"}
    return tuple(
        story.item_id
        for story in stories
        if story.status == "todo" and set(story.depends_on).issubset(completed)
    )


def validate_project(epic: WorkItem, stories: Sequence[WorkItem]) -> List[str]:
    errors: List[str] = []
    errors.extend(_require_fields(epic, ("kind", "id", "title", "status", "owner", "updated", "coverage")))
    if epic.metadata.get("kind") != "epic":
        errors.append(f"{epic.path}: kind 必须为 epic")
    if not EPIC_ID_RE.fullmatch(str(epic.metadata.get("id", ""))):
        errors.append(f"{epic.path}: Epic id 必须匹配 EPIC-[A-Z0-9-]+")
    elif epic.path.parent.name != "epics" or epic.path.name != f"{epic.metadata.get('id')}.md":
        errors.append(f"{epic.path}: Epic 必须独立保存为 epics/{epic.metadata.get('id')}.md")
    if epic.metadata.get("status") not in STATUS_LABELS:
        errors.append(f"{epic.path}: status 必须是 {', '.join(STATUS_LABELS)}")
    for field in ("title", "owner"):
        if not str(epic.metadata.get(field, "")).strip():
            errors.append(f"{epic.path}: {field} 不能为空")
    _validate_date(epic, errors)
    _validate_sections(epic, ("愿景", "成功标准", "Story 地图"), errors)
    _validate_heading_contract(epic.path, epic.headings, EPIC_HEADINGS, errors)
    _validate_flat_document(epic.path, epic.body, errors, allow_tables=True)
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
    agent_cards: List[AgentCard] = []
    for story in stories:
        errors.extend(
            _require_fields(
                story,
                (
                    "kind",
                    "id",
                    "epic",
                    "title",
                    "status",
                    "gate",
                    "owner",
                    "depends_on",
                    "blocker",
                    "updated",
                    "intent_version",
                ),
            )
        )
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
        if story.metadata.get("status") not in STATUS_LABELS:
            errors.append(f"{story.path}: status 必须是 {', '.join(STATUS_LABELS)}")
        gate = str(story.metadata.get("gate", ""))
        if not GATE_ID_RE.fullmatch(gate):
            errors.append(f"{story.path}: gate 必须是稳定的字母数字标识")
        if not isinstance(story.metadata.get("depends_on"), list):
            errors.append(f"{story.path}: depends_on 必须使用内联列表，如 [STORY-01]")
        if not str(story.metadata.get("intent_version", "")).isdigit() or int(
            str(story.metadata.get("intent_version", "0"))
        ) < 1:
            errors.append(f"{story.path}: intent_version 必须是正整数")
        for field in ("title", "owner", "blocker"):
            if not str(story.metadata.get(field, "")).strip():
                errors.append(f"{story.path}: {field} 不能为空")
        _validate_date(story, errors)
        _validate_sections(story, ("愿景", "范围", "TODO", "验收标准"), errors)
        _validate_heading_contract(story.path, story.headings, STORY_HEADINGS, errors)
        _validate_flat_document(story.path, story.body, errors, allow_tables=False)
        _validate_budget(story.path, story.body, STORY_CONTENT_LIMIT, errors)
        card = _validate_agent_card(story, errors)
        if card:
            agent_cards.append(card)
        if not MIN_TODOS <= len(story.todos) <= MAX_TODOS:
            errors.append(f"{story.path}: TODO 必须包含 {MIN_TODOS}～{MAX_TODOS} 个复选项")
        for _, todo in story.todos:
            length = visible_char_count(todo)
            if length > MAX_TODO_CHARS:
                errors.append(f"{story.path}: TODO 单项有效字符 {length} 超过上限 {MAX_TODO_CHARS}: {todo}")
        all_done = bool(story.todos) and story.todo_done == len(story.todos)
        if story.status == "done" and not all_done:
            errors.append(f"{story.path}: status=done 时所有 TODO 必须勾选")
        if all_done and story.status != "done":
            errors.append(f"{story.path}: TODO 已全部完成，status 应为 done")
        blocker = str(story.metadata.get("blocker", "")).strip()
        if story.status == "blocked" and blocker in {"", "无"}:
            errors.append(f"{story.path}: status=blocked 时 blocker 必须说明阻塞")
        if story.status != "blocked" and blocker not in {"", "无"}:
            errors.append(f"{story.path}: blocker 非“无”时 status 必须为 blocked")
        if story.status in {"in_progress", "done"} and str(story.metadata.get("owner", "")).strip() == "待领取":
            errors.append(f"{story.path}: {story.status} 时 owner 不能为待领取")
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
    for card in agent_cards:
        for coverage_id in card.owns:
            owners.setdefault(coverage_id, []).append(str(card.metadata.get("story", card.path.name)))
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
            elif story.status in {"in_progress", "done"} and story_by_id[dependency].status != "done":
                errors.append(f"{story.path}: {story.status} 但依赖 {dependency} 尚未完成")

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

    all_stories_done = bool(stories) and all(story.status == "done" for story in stories)
    if all_stories_done and epic.status != "done":
        errors.append(f"{epic.path}: 所有 Story 已完成，Epic status 应为 done")
    if epic.status == "done" and not all_stories_done:
        errors.append(f"{epic.path}: Epic status=done 时所有 Story 必须完成")
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


def dashboard_block(epic: WorkItem, stories: Sequence[WorkItem], dashboard_path: Path) -> str:
    completed = sum(1 for story in stories if story.status == "done")
    active = [story.item_id for story in stories if story.status == "in_progress"]
    ready = ready_story_ids(stories)
    epic_link = _markdown_link(f"{epic.item_id} {epic.title}", epic.path, dashboard_path.parent)
    lines = [
        START_MARKER,
        "## Epic / Story 一览",
        "",
        f"- Epic：{epic_link}",
        f"- Story：{completed}/{len(stories)} 已完成",
        f"- 当前推进：{', '.join(active) if active else '无'}",
        f"- 可领取：{', '.join(ready) if ready else '无'}",
        "",
        "| Story | 门禁 | 状态 | TODO | 依赖 | 负责人 | 当前阻塞 | 下一项 |",
        "| --- | --- | --- | ---: | --- | --- | --- | --- |",
    ]
    for story in stories:
        story_link = _markdown_link(f"{story.item_id} {story.title}", story.path, dashboard_path.parent)
        dependencies = ", ".join(story.depends_on) if story.depends_on else "无"
        todo = f"{story.todo_done}/{len(story.todos)}"
        lines.append(
            "| "
            + " | ".join(
                (
                    _table_cell(story_link),
                    _table_cell(story.metadata["gate"]),
                    _table_cell(STATUS_LABELS[story.status]),
                    _table_cell(todo),
                    _table_cell(dependencies),
                    _table_cell(story.metadata["owner"]),
                    _table_cell(story.metadata["blocker"]),
                    _table_cell(story.next_todo),
                )
            )
            + " |"
        )
    lines.extend(("", "本区块由 Epic/Story 脚本生成；请修改 Story 元数据和 TODO，不要直接编辑表格。", END_MARKER))
    return "\n".join(lines)


def _replace_dashboard(text: str, block: str, path: Path) -> str:
    if text.count(START_MARKER) != 1 or text.count(END_MARKER) != 1:
        raise DocumentError(f"{path}: 必须且只能包含一组 Epic/Story 仪表盘标记")
    start = text.index(START_MARKER)
    end = text.index(END_MARKER)
    if end < start:
        raise DocumentError(f"{path}: 仪表盘标记顺序错误")
    end += len(END_MARKER)
    return text[:start] + block + text[end:]


def _atomic_write(path: Path, text: str) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            handle.write(text)
            temporary = Path(handle.name)
        temporary.chmod(path.stat().st_mode)
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
    if args.overview:
        overview = args.overview.read_text(encoding="utf-8")
        if not _report_errors(validate_overview(args.overview, overview)):
            return 1
    if args.dashboard:
        current = args.dashboard.read_text(encoding="utf-8")
        expected = _replace_dashboard(current, dashboard_block(epic, stories, args.dashboard), args.dashboard)
        if not _report_errors(validate_dashboard(args.dashboard, expected)):
            return 1
        if expected != current:
            print(f"ERROR: 仪表盘已过期，请运行 render: {args.dashboard}", file=sys.stderr)
            return 1
    print(f"OK: {epic.item_id}; stories={len(stories)}; completed={sum(s.status == 'done' for s in stories)}")
    return 0


def command_render(args: argparse.Namespace) -> int:
    epic, stories = load_project(args.epic, args.stories_dir)
    if not _validate_or_report(epic, stories):
        return 1
    current = args.dashboard.read_text(encoding="utf-8")
    updated = _replace_dashboard(current, dashboard_block(epic, stories, args.dashboard), args.dashboard)
    if not _report_errors(validate_dashboard(args.dashboard, updated)):
        return 1
    if updated == current:
        print(f"OK: 仪表盘已是最新: {args.dashboard}")
        return 0
    _atomic_write(args.dashboard, updated)
    print(f"OK: 已更新仪表盘: {args.dashboard}")
    return 0


def command_status(args: argparse.Namespace) -> int:
    epic, stories = load_project(args.epic, args.stories_dir)
    if not _validate_or_report(epic, stories):
        return 1
    ready = ready_story_ids(stories)
    payload = {
        "epic": {
            "id": epic.item_id,
            "title": epic.title,
            "status": epic.status,
            "coverage": list(epic.metadata.get("coverage", [])),
            "stories_completed": sum(story.status == "done" for story in stories),
            "stories_total": len(stories),
            "ready_stories": list(ready),
            "content_chars": epic.content_chars,
            "content_limit": EPIC_CONTENT_LIMIT,
        },
        "stories": [
            {
                "id": story.item_id,
                "title": story.title,
                "gate": story.metadata["gate"],
                "status": story.status,
                "todo_done": story.todo_done,
                "todo_total": len(story.todos),
                "depends_on": list(story.depends_on),
                "owner": story.metadata["owner"],
                "blocker": story.metadata["blocker"],
                "next_todo": story.next_todo,
                "content_chars": story.content_chars,
                "content_limit": STORY_CONTENT_LIMIT,
            }
            for story in stories
        ],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"{epic.item_id} {epic.title}: {STATUS_LABELS[epic.status]}")
        print(f"可领取: {', '.join(ready) if ready else '无'}")
        for story in stories:
            print(
                f"{story.item_id}\t{STATUS_LABELS[story.status]}\t"
                f"TODO {story.todo_done}/{len(story.todos)}\t{story.next_todo}"
            )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="校验 Epic/Story、意图版本、覆盖主责、执行卡与内容预算，并生成项目仪表盘。",
        epilog=(
            "输出与退出码:\n"
            "  check/status 不修改文件；render 只替换 dashboard 标记区块；错误写入 stderr。\n"
            "  0=成功，1=格式/状态/仪表盘校验失败，2=命令行或 I/O 错误。\n\n"
            "示例:\n"
            "  epic_story.py check --epic topic/epics/EPIC-ID.md --stories-dir topic/stories\n"
            "  epic_story.py check --epic topic/epics/EPIC-ID.md --stories-dir topic/stories "
            "--overview topic/README.md --dashboard topic/项目进展.md\n"
            "  epic_story.py render --epic topic/epics/EPIC-ID.md --stories-dir topic/stories "
            "--dashboard topic/项目进展.md\n"
            "  epic_story.py status --epic topic/epics/EPIC-ID.md --stories-dir topic/stories --json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--epic", type=Path, required=True, help="Epic Markdown 文件")
        subparser.add_argument("--stories-dir", type=Path, required=True, help="包含 Story-*.md 的目录")

    check = subparsers.add_parser("check", help="校验格式、依赖、状态和可选仪表盘新鲜度")
    add_common(check)
    check.add_argument("--overview", type=Path, help="同时检查人读项目入口的结构和字数")
    check.add_argument("--dashboard", type=Path, help="同时检查受控仪表盘是否为最新")
    check.set_defaults(handler=command_check)

    render = subparsers.add_parser("render", help="校验后更新仪表盘受控区块")
    add_common(render)
    render.add_argument("--dashboard", type=Path, required=True, help="包含受控标记的项目进展文件")
    render.set_defaults(handler=command_render)

    status = subparsers.add_parser("status", help="输出 Epic/Story 当前状态")
    add_common(status)
    status.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    status.set_defaults(handler=command_status)
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
