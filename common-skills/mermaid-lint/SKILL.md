---
name: mermaid-lint
description: 验证并修复 markdown 文件中 mermaid 图表的语法错误，支持单文件、多文件和整个目录。当用户编辑了包含 mermaid 图的 markdown，或要求检查/修复 mermaid 语法时使用。
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion, AskQuestion
---

# Mermaid Lint

验证 markdown 文件中所有 mermaid 图表的语法正确性，定位错误并自动修复。

**输入**: 一个或多个 markdown 文件路径、glob 或目录。若用户未提供，搜索当前目录下的 `.md` 文件并询问用户要检查哪些。

## 校验方式

脚本把每个 mermaid 块喂给真实的 mermaid 渲染器（无头浏览器里的 `mermaid.render`），能渲染出来才算通过。

不要改成 `mermaid.parse`。`parse` 只覆盖解析阶段，渲染和布局阶段抛出的错误它看不到——例如 gantt 里的非法日期 `notadate` 能通过 `parse` 却渲染失败。用户真正关心的是"这张图在文档里能不能显示"，只有渲染器能回答。

整批图表共用一个浏览器会话，因此校验 60 个图表和校验 1 个图表的耗时都在 2 秒量级，可以放心一次性扫整个目录。

---

## 第〇步：依赖检测

先跑一次验证脚本，若输出 JSON 中 `status` 为 `"missing_dependency"`，按 `install_hints` 处理。

```bash
python {baseDirectory}/validate-mermaid.py "<markdown_file>"
```

**不要自作主张安装依赖。** 缺依赖时把 `missing` 和 `install_hints` 展示给用户，询问下一步，提供这些选项：

- 用 `npx -p @mermaid-js/mermaid-cli mmdc` 临时运行，不往全局装东西
- 由用户自行安装后重试
- 取消操作

只有用户明确同意后才执行安装命令。全局 `npm install -g` 会影响用户机器上所有项目，必须由用户拍板。

---

## 第一步：运行验证

```bash
# 单文件
python {baseDirectory}/validate-mermaid.py "docs/architecture.md"

# 多文件 / glob / 整个目录（目录会递归匹配 *.md）
python {baseDirectory}/validate-mermaid.py "docs/**/*.md"
python {baseDirectory}/validate-mermaid.py docs/
```

脚本输出 JSON 到 stdout。退出码：`0` 全部通过，`1` 存在语法错误，`2` 用法错误或依赖缺失。

### 输出结构

```json
{
  "status": "error",
  "summary": {
    "files": 2,
    "total_blocks": 7,
    "valid_blocks": 6,
    "error_blocks": 1,
    "warnings": 1,
    "unmatched_patterns": []
  },
  "files": [
    {
      "file": "/abs/path/architecture.md",
      "total_blocks": 5,
      "valid_blocks": 4,
      "errors": [
        {
          "block_index": 2,
          "line_start": 45,
          "line_end": 58,
          "diagram_type": "graph TD",
          "mermaid_source": "graph TD\n    A[Start --> B[End]",
          "error_message": "Parse error on line 2: ...",
          "error_line_in_block": 2,
          "error_line_in_file": 46,
          "timed_out": false
        }
      ],
      "warnings": [
        { "line": 88, "message": "第 88 行的 mermaid 代码块直到文件结尾都没有闭合，已跳过校验。" }
      ],
      "blocks": [
        { "index": 1, "line_start": 20, "line_end": 35, "diagram_type": "graph TD", "valid": true }
      ]
    }
  ]
}
```

`error_line_in_file` 已经是源文件里的绝对行号，直接用它定位，不要再拿 `line_start` 换算。

`warnings` 不会让退出码变成 1，但同样需要处理并报告给用户——未闭合的代码块本身就是文档缺陷。

`timed_out` 为 `true` 表示该块渲染超时或渲染进程崩溃，不一定是语法错误，通常是图表过大。这类块要提示用户人工确认，不要当成语法问题去"修"。

---

## 第二步：修复错误

对每个文件 `errors` 数组中的每一项：

1. **读取源文件**，定位 `line_start` 到 `line_end` 之间的 mermaid 块。
2. **分析 `error_message` 和 `mermaid_source`**，理解语法问题的根因。
3. **用 Edit 工具直接修复对应的 mermaid 块**。只改有问题的部分，不动其他内容。

### 常见错误模式速查

| 错误信息关键词 | 常见原因 | 修复方向 |
|---|---|---|
| `Expecting 'SQE'` | `[` 未闭合 | 补上 `]` |
| `Expecting 'PE'` | `(` 未闭合 | 补上 `)` |
| `Expecting 'DIAMOND_STOP'` | `{` 未闭合 | 补上 `}` |
| `Unexpected token` | 使用了非法字符或关键字 | 检查是否有特殊字符需要用引号包裹 |
| `Lexer error` / `Lexical error` | 非法字符 | 删除或转义特殊字符 |
| `Parse error on line N` | 块内第 N 行语法错误 | 用 `error_line_in_file` 定位源文件行 |
| `Invalid date:...` | gantt 日期不符合 `dateFormat` | 改成符合声明格式的日期 |
| `Trying to inactivate an inactive participant` | sequenceDiagram 的 activate/deactivate 不配对 | 补齐或删除多余的 `deactivate` |
| `Negative values are not allowed` | pie 图出现负数 | 改成非负数值 |
| `Edge limit exceeded` | 图表边数超出 mermaid 上限 | 拆分成多张图 |

### 修复原则

- **最小修改**：只修正语法错误，不重写、不重排正确的图表。
- **保留语义**：修复后的图表应尽量保持原作者想表达的结构。
- **不确定时询问**：如果无法确定原意（比如缺失的节点名称），询问用户而不是猜测。

---

## 第三步：重新验证

修复完成后，**必须重新运行验证脚本**：

```bash
python {baseDirectory}/validate-mermaid.py "<same_targets>"
```

- 若全部通过：报告完成。
- 若仍有错误：继续修复，循环此流程。
- 若同一个块连续 3 次修复失败：停止自动修复，将该块的源码和错误信息完整展示给用户，请求人工介入。

---

## 输出格式

验证过程中向用户展示进度：

```
## Mermaid Lint: docs/ (2 个文件)

检查到 7 个 mermaid 图表

  architecture.md
    Block 1 (行 20-35): graph TD — 通过
    Block 3 (行 70-85): classDiagram — 语法错误
      行 74: 未闭合的方括号
    警告 行 88: mermaid 代码块未闭合，已跳过

  design.md
    Block 1 (行 12-24): sequenceDiagram — 通过

正在修复 architecture.md Block 3 ...
[修复完成，重新验证]

全部 7 个 mermaid 图表验证通过，1 处警告待人工确认。
```

---

## 环境变量

正常使用不需要设置，仅用于排查问题：

- `MERMAID_LINT_BLOCK_TIMEOUT_MS`：单个图表的渲染超时，默认 `20000`。
- `MERMAID_LINT_SESSION_OVERHEAD_MS`：单轮会话里浏览器启动等固定开销的预算，默认 `15000`。冷启动很慢的机器可以调高。

---

## 使用示例

```
用户: /mermaid-lint docs/architecture.md
用户: 帮我检查这个 markdown 里的 mermaid 图有没有语法问题
用户: 把 docs 目录下所有文档的 mermaid 图都验一遍
用户: 修一下 docs/design.md 里的 mermaid 报错
```
