#!/usr/bin/env python3
"""维护 large-task-planning v2 的 Agent JSON 与人读投影。

脚本定义：以 `agent/plan.json` 和 `agent/stories/*.json` 为唯一事实源，校验计划、
提取单 Story brief、原子迁移状态，并生成面向人的 SPEC.md 与 STATUS.md。
参数定义：项目命令接收 --plan 和 --stories-dir；write 接收 JSON 文件与输入；
migrate-v1 接收 v1 Epic、Story 目录和一个空的新输出目录。
输出定义：render/transition/write/migrate-v1 会写明确目标；其他命令只读。
退出码：0 成功，1 契约失败，2 I/O 失败。脚本不执行 Story 或修改业务代码。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Sequence


SCHEMA_VERSION = 2
PLAN_KIND = "large-task-plan"
STORY_KIND = "large-task-story"
STATUSES = ("todo", "in_progress", "blocked", "done")
PLAN_ID_RE = re.compile(r"^EPIC-[A-Z0-9][A-Z0-9-]*$")
STORY_ID_RE = re.compile(r"^STORY-(\d{2})(?:\.([1-9]\d*))?$")
GOLDEN_ID_RE = re.compile(r"^GC-(?:0[1-9]|[1-9]\d+)$")
USER_STORY_ID_RE = re.compile(r"^US-(?:0[1-9]|[1-9]\d+)$")
DECISION_ID_RE = re.compile(r"^D-(?:0[1-9]|[1-9]\d+)$")
ACCEPTANCE_ID_RE = re.compile(r"^AC-(?:0[1-9]|[1-9]\d+)$")
LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
LEGACY_SECTION_RE = re.compile(
    r"^<!--\s*large-task-planning:([a-z][a-z0-9-]*)[^>]*-->[ \t]*\n^##\s+.+?$",
    re.MULTILINE,
)

PLAN_FIELDS = (
    "kind",
    "schema_version",
    "id",
    "title",
    "goal_version",
    "updated",
    "language",
    "spec",
    "golden_acceptance",
    "final_story",
)
SPEC_FIELDS = (
    "problem_statement",
    "solution",
    "user_stories",
    "boundaries",
    "decisions",
    "testing",
    "out_of_scope",
)
USER_STORY_FIELDS = ("id", "actor", "want", "benefit")
DECISION_FIELDS = ("id", "decision", "rationale", "impact", "owner")
TESTING_FIELDS = ("seams", "strategy")
GOLDEN_FIELDS = ("id", "title", "fixture", "actions", "oracle", "evidence")
STORY_FIELDS = (
    "kind",
    "schema_version",
    "id",
    "plan",
    "title",
    "intent_version",
    "status",
    "blocked_by",
    "covers",
    "outcome",
    "acceptance",
    "context",
    "owner",
    "blocker",
    "updated",
    "handoff",
)
ACCEPTANCE_FIELDS = ("id", "criterion", "passed")
CONTEXT_FIELDS = (
    "test_seams",
    "code_anchors",
    "authoritative_inputs",
    "write_scope",
    "stop_conditions",
)
HANDOFF_FIELDS = ("summary", "verification", "remaining", "risks", "next")

HUMAN_LABELS = {
    "zh-Hans": {
        "generated": "> 这是供项目参与者阅读的视图，由结构化计划自动生成；请通过计划工具更新内容。",
        "status_link": "[查看当前进展](STATUS.md)",
        "spec_link": "[查看目标与验收](SPEC.md)",
        "why": "为什么要做",
        "experience": "完成后是什么样",
        "promises": "对使用者的承诺",
        "boundaries": "必须守住的边界",
        "decisions": "已经做出的关键取舍",
        "testing": "怎样确认真的完成",
        "seams": "我们从哪里观察结果",
        "golden": "必须走通的真实场景",
        "delivery": "我们会怎样走到终点",
        "out_of_scope": "范围之外",
        "status": "进展",
        "progress": "此刻的判断",
        "current": "正在推进",
        "ready": "接下来",
        "queued": "之后的路线",
        "attention": "需要关注",
        "completed": "已经得到的结果",
        "none": "无",
        "owner_user": "产品约束",
        "owner_agent": "实现取舍",
        "fixture": "准备",
        "actions": "怎么做",
        "oracle": "应该看到",
        "evidence": "留下什么证据",
        "no_current": "当前没有正在执行的工作。",
        "no_ready": "当前没有可直接开始的下一项结果。",
        "no_queue": "没有尚在等待前置结果的工作。",
        "no_attention": "目前没有需要人工介入的阻塞或已知残余风险。",
        "no_completed": "还没有已经验证完成的结果。",
    },
    "en": {
        "generated": "> This reader view is generated from the structured plan; update it through the plan tooling.",
        "status_link": "[View current progress](STATUS.md)",
        "spec_link": "[View goals and acceptance](SPEC.md)",
        "why": "Why this matters",
        "experience": "What done looks like",
        "promises": "Promises to users",
        "boundaries": "Boundaries we must preserve",
        "decisions": "Key trade-offs already made",
        "testing": "How we will know it is done",
        "seams": "Where results are observed",
        "golden": "Real journeys that must work",
        "delivery": "How we will reach the outcome",
        "out_of_scope": "Out of scope",
        "status": "Progress",
        "progress": "Current assessment",
        "current": "In progress now",
        "ready": "Up next",
        "queued": "Later on the route",
        "attention": "Needs attention",
        "completed": "Outcomes already achieved",
        "none": "None",
        "owner_user": "Product constraint",
        "owner_agent": "Implementation trade-off",
        "fixture": "Set-up",
        "actions": "What to do",
        "oracle": "What we should see",
        "evidence": "Evidence to retain",
        "no_current": "No work is currently in progress.",
        "no_ready": "No next outcome can be started immediately.",
        "no_queue": "No work is waiting on an earlier outcome.",
        "no_attention": "No blocker or known residual risk currently needs human attention.",
        "no_completed": "No outcome has been verified yet.",
    },
}


class PlanError(RuntimeError):
    """计划、投影或状态不满足 v2 契约。"""


@dataclass(frozen=True)
class Plan:
    path: Path
    data: dict[str, Any]

    @property
    def item_id(self) -> str:
        return str(self.data.get("id", ""))

    @property
    def title(self) -> str:
        return str(self.data.get("title", ""))


@dataclass(frozen=True)
class Story:
    path: Path
    data: dict[str, Any]

    @property
    def item_id(self) -> str:
        return str(self.data.get("id", ""))

    @property
    def title(self) -> str:
        return str(self.data.get("title", ""))

    @property
    def status(self) -> str:
        return str(self.data.get("status", ""))

    @property
    def blocked_by(self) -> tuple[str, ...]:
        return tuple(_as_string_list(self.data.get("blocked_by")))

    @property
    def covers(self) -> tuple[str, ...]:
        return tuple(_as_string_list(self.data.get("covers")))


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, str) and item.strip()]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise PlanError(f"无法读取 {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise PlanError(f"{path}: JSON 无效: {error}") from error
    if not isinstance(value, dict):
        raise PlanError(f"{path}: 顶层必须是 JSON 对象")
    return value


def _ordered(data: dict[str, Any], order: Sequence[str]) -> dict[str, Any]:
    result = {key: data[key] for key in order if key in data}
    result.update({key: value for key, value in data.items() if key not in result})
    return result


def canonicalize(data: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(data)
    if result.get("kind") == PLAN_KIND:
        spec = result.get("spec")
        if isinstance(spec, dict):
            spec = _ordered(spec, SPEC_FIELDS)
            testing = spec.get("testing")
            if isinstance(testing, dict):
                spec["testing"] = _ordered(testing, TESTING_FIELDS)
            result["spec"] = spec
        return _ordered(result, PLAN_FIELDS)
    if result.get("kind") == STORY_KIND:
        context = result.get("context")
        if isinstance(context, dict):
            result["context"] = _ordered(context, CONTEXT_FIELDS)
        handoff = result.get("handoff")
        if isinstance(handoff, dict):
            result["handoff"] = _ordered(handoff, HANDOFF_FIELDS)
        return _ordered(result, STORY_FIELDS)
    return result


def dump_json(data: dict[str, Any]) -> str:
    return json.dumps(canonicalize(data), ensure_ascii=False, indent=2) + "\n"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _unknown_fields(value: dict[str, Any], allowed: Sequence[str], label: str, errors: list[str]) -> None:
    unknown = sorted(set(value) - set(allowed))
    missing = [field for field in allowed if field not in value]
    if unknown:
        errors.append(f"{label}: 未知字段: {', '.join(unknown)}")
    if missing:
        errors.append(f"{label}: 缺少字段: {', '.join(missing)}")


def _nonempty_string(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label}: 必须是非空字符串")


def _string_list(
    value: Any,
    label: str,
    errors: list[str],
    *,
    nonempty: bool = False,
) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{label}: 必须是非空字符串数组")
        return
    if nonempty and not value:
        errors.append(f"{label}: 至少需要一项")


def _iso_date(value: Any, label: str, errors: list[str]) -> None:
    try:
        date.fromisoformat(str(value))
    except ValueError:
        errors.append(f"{label}: 必须是 YYYY-MM-DD")


def _unique_ids(items: Sequence[Any], field: str, pattern: re.Pattern[str], label: str, errors: list[str]) -> None:
    ids: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{label}[{index}]: 必须是对象")
            continue
        item_id = str(item.get(field, ""))
        if not pattern.fullmatch(item_id):
            errors.append(f"{label}[{index}].{field}: ID 无效: {item_id!r}")
        ids.append(item_id)
    if len(ids) != len(set(ids)):
        errors.append(f"{label}: ID 必须唯一")


def validate_plan_data(path: Path, data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    label = str(path)
    _unknown_fields(data, PLAN_FIELDS, label, errors)
    if any(field not in data for field in PLAN_FIELDS):
        return errors
    if data["kind"] != PLAN_KIND or data["schema_version"] != SCHEMA_VERSION:
        errors.append(f"{label}: 必须是 kind={PLAN_KIND}, schema_version={SCHEMA_VERSION}")
    if not PLAN_ID_RE.fullmatch(str(data["id"])):
        errors.append(f"{label}.id: 必须匹配 EPIC-<NAME>")
    _nonempty_string(data["title"], f"{label}.title", errors)
    if not isinstance(data["goal_version"], int) or isinstance(data["goal_version"], bool) or data["goal_version"] < 1:
        errors.append(f"{label}.goal_version: 必须是正整数")
    _iso_date(data["updated"], f"{label}.updated", errors)
    if not isinstance(data["language"], str) or not LANGUAGE_RE.fullmatch(data["language"]):
        errors.append(f"{label}.language: 必须是 BCP-47 标签")
    if not STORY_ID_RE.fullmatch(str(data["final_story"])):
        errors.append(f"{label}.final_story: 必须是 Story ID")

    spec = data["spec"]
    if not isinstance(spec, dict):
        errors.append(f"{label}.spec: 必须是对象")
    else:
        _unknown_fields(spec, SPEC_FIELDS, f"{label}.spec", errors)
        if all(field in spec for field in SPEC_FIELDS):
            _nonempty_string(spec["problem_statement"], f"{label}.spec.problem_statement", errors)
            _nonempty_string(spec["solution"], f"{label}.spec.solution", errors)
            _string_list(spec["boundaries"], f"{label}.spec.boundaries", errors, nonempty=True)
            _string_list(spec["out_of_scope"], f"{label}.spec.out_of_scope", errors)
            stories = spec["user_stories"]
            if not isinstance(stories, list) or not stories:
                errors.append(f"{label}.spec.user_stories: 至少需要一项")
            else:
                _unique_ids(stories, "id", USER_STORY_ID_RE, f"{label}.spec.user_stories", errors)
                for index, item in enumerate(stories):
                    if isinstance(item, dict):
                        item_label = f"{label}.spec.user_stories[{index}]"
                        _unknown_fields(item, USER_STORY_FIELDS, item_label, errors)
                        for field in USER_STORY_FIELDS[1:]:
                            if field in item:
                                _nonempty_string(item[field], f"{item_label}.{field}", errors)
            decisions = spec["decisions"]
            if not isinstance(decisions, list):
                errors.append(f"{label}.spec.decisions: 必须是数组")
            else:
                _unique_ids(decisions, "id", DECISION_ID_RE, f"{label}.spec.decisions", errors)
                for index, item in enumerate(decisions):
                    if isinstance(item, dict):
                        item_label = f"{label}.spec.decisions[{index}]"
                        _unknown_fields(item, DECISION_FIELDS, item_label, errors)
                        for field in ("decision", "rationale", "impact"):
                            if field in item:
                                _nonempty_string(item[field], f"{item_label}.{field}", errors)
                        if item.get("owner") not in {"user", "agent"}:
                            errors.append(f"{item_label}.owner: 必须是 user 或 agent")
            testing = spec["testing"]
            if not isinstance(testing, dict):
                errors.append(f"{label}.spec.testing: 必须是对象")
            else:
                _unknown_fields(testing, TESTING_FIELDS, f"{label}.spec.testing", errors)
                if "seams" in testing:
                    _string_list(testing["seams"], f"{label}.spec.testing.seams", errors, nonempty=True)
                if "strategy" in testing:
                    _nonempty_string(testing["strategy"], f"{label}.spec.testing.strategy", errors)

    cases = data["golden_acceptance"]
    if not isinstance(cases, list) or not cases:
        errors.append(f"{label}.golden_acceptance: 至少需要一项")
    else:
        _unique_ids(cases, "id", GOLDEN_ID_RE, f"{label}.golden_acceptance", errors)
        for index, item in enumerate(cases):
            if not isinstance(item, dict):
                continue
            item_label = f"{label}.golden_acceptance[{index}]"
            _unknown_fields(item, GOLDEN_FIELDS, item_label, errors)
            if "title" in item:
                _nonempty_string(item["title"], f"{item_label}.title", errors)
            for field in ("fixture", "actions", "oracle", "evidence"):
                if field in item:
                    _string_list(item[field], f"{item_label}.{field}", errors, nonempty=True)
    return errors


def validate_story_data(path: Path, data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    label = str(path)
    _unknown_fields(data, STORY_FIELDS, label, errors)
    if any(field not in data for field in STORY_FIELDS):
        return errors
    if data["kind"] != STORY_KIND or data["schema_version"] != SCHEMA_VERSION:
        errors.append(f"{label}: 必须是 kind={STORY_KIND}, schema_version={SCHEMA_VERSION}")
    story_id = str(data["id"])
    if not STORY_ID_RE.fullmatch(story_id):
        errors.append(f"{label}.id: 必须匹配 STORY-NN 或 STORY-NN.M")
    if not path.name.startswith(story_id):
        errors.append(f"{label}: 文件名必须以 {story_id} 开头")
    if not PLAN_ID_RE.fullmatch(str(data["plan"])):
        errors.append(f"{label}.plan: 必须是 EPIC ID")
    _nonempty_string(data["title"], f"{label}.title", errors)
    _nonempty_string(data["outcome"], f"{label}.outcome", errors)
    if not isinstance(data["intent_version"], int) or isinstance(data["intent_version"], bool) or data["intent_version"] < 1:
        errors.append(f"{label}.intent_version: 必须是正整数")
    status = str(data["status"])
    if status not in STATUSES:
        errors.append(f"{label}.status: 必须是 {', '.join(STATUSES)}")
    for field in ("blocked_by", "covers"):
        _string_list(data[field], f"{label}.{field}", errors)
        values = data[field] if isinstance(data[field], list) else []
        if len(values) != len(set(str(item) for item in values)):
            errors.append(f"{label}.{field}: 不能重复")
    if story_id in _as_string_list(data["blocked_by"]):
        errors.append(f"{label}.blocked_by: Story 不能阻塞自己")

    acceptance = data["acceptance"]
    if not isinstance(acceptance, list) or not acceptance:
        errors.append(f"{label}.acceptance: 至少需要一项")
    else:
        _unique_ids(acceptance, "id", ACCEPTANCE_ID_RE, f"{label}.acceptance", errors)
        for index, item in enumerate(acceptance):
            if not isinstance(item, dict):
                continue
            item_label = f"{label}.acceptance[{index}]"
            _unknown_fields(item, ACCEPTANCE_FIELDS, item_label, errors)
            if "criterion" in item:
                _nonempty_string(item["criterion"], f"{item_label}.criterion", errors)
            if "passed" in item and not isinstance(item["passed"], bool):
                errors.append(f"{item_label}.passed: 必须是布尔值")

    context = data["context"]
    if not isinstance(context, dict):
        errors.append(f"{label}.context: 必须是对象")
    else:
        _unknown_fields(context, CONTEXT_FIELDS, f"{label}.context", errors)
        for field in CONTEXT_FIELDS:
            if field in context:
                _string_list(
                    context[field],
                    f"{label}.context.{field}",
                    errors,
                    nonempty=field in {"test_seams", "code_anchors"},
                )

    owner = data["owner"]
    blocker = data["blocker"]
    if status == "todo":
        if owner is not None:
            errors.append(f"{label}.owner: todo Story 必须为 null")
    elif not isinstance(owner, str) or not owner.strip():
        errors.append(f"{label}.owner: active Story 必须是非空字符串")
    if status == "blocked":
        if not isinstance(blocker, str) or not blocker.strip():
            errors.append(f"{label}.blocker: blocked Story 必须写明具体原因")
    elif blocker is not None:
        errors.append(f"{label}.blocker: 非 blocked Story 必须为 null")
    _iso_date(data["updated"], f"{label}.updated", errors)

    handoff = data["handoff"]
    if handoff is not None and not isinstance(handoff, dict):
        errors.append(f"{label}.handoff: 必须为 null 或对象")
    elif isinstance(handoff, dict):
        _unknown_fields(handoff, HANDOFF_FIELDS, f"{label}.handoff", errors)
        if "summary" in handoff:
            _nonempty_string(handoff["summary"], f"{label}.handoff.summary", errors)
        if "next" in handoff:
            _nonempty_string(handoff["next"], f"{label}.handoff.next", errors)
        for field in ("verification", "remaining", "risks"):
            if field in handoff:
                _string_list(handoff[field], f"{label}.handoff.{field}", errors)

    if status == "done":
        if isinstance(acceptance, list) and any(
            isinstance(item, dict) and item.get("passed") is not True for item in acceptance
        ):
            errors.append(f"{label}: done Story 的 acceptance 必须全部 passed=true")
        if not isinstance(handoff, dict):
            errors.append(f"{label}: done Story 必须有 handoff")
        else:
            if not handoff.get("verification"):
                errors.append(f"{label}: done Story 的 handoff.verification 不能为空")
            if handoff.get("remaining"):
                errors.append(f"{label}: done Story 的 handoff.remaining 必须为空")
    return errors


def story_order(story_id: str) -> tuple[int, int, str]:
    match = STORY_ID_RE.fullmatch(story_id)
    if not match:
        return (sys.maxsize, sys.maxsize, story_id)
    return (int(match.group(1)), int(match.group(2) or 0), story_id)


def load_project(plan_path: Path, stories_dir: Path) -> tuple[Plan, list[Story]]:
    if plan_path.name != "plan.json" or plan_path.parent.name != "agent":
        raise PlanError("--plan 必须是 <topic>/agent/plan.json")
    if stories_dir.name != "stories" or stories_dir.parent.resolve() != plan_path.parent.resolve():
        raise PlanError("--stories-dir 必须是同一 agent/ 下的 stories/")
    if not stories_dir.is_dir():
        raise PlanError(f"Story 目录不存在: {stories_dir}")
    plan = Plan(plan_path, _read_json(plan_path))
    story_paths = sorted(stories_dir.glob("*.json"))
    stories = [Story(path, _read_json(path)) for path in story_paths]
    return plan, sorted(stories, key=lambda item: story_order(item.item_id))


def _cycle(stories: dict[str, Story]) -> list[str] | None:
    visiting: list[str] = []
    complete: set[str] = set()

    def visit(story_id: str) -> list[str] | None:
        if story_id in complete:
            return None
        if story_id in visiting:
            start = visiting.index(story_id)
            return visiting[start:] + [story_id]
        visiting.append(story_id)
        for dependency in stories[story_id].blocked_by:
            if dependency in stories:
                found = visit(dependency)
                if found:
                    return found
        visiting.pop()
        complete.add(story_id)
        return None

    for story_id in stories:
        found = visit(story_id)
        if found:
            return found
    return None


def golden_ids(plan: Plan) -> set[str]:
    cases = plan.data.get("golden_acceptance")
    if not isinstance(cases, list):
        return set()
    return {str(item.get("id")) for item in cases if isinstance(item, dict)}


def validate_project(plan: Plan, stories: Sequence[Story]) -> list[str]:
    errors = validate_plan_data(plan.path, plan.data)
    for story in stories:
        errors.extend(validate_story_data(story.path, story.data))
    if not stories:
        errors.append(f"{plan.path}: 至少需要一个 Story")
        return errors
    by_id: dict[str, Story] = {}
    for story in stories:
        if story.item_id in by_id:
            errors.append(f"{story.path}: Story ID 重复: {story.item_id}")
        by_id[story.item_id] = story
        if story.data.get("plan") != plan.data.get("id"):
            errors.append(f"{story.path}.plan: 与 {plan.path}.id 不一致")
    known = set(by_id)
    cases = golden_ids(plan)
    for story in stories:
        unknown_dependencies = sorted(set(story.blocked_by) - known)
        if unknown_dependencies:
            errors.append(f"{story.path}: 未知 blocker: {', '.join(unknown_dependencies)}")
        unknown_cases = sorted(set(story.covers) - cases)
        if unknown_cases:
            errors.append(f"{story.path}: covers 引用了未知黄金案例: {', '.join(unknown_cases)}")
        if story.status in {"in_progress", "done"}:
            unfinished = [
                dependency
                for dependency in story.blocked_by
                if dependency in by_id and by_id[dependency].status != "done"
            ]
            if unfinished:
                errors.append(f"{story.path}: {story.status} 但 blocker 未完成: {', '.join(unfinished)}")
    cycle = _cycle(by_id)
    if cycle:
        errors.append(f"{plan.path}: Story blocker 成环: {' -> '.join(cycle)}")
    final_id = str(plan.data.get("final_story", ""))
    final = by_id.get(final_id)
    if final is None:
        errors.append(f"{plan.path}: final_story 不存在: {final_id}")
    else:
        reachable: set[str] = set()

        def collect(story_id: str) -> None:
            for dependency in by_id[story_id].blocked_by:
                if dependency in by_id and dependency not in reachable:
                    reachable.add(dependency)
                    collect(dependency)

        collect(final_id)
        missing_paths = sorted(known - {final_id} - reachable, key=story_order)
        if missing_paths:
            errors.append(
                f"{plan.path}: final_story 必须直接或间接阻塞于全部 Story，缺少: {', '.join(missing_paths)}"
            )
        missing_cases = sorted(cases - set(final.covers))
        if missing_cases:
            errors.append(f"{final.path}: final_story 缺少黄金覆盖: {', '.join(missing_cases)}")
    return errors


def report(errors: Iterable[str]) -> bool:
    items = list(errors)
    for error in items:
        print(f"ERROR: {error}", file=sys.stderr)
    return not items


def ready_story_ids(stories: Sequence[Story]) -> list[str]:
    by_id = {story.item_id: story for story in stories}
    return [
        story.item_id
        for story in stories
        if story.status == "todo"
        and all(by_id[dependency].status == "done" for dependency in story.blocked_by)
    ]


def status_payload(plan: Plan, stories: Sequence[Story]) -> dict[str, Any]:
    ready = ready_story_ids(stories)
    completed = sum(story.status == "done" for story in stories)
    if completed == len(stories):
        overall = "done"
    elif any(story.status == "in_progress" for story in stories) or ready:
        overall = "active"
    else:
        overall = "blocked"
    return {
        "schema_version": SCHEMA_VERSION,
        "plan": {
            "id": plan.item_id,
            "title": plan.title,
            "status": overall,
            "completed": completed,
            "total": len(stories),
            "final_story": plan.data["final_story"],
        },
        "ready": ready,
        "stories": [
            {
                "id": story.item_id,
                "title": story.title,
                "status": story.status,
                "owner": story.data["owner"],
                "blocked_by": list(story.blocked_by),
                "covers": list(story.covers),
                "acceptance": {
                    "passed": sum(
                        item.get("passed") is True
                        for item in story.data["acceptance"]
                        if isinstance(item, dict)
                    ),
                    "total": len(story.data["acceptance"]),
                },
                "blocker": story.data["blocker"],
                "path": str(story.path),
            }
            for story in stories
        ],
    }


def _labels(plan: Plan) -> dict[str, str]:
    language = str(plan.data.get("language", "en")).lower()
    return HUMAN_LABELS["zh-Hans"] if language == "zh" or language.startswith("zh-") else HUMAN_LABELS["en"]


def _bullets(values: Sequence[str], none: str) -> str:
    return "\n".join(f"- {value}" for value in values) if values else f"- {none}"


def _inline_steps(values: Sequence[str], *, chinese: bool) -> str:
    cleaned = [value.strip().rstrip("。；;.") for value in values]
    joined = ("；" if chinese else "; ").join(cleaned)
    return f"{joined}。" if chinese else f"{joined}."


def spec_document(plan: Plan, stories: Sequence[Story]) -> str:
    labels = _labels(plan)
    chinese = labels is HUMAN_LABELS["zh-Hans"]
    colon = "：" if chinese else ":"
    spec = plan.data["spec"]
    lines = [f"# {plan.title}", "", labels["generated"], "", labels["status_link"], ""]
    lines.extend([f"## {labels['why']}", "", spec["problem_statement"], ""])
    lines.extend([f"## {labels['experience']}", "", spec["solution"], ""])
    lines.extend([f"## {labels['promises']}", ""])
    for item in spec["user_stories"]:
        lines.append(
            f"- **{item['actor']}：** 可以{item['want']}，从而{item['benefit']}。"
            if chinese
            else f"- **{item['actor']}:** Can {item['want']}, so that {item['benefit']}."
        )
    lines.extend(["", f"## {labels['boundaries']}", "", _bullets(spec["boundaries"], labels["none"]), ""])
    lines.extend([f"## {labels['decisions']}", ""])
    if spec["decisions"]:
        for item in spec["decisions"]:
            owner = labels[f"owner_{item['owner']}"]
            lines.extend(
                [
                    f"### {item['decision']}（{owner}）",
                    "",
                    item["rationale"],
                    "",
                    f"**影响：** {item['impact']}" if chinese else f"**Impact:** {item['impact']}",
                    "",
                ]
            )
    else:
        lines.extend([labels["none"], ""])
    lines.extend([f"## {labels['testing']}", "", f"### {labels['seams']}", ""])
    lines.extend([_bullets(spec["testing"]["seams"], labels["none"]), "", spec["testing"]["strategy"], ""])
    lines.extend([f"### {labels['golden']}", ""])
    for case in plan.data["golden_acceptance"]:
        lines.extend(
            [
                f"#### {case['title']}",
                "",
                f"- **{labels['fixture']}{colon}** {_inline_steps(case['fixture'], chinese=chinese)}",
                f"- **{labels['actions']}{colon}** {_inline_steps(case['actions'], chinese=chinese)}",
                f"- **{labels['oracle']}{colon}** {_inline_steps(case['oracle'], chinese=chinese)}",
                f"- **{labels['evidence']}{colon}** {_inline_steps(case['evidence'], chinese=chinese)}",
                "",
            ]
        )
    lines.extend([f"## {labels['delivery']}", ""])
    for index, story in enumerate(stories, 1):
        lines.extend([f"{index}. **{story.title}**", "", f"   {story.data['outcome']}", ""])
    lines.extend([f"## {labels['out_of_scope']}", "", _bullets(spec["out_of_scope"], labels["none"]), ""])
    return "\n".join(lines).rstrip() + "\n"


def status_document(plan: Plan, stories: Sequence[Story]) -> str:
    labels = _labels(plan)
    payload = status_payload(plan, stories)
    summary = payload["plan"]
    by_status = {status: [story for story in stories if story.status == status] for status in STATUSES}
    latest = max(
        [str(plan.data["updated"]), *(str(story.data["updated"]) for story in stories)]
    )
    lines = [
        f"# {plan.title} — {labels['status']}",
        "",
        labels["generated"],
        "",
        labels["spec_link"],
        "",
    ]
    if summary["status"] == "done":
        assessment = (
            f"已完成。{summary['total']} 项计划结果均已验证。"
            if labels is HUMAN_LABELS["zh-Hans"]
            else f"Complete. All {summary['total']} planned outcomes are verified."
        )
    elif summary["status"] == "blocked":
        assessment = (
            f"当前受阻。已验证 {summary['completed']} / {summary['total']} 项计划结果。"
            if labels is HUMAN_LABELS["zh-Hans"]
            else f"Blocked. {summary['completed']} of {summary['total']} planned outcomes are verified."
        )
    elif not by_status["in_progress"] and summary["completed"] == 0:
        assessment = (
            "尚未开始。第一项结果已经明确，可以直接推进。"
            if labels is HUMAN_LABELS["zh-Hans"]
            else "Not started. The first outcome is clear and ready to begin."
        )
    elif not by_status["in_progress"]:
        assessment = (
            f"处于阶段交接。已验证 {summary['completed']} / {summary['total']} 项计划结果，下一项可以开始。"
            if labels is HUMAN_LABELS["zh-Hans"]
            else f"Between stages. {summary['completed']} of {summary['total']} planned outcomes are verified, and the next is ready."
        )
    else:
        assessment = (
            f"正在推进。已验证 {summary['completed']} / {summary['total']} 项计划结果。"
            if labels is HUMAN_LABELS["zh-Hans"]
            else f"In progress. {summary['completed']} of {summary['total']} planned outcomes are verified."
        )
    lines.extend(
        [
            f"## {labels['progress']}",
            "",
            assessment,
            "",
            f"最近更新：{latest}。" if labels is HUMAN_LABELS["zh-Hans"] else f"Last updated: {latest}.",
            "",
        ]
    )

    def add_outcomes(title: str, items: Sequence[Story], empty: str) -> None:
        lines.extend([f"## {title}", ""])
        if not items:
            lines.extend([empty, ""])
            return
        for story in items:
            lines.append(f"- **{story.title}**：{story.data['outcome']}")
        lines.append("")

    add_outcomes(labels["current"], by_status["in_progress"], labels["no_current"])
    ready_set = set(payload["ready"])
    ready = [story for story in stories if story.item_id in ready_set]
    add_outcomes(labels["ready"], ready, labels["no_ready"])
    queued = [
        story
        for story in stories
        if story.status == "todo" and story.item_id not in ready_set
    ]
    add_outcomes(labels["queued"], queued, labels["no_queue"])

    attention: list[str] = []
    for story in by_status["blocked"]:
        attention.append(f"**{story.title}**：{story.data['blocker']}")
    for story in stories:
        handoff = story.data.get("handoff")
        if isinstance(handoff, dict):
            for risk in _as_string_list(handoff.get("risks")):
                attention.append(f"**{story.title}**：{risk}")
    lines.extend([f"## {labels['attention']}", ""])
    lines.extend(
        [*(f"- {item}" for item in attention), ""]
        if attention
        else [labels["no_attention"], ""]
    )

    lines.extend([f"## {labels['completed']}", ""])
    if not by_status["done"]:
        lines.extend([labels["no_completed"], ""])
    else:
        for story in by_status["done"]:
            handoff = story.data.get("handoff")
            result = handoff.get("summary") if isinstance(handoff, dict) else story.data["outcome"]
            lines.append(f"- **{story.title}**：{result}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def human_paths(plan: Plan) -> tuple[Path, Path]:
    root = plan.path.parent.parent
    return root / "SPEC.md", root / "STATUS.md"


def projection_errors(plan: Plan, stories: Sequence[Story]) -> list[str]:
    spec_path, status_path = human_paths(plan)
    errors: list[str] = []
    expected = ((spec_path, spec_document(plan, stories)), (status_path, status_document(plan, stories)))
    for path, content in expected:
        if not path.is_file():
            errors.append(f"{path}: 人读投影缺失，请运行 render")
            continue
        try:
            current = path.read_text(encoding="utf-8")
        except OSError as error:
            errors.append(f"{path}: 无法读取: {error}")
            continue
        if current != content:
            errors.append(f"{path}: 人读投影已过期，请运行 render")
    return errors


def render_project(plan: Plan, stories: Sequence[Story]) -> tuple[Path, Path]:
    spec_path, status_path = human_paths(plan)
    _atomic_write(spec_path, spec_document(plan, stories))
    _atomic_write(status_path, status_document(plan, stories))
    return spec_path, status_path


def command_check(args: argparse.Namespace) -> int:
    plan, stories = load_project(args.plan, args.stories_dir)
    errors = validate_project(plan, stories)
    if not errors:
        errors.extend(projection_errors(plan, stories))
    if not report(errors):
        return 1
    print(f"OK: {plan.item_id}; stories={len(stories)}; ready={len(ready_story_ids(stories))}; projections=fresh")
    return 0


def command_render(args: argparse.Namespace) -> int:
    plan, stories = load_project(args.plan, args.stories_dir)
    if not report(validate_project(plan, stories)):
        return 1
    spec_path, status_path = render_project(plan, stories)
    print(f"OK: rendered {spec_path} and {status_path}")
    return 0


def command_status(args: argparse.Namespace) -> int:
    plan, stories = load_project(args.plan, args.stories_dir)
    if not report(validate_project(plan, stories)):
        return 1
    payload = status_payload(plan, stories)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        summary = payload["plan"]
        print(f"{summary['id']} {summary['title']}: {summary['status']} ({summary['completed']}/{summary['total']})")
        print(f"ready: {', '.join(payload['ready']) if payload['ready'] else 'none'}")
        for story in payload["stories"]:
            accepted = story["acceptance"]
            print(f"{story['id']}\t{story['status']}\t{accepted['passed']}/{accepted['total']}")
    return 0


def command_brief(args: argparse.Namespace) -> int:
    plan, stories = load_project(args.plan, args.stories_dir)
    if not report(validate_project(plan, stories)):
        return 1
    by_id = {story.item_id: story for story in stories}
    story = by_id.get(args.story)
    if story is None:
        raise PlanError(f"未知 Story: {args.story}")
    cases = [case for case in plan.data["golden_acceptance"] if case["id"] in story.covers]
    dependencies = [
        {
            "id": dependency,
            "title": by_id[dependency].title,
            "handoff": by_id[dependency].data["handoff"],
        }
        for dependency in story.blocked_by
    ]
    payload = {
        "plan": {
            "id": plan.item_id,
            "title": plan.title,
            "goal_version": plan.data["goal_version"],
            "problem_statement": plan.data["spec"]["problem_statement"],
            "solution": plan.data["spec"]["solution"],
            "boundaries": plan.data["spec"]["boundaries"],
            "decisions": plan.data["spec"]["decisions"],
            "testing": plan.data["spec"]["testing"],
            "out_of_scope": plan.data["spec"]["out_of_scope"],
        },
        "golden_acceptance": cases,
        "story": story.data,
        "dependency_handoffs": dependencies,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def command_completion_check(args: argparse.Namespace) -> int:
    plan, stories = load_project(args.plan, args.stories_dir)
    errors = validate_project(plan, stories)
    if not errors:
        errors.extend(projection_errors(plan, stories))
    if not report(errors):
        return 1
    unfinished = [story.item_id for story in stories if story.status != "done"]
    if unfinished:
        print(f"ERROR: 仍有未完成 Story: {', '.join(unfinished)}", file=sys.stderr)
        return 1
    cases = len(plan.data["golden_acceptance"])
    print(f"OK: {plan.item_id}; stories={len(stories)}/{len(stories)}; golden_cases={cases}/{cases}")
    return 0


def _read_payload(path: Path | None) -> dict[str, Any]:
    if path is not None:
        return _read_json(path)
    raw = sys.stdin.read()
    if not raw.strip():
        raise PlanError("write 需要 --from 或 stdin JSON")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise PlanError(f"stdin JSON 无效: {error}") from error
    if not isinstance(value, dict):
        raise PlanError("stdin 顶层必须是 JSON 对象")
    return value


def command_write(args: argparse.Namespace) -> int:
    data = _read_payload(args.from_path)
    kind = data.get("kind")
    if kind == PLAN_KIND:
        errors = validate_plan_data(args.file, data)
    elif kind == STORY_KIND:
        errors = validate_story_data(args.file, data)
    else:
        raise PlanError(f"未知 kind: {kind!r}")
    if not report(errors):
        return 1
    _atomic_write(args.file, dump_json(data))
    print(f"OK: wrote {args.file}; run render/check after project updates")
    return 0


def command_transition(args: argparse.Namespace) -> int:
    current = Story(args.story, _read_json(args.story))
    if not report(validate_story_data(current.path, current.data)):
        return 1
    if args.expect and current.status != args.expect:
        raise PlanError(f"{current.path}: 期望状态 {args.expect}，实际为 {current.status}")
    allowed = {
        "todo": {"todo", "in_progress", "blocked"},
        "in_progress": {"in_progress", "blocked", "done"},
        "blocked": {"blocked", "todo", "in_progress"},
        "done": {"done"},
    }
    target = args.status
    if target not in allowed[current.status] and not (
        current.status == "done" and args.reopen and target == "in_progress"
    ):
        raise PlanError(f"{current.path}: 不允许状态迁移 {current.status} -> {target}")
    updated_data = deepcopy(current.data)
    updated_data["status"] = target
    updated_data["updated"] = args.at or date.today().isoformat()
    if target == "todo":
        updated_data["owner"] = None
    elif args.owner:
        updated_data["owner"] = args.owner
    if target == "blocked":
        blocker = args.blocker or updated_data.get("blocker")
        if not isinstance(blocker, str) or not blocker.strip():
            raise PlanError("迁移到 blocked 必须传 --blocker")
        updated_data["blocker"] = blocker
    else:
        updated_data["blocker"] = None
    updated = Story(current.path, updated_data)
    plan_path = args.story.parent.parent / "plan.json"
    stories_dir = args.story.parent
    plan, stories = load_project(plan_path, stories_dir)
    replaced = [updated if story.path.resolve() == current.path.resolve() else story for story in stories]
    if not report(validate_project(plan, replaced)):
        return 1
    _atomic_write(current.path, dump_json(updated_data))
    render_project(plan, replaced)
    print(f"OK: {current.item_id} {current.status} -> {target}; projections refreshed")
    return 0


def _legacy_markdown(path: Path) -> tuple[dict[str, Any], str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise PlanError(f"无法读取 {path}: {error}") from error
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise PlanError(f"{path}: v1 Markdown 缺少 frontmatter")
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as error:
        raise PlanError(f"{path}: v1 frontmatter 未结束") from error
    metadata: dict[str, Any] = {}
    for line in lines[1:end]:
        if not line.strip() or ":" not in line:
            continue
        key, raw = line.split(":", 1)
        value = raw.strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            metadata[key.strip()] = [] if not inner else [item.strip().strip("'\"") for item in inner.split(",")]
        elif re.fullmatch(r"\d+", value):
            metadata[key.strip()] = int(value)
        else:
            metadata[key.strip()] = value.strip("'\"")
    return metadata, "\n".join(lines[end + 1 :]).strip()


def _legacy_section(body: str, section_id: str) -> str:
    matches = list(LEGACY_SECTION_RE.finditer(body))
    for index, match in enumerate(matches):
        if match.group(1) == section_id:
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
            return body[match.end() : end].strip()
    return ""


def _legacy_agent_docs(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}
    golden: list[dict[str, Any]] = []
    agent_dir = root / "agent"
    if agent_dir.is_dir():
        for path in agent_dir.glob("*.json"):
            data = _read_json(path)
            if data.get("kind") == "agent-card":
                cards[str(data.get("story", ""))] = data
            elif data.get("kind") == "golden-acceptance":
                golden.append(data)
    if len(golden) != 1:
        raise PlanError("v1 计划必须恰好有一份 kind=golden-acceptance 的 agent/*.json")
    return cards, golden[0]


def _legacy_bullets(text: str) -> list[str]:
    return [value.strip() for value in re.findall(r"^\s*[-*]\s+(.+)$", text, re.MULTILINE) if value.strip()]


def _legacy_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def command_migrate_v1(args: argparse.Namespace) -> int:
    epic_meta, epic_body = _legacy_markdown(args.epic)
    root = args.epic.parent.parent if args.epic.parent.name == "epics" else args.epic.parent
    if args.stories_dir.resolve().parent != root.resolve():
        raise PlanError("v1 Epic 与 stories/ 必须属于同一计划根目录")
    if args.output_dir.resolve() == root.resolve():
        raise PlanError("migrate-v1 必须写入新目录，不能原地覆盖")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise PlanError(f"输出目录必须为空: {args.output_dir}")
    cards, golden = _legacy_agent_docs(root)
    legacy: list[tuple[Path, dict[str, Any], str]] = []
    for path in sorted(args.stories_dir.glob("Story-*.md")):
        metadata, body = _legacy_markdown(path)
        legacy.append((path, metadata, body))
    if not legacy:
        raise PlanError("v1 stories/ 中没有 Story")
    missing = [str(meta.get("id")) for _, meta, _ in legacy if str(meta.get("id")) not in cards]
    if missing:
        raise PlanError(f"v1 Story 缺少执行卡: {', '.join(missing)}")

    plan_id = str(epic_meta.get("id", ""))
    title = str(epic_meta.get("title", plan_id))
    boundaries = _legacy_bullets(_legacy_section(epic_body, "project-boundaries"))
    if not boundaries:
        boundaries = ["沿用 v1 Epic 已确认边界；开始执行前复核迁移结果。"]
    user_stories = []
    decisions = []
    out_of_scope: list[str] = []
    for index, (_, metadata, body) in enumerate(legacy, 1):
        outcome = _legacy_section(body, "vision") or str(metadata.get("title", ""))
        user_stories.append(
            {
                "id": f"US-{index:02d}",
                "actor": "相关使用者",
                "want": str(metadata.get("title", outcome)),
                "benefit": "获得这一阶段承诺的可观察结果",
            }
        )
        decision = _legacy_section(body, "key-decisions")
        if decision:
            decisions.append(
                {
                    "id": f"D-{len(decisions) + 1:02d}",
                    "decision": f"沿用“{metadata.get('title', '原计划')}”中的已确认取舍",
                    "rationale": "该取舍从 v1 计划原文迁移。",
                    "impact": " ".join(re.sub(r"<!--.*?-->", "", decision, flags=re.DOTALL).split()),
                    "owner": "user",
                }
            )
        scope = _legacy_section(body, "scope")
        out_of_scope.extend(item for item in re.split(r"[。；]\s*", scope) if "不在本 Story" in item)
    if not out_of_scope:
        out_of_scope = ["迁移后复核 v1 各 Story 中分散记录的范围外事项。"]

    migrated_cases: list[dict[str, Any]] = []
    raw_cases = golden.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise PlanError("v1 黄金验收没有案例")
    for case in raw_cases:
        if not isinstance(case, dict):
            raise PlanError("v1 黄金案例必须是对象")
        migrated_cases.append(
            {
                "id": case.get("id"),
                "title": case.get("title"),
                "fixture": _legacy_list(case.get("fixture")),
                "actions": _legacy_list(case.get("interaction")),
                "oracle": _legacy_list(case.get("oracle")),
                "evidence": _legacy_list(case.get("evidence")),
            }
        )
    final_story = str(sorted(legacy, key=lambda item: story_order(str(item[1].get("id"))))[-1][1]["id"])
    plan_data = {
        "kind": PLAN_KIND,
        "schema_version": SCHEMA_VERSION,
        "id": plan_id,
        "title": title,
        "goal_version": int(epic_meta.get("goal_version", 1)),
        "updated": date.today().isoformat(),
        "language": epic_meta.get("language", "zh-Hans"),
        "spec": {
            "problem_statement": "从 v1 迁移：原计划未单独保存问题陈述；执行前根据原始需求复核。",
            "solution": _legacy_section(epic_body, "vision") or title,
            "user_stories": user_stories,
            "boundaries": boundaries,
            "decisions": decisions,
            "testing": {
                "seams": ["迁移后为每张 Story 复核最高且稳定的公共测试 seam。"],
                "strategy": "保留 v1 行为验收，并在执行前确认测试不依赖实现细节。",
            },
            "out_of_scope": out_of_scope,
        },
        "golden_acceptance": migrated_cases,
        "final_story": final_story,
    }
    plan_path = args.output_dir / "agent" / "plan.json"
    migrated_stories: list[Story] = []
    all_nonfinal = [str(meta["id"]) for _, meta, _ in legacy if str(meta["id"]) != final_story]
    for _, metadata, body in legacy:
        story_id = str(metadata["id"])
        card = cards[story_id]
        status = str(card.get("status", "todo"))
        criteria = _legacy_bullets(_legacy_section(body, "acceptance-criteria"))
        if not criteria:
            criteria = ["复核并满足 v1 Story 的原验收结果。"]
        owner: str | None = str(card.get("owner", "")).strip() or None
        if status == "todo" or owner == "待领取":
            owner = None
        blocker: str | None = str(card.get("blocker", "")).strip() or None
        if blocker == "无" or status != "blocked":
            blocker = None
        verification = _legacy_list(card.get("verification"))
        handoff: dict[str, Any] | None = None
        if status != "todo":
            handoff = {
                "summary": str(card.get("handoff", "从 v1 迁移的进行中工作。")),
                "verification": verification,
                "remaining": [] if status == "done" else ["继续 v1 Story 的剩余工作。"],
                "risks": [],
                "next": "按迁移后的 frontier 继续。",
            }
            if status == "done" and not verification:
                handoff["verification"] = ["迁移后复核 v1 完成证据。"]
        blocked_by = _legacy_list(metadata.get("depends_on"))
        if story_id == final_story:
            blocked_by = all_nonfinal
        technical = str(card.get("technical_plan", "")).strip()
        inputs = str(card.get("authoritative_inputs", "")).strip()
        scope = _legacy_section(body, "scope")
        story_data = {
            "kind": STORY_KIND,
            "schema_version": SCHEMA_VERSION,
            "id": story_id,
            "plan": plan_id,
            "title": metadata.get("title", story_id),
            "intent_version": int(metadata.get("intent_version", 1)),
            "status": status,
            "blocked_by": blocked_by,
            "covers": _legacy_list(card.get("acceptance_cases")),
            "outcome": _legacy_section(body, "vision") or str(card.get("goal", "")),
            "acceptance": [
                {"id": f"AC-{index:02d}", "criterion": criterion, "passed": status == "done"}
                for index, criterion in enumerate(criteria, 1)
            ],
            "context": {
                "test_seams": ["迁移待复核：选择本 Story 的最高公共 seam。"],
                "code_anchors": [technical or "迁移待复核：补充当前代码入口。"],
                "authoritative_inputs": [inputs] if inputs else [],
                "write_scope": [scope] if scope else [],
                "stop_conditions": _legacy_list(card.get("stop_conditions")),
            },
            "owner": owner,
            "blocker": blocker,
            "updated": date.today().isoformat(),
            "handoff": handoff,
        }
        if story_id == final_story:
            story_data["covers"] = [case["id"] for case in migrated_cases]
        migrated_stories.append(
            Story(args.output_dir / "agent" / "stories" / f"{story_id}.json", story_data)
        )
    plan = Plan(plan_path, plan_data)
    errors = validate_project(plan, migrated_stories)
    if not report(errors):
        return 1
    _atomic_write(plan.path, dump_json(plan.data))
    for story in migrated_stories:
        _atomic_write(story.path, dump_json(story.data))
    render_project(plan, migrated_stories)
    print(
        f"OK: migrated to {args.output_dir}; stories={len(migrated_stories)}; v1 unchanged; "
        "review problem_statement, public seams, code anchors, and out_of_scope before execution"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="维护 Agent JSON 单一事实源，并生成人读 SPEC/STATUS。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "输出与退出码:\n"
            "  check/status/brief/completion-check 只读；render 生成 SPEC.md 和 STATUS.md；\n"
            "  write/transition 原子更新 JSON；migrate-v1 只写空的新目录。\n"
            "  0=成功，1=计划契约失败，2=I/O 失败。\n\n"
            "示例:\n"
            "  epic_story.py render --plan docs/plan/agent/plan.json "
            "--stories-dir docs/plan/agent/stories\n"
            "  epic_story.py brief --plan docs/plan/agent/plan.json "
            "--stories-dir docs/plan/agent/stories --story STORY-01\n"
            "  epic_story.py transition --story docs/plan/agent/stories/STORY-01.json "
            "--expect todo --status in_progress --owner worker-1\n"
            "  epic_story.py migrate-v1 --epic old/epics/EPIC-X.md "
            "--stories-dir old/stories --output-dir new-plan"
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    def add_project(command: argparse.ArgumentParser) -> None:
        command.add_argument("--plan", type=Path, required=True, help="<topic>/agent/plan.json")
        command.add_argument("--stories-dir", type=Path, required=True, help="同一 agent/ 下的 stories/")

    check = commands.add_parser("check", help="校验 JSON、依赖和人读投影新鲜度")
    add_project(check)
    check.set_defaults(handler=command_check)

    render = commands.add_parser("render", help="从 JSON 整份生成 SPEC.md 与 STATUS.md")
    add_project(render)
    render.set_defaults(handler=command_render)

    status = commands.add_parser("status", help="按需输出当前状态与 frontier")
    add_project(status)
    status.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    status.set_defaults(handler=command_status)

    brief = commands.add_parser("brief", help="提取一张 Story 的 fresh-context 执行包")
    add_project(brief)
    brief.add_argument("--story", required=True, help="Story ID")
    brief.set_defaults(handler=command_brief)

    completion = commands.add_parser("completion-check", help="确认全部 Story、黄金覆盖和人读投影收口")
    add_project(completion)
    completion.set_defaults(handler=command_completion_check)

    write = commands.add_parser("write", help="校验并原子写入 plan 或 Story JSON")
    write.add_argument("--file", type=Path, required=True)
    write.add_argument("--from", dest="from_path", type=Path, help="输入 JSON；省略则读 stdin")
    write.set_defaults(handler=command_write)

    transition = commands.add_parser("transition", help="原子更新 Story 状态并刷新人读投影")
    transition.add_argument("--story", type=Path, required=True)
    transition.add_argument("--expect", choices=STATUSES, help="并发保护：要求当前状态")
    transition.add_argument("--status", choices=STATUSES, required=True)
    transition.add_argument("--owner", help="非 todo 状态的 owner")
    transition.add_argument("--blocker", help="blocked 状态的具体原因")
    transition.add_argument("--reopen", action="store_true", help="允许 done -> in_progress")
    transition.add_argument("--at", help="更新日期 YYYY-MM-DD；默认今天")
    transition.set_defaults(handler=command_transition)

    migrate = commands.add_parser("migrate-v1", help="非破坏性迁移 v1 到空的新目录")
    migrate.add_argument("--epic", type=Path, required=True, help="v1 Epic Markdown")
    migrate.add_argument("--stories-dir", type=Path, required=True, help="v1 stories/ 目录")
    migrate.add_argument("--output-dir", type=Path, required=True, help="空的新目录")
    migrate.set_defaults(handler=command_migrate_v1)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if getattr(args, "at", None):
            date.fromisoformat(args.at)
        return int(args.handler(args))
    except PlanError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"ERROR: I/O 失败: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
