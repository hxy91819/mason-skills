#!/usr/bin/env python3
"""Audit and retire Git worktrees whose commits are durable on GitHub.

Inputs: a Git repository, a minimum age for PR-less worktrees, a reviewed dry-run
report or selected approval tokens, and an optional backup root. Outputs: a
bounded text or JSON report plus per-target metadata and a batch manifest in
apply mode. Exit 0 means every approved candidate completed, 1 means discovery,
approval, backup, or removal had a rejected item, and 2 is an argparse usage
error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


PR_NUMBER_RE = re.compile(r"\bpr-(\d+)\b")
PR_JSON_FIELDS = (
    "number,state,title,url,headRefName,headRefOid,mergedAt,closedAt"
)
IGNORED_SAMPLE_LIMIT = 50


@dataclass(frozen=True)
class PullRequestInfo:
    number: int
    state: str
    title: str
    url: str
    head_ref_name: str | None
    head_ref_oid: str | None
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
    locked_reason: str | None
    prunable_reason: str | None

    @property
    def branch_name(self) -> str | None:
        if self.branch_ref is None:
            return None
        prefix = "refs/heads/"
        if self.branch_ref.startswith(prefix):
            return self.branch_ref[len(prefix) :]
        return self.branch_ref


@dataclass(frozen=True)
class RepositoryInfo:
    name_with_owner: str
    default_branch: str
    default_head_oid: str


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
        locked_reason: str | None = None
        prunable_reason: str | None = None
        for line in block.splitlines():
            if line.startswith("worktree "):
                path = Path(line.removeprefix("worktree ").strip())
            elif line.startswith("HEAD "):
                head = line.removeprefix("HEAD ").strip()
            elif line.startswith("branch "):
                branch_ref = line.removeprefix("branch ").strip()
            elif line == "detached":
                detached = True
            elif line == "locked" or line.startswith("locked "):
                locked_reason = line.removeprefix("locked").strip() or "locked"
            elif line == "prunable" or line.startswith("prunable "):
                prunable_reason = line.removeprefix("prunable").strip() or "prunable"
        if path is None:
            raise CommandError(f"Unable to parse worktree block:\n{block}")
        entries.append(
            WorktreeInfo(
                path=path.resolve(),
                head=head,
                branch_ref=branch_ref,
                detached=detached,
                locked_reason=locked_reason,
                prunable_reason=prunable_reason,
            )
        )
    return entries


def infer_pr_number(*values: str | None) -> int | None:
    for value in values:
        if value and (match := PR_NUMBER_RE.search(value)):
            return int(match.group(1))
    return None


def parse_json_result(
    result: subprocess.CompletedProcess[str], *, source: str
) -> tuple[Any | None, str | None]:
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        return None, detail
    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON from {source}: {exc}"


def parse_pr_info(raw: dict[str, Any]) -> PullRequestInfo:
    return PullRequestInfo(
        number=int(raw["number"]),
        state=str(raw["state"]),
        title=str(raw["title"]),
        url=str(raw["url"]),
        head_ref_name=(
            str(raw["headRefName"]) if raw.get("headRefName") is not None else None
        ),
        head_ref_oid=(
            str(raw["headRefOid"]) if raw.get("headRefOid") is not None else None
        ),
        merged_at=str(raw["mergedAt"]) if raw.get("mergedAt") is not None else None,
        closed_at=str(raw["closedAt"]) if raw.get("closedAt") is not None else None,
    )


def query_repository(repo_root: Path) -> RepositoryInfo:
    view = run_command(
        ["gh", "repo", "view", "--json", "nameWithOwner,defaultBranchRef"],
        cwd=repo_root,
        check=False,
    )
    raw, error = parse_json_result(view, source="gh repo view")
    if error is not None:
        raise CommandError(f"GitHub repository lookup failed: {error}")
    try:
        name_with_owner = str(raw["nameWithOwner"])
        default_branch = str(raw["defaultBranchRef"]["name"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CommandError(f"Invalid GitHub repository data: {exc}") from exc

    commit = run_command(
        [
            "gh",
            "api",
            f"repos/{name_with_owner}/commits/{quote(default_branch, safe='')}",
        ],
        cwd=repo_root,
        check=False,
    )
    commit_raw, commit_error = parse_json_result(commit, source="gh api")
    if commit_error is not None:
        raise CommandError(f"Default branch lookup failed: {commit_error}")
    try:
        default_head_oid = str(commit_raw["sha"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CommandError(f"Invalid default branch data: {exc}") from exc
    return RepositoryInfo(name_with_owner, default_branch, default_head_oid)


def query_pr_by_number(
    number: int, *, repo_root: Path
) -> tuple[PullRequestInfo | None, str | None]:
    result = run_command(
        ["gh", "pr", "view", str(number), "--json", PR_JSON_FIELDS],
        cwd=repo_root,
        check=False,
    )
    raw, error = parse_json_result(result, source="gh pr view")
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
            PR_JSON_FIELDS,
            "--limit",
            "20",
        ],
        cwd=repo_root,
        check=False,
    )
    rows, error = parse_json_result(result, source="gh pr list")
    if error is not None:
        return None, error
    if not isinstance(rows, list):
        return None, "invalid PR list data from gh"
    if not rows:
        return None, None

    exact = [row for row in rows if row.get("headRefName") == branch_name]
    matches = exact or rows
    open_matches = [row for row in matches if str(row.get("state", "")).upper() == "OPEN"]
    if open_matches:
        matches = open_matches
    if len(matches) > 1:
        numbers = ", ".join(str(row.get("number")) for row in matches)
        return None, f"ambiguous branch match for {branch_name}: {numbers}"
    try:
        return parse_pr_info(matches[0]), None
    except (KeyError, TypeError, ValueError) as exc:
        return None, f"invalid PR data from gh: {exc}"


def remote_contains_commit(
    *,
    repo_root: Path,
    repository: RepositoryInfo,
    local_head: str,
    remote_head: str,
) -> tuple[bool, str | None]:
    if local_head == remote_head:
        return True, None
    endpoint = (
        f"repos/{repository.name_with_owner}/compare/"
        f"{quote(local_head, safe='')}...{quote(remote_head, safe='')}"
    )
    result = run_command(["gh", "api", endpoint], cwd=repo_root, check=False)
    raw, error = parse_json_result(result, source="gh api compare")
    if error is not None:
        return False, error
    try:
        merge_base = str(raw["merge_base_commit"]["sha"])
    except (KeyError, TypeError, ValueError) as exc:
        return False, f"invalid compare data from gh: {exc}"
    return merge_base == local_head, None


def remote_branches_at_head(
    *, repo_root: Path, repository: RepositoryInfo, local_head: str
) -> tuple[list[str], str | None]:
    endpoint = (
        f"repos/{repository.name_with_owner}/commits/"
        f"{quote(local_head, safe='')}/branches-where-head"
    )
    result = run_command(["gh", "api", endpoint], cwd=repo_root, check=False)
    rows, error = parse_json_result(result, source="gh api branches-where-head")
    if error is not None:
        return [], error
    if not isinstance(rows, list):
        return [], "invalid branches-where-head data from gh"
    try:
        return sorted(str(row["name"]) for row in rows), None
    except (KeyError, TypeError, ValueError) as exc:
        return [], f"invalid branches-where-head data from gh: {exc}"


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


def read_local_tree_fingerprint(local_dir: Path) -> tuple[dict[str, Any] | None, str | None]:
    pending = [local_dir]
    entries: list[dict[str, Any]] = []
    while pending:
        current = pending.pop()
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            if current == local_dir:
                break
            return None, f"path disappeared while inventorying .local: {current}"
        except OSError as exc:
            return None, f"cannot inventory .local path {current}: {exc}"

        relative = "." if current == local_dir else str(current.relative_to(local_dir))
        item = {
            "path": relative,
            "mode": metadata.st_mode,
            "size": metadata.st_size,
            "mtime_ns": metadata.st_mtime_ns,
            "symlink_target": None,
        }
        if stat.S_ISLNK(metadata.st_mode):
            try:
                item["symlink_target"] = os.readlink(current)
            except OSError as exc:
                return None, f"cannot read .local symlink {current}: {exc}"
        elif stat.S_ISDIR(metadata.st_mode):
            try:
                children = sorted(
                    (Path(entry.path) for entry in os.scandir(current)),
                    key=lambda child: child.name,
                    reverse=True,
                )
            except OSError as exc:
                return None, f"cannot inventory .local directory {current}: {exc}"
            pending.extend(children)
        entries.append(item)

    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return {
        "entry_count": len(entries),
        "metadata_digest": hashlib.sha256(encoded).hexdigest(),
    }, None


def read_ignored_roots(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    result = run_command(
        [
            "git",
            "-C",
            str(path),
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "--directory",
            "-z",
        ],
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "git ls-files failed"
        return None, detail
    local_tree, local_tree_error = read_local_tree_fingerprint(path / ".local")
    if local_tree_error is not None:
        return None, local_tree_error
    roots = sorted(value for value in result.stdout.split("\0") if value)
    encoded = "\0".join(roots).encode("utf-8", errors="surrogateescape")
    discarded = [
        value
        for value in roots
        if value != ".local" and not value.startswith(".local/")
    ]
    return (
        {
            "count": len(roots),
            "count_kind": "ignored path roots, not files or bytes",
            "digest": hashlib.sha256(encoded).hexdigest(),
            "sample": roots[:IGNORED_SAMPLE_LIMIT],
            "sample_truncated": len(roots) > IGNORED_SAMPLE_LIMIT,
            "discarded_count": len(discarded),
            "discarded_sample": discarded[:IGNORED_SAMPLE_LIMIT],
            "discarded_sample_truncated": len(discarded) > IGNORED_SAMPLE_LIMIT,
            "local_tree": local_tree,
        },
        None,
    )


def worktree_age_hours(path: Path) -> float | None:
    marker = path / ".git"
    try:
        modified = marker.stat().st_mtime
    except OSError:
        return None
    now = datetime.now(timezone.utc).timestamp()
    return max(0.0, (now - modified) / 3600)


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def local_fingerprint(
    worktree: WorktreeInfo, dirty: bool | None, ignored: dict[str, Any] | None
) -> str:
    value = {
        "path": str(worktree.path),
        "head": worktree.head,
        "branch": worktree.branch_name,
        "detached": worktree.detached,
        "locked": worktree.locked_reason,
        "prunable": worktree.prunable_reason,
        "dirty": dirty,
        "ignored_count": ignored["count"] if ignored else None,
        "ignored_digest": ignored["digest"] if ignored else None,
        "local_tree": ignored["local_tree"] if ignored else None,
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def approval_token(entry: dict[str, Any], repo_root: Path) -> str:
    value = {
        "repo": str(repo_root),
        "path": entry["path"],
        "head": entry["head"],
        "branch": entry["branch"],
        "local_fingerprint": entry["local_fingerprint"],
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


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
    temporary.chmod(0o600)
    temporary.replace(path)


def parse_nonnegative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit and retire remotely durable Git worktrees.",
        epilog=(
            "Examples:\n"
            "  cleanup_worktrees.py --repo . --dry-run --json "
            "--write-approval-report /tmp/audit.json\n"
            "  cleanup_worktrees.py --repo . --apply "
            "--approve-report /tmp/audit.json\n"
            "  cleanup_worktrees.py --repo /src/project --apply --approve TOKEN\n\n"
            "Outputs:\n"
            "  Dry-run can save the reviewed candidate set as an approval report. "
            "Apply rechecks remote durability and local state, removes still-matching "
            "approved worktrees, skips changed candidates, and never adds new candidates."
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
        help="Remove worktrees approved by a report or one or more tokens",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Report worktree status and approval tokens without deleting (default)",
    )
    approval = parser.add_mutually_exclusive_group()
    approval.add_argument(
        "--approve",
        action="append",
        default=[],
        metavar="TOKEN",
        help="Approve one dry-run candidate; repeat for multiple worktrees",
    )
    approval.add_argument(
        "--approve-report",
        metavar="PATH",
        help="Approve every candidate recorded in one reviewed dry-run JSON report",
    )
    parser.add_argument(
        "--write-approval-report",
        metavar="PATH",
        help="Write the complete dry-run JSON to PATH for later --approve-report",
    )
    parser.add_argument(
        "--min-no-pr-age-hours",
        type=parse_nonnegative_float,
        default=24.0,
        help=(
            "Minimum worktree age before a PR-less HEAD already in the remote default "
            "branch is eligible (default: 24)"
        ),
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
    if args.apply and not (args.approve or args.approve_report):
        parser.error("--apply requires --approve-report or at least one --approve token")
    if not args.apply and (args.approve or args.approve_report):
        parser.error("--approve and --approve-report are valid only with --apply")
    if args.apply and args.write_approval_report:
        parser.error("--write-approval-report is valid only with dry-run")
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
    repository = query_repository(selected_root)
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

        dirty, dirty_error = read_worktree_dirty(worktree.path)
        ignored, ignored_error = read_ignored_roots(worktree.path)
        age_hours = worktree_age_hours(worktree.path)
        entry: dict[str, Any] = {
            "name": worktree.path.name,
            "path": str(worktree.path),
            "path_relative": to_repo_relative(worktree.path, primary_repo_root),
            "managed": path_is_relative_to(worktree.path, managed_worktrees_root),
            "branch": worktree.branch_name,
            "detached": worktree.detached,
            "head": worktree.head,
            "locked_reason": worktree.locked_reason,
            "prunable_reason": worktree.prunable_reason,
            "age_hours": round(age_hours, 2) if age_hours is not None else None,
            "dirty": dirty,
            "ignored": ignored,
            "local_fingerprint": local_fingerprint(worktree, dirty, ignored),
            "pr": None,
            "expiration_reason": None,
            "remote_proof": None,
            "skip_reason": None,
            "approval_token": None,
            "action": "would-remove",
            "backup_path": None,
            "error": None,
        }

        skip_reason: str | None = None
        if worktree.path == selected_root:
            skip_reason = "selected --repo checkout cannot be removed"
        elif worktree.locked_reason is not None:
            skip_reason = f"worktree is locked: {worktree.locked_reason}"
        elif worktree.prunable_reason is not None:
            skip_reason = f"worktree metadata is prunable: {worktree.prunable_reason}"
        elif dirty_error is not None:
            skip_reason = f"git status failed: {dirty_error}"
        elif ignored_error is not None:
            skip_reason = f"ignored-file inventory failed: {ignored_error}"
        elif dirty:
            skip_reason = "worktree has staged, unstaged, or untracked changes"

        pr_info: PullRequestInfo | None = None
        if skip_reason is None:
            branch_name = worktree.branch_name
            pr_number = infer_pr_number(worktree.path.name, branch_name)
            if pr_number is not None:
                pr_info, pr_lookup_error = query_pr_by_number(
                    pr_number, repo_root=selected_root
                )
            elif branch_name:
                pr_info, pr_lookup_error = query_pr_by_branch(
                    branch_name, repo_root=selected_root
                )
            else:
                pr_lookup_error = None

            if pr_lookup_error is not None:
                skip_reason = f"PR lookup failed: {pr_lookup_error}"
            elif pr_info is not None:
                entry["pr"] = {
                    "number": pr_info.number,
                    "state": pr_info.state,
                    "title": pr_info.title,
                    "url": pr_info.url,
                    "head_ref_name": pr_info.head_ref_name,
                    "head_ref_oid": pr_info.head_ref_oid,
                    "merged_at": pr_info.merged_at,
                    "closed_at": pr_info.closed_at,
                }
                expiration_reason = pr_info.expiration_reason
                if expiration_reason is None:
                    skip_reason = "PR is still open"
                elif pr_info.head_ref_oid is None:
                    skip_reason = "PR has no remote head OID"
                else:
                    durable, durability_error = remote_contains_commit(
                        repo_root=selected_root,
                        repository=repository,
                        local_head=worktree.head,
                        remote_head=pr_info.head_ref_oid,
                    )
                    if durability_error is not None:
                        skip_reason = (
                            f"remote durability check failed: {durability_error}"
                        )
                    elif not durable:
                        skip_reason = "worktree HEAD is not contained in the PR remote head"
                    else:
                        entry["expiration_reason"] = expiration_reason
                        entry["remote_proof"] = {
                            "kind": "pull-request-head",
                            "remote_head": pr_info.head_ref_oid,
                            "description": (
                                f"HEAD is durable in {pr_info.url} ({expiration_reason})"
                            ),
                        }
            elif age_hours is None:
                skip_reason = "worktree age is unavailable"
            elif age_hours < args.min_no_pr_age_hours:
                skip_reason = (
                    "no associated PR and worktree is younger than "
                    f"{args.min_no_pr_age_hours:g} hours"
                )
            else:
                remote_branches, branch_error = remote_branches_at_head(
                    repo_root=selected_root,
                    repository=repository,
                    local_head=worktree.head,
                )
                if branch_error is not None:
                    skip_reason = f"remote branch lookup failed: {branch_error}"
                elif remote_branches:
                    entry["expiration_reason"] = "pushed-remote-branch"
                    entry["remote_proof"] = {
                        "kind": "remote-branch-head",
                        "remote_head": worktree.head,
                        "branches": remote_branches,
                        "description": (
                            "HEAD is the current tip of remote branch(es): "
                            + ", ".join(remote_branches)
                        ),
                    }
                else:
                    durable, durability_error = remote_contains_commit(
                        repo_root=selected_root,
                        repository=repository,
                        local_head=worktree.head,
                        remote_head=repository.default_head_oid,
                    )
                    if durability_error is not None:
                        skip_reason = (
                            f"remote durability check failed: {durability_error}"
                        )
                    elif not durable:
                        skip_reason = (
                            "no completed PR, remote branch tip, or containment in "
                            f"the remote default branch {repository.default_branch}"
                        )
                    else:
                        entry["expiration_reason"] = "landed-on-default"
                        entry["remote_proof"] = {
                            "kind": "default-branch",
                            "remote_head": repository.default_head_oid,
                            "description": (
                                f"HEAD is durable in remote default branch "
                                f"{repository.default_branch}"
                            ),
                        }

        entry["skip_reason"] = skip_reason
        if skip_reason is not None:
            entry["action"] = "skip"
        else:
            entry["approval_token"] = approval_token(entry, primary_repo_root)
        entries.append(entry)

    return {
        "mode": "apply" if args.apply else "dry-run",
        "common_repo_root": str(primary_repo_root),
        "selected_repo_root": str(selected_root),
        "repository": {
            "name_with_owner": repository.name_with_owner,
            "default_branch": repository.default_branch,
            "default_head_oid": repository.default_head_oid,
        },
        "managed_worktrees_root": str(managed_worktrees_root),
        "backup_root": str(backup_root),
        "min_no_pr_age_hours": args.min_no_pr_age_hours,
        "worktree_count_before": len(worktrees),
        "worktree_count_after": len(worktrees),
        "scanned": len(entries),
        "eligible": sum(entry["skip_reason"] is None for entry in entries),
        "approved": 0,
        "removed": 0,
        "failed": 0,
        "rejected_approvals": [],
        "entries": entries,
    }


def read_approval_report(path: str, summary: dict[str, Any]) -> list[str]:
    report_path = Path(path).expanduser().resolve()
    try:
        raw = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CommandError(f"Cannot read approval report {report_path}: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("entries"), list):
        raise CommandError(f"Invalid approval report {report_path}: missing entries")
    if raw.get("common_repo_root") != summary["common_repo_root"]:
        raise CommandError(
            f"Approval report {report_path} belongs to a different repository"
        )
    tokens = [
        entry.get("approval_token")
        for entry in raw["entries"]
        if isinstance(entry, dict) and entry.get("approval_token") is not None
    ]
    if not tokens or not all(isinstance(token, str) for token in tokens):
        raise CommandError(f"Approval report {report_path} has no valid candidates")
    return tokens


def current_worktree(repo_root: Path, path: Path) -> WorktreeInfo | None:
    worktrees = parse_worktree_list(
        run_git("-C", str(repo_root), "worktree", "list", "--porcelain")
    )
    return next((worktree for worktree in worktrees if worktree.path == path), None)


def revalidate_local_state(entry: dict[str, Any], repo_root: Path) -> str | None:
    path = Path(entry["path"])
    worktree = current_worktree(repo_root, path)
    if worktree is None:
        return "worktree registration disappeared after audit"
    dirty, dirty_error = read_worktree_dirty(path)
    ignored, ignored_error = read_ignored_roots(path)
    if dirty_error is not None:
        return f"git status failed during revalidation: {dirty_error}"
    if ignored_error is not None:
        return f"ignored-file inventory failed during revalidation: {ignored_error}"
    current_fingerprint = local_fingerprint(worktree, dirty, ignored)
    if current_fingerprint != entry["local_fingerprint"]:
        return "worktree HEAD, lock, dirty state, or ignored files changed after audit"
    return None


def git_supports_user_approval(repo_root: Path) -> bool:
    result = run_command(["git", "--wrapper-help"], cwd=repo_root, check=False)
    return result.returncode == 0 and "--user-approved" in result.stdout


def apply_candidates(summary: dict[str, Any], approved_tokens: list[str]) -> None:
    eligible_by_token = {
        entry["approval_token"]: entry
        for entry in summary["entries"]
        if entry["approval_token"] is not None
    }
    approvals = set(approved_tokens)
    if len(approvals) != len(approved_tokens):
        raise CommandError("Duplicate approval tokens are not allowed")
    unknown = sorted(approvals - set(eligible_by_token))
    summary["rejected_approvals"] = [token[:12] for token in unknown]
    candidates = [
        eligible_by_token[token]
        for token in approved_tokens
        if token in eligible_by_token
    ]
    for entry in summary["entries"]:
        if entry["approval_token"] is not None:
            entry["action"] = "approved" if entry in candidates else "not-approved"
    summary["approved"] = len(candidates)
    if not candidates:
        return

    backup_root = Path(summary["backup_root"]).resolve()
    for candidate in candidates:
        worktree_path = Path(candidate["path"]).resolve()
        if path_is_relative_to(backup_root, worktree_path):
            raise CommandError(
                f"Backup root {backup_root} is inside cleanup target {worktree_path}"
            )

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    batch_root = backup_root / timestamp
    batch_root.mkdir(parents=True, mode=0o700, exist_ok=False)
    batch_root.chmod(0o700)
    summary["backup_root"] = str(batch_root)
    manifest_path = batch_root / "manifest.json"
    guard_supports_user_approval = git_supports_user_approval(
        Path(summary["common_repo_root"])
    )

    def update_manifest() -> None:
        write_json(
            manifest_path,
            {
                "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "backup_root": str(batch_root),
                "rejected_approvals": summary["rejected_approvals"],
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
                    "updated_at": datetime.now()
                    .astimezone()
                    .isoformat(timespec="seconds"),
                    "source_local_dir": str(local_dir),
                    "worktree": candidate,
                },
            )

        def fail_candidate(error: str) -> None:
            candidate["action"] = "failed"
            candidate["error"] = error
            summary["failed"] += 1
            update_metadata()
            update_manifest()

        state_error = revalidate_local_state(
            candidate, Path(summary["common_repo_root"])
        )
        if state_error is not None:
            fail_candidate(state_error)
            continue

        try:
            backup_dir = ensure_unique_backup_dir(batch_root, candidate["name"])
            backup_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
            backup_dir.chmod(0o700)
            candidate["backup_path"] = str(backup_dir)
            candidate["action"] = "remove-pending"
            metadata_path = backup_dir / "metadata.json"
            if local_dir.exists():
                shutil.copytree(local_dir, backup_dir / ".local", symlinks=True)
        except OSError as exc:
            fail_candidate(f"backup failed: {exc}")
            continue

        update_metadata()
        update_manifest()

        state_error = revalidate_local_state(
            candidate, Path(summary["common_repo_root"])
        )
        if state_error is not None:
            fail_candidate(state_error)
            continue

        # 单级授权：wrapper 唯一的授权参数是 --user-approved。脚本已预先验证
        # 目标干净且远端可证明，reason 记录该预检结论供审计；wrapper 不在时
        # 直接用普通 git（探测见 git_supports_user_approval）。
        remove_args = ["git"]
        if guard_supports_user_approval:
            remove_args.append(
                "--user-approved="
                f"worktree-cleanup approval {candidate['approval_token'][:12]} "
                "for a clean remotely durable worktree"
            )
        remove_args.extend(["worktree", "remove", str(worktree_path)])
        result = run_command(
            remove_args,
            cwd=Path(summary["common_repo_root"]),
            check=False,
        )
        if result.returncode != 0:
            candidate["action"] = (
                "authorization-required" if result.returncode == 77 else "failed"
            )
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

    summary["worktree_count_after"] = len(
        parse_worktree_list(
            run_git(
                "-C",
                summary["common_repo_root"],
                "worktree",
                "list",
                "--porcelain",
            )
        )
    )


def print_text(summary: dict[str, Any]) -> None:
    print(f"mode: {summary['mode']}")
    print(f"repo: {summary['common_repo_root']}")
    print(f"github_repo: {summary['repository']['name_with_owner']}")
    print(f"default_branch: {summary['repository']['default_branch']}")
    print(f"backup_root: {summary['backup_root']}")
    print(f"worktrees_before: {summary['worktree_count_before']}")
    print(f"worktrees_after: {summary['worktree_count_after']}")
    print(f"scanned: {summary['scanned']}")
    print(f"eligible: {summary['eligible']}")
    print(f"approved: {summary['approved']}")
    print(f"removed: {summary['removed']}")
    print(f"failed: {summary['failed']}")
    print(f"rejected_approvals: {len(summary['rejected_approvals'])}")
    print()

    for entry in summary["entries"]:
        pr = entry["pr"]
        pr_summary = f"PR #{pr['number']} {pr['state']}" if pr else "no-pr"
        print(f"- {entry['path_relative']}")
        print(f"  scope: {'managed' if entry['managed'] else 'external'}")
        print(f"  pr: {pr_summary}")
        print(f"  head: {entry['head']}")
        print(f"  remote_proof: {entry['remote_proof'] or 'none'}")
        print(f"  dirty: {entry['dirty']}")
        print(f"  locked: {entry['locked_reason'] or 'no'}")
        ignored = entry["ignored"]
        print(
            "  ignored_path_roots_not_files: "
            f"{ignored['count'] if ignored else 'unknown'}"
        )
        if ignored:
            print(
                "  local_backup: "
                f"{'yes' if ignored['local_tree']['entry_count'] else 'no'}"
            )
            print(f"  ignored_roots_deleted_count: {ignored['discarded_count']}")
            print(f"  ignored_roots_deleted_sample: {ignored['discarded_sample']}")
            print(
                "  ignored_roots_deleted_sample_truncated: "
                f"{'yes' if ignored['discarded_sample_truncated'] else 'no'}"
            )
        else:
            print("  local_backup: unknown")
            print("  ignored_roots_deleted_count: unknown")
            print("  ignored_roots_deleted_sample: unknown")
            print("  ignored_roots_deleted_sample_truncated: unknown")
        print(f"  action: {entry['action']}")
        if entry["approval_token"]:
            print(f"  approval_token: {entry['approval_token']}")
        if entry["backup_path"]:
            print(f"  backup_path: {entry['backup_path']}")
        if entry["skip_reason"]:
            print(f"  note: {entry['skip_reason']}")
        if entry["error"]:
            print(f"  error: {entry['error']}")
        print()


def emit_error(args: argparse.Namespace, error: str) -> None:
    if args.json:
        json.dump({"error": error, "mode": "apply" if args.apply else "dry-run"}, sys.stdout)
        sys.stdout.write("\n")
    else:
        print(f"ERROR: {error}", file=sys.stderr)


def main() -> int:
    args = parse_args()
    try:
        summary = discover(args)
        if args.apply:
            approved_tokens = (
                read_approval_report(args.approve_report, summary)
                if args.approve_report
                else args.approve
            )
            apply_candidates(summary, approved_tokens)
        elif args.write_approval_report:
            write_json(Path(args.write_approval_report).expanduser(), summary)
    except (CommandError, OSError) as exc:
        emit_error(args, str(exc))
        return 1

    if args.json:
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print_text(summary)
    return 1 if summary["failed"] or summary["rejected_approvals"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
