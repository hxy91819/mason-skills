#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Link this skill into a repository-local skills directory."
    )
    parser.add_argument("--repo", required=True)
    parser.add_argument("--skills-dir", default=".agents/skills")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def repository_root(path):
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        message = error.stderr.strip() if getattr(error, "stderr", None) else str(error)
        raise ValueError(f"--repo must be inside a Git repository: {message}") from error
    return Path(result.stdout.strip()).resolve()


def relative_skills_dir(value):
    path = Path(value)
    if (
        path == Path(".")
        or path.is_absolute()
        or not value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("--skills-dir must be a non-empty relative path below the repository")
    return path


def same_target(link, source):
    try:
        return link.resolve(strict=True) == source.resolve(strict=True)
    except OSError:
        return False


def target_parent_within_repository(target, root):
    parent = target.parent.resolve(strict=False)
    try:
        parent.relative_to(root)
    except ValueError as error:
        raise ValueError("--skills-dir resolves outside the repository") from error
    return parent


def main():
    args = parse_args()
    source = Path(__file__).resolve().parents[1]
    if not (source / "SKILL.md").is_file():
        raise ValueError(f"skill source has no SKILL.md: {source}")

    root = repository_root(Path(args.repo).resolve())
    skills_dir = relative_skills_dir(args.skills_dir)
    target = root / skills_dir / source.name
    target_parent_within_repository(target, root)

    if target.is_symlink():
        if same_target(target, source):
            print(f"KEEP {target}")
            return 0
        print(f"CONFLICT {target} points to {os.readlink(target)}", file=sys.stderr)
        return 1
    if target.exists():
        print(f"CONFLICT {target} is an existing file or directory", file=sys.stderr)
        return 1

    relative_source = os.path.relpath(source, target.parent)
    if not args.apply:
        print(f"CREATE {target} -> {relative_source}")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(relative_source, target_is_directory=True)
    print(f"CREATE {target} -> {relative_source}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        print(f"ERROR {error}", file=sys.stderr)
        raise SystemExit(2)
