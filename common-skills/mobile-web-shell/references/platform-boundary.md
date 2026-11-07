# 平台适配层边界

## 目标

让业务代码在 H5、小程序、原生壳或 SSR 之间迁移时，不需要搜遍页面找 `document`、`window`、`visualViewport`。外壳能力只有一处实现、一处测试、一处放行。

这不是“禁止使用浏览器 API”，而是把“哪些代码知道浏览器存在”收成一个可审查的边界。

## 文件职责

适配层目录通常叫 `src/platform/`。一个够用的拆分：

| 文件 | 职责 | 业务侧入口 |
| --- | --- | --- |
| `web-chrome.ts` | 写 `theme-color`，把主题和整份色板写到文档根 | 主题 Store 在路由/主题变化时调用 |
| `keyboard-viewport.ts` | 读可见视口，判断软键盘，给出 `height` / `top` / `insetBottom` | 整页输入用页面级 composable，底部弹窗用 `insetBottom` |
| `service-worker.ts` | 注册 SW，等待更新，向调用方暴露“有新版本” | 应用启动时注册一次 |
| `push.ts` | 权限、PushManager、订阅/退订、UI 状态翻译 | 通知设置页 |
| `swipe-back.ts` | 文档级边缘右滑，触发调用方注入的返回动作 | 应用启动时安装一次 |
| `navigation.ts` | 跨站跳转 | 登录跳转等 |
| `network.ts` | 把宿主 `fetch` 交给请求适配器 | 需要流式响应的请求层 |
| `dom.ts` | 查询已渲染节点 | 需要在渲染后测量的页面 |
| `route.ts` | 读 hash 路由，监听浏览器前进/后退 | 主题同步、页面生命周期 |

适配层不决定：哪些页面是 Tab、顶部用哪个色值、通知文案是什么、页面栈还有几页。这些属于应用外壳策略，放在 Store、路由配置或页面层。`swipe-back.ts` 用 `enabled()` 和 `onBack()` 注入这些判断，就是一个正确示范。

## 访问规则

1. 浏览器宿主对象只在适配层出现。
2. 适配层也写 `globalThis.document`，不写裸 `document`。这样同一份代码在 SSR、测试和小程序构建里不会因为未声明全局而直接抛错，也让 lint 有统一的匹配点。
3. 业务侧只 import 适配层函数。页面、Store、组件不写 `theme-color`、不读 `visualViewport`、不注册 Service Worker、不调用 `location.assign`。

## ESLint 规则

`assets/templates/eslint-platform-boundary.mjs` 提供可直接展开到 flat config 的片段。三层缺一不可：

```js
import { platformBoundaryConfig } from './eslint-platform-boundary.mjs'

export default [
  // ...你的基础配置
  ...platformBoundaryConfig(),
]
```

- `no-restricted-globals`：拦 `window`、`document`、`navigator`、`location`、`localStorage`、`sessionStorage`、`fetch`、`history`、`XMLHttpRequest`、`visualViewport` 等裸名。适配层也不放行。
- `no-restricted-properties`：拦 `globalThis.window`、`globalThis.document` 等属性访问。只对适配层目录放行。
- `no-restricted-syntax`：拦类型断言和方括号绕过，例如 `(globalThis as any).document`、`(globalThis as unknown as Window).document`、`globalThis['document']`。
- 可选 `no-restricted-imports`：如果项目同时支持小程序或原生壳，可以把 `axios`、`vue-router` 这类只适用于某一端的库列进去。不要默认替别的项目决定。

规则片段默认放行 `src/platform/**`；目录不同时传 `{ files, allowedFiles }`。不要用 `eslint-disable` 代替放行，也不要在业务文件里加一次性 exception。确需例外时，把该文件逐条写进 override，并在项目指南里写原因。

自检方式：在业务目录临时写一个 `const el = document.querySelector('x')`，`eslint` 必须报错；删掉临时文件后适配层必须通过。

## 框架差异

### uni-app

- 条件编译用 `// #ifdef H5` / `// #ifndef H5`。适配层可以在同一个文件里保留 H5 和小程序两条实现，导出同一个函数签名。
- H5 键盘用 `visualViewport`；小程序没有这个对象，改听 `uni.onKeyboardHeightChange`，返回 `{ open, height: null, top: 0, insetBottom }`。
- 页面导航、系统弹窗、TabBar 由 `uni.*` 管理；这些调用应留在应用层或页面层，不要塞进浏览器适配器。这样适配器搬到普通 Vue/React 时不用拆 `uni` 依赖。
- `pages.json` 里 Tab 页设 `navigationStyle: custom`，子页保留框架导航栏。Tab 页根容器用 `padding-top: env(safe-area-inset-top)`，并让背景延伸到状态栏下。
- 陷阱：uni-app H5 的 `--window-top` 在 custom 导航下不为 0。键盘打开时不要用它叠加 `offsetTop` 推算导航栏位置，否则状态栏下会留一条导航栏高度的空带。

### 普通 Vue

- 用 `.web.ts` / `.native.ts` 或 `import.meta.env` 分流，不用 `#ifdef`。
- 把键盘适配包成 composable：

```ts
// src/composables/useKeyboardViewport.ts
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { observeKeyboardViewport } from '@/platform/keyboard-viewport'

export function useKeyboardViewport() {
  const viewport = ref({ open: false, height: null, top: 0, insetBottom: 0 })
  let stop: (() => void) | undefined
  onMounted(() => { stop = observeKeyboardViewport(value => { viewport.value = value }) })
  onBeforeUnmount(() => stop?.())
  return viewport
}
```

- 路由用 Vue Router；在 `router.afterEach` 和主题 watch 里调用 `setThemeColor` / `setDocumentPalette`。
- 系统弹窗用组件库或自建 modal；把根节点色板写在 `document.documentElement` 上，弹窗挂在 `body` 也能拿到变量。
- SW 注册在 `main.ts` 里调用一次，是否生产环境由调用方传入 `enabled`，不要把 `import.meta.env` 写进适配器。

### React

```tsx
// src/hooks/useKeyboardViewport.ts
import { useEffect, useState } from 'react'
import { observeKeyboardViewport, type KeyboardViewport } from '@/platform/keyboard-viewport'

export function useKeyboardViewport(): KeyboardViewport {
  const [viewport, setViewport] = useState<KeyboardViewport>({
    open: false, height: null, top: 0, insetBottom: 0,
  })
  useEffect(() => observeKeyboardViewport(setViewport), [])
  return viewport
}
```

- React 没有条件编译；用文件后缀、构建变量或运行时能力判断。
- 路由用 React Router；`useEffect` 监听 `location` 变化同步 theme-color。
- 注意 effect 清理：`observeKeyboardViewport` 返回取消函数，直接 `return observeKeyboardViewport(...)` 即可。

## 搬迁步骤

1. 复制 `assets/templates/platform/` 到目标项目的 `src/platform/`。
2. 复制并接入 ESLint 片段，先跑一次 lint，确认适配层通过、业务违规被抓。
3. 把调用方接上：启动时注册 SW、安装边缘返回、初始化主题同步；页面按需用键盘 composable/hook。
4. 用生产构建跑 `assets/templates/e2e/` 里的键盘和安全区骨架，把选择器改成目标页面。
5. 真机确认键盘上推、standalone、安全区和系统弹窗。

## 完成条件

- 业务目录搜不到裸浏览器对象和 `globalThis.<host>`（适配层除外）。
- 适配层文件都有明确职责；没有把“哪些页面是 Tab”“通知文案”这类应用策略塞进来。
- 新增浏览器能力时，先加适配层函数和调用方说明，再改页面。
