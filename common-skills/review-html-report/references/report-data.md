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
| `pageCompare` | 默认 false；true 时新增「整体前后对照」：逐页用 `pages[].before/after` 真实截图出滑块，只展开有像素变化的页，无变化页只列 id。需要 `mode: fix`，每个视觉页都要有 after |
| `metrics` | 可选，`[{"name": "箭头线索", "before": 5, "after": 0}]`，在整体对照顶部渲染改前/改后指标表；数值由上游从真实记录统计 |
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
| `beforeBox/afterBox` | 各自对应 beforeImg/afterImg 的截图像素框 `[x,y,w,h]`；支持多框 `[[x,y,w,h], ...]`，带标签用 `{"box": [x,y,w,h], "label": "改动点"}`，可单独使用或混入多框数组。与现有 `.rbox` 同样式，滑块两层分别裁切，并排两图分别画框 |
| `lookHere` | 一句「看哪里」的提示，指出两框中的具体变化 |
| `steps` | 行为修补的有序操作序列，非空数组；每步为 `{title, beforeImg, afterImg, beforeBox, afterBox, lookHere}`。提供时替代 finding 级单组对照，步骤图片不回落页级，避免重复静态图冒充操作证据 |
| `before/after` | 可选，现状与复验结果的文字说明，不是图片路径 |

HTML 的采纳/讨论/驳回是审阅反馈，不会把 `resolution` 改为已修复。只有上游实际修改并复验后才能写 fixed。

## 前后图采集与标注

采集前由上游冻结修前／修后版本、代表数据（含角色与状态）、视口和滚动位置，等待字体与图片加载完成；在 `context` 记录版本／数据标识及采集条件。报告生成方核对这些信息，缺失时在 `limits` 标明不能支持的比较结论，不自行启动采集。

使用遮罩时，在 `limits` 明列遮掉的区域、内容及不支持的结论；涉及结论的遮罩区域另附同轮未遮罩证据或定向断言，不能用像素通过证明其中的文字、数值或对齐正确。

前后图必须同一画面、同视口、同滚动位置；以改动元素滚入视窗为锚，固定截图范围后分别采集。两张都画红框，并用 `lookHere` 说明框内发生什么变化；新增元素的 `beforeBox` 标在它应出现的位置。`box` 是原始证据图的旧字段，不能代替两张对照图各自的框。

`category: visual` 且视觉证据模式、`resolution: fixed` 的项，每组双图缺 `beforeBox` 或 `afterBox`（含无有效框）、或图片原始像素尺寸不同／无法读取，均记入 `limits`；报告状态为 incomplete，`--check` 输出具体 finding／步骤与原因，即使两张图片相同也检查。`--check` 保持现有退出码语义：一致性缺口在 JSON 中报告，图片读取失败仍退出非零。是否同画面与同滚动位置由采集者确认，尺寸检查不能证明这一点。

坐标建议由 Playwright 的 `locator.boundingBox()` 获取。它返回视口 CSS 像素；视口截图按截图像素与 CSS 视口比例缩放；整页截图的 y 还要加 `scrollY`；局部截图先减去裁切区域原点再缩放。以最终原图像素填写，不按报告内缩放后的图片重算。

```json
{
  "id": "V05", "page": "editor", "severity": "should", "category": "visual",
  "resolution": "fixed", "fix": "保存时正确处理另一账号登录后的状态",
  "steps": [
    {
      "title": "打开编辑页，再由另一账号登录后保存",
      "beforeImg": "/artifacts/save-before.png", "afterImg": "/artifacts/save-after.png",
      "beforeBox": {"box": [80, 160, 400, 100], "label": "保存报错"},
      "afterBox": [[80, 160, 400, 100], [500, 160, 120, 40]],
      "lookHere": "看保存结果：改前报错，改后显示保存成功。"
    }
  ]
}
```

行为修补按真实操作顺序添加多步，分别呈现打开编辑页、另一账号登录、保存结果等关键状态，每步都提供双图、双框和一句提示。静态最终页不能证明操作序列；准备尚未完成时保留上游未复验状态。

## PPT 映射

已有 `findings.json` 继续使用上述 pages、category 和截图字段，设 `title: PPT 版式视觉验收`，默认 `evidenceMode: visual`，不设 showCoverage。过程记录留在 JSON；已修问题的说明与滑动对照放在同一张卡里。修复模式设 `pageCompare: true` 并填 `metrics`，展示整体改前改后差异；`pages[].before` 为首轮截图，`after` 为最终复验截图。

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
