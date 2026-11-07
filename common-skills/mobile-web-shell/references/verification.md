# 验证方法与模拟边界

## 基线

- 手机视口：`393 × 852`（iPhone 16 一代的 CSS 像素），同时看 `402 × 874`。
- 安全区：Chromium CDP `Emulation.setSafeAreaInsetsOverride`，常用 top 59 / bottom 34；刘海较浅的机型可用 top 47 / bottom 34。断言安全区逻辑时用 59 更严格。
- 主题：浅色和深色都跑一遍；`page.emulateMedia({ reducedMotion: 'reduce' })` 减少动画干扰截图和坐标断言。
- 构建：用生产构建（`vite build` / `uni build -p h5`）加静态服务器，不用 dev server。dev server 的模块 URL、HMR 和 SW 行为都和发布后不同。

## 请求 mock 的坑

只按 pathname 拦截：

```ts
await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ json: { data: [] } }))
```

不要用：

```ts
await page.route('**/api/**', ...) // 可能把 dev 源码模块 URL 也当成接口
```

在 dev server 下，源码模块路径可能包含 `/api/`，glob 会把它们一起拦掉，页面根本没加载，测试却可能把“空白页”当成业务错误。用 `URL.pathname` 判断最稳。

## 安全区

```ts
const cdp = await page.context().newCDPSession(page)
await cdp.send('Emulation.setSafeAreaInsetsOverride', {
  insets: { top: 59, bottom: 34, left: 0, right: 0 },
})
```

断言：

- `meta[name=viewport]` 含 `viewport-fit=cover`。
- Tab 页标题的 `boundingBox().y >= 59`。
- 页面根容器的 `y <= 0.5`，背景延伸到状态栏下。
- 子页有框架导航栏和返回按钮；Tab 页没有。
- 底部最后一个 Tab 项距视口底部至少 33px（34 的安全区减 1px 误差）。

## 键盘

注入可控的 `visualViewport`，见 `keyboard-viewport.md`。断言：

- 输入区底边等于 `offsetTop + height`。
- 页面根顶边等于 `offsetTop`。
- TabBar 隐藏，页头收起的元素隐藏。
- 输入内容保留，发送按钮可见。
- 键盘关闭后布局恢复。
- 键盘打开时程序化跳到其他页面，目标页的 TabBar 正常显示。

浏览器模拟只验证“代码是否按 `visualViewport` 坐标布局”，不能证明 iOS 真的这样推布局视口。真机必须再看一次。

## 主题与系统弹窗

- `meta[name=theme-color]`：Tab 页等于页面背景，子页等于导航栏背景；浅色/深色、前进/后退后都正确。
- `html[data-theme]` 和根 CSS 变量存在。
- 系统弹窗（`.uni-modal` 或自建 modal）的背景色等于当前主题卡片色。
- 深色下拉：`document.body` 背景不是白色，刷新指示器背景不是白色。
- 截图看不到状态栏颜色，必须断言 meta 值。

## 触摸

Playwright 没有内置滑动 API，用 CDP 派发真实触摸序列：

```ts
async function touchSwipe(page, fromX, fromY, toX, toY, steps = 18) {
  const cdp = await page.context().newCDPSession(page)
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: fromX, y: fromY }] })
  for (let step = 1; step <= steps; step += 1) {
    await cdp.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: [{
        x: fromX + (toX - fromX) * step / steps,
        y: fromY + (toY - fromY) * step / steps,
      }],
    })
    await page.waitForTimeout(16)
  }
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
  await cdp.detach()
}
```

- 下拉刷新：从页面中部向下拖超过触发距离（例如 150px），断言列表接口重新请求。mock 只拦 `/api/`，并记录请求次数。
- 边缘返回：从左缘 8px 起手向右 200px，断言回到上一页；从页面中部起手、Tab 页起手都不触发。
- 方向锁定：斜向滑动不吞页面滚动。

## 离线

1. 等 `navigator.serviceWorker.ready`，确认 `registration.active.state === 'activated'`。
2. 再导航一次，确认 `navigator.serviceWorker.controller` 为真。
3. 请求一个 `/api/` 路径，确认 Cache Storage 没有 `/api/` URL。
4. 确认 Cache Storage 有 `/index.html` 和至少一个 `/assets/`。
5. `context.setOffline(true)`，刷新，确认应用外壳仍渲染。
6. 清理旧 SW：`getRegistrations()` 逐个 `unregister()`，清站点数据，再硬刷新。只刷新不一定能清掉旧 SW；验收前确认 controller 对应的脚本已注销或更新。

## 更新

- 先让现有 SW 控制页面，再改服务端返回的 `sw.js` 版本（测试服务器可动态替换版本字符串）。
- 重新加载，断言“有新版本”提示出现，`registration.waiting.state === 'installed'`。
- 点击“立即刷新”，断言只发生一次导航，缓存名包含新版本。
- 不要在 install 阶段 `skipWaiting`，否则测不到 waiting 和提示。

## Web Push

见 `push.md`。至少跑订阅 UI 状态机和 SW 展示通知两条；真实送达、系统通知样式、点击唤起必须真机。

## 浏览器模拟不出的情况

交付说明里逐项标注，不要把模拟通过写成真机通过：

- iOS 键盘把布局视口上推、键盘动画、系统表单辅助栏。
- 主屏幕 standalone 外壳、状态栏样式、启动图。
- 安全区在横屏、分屏、不同机型上的实际值。
- 系统通知的显示、点击、权限设置路径。
- 真实网络下的 SW 更新检查、CDN/代理缓存行为。
- 深色模式下系统弹窗、下拉刷新、回弹画布的真实合成结果。

## 截图与证据

- 关键状态截图：键盘打开、键盘关闭、安全区、深色系统弹窗、下拉刷新。
- 截图文件名带主题和状态，便于对照。
- 记录视口、安全区、主题、路由、账号角色和构建产物；没有这些，截图无法复现。
- 截图只作辅助，坐标和 DOM 断言才是回归证据。
