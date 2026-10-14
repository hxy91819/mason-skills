# 首次配置引导（Bootstrap）

进入条件：解析后的配置路径（`--config` > `BB_DISPATCH_CONFIG` > `~/.config/bb-dispatch/config.yaml`）上确实没有文件。`bb-dispatch` 报“无法读取配置 <路径>”时先看这个路径：文件不存在才进入引导；文件存在却读不了（YAML 损坏、路径是目录、无权限）是已有配置的故障，把错误原话报给用户并修复那份文件，不新建覆盖。

目标：在同一次对话里检测 BB 实际可用的 provider 与模型，给出一份可直接派发的建议配置，经用户确认后写入并通过 `--dry-run` 验证，再回到原来的派发任务。全程让用户看得到进度：每个阶段开始前用一两句话说明正在做什么、刚才发现了什么，写在回复正文里；在 BB 子线程里代用户执行时，阶段结论另用 `bb thread tell <父线程> --mode queue` 转发。检测命令的原始 JSON 自己消化，给用户的是整理后的结论。无人值守的调用方（编排 driver、自动化脚本）没有人可以确认，照常以缺少配置失败并报告，不进入引导。

检测、写入和自检都沿用原派发的显式参数：`--config`、`--project`、`--environment`，以及显式给出的 `--permission-mode`、`--reasoning`；没有指定时才用当前线程的上下文和配置默认值。

## 1. 告知并开始检测

先告诉用户：在 <路径> 没有找到派发配置，补一份就能继续派发；现在开始检测本机 BB 已接入的 provider 和模型，只运行几条只读命令。然后执行：

```bash
bb status --json                       # thread.id 作为 <thread-id>；thread.environment.display.id 作为 <env>
bb thread show <thread-id> --json      # thread.providerId 是当前会话正在用的 provider
bb provider list --environment <env> --json
bb provider models <provider-id> --environment <env> --json   # 对每个 available 的 provider 各跑一次
```

原派发指定了环境 ID 时，provider 查询用该 ID；指定的是目录路径时，查询仍用当前线程环境作代理（与脚本一致），路径只在自检时原样传回。不在 BB 线程里运行（`bb status --json` 没有 `thread`）且没有指定环境 ID 时，省略 `--environment` 和 `thread show`，用本机默认目录。

逐个 provider 记录 `id`、`displayName`、`available`、`capabilities.permissionModes`，以及模型目录里每项的 `id`、`displayName`、`description`、`supportedReasoningEfforts[*].reasoningEffort`、`defaultReasoningEffort`、`isDefault`。目录可能上百项，只提取这些字段，可用一次性脚本汇总。`maintenance` 是插件维护能力标记，不是可用性信号，不据此排除。

候选 provider：`available: true` 且模型目录非空。不可用的 provider 记下名称和原因线索（`strings.signInHint` 等），空目录的也记下，两者都不进建议。一个候选都没有时停止引导：告诉用户先在 BB 里接入并登录至少一个 provider（BB 自带的 `acp-provider` 技能可引导接入），完成后再回来派发。

## 2. 汇报检测结果

用一张短表列出候选 provider：显示名、provider id、支持的权限模式、模型数、标 `isDefault` 的模型；当前会话正在用的 provider 标注出来，它已经证明能跑。表后一句话列出不可用或空目录的 provider。

## 3. 生成建议配置

按 [config.example.yaml](config.example.yaml) 的结构写最简建议，`defaults` 用字符串或有序别名列表（fallback 形式）。按下面的顺序决定，每条规则取第一个命中的；关键词不分大小写、按子串匹配，并列时取目录里靠前的一项：

- 主 provider：当前会话正在用的那个；它不是候选或不在 BB 线程里时，选目录带文字描述且模型最多的候选。
- 权限模式：原派发显式传了 `--permission-mode` 就以它为准，主 provider 必须支持它；否则主 provider 支持 `accept-edits` 就用 `accept-edits`，不支持时改用它支持的模式，并说明这意味着子线程获得的权限（`full` 为完全自主执行）。
- `simple` 模型：description 含 fast、affordable、flash、lite、mini；其次 id 含这些字样；再其次 `isDefault`；都没有则按自己对模型档位的了解选。
- `medium` 模型：description 含 latest workhorse；其次含 workhorse 或 everyday；再其次 `isDefault`；都没有同上。命中的模型与 `simple` 相同而目录还有别的模型时，顺延到下一条规则。
- `complex` 模型：description 含 frontier、most capable、most demanding；其次 id 含 pro、opus、max；都没有同上。
- 只有一个模型时三档都用它。靠 id 字样或自己的了解选出的项标注“拿不准，请确认”。
- `reasoning`：只写 `supportedReasoningEfforts[*].reasoningEffort` 里的精确字符串。`simple` 用 `defaultReasoningEffort`；`medium` 用 `medium`，没有则默认值；`complex` 用 `xhigh`，没有则 `high`，再没有则默认值。模型只有一个级别时三档都写它并说明无法靠 reasoning 拉开；没有级别信息时省略字段。
- 备用 provider：其余候选里必须支持已定的权限模式；优先目录带文字描述的，仍多个时取 `provider list` 顺序靠前的一项，并说明这是稳定选择规则不是质量排名。有则给每档追加一个 fallback 别名，模型按同样规则从它的目录里选；没有则单别名。
- 模型 id 保留原值，用单引号包住，值里的单引号写成两个单引号。id 可能含 `/`、`[` 或 `"`；含双引号的 id 不转义就套双引号会写出无效 YAML。

把建议 YAML 整段给用户，每个选择用一句话说明依据。YAML 后给编号决策列表，第一项是“按建议写入”，其余是常见替代：换主 provider、换某一档的模型或推理级别、改权限模式、改成负载均衡（格式见[配置与派发](dispatch.md)）。宿主有原生提问工具时可以用它收集选择，否则结束回合等用户回复。

## 4. 写入并验证

用户确认后创建目录并写入配置文件，再对三档各跑一次自检；建议含备用别名时，每档再以备用别名为起点跑一次，确认 `selection.agent` 等于该别名：

```bash
bb-dispatch --difficulty simple --task '配置自检' --dry-run
bb-dispatch --difficulty medium --task '配置自检' --dry-run
bb-dispatch --difficulty complex --task '配置自检' --dry-run
bb-dispatch --difficulty simple --task '配置自检' --dry-run --fallback-from <备用别名>
bb-dispatch --difficulty medium --task '配置自检' --dry-run --fallback-from <备用别名>
bb-dispatch --difficulty complex --task '配置自检' --dry-run --fallback-from <备用别名>
```

原派发带了 `--config`、`--environment`、`--project` 或 `--permission-mode` 时，自检带同样的参数；原派发显式传了 `--reasoning` 的，对该难度再多跑一次带它的自检。不在 BB 线程里时必须显式传 `--environment <已有环境 ID>`，脚本没有环境无法校验。

全部通过后告诉用户：配置文件在哪里、三档各自会用什么 provider 和模型、备用候选是否也通过、以后直接编辑该文件就能调整，然后用原来的全部参数继续原本的派发任务。某档失败时把错误原话和修正方案告诉用户，按用户确认的方向改完重跑该档；备用别名某档失败同样处理，首选通过不算全部通过。修正只限于用户已确认范围内的字段，换成未确认的模型或 provider 要先回到第 3 步。

## 完成条件

配置文件已写入、三档自检（含备用别名）都通过、用户知道配置路径和调整方式，原本的派发任务已继续。
