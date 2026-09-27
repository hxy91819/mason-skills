#!/usr/bin/env python3
"""
Mermaid diagram syntax validator.

Extracts every mermaid code block from markdown files and hands them to
mermaid-worker.mjs, which renders them one by one inside a single browser
session, then prints a structured JSON report for an agent to consume.

Usage:
    python validate-mermaid.py <markdown_file_or_glob> [more ...]

Exit codes:
    0 - every diagram is valid (warnings may still be present)
    1 - at least one diagram has a syntax error
    2 - usage error / missing dependency / worker failure
"""

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Optional

WORKER_NAME = "mermaid-worker.mjs"
# Raise on slow machines; drop to a tiny value to exercise the timeout fallback.
PER_BLOCK_TIMEOUT_MS = int(os.environ.get("MERMAID_LINT_BLOCK_TIMEOUT_MS", "20000"))
# Budget for fixed per-session cost such as browser startup; raise it on slow cold starts.
SESSION_OVERHEAD_MS = int(os.environ.get("MERMAID_LINT_SESSION_OVERHEAD_MS", "15000"))


@dataclass
class MermaidBlock:
    """A mermaid code block extracted from markdown."""

    index: int  # 1-based position within the file
    line_start: int  # first content line in the source file, 1-based
    line_end: int  # last content line in the source file, 1-based
    content: str  # block body, fences excluded
    diagram_type: str  # e.g. "graph TD", "sequenceDiagram"


@dataclass
class FileReport:
    path: str
    blocks: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Dependency detection
# ---------------------------------------------------------------------------


