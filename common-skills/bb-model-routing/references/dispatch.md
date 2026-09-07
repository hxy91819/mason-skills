# 配置与派发

依赖 Python 3.10+、PyYAML、PATH 中的 `bb`。入口为技能目录内的 `scripts/bb-dispatch`，也可将它软链为用户命令 `~/.local/bin/bb-dispatch`。

首次使用，将 [config.example.yaml](config.example.yaml) 复制到 `~/.config/bb-dispatch/config.yaml`，按实际环境修改。脚本只读取配置，不自动安装 provider 或覆盖用户配置。用 `--config` 或 `BB_DISPATCH_CONFIG` 指向另一份配置。

```bash
bb-dispatch --difficulty simple --task '补充 README 示例' --dry-run
bb-dispatch --difficulty medium --kind debug --task '定位登录失败，给出复现和修复'
bb-dispatch --difficulty medium --agent agy --permission-mode full --task '执行已授权的任务'
```

最后一个示例仅适用于任务已授权 Full Access。默认 `accept-edits`，本机 Pi 和 AGY 仅支持 full，权限不匹配会报错；用户可以在配置顶层或特定环境设置已授权的 `permission_mode`，脚本不会自动升级权限。

配置 `version: 1`。`defaults` 将 simple/medium/complex/debug 映射到工具别名，`agents` 为别名定义 provider/model/reasoning。reasoning 可以是固定字符串，也可以按 simple/medium/complex 配置。`environments.<精确环境 ID>` 可覆盖 defaults、agents、permission_mode；同名工具配置整体替换，必须完整写出三项。无环境覆盖时使用顶层配置；实际可用性仍向目标环境校验。

优先级：命令行覆盖 > 环境配置 > 顶层配置。`--kind debug` 优先难度路由，`--agent` 优先 debug。脚本不从任务文本猜测类型；调用 Agent 负责识别排障任务。模型和思考深度的明确要求用配置别名、`--reasoning` 表达，缺失配置时先补齐，不静默替换。

默认从 `bb status` 解析环境，项目使用该环境的所属项目。`--project` 和 `--environment` 可显式指定，但必须匹配；只使用现有环境，不建分支或 worktree。同项目同环境时关联当前父线程。

每次调用会校验 provider 是否存在且可用、权限是否兼容、模型及 reasoning 是否在目录中。`--dry-run` 同样执行只读校验并输出参数数组，不创建线程。实际派发返回 JSON 的 `selection` 和 BB 原始 `result`，只调用一次 spawn；超时或响应异常时先查线程，避免重复创建。目录不做持久缓存，防止安装、账号或环境变化后继续使用过期配置。

验证：`python3 -m unittest discover -s scripts -p 'test_*.py'`（从技能目录运行）。

## Pi 额度切换

初始配置中 `pi` 默认指向 Ollama Cloud；`pi-ollama` 和 `pi-zai` 分别固定选择两条 GLM 5.3 Flash 路由，推理级别均为 `max`。具体模型 ID 以用户配置为准，环境覆盖时同步维护这些别名。

新任务可用 `--agent pi-zai` 或 `--agent pi-ollama` 选择渠道。脚本只负责启动前校验，不监控额度，也不自动重派；Agent 需要查看线程状态与错误。明确的余额不足、套餐额度耗尽可触发切换，单独的 HTTP 429、短时限速、超时或认证失败不构成此依据。用户限定渠道时先遵循限制。

已有任务耗尽额度时，先确认原回合已结束，检查已完成工作和剩余目标，避免重复副作用。告知用户切换原因，读取原环境下另一条路由的模型目录确认可用，然后在原 Pi 线程继续：

```bash
bb thread tell <thread-id> '<已完成工作与剩余目标；避免重复操作>' \
  --model <另一条路由的完整模型ID> --reasoning-level max --json
```

该命令在下一回合选择替代模型；若还希望后续回合默认使用它，执行 `bb thread update <thread-id> --model <完整模型ID> --reasoning-level max --json`。只更新属于当前任务的 Pi 线程，不改权限或全局默认。两条路由均耗尽时报告等待重置，不在它们之间循环切换。脚本的 `--agent` 用于新建线程，不能用它重新派发整个未完成任务来冒充续接。
