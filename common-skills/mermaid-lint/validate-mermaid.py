#!/usr/bin/env python3
"""
Mermaid 图表语法验证器。

从 markdown 文件中提取所有 mermaid 代码块，交给 mermaid-worker.mjs 在单个浏览器会话里
逐块渲染校验，输出结构化 JSON 供 AI 消费。

用法:
    python validate-mermaid.py <markdown_file_or_glob> [more ...]

退出码:
    0 - 所有图表语法正确（可能带 warnings）
    1 - 存在语法错误
    2 - 用法错误 / 依赖缺失 / worker 异常
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
# 慢机器上可调高；测试超时降级路径时可调到极小值。
PER_BLOCK_TIMEOUT_MS = int(os.environ.get("MERMAID_LINT_BLOCK_TIMEOUT_MS", "20000"))
# 单轮会话里浏览器启动等固定开销的预算，冷启动慢的机器需要调高。
SESSION_OVERHEAD_MS = int(os.environ.get("MERMAID_LINT_SESSION_OVERHEAD_MS", "15000"))


@dataclass
class MermaidBlock:
    """从 markdown 中提取的 mermaid 代码块。"""

    index: int  # 文件内序号，从 1 开始
    line_start: int  # 块内容起始行（源文件中，1-based）
    line_end: int  # 块内容结束行（源文件中，1-based）
    content: str  # 代码块内容（不含 fence）
    diagram_type: str  # 图表类型，如 "graph TD", "sequenceDiagram"


@dataclass
class FileReport:
    path: str
    blocks: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# 依赖检测
# ---------------------------------------------------------------------------


def find_mermaid_cli_dir() -> Optional[str]:
    """
    从 PATH 上的 mmdc 反查 @mermaid-js/mermaid-cli 的安装目录。

    worker 需要复用它自带的 puppeteer 和 mermaid 运行时，因此这里要的是包目录而非可执行文件。
    """
    mmdc = shutil.which("mmdc")
    if not mmdc:
        return None

    current = os.path.dirname(os.path.realpath(mmdc))
    # 从 src/cli.js 往上找最近的 package.json，层数够覆盖常见的全局/局部安装布局。
    for _ in range(5):
        if os.path.isfile(os.path.join(current, "package.json")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None


def check_dependencies() -> Optional[dict]:
    """检查 node 与 mermaid-cli 是否就绪，缺失时返回描述 dict，就绪返回 None。"""

    missing = []
    install_hints = []

    if not shutil.which("node"):
        missing.append("node")
        install_hints.append("Node.js 未安装。建议用系统包管理器或 nvm 安装 Node.js >= 18。")

    if not shutil.which("mmdc"):
        missing.append("mermaid-cli")
        install_hints.append(
            "mermaid-cli 未安装。免全局安装的用法: "
            "npx -p @mermaid-js/mermaid-cli mmdc --version；"
            "若确实要常驻再考虑 npm install -g @mermaid-js/mermaid-cli。"
        )

    if missing:
        return {
            "status": "missing_dependency",
            "missing": missing,
            "install_hints": install_hints,
        }
    return None


# ---------------------------------------------------------------------------
# Mermaid 块提取
# ---------------------------------------------------------------------------

# CommonMark 围栏：最多 3 个前导空格，3 个及以上的反引号或波浪号，其后是 info string。
_FENCE_RE = re.compile(r"^(?P<indent> {0,3})(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
# mermaid-cli 同时支持 :::mermaid ... ::: 这种指令式写法。
_DIRECTIVE_OPEN_RE = re.compile(r"^ {0,3}:{3,}\s*mermaid\s*$", re.IGNORECASE)
_DIRECTIVE_CLOSE_RE = re.compile(r"^ {0,3}:{3,}\s*$")


def _fence_info_lang(info: str) -> str:
    """取 info string 的首个 token 作为语言标记，兼容 ```mermaid title="x" 这类写法。"""
    stripped = info.strip()
    if not stripped:
        return ""
    return stripped.split()[0].lower()


def extract_mermaid_blocks(lines: list) -> tuple:
    """
    从 markdown 行序列中提取 mermaid 块，返回 (blocks, warnings)。

    这里必须跟踪**所有**围栏而不只是 mermaid 围栏：文档里用 ````markdown 包一段
    故意写坏的 mermaid 当反例是常见写法，只认 ```mermaid 会把它当成真实图表误报。
    只有处在最外层（不在任何围栏内）时，才会把 mermaid 围栏识别为待校验的块。
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
                line_start=open_line + 1,  # 内容从开围栏的下一行开始
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
                # 收尾围栏长度必须不短于开头，否则 ```` 块里的 ``` 会被误当成结束。
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
                # 按 CommonMark 规则剥掉与开头围栏等量的缩进。
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
            # CommonMark：反引号围栏的 info string 里不允许再出现反引号。
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

    # 未闭合的围栏无法确定作者本意的结束位置，只告警不猜测内容，避免产出误导性的语法错误。
    if in_fence and fence_is_mermaid:
        warnings.append(
            {
                "line": fence_open_line,
                "message": f"第 {fence_open_line} 行的 mermaid 代码块直到文件结尾都没有闭合，已跳过校验。",
            }
        )
    if in_directive:
        warnings.append(
            {
                "line": directive_open_line,
                "message": f"第 {directive_open_line} 行的 :::mermaid 块直到文件结尾都没有闭合，已跳过校验。",
            }
        )

    return blocks, warnings