def find_mermaid_cli_dir() -> Optional[str]:
    """
    Locate the @mermaid-js/mermaid-cli install directory from mmdc on PATH.

    The worker reuses the puppeteer and mermaid runtime bundled inside that
    package, so what is needed here is the package directory, not the executable.
    """
    mmdc = shutil.which("mmdc")
    if not mmdc:
        return None

    current = os.path.dirname(os.path.realpath(mmdc))
    # Walk up from src/cli.js to the nearest package.json; five levels covers
    # the usual global and local install layouts.
    for _ in range(5):
        if os.path.isfile(os.path.join(current, "package.json")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None


def check_dependencies() -> Optional[dict]:
    """Return a description dict when node or mermaid-cli is missing, else None."""

    missing = []
    install_hints = []

    if not shutil.which("node"):
        missing.append("node")
        install_hints.append("Node.js is not installed. Install Node.js >= 18 via your system package manager or nvm.")

    if not shutil.which("mmdc"):
        missing.append("mermaid-cli")
        install_hints.append(
            "mermaid-cli is not installed. To avoid a global install: "
            "npx -p @mermaid-js/mermaid-cli mmdc --version. "
            "Only consider npm install -g @mermaid-js/mermaid-cli if you want it permanently."
        )

    if missing:
        return {
            "status": "missing_dependency",
            "missing": missing,
            "install_hints": install_hints,
        }
    return None


# ---------------------------------------------------------------------------
# Mermaid block extraction
# ---------------------------------------------------------------------------

# CommonMark fence: up to 3 leading spaces, 3+ backticks or tildes, then an info string.
_FENCE_RE = re.compile(r"^(?P<indent> {0,3})(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
# mermaid-cli also accepts the directive form :::mermaid ... :::
_DIRECTIVE_OPEN_RE = re.compile(r"^ {0,3}:{3,}\s*mermaid\s*$", re.IGNORECASE)
_DIRECTIVE_CLOSE_RE = re.compile(r"^ {0,3}:{3,}\s*$")


def _fence_info_lang(info: str) -> str:
    """Use the first token of the info string as the language tag, so
    ```mermaid title="x" is still recognised."""
    stripped = info.strip()
    if not stripped:
        return ""
    return stripped.split()[0].lower()


def extract_mermaid_blocks(lines: list) -> tuple:
    """
    Extract mermaid blocks from a sequence of markdown lines; returns (blocks, warnings).

    Every fence has to be tracked, not just mermaid ones. Wrapping a deliberately
    broken mermaid sample in a longer fence to show a counter-example is common in
    documentation, and matching only ```mermaid would report it as a real diagram.
    A mermaid fence is treated as a block to validate only at the outermost level,
    that is when no other fence is currently open.
    """

    blocks = []
    warnings = []

    in_fence = False
    fence_char = ""
    fence_len = 0
    fence_indent = 0
    fence_is_mermaid = False
    fence_open_line = 0

    in_directive = False
    directive_open_line = 0

    content_lines = []
    index = 0

    def close_block(open_line: int, content_end_line: int) -> None:
        nonlocal index
        index += 1
        blocks.append(
            MermaidBlock(
                index=index,
                line_start=open_line + 1,  # content starts on the line after the opening fence
                line_end=content_end_line,
                content="".join(content_lines).strip(),
                diagram_type=_infer_diagram_type(content_lines),
            )
        )

    for lineno, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")

        if in_fence:
            match = _FENCE_RE.match(line)
            is_close = (
                match is not None
                and match.group("fence")[0] == fence_char
                # The closing fence must be at least as long as the opening one,
                # otherwise a ``` inside a ```` block would close it early.
                and len(match.group("fence")) >= fence_len
                and match.group("info").strip() == ""
            )
            if is_close:
                if fence_is_mermaid:
                    close_block(fence_open_line, lineno - 1)
                in_fence = False
                fence_is_mermaid = False
                content_lines = []
            elif fence_is_mermaid:
                # Strip the opening fence indentation, per CommonMark.
                content_lines.append(_strip_indent(raw, fence_indent))
            continue

        if in_directive:
            if _DIRECTIVE_CLOSE_RE.match(line):
                close_block(directive_open_line, lineno - 1)
                in_directive = False
                content_lines = []
            else:
                content_lines.append(raw)
            continue

        match = _FENCE_RE.match(line)
        if match:
            info = match.group("info")
            # CommonMark: a backtick fence info string may not contain backticks.
            if match.group("fence")[0] == "`" and "`" in info:
                continue
            in_fence = True
            fence_char = match.group("fence")[0]
            fence_len = len(match.group("fence"))
            fence_indent = len(match.group("indent"))
            fence_is_mermaid = _fence_info_lang(info) == "mermaid"
            fence_open_line = lineno
            content_lines = []
            continue

        if _DIRECTIVE_OPEN_RE.match(line):
            in_directive = True
            directive_open_line = lineno
            content_lines = []

    # An unterminated fence gives no reliable end position, so warn instead of
    # guessing at the content and emitting a misleading syntax error.
    if in_fence and fence_is_mermaid:
        warnings.append(
            {
                "line": fence_open_line,
                "message": (
                    f"Mermaid code block opened at line {fence_open_line} is never closed "
                    "before end of file; skipped."
                ),
            }
        )
    if in_directive:
        warnings.append(
            {
                "line": directive_open_line,
                "message": (
                    f":::mermaid block opened at line {directive_open_line} is never closed "
                    "before end of file; skipped."
                ),
            }
        )

    return blocks, warnings


def _strip_indent(raw_line: str, indent: int) -> str:
    """Strip at most `indent` leading spaces, preserving deeper indentation."""
    stripped = 0
    position = 0
    while position < len(raw_line) and stripped < indent and raw_line[position] == " ":
        position += 1
        stripped += 1
    return raw_line[position:]


def _infer_diagram_type(content_lines: list) -> str:
    """Infer the diagram type from the first diagram statement."""
    in_directive = False
    for line in content_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if in_directive:
            in_directive = "}%%" not in stripped
            continue
        if stripped.startswith("%%{"):
            in_directive = "}%%" not in stripped
            continue
        if stripped.startswith("%%"):
            continue
        parts = stripped.split()
        first = parts[0]
        # graph and flowchart are normally followed by a direction
        if first.lower() in ("graph", "flowchart") and len(parts) > 1:
            return f"{parts[0]} {parts[1]}"
        return first
    return "unknown"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_ERROR_LINE_RE = re.compile(r"[Pp]arse error on line (\d+)")


def run_worker(payload: dict) -> dict:
    """Run the Node worker that performs the actual render-based validation."""

    worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), WORKER_NAME)
    if not os.path.isfile(worker):
        return {"status": "worker_error", "error": f"Worker script not found: {worker}", "results": []}

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as handle:
            json.dump(payload, handle)
            tmp_path = handle.name

        # Worst case the worker spends one session per block, so allow the same order
        # of magnitude here. Timing out before the worker does would throw away the
        # partial results it has already collected.
        block_count = max(1, len(payload.get("blocks", [])))
        worst_case_ms = (PER_BLOCK_TIMEOUT_MS * block_count + SESSION_OVERHEAD_MS) * 2
        timeout_s = worst_case_ms / 1000 + 60

        result = subprocess.run(
            ["node", worker, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )

        stdout = (result.stdout or "").strip()
        if not stdout:
            return {
                "status": "worker_error",
                "error": (result.stderr or "Worker produced no output").strip(),
                "results": [],
            }
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {
                "status": "worker_error",
                "error": f"Worker output is not valid JSON: {stdout[:500]}",
                "results": [],
            }
    except subprocess.TimeoutExpired:
        return {"status": "worker_error", "error": "Worker timed out overall", "results": []}
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _extract_error_line(message: str) -> Optional[int]:
    """Pull the block-relative line number out of "Parse error on line 5:"."""
    match = _ERROR_LINE_RE.search(message)
    return int(match.group(1)) if match else None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def expand_targets(patterns: list) -> tuple:
    """Expand CLI arguments into a deduplicated markdown file list; returns (files, missing)."""
    files = []
    missing = []
    seen = set()

    for pattern in patterns:
        if os.path.isfile(pattern):
            matches = [pattern]
        elif os.path.isdir(pattern):
            matches = sorted(glob.glob(os.path.join(pattern, "**", "*.md"), recursive=True))
        else:
            matches = sorted(glob.glob(pattern, recursive=True))

        if not matches:
            missing.append(pattern)
            continue

        for match in matches:
            path = os.path.abspath(match)
            if path not in seen and os.path.isfile(path):
                seen.add(path)
                files.append(path)

    return files, missing


def main() -> None:
    if len(sys.argv) < 2:
        _emit({"status": "error", "error": f"Usage: {sys.argv[0]} <markdown_file_or_glob> [more ...]"})
        sys.exit(2)

    targets, missing = expand_targets(sys.argv[1:])
    if missing and not targets:
        _emit({"status": "error", "error": f"No files matched: {', '.join(missing)}"})
        sys.exit(2)

    dep_issue = check_dependencies()
    if dep_issue:
        _emit(dep_issue)
        sys.exit(2)

    cli_dir = find_mermaid_cli_dir()
    if not cli_dir:
        _emit(
            {
                "status": "missing_dependency",
                "missing": ["mermaid-cli"],
                "install_hints": [
                    "Found the mmdc executable but could not locate its install directory. "
                    "Reinstall @mermaid-js/mermaid-cli."
                ],
            }
        )
        sys.exit(2)

    reports = []
    worker_blocks = []
    for path in targets:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                lines = handle.readlines()
        except OSError as exc:
            reports.append(FileReport(path=path, warnings=[{"line": 0, "message": f"Read failed: {exc}"}]))
            continue

        blocks, warnings = extract_mermaid_blocks(lines)
        reports.append(FileReport(path=path, blocks=blocks, warnings=warnings))
        for block in blocks:
            worker_blocks.append(
                {
                    "key": f"{len(reports) - 1}:{block.index}",
                    "domId": f"lint{len(worker_blocks)}",
                    "content": block.content,
                }
            )

    verdicts = {}
    if worker_blocks:
        outcome = run_worker(
            {
                "cliDir": cli_dir,
                "perBlockTimeoutMs": PER_BLOCK_TIMEOUT_MS,
                "sessionOverheadMs": SESSION_OVERHEAD_MS,
                "blocks": worker_blocks,
            }
        )
        if outcome.get("status") != "ok":
            _emit({"status": "error", "error": outcome.get("error", "Worker failed")})
            sys.exit(2)
        verdicts = {item["key"]: item for item in outcome.get("results", [])}

    files_payload = []
    total_blocks = 0
    total_valid = 0
    total_warnings = 0

    for file_index, report in enumerate(reports):
        errors = []
        block_rows = []

        for block in report.blocks:
            verdict = verdicts.get(f"{file_index}:{block.index}", {})
            valid = bool(verdict.get("valid"))
            block_rows.append(
                {
                    "index": block.index,
                    "line_start": block.line_start,
                    "line_end": block.line_end,
                    "diagram_type": block.diagram_type,
                    "valid": valid,
                }
            )
            if valid:
                continue

            message = verdict.get("error", "Unknown error")
            line_in_block = _extract_error_line(message)
            errors.append(
                {
                    "block_index": block.index,
                    "line_start": block.line_start,
                    "line_end": block.line_end,
                    "diagram_type": block.diagram_type,
                    "mermaid_source": block.content,
                    "error_message": message,
                    "error_line_in_block": line_in_block,
                    # Provide the absolute source line so callers do not have to
                    # recompute it from line_start.
                    "error_line_in_file": (
                        block.line_start + line_in_block - 1 if line_in_block else None
                    ),
                    "timed_out": bool(verdict.get("timedOut")),
                }
            )

        total_blocks += len(report.blocks)
        total_valid += len(report.blocks) - len(errors)
        total_warnings += len(report.warnings)

        files_payload.append(
            {
                "file": report.path,
                "total_blocks": len(report.blocks),
                "valid_blocks": len(report.blocks) - len(errors),
                "errors": errors,
                "warnings": report.warnings,
                "blocks": block_rows,
            }
        )

    error_blocks = total_blocks - total_valid
    _emit(
        {
            "status": "error" if error_blocks else "success",
            "summary": {
                "files": len(files_payload),
                "total_blocks": total_blocks,
                "valid_blocks": total_valid,
                "error_blocks": error_blocks,
                "warnings": total_warnings,
                "unmatched_patterns": missing,
            },
            "files": files_payload,
        }
    )
    sys.exit(1 if error_blocks else 0)


def _emit(data: dict) -> None:
    """Write the JSON report to stdout."""
    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
