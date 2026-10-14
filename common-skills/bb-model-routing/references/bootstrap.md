# 首次配置引导（Bootstrap）

进入条件：派发配置文件不存在，表现为 `bb-dispatch` 报“无法读取配置 <路径>”，或派发前检查 `~/.config/bb-dispatch/config.yaml`（`--config`、`BB_DISPATCH_CONFIG` 指定的路径优先）时文件缺失。目标：在同一次对话里检测 BB 实际可用的 provider 与模型，给出一份可直接派发的建议配置，经用户确认后写入并通过 `--dry-run` 验证，再回到原来的派发任务。

全程让用户看得到进度：每个阶段开始前用一两句话说明正在做什么、刚才发现了什么。检测命令的原始 JSON 自己消化，给用户的是整理后的结论。无人值守的调用方（编排 driver、自动化脚本）没有人可以确认，照常以缺少配置失败并报告，不进入引导。

## 1. 告知并开始检测

先告诉用户：没有找到派发配置（给出路径），这不影响后面的工作，现在开始检测本机 BB 已接入的 provider 和模型，只运行几条只读命令。然后执行：

```bash
bb status --json                       # thread.id、thread.environment.display.id 作为 <env>
bb thread show <thread-id> --json      # thread.providerId 是当前会话正在用的 provider
bb provider list --environment <env> --json
bb provider models <provider-id> --environment <env> --json   # 对每个可用 provider 各跑一次
```

不在 BB 线程里运行时省略 `--environment` 和 `thread show`，用本机默认目录。

`provider list` 每项看 `id`、`displayName`、`available`、`capabilities.permissionModes`。有效 provider 的判定：`available: true`，且 `permissionModes` 包含打算使用的权限模式（默认 `accept-edits`）。只支持 `full` 的 provider 单独列出，说明要把 `permission_mode` 设为 `full` 才能派给它。不可用的 provider 列出名称和原因线索（`strings.signInHint` 等），不进建议。

`provider models` 每项看 `id`、`displayName`、`description`、`supportedReasoningEfforts`、`defaultReasoningEffort`、`isDefault`。返回空数组的 provider 不进建议。

一个有效 provider 都没有时停止引导：告诉用户先在 BB 里接入并登录至少一个 provider（BB 自带的 `acp-provider` 技能可引导接入），完成后再回来派发。

## 2. 汇报检测结果

用一张短表列出有效 provider：显示名、provider id、支持的权限模式、模型数、标 `isDefault` 的模型。表后一句话列出不可用或仅支持 `full` 的 provider。当前会话正在用的 provider 标注出来，它已经证明能跑。

## 3. 生成建议配置

按 [config.example.yaml](config.example.yaml) 的结构写最简建议，`defaults` 用字符串或有序别名列表（fallback 形式）：

- 主 provider 优先选当前会话正在用的那个；不在 BB 线程里时选模型目录最完整、权限模式兼容的 provider。
- 三档模型从主 provider 的目录里选。`simple` 选描述含 fast、affordable、flash 等字样或最轻量的一档；`medium` 选 `isDefault` 或描述为 workhorse 的主力模型；`complex` 选描述为 frontier、most capable 的最强模型。目录描述没有线索时按自己对模型档位的了解选，并在建议里标注“拿不准，请确认”。只有一个模型时三档都用它，靠 `reasoning` 拉开档位。
- `reasoning` 只能取该模型 `supportedReasoningEfforts` 里的值：`simple` 用 `defaultReasoningEffort`，`medium` 用中档，`complex` 用高档。模型没有级别信息时省略该字段。
- 有第二个有效 provider 时，给每档追加一个 fallback 别名，模型按同样规则从它的目录里选；没有则单别名。
- 模型 id 原样复制并加引号，它可能含 `/`、`[` 或 `"`。
- `permission_mode` 默认 `accept-edits`；主 provider 不支持它时改为它支持的模式，并说明这意味着子线程获得的权限。

把建议 YAML 整段给用户，每个选择用一句话说明依据。YAML 后给编号决策列表，第一项是“按建议写入”，其余是常见替代：换主 provider、换某一档的模型或推理级别、改权限模式、改成负载均衡（格式见[配置与派发](dispatch.md)）。宿主有原生提问工具时可以用它收集选择，否则结束回合等用户回复。

## 4. 写入并验证

用户确认后创建目录并写入配置文件，再对三档各跑一次：

```bash
bb-dispatch --difficulty simple --task '配置自检' --dry-run
bb-dispatch --difficulty medium --task '配置自检' --dry-run
bb-dispatch --difficulty complex --task '配置自检' --dry-run
```

全部通过后告诉用户：配置文件在哪里、三档各自会用什么 provider 和模型、以后直接编辑该文件就能调整，然后继续原本的派发任务。某档失败时把错误原话和修正方案告诉用户，按用户确认的方向改完重跑该档；修正只限于用户已确认范围内的字段，换成未确认的模型或 provider 要先回到第 3 步。

## 完成条件

配置文件已写入、三档 dry-run 都通过、用户知道配置路径和调整方式，原本的派发任务已继续。
