# 报告数据契约

同一个 renderer 处理文字与视觉证据，所有正文按纯文本转义，不传 HTML 片段。图片传本地绝对路径，渲染器内嵌为 data URI；生成的 HTML 不依赖外部脚本、样式或图片。

## 公共字段

| 字段 | 含义 |
|---|---|
| `target` | 必填，被审目标路径或名称 |
| `title` | 报告标题，默认「审查报告」 |
| `mode` | `review`（默认）或 `fix`；表示是否实际修复 |
| `evidenceMode` | `visual`（默认）或 `text`；每个 pages 条目可单独覆盖，支持混合输入 |
| `status` | 可省略；`clean/reviewed/fixed/incomplete`。脚本根据覆盖与待修项保守计算，不能用声明覆盖缺口 |
| `pageCount` | 实际检查单元总数：视觉页/状态数或文本文件/片段数 |
| `pages` | 非空检查单元列表，`id` 唯一；缺截图的单元仍保留以记录未覆盖范围 |
| `findings` | 问题列表；无发现填 `[]` |
| `context` | 背景键值表，如模式、受众、疑问、决策、输入版本、技能版本、执行线程；折叠展示 |
| `contract` | PPT 既有版面契约键值表，与 context 合并展示 |
| `showCoverage` | 默认 false；true 时展示紧凑检查记录表，不嵌入逐页全景图 |
| `fixedCopy` | 实际改后全文，仅 mode=fix 使用 |
| `suggestedCopy` | 可选，完整建议稿，明确标记尚未执行 |
| `limits` | 缺图、不可辨认区域、未验证状态等；非空时不能报告为完成 |
| `pending/commands/kept` | 可保留本地过程记录，不展开进 HTML；pending 非空仍阻止 clean/fixed。需用户处理的待办也写入对应 finding |

`pages[]`：`id`、`title` 或 `where`、`review.before`（真实观察；文字模式含文件用途及覆盖行号）。视觉模式另填 `before` 截图路径、`review.interaction`（实操结果或不适用理由）；修复模式填 `review.after`，视觉另填 `after` 截图。`beforeRuler/afterRuler` 可保留本地，不嵌入报告。纯文本不需要图片或 interaction。观察缺失降为覆盖不足；被引用的图片缺失会使 HTML 生成失败，保留旧报告。

## 问题字段

| 字段 | 含义 |
|---|---|
| `id/title/severity` | 稳定 ID、标题、`blocking/should/optional` |
| `category` | `visual`（默认）或 `content`，由审查者判断，不从 kind 猜测 |
| `page/where` | 检查单元 ID、代码行号/画面区域/运行时来源 |
| `kind/action` | 可选，问题类型及保留/改写/降级/删除等建议动作 |
| `changeSummary/short` | 一句话核心变化/问题说明，前者优先 |
| `why/audienceReason` | 影响、判定理由及受众依据 |
| `fix` | 完整建议或实际修复说明；说明是否已执行 |
| `resolution` | `open`（默认）/`fixed`/`kept`；fixed 有实际 fix，kept 有 resolutionReason |
| `resolutionReason` | 采纳、修正或拒绝的原因 |
| `textComparison` | 已修文字项用 `{ "before": "原文", "after": "实际改后原文" }`；未执行项用 `{ "before": "原文", "suggested": "完整替换建议" }`。删除后的 after 可为空字符串 |
| `annotatedImg` | 已画红框的真实局部图，适合只读 spec-leak finding；渲染器直接内嵌，不再二次画框 |
| `img/box/boxPct/label` | 已修项的原始证据图与红框。box 为该图像素 `[x,y,w,h]`，boxPct 为百分比；label 是短标签 |
| `beforeImg/afterImg` | 实际修复前后图；省略时回落到关联页的 before/after，仅 fixed 项显示滑块 |
| `before/after` | 可选，现状与复验结果的文字说明，不是图片路径 |

HTML 的采纳/讨论/驳回是审阅反馈，不会把 `resolution` 改为已修复。只有上游实际修改并复验后才能写 fixed。

## PPT 映射

已有 `findings.json` 继续使用上述 pages、category 和截图字段，设 `title: PPT 版式视觉验收`，默认 `evidenceMode: visual`，不设 showCoverage。过程记录留在 JSON；已修问题的说明与滑动对照放在同一张卡里。

## spec-leak 映射与文字示例

默认直接修复后用 `mode: fix`，填写真实 `textComparison.after`、`review.after`，视觉修复另填 after 截图；复验通过的项设 fixed，未解决的项仍为 open。需要展示实际改后全文时用 fixedCopy。以下例子演示用户明确要求只读时的未执行建议。

```json
{
  "target": "instructions.md",
  "title": "内容审查",
  "mode": "review",
  "evidenceMode": "text",
  "pageCount": 1,
  "context": {"模式": "文本", "受众": "维护者", "决策": "如何执行长期规范", "输入版本": "实际版本或哈希"},
  "showCoverage": true,
  "pages": [{"id": "file1", "where": "instructions.md:1-20", "review": {"before": "已读 1–20 行，发现一次性会话开场，其余为长期操作规范。"}}],
  "findings": [{
    "id": "F1", "severity": "should", "category": "content", "page": "file1",
    "title": "一次性会话开场进入长期规范", "kind": "提示词残留", "action": "删除",
    "changeSummary": "[删除] 面向本次对话的开场白", "where": "instructions.md:1",
    "why": "开场白不承担操作规则。", "audienceReason": "维护者需要可长期执行的步骤。",
    "textComparison": {"before": "好的，下面帮你完成本次修改。", "suggested": "删除，不替换。"},
    "fix": "建议删除该句，尚未执行。", "resolution": "open"
  }],
  "suggestedCopy": "填写删改后的完整建议稿，仍未执行。"
}
```

spec-leak 视觉模式改为 `evidenceMode: visual`，pages 填真实截图和交互观察；finding 的 `annotatedImg` 填采集标注脚本返回的局部图绝对路径。保留原图、DOM/位图盘点、逐页覆盖等原始产物。报告通过背景与紧凑表展示结论依据，不复制全部证据文件。
