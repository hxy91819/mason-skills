# 离线与更新

## 目标

第一次打开后，断网刷新仍能渲染应用外壳；发版后浏览器能发现新版本，并让用户主动刷新，而不是继续吃旧缓存。

手写一个够用的 Service Worker，比引入 Workbox 更容易看清缓存边界。关键不是缓存多少，而是**不缓存什么**。

## 注册

- 只在 H5 生产构建注册。开发模式没有 `/sw.js` 产物，注册会 404，还会让热更新和调试被缓存干扰。
- 只在适配层注册，页面和 Store 不直接碰 `navigator.serviceWorker`。是否生产环境由调用方传 `enabled`，不要把构建变量写死进适配器。
- 注册参数：

```ts
navigator.serviceWorker.register('/sw.js', {
  scope: '/',
  updateViaCache: 'none',
})
```

`updateViaCache: 'none'` 让浏览器每次检查 SW 脚本都绕过 HTTP 缓存；服务端还要给 `/sw.js` 返回 `Cache-Control: no-cache`。两者缺一，发版后可能迟迟发现不了新版本。

## 缓存边界

缓存：

- 应用外壳：`/`、`/index.html`、离线页 `/static/offline.html`；
- 入口 HTML 引用的 `/assets/` 资源（带 hash，内容变化文件名变化）；
- `/static/` 下的图标、字体、Manifest 等原样拷贝的资源。

不缓存：

- `/api/` 下的所有请求，包括 SSE 流式响应；
- 所有非 GET 请求（提交、删除、上传）；
- 跨源请求；
- 带查询串的动态页面。

这些请求直接 `return`，让浏览器网络栈处理。不要用 `networkFirst` 包住 API：离线时返回一个旧的 JSON 比直接失败更难排查。

## 首访预缓存

首次访问时，页面还没被 SW 接管，入口 HTML 里的 JS/CSS 请求不会进入 `fetch` 事件。只 `cache.addAll(['/', '/index.html'])` 的结果是：断网刷新能拿到 HTML，但没有脚本，页面白屏。

正确做法：预缓存入口 HTML 后，从 HTML 里提取 `/assets/` 资源，再补缓存一轮：

```js
const html = await (await cache.match('/index.html')).text()
const assetUrls = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)]
  .map(match => match[1])
await Promise.all([...new Set(assetUrls)].map(url => cache.add(url).catch(() => undefined)))
```

单个资源失败不要拖垮整个 install；入口 HTML 和离线页必须成功。

## 请求策略

| 请求 | 策略 |
| --- | --- |
| 导航（`request.mode === 'navigate'`） | 网络优先；成功就把最新入口写入 `/index.html`；失败回退缓存的 `/index.html`，再回退 `/`，最后回退离线页 |
| `/assets/*`、`/static/*` | 缓存优先；未命中回源，成功且 `response.type === 'basic'` 才写入；失败直接抛错 |
| `/api/*`、非 GET、跨源 | 不拦截，直通网络 |

导航成功时写入的是 `response.clone()`，不能把已经消费的 body 再写缓存。`cache.put` 失败不应让导航失败。

## 版本与清理

- 源文件里写 `const SW_VERSION = '__SW_VERSION__'`，构建时替换成时间戳或提交号。`vite-sw-version.mjs` 是一个最小插件：在 `closeBundle` 阶段找到产物里的 `sw.js`，替换占位符。
- 缓存名带版本：`${CACHE_PREFIX}-${SW_VERSION}`。`activate` 时删除同一前缀下不属于当前版本的缓存，避免旧 hash 资源长期占用空间。
- 不要用 `self.skipWaiting()` 在 install 阶段强制接管。让新 SW 停在 waiting，由页面提示用户，用户确认后再 `SKIP_WAITING`。
- 重复发布同一提交时，如果版本号只取提交号，SW 不会重新安装。用时间戳或“提交号 + 构建时间”保证每次构建版本不同；代价是每次发版都会让客户端下载一次新 SW，这是可接受的。

## 更新提示

`service-worker.ts` 适配器负责：

1. 注册 SW；
2. 页面在旧 SW 控制下打开时，如果 `registration.waiting` 存在，提示更新；
3. 监听 `updatefound`，新 SW 进入 `installed` 且已有 `controller` 时才提示（首次安装不提示）；
4. 用户确认后 `worker.postMessage({ type: 'SKIP_WAITING' })`；
5. 监听一次 `controllerchange`，刷新页面一次，防止循环刷新。

提示文案和“立即刷新/稍后”按钮由应用层弹窗实现；适配器只暴露 `onUpdateReady({ apply })`。不要在适配器里写死某个 UI 库的 `showModal`。

## 静态服务器

Service Worker 必须从根作用域提供。如果构建产物在 `/static/sw.js`，服务器要把 `/sw.js` 重写到它，并返回：

- `Service-Worker-Allowed: /`
- `Cache-Control: no-cache`

其余缓存头：

| 路径 | Cache-Control | 原因 |
| --- | --- | --- |
| `/sw.js` | `no-cache` | 发版后必须重新检查脚本 |
| `/assets/*` | `public, max-age=31536000, immutable` | 文件名带 hash |
| `/static/*` | `public, max-age=86400` | 文件名通常不带 hash，给一天 |
| `/`、`/index.html`、SPA fallback | `no-cache` | 发版后马上拿到新入口 |
| `/api/*` | 由后端决定，至少 `no-store` | 不参与静态缓存 |

`assets/templates/Caddyfile.snippet` 给出最小 Caddy 片段。Nginx 等价写法是把 `location = /sw.js` 指向实际文件并加 `add_header Service-Worker-Allowed /`，其余按路径设 `expires`。

## 测试

用生产构建，不要用 dev server。测试自带一个极小静态服务器，模拟 Caddy 的 `/sw.js` 重写、缓存头和 SPA fallback；否则你测的是 dev server 的行为，不是发布后的行为。

断言：

1. `navigator.serviceWorker.ready` 后 `registration.active.state === 'activated'`。
2. 再导航一次，`navigator.serviceWorker.controller` 为真。
3. 请求一个 `/api/` 路径，Cache Storage 里没有任何 `/api/` URL。
4. Cache Storage 里有 `/index.html` 和至少一个 `/assets/` 资源。
5. 断网后刷新，应用外壳仍渲染。
6. 改 SW 版本后重新加载，新 SW 进入 `waiting`，更新提示出现；确认后只刷新一次，缓存名切到新版本。

桌面浏览器清理旧 SW 的顺序：先 `navigator.serviceWorker.getRegistrations()` 逐个 `unregister()`，再清站点数据，再硬刷新。只刷新页面不一定能清掉旧 SW；验收前确认 `navigator.serviceWorker.controller` 对应的脚本已经注销或更新。

完整骨架见 `assets/templates/e2e/pwa-offline.spec.ts`。
