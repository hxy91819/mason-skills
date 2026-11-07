# 浏览器适配层模板

复制整个目录到目标项目的 `src/platform/`，按项目改 import 路径和文案。模板只依赖浏览器标准 API，不依赖 uni-app、Vue 或 React；框架调用留在应用层。

| 文件 | 职责 |
| --- | --- |
| `web-chrome.ts` | 写 `theme-color`；把主题和整份色板写到文档根 |
| `keyboard-viewport.ts` | 读 `visualViewport`，判断软键盘，输出 `height` / `top` / `insetBottom` |
| `service-worker.ts` | 注册 SW；通过 `onUpdateReady` 把“有新版本”交给应用层 |
| `push.ts` | 权限、PushManager、订阅/退订、UI 状态纯函数 |
| `swipe-back.ts` | 文档级边缘右滑；`enabled()` / `onBack()` 由调用方注入 |
| `navigation.ts` | 跨站跳转 |
| `network.ts` | 把宿主 `fetch` 交给请求适配器 |
| `dom.ts` | 查询已渲染节点 |
| `route.ts` | 读 hash 路由；监听浏览器前进/后退 |

## 接入顺序

1. 复制目录，接入 `eslint-platform-boundary.mjs`，先跑 lint。
2. 在应用启动处调用一次 `registerServiceWorker({ enabled: import.meta.env.PROD, onUpdateReady })`、`installEdgeSwipeBack({ enabled, onBack })`。
3. 在主题/路由变化处调用 `setThemeColor` 和 `setDocumentPalette`。
4. 页面按需用 `observeKeyboardViewport`；底部弹窗用 `insetBottom`。

## 框架差异

- **uni-app**：H5 分支用这些模板；小程序分支把 `keyboard-viewport.ts` 换成 `uni.onKeyboardHeightChange`，把 `service-worker.ts` 置空。系统弹窗、页面栈判断留在应用层，不要塞进适配器。H5 custom 导航下 `--window-top` 不为 0，键盘布局不要叠加它。
- **普通 Vue**：用 composable 包装 `observeKeyboardViewport`；路由用 Vue Router；弹窗用组件库；SW 是否生产环境由 `main.ts` 传入。
- **React**：用 `useEffect` 包装；effect 直接返回 `observeKeyboardViewport` 的取消函数；路由用 React Router；不要用条件编译注释。

## 注意

- 适配器只提供能力，不决定页面策略。`service-worker.ts` 不直接弹 `uni.showModal`，`swipe-back.ts` 不直接 `uni.navigateBack`；这样换框架时只改调用方。
- `push.ts` 里的文案是通用默认值，按产品改。不要把 VAPID 私钥、服务端 key 或业务数据带进前端。
- `keyboard-viewport.ts` 的 120px 阈值是经验值；如果目标机型误判，先调整阈值和 `isCoarsePointer`，不要改成“只要 resize 就算键盘”。
