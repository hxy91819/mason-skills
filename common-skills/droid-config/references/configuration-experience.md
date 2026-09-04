# Droid 配置经验

## 2026-09-04 快照

以下结果来自 Droid `0.212.0`、Factory 文档、模型厂商文档和 Ollama Cloud 实际请求。未来调用必须按 [官方来源与刷新规则](official-sources.md) 重新核验。

| 模型 | Ollama 请求 ID | 厂商上下文 | Droid/Ollama 最大输出 | effort | 图像 |
| --- | --- | ---: | ---: | --- | --- |
| GLM 5.3 | `glm-5.3` | 1,048,576 | 131,072 | `low/high/max`，默认 `max` | 否 |
| GLM 5.3 Flash | `glm-5.3-flash` | 1,048,576 | 131,072 | `low/high/max`，Droid 默认 `high` | 是 |
| DeepSeek V4 Flash | `deepseek-v4-flash:0731` | 1,048,576 | 65,536 | `off/low/high/max`，Droid 默认 `high` | 否 |
| Kimi K3 | `kimi-k3` | 1,048,576 | 131,072 | 厂商为 `low/high/max`、默认 `max` 且始终思考 | 是 |

DeepSeek 厂商接口当时标注最大输出 384K，但 Ollama Cloud 对 `deepseek-v4-flash:0731` 返回“maximum output tokens 65536”。Droid 的 `maxOutputTokens` 会进入真实请求，因此必须采用 65,536；照抄厂商上限会导致 Droid 在首轮前失败。

## 经验证的 Mission 组合

- orchestrator：GLM 5.3，`max`
- worker：GLM 5.3 Flash，`max`（用户明确选择；Factory 内置模型默认仍为 `high`）
- validator：DeepSeek V4 Flash，`max`

这是当前部署的质量优先选择，不是通用强制值。未来版本先从 `droid exec --help` 和模型官方文档确认 effort，再服从用户指定；不要把 Factory 默认值与用户显式配置混为一谈。

当时使用的压缩阈值为：128K 输出模型 900,000；64K 输出的 DeepSeek 950,000。选择原则是 `context - compaction threshold` 大于最大输出并包含额外安全余量，而非复制固定数字。

## 自定义模型结构

以下仅展示字段关系，凭据使用占位符：

```json
{
  "customModels": [
    {
      "apiKey": "${OLLAMA_API_KEY}",
      "baseUrl": "https://ollama.com/v1",
      "displayName": "GLM 5.3",
      "id": "custom:GLM-5.3-0",
      "index": 0,
      "maxOutputTokens": 131072,
      "model": "glm-5.3",
      "noImageSupport": true,
      "provider": "generic-chat-completion-api"
    }
  ]
}
```

Factory 文档允许环境变量插值，但只有 Droid 启动环境确实定义变量时才能使用。现有明文 key 的复制应在进程内完成，不把 key 放进补丁、终端输出或临时文档。

## 已验证的排障经验

- 先升级再看模型目录。旧 Droid 可能缺少新模型、effort 元数据或 Mission 字段。
- `droid exec --help` 同时列出内置模型、自定义模型和内置模型的 effort；它适合验证解析结果，但不能替代真实 API 调用。
- `/v1/models` 确认准确请求 ID，`/api/show` 确认 context 与 vision/thinking/tools capabilities。
- 最小 API 请求把 `max_tokens` 设置为候选上限并要求只回复 `OK`，可以低成本暴露供应商上限拒绝。
- 四个模型应串行验证。并行启动多个 Droid 进程会竞争单一日志文件，导致失败时段难以归因。
- `droid exec` 只显示笼统 `Exec failed` 时，先按 session/time 查 `~/.factory/logs/`，再用同一模型、effort 与上限直连供应商；直连成功通常说明 Droid 字段或请求组合有问题。
- 配置摘要只用 `jq` 投影允许字段。哈希可用于比较 key 是否一致，但不输出原值；完整文件即使编码后仍可能泄密。
