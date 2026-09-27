
# TypeScript 新项目 Agent Harness 设计指南

基于 OpenClaw 仓库（2026.9.6，`origin/main`）的实证考察与本次讨论整理。标注 **[OC]** 的是 OpenClaw 已实践的做法，标注 **[补]** 的是它没做、但我认为新项目应该补上的。

---

## 0. 三条底层原则

1. **能用脚本卡住的，不写进 AGENTS.md。** 模型会忘，CI 不会。每条规则要么是可执行的门禁，要么是解释"为什么"的一句话加指向。
2. **门禁按"这个错误会不会让 agent 下次改错"来选，不按传统代码健康度指标选。** 文件长度、类型断言、模块边界、死导出值得卡；函数长度、圈复杂度不值得。
3. **严谨度由故障成本决定，同一仓库可以分区。** 故障便宜的区域用"快速检测 + 向前修"，故障贵的区域（状态、数据、凭据、对外契约）用"预防 + 契约 + 变异分数"。

---

## 1. 三层结构

| 层           | 作用                                  | 载体                                                                      |
| ------------ | ------------------------------------- | ------------------------------------------------------------------------- |
| 指令层       | 告诉 agent 优先级、纪律、去哪找 owner | `AGENTS.md`（根 + 目录级）、按需加载的 skill                            |
| 机械约束层   | 让错误在 CI 变红                      | lint、typecheck、`check-*` 脚本、棘轮基线、契约测试                     |
| 运行时护栏层 | 代码写对了也不能随便执行              | worktree 隔离、文件工具限工作区、exec 审批、pre-commit 密钥扫描、托管身份 |

---

## 2. 指令层：AGENTS.md 怎么写 [OC]

**根文件只放三块**：设计优先级、工作约定、执行纪律。不超过一屏能读完的量。示例纪律（可直接抄）：

```
- Root cause deep. Proof scoped.
- Real failing entry point first. Bypassed boundary != proof.
- Repeated failures or 10 min without new evidence: change approach. No blind retries.
- Time pressure never waives gates. Report concrete blockers.
- Before restoring a removed path, run `git log -p -S <symbol>` and read why it was removed.
- Before changing an export, grep its callers; read owners, siblings, tests.
```

**目录级 AGENTS.md** 只写该目录的不变量，每条规则附 issue/PR 编号作为证据（例：`test/AGENTS.md`："async waits synchronize on produced state, never on the action returning: #125441, #125456"）。

**工作流放进 `.agents/skills/<name>/SKILL.md` + `references/`**，按需读取，不常驻上下文。上下文成本本身是设计约束："Keep generated prompt/tool/context additions bounded and deterministic."

**"一个职责一个 owner"** 写进根文件，并说明：调用方消费 owner 的操作和记录的事实；缓存和投影从 owner 派生并带显式失效生命周期。这句话后面会变成契约测试的归属规则。

---

## 3. 机械约束层

### 3.1 单入口聚合命令 [OC]

`pnpm check`（对应 `scripts/check.mts`）：preflight → typecheck → lint → policy guards，支持 `--base origin/main` 做棘轮对比。agent 只需要记一条命令。

### 3.2 类型与语义正确性（全开 error）[OC]

oxlint/ESLint：

```
typescript/no-explicit-any, no-floating-promises, no-misused-promises,
only-throw-error, switch-exhaustiveness-check, consistent-return,
restrict-plus-operands, import/no-self-import, import/no-duplicates, import/first
```

这是零成本的爆炸半径分析：加 union variant、改签名，所有漏处理处在 typecheck 就红。返回值用 `Readonly<>`/`ReadonlyArray`，把"别名污染"从运行时 bug 变成编译错误。

### 3.3 禁止掩盖型修复 [OC]

自定义 lint（OpenClaw 用 oxlint jsPlugin，ESLint 等价物是自定义 rule）：`no-widen-then-assert`、`no-chained-type-assertions`。加上 `as` 断言棘轮：每个断言必须带 `// SAFETY:` 注释，否则计入基线且只能减。

### 3.4 循环依赖与分层边界 [OC，工具选择为补]

新项目直接用 **dependency-cruiser**，一个配置同时管环和分层：

```js
module.exports = {
  forbidden: [
    { name: "no-circular", from: {}, to: { circular: true } },
    { name: "no-controller-to-dao", from: { path: "^src/controllers" }, to: { path: "^src/dao" } },
    { name: "no-dao-upward",       from: { path: "^src/dao" }, to: { path: "^src/(services|controllers)" } },
  ],
};
```

只有当规则不在 import 图上时（调用顺序、控制流、注释与 AST 的关系）才值得手写 TS AST 脚本，且**和修 bug 的 PR 一起提交**，让每个守卫都有一个真实事故做注脚。OpenClaw 自写 SCC 检测是因为几千文件下 madge 太慢且解析不一致，小项目不需要。

### 3.5 棘轮（对存量债务最有效的设计）[OC]

基线文件提交进仓库，只能缩不能加。建议四个：