def _strip_indent(raw_line: str, indent: int) -> str:
    """剥掉不超过 indent 个前导空格，保留其余缩进。"""
    stripped = 0
    position = 0
    while position < len(raw_line) and stripped < indent and raw_line[position] == " ":
        position += 1
        stripped += 1
    return raw_line[position:]


def _infer_diagram_type(content_lines: list) -> str:
    """从代码块首个非空行推断图表类型。"""
    for line in content_lines:
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        first = parts[0]
        # flowchart / graph 后面通常跟方向
        if first.lower() in ("graph", "flowchart") and len(parts) > 1:
            return f"{parts[0]} {parts[1]}"
        return first
    return "unknown"


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------

_ERROR_LINE_RE = re.compile(r"[Pp]arse error on line (\d+)")


def run_worker(payload: dict) -> dict:
    """调用 Node worker 完成实际渲染校验。"""

    worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), WORKER_NAME)
    if not os.path.isfile(worker):
        return {"status": "worker_error", "error": f"未找到 worker 脚本: {worker}", "results": []}

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as handle:
            json.dump(payload, handle)
            tmp_path = handle.name

        # worker 最坏情况是每块各占一轮，这里按同样量级放宽，避免外层先于 worker 超时，
        # 否则拿不到 worker 已经收集到的部分结果。
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
                "error": (result.stderr or "worker 无任何输出").strip(),
                "results": [],
            }
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {
                "status": "worker_error",
                "error": f"worker 输出不是合法 JSON: {stdout[:500]}",
                "results": [],
            }
    except subprocess.TimeoutExpired:
        return {"status": "worker_error", "error": "worker 整体超时", "results": []}
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _extract_error_line(message: str) -> Optional[int]:
    """从形如 'Parse error on line 5:' 的消息中提取块内相对行号。"""
    match = _ERROR_LINE_RE.search(message)
    return int(match.group(1)) if match else None


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def expand_targets(patterns: list) -> tuple:
    """把命令行参数展开成去重后的 markdown 文件列表，返回 (files, missing)。"""
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
        _emit({"status": "error", "error": f"用法: {sys.argv[0]} <markdown_file_or_glob> [more ...]"})
        sys.exit(2)

    targets, missing = expand_targets(sys.argv[1:])
    if missing and not targets:
        _emit({"status": "error", "error": f"未匹配到任何文件: {', '.join(missing)}"})
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
                "install_hints": ["找到了 mmdc 可执行文件，但无法定位其安装目录，请重装 @mermaid-js/mermaid-cli。"],
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
            reports.append(FileReport(path=path, warnings=[{"line": 0, "message": f"读取失败: {exc}"}]))
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
            _emit({"status": "error", "error": outcome.get("error", "worker 执行失败")})
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

            message = verdict.get("error", "未知错误")
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
                    # 直接给出源文件绝对行号，省得调用方再拿 line_start 换算一次。
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
    """输出 JSON 到 stdout。"""
    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
