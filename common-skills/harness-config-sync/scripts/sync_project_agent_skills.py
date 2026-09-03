#!/usr/bin/env python3
"""Synchronize cataloged project Skills into one harness directory.

Definition:
    Validate ``.agents/skill-catalog.json`` and create relative links from a
    harness-specific project directory to canonical ``.agents/skills`` paths.
    A canonical Skill may itself be a symlink into the same repository, such as
    a tool submodule, but it may not resolve outside the repository.

Parameters:
    ``--repo`` selects the repository, ``--target`` selects one harness Skills
    directory, and ``--apply`` enables writes. Without ``--apply`` the script
    prints the same plan without changing files.

Outputs and exit codes:
    stdout contains ``CREATE``/``KEEP`` entries and a summary. Conflicts and
    validation errors go to stderr. Exit 0 means the plan is valid; exit 2
    means no safe synchronization was possible. Apply mode preflights every
    entry and removes links created by the current run if a later write fails.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Sequence

SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ValidationError(Exception):
    """Raised when the repository cannot safely be synchronized."""


@dataclass(frozen=True)
class LinkPlan:
    name: str
    source: Path
    resolved_source: Path
    target: Path

    @property
    def relative_source(self) -> str:
        return os.path.relpath(self.source, start=self.target.parent)


@dataclass(frozen=True)
class CatalogEntry:
    name: str
    path: PurePath


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def resolve_repository(raw_repository: str) -> Path:
    repository = Path(raw_repository).expanduser().resolve()
    if not repository.is_dir():
        raise ValidationError(f"Repository is not a directory: {repository}")
    return repository


def validate_relative_path(raw_path: str, label: str) -> PurePath:
    pure_path = PurePath(raw_path)
    if pure_path.is_absolute() or ".." in pure_path.parts or not pure_path.parts:
        raise ValidationError(f"{label} has an unsafe path: {raw_path!r}")
    return pure_path


def load_catalog(repository: Path) -> list[CatalogEntry]:
    catalog_path = repository / ".agents" / "skill-catalog.json"
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValidationError(f"Missing catalog: {catalog_path}") from error
    except json.JSONDecodeError as error:
        raise ValidationError(f"Invalid JSON in {catalog_path}: {error}") from error

    skills = catalog.get("skills") if isinstance(catalog, dict) else None
    if not isinstance(skills, list) or not skills:
        raise ValidationError("Catalog must contain a non-empty 'skills' list")

    entries: list[CatalogEntry] = []
    seen_names: set[str] = set()
    for index, skill in enumerate(skills, start=1):
        if not isinstance(skill, dict):
            raise ValidationError(f"Catalog skill #{index} must be an object")
        name = skill.get("name")
        source_path = skill.get("path")
        if not isinstance(name, str) or not SKILL_NAME_RE.fullmatch(name) or name in {".", ".."}:
            raise ValidationError(f"Catalog skill #{index} has an unsafe name: {name!r}")
        if name in seen_names:
            raise ValidationError(f"Catalog contains duplicate skill name: {name}")
        if not isinstance(source_path, str):
            raise ValidationError(f"Catalog skill {name} has no string path")
        seen_names.add(name)
        entries.append(
            CatalogEntry(
                name=name,
                path=validate_relative_path(source_path, f"Catalog skill {name}"),
            )
        )
    return entries


def build_plan(repository: Path, target_subpath: str) -> list[LinkPlan]:
    source_root = repository / ".agents" / "skills"
    resolved_source_root = source_root.resolve()
    if not source_root.is_dir() or not is_within(resolved_source_root, repository):
        raise ValidationError(f"Invalid project skill source root: {source_root}")

    target_path = validate_relative_path(target_subpath, "Project skills target")
    target_root = repository.joinpath(*target_path.parts)
    if target_root == source_root:
        raise ValidationError("Project skills target must differ from .agents/skills")
    if not is_within(target_root.parent.resolve(), repository):
        raise ValidationError(f"Project skills directory escapes the repository: {target_root}")
    if (target_root.exists() or target_root.is_symlink()) and not is_within(target_root.resolve(), repository):
        raise ValidationError(f"Project skills directory escapes the repository: {target_root}")

    plan: list[LinkPlan] = []
    for entry in load_catalog(repository):
        source = repository.joinpath(*entry.path.parts)
        if not is_within(source, source_root):
            raise ValidationError(f"Catalog skill {entry.name} is outside .agents/skills: {entry.path}")
        try:
            resolved_source = source.resolve(strict=True)
        except OSError as error:
            raise ValidationError(f"Catalog skill {entry.name} has an unreadable source: {error}") from error

        inside_standard_root = is_within(resolved_source, resolved_source_root)
        repository_internal_link = source.is_symlink() and is_within(resolved_source, repository)
        if not inside_standard_root and not repository_internal_link:
            raise ValidationError(
                f"Catalog skill {entry.name} escapes the repository through .agents/skills: {entry.path}"
            )

        skill_file = source / "SKILL.md"
        try:
            skill_content = skill_file.read_text(encoding="utf-8")
        except OSError as error:
            raise ValidationError(f"Catalog skill {entry.name} has unreadable SKILL.md: {error}") from error
        if not source.is_dir() or not skill_content.strip():
            raise ValidationError(
                f"Catalog skill {entry.name} must be a directory with a nonempty SKILL.md"
            )
        plan.append(
            LinkPlan(
                name=entry.name,
                source=source,
                resolved_source=resolved_source,
                target=target_root / entry.name,
            )
        )
    return plan


def existing_link_matches(item: LinkPlan) -> bool:
    raw_target = os.readlink(item.target)
    if os.path.isabs(raw_target):
        return False
    linked_path = Path(os.path.abspath(item.target.parent / raw_target))
    if linked_path != item.source:
        return False
    try:
        return item.target.resolve(strict=True) == item.resolved_source
    except OSError:
        return False


def classify_plan(plan: Sequence[LinkPlan]) -> tuple[list[LinkPlan], list[LinkPlan], list[str]]:
    creates: list[LinkPlan] = []
    unchanged: list[LinkPlan] = []
    conflicts: list[str] = []
    for item in plan:
        if item.target.is_symlink():
            if existing_link_matches(item):
                unchanged.append(item)
            else:
                conflicts.append(f"{item.name}: existing link points to {os.readlink(item.target)!r}")
        elif item.target.exists():
            kind = "directory" if item.target.is_dir() else "file"
            conflicts.append(f"{item.name}: existing {kind} at {item.target}")
        else:
            creates.append(item)
    return creates, unchanged, conflicts


def print_plan(creates: Sequence[LinkPlan], unchanged: Sequence[LinkPlan], conflicts: Sequence[str]) -> None:
    for item in creates:
        print(f"CREATE  {item.target} -> {item.relative_source}")
    for item in unchanged:
        print(f"KEEP    {item.target} -> {item.relative_source}")
    for conflict in conflicts:
        print(f"CONFLICT {conflict}", file=sys.stderr)


def synchronize(repository: Path, apply: bool, target_subpath: str) -> int:
    plan = build_plan(repository, target_subpath)
    creates, unchanged, conflicts = classify_plan(plan)
    print_plan(creates, unchanged, conflicts)
    if conflicts:
        print("No changes made: resolve every conflict before retrying.", file=sys.stderr)
        return 2

    if not apply:
        print(f"Dry run: {len(creates)} to create, {len(unchanged)} already correct.")
        return 0

    target_root = plan[0].target.parent
    target_root.mkdir(parents=True, exist_ok=True)
    if not is_within(target_root.resolve(), repository):
        raise ValidationError(f"Project skill target escapes the repository: {target_root}")

    # Recheck the complete create set before the first write. Roll back this run
    # if a later filesystem error prevents the full set from being created.
    for item in creates:
        if item.target.exists() or item.target.is_symlink():
            raise ValidationError(f"Target changed during synchronization: {item.target}")

    created: list[Path] = []
    try:
        for item in creates:
            item.target.symlink_to(item.relative_source)
            created.append(item.target)
    except OSError as error:
        for target in reversed(created):
            target.unlink(missing_ok=True)
        raise ValidationError(f"Failed to create project skill links; rolled back this run: {error}") from error

    print(f"Applied: {len(creates)} created, {len(unchanged)} already correct.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a project Skill catalog and link its entries from one harness directory "
            "to canonical .agents/skills paths."
        ),
        epilog="""Outputs:
  CREATE/KEEP lines on stdout; conflicts and validation errors on stderr.
  Exit 0: valid dry run or successful apply. Exit 2: no safe apply was possible.

Examples:
  %(prog)s --repo /workspace/project
  %(prog)s --repo /workspace/project --target .claude/skills --apply
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--repo", default=".", help="Repository root (default: current directory)")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create every planned link after an all-entry preflight; otherwise only print the plan",
    )
    parser.add_argument(
        "--target",
        default=".kiro/skills",
        help="Harness project skills directory relative to the repository (default: .kiro/skills)",
    )
    args = parser.parse_args(argv)

    try:
        return synchronize(resolve_repository(args.repo), args.apply, args.target)
    except ValidationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
