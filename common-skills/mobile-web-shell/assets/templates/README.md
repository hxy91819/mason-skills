# 模板使用说明

这些模板来自一个已在真实移动 H5 项目验证过的外壳实现，去掉了项目名、业务文案、品牌色和真实域名。复制后按项目替换参数。

## 文件

| 路径 | 用途 |
| --- | --- |
| `platform/` | 浏览器适配层；只依赖标准 API |
| `eslint-platform-boundary.mjs` | 适配层边界的 flat config 片段 |
| `sw.js` | 离线、更新、可选推送的 Service Worker |
| `vite-sw-version.mjs` | Vite 构建时替换 SW 版本 |
| `Caddyfile.snippet` | `/sw.js`、静态资源、SPA fallback 的缓存头 |
| `manifest.webmanifest` | PWA Manifest 模板 |
| `index-head.html` | iOS meta、Manifest、启动图 |
| `e2e/keyboard-layout.spec.ts` | 模拟键盘与 `visualViewport` |
| `e2e/safe-area.spec.ts` | CDP 安全区模拟 |
| `e2e/pwa-offline.spec.ts` | 生产构建的离线和更新验收 |

## 参数

HTML、Manifest、Caddy 片段使用 `__TOKEN__` 占位：

| 占位 | 说明 |
| --- | --- |
| `__APP_NAME__` / `__APP_SHORT_NAME__` / `__APP_DESCRIPTION__` | 应用名、短名、描述 |
| `__THEME_COLOR__` / `__BACKGROUND_COLOR__` | 首屏主题色、背景色 |
| `__ICON_192__` / `__ICON_512__` / `__ICON_MASKABLE_512__` | 图标路径 |
| `__MANIFEST_HREF__` / `__APPLE_TOUCH_ICON__` | Manifest、iOS 图标路径 |
| `__SPLASH_*__` | 启动图路径 |
| `__SITE_ADDRESS__` / `__WEB_ROOT__` / `__API_UPSTREAM__` / `__SERVICE_WORKER_FILE__` | Caddy 站点、根目录、API 上游、SW 实际文件 |

`sw.js` 只有 `__SW_VERSION__` 一个占位，由 `vite-sw-version.mjs` 替换；`CACHE_PREFIX`、`DEFAULT_NOTIFICATION_URL`、`PRERECACHE_URLS` 按项目改。

`sw.js` 默认预缓存 `/`、`/index.html`、`/static/offline.html`；确保离线页随构建产物发布，否则 install 会失败。图标路径也要和 Manifest 一致。

## 接入顺序

1. 复制 `platform/` 到 `src/platform/`，按项目改 import 路径。
2. 在 ESLint flat config 里展开 `platformBoundaryConfig()`。
3. 在 `index.html` 里放入 `index-head.html` 的内容并替换占位；把 `manifest.webmanifest` 放到静态目录。
4. 把 `sw.js` 放到 `src/static/sw.js`，在 Vite 配置里加 `serviceWorkerVersionPlugin()`。
5. 在应用启动处注册 SW、安装边缘返回、初始化主题同步。
6. 用 `Caddyfile.snippet` 或等价的 Nginx 配置设置缓存头。
7. 复制 `e2e/` 到项目的 Playwright 目录，替换选择器和路由，先跑生产构建，再跑测试。

## 验证

- `eslint src/`：业务文件写裸 `document` 必须报错，适配层通过。
- `vue-tsc --noEmit`（或 `tsc --noEmit`）：适配层类型检查通过。
- Playwright：键盘、安全区、离线三条骨架按目标应用改完后能跑通。
- 真机：iOS 键盘上推、standalone 外壳、安全区、系统弹窗、Web Push 送达。

模板不包含业务页面、登录、后端订阅接口和品牌资源；这些需要按项目补齐。
