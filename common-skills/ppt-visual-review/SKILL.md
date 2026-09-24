---
name: ppt-visual-review
description: 当用户显式调用 $ppt-visual-review，要求检查并修复 PPT 式 HTML 的布局与视觉一致性时使用。
disable-model-invocation: true
triggers:
  - user
---

# PPT Visual Review

流程类 Skill，仅在用户显式调用 `$ppt-visual-review` 时运行。定位是**布局验收**：观众在投影尺度下看到的版面是否有序——箭头能读出起止、留白承担用途、同类元素长得一样、全局字体与颜色成体系、对齐与中文排版细节（孤字、避头尾、标点、中英混排、行长行距、字数字号）过关、层级与分组一眼可读。论据、数据口径等内容质量不在本技能范围。真实画面是判定依据，脚本测量是线索。

## 角色与模式

- **审查者**：由 `$bb-model-routing` 派发的独立 BB 线程。亲自截图、逐页看图、裁决脚本线索、定级、复验；不修改 deck。审查者读完本文件后按 [references/review-checklist.md](references/review-checklist.md) 自己完成审查，是审查链的终点。
- **主 Agent**：固定输入、派发、裁决意见是否采纳、修改源文件、运行项目验证、生成最终报告。不自审冒充独立审查。

默认**修复模式**：在审查范围内直接修改版式，不逐条询问。用户明确说"只审查/不改源文件"时为**只读模式**：只跑第 1 轮审查，跳过修复循环，直接出报告。

### 派发方式

每次派发审查（首轮与新开的复审线程）都由宿主按名称加载 `$bb-model-routing`，用它的 `bb-dispatch` 发起，难度固定为 `simple`：

```bash
bb-dispatch --difficulty simple --title 'PPT 布局审查 rN' --task '<交接材料>'
```

- 不改用宿主内置 subagent，也不按页数或 deck 复杂度升档；provider、模型、推理级别由 `bb-model-routing` 的配置决定，不写进 `--task`。
- `--task` 开头写明：「你是本次 PPT 布局审查的审查者（reviewer）。读取 `<本 Skill 绝对路径>/SKILL.md` 与 `references/review-checklist.md`，亲自完成全部页的截图、看图、定级和记录。这是终点任务：不要再派发 subagent 或 BB 线程，不要调用 `$bb-model-routing`、`bb-dispatch` 或 `$ppt-visual-review` 发起新的审查流程，也不要修改 deck。」随后附交接材料。
- 派发后结束当前回合，等 BB 完成通知送达再读结果；不用 `bb thread wait` 或反复查询。
- 派发失败或线程因 provider/额度中断时，按 `bb-model-routing` 的 fallback 规则续派，仍为 `simple`。无法派发时记录缺口，不以主 Agent 自审替代。
- 一个审查线程覆盖全 deck；只有页数多到单线程无法完成时才按页拆分，每个线程同样是 `simple` 的终点任务，由主 Agent 合并覆盖记录。

## 工作流

### 1. 固定输入

记录 deck 路径、内容哈希、实际页数、投影视口、模式、用户原始要求，并建立本次产物目录（用户指定或系统临时目录，不放技能仓库）：`<产物>/r1/`、`<产物>/r2/`… 每轮一个子目录，`<产物>/findings.json` 为跨轮唯一记录。

完成标准：上述字段可追溯，产物目录已创建。

### 2. 派发首轮审查

交接材料：本 Skill 解析后的绝对路径、角色 `reviewer`、轮次 `r1`、deck 路径/URL 与哈希、全部页清单、视口、模式、用户原始要求（含用户已指出的问题）、产物目录。

审查者返回：`findings.json` 路径、覆盖/缺口摘要、待修 finding ID 列表、本轮 `rN/before.json`（或 `after.json`）测量文件路径。

完成标准：审查者覆盖全部页；只读模式直接跳到第 5 步。

### 3. 主 Agent 修复

逐条处理 `open` 的 finding，在 `findings.json` 上写 `resolution` 与 `resolutionReason`：可修的直接修（`fix` 写实际改动）；判断为有意设计或超出范围的写 `kept` 并说明画面中的具体用途；依赖缺失素材/事实的保持 `open` 并写明所缺输入。审查者提交的是证据和建议，主 Agent 可修正方案，但要记理由。

