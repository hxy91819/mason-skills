---
name: mobile-web-shell
description: 手动把移动 H5/PWA 外壳打磨到接近原生：PWA 安装、键盘与安全区、离线更新、手势与系统弹窗、去网页感与 Web Push。
disable-model-invocation: true
triggers:
  - user
---

# 移动 Web 外壳

用户说“像 App”“去网页感”“添加到主屏幕”“键盘顶起”“离线可用”“发版后提示更新”“手机上能收到通知”时，用这套清单。也可以在新移动 H5 项目立项时按顺序落地。它处理浏览器外壳，不替代业务页面设计。

## 先定适配层边界

外壳能力集中在一个平台适配层（下称 `src/platform/`），业务页面、组件和 Store 只调用适配层函数。

- 浏览器宿主对象只在适配层出现，且一律经 `globalThis.xxx` 访问。裸全局名（`document`、`window`、`fetch` 等）全项目禁止，适配层也不例外。
- 用 ESLint 三层拦截：`no-restricted-globals` 拦裸名，`no-restricted-properties` 拦 `globalThis.window/document/navigator/location/visualViewport/localStorage/sessionStorage/fetch/history/XMLHttpRequest`，`no-restricted-syntax` 拦类型断言和方括号访问。`src/platform/**` 用 override 放行后两条。
- 例外只按文件写进 override，并在指南里写原因。不要用别名、断言或跨层 import 绕过。
- 适配层只提供能力，不决定“哪些页面是 Tab、顶部用什么颜色、通知文案是什么”。这些是应用外壳策略，留在应用层。

各文件职责、可复制的适配器和 ESLint 片段见 [references/platform-boundary.md](references/platform-boundary.md) 与 `assets/templates/`。

## 按这个顺序做

先做用户第一眼能感知、做错会直接坏交互的部分；推送放最后，因为它依赖前面的 Service Worker 与主屏幕安装。

### 1. PWA 外壳

- 提供 Web App Manifest：`name`、`short_name`、`start_url`、`scope`、`display: standalone`、主题/背景色、192/512 图标，以及一张留足中心安全区的 `maskable` 图标。
- `index.html` 补齐 iOS meta、`apple-touch-icon` 和按“逻辑分辨率 × 像素比”匹配的竖屏启动图；新增机型时图片和 `media` 条件同时补齐。
- `viewport` 带 `viewport-fit=cover`。Tab 页用自绘页头，页面根容器从视口顶端开始，内容用 `env(safe-area-inset-top)` 让开状态栏；子页保留框架导航栏以提供返回按钮。
- `theme-color` 跟随当前页顶部：Tab 页取页面背景，子页取导航栏背景；路由变化、主题切换、浏览器前进/后退都要同步。默认值写在 HTML 里，避免首屏闪错色。
- 系统弹窗、Toast、ActionSheet 和下拉刷新露出的画布在页面容器之外，要把整份主题色板写到文档根（`data-theme` + CSS 变量），不能只靠页面容器上的变量。

细节和 iOS 能力边界见 [references/pwa-shell.md](references/pwa-shell.md)。

### 2. 键盘与视口

- 键盘状态只有一个入口。页面需要“输入区贴住键盘”时调用统一的 composable/hook，不在业务代码里读 `visualViewport`、`innerHeight` 或 `matchMedia`。
- iOS 弹键盘时布局视口不变，只缩小 `visualViewport`，还可能把可见区域上推 `offsetTop`。贴键盘布局只用可见区域坐标：`top = offsetTop`、`height = visualViewport.height`；底部被挡住的高度是 `innerHeight - offsetTop - height`。
- 键盘打开时隐藏 TabBar、收起大页头，把可见区域留给内容和输入框。整页高度用 `100dvh`，保留 `100vh` 回退。
- 普通表单优先放文档流。底部弹窗内放输入框时，用 `insetBottom` 把底边抬到可见区域底边，高度不超过可见高度，确认按钮留在弹窗底部；必须在 iPhone 真机验证。
- 输入语义按内容选：时间保留文本键盘，人数用数字键盘，搜索用 `inputmode="search"`，并用 `enterkeyhint` 标出“下一项/完成/搜索”。

原理、检测阈值和 `--window-top` 陷阱见 [references/keyboard-viewport.md](references/keyboard-viewport.md)。

### 3. 离线与更新