- 文件行数超阈值名单（阈值 600–800，宽松，只拦 god file；规则文本写明"沿职责边界拆，不按行数拆"）
- 无 SAFETY 注释的类型断言计数
- `eslint-disable` / `@ts-ignore` 计数
- **[补]** 认知复杂度（`sonarjs/cognitive-complexity`，阈值 25 左右）——不用圈复杂度，不用函数长度

### 3.6 隐式契约的基线文件 [OC]

凡是编译器看不见的边界，生成基线 + `--check`，改动必须显式 regen 并出现在 PR diff 里：
数据库 schema、API 响应 shape、生成的 prompt/模板文本、配置 schema、公开 SDK 导出面、跨语言协议生成物。原理："把无意中改了变成必须显式接受"。

### 3.7 死代码与退役流程 [OC]

- knip 查未使用导出，导出越少隐藏调用方越少。
- 旧 API 先标 deprecated + 脚本禁止新增使用（`check-deprecated-api-usage`），存量迁完再删。
- 在生产者修，不在消费者补。

### 3.8 影响面测试选择 [OC]

`test:changed --changed origin/main` 按 import 图反推受影响测试。目的是让"跑相关测试"便宜到 agent 没理由跳过。

### 3.9 契约测试与公共模块治理 [OC 部分，补为主]

- **[补] fan-in 名单**：用 dependency-cruiser 输出依赖图，传递 fan-in ≥ 阈值的文件写入 `config/shared-modules.txt`，随代码自动更新。这份名单就是"哪些是公共模块"的答案，不靠人判断。
- **[OC] 契约测试归 owner**：一套 `*.contract.test.ts` 跑所有实现者（OpenClaw 有 48 个）。消费者依赖了未写进契约的行为，把用例加到 owner 的契约测试里，不加在自己测试里。
- **[补] 不知道契约时先钉住行为**：对名单模块做录制回放（characterization / golden），理解契约是之后逐条转写的过程。
- **[补] 变异测试**（Stryker）只对名单模块跑，分数记基线做棘轮。这是"契约测试够不够"唯一可靠的度量；行覆盖率回答不了。
- **[补] CI 规则**：PR 触碰名单文件 → 跑全部传递依赖方测试 + 变异分数不降 + CODEOWNERS 要求 owner review。把"人决定要不要分析"这一步删掉。

### 3.10 性能优化专用：差分测试 [补]

保留旧实现作参照，用 `fast-check` 生成输入，断言新旧输出相等；合入后删旧实现，差分测试转成 characterization。加缓存时另写不变量测试：返回值不可被调用方污染、读己之写、缓存键含全部维度（租户/flag/时间）、错误不缓存、副作用次数。

---

## 4. 运行时护栏层 [OC]

- 每个任务一个 git worktree；文件工具 `workspaceOnly`。
- 敏感 exec 走审批（sandbox / tool policy / elevated 三层）。
- pre-commit 扫 staged 内容的敏感字面量（`hooks.blockedLiteralsFile`），命中拒绝并脱敏输出。
- agent 发布走托管身份，禁止直接 `git push` / `gh pr create`。
- PR 必须带工作会话链接，保证可追溯。

---

## 5. 按故障成本分区

| 区域                       | 策略                                                           |
| -------------------------- | -------------------------------------------------------------- |
| UI、脚本、文档、边缘插件   | 棘轮 + 边界守卫 + 定时全量 CI + 向前修                         |
| 状态/DB/配置/凭据/对外 API | PR 级完整 CI + golden + 契约测试 + 变异分数棘轮 + owner review |

OpenClaw 目前是一个标准套全仓库，而那个标准按低成本区定的——14 天里 404 个 fix 落在状态层就是代价。新项目从第一天就分区。

---

## 6. 明确不采纳的

- `max-lines-per-function`、`complexity`（圈复杂度）、`max-params` 硬门禁——会诱导 agent 按行数机械拆分，把状态撒到多个函数里。
- 全仓库统一的覆盖率阈值——衡量的是"跑过"不是"约束了"。
- 把规则写进 AGENTS.md 而不做成脚本。
- 为每个新集成加核心工具/manager——走插件契约。
- 新建 JSON/JSONL sidecar 存状态——用 SQLite。

---

## 7. 落地顺序（新项目第一周）

1. **Day 1**：严格 tsconfig + 3.2 的 lint 规则 + dependency-cruiser（环 + 分层）+ `pnpm check` 单入口 + pre-commit 密钥扫描。
2. **Day 2**：根 AGENTS.md（三块）+ 第一份目录级 AGENTS.md + worktree/审批配置。
3. **Day 3**：棘轮框架（一个通用 `shrink-ratchet` 库，四个基线文件）+ 隐式契约基线（至少 DB schema 和 API shape）。
4. **Day 4**：fan-in 名单生成脚本 + `test:changed` + CODEOWNERS 按名单生成。
5. **Day 5**：对名单里故障最贵的一个模块做契约测试 + 跑一次 Stryker 记基线。

之后的规则：每出一类 bug，修复 PR 同时加一个 `check-*` 脚本；每次"测试全绿还是出事"，给涉事模块补 golden 和变异基线。前置成本一周，边际成本接近零——压力是持续的，门禁只需要建一次。
