---
name: tech-doc-html
description: 将技术方案文档生成为生动、交互式、易于理解的单文件 HTML 可视化页面。当用户提到生成技术方案 HTML、绘制架构图 HTML、创建交互式技术文档、将设计文档可视化为网页时触发此 skill。This skill should be used when the user wants to create interactive HTML visualizations of technical designs, architecture diagrams, or implementation plans.
---

# 技术方案 HTML 可视化

将技术方案内容转化为生动、交互式的单文件 HTML 页面，帮助读者快速理解系统设计。

## 核心原则

1. **交互优先** — 不是静态文档的美化，而是通过交互让读者"动手玩"技术概念
2. **单文件可打开** — CSS/JS 内嵌；复杂图表可通过 CDN 引入 Mermaid（见下方图表选型与安全配置）
3. **服务理解** — 每个交互/动态效果都必须服务于"帮助理解"这个目标

## 工作流程

### Step 1: 分析技术方案内容

阅读用户提供的技术方案文档，识别其中的信息类型：
- 系统架构 / 组件关系
- 算法或原理解释
- 多方案对比
- 数据流 / 请求链路
- 实现步骤 / 里程碑
- 风险评估
- 关键指标 / 性能数据
- 术语密集的概念说明

### Step 2: 选择可视化 + 交互组件

根据信息类型，为每块内容选择最合适的组件和交互方式：

| 信息类型 | 推荐组件 | 交互方式 |
|----------|----------|----------|
| 系统架构图 / 部署 / 时序 / 状态机 | **Mermaid**（优先） | 静态图；节点详情放侧栏文字 |
| 复杂数据流 / 多分支流程 | **Mermaid** flowchart | 同上 |
| 少量节点 + 必须点击看图 | SVG 流程图 + 侧栏（§8） | 点击节点查看详情 |
| 算法/原理 | 交互式 SVG 图解（§9） | 滑块调参实时渲染 |
| 方案对比 | 对比表格 | good/bad 着色 + hover 高亮 |
| 实现步骤 | 时间线/里程碑 | 折叠展开代码段 |
| 简单链路动画点缀 | SVG 线段（§11） | 虚线 CSS 流动动画 |
| 风险评估 | 风险矩阵表 | 严重等级色标 (HIGH/MED/LOW) |
| 关键指标 | Summary 指标条 | 顶部一览 |
| 术语解释 | Sticky 术语表侧栏 | Hover 联动高亮 |
| 多视角说明 | Tab 切换面板 | 点击切换不同视图 |
| 流程演示 | 步骤高亮 | 点击"下一步"逐步高亮 |

### Step 3: 加载 Mermaid 安全规范（含 Mermaid 时强制）

若输出含 Mermaid，**先**读取 `references/mermaid_security.md`，再写任何 `mermaid.initialize` 或 diagram 源码。要求与 light-harness pre-commit gate（`check_mermaid_insecure_config.py`）一致：

- `securityLevel: 'sandbox'` 或 `'strict'`
- `htmlLabels: false`（含 `flowchart.htmlLabels`）
- diagram 中禁止 `click` 回调、`javascript:` URL、弱 `%%{init}%%`

### Step 4: 加载设计规范

读取 `references/design_system.md` 获取：
- CSS 变量（色彩/字体/间距）
- 页面骨架 HTML
- 排版层级
- 响应式断点

### 图表选型（简）

- **默认用 Mermaid** 画架构、部署、时序、状态、ER、节点较多的 flowchart——不要手写复杂 SVG
- **仅当**需要「点击图中节点 → 侧栏切换详情」且节点 ≤5 时，用手写 SVG 模板（`component_patterns.md` §8）
- **滑块调参、动态柱状图** 仍用 §9 的 JS + SVG

### Step 5: 加载组件模板

读取 `references/component_patterns.md` 获取选定组件的完整 HTML + CSS + JS 代码模板（§7 Mermaid 已含安全 `initialize` 模板）。

### Step 6: 组装输出

将组件组合为完整的单文件 HTML，确保：
- 所有样式在一个 `<style>` 块中
- 所有脚本在一个 `<script>` 块中（放在 body 末尾）
- 复杂关系图用 Mermaid（CDN + 安全 `mermaid.initialize`）；简单交互图 SVG 内嵌
- 响应式适配移动端

## 页面结构模板

标准技术方案 HTML 的推荐 section 组织：

```
1. Header    — 标题 + eyebrow 类型标签 + 一句话摘要
2. Summary   — 4 格关键数字指标条（如：预计工时、涉及服务数...）
3. 架构/概览 — Mermaid 系统图（核心，占最大视觉面积）
4. 原理图解  — 交互式概念解释（滑块/按钮让用户探索）
5. 方案对比  — 表格，good/bad 着色
6. 实现计划  — 时间线 + 里程碑 + 折叠代码
7. 风险矩阵  — HIGH/MED/LOW 色标
8. 开放问题  — 待决策项（可选）
```

不是每个方案都需要全部 section，根据内容取舍。

## 交互设计决策指南

### 何时使用交互

