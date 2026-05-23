# Mermaid 嵌入安全规范

单文件 HTML 通过 CDN 加载 Mermaid 时，错误配置或 diagram 语法可能打开 **HTML 注入 / 脚本执行** 路径。本规范与 monorepo 内 `light-harness/scripts/security/check_mermaid_insecure_config.py`（pre-commit hook `check-mermaid-insecure-config`）对齐；生成或修改含 Mermaid 的 HTML 后**必须**通过该检查。

## 必须使用的 `mermaid.initialize` 配置

`securityLevel` 与 `htmlLabels` 是硬性要求，不可省略或弱化：

```javascript
mermaid.initialize({
  startOnLoad: true,
  securityLevel: 'sandbox', // 或 'strict'；禁止 'loose' / 'antiscript'
  htmlLabels: false,
  theme: 'base',
  themeVariables: {
    fontFamily: 'system-ui, -apple-system, sans-serif',
    fontSize: '14px',
    primaryColor: '#FAF9F5',
    primaryTextColor: '#141413',
    primaryBorderColor: '#D1CFC5',
    lineColor: '#87867F',
    secondaryColor: '#E3DACC',
    tertiaryColor: '#fff'
  },
  flowchart: { useMaxWidth: true, htmlLabels: false, curve: 'basis' }
});
```

| 选项 | 要求 | 原因 |
|------|------|------|
| `securityLevel` | `'strict'` 或 `'sandbox'` | 限制 diagram 内可执行内容与 HTML 标签 |
| `htmlLabels` | `false`（全局与 `flowchart` 内均禁止 `true`） | 避免节点标签走 HTML 渲染路径 |
| `secure` | 不要写 `secure: []` | 空 allowlist 会覆盖默认安全列表 |

参考实现：`light-harness/frontend/src/lib/mermaid-config.ts`。

## Diagram 源码禁止项

在 `<pre class="mermaid">` 或 fenced mermaid 块中**不要**使用：

| 禁止 | 示例 | 替代 |
|------|------|------|
| `click` 回调 | `click A callback` / `click A call fn()` | 节点说明放图下文字或侧栏；交互用页面自己的 JS |
| `javascript:` 链接 | `click A "javascript:..."` | `https://` 普通链接，或不用 `click` |
| 弱安全 init | `%%{init: {'theme':'base'}}%%` 且未设 `securityLevel` | 在 init 中显式写 `securityLevel: 'strict'` 或 `'sandbox'`，或删掉 init、只用页面级 `initialize` |
| 弱 securityLevel | `securityLevel: 'loose'` / `'antiscript'` | 仅用 `strict` / `sandbox` |

若必须使用 `%%{init: ...}%%`，块内必须包含可识别的 `securityLevel: 'strict'` 或 `'sandbox'`（与 gate 正则一致）。

## 推荐写法

- 节点标签用纯文本或 `["带引号的标签"]`，避免 HTML 片段。
- 架构说明、点击详情放在 Mermaid 图下方的列表或侧栏，不要用 Mermaid `click` 绑页面回调。
- 将 `mermaid.initialize({...})` 集中写在页面底部单一 `<script>` 中，便于 gate 扫描。
- CDN 使用固定主版本（如 `mermaid@11`），与项目其它页面保持一致。

## 发布前 Gate 检查（强制）

完整 Gate 顺序：**安全配置 → 语法预检 → Playwright 浏览器渲染**。

### Gate 1: 安全配置检查

对生成的 `.html`（及同目录相关文件）运行 skill 自带检查脚本：

```bash
python3 .agents/skills/tech-doc-html/scripts/security/check_mermaid_insecure_config.py path/to/output.html
```

或在 monorepo 根目录使用 light-harness 同源脚本：

```bash
python3 light-harness/scripts/security/check_mermaid_insecure_config.py path/to/output.html
```

退出码 `0` 方可视为通过；`1` 时按输出中的 `[RULE_CODE]` 逐条修复。

### Gate 2: 语法预检（新增）

安全门通过后，用 `mermaid.parse()` API 验证 diagram 源码语法：

```bash
node .agents/skills/tech-doc-html/scripts/security/check_mermaid_syntax.mjs <project-root> path/to/output.html
```

`<project-root>` 是包含 `node_modules/mermaid` 和 `node_modules/jsdom` 的项目根目录。脚本在该项目下解析 `mermaid` 和 `jsdom` 依赖。

退出码 `0` 表示所有 `<pre class="mermaid">` 块语法正确；`1` 时输出 `[MERMAID_SYNTAX]` 错误行号和 parse 错误信息。

**常见语法问题：**
| 错误表现 | 根因 | 修复 |
|---------|------|------|
| `Parse error on line N` | 节点 ID 含空格或特殊字符 | 用 `["带引号的标签"]` |
| `Lexical error` | `<br/>` 等 HTML 标签在纯文本节点中 | 去掉 `<br/>`，用换行分多行 |
| `Expecting 'EOF'` | 花括号 `{}` 或方括号 `[]` 未闭合 | 检查菱形节点 `{label}` 是否成对 |
| `&dollar;` 在浏览器中解析失败 | HTML 实体编码 | 在 `<pre>` 中直接写 `$` 或 `${...}`，不要用实体 |

### Gate 3: 浏览器渲染验证

语法预检通过后，Playwright 验证渲染 + 交互（见 QA 流程）。

### Gate 规则一览（与 pre-commit 一致）

| 规则 ID | 检测内容 |
|---------|----------|
| `MERMAID_SECURITY_LEVEL_REQUIRED` | `mermaid.initialize` / `%%{init}` 未显式设置 `securityLevel: strict\|sandbox` |
| `MERMAID_HTML_LABELS_TRUE` | `htmlLabels: true` |
| `MERMAID_SECURITY_LEVEL_LOOSE` | `securityLevel: loose\|antiscript` |
| `MERMAID_CLICK_CALLBACK` | `click <id> <callback>` |
| `MERMAID_CLICK_JAVASCRIPT_URL` | `click` 中含 `javascript:` URL |
| `MERMAID_SECURE_OVERRIDE_EMPTY` | `secure: []` |

## 与 QA 流程的关系

Playwright 只验证「图能画出来」；**不能**替代安全配置 gate。完整 QA 顺序：

1. `check_mermaid_insecure_config.py` → 0 退出码  
2. Playwright console 0 errors + `.mermaid svg` 存在  

两者都通过才可发布 HTML。
