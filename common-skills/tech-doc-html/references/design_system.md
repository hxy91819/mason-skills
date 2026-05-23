# 设计系统规范

从 html-effectiveness 仓库提炼的完整设计系统，可直接复制代码到 HTML 文件中使用。

## CSS 变量

```css
:root {
  /* 色彩 */
  --ivory:    #FAF9F5;   /* 页面背景（暖奶白） */
  --slate:    #141413;   /* 主文字/强调色 */
  --clay:     #D97757;   /* 高亮/告警/CTA（暖锈橙） */
  --olive:    #788C5D;   /* 成功/确认（柔绿） */
  --oat:      #E3DACC;   /* 次要强调/徽章（暖米色） */
  --sky:      #6A8CAF;   /* 信息/链接（蓝灰） */
  --rust:     #B04A3F;   /* 严重告警/删除（深红） */

  /* 灰阶 */
  --gray-100: #F0EEE6;
  --gray-150: #F0EEE6;
  --gray-300: #D1CFC5;
  --gray-500: #87867F;
  --gray-700: #3D3D3A;

  /* 字体：除代码外统一使用非衬线字体 */
  --sans:  system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --mono:  ui-monospace, "SF Mono", Menlo, Monaco, Consolas, monospace;
}
```

## 色彩语义

| 色彩变量 | 用途 |
|----------|------|
| `--clay` | 高亮重点、警告标识、CTA 按钮、active 边框 |
| `--olive` | 成功状态、已完成标记、正面指标 |
| `--oat` | 徽章背景、次要按钮、hover 背景 |
| `--rust` | 严重告警、失败路径、删除操作 |
| `--sky` | 信息标识、辅助链接色 |
| `--slate` | 主文字、强调标题、代码面板背景 |
| `--gray-500` | 次要文字、边框、箭头 |

## 排版层级

```css
/* 页面标题 */
h1 {
  font-family: var(--sans);
  font-weight: 650;
  font-size: 34px;
  line-height: 1.15;
  color: var(--slate);
  letter-spacing: -0.01em;
  margin-bottom: 16px;
}

/* 章节标题 */
h2 {
  font-family: var(--sans);
  font-weight: 650;
  font-size: 24px;
  color: var(--slate);
  letter-spacing: -0.01em;
  margin: 40px 0 12px;
}

/* 小节标题 */
h3 {
  font-family: var(--sans);
  font-weight: 650;
  font-size: 19px;
  color: var(--slate);
  margin-bottom: 6px;
}

/* 正文 */
body, p {
  font-family: var(--sans);
  font-size: 15px;
  line-height: 1.6;
  color: var(--gray-700);
}

/* Eyebrow 标签（章节类型标识） */
.eyebrow {
  font-family: var(--sans);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--gray-500);
  margin-bottom: 10px;
}

/* 单等宽标签 */
.label {
  font-family: var(--sans);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--gray-500);
}

/* 内联代码 */
code {
  font-family: var(--mono);
  font-size: 13px;
  background: var(--gray-100);
  padding: 1.5px 5px;
  border-radius: 4px;
}
```

## 间距系统

| 用途 | 尺寸 |
|------|------|
| 最小间隙 | 8px |
| 元素内间距 | 12px |
| 卡片内 padding | 16-20px |
| section 间距 | 48-64px |
| 页面顶部 padding | 56px |
| 页面底部 padding | 120px |
| max-width | 1100px |

## 圆角规范

| 元素类型 | 圆角 |
|----------|------|
| 小按钮/chip | 6-8px |
| 面板/卡片 | 12-14px |
| 代码面板 | 12px |
| 胶囊按钮 | 999px |

## 边框规范

```css
/* 标准边框 */
border: 1.5px solid var(--gray-300);

/* 强调边框（hover/active） */
border: 2px solid var(--clay);

/* 面板边框 */
border: 1.5px solid var(--gray-300);
border-radius: 14px;
```

## 阴影

仅在 hover 状态使用，保持克制：
```css
/* 卡片 hover */
box-shadow: 0 10px 30px rgba(20, 20, 19, 0.10);
```

## 响应式断点

