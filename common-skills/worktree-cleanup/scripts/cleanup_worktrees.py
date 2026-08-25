#!/usr/bin/env python3
"""Audit and retire stale Git worktrees associated with closed GitHub PRs.

Inputs: a Git repository, optional scope overrides, and an optional backup root.
Outputs: a text or JSON report plus per-target metadata and a batch manifest in
apply mode. Exit 0 means the audit/apply completed, 1 means discovery or removal
failed, and 2 is reserved for argparse usage errors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PR_NUMBER_RE = re.compile(r"\bpr-(\d+)\b")


@dataclass(frozen=True)
class PullRequestInfo:
    number: int
    state: str
    title: str
    url: str
    head_ref_name: str | None
    merged_at: str | None
    closed_at: str | None

    @property
    def expiration_reason(self) -> str | None:
        state = self.state.upper()
        if self.merged_at or state == "MERGED":
            return "merged"
        if self.closed_at or state == "CLOSED":
            return "closed"
        return None


@dataclass(frozen=True)
class WorktreeInfo:
    path: Path
    head: str
    branch_ref: str | None
    detached: bool

    @property
    def branch_name(self) -> str | None:
        if self.branch_ref is None:
            return None
        prefix = "refs/heads/"
        if self.branch_ref.startswith(prefix):
            return self.branch_ref[len(prefix) :]
        return self.branch_ref


class CommandError(RuntimeError):
    pass


def run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise CommandError(f"{' '.join(args)} failed: {detail or result.returncode}")
    return result


def run_git(*args: str, cwd: Path | None = None) -> str:
    return run_command(["git", *args], cwd=cwd).stdout.strip()


def parse_worktree_list(output: str) -> list[WorktreeInfo]:
    entries: list[WorktreeInfo] = []
    for block in output.strip().split("\n\n"):
        if not block.strip():
            continue
        path: Path | None = None
        head = ""
        branch_ref: str | None = None
        detached = False
        for line in block.splitlines():
            if line.startswith("worktree "):
                path = Path(line.removeprefix("worktree ").strip())
            elif line.startswith("HEAD "):
                head = line.removeprefix("HEAD ").strip()
            elif line.startswith("branch "):
                branch_ref = line.removeprefix("branch ").strip()
            elif line == "detached":
                detached = True
        if path is None:
            raise CommandError(f"Unable to parse worktree block:\n{block}")
        entries.append(
            WorktreeInfo(
                path=path.resolve(),
                head=head,
                branch_ref=branch_ref,
                detached=detached,
            )
        )
    return entries


def infer_pr_number(*values: str | None) -> int | None:
    for value in values:
        if value and (match := PR_NUMBER_RE.search(value)):
            return int(match.group(1))
    return None


def parse_pr_info(raw: dict[str, Any]) -> PullRequestInfo:
    return PullRequestInfo(
        number=int(raw["number"]),
        state=str(raw["state"]),
        title=str(raw["title"]),
        url=str(raw["url"]),
        head_ref_name=(
            str(raw["headRefName"]) if raw.get("headRefName") is not None else None
        ),
        merged_at=str(raw["mergedAt"]) if raw.get("mergedAt") is not None else None,
        closed_at=str(raw["closedAt"]) if raw.get("closedAt") is not None else None,
    )


def parse_gh_json(result: subprocess.CompletedProcess[str]) -> tuple[Any | None, str | None]:
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown gh error"
        return None, detail
    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON from gh: {exc}"


def query_pr_by_number(
    number: int, *, repo_root: Path
) -> tuple[PullRequestInfo | None, str | None]:
    result = run_command(
        [
            "gh",
            "pr",
            "view",
            str(number),
            "--json",
            "number,state,title,url,headRefName,mergedAt,closedAt",
        ],
        cwd=repo_root,
        check=False,
    )
    raw, error = parse_gh_json(result)
    if error is not None:
        return None, error
    try:
        return parse_pr_info(raw), None
    except (KeyError, TypeError, ValueError) as exc:
        return None, f"invalid PR data from gh: {exc}"


def query_pr_by_branch(
    branch_name: str, *, repo_root: Path
) -> tuple[PullRequestInfo | None, str | None]:
    result = run_command(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "all",
            "--head",
            branch_name,
            "--json",
            "number,state,title,url,headRefName,mergedAt,closedAt",
            "--limit",
            "10",
        ],
        cwd=repo_root,
        check=False,
    )
    rows, error = parse_gh_json(result)
    if error is not None:
        return None, error
    if not isinstance(rows, list):
        return None, "invalid PR list data from gh"
    if not rows:
        return None, None

    exact = [row for row in rows if row.get("headRefName") == branch_name]
    matches = exact or rows
    if len(matches) > 1:
        numbers = ", ".join(str(row.get("number")) for row in matches)
        return None, f"ambiguous branch match for {branch_name}: {numbers}"
    try:
        return parse_pr_info(matches[0]), None
    except (KeyError, TypeError, ValueError) as exc:
        return None, f"invalid PR data from gh: {exc}"


def path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def read_worktree_dirty(path: Path) -> tuple[bool | None, str | None]:
    result = run_command(
        ["git", "-C", str(path), "status", "--porcelain", "--untracked-files=all"],
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "git status failed"
        return None, detail
    return bool(result.stdout.strip()), None


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def ensure_unique_backup_dir(batch_root: Path, worktree_name: str) -> Path:
    candidate = batch_root / worktree_name
    if not candidate.exists():
        return candidate
    for index in range(2, 1000):
        suffixed = batch_root / f"{worktree_name}-{index}"
        if not suffixed.exists():
            return suffixed
    raise CommandError(f"Unable to allocate backup directory for {worktree_name}")


def default_backup_root(primary_repo_root: Path, common_git_dir: Path) -> Path:
    state_home = Path(
        os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
    ).expanduser()
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", primary_repo_root.name).strip("-")
    repo_id = hashlib.sha256(str(common_git_dir.resolve()).encode()).hexdigest()[:10]
    return state_home / "worktree-cleanup" / f"{slug or 'repository'}-{repo_id}"


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit and retire stale Git worktrees associated with closed PRs.",
        epilog=(
            "Examples:\n"
            "  cleanup_worktrees.py --repo . --dry-run\n"
            "  cleanup_worktrees.py --repo /src/project --apply --json\n\n"
            "Outputs:\n"
            "  Dry-run prints a report only. Apply mode also writes per-target metadata "
            "and a batch manifest under the backup root."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Repository checkout to inspect (default: current directory)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Back up .local and remove eligible expired worktrees",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Report worktree status without deleting anything (default)",
    )
    parser.add_argument(
        "--include-external",
        action="store_true",
        help="Include expired worktrees outside the primary checkout's .worktrees/",
    )
    parser.add_argument(
        "--force-remove-dirty",
        action="store_true",
        help="Remove eligible dirty worktrees with git worktree remove --force",
    )
    parser.add_argument(
        "--backup-root",
        help=(
            "Backup root; relative paths resolve from --repo "
            "(default: XDG state directory namespaced by repository)"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of a text summary",
    )
    args = parser.parse_args()
    if not args.apply:
        args.dry_run = True
    return args


def discover(args: argparse.Namespace) -> dict[str, Any]:
    selected_repo = Path(args.repo).expanduser().resolve()
    selected_root = Path(
        run_git("-C", str(selected_repo), "rev-parse", "--show-toplevel")
    ).resolve()
    common_git_dir = Path(
        run_git(
            "-C",
            str(selected_repo),
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        )
    ).resolve()
    worktrees = parse_worktree_list(
        run_git("-C", str(selected_root), "worktree", "list", "--porcelain")
    )
    if not worktrees:
        raise CommandError("No Git worktrees found")

    primary_repo_root = worktrees[0].path
    managed_worktrees_root = primary_repo_root / ".worktrees"
    if args.backup_root:
        backup_root = Path(args.backup_root).expanduser()
        if not backup_root.is_absolute():
            backup_root = selected_root / backup_root
        backup_root = backup_root.resolve()
    else:
        backup_root = default_backup_root(primary_repo_root, common_git_dir)
    entries: list[dict[str, Any]] = []

    for worktree in worktrees:
        if worktree.path == primary_repo_root:
            continue

        worktree_name = worktree.path.name
        branch_name = worktree.branch_name
        managed = path_is_relative_to(worktree.path, managed_worktrees_root)
        local_dir = worktree.path / ".local"
        pr_number = infer_pr_number(worktree_name, branch_name)
        if pr_number is not None:
            pr_info, pr_lookup_error = query_pr_by_number(
                pr_number, repo_root=selected_root
            )
        elif branch_name:
            pr_info, pr_lookup_error = query_pr_by_branch(
                branch_name, repo_root=selected_root
            )
        else:
            pr_info, pr_lookup_error = None, None

        expiration_reason = pr_info.expiration_reason if pr_info else None
        dirty, dirty_error = read_worktree_dirty(worktree.path)
        skip_reason: str | None = None
        if worktree.path == selected_root:
            skip_reason = "selected --repo checkout cannot be removed"
        elif pr_lookup_error is not None:
            skip_reason = f"PR lookup failed: {pr_lookup_error}"
        elif pr_info is None:
            skip_reason = "no associated PR found"
        elif expiration_reason is None:
            skip_reason = "PR is still open"
        elif not managed and not args.include_external:
            skip_reason = "external worktree; rerun with --include-external"
        elif dirty_error is not None:
            skip_reason = f"git status failed: {dirty_error}"
        elif dirty and not args.force_remove_dirty:
            skip_reason = (
                "worktree has uncommitted changes; explicit authorization and "
                "--force-remove-dirty are required"
            )

        entry: dict[str, Any] = {
            "name": worktree_name,
            "path": str(worktree.path),
            "path_relative": to_repo_relative(worktree.path, primary_repo_root),
            "managed": managed,
            "branch": branch_name,
            "detached": worktree.detached,
            "head": worktree.head,
            "has_local_dir": local_dir.exists(),
            "pr": None,
            "expired": expiration_reason is not None,
            "expiration_reason": expiration_reason,
            "dirty": dirty,
            "skip_reason": skip_reason,
            "action": (
                "skip"
                if skip_reason is not None
                else ("remove" if args.apply else "would-remove")
            ),
            "backup_path": None,
            "error": None,
        }
        if pr_info is not None:
            entry["pr"] = {
                "number": pr_info.number,
                "state": pr_info.state,
                "title": pr_info.title,
                "url": pr_info.url,
                "head_ref_name": pr_info.head_ref_name,
                "merged_at": pr_info.merged_at,
                "closed_at": pr_info.closed_at,
            }
        entries.append(entry)

    return {
        "mode": "apply" if args.apply else "dry-run",
        "common_repo_root": str(primary_repo_root),
        "selected_repo_root": str(selected_root),
        "managed_worktrees_root": str(managed_worktrees_root),
        "backup_root": str(backup_root),
        "scanned": len(entries),
        "eligible": sum(entry["skip_reason"] is None for entry in entries),
        "removed": 0,
        "failed": 0,
        "entries": entries,
    }


def apply_candidates(summary: dict[str, Any]) -> None:
    candidates = [entry for entry in summary["entries"] if entry["skip_reason"] is None]
    if not candidates:
        return

    backup_root = Path(summary["backup_root"]).resolve()
    for candidate in candidates:
        worktree_path = Path(candidate["path"]).resolve()
        if path_is_relative_to(backup_root, worktree_path):
            raise CommandError(
                f"Backup root {backup_root} is inside cleanup target {worktree_path}"
            )

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    batch_root = backup_root / timestamp
    batch_root.mkdir(parents=True, exist_ok=False)
    summary["backup_root"] = str(batch_root)
    manifest_path = batch_root / "manifest.json"

    def update_manifest() -> None:
        write_json(
            manifest_path,
            {
                "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "backup_root": str(batch_root),
                "items": summary["entries"],
            },
        )

    update_manifest()
    for candidate in candidates:
        worktree_path = Path(candidate["path"])
        local_dir = worktree_path / ".local"
        metadata_path: Path | None = None

        def update_metadata() -> None:
            if metadata_path is None:
                return
            write_json(
                metadata_path,
                {
                    "backup_created_at": datetime.now()
                    .astimezone()
                    .isoformat(timespec="seconds"),
                    "source_local_dir": str(local_dir),
                    "worktree": candidate,
                },
            )

        try:
            backup_dir = ensure_unique_backup_dir(batch_root, candidate["name"])
            backup_dir.mkdir(parents=True, exist_ok=False)
            candidate["backup_path"] = str(backup_dir)
            candidate["action"] = "remove-pending"
            metadata_path = backup_dir / "metadata.json"
            if local_dir.exists():
                shutil.copytree(local_dir, backup_dir / ".local", symlinks=True)
        except OSError as exc:
            candidate["action"] = "failed"
            candidate["error"] = f"backup failed: {exc}"
            summary["failed"] += 1
            update_metadata()
            update_manifest()
            break

        update_metadata()
        update_manifest()

        remove_args = ["git", "worktree", "remove"]
        if candidate["dirty"]:
            remove_args.append("--force")
        remove_args.append(str(worktree_path))
        result = run_command(
            remove_args,
            cwd=Path(summary["common_repo_root"]),
            check=False,
        )
        if result.returncode != 0:
            candidate["action"] = "failed"
            candidate["error"] = (
                result.stderr.strip()
                or result.stdout.strip()
                or f"git exited {result.returncode}"
            )
            summary["failed"] += 1
        else:
            candidate["action"] = "removed"
            summary["removed"] += 1

        update_metadata()
        update_manifest()
        if candidate["action"] == "failed":
            break


def print_text(summary: dict[str, Any]) -> None:
    print(f"mode: {summary['mode']}")
    print(f"repo: {summary['common_repo_root']}")
    print(f"selected_repo: {summary['selected_repo_root']}")
    print(f"managed_worktrees_root: {summary['managed_worktrees_root']}")
    print(f"backup_root: {summary['backup_root']}")
    print(f"scanned: {summary['scanned']}")
    print(f"eligible: {summary['eligible']}")
    print(f"removed: {summary['removed']}")
    print(f"failed: {summary['failed']}")
    print()

    for entry in summary["entries"]:
        pr = entry["pr"]
        pr_summary = f"PR #{pr['number']} {pr['state']}" if pr else "no-pr"
        print(f"- {entry['path_relative']}")
        print(f"  pr: {pr_summary}")
        print(f"  expired: {entry['expiration_reason'] or 'no'}")
        dirty = entry["dirty"] if entry["dirty"] is not None else "unknown"
        print(f"  has_uncommitted_changes: {dirty}")
        print(f"  has_local_dir: {entry['has_local_dir']}")
        print(f"  action: {entry['action']}")
        if entry["backup_path"]:
            print(f"  backup_path: {entry['backup_path']}")
        if entry["skip_reason"]:
            print(f"  note: {entry['skip_reason']}")
        if entry["error"]:
            print(f"  error: {entry['error']}")
        if pr:
            print(f"  url: {pr['url']}")
        print()


def main() -> int:
    args = parse_args()
    try:
        summary = discover(args)
        if args.apply:
            apply_candidates(summary)
    except (CommandError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print_text(summary)
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