- Service Worker 只在生产构建注册，且只经适配层注册。开发模式没有 `/sw.js` 产物，不注册，避免缓存干扰调试。
- 只缓存应用外壳和带 hash 的 `/assets/`、`/static/` 静态资源。导航请求网络优先，失败回退缓存的入口 HTML，再失败回退离线页；`/api/` 与所有非 GET 请求直通网络，不写入 Cache Storage。
- 首次访问时页面还没被 SW 接管，入口 HTML 里的 JS/CSS 不会经过 `fetch`。预缓存阶段要额外从 `index.html` 提取 `/assets/` 资源补缓存，否则首次离线只有 HTML 没有脚本。
- 版本占位符由构建插件替换；版本变化才会安装新 SW。新 SW 进入 waiting 时提示“有新版本”，确认后 `SKIP_WAITING`，并在 `controllerchange` 时只刷新一次。
- 静态服务器配合：`/sw.js` 从根作用域提供且 `no-cache`，`/assets/*` 长缓存，`/static/*` 一天缓存，入口 HTML `no-cache`，SPA 未知路径回退 `index.html`。

缓存策略、构建插件和 Caddy 片段见 [references/offline-update.md](references/offline-update.md)。

### 4. 交互细节

- 下拉刷新只开在有列表或数据读取的页面，回调里调用已有加载函数，并在 `finally` 停止刷新。刷新时露出的画布颜色跟随主题。
- iOS 主屏幕模式没有系统返回手势时，补一个应用级边缘右滑返回：左缘窄带起手、水平向右超过阈值才触发；输入框聚焦、横向滚动容器内起手、Tab 页或页面栈只有一页时跳过。方向未锁定前让位给页面滚动。
- `html`、`body` 设 `overscroll-behavior: none`，内部滚动区设 `contain`，避免滚动链把内容拖出外壳。
- 关闭点击高亮、长按菜单和默认文本选择；输入框、`textarea`、`contenteditable` 和明确标为可复制的正文保持可选中。
- 系统弹窗和下拉刷新共用根节点色板；不要给它们另写一套浅色底。

手势、触摸和系统弹窗的细节见 [references/interaction-polish.md](references/interaction-polish.md)。

### 5. 质感

- 页面切换用短促的位移/淡入，Tab 切换用淡入，子页从右侧推入；尊重 `prefers-reduced-motion`。
- 按钮按下有轻微缩放或颜色反馈，键盘焦点有可见 focus ring，但不要给所有元素加过渡。
- 首屏慢接口用骨架屏，空状态用真实空文案；避免“正在读取”闪一下再变空列表。
- 检查首屏白闪、深色下拉白块、状态栏颜色跳变和固定底栏遮挡；这几处最容易暴露“网页感”。
- 图标、启动图、字体和间距按同一套尺度收口，不在页面里散落魔法数。

### 6. Web Push（按需）

- 先判断能力再显示开关：不支持、iOS 未安装到主屏幕、非安全上下文、服务端未启用、权限被拒绝、已订阅/未订阅，各有明确文案和可切换状态。
- iPhone/iPad 需 iOS 16.4+，先在 Safari“分享 → 添加到主屏幕”，再从主屏幕图标打开；站内标签页不能订阅。
- 订阅要幂等：已有浏览器订阅直接复用；关闭时先取消浏览器订阅，再把 endpoint 交给服务端删除。
- Service Worker 的 `push` 只接受字符串字段和以 `/` 开头的站内路径；`notificationclick` 优先聚焦同源窗口，再导航到目标页，没有窗口才新开。
- VAPID 三项要么全填、要么全空；服务端关闭时前端显示未启用，不报错。

能力矩阵、订阅状态机和测试方法见 [references/push.md](references/push.md)；国内发布与登录门槛见 [references/cn-distribution.md](references/cn-distribution.md)。

## 框架差异

这套实现最初落在 uni-app 的 H5 构建上。搬到普通 Vue/React 时，保留浏览器核心，替换框架调用：

| 能力 | uni-app 写法 | 普通 Vue/React |
| --- | --- | --- |
| 条件编译 | `// #ifdef H5` / `// #ifndef H5` | 用 `.web.ts` / `.native.ts` 或构建变量分流 |
| 页面导航 | `uni.navigateTo` / `uni.navigateBack` | Vue Router / React Router |
| 系统弹窗 | `uni.showModal` / `uni.showToast` | 自建或组件库的 modal/toast |
| 键盘事件 | H5 用 `visualViewport`；小程序用 `uni.onKeyboardHeightChange` | 只用 `visualViewport`；原生壳用原生键盘插件 |
| 页面配置 | `pages.json` 的 `navigationStyle: custom`、`enablePullDownRefresh` | 路由 meta、布局组件、自建下拉刷新 |
| 文档根 | `uni-page-wrapper` 等框架容器 | `#app` 根节点与 `html/body` |