```css
@media (max-width: 960px) {
  /* 两栏→单栏 */
  .page { grid-template-columns: 1fr; }
}
@media (max-width: 760px) {
  /* 双列网格→单列 */
  .grid { grid-template-columns: 1fr; }
}
```

## 页面骨架

```html
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>技术方案标题</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<style>
  :root { /* 粘贴上方 CSS 变量 */ }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--ivory);
    color: var(--gray-700);
    font-family: var(--sans);
    font-size: 15px;
    line-height: 1.6;
    padding: 56px 24px 120px;
    -webkit-font-smoothing: antialiased;
  }
  .page {
    max-width: 1100px;
    margin: 0 auto;
  }
</style>
</head>
<body>
<div class="page">
  <!-- Header -->
  <header>
    <div class="eyebrow">技术方案 · 类型标签</div>
    <h1>方案标题</h1>
    <p class="lead">一句话摘要...</p>
  </header>

  <!-- 内容 sections -->
</div>

<script>
  mermaid.initialize({
    startOnLoad: true,
    securityLevel: 'sandbox',
    htmlLabels: false,
    theme: 'base',
    themeVariables: {
      fontFamily: 'system-ui, sans-serif',
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
  // 其他交互逻辑
</script>
</body>
</html>
```

## Mermaid 图表规范

复杂架构/流程/时序图优先用 Mermaid，不要手写大段 SVG。嵌入时必须遵循 `references/mermaid_security.md`（`securityLevel` + `htmlLabels: false` + gate 检查）。

```css
.diagram {
  background: #fff;
  border: 1.5px solid var(--gray-300);
  border-radius: 14px;
  padding: 24px;
  overflow-x: auto;
}
.mermaid {
  display: flex;
  justify-content: center;
  min-height: 120px;
}
.mermaid svg {
  max-width: 100%;
  height: auto;
}
```

常用 diagram 类型：`flowchart TB/LR`、`sequenceDiagram`、`stateDiagram-v2`、`erDiagram`。

## SVG 图表规范

以下适用于**少量节点**的可点击图、滑块调参图、简单流动动画——复杂关系图请用上文 Mermaid。

```css
/* 图表容器 */
.diagram {
  background: #fff;
  border: 1.5px solid var(--gray-300);
  border-radius: 14px;
  padding: 24px;
  overflow-x: auto;
}

/* SVG 基础 */
svg { display: block; width: 100%; height: auto; }
svg text { font-family: var(--sans); font-size: 12px; fill: var(--slate); }
svg .sub  { font-size: 10px; fill: var(--gray-500); }
```

SVG 箭头标记定义：
```html
<defs>
  <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"
          markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 z" fill="#87867F"/>
  </marker>
  <marker id="arrow-clay" viewBox="0 0 10 10" refX="9" refY="5"
          markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M0,0 L10,5 L0,10 z" fill="#D97757"/>
  </marker>
</defs>
```

## 代码面板规范

```css
.code {
  background: var(--slate);
  border-radius: 12px;
  padding: 18px 20px;
  overflow-x: auto;
}
.code pre {
  font-family: var(--mono);
  font-size: 12.5px;
  line-height: 1.65;
  color: #E8E6DE;
  white-space: pre;
}
/* 语法高亮 */
.code .kw  { color: var(--clay); }      /* 关键字 */
.code .str { color: var(--olive); }     /* 字符串 */
.code .cm  { color: var(--gray-500); }  /* 注释 */
.code .fn  { color: #C9B98A; }          /* 函数名 */
```

## 交互基础规范

```css
/* 可交互元素通用 hover */
.interactive {
  cursor: pointer;
  transition: transform 150ms ease, border-color 150ms ease;
}
.interactive:hover {
  transform: translateY(-1px);
  border-color: var(--slate);
}

/* Active 状态（被选中的节点） */
.active {
  border-color: var(--clay);
  border-width: 2px;
}

/* 滑块统一风格 */
input[type=range] {
  accent-color: var(--clay);
}

/* 按钮通用样式 */
button {
  appearance: none;
  border: 1.5px solid var(--gray-300);
  background: var(--gray-100);
  border-radius: 6px;
  font-family: var(--sans);
  font-size: 11px;
  padding: 6px 10px;
  cursor: pointer;
}
button:hover {
  background: var(--oat);
}
```
