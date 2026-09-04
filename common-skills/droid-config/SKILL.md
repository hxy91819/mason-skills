---
name: droid-config
description: "配置、升级和验证 Factory Droid，并维护脱敏的本地运行审计。仅供用户通过 $droid-config 手动调用。"
disable-model-invocation: true
---

# Droid 配置

只在用户显式调用 `$droid-config` 后执行。本 Skill 覆盖 Droid CLI 升级、BYOK/自定义模型、默认模型、上下文压缩和 Mission 角色路由。

## 开始前

1. 完整阅读 [官方来源与刷新规则](references/official-sources.md)，在线核对本次涉及的 Droid 与模型资料。
2. 涉及模型、上下文、输出上限、effort 或 Mission 时，再阅读 [配置经验](references/configuration-experience.md)。其中的数值是带日期的经验快照，不是当前事实源。
3. 先运行只读检查：

   ```bash
   python3 scripts/droid_config_audit.py check
   python3 scripts/droid_config_audit.py show
   ```

4. 确认 `command -v droid`、`droid --version`、`droid update --check`、`droid --help` 和 `droid exec --help`。从实际命令输出确认安装方式、更新入口、模型 ID 与可用 effort。

## 安全边界

- 先读后写；只修改用户要求的 Droid 配置。保留无关设置与并发改动。
- 把 `~/.factory/settings.json` 视为密钥文件。仅输出脱敏投影；不得打印完整文件、`apiKey`、token、Authorization header 或可逆的全文编码。
- 写入前创建带时间戳的备份并设为 `0600`。完成后把活动配置也设为 `0600`。
- 复用已有凭据时在进程内复制值，不经过 stdout、命令回显或补丁正文。缺少目标供应商凭据时停止并请用户提供安全的凭据来源。
- 升级、配置写入和最小模型调用属于用户明确请求时才执行的副作用。除非用户明确要求运行 Mission，不启动完整 Mission；模型配置验证只做最小调用。
- 官方资料不可达、来源相互冲突或供应商上限无法验证时，保留现值并报告不确定性。

## 工作流

### 1. 建立来源矩阵

对每个目标模型记录并交叉核验：展示名、请求模型 ID、API 协议与 base URL、上下文窗口、供应商实际最大输出、支持的 reasoning effort、图像能力和资料日期。

采用以下优先级：实际供应商端点与错误响应 > 当前供应商文档 > 模型厂商文档 > 本 Skill 的经验快照。Droid 字段语义和 Mission 字段以当前 Factory 文档与 `droid --help` 为准。发生差异时保留两层事实并解释最终取值。

### 2. 升级 Droid

先 `droid update --check`，再在用户要求升级时运行 `droid update`。升级后重新运行版本、帮助和模型目录检查；新版本可能改变模型 ID、effort 枚举或配置 schema。

### 3. 设计并写入配置

- `customModels` 只保留用户指定的自定义模型；不要把“清理自定义模型”扩大为组织级内置模型禁用。
- `maxOutputTokens` 使用当前供应商路由实际接受的上限，不直接照抄模型厂商理论上限。
- `noImageSupport` 根据实际路由能力设置；供应商 `/api/show` 或等价模型信息优先于营销页。
- `compactionTokenLimitPerModel` 必须为最长一次输出和额外安全余量留空间，取便于审计的向下取整值。
- 自定义 ID 稳定、唯一；Mission、默认会话与压缩映射全部引用最终 ID。清除已删除模型的悬空映射。
- sampling 参数只有在官方明确要求且供应商允许时才加入 `extraArgs`；供应商固定的参数保持省略。

### 4. 配置 Mission

使用当前 Factory 文档中的字段：

- `missionOrchestratorModel` / `missionOrchestratorReasoningEffort`
- `missionModelSettings.workerModel` / `workerReasoningEffort`
- `missionModelSettings.validationWorkerModel` / `validationWorkerReasoningEffort`

编排器与验证器优先质量，worker 兼顾吞吐；所有 effort 都必须先验证目标模型支持。保留 `skipScrutiny`、`skipUserTesting` 等用户未要求变更的策略，并在交付时说明其有效状态。

### 5. 验证

1. 运行 `jq empty ~/.factory/settings.json` 和审计脚本 `check`。
2. 用 `droid exec --help` 确认目标模型被识别，所有默认/Mission/压缩引用均存在。
3. 按模型顺序执行最小真实调用，包含目标 effort。串行执行，确保单一日志文件中的失败可归因。
4. 失败时先查看对应时段日志，再直接调用供应商兼容端点做最小请求，以区分 Droid、凭据、模型 ID、effort 与输出上限问题。
5. 修改参数后只重试受影响模型；最终四类检查必须同时通过：版本、结构、引用、真实调用。

### 6. 脱敏审计

对发生写入的运行用稳定 ID 记录最小事实；审计失败只警告，不回滚或改变已经验证成功的 Droid 配置结果：

```bash
python3 scripts/droid_config_audit.py record \
  --run-id droid-config-YYYYMMDDTHHMMSSZ \
  --operation configure --outcome success \
  --version-before 0.x --version-after 0.y \
  --duration-ms 12345 --model glm-x --model model-y
```

用户后续明确接受或拒绝结果时，用同一 ID 回写决策；重复回写覆盖原决定：

```bash
python3 scripts/droid_config_audit.py decide \
  --run-id droid-config-YYYYMMDDTHHMMSSZ --decision accepted
```

历史默认位于 `~/.cache/droid-config/run-history.json`，不进入仓库；只保存稳定 ID、版本、模型 ID、耗时、操作、结果与接受/拒绝决定。用 `show` 聚合复盘，用 `history-check` 校验滚动与双计语义。

## 完成标准

- Droid 更新检查、目标配置、Mission 引用、JSON/schema 检查和每个目标模型的真实调用均有可验证结果。
- 旧模型、旧压缩键和旧 Mission 引用已按用户范围移除，不存在悬空引用。
- 配置与备份权限安全，输出中没有密钥。
- 交付报告包含资料日期、厂商能力与供应商实际限制的差异、最终 effort、保留的 Mission 策略、备份路径和审计 run ID。