uni-app 的 custom 导航有一个额外陷阱：`--window-top` 在 H5 下不为 0，键盘打开时不要把它叠加到 `offsetTop` 上推算导航栏位置，否则状态栏下会留一条空带。普通 Vue/React 没有这个变量，但同样不要把 `innerHeight` 和 `visualViewport.offsetTop` 混用。

## 验证

用生产构建验，不用 dev server：

1. 基线视口 `393 × 852`，同时看 `402 × 874`。Chromium 用 CDP `Emulation.setSafeAreaInsetsOverride` 模拟 top 59 / bottom 34 的安全区。
2. 键盘：注入可控的 `visualViewport`，分别设 `offsetTop = 0` 和 `35`，断言输入区底边等于 `offsetTop + height`、页面顶边等于 `offsetTop`、TabBar 隐藏、输入内容不丢。
3. 安全区：断言 Tab 页标题在安全区之下，页面根从视口顶端开始；子页保留框架导航和返回按钮。
4. 离线：先等 `navigator.serviceWorker.ready`，再导航一次让 SW 接管；断网刷新后应用外壳仍渲染，`/api/` 不出现在 Cache Storage，带 hash 的 `/assets/` 已缓存。
5. 更新：改 SW 版本触发 waiting，断言更新提示出现；确认后只刷新一次，缓存名切到新版本。
6. 交互：用 CDP 派发触摸序列测下拉刷新和边缘返回；断言输入框的 `inputmode` / `type` / `enterkeyhint`；深色下拉断言 `body` 和刷新指示器不是白色。
7. 请求 mock 只按 `new URL(url).pathname.startsWith('/api/')` 拦截。不要用 `**/api/**`：在 dev server 下它可能把源码模块 URL 也当成接口，导致页面根本没加载。

浏览器模拟不出来的情况，交付前用真机确认：iOS 键盘把布局视口上推、主屏幕 standalone 外壳、安全区与状态栏的实际颜色、Web Push 的真实订阅与送达、系统弹窗/表单辅助栏。模拟通过不等于真机通过。

可复制的测试骨架在 `assets/templates/e2e/`，测试边界和排错顺序见 [references/verification.md](references/verification.md)。

## 已知不可修复

iOS 键盘上方的 ∧ ∨ ✓ 表单辅助栏由 WebKit 绘制，网页没有受支持的 API 可以隐藏。不要为它写兼容代码，也不要把“没找到 API”说成“永远不存在”。

## 完成条件

- 适配层边界生效：业务侧没有裸浏览器对象，ESLint 对违规文件报错，适配层自身通过。
- 清单里的优先级逐项过完；每项都有生产构建上的可观察验证，或明确标为“仅真机可验”。
- PWA、键盘、离线、更新、手势、系统弹窗中至少触及本次改动的那几项已复查；没有用源码正则或单元测试替代真实页面验证。
- 真机边界、未验证项和已知不可修复项写进交付说明。

## 资产与引用

| 路径 | 内容 | 什么时候读 |
| --- | --- | --- |
| `assets/templates/platform/` | 可复制的浏览器适配层 | 新建或搬迁外壳能力 |
| `assets/templates/eslint-platform-boundary.mjs` | 适配层边界的 flat config 片段 | 接入 lint |
| `assets/templates/sw.js` | 离线、更新、可选推送的 Service Worker | 做 PWA 离线 |
| `assets/templates/vite-sw-version.mjs` | 构建时替换 SW 版本 | 用 Vite 构建 |
| `assets/templates/Caddyfile.snippet` | SW 与静态资源缓存头 | 配静态服务器 |
| `assets/templates/manifest.webmanifest` | Manifest 模板 | 做“添加到主屏幕” |
| `assets/templates/index-head.html` | iOS meta 与启动图片段 | 同上 |
| `assets/templates/e2e/` | 键盘、安全区、离线的 Playwright 骨架 | 写验收 |
| `references/platform-boundary.md` | 适配层职责、lint 规则、例外政策 | 接入或评审边界 |
| `references/pwa-shell.md` | Manifest、iOS meta、theme-color、安全区 | 做 PWA 外壳 |
| `references/keyboard-viewport.md` | iOS 视口模型、检测、弹窗布局 | 处理键盘问题 |
| `references/offline-update.md` | SW 缓存、首访预缓存、更新流程 | 做离线与发版提示 |
| `references/interaction-polish.md` | 手势、滚动、选择、输入、系统弹窗 | 去网页感 |
| `references/push.md` | 能力矩阵、订阅、SW 推送、测试 | 做 Web Push |
| `references/verification.md` | Playwright/CDP 手法与真机边界 | 写验收 |
| `references/cn-distribution.md` | 国内发布渠道与登录门槛（带来源） | 面向大陆用户发布 |