修法原则：

- 优先改共享样式与容器策略（标题、卡片、箭头、颜色变量），逐页确认不损害其他页的阅读任务；同一问题跨页出现时一次修全。
- 留白的修法是重排：放大主体、调整分栏、把结论移到空带、收紧容器高度；填充装饰或统一居中不是默认解。
- 箭头修到能读出"谁指向谁"：对准起止对象的边、落在两者之间的通道里，或删掉不承载关系的箭头。
- 一致性以多数值或 deck 既有契约为准收敛；刻意的强调（如首尾节点）保留，但需要画面上可读出的区分理由。
- 对齐收敛到同一条参考线；孤字、避头尾用宽度调整、手动断行或改写解决，不靠缩小字号；标点问题优先修字体栈（中文字体排在西文字体前或为标点单独指定字体），再逐处改字符。
- 字数过多先压缩成要点或拆页，而不是缩小字号塞下。
- 保留真实事实与用户原意；缺失的数字或素材不编造。

完成标准：每个 `open` finding 都有处理记录；被审项目现有的相关检查已运行。

### 4. 复审循环

将改动摘要、处理过的 finding ID、新哈希用 `bb thread tell <审查线程ID> '<复审请求>'` 发给同一审查线程续办（消息里重申它是终点审查者、不再派发），同样等完成通知；线程不能续办时按上文派发方式以 `simple` 新派一个审查线程，并附 `findings.json` 与历轮产物。轮次 +1。审查者重新测量并**全量**复看每一页（共享样式会波及未改页），把已修项标 `fixed` 并写 `afterImg`，发现回归或新问题追加新 finding（记首次出现的轮次与截图）。

循环回到第 3 步，直到审查者返回 **clean**：全部页已覆盖，无 `blocking`/`should` 级 `open` 项，`optional` 项已修或以 `kept` 留痕。同一 finding 连续两轮复验未改善时，审查者补充定位证据与可验证的修复方向，主 Agent 换修法而非重复改动；第三轮仍无改善时保持 `open`、写明阻塞原因并结束循环。只剩依赖缺失输入的 `open` 项时同样结束循环，状态为 `reviewed`。

完成标准：审查者给出 clean，或剩余项全部有明确阻塞原因。主 Agent 的修复说明不等于复验通过，只有审查者看过真实 after 才算 `fixed`。

### 5. 输出整体报告

由宿主按名称加载 `$review-html-report`，按其数据契约用 `findings.json` 生成 HTML，并在浏览器里验证展示（折叠、红框、滑块极值/中点/并排/resize）。本技能的固定设置：

- `title: PPT 版式视觉验收`，`evidenceMode: visual`，修复模式 `mode: fix`。
- **整体前后对照**：`pageCompare: true`；`pages[].before` 为 r1 截图，`pages[].after` 为最终轮截图，`review.after` 写该页的复验结论。
- `metrics`：从 r1 与最终轮测量 JSON 统计，至少包含布局类线索按 kind 的改前/改后计数（arrow、void、box-style、role-style、title、font-family、font-size、color、align、widow、kinsoku、half-punct、cjk-spacing、line-length、leading、density、min-size、edge），以及 finding 总数/已修/保留/待处理、复审轮次。
- 每条 fixed finding 带红框 `box`/`label` 与真实前后对照；`limits` 记录缺图、未操作的交互、覆盖缺口。

只读模式同样出 HTML（`mode: review`，不设 pageCompare）；用户明确只要文字时改为 Markdown。

完成标准：HTML 生成且浏览器验证通过；回复给出报告链接、结论状态、剩余待处理项。状态以证据为准：覆盖缺口为 `incomplete`，有待处理项为 `reviewed`，全部核对且已修复复验为 `fixed`，无发现为 `clean`。

## 运行记录与回看

每轮在 `findings.json` 的 `context` 中记录审查线程 ID、`bb-dispatch` 返回的实际选择、轮次、输入哈希和产物路径。用 `bb thread log <id>`、`bb thread output <id>` 回看审查线程的真实工具调用。结构化自检用 `$review-html-report` 的 `build-report.py --data <findings.json> --check`，它只校验记录一致性，不能证明看过图。当前缺口：无跨 deck 的接受率统计或 rollup，采纳/拒绝理由只存在于本轮 `findings.json`。
