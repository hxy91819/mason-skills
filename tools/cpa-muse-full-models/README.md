# CLIProxy Muse Full models

CLIProxyAPI v8 的 Meta 静态目录暂未收录 Muse Wonder Full。本扩展通过公开的原生 `ModelRegistrar` ABI 补充两个准确的模型 ID，供现有 Meta 凭证和内置执行器使用：

- `muse-wonder-full-1.0`
- `muse-wonder-full-1.0-contributor`

扩展只提供目录元数据，保留原生 Meta 模型目录及其远程更新；不声明 `ModelProvider`，因为后者会接管并替换原生 OAuth 模型发现。认证、刷新和请求执行仍由 CLIProxy 负责。当前凭证必须具有 Full 权限；目录注册本身不会授予订阅权限。普通 API key 的权限和 Muse Code 订阅凭证不同，安装前应以实际请求核对。

元数据使用 Muse 系列的 1,048,576 context、65,536 输出上限和 minimal/low/medium/high/xhigh/max 推理级别。BB Pi 配置应使用 `openai-responses`，模型 ID 保持原样。Contributor 是独立的上游模型选择，不是别名。

## 构建与验证

```sh
sh build.sh
python3 test_abi.py
# Linux arm64 安装包（安装交叉编译器及其 libc headers 后）：
CC=aarch64-linux-gnu-gcc sh build.sh dist/arm64
python3 package.py dist/arm64/cpa-muse-full-models.so
```

构建产物为 `dist/cpa-muse-full-models.so`，用于 Linux；用 CLIProxy 所在架构的 C 编译器构建。测试通过 `ctypes` 调用真实 ABI，验证生命周期、准确路由和分配/释放边界。

## 安装与验收

将 `.so` 安装到 CLIProxy 的 `plugins.dir`，并启用 `plugins.configs.cpa-muse-full-models.enabled`。也可在 v8 Plugin Store 中添加本目录的 [registry.json](registry.json) 作为自定义源，使用 `direct` install artifact（平台、HTTPS URL、SHA-256 和 size）安装。

`artifacts/linux-arm64/` 保留由本目录源码构建的版本化安装包，供无法回连构建机器的代理下载。Plugin Store 的 direct artifact 必须为 ZIP，根目录只放 `cpa-muse-full-models.so`；裸 `.so` 只能手动复制安装。`package.py` 检查架构及注册版本，生成时间戳固定的 ZIP，并更新 registry 的 SHA-256/size。

已经发布的版本文件不覆盖；更新时同时更新 C 的 `PLUGIN_VERSION` 和 registry 的版本，再构建新版本包。历史 v0.1.0 裸库保留为构建快照，当前可通过 Store 安装的版本为 v0.1.1 ZIP。安装包不含凭证。临时下载源只在安装期间启用，安装后移除。若使用 HTTP 临时源，CLIProxy 要求匹配该地址的 `store-auth` 规则：`type: none`、`apply-to: [registry, artifact]`、`allow-insecure: true`；安装后同时删除该临时规则。

验收必须同时核对客户端 `/v1/models`、原有 Meta 模型仍可列举、Full 两版的 Responses 请求（返回的模型 ID 一致），以及 BB 的 `provider models pi`。如上游目录正式收录 Full，可禁用并删除这个扩展，保留 BB 中的模型 ID；无需改登录凭证。

运行地址、接入 key、账号和机器备份放在机器配置或线程工件中，不进入源码。

参考：[CLIProxy ABI 示例](https://github.com/router-for-me/CLIProxyAPI/tree/bf934162/examples/plugin/model/c)、[模型 registrar 契约](https://github.com/router-for-me/CLIProxyAPI/blob/bf934162/sdk/pluginapi/types.go)、[Muse 模型说明](https://dev.meta.ai/docs/models)。
