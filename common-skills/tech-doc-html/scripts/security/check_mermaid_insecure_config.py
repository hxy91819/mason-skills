#!/usr/bin/env python3
"""Detect insecure Mermaid configuration patterns.

This hook blocks risky Mermaid options that may enable unsafe HTML/script
rendering paths in diagrams.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys


MERMAID_INIT_DIRECTIVE_PATTERN = re.compile(r"%%\{init:\s*(.*?)%%", re.DOTALL)
MERMAID_INITIALIZE_PATTERN = re.compile(
    r"mermaid(?:API)?\.initialize\s*\(\s*(\{.*?\})\s*\)", re.DOTALL
)
ACCEPTABLE_SECURITY_LEVEL_PATTERN = re.compile(
    r"(?:['\"])?securityLevel(?:['\"])?\s*:\s*(?:['\"])?(?:strict|sandbox)(?:['\"])?",
    re.IGNORECASE,
)


RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "MERMAID_HTML_LABELS_TRUE",
        re.compile(r"(?:['\"])?htmlLabels(?:['\"])?\s*:\s*true\b", re.IGNORECASE),
        "Avoid `htmlLabels: true`; prefer plain text labels or set false.",
    ),
    (
        "MERMAID_SECURITY_LEVEL_LOOSE",
        re.compile(
            r"(?:['\"])?securityLevel(?:['\"])?\s*:\s*(?:['\"])?(?:loose|antiscript)(?:['\"])?",
            re.IGNORECASE,
        ),
        "Avoid weak `securityLevel` (`loose`/`antiscript`); keep strict defaults.",
    ),
    (
        "MERMAID_CLICK_CALLBACK",
        re.compile(
            r"^\s*click\s+\S+\s+(?:call\s+)?[A-Za-z_][A-Za-z0-9_]*(?:\s*\(\s*\))?\b",
            re.IGNORECASE,
        ),
        "Avoid Mermaid `click` callbacks (`click id callback` / `click id call fn()`); prefer plain links.",
    ),
    (
        "MERMAID_CLICK_JAVASCRIPT_URL",
        re.compile(
            r"^\s*click\s+\S+.*['\"]\s*javascript:\\?",
            re.IGNORECASE,
        ),
        "Avoid `javascript:` URLs in Mermaid `click` statements.",
    ),
    (
        "MERMAID_SECURE_OVERRIDE_EMPTY",
        re.compile(r"(?:['\"])?secure(?:['\"])?\s*:\s*\[\s*\]", re.IGNORECASE),
        "Avoid empty Mermaid `secure` allowlist override; keep secure defaults.",
    ),
)

TEXT_EXTENSIONS = {
    ".md",
    ".markdown",
    ".mdx",
    ".html",
    ".htm",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".json",
    ".mmd",
    ".txt",
}

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
}


def _line_no(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def _check_explicit_strict(file_path: pathlib.Path, content: str, findings: list[str]) -> None:
    for match in MERMAID_INIT_DIRECTIVE_PATTERN.finditer(content):
        block = match.group(1)
        if ACCEPTABLE_SECURITY_LEVEL_PATTERN.search(block):
            continue
        line_no = _line_no(content, match.start())
        snippet = match.group(0).splitlines()[0].strip()
        findings.append(
            f"{file_path}:{line_no}: [MERMAID_SECURITY_LEVEL_REQUIRED] "
            "`%%{init}` must explicitly set `securityLevel: 'strict' or 'sandbox'`. "
            f"-> {snippet}"
        )

    for match in MERMAID_INITIALIZE_PATTERN.finditer(content):
        block = match.group(1)
        if ACCEPTABLE_SECURITY_LEVEL_PATTERN.search(block):
            continue
        line_no = _line_no(content, match.start())
        snippet = match.group(0).splitlines()[0].strip()
        findings.append(
            f"{file_path}:{line_no}: [MERMAID_SECURITY_LEVEL_REQUIRED] "
            "`mermaid.initialize(...)` must explicitly set `securityLevel: 'strict' or 'sandbox'`. "
            f"-> {snippet}"
        )


def _iter_files(paths: list[str]) -> list[pathlib.Path]:
    if paths:
        return [pathlib.Path(p) for p in paths]

    files: list[pathlib.Path] = []
    for path in pathlib.Path(".").rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in TEXT_EXTENSIONS:
            files.append(path)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check repository for insecure Mermaid configuration."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Optional file paths from pre-commit; scans repo when omitted.",
    )
    args = parser.parse_args()

    findings: list[str] = []
    files = _iter_files(args.paths)

    for file_path in files:
        if any(part in SKIP_DIRS for part in file_path.parts):
            continue
        if file_path.suffix.lower() not in TEXT_EXTENSIONS:
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        _check_explicit_strict(file_path, content, findings)

        for line_no, line in enumerate(content.splitlines(), start=1):
            for code, pattern, message in RULES:
                if pattern.search(line):
                    findings.append(
                        f"{file_path}:{line_no}: [{code}] {message} -> {line.strip()}"
                    )

    if findings:
        print("Found insecure Mermaid configuration:")
        for item in findings:
            print(item)
        return 1

    print("No insecure Mermaid configuration found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
