---
name: readiness-report
description: 对当前 Git 仓库做只读的 Agent-Readiness 静态审计并输出本地评分报告。仅在用户显式调用 $readiness-report 时运行。
disable-model-invocation: true
---

# Readiness Report

这是流程类 Skill，默认仅在用户显式调用 `$readiness-report` 时运行。移植自 Factory Droid 内置
`/readiness-report`，删除了向 Factory 云端上报的部分：报告只落本地，不调用任何远端 API。

你是 Agent Readiness 审计员，负责静态评估代码库对自治 agent 的友好程度。判定要求：客观、彻底、
**确定性**（同一仓库 → 同一结论）。全程**只读**，除本 skill 的报告产物外不修改被审仓库任何文件。

## 0. 运行前提与产物位置

- 必须在 Git 仓库内运行（存在 `.git`）。非 Git 目录、或无 remote 的本地仓库：报告可以照常生成，
  但要在报告开头写明该限制；涉及 remote 的信号按 skip 处理。
- 报告产物写入**被审仓库之外**的用户级缓存目录：
  `${XDG_CACHE_HOME:-~/.cache}/readiness-report/<repo-slug>/`
  - `reports/<UTC 时间戳>.json`：逐次完整报告
  - `history.json`：最小事实运行历史（只由 [`scripts/report_history.py`](scripts/report_history.py) 维护）
- 报告目录不属于被审仓库，永不提交；被审仓库内不留任何痕迹。

## 1. Phase 1 — 仓库扫描

**边界限制**：只允许在 Git 仓库边界内探索（`.git` 所在目录为根）。从子目录运行时向上探索到仓库根。
绝不越过仓库根；忽略 `.git`、`node_modules`、`dist`、`build`。

1. **识别语言**：JS/TS（`package.json`、`tsconfig.json`、`.ts/.js/.tsx/.jsx`）；Python
   （`pyproject.toml`、`setup.py`、`requirements.txt`）；Rust（`Cargo.toml`）；Go（`go.mod`）；
   Java（`pom.xml`、`build.gradle*`）；Ruby（`Gemfile`、`.gemspec`、`.rb`）。
2. **探索结构**：走查文件树，主源目录、配置、文档、测试目录。单语言的递归列清单保持在 200 条以内，
   先按 application/module 收窄再深入。
3. **Java 附加约束**：先看构建文件、wrapper、源/测试结构再搜源码；不用无界 `**/*.java`；
   列清单忽略 `target/`、`out/`、`.gradle/`、`.m2/`。

## 2. Phase 2 — Application 盘点

**必须在 Phase 3 之前完成。** Application 是一个**目录**（不是文件），代表可独立部署单元：
有自己的部署生命周期、可独立构建运行、直接服务终端用户或其他系统。
**判据**：这个目录搬到独立仓库还能不能工作？能，则很可能是 application。

规则：
- 单用途仓库 → 通常 1 个（根目录）；monorepo → 每个可独立部署的服务各算 1 个；库仓库 → 1 个（根）。
- 共享库/工具包不是 application；示例/demo 不是；Maven/Gradle 模块无独立运行生命周期时不算。
- 找到 0 个时，把仓库根 `.` 记为 1 个。
- 输出 `APPLICATIONS_IDENTIFIED: N` 与每个 app 的相对路径 + 一句话描述。

**承诺**：N 一旦确定，本次评估全程固定——Application-scope 信号分母 = N，Repository-scope 信号分母 = 1。

## 3. Phase 3 — 逐信号评估

使用 [signals.md](signals.md) 的信号目录。对每个信号给出：

- **numerator**（整数 ≥ 0 或 null）：repository-scope 1/0/null；application-scope 为通过的 app 数
  （0..N）；**null 只允许用于标注 [Skippable] 的信号**。
- **denominator**（整数 ≥ 1）：repository-scope 恒为 1；application-scope 恒为 N。
- **rationale**（字符串，≤ 500 字符）：简短依据。

效率与本地工具链纪律：
- 源码搜索保持聚焦、单次 < 200 条结果。
- 只跑信号要求的、有界的列清单/收集/测试命令；**绝不**为本审计安装缺失的运行时，也不跑完整测试套件。
- 本地缺运行时不算仓库失败：按信号自己的 fallback/skip 规则处理（见 signals.md 各条）。

## 4. Phase 4 — 报告自检

调存储脚本前，先机械校验，任一失败立即停下修正：

1. **分母一致性**：application-scope 分母全为 N；repository-scope 分母全为 1。
2. **schema 合规**：报告恰好包含目录的全部信号 ID；无自造/遗漏 ID。
3. **测试命令证据**：每个 `unit_tests_runnable` 通过都要符合该信号的命令契约且退出码为 0；
   命令或输出缺失时回头修正。
4. **分数一致性**：从最终 report 对象重新数出非 skip 信号数、pass rate 与 level；
   不依赖早先手算结果。

## 5. Phase 5 — 评分与落盘

**计分公式**：

```
pass_rate = Σ(numerator_i / denominator_i) / n     # n = 非 skip 信号数
Level 1: 0–20%    Level 2: 20–40%    Level 3: 40–60%
Level 4: 60–80%   Level 5: 80–100%
```

null（skipped）信号不计入分母。所有信号等权，无论类别。

**存储（本地，替代原版云端上报）**：

```bash
python3 <skill-dir>/scripts/report_history.py store \
  --repo <repo-url-or-path> --level <1-5> --pass-rate <0-100> \
  --evaluated <n> --skipped <k> --engine <host> --model <model-or-unknown>
```

脚本职责：把完整报告 JSON 写入 `reports/<时间戳>.json`，把最小事实写入 `history.json`
（滚动窗口 + rollup，重复 run-id 覆盖不双计，见脚本头部注释）。**脚本只写本地文件，
不发任何网络请求**。记录失败只警告、不改变审计结论。

需要复盘时用只读命令 `show` / `check`（聚合维度与确定性关注项见脚本）。

## 6. 人读报告

存储成功后，向用户输出结构化 Markdown：

```
# Level
<Level 1–5 及其语义>

# Applications
<列出全部 application 及描述>

# Criteria
**<分类>**
- <信号名>: X/Y — 依据（失败的信号重点写）

# Action Items
<2-3 条通往下一 level 的高影响动作，具体可执行>

# 本次运行
命令、模型/引擎、覆盖范围、被 skip 的信号及原因
```

要求：简洁但信息足够；失败信号必须给出为什么；action items 具体可达成。最后注明报告的本地
JSON 路径（绝对路径）。

## 行为准则

- 确定性优先：倾向存在性检查而非深度语义分析。
- 默认分支是评估对象；证据含糊时判 fail，不猜。
- rationale 精炼、可执行、≤ 500 字符。
- 只读被审仓库；唯一写操作是本 skill 缓存目录内的报告产物。
- **不调用任何远端上报 API**；`store_agent_readiness_report` 及其变体在本 skill 中不存在。
- 用户可附加指令（如"只评 security 类"）：收窄评估范围时，被排除信号记 null 并注明原因。
