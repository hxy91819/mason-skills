# 官方来源与刷新规则

## 每次调用都刷新

本文件只维护入口，不缓存模型结论。执行配置前读取当前页面，并在报告中注明核验日期。

### Factory

- 文档索引：<https://docs.factory.ai/llms.txt>
- Droid 设置：<https://docs.factory.ai/droid-cli/settings.md>
- 自定义模型 / BYOK：<https://docs.factory.ai/model-independence/byok.md>
- 当前内置模型与 effort：<https://docs.factory.ai/models.md>
- Mission 配置：<https://docs.factory.ai/missions/reference.md>

先从 `llms.txt` 重新发现页面；固定链接失效时以索引中的新地址为准。命令行行为同时以当前 `droid --help`、`droid exec --help` 和 `droid update --help` 为准。

### Ollama

- OpenAI 兼容接口：<https://docs.ollama.com/api/openai-compatibility.md>
- 模型库：`https://ollama.com/library/<model>`
- 当前账号模型目录：`GET https://ollama.com/v1/models`
- 当前路由模型信息：`POST https://ollama.com/api/show`，请求体为 `{"model":"<id>"}`

目录与 show 接口使用现有凭据，但只输出 `id`、context、capabilities 等非敏感字段。供应商路由可能把厂商最大输出收紧；用短回答请求和候选 `max_tokens` 验证，保留 HTTP 状态与脱敏错误文本。

### 模型厂商

- Z.ai 文档索引：<https://docs.z.ai/llms.txt>
- GLM 新版本迁移入口：<https://docs.z.ai/guides/overview/migrate-to-glm-new.md>
- DeepSeek 模型与价格：<https://api-docs.deepseek.com/quick_start/pricing>
- DeepSeek Chat API：<https://api-docs.deepseek.com/api/create-chat-completion>
- Kimi K3 官方模型卡：<https://github.com/MoonshotAI/Kimi-K3>
- Kimi 平台文档：<https://platform.kimi.ai/docs/guide/kimi-k3-quickstart>

具体模型页面会变化。优先从厂商索引、模型卡或当前文档导航发现，不从旧文件名推断新模型参数。

## 证据优先级

1. 当前凭据下供应商端点实际返回的模型 ID、capabilities 与参数拒绝信息。
2. 当前供应商兼容接口文档。
3. 当前模型厂商文档或官方模型卡。
4. Factory 当前设置/Mission 文档与 CLI 帮助中的字段支持。
5. [配置经验](configuration-experience.md) 中带日期的历史快照。

层级并非互相覆盖：厂商资料回答模型理论能力，供应商端点回答这条实际路由可用的能力，Factory 资料回答 Droid 如何表达它。报告中并列记录差异。

## 新鲜度门禁

- 记录核验日期、Droid 当前版本和 `droid update --check` 结果。
- 对每个模型至少取得一个当前官方来源和一个实际供应商证据。
- 页面不可达时保留已有配置，不根据搜索摘要或经验快照提高上限。
- 模型 ID、effort 或最大输出任一未确认时，不宣称真实调用验证完成。
