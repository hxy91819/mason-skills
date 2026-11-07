# PWA 外壳

## 目标

从浏览器标签页打开时是一个网页；从主屏幕图标打开时，没有地址栏、状态栏颜色正确、启动不白屏、图标不被裁切。离线与更新是下一层能力，不靠 Manifest 实现。

## Manifest

放在 `src/static/manifest.webmanifest` 或等价目录，构建后由 `index.html` 的 `<link rel="manifest" href="/static/manifest.webmanifest">` 引用。最小字段：

```json
{
  "name": "应用全名",
  "short_name": "短名",
  "description": "一句话说明",
  "lang": "zh-CN",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "background_color": "#F5F1E9",
  "theme_color": "#123047",
  "icons": [
    { "src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any" },
    { "src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any" },
    { "src": "/static/icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ]
}
```

- `start_url` 和 `scope` 用根路径，除非应用确实部署在子路径；两者不一致会让主屏幕入口跳出作用域。
- `purpose: maskable` 的图形必须留在中心安全区。系统可能裁成圆形、圆角方形或任意形状；把 logo 铺满整张图是最常见的裁切事故。
- `background_color` 用于启动时的画布，`theme_color` 用于浏览器/任务切换器的主题色。它们不必等于运行时的 `meta[name=theme-color]`，但默认值应和首屏一致。
- 图标、启动图、Manifest 都要随构建产物发布，并用 HTTP 200 验证。主屏幕入口出现空白图标，通常不是 Manifest 语法问题，而是路径 404 或 `Content-Type` 不对。

## iOS meta 与启动图

```html
<meta name="viewport" content="width=device-width, user-scalable=no, initial-scale=1.0, maximum-scale=1.0, minimum-scale=1.0, viewport-fit=cover" />
<meta name="theme-color" content="#F5F1E9" />
<meta name="apple-mobile-web-app-capable" content="yes" />
<meta name="mobile-web-app-capable" content="yes" />
<meta name="apple-mobile-web-app-title" content="短名" />
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
<link rel="manifest" href="/static/manifest.webmanifest" />
<link rel="apple-touch-icon" sizes="180x180" href="/static/icons/apple-touch-icon.png" />
```

- `viewport-fit=cover` 是使用 `env(safe-area-inset-*)` 的前提；没有它，安全区变量在 iOS 上拿不到有效值。
- `apple-mobile-web-app-capable` 和 `mobile-web-app-capable` 都写，兼容不同 iOS 版本和浏览器。
- `black-translucent` 让页面背景延伸到状态栏下，同时要求页面自己让出顶部安全区；如果页面没有 `padding-top: env(safe-area-inset-top)`，标题会被状态栏压住。
- 启动图用 `apple-touch-startup-image`，每个 `<link>` 带 `media` 条件，覆盖“逻辑分辨率 × 像素比”和竖屏方向：

```html
<link rel="apple-touch-startup-image"
  media="(device-width: 393px) and (device-height: 852px) and (-webkit-device-pixel-ratio: 3) and (orientation: portrait)"
  href="/static/splash/splash-1179x2556.png" />
```

`393 × 3 = 1179`，`852 × 3 = 2556`。新增机型时，图片尺寸和 `media` 条件要同时补齐；只改图片不改条件，或者只改条件不补图，都会回退到白屏。Apple 的归档文档确认过该 link 的历史支持，但当前所有 iOS 版本的完整兼容矩阵没有官方保证，交付前用目标机型真机看一眼启动过程。

## 安全区与页头

- 页面根容器从视口顶端开始，背景铺到状态栏下；内容区加 `padding-top: env(safe-area-inset-top)`。只给内容加 padding、把根容器也往下推，会在状态栏下留一条背景断层。
- 底部固定操作区加 `padding-bottom: env(safe-area-inset-bottom)`，否则会被 Home Indicator 盖住。
- Tab 页建议自绘页头，不显示框架导航栏；子页保留框架导航栏和返回按钮。这样 Tab 页的首屏更像原生，子页仍有明确的返回路径。
- 安全区不能只用固定像素模拟。浏览器窗口变化、横竖屏切换、分屏和键盘弹出都会改变可用区域。

## theme-color 跟随当前页

`meta[name=theme-color]` 是运行时值，不是一次写死：

- Tab 页顶部是页面背景，取 `bgColor`；子页顶部是框架导航栏，取 `panelBg`。两者在深色/浅色主题下各有一份。
- 路由变化、主题切换、浏览器前进/后退、`navigateBack` 都要同步。只在页面 `onMounted` 里设一次，返回 Tab 页后状态栏会停在子页颜色。
- 路由尚未就绪时用默认背景色，和 `index.html` 里的初始 meta 一致，避免首屏闪错色。
- 截图看不到状态栏颜色，验收要直接断言 `meta[name=theme-color]` 的值。

## 文档根色板

系统弹窗（`uni.showModal`、Toast、ActionSheet 或自建 modal）、下拉刷新指示器、iOS 回弹露出的画布，都在页面容器之外。它们拿不到页面容器上的 CSS 变量。

做法：把当前主题和整份色板写到 `document.documentElement`：

```ts
root.dataset.theme = theme
for (const [name, value] of Object.entries(palette)) {
  root.style.setProperty(`--app-${name}`, value)
}
```

然后 `html[data-theme] .modal`、`body`、页面外画布、刷新指示器统一读这组变量。不要给系统弹窗另写一套浅色底，也不要用 `prefers-color-scheme` 绕开应用内主题；用户选了深色，系统弹窗就应该是深色。

## iOS 主屏幕能力边界

- Web Push 从 iOS/iPadOS 16.4 起支持，但只对“添加到主屏幕”的 Web App 生效，普通 Safari 标签页不能订阅。
- iOS 主屏幕 Web App 没有系统返回手势，需要应用自己补边缘右滑返回（见 `interaction-polish.md`）。
- 没有受支持的网页 API 隐藏键盘上方的表单辅助栏（∧ ∨ ✓），详见 `keyboard-viewport.md`。
- `apple-touch-startup-image` 是历史支持能力，不是当前所有机型的兼容保证；把它当作渐进增强，启动图缺失时至少保证 `background_color` 正确。
- 主屏幕安装、通知权限、推送送达都必须在真机验证；桌面 Chromium 的 PWA 模拟不能证明 iOS 行为。

## 验收

- Manifest 可访问，字段和图标尺寸正确；maskable 图标在圆形/圆角裁切下不丢主体。
- 所有 `apple-touch-icon` 和 `apple-touch-startup-image` 返回 200，`Content-Type` 为图片。
- `meta[name=theme-color]` 在 Tab 页/子页、浅色/深色、前进/后退后都正确。
- CDP 设 top 59 / bottom 34 后，Tab 页标题在安全区之下，页面根从视口顶端开始。
- 系统弹窗和深色下拉的画布颜色来自根色板，不出现白块。