- **概念有参数可调** → 用滑块（如：缓存大小、节点数量、超时时间）
- **系统有多个组件** → 用 Mermaid 架构图；仅少数节点需点击详情时用 SVG 可点击流程图（§8）
- **有步骤/时序** → 用"下一步"按钮逐步高亮
- **有大段代码** → 用折叠，默认只展示关键几行
- **有多方案选择** → 用 Tab 切换

### 何时不使用交互

- 信息量少、一段话能说清 → 纯文本
- 对比项只有 2-3 个 → 简单表格即可，不需要额外 JS
- 流程只有 3 步以内 → 静态图即可

## 输出质量检查

生成的 HTML 必须满足：
1. 浏览器直接打开可用（允许 Mermaid CDN；离线场景需说明需联网）
2. 所有交互有 hover 态反馈（cursor: pointer, border 变化等）
3. 字体风格统一：除 `code` / `pre` / 代码面板内容外，全部使用 `--sans`
4. 移动端可用（至少单列 fallback）
5. Mermaid 容器可横向滚动；手写 SVG 用 viewBox 确保缩放
6. 代码面板暗底 + 语法高亮
7. 页面 max-width 控制在 1100px 以内
8. **Mermaid 安全 gate 通过**（见下）

### Mermaid 安全 gate（含 Mermaid 时强制）

组装完成后、Playwright 之前运行：

```bash
python3 .agents/skills/tech-doc-html/scripts/security/check_mermaid_insecure_config.py path/to/output.html
```

退出码必须为 `0`。规则详情见 `references/mermaid_security.md`（与 light-harness `.pre-commit-config.yaml` → `check-mermaid-insecure-config` 同源）。

## QA 验证 — 无头浏览器检查（强制）

Mermaid gate 通过后，生成 HTML **必须**再通过 Playwright MCP 验证，确保交互逻辑没有 JS 错误。

### 验证步骤

**Step 1: 初始化 Playwright MCP**
```bash
node <skill-path>/setup.js
```

**Step 2: 导航到页面**
```bash
mcporter call playwright.browser_navigate url=file:///path/to/output.html
```

**Step 3: Console 错误检查**
```bash
mcporter call playwright.browser_console_messages
```
- 必须 **0 errors**。任何 SyntaxError / ReferenceError 都意味着 JS 未执行，所有交互失效。
- Mermaid 语法错误会在 console 出现，需修正 diagram 源码后重跑。
- 常见根因：HTML 字符串中的未转义引号（如 `"review 这个 MR"` 导致 `"` 截断字符串）。

**Step 4: 关键变量存在性检查**
```bash
mcporter call playwright.browser_evaluate function="()=>({
  FLOW_DETAIL: typeof FLOW_DETAIL !== 'undefined',
  hasNodes: document.querySelectorAll('.node').length > 0,
  hasSteps: document.querySelectorAll('.step-node').length > 0
})"
```
- 如果关键变量为 `false`，说明 JS block 被浏览器放弃执行 → 回到 Step 3 排查语法错误。

**Step 5: 交互功能测试**

| 交互类型 | 测试命令 | 通过标准 |
|---------|---------|---------|
| SVG 节点点击 | `browser_evaluate` 调用 `dispatchEvent('click')` | 面板标题变为对应节点名称 |
| 步骤按钮 | `browser_evaluate` 调用 `btn.click()` | `stepInfo` 从 "步骤 1/N" 变为 "步骤 2/N" |
| Tab 切换 | `browser_evaluate` 调用 `tab.click()` | `activeTab` 变为目标 tab 文本 |
| Mermaid 渲染 | `browser_evaluate` 检查 `.mermaid svg` 存在 | 至少 1 个 SVG 子节点；无 mermaid parse error |
| 术语表 hover | `browser_evaluate` 调用 `mouseenter` / `mouseleave` | `dt.hl` 类正确添加/移除 |

**Step 6: 截图确认**
```bash
mcporter call playwright.browser_take_screenshot type=png filename=screenshots/qa-check.png
```
- 截图保存到当前工作目录 `screenshots/` 目录下，作为验证凭证。

### 常见失败模式

| 现象 | 根因 | 修复 |
|------|------|------|
| Console 报 `SyntaxError` | JS 字符串中的 `"` 未转义 | 将内层引号改为 `'` 或转义为 `\"` |
| 变量 `undefined` | `<script>` 标签之前的 HTML 有语法错误导致整段放弃 | 检查 HTML 实体编码（如 `=&gt;` 应为 `=>`） |
| 按钮点击无反应 | `addEventListener` 未绑定（JS 未执行） | 同左，修复 SyntaxError 后重试 |
| Tab 切换无变化 | CSS 类 `.active` 未正确切换 | 检查 JS 逻辑，确保 classList 操作正确 |

### 铁律

- **Mermaid gate 未通过 = 页面不可发布**，即使浏览器里图能正常显示。
- **Console 有 error = 页面不可用**，无论视觉上看起来多正常。
- **必须修复所有 JS 错误后再发布**，不要心存侥幸。
- **截图是验证凭证**，QA 完成后保留截图以便追溯。

## 参考示例

`assets/example_output.html` 提供了一个完整的缓存系统设计方案的 HTML 输出，包含交互式架构图、滑块演示、方案对比等，可作为输出质量的参照基准。
