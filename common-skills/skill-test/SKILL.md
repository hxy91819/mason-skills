---
name: skill-test
description: 用宿主原生 subagent 对 skill 做隔离的行为测试与盲 A/B。
disable-model-invocation: true
---

# Skill Test

这是流程类 Skill，仅在用户显式调用 `$skill-test` 时运行。主 Agent 设计测试、保存判定标准并复核证据；新建的原生 subagent 只接收待测 skill 与原始任务并完成任务。

## 建立测试契约

1. 完整读取待测 `SKILL.md` 及完成测试所需的直接引用。
2. 优先使用用户给出的原始任务；没有时，按待测 skill 的描述构造一个最小、真实、可验证的任务。
3. 在 subagent 上下文之外记录可观察的成功标准、工作区基线、安全边界和允许的副作用。
4. 为生成物准备临时目录、隔离夹具、mock 或只读环境。测试任务需要额外授权且无法安全等价时，报告受阻。

待测 skill、原始任务、成功标准、基线和隔离方式均明确后再派生 subagent。

## 选择 subagent 和模型

使用当前宿主提供的原生 subagent/delegation 工具；不要通过 ACPX 或 shell 启动另一个 coding agent。

按以下顺序选择模型：

1. 用户指定模型时使用该模型；不可用则报告基础设施失败，不静默替换。
2. 宿主允许选择模型时，优先选择具备任务所需工具与上下文长度的非 frontier、较低成本模型。只有模型目录或用户明确标注时才写 `non-frontier`，无法确认时写 `unknown`。
3. 宿主不允许选择模型时使用其原生默认值或继承值，并在结果中明确说明模型选择未受控。

模型较弱造成的失败是测试信号，不自动改用更强模型覆盖。需要区分 skill 缺陷和模型能力边界时，再用同一任务增加一个更强模型对照组。

## 保持测试上下文纯净

创建全新 subagent，不继承当前对话。Codex 使用 `spawn_agent` 的 `fork_turns: "none"`；其他宿主使用等价的 fresh/isolated context 选项。若宿主只能继承当前上下文，可以继续做探索性测试，但必须标为 `context_isolated=no`，不得声称是盲测。

发送给 subagent 的任务只包含：

```text
Use $<skill-name> at <absolute-skill-path> to complete this user request:

<original-user-request>
```

若 subagent 可稳定发现该 skill，可省略路径，但仍显式写 `$<skill-name>`。不得加入成功标准、预期答案、已知缺陷、怀疑原因、拟议修复、实现计划、历史输出或主 Agent 结论。安全隔离放在环境和权限边界中，不写进任务来暗示期望行为。

保存实际发送的完整任务。删除 skill 选择行与原始任务后，不应剩余测试语义；满足此条件才派生 subagent。

## 执行与取证

一次测试对应一个全新 subagent。A/B 或多模型对照使用彼此独立的 subagent；环境没有共享写入时可并行执行。

subagent 完成后，由主 Agent 检查：

- 实际模型、上下文隔离方式及其原生运行标识；
- subagent 是否读取并使用了指定 skill；
- 工具调用、错误、最终答复和可观察产物；
- 工作区变化、测试结果、安全边界和完成条件；
- 是否出现任务之外的上下文泄漏。

subagent 的自我评价不是通过证据。未成功派生、未读取 skill、模型不可用或工具基础设施失败时，结论是 `infrastructure-failed`，不是 skill 失败。

## 判定与对照

主 Agent依据预先保存的标准给出 `passed`、`partial`、`failed` 或 `infrastructure-failed`，每项判断都对应可复核证据。

验证一次 skill 修订时优先做盲 A/B：

1. 将修订前后版本放入名称不泄漏版本身份的隔离目录。
2. 使用相同模型、原始任务、权限和夹具；唯一变量是 skill 内容。
3. 每组使用全新 subagent，不向任一组提供另一组结果。
4. 比较可观察行为。结果含糊时增加独立重复，不污染任务提示。

只有差异可归因于 skill 版本时，才声称修订有效。用户要求迭代 skill 时，只修复证据支持的问题；每次修订后用新 subagent 复测，最多两轮，然后报告剩余不确定性。

## 运行历史

使用 [`scripts/test_history.py`](scripts/test_history.py) 保存最小事实。默认历史位于 `${XDG_CACHE_HOME:-~/.cache}/skill-test/history.json`，只包含 engine、model、model class、耗时、outcome、上下文隔离状态、稳定 test ID 和主 Agent disposition；不保存任务、回复、diff、日志、路径或密钥。

测试结束后记录一次：

```bash
python3 <skill-dir>/scripts/test_history.py record \
  --test-id <stable-id> --skill <skill-name> --engine <native-engine> \
  --model <actual-model-or-unknown> --model-class <non-frontier|frontier|unknown> \
  --duration-ms <milliseconds> --outcome <outcome> \
  --context-isolated <yes|no|unknown>
```

主 Agent 复核后回写裁决：`accepted` 表示采纳该测试为有效证据，`rejected` 表示因污染、设计缺陷或偶发性不采纳。相同 test ID 的裁决是覆盖，不是追加：

```bash
python3 <skill-dir>/scripts/test_history.py decide \
  --test-id <stable-id> --disposition <accepted|rejected>
```

记录命令失败时仅警告并继续主流程，不改变测试结论。需要复盘时运行 `show`；它会输出固定维度聚合和确定性关注项，live 窗口与 rollup 只计一次。

## 汇报

简要报告待测 skill、原始任务、实际 subagent/model、模型类别与上下文隔离状态；逐字展示实际发送的任务；给出判定、关键证据、A/B 或复测结果、工作区变化、隔离资产清理情况，以及模型选择或宿主能力造成的限制。
