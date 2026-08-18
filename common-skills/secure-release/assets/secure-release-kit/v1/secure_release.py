#!/usr/bin/env python3
"""Fail-closed release validation and the secure-release kit v1 npm adapter.

Definition:
  Validate immutable Git release identity, extract committed changelog notes,
  create/verify a canonical SHA-256 manifest, and package/publish/smoke one npm
  package. CI copies this file into the target repository; it never loads a
  Codex skill at runtime.

Parameters:
  Run ``secure_release.py <command> --help`` for command-specific parameters.

Outputs:
  Commands write only explicitly requested notes, artifacts, or manifests.
  Success summaries go to stdout; actionable failures go to stderr with exit 1.

Examples:
  python3 secure_release.py source --tag v1.2.3 --version 1.2.3 --primary-ref origin/main
  python3 secure_release.py manifest-verify --manifest release/manifest.json --directory release
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


STABLE_TAG = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MANIFEST_SCHEMA = "https://mason-skills.example/secure-release/manifest/v1"


class ReleaseError(RuntimeError):
    """Expected invalid input or release-state error."""


def run(command: Sequence[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise ReleaseError(f"could not execute {command[0]}: {exc}") from exc


def checked(command: Sequence[str], *, cwd: Path | None = None) -> str:
    result = run(command, cwd=cwd)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ReleaseError(f"command failed ({' '.join(command)}): {detail}")
    return result.stdout.strip()


def parse_tag(tag: str) -> str:
    match = STABLE_TAG.fullmatch(tag)
    if match is None:
        raise ReleaseError(f"tag must be a stable vX.Y.Z value: {tag}")
    return tag[1:]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def regular_file(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise ReleaseError(f"cannot inspect artifact {path}: {exc}") from exc
    if not stat.S_ISREG(mode):
        raise ReleaseError(f"artifact must be a regular file, not a symlink or directory: {path}")


def source(args: argparse.Namespace) -> None:
    expected = parse_tag(args.tag)
    if args.version != expected:
        raise ReleaseError(f"declared version {args.version} does not match tag {args.tag}")
    tag_commit = checked(("git", "rev-parse", "--verify", f"refs/tags/{args.tag}^{{commit}}"))
    primary_commit = checked(("git", "rev-parse", "--verify", f"{args.primary_ref}^{{commit}}"))
    ancestry = run(("git", "merge-base", "--is-ancestor", tag_commit, primary_commit))
    if ancestry.returncode != 0:
        raise ReleaseError(f"tag commit {tag_commit} is not reachable from {args.primary_ref}")
    head_commit = checked(("git", "rev-parse", "HEAD^{commit}"))
    if head_commit != tag_commit:
        raise ReleaseError(f"HEAD {head_commit} is not the exact tag commit {tag_commit}")
    print(f"source ok: tag={args.tag} version={args.version} commit={tag_commit}")


def changelog(args: argparse.Namespace) -> None:
    parse_tag(args.tag)
    content = args.changelog.read_text(encoding="utf-8")
    if not content.startswith("# Changelog\n"):
        raise ReleaseError("changelog must start with '# Changelog'")
    marker = f"## {args.tag}\n"
    start = content.find(marker)
    if start < 0 or (start > 0 and content[start - 1] != "\n"):
        raise ReleaseError(f"changelog has no exact section for {args.tag}")
    end = content.find("\n## ", start + len(marker))
    notes = content[start:] if end < 0 else content[start : end + 1]
    if not notes.strip().splitlines()[1:]:
        raise ReleaseError(f"changelog section for {args.tag} is empty")
    args.notes.parent.mkdir(parents=True, exist_ok=True)
    args.notes.write_text(notes.rstrip() + "\n", encoding="utf-8")
    print(f"changelog ok: tag={args.tag} notes={args.notes}")


def build_manifest(tag: str, version: str, artifacts: Sequence[Path], output: Path) -> None:
    parse_tag(tag)
    if version != tag[1:]:
        raise ReleaseError(f"manifest version {version} does not match tag {tag}")
    if not artifacts:
        raise ReleaseError("at least one artifact is required")
    names: set[str] = set()
    records: list[dict[str, Any]] = []
    for artifact in artifacts:
        regular_file(artifact)
        if artifact.name in names or artifact.name == output.name:
            raise ReleaseError(f"duplicate or reserved artifact filename: {artifact.name}")
        names.add(artifact.name)
        records.append(
            {"name": artifact.name, "sha256": sha256(artifact), "size": artifact.stat().st_size}
        )
    commit = checked(("git", "rev-parse", "HEAD^{commit}"))
    payload = {
        "schema": MANIFEST_SCHEMA,
        "tag": tag,
        "version": version,
        "commit": commit,
        "artifacts": sorted(records, key=lambda item: item["name"]),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"manifest created: path={output} artifacts={len(records)} commit={commit}")


def manifest_create(args: argparse.Namespace) -> None:
    build_manifest(args.tag, args.version, args.artifact, args.output)


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"cannot read valid manifest {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != MANIFEST_SCHEMA:
        raise ReleaseError("manifest has an unknown schema")
    return value


def manifest_verify(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.manifest)
    tag = manifest.get("tag")
    version = manifest.get("version")
    commit = manifest.get("commit")
    records = manifest.get("artifacts")
    if not isinstance(tag, str) or not isinstance(version, str) or version != parse_tag(tag):
        raise ReleaseError("manifest tag and version are invalid or inconsistent")
    if args.tag is not None and tag != args.tag:
        raise ReleaseError(f"manifest tag {tag} does not match expected {args.tag}")
    if args.version is not None and version != args.version:
        raise ReleaseError(f"manifest version {version} does not match expected {args.version}")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40,64}", commit):
        raise ReleaseError("manifest commit is invalid")
    if checked(("git", "rev-parse", "HEAD^{commit}")) != commit:
        raise ReleaseError("manifest commit does not match checked-out HEAD")
    if not isinstance(records, list) or not records:
        raise ReleaseError("manifest artifacts must be a non-empty array")
    expected: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise ReleaseError("manifest contains an invalid artifact record")
        name, digest, size = record.get("name"), record.get("sha256"), record.get("size")
        if (
            not isinstance(name, str)
            or Path(name).name != name
            or name in expected
            or not isinstance(digest, str)
            or SHA256.fullmatch(digest) is None
            or not isinstance(size, int)
            or size < 0
        ):
            raise ReleaseError("manifest contains an unsafe or invalid artifact record")
        expected.add(name)
        artifact = args.directory / name
        regular_file(artifact)
        if artifact.stat().st_size != size or sha256(artifact) != digest:
            raise ReleaseError(f"artifact size or SHA-256 mismatch: {name}")
    actual = {
        path.name
        for path in args.directory.iterdir()
        if path.name != args.manifest.name
    }
    if actual != expected:
        raise ReleaseError(f"artifact set mismatch: expected={sorted(expected)} actual={sorted(actual)}")
    print(f"manifest verified: tag={tag} artifacts={len(expected)} commit={commit}")


def read_package(package_dir: Path) -> tuple[str, str]:
    try:
        value = json.loads((package_dir / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"cannot read package.json: {exc}") from exc
    if not isinstance(value, dict):
        raise ReleaseError("package.json must contain a JSON object")
    name, version = value.get("name"), value.get("version")
    if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
        raise ReleaseError("package.json must contain non-empty name and version")
    return name, version


def npm_pack_record(payload: Any, *, context: str) -> dict[str, Any]:
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = list(payload.values())
    else:
        records = []
    if len(records) != 1 or not isinstance(records[0], dict):
        raise ReleaseError(f"{context} must produce exactly one package")
    return records[0]


def npm_pack(args: argparse.Namespace) -> None:
    _, version = read_package(args.package_dir)
    if version != parse_tag(args.tag):
        raise ReleaseError(f"package version {version} does not match tag {args.tag}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="secure-release-pack-") as temporary:
        result = run(
            (args.npm, "pack", "--json", "--pack-destination", temporary), cwd=args.package_dir
        )
        if result.returncode != 0:
            raise ReleaseError(f"npm pack failed: {result.stderr.strip() or result.stdout.strip()}")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ReleaseError("npm pack did not return valid JSON") from exc
        filename = npm_pack_record(payload, context="npm pack").get("filename")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ReleaseError("npm pack returned an unsafe filename")
        source_path = Path(temporary) / filename
        regular_file(source_path)
        destination = args.output_dir / filename
        if destination.exists():
            raise ReleaseError(f"refusing to overwrite existing artifact: {destination}")
        shutil.move(source_path, destination)
    build_manifest(args.tag, version, (destination,), args.manifest)
    print(f"npm pack ok: artifact={destination}")


def npm_absent(args: argparse.Namespace) -> None:
    result = run((args.npm, "view", f"{args.package}@{args.version}", "version", "--registry", args.registry))
    if result.returncode == 0:
        raise ReleaseError(f"npm version already exists: {args.package}@{args.version}")
    combined = f"{result.stdout}\n{result.stderr}"
    if re.search(r"^npm (?:ERR!|error) code E404\s*$", combined, re.MULTILINE) is None:
        raise ReleaseError("npm lookup failed without a recognized E404; absence is unproven")
    print(f"npm registry absence verified: {args.package}@{args.version}")


def npm_existing(args: argparse.Namespace) -> None:
    regular_file(args.artifact)
    exact = f"{args.package}@{args.version}"
    with tempfile.TemporaryDirectory(prefix="secure-release-existing-") as temporary:
        result = run(
            (
                args.npm,
                "pack",
                exact,
                "--json",
                "--ignore-scripts",
                "--pack-destination",
                temporary,
                "--registry",
                args.registry,
            )
        )
        if result.returncode != 0:
            raise ReleaseError(
                "cannot download the existing npm version for byte comparison: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ReleaseError("npm pack for the existing version did not return valid JSON") from exc
        filename = npm_pack_record(
            payload, context="existing npm version resolution"
        ).get("filename")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ReleaseError("existing npm version returned an unsafe filename")
        downloaded = Path(temporary) / filename
        regular_file(downloaded)
        if downloaded.stat().st_size != args.artifact.stat().st_size or sha256(downloaded) != sha256(args.artifact):
            raise ReleaseError(f"existing npm bytes differ from intended artifact: {exact}")
    print(f"npm existing version reconciled: {exact} bytes=identical")


def npm_publish(args: argparse.Namespace) -> None:
    regular_file(args.artifact)
    command = [
        args.npm,
        "publish",
        str(args.artifact),
        "--access",
        args.access,
        "--tag",
        args.dist_tag,
        "--provenance",
        "--registry",
        args.registry,
    ]
    checked(command)
    print(f"npm publish completed: artifact={args.artifact} registry={args.registry}")


def npm_smoke(args: argparse.Namespace) -> None:
    exact = f"{args.package}@{args.version}"
    observed = checked((args.npm, "view", exact, "version", "--registry", args.registry))
    if observed.strip().strip('"') != args.version:
        raise ReleaseError(f"registry returned version {observed!r}, expected {args.version}")
    with tempfile.TemporaryDirectory(prefix="secure-release-smoke-") as temporary:
        consumer = Path(temporary)
        checked((args.npm, "init", "--yes"), cwd=consumer)
        checked((args.npm, "install", "--ignore-scripts", "--no-audit", "--no-fund", exact, "--registry", args.registry), cwd=consumer)
        package_json = consumer / "node_modules" / Path(*args.package.split("/")) / "package.json"
        _, installed = read_package(package_json.parent)
        if installed != args.version:
            raise ReleaseError(f"installed version {installed} does not match {args.version}")
    print(f"npm smoke ok: installed={exact}")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Secure release kit v1: common validators and the implemented npm adapter.",
        epilog=(
            "Outputs:\n"
            "  Writes only explicitly named release artifacts, manifests, or notes.\n"
            "  All validation and adapter failures exit nonzero.\n\n"
            "Examples:\n"
            "  %(prog)s source --tag v1.2.3 --version 1.2.3 --primary-ref origin/main\n"
            "  %(prog)s npm-pack --tag v1.2.3 --package-dir . --output-dir release "
            "--manifest release/manifest.json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = root.add_subparsers(dest="command", required=True)

    command = commands.add_parser("source", help="Validate stable tag, version, HEAD, and primary ancestry.")
    command.add_argument("--tag", required=True)
    command.add_argument("--version", required=True)
    command.add_argument("--primary-ref", required=True)
    command.set_defaults(handler=source)

    command = commands.add_parser("changelog", help="Extract an exact committed changelog section.")
    command.add_argument("--tag", required=True)
    command.add_argument("--changelog", required=True, type=Path)
    command.add_argument("--notes", required=True, type=Path)
    command.set_defaults(handler=changelog)

    command = commands.add_parser("manifest-create", help="Create a canonical manifest for release files.")
    command.add_argument("--tag", required=True)
    command.add_argument("--version", required=True)
    command.add_argument("--artifact", required=True, action="append", type=Path)
    command.add_argument("--output", required=True, type=Path)
    command.set_defaults(handler=manifest_create)

    command = commands.add_parser("manifest-verify", help="Verify identity and the exact artifact set.")
    command.add_argument("--manifest", required=True, type=Path)
    command.add_argument("--directory", required=True, type=Path)
    command.add_argument("--tag")
    command.add_argument("--version")
    command.set_defaults(handler=manifest_verify)

    command = commands.add_parser("npm-pack", help="Build exactly one npm tarball and its manifest.")
    command.add_argument("--tag", required=True)
    command.add_argument("--package-dir", required=True, type=Path)
    command.add_argument("--output-dir", required=True, type=Path)
    command.add_argument("--manifest", required=True, type=Path)
    command.add_argument("--npm", default="npm")
    command.set_defaults(handler=npm_pack)

    for name, help_text, handler in (
        ("npm-absent", "Require a recognized npm E404 for the exact version.", npm_absent),
        ("npm-smoke", "Resolve and clean-install the exact npm version.", npm_smoke),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--package", required=True)
        command.add_argument("--version", required=True)
        command.add_argument("--registry", default="https://registry.npmjs.org/")
        command.add_argument("--npm", default="npm")
        command.set_defaults(handler=handler)

    command = commands.add_parser(
        "npm-existing", help="Require an existing npm version to have identical tarball bytes."
    )
    command.add_argument("--package", required=True)
    command.add_argument("--version", required=True)
    command.add_argument("--artifact", required=True, type=Path)
    command.add_argument("--registry", default="https://registry.npmjs.org/")
    command.add_argument("--npm", default="npm")
    command.set_defaults(handler=npm_existing)

    command = commands.add_parser("npm-publish", help="Publish one exact tarball with provenance.")
    command.add_argument("--artifact", required=True, type=Path)
    command.add_argument("--registry", default="https://registry.npmjs.org/")
    command.add_argument("--access", choices=("public", "restricted"), default="public")
    command.add_argument("--dist-tag", default="latest")
    command.add_argument("--npm", default="npm")
    command.set_defaults(handler=npm_publish)
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        args.handler(args)
    except (ReleaseError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
